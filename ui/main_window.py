import os
import tempfile

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTreeView, QTableView, QToolBar, QStatusBar,
    QLabel, QSplitter, QMessageBox, QFileDialog,
    QApplication, QLineEdit, QMenu, QToolTip,
    QStyle, QInputDialog, QDialog
)
from PySide6.QtCore import Qt, QSize, QTimer, QPoint, QModelIndex, QUrl
from PySide6.QtGui import (
    QAction, QStandardItemModel, QStandardItem,
    QDesktopServices, QKeySequence
)

from services.s3_client import S3Client
from services.credential_store import CredentialStore
from ui.credential_dialog import CredentialDialog
from ui.confirm_dialog import ConfirmDialog
from workers.s3_list_worker import S3ListWorker
from services.transfer_manager import TransferManager
from ui.transfers_drawer import TransfersDrawer
from ui.styles import LIGHT_STYLE, DARK_STYLE


class MainWindow(QMainWindow):
    # table columns
    COL_ICON = 0
    COL_NAME = 1
    COL_TYPE = 2
    COL_SIZE = 3
    COL_MODIFIED = 4

    # item roles
    ROLE_KEY = Qt.UserRole + 1
    ROLE_IS_FOLDER = Qt.UserRole + 2

    def __init__(self):
        super().__init__()
        self.setWindowTitle("S3 Browser")
        self.resize(1100, 700)
        self.setAcceptDrops(True)

        # core
        self.s3 = None
        self.transfer_mgr = None

        # current location
        self.current_bucket = None
        self.current_prefix = ""

        # current listing (used for search + UI)
        self.current_folders = []
        self.current_files = []

        # cache + worker safety
        self.cache = {}             # (bucket,prefix) -> (folders, files)
        self.tree_item_map = {}     # id -> item
        self._workers = set()
        self._nav_token = 0

        # clipboard-like (multi)
        self.clipboard_items = []   # [(bucket, key_or_prefix, is_folder)]
        self.clipboard_cut = False

        # tree behavior
        self.show_files_in_tree = False

        # open-after-download map
        self.open_after_done = {}   # transfer_id -> True

        # keep transfer meta (mode/bucket/key) so we can refresh correct folder after done
        self._transfer_meta = {}    # tid -> (mode, bucket, key)

        # theme
        self._dark_enabled = True
        QApplication.instance().setStyleSheet(DARK_STYLE)

        # build UI
        self.create_toolbar()
        self.create_center()
        self.create_status_bar()
        self.init_models()
        self.configure_views()

        QTimer.singleShot(0, self.auto_connect_if_possible)

    # -------------------- helpers --------------------
    def _run_worker(self, w):
        """Keep QThread refs so they don't get GC'd mid-run."""
        self._workers.add(w)
        w.finished.connect(lambda: self._workers.discard(w))
        w.finished.connect(w.deleteLater)
        w.start()

    def toast(self, message: str, ms: int = 1500):
        pos = self.mapToGlobal(QPoint(20, self.height() - 60))
        QToolTip.showText(pos, message, self)
        QTimer.singleShot(ms, QToolTip.hideText)

    def _folder_of_key(self, key: str) -> str:
        p = "/".join(key.split("/")[:-1]).strip()
        return (p + "/") if p else ""

    def invalidate_prefix(self, bucket: str, prefix: str):
        """Remove cache for (bucket,prefix) safely."""
        self.cache.pop((bucket, prefix), None)

    def invalidate_and_reload_current(self, reload_tree: bool = True, reload_table: bool = True):
        """Invalidate current folder cache and reload UI."""
        if not self.current_bucket:
            return
        self.invalidate_prefix(self.current_bucket, self.current_prefix)

        if reload_table:
            self.load_table_from_prefix(self.current_bucket, self.current_prefix, force_refresh=True)

        if reload_tree:
            self.refresh_tree_node_for_current()

    # -------------------- toolbar --------------------
    def create_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)

        self.action_connect = QAction(self.style().standardIcon(QStyle.SP_DialogYesButton), "Connect", self)
        self.action_refresh = QAction(self.style().standardIcon(QStyle.SP_BrowserReload), "Refresh", self)

        # Transfers: checkable so it looks selected
        self.action_transfers = QAction(self.style().standardIcon(QStyle.SP_FileDialogInfoView), "Transfers", self)
        self.action_transfers.setCheckable(True)
        self.action_transfers.setToolTip("Show transfers panel")

        self.action_theme = QAction(self.style().standardIcon(QStyle.SP_DialogResetButton), "Theme", self)
        self.action_theme.setToolTip("Toggle Dark/Light")

        tb.addAction(self.action_connect)
        tb.addAction(self.action_refresh)
        tb.addSeparator()

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search files + folders…")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setFixedWidth(280)
        self.search_box.textChanged.connect(self.apply_search_filter)
        tb.addWidget(self.search_box)

        tb.addSeparator()

        self.action_tree_files = QAction("Tree Files", self)
        self.action_tree_files.setCheckable(True)
        self.action_tree_files.setToolTip("Show files in left tree (can be heavy)")
        tb.addAction(self.action_tree_files)

        tb.addSeparator()
        tb.addAction(self.action_transfers)

        tb.addSeparator()
        tb.addAction(self.action_theme)

        # signals
        self.action_connect.triggered.connect(self.connect_or_disconnect)
        self.action_refresh.triggered.connect(self.refresh_current)
        self.action_transfers.triggered.connect(self.toggle_transfers_drawer)
        self.action_theme.triggered.connect(self.toggle_dark)
        self.action_tree_files.toggled.connect(self.on_toggle_tree_files)

    def toggle_dark(self):
        self._dark_enabled = not self._dark_enabled
        QApplication.instance().setStyleSheet(DARK_STYLE if self._dark_enabled else LIGHT_STYLE)
        self.toast("Dark mode" if self._dark_enabled else "Light mode")

    def on_toggle_tree_files(self, enabled: bool):
        self.show_files_in_tree = enabled
        if self.s3:
            # keep same expand/selection state
            self.refresh_current()
            self.toast("Tree updated")

    # -------------------- center --------------------
    def create_center(self):
        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # path bar
        path_wrap = QWidget()
        path_wrap.setObjectName("crumbBar")
        pb = QHBoxLayout(path_wrap)
        pb.setContentsMargins(10, 6, 10, 6)
        pb.setSpacing(8)

        pb.addWidget(QLabel("Path:"))
        self.path_text = QLineEdit()
        self.path_text.setPlaceholderText("bucket/prefix/")
        self.path_text.returnPressed.connect(self.on_path_enter)
        pb.addWidget(self.path_text, 1)
        root.addWidget(path_wrap)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)

        self.tree = QTreeView()
        self.tree.setHeaderHidden(True)
        self.tree.clicked.connect(self.on_tree_clicked)
        self.tree.expanded.connect(self.on_tree_expanded)

        self.table = QTableView()
        splitter.addWidget(self.tree)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        root.addWidget(splitter, 1)

        # transfers drawer
        self.transfers_drawer = TransfersDrawer()
        self.transfers_drawer.setVisible(False)

        # If your TransfersDrawer has a close_requested signal, keep it.
        if hasattr(self.transfers_drawer, "close_requested"):
            self.transfers_drawer.close_requested.connect(self.hide_transfers_drawer)

        root.addWidget(self.transfers_drawer)

        self.setCentralWidget(container)

    def toggle_transfers_drawer(self):
        vis = not self.transfers_drawer.isVisible()
        self.transfers_drawer.setVisible(vis)
        self.action_transfers.setChecked(vis)

    def hide_transfers_drawer(self):
        self.transfers_drawer.setVisible(False)
        self.action_transfers.setChecked(False)

    # -------------------- status --------------------
    def create_status_bar(self):
        st = QStatusBar()
        self.setStatusBar(st)

        self.status_label = QLabel("Disconnected")
        self.status_label.setObjectName("statusPill")
        self.status_label.setProperty("state", "disconnected")
        st.addWidget(self.status_label)

    def set_connected_state(self, connected: bool):
        if connected:
            self.status_label.setText("Connected")
            self.status_label.setProperty("state", "connected")
            self.action_connect.setText("Disconnect")
        else:
            self.status_label.setText("Disconnected")
            self.status_label.setProperty("state", "disconnected")
            self.action_connect.setText("Connect")

        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    # -------------------- models --------------------
    def init_models(self):
        self.tree_model = QStandardItemModel()
        self.tree_model.setHorizontalHeaderLabels(["S3"])
        self.tree.setModel(self.tree_model)

        self.table_model = QStandardItemModel()
        self.table_model.setHorizontalHeaderLabels(["", "Name", "Type", "Size (KB)", "Last Modified"])
        self.table.setModel(self.table_model)

    def configure_views(self):
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self.on_table_double_clicked)

        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_table_context_menu)

    # -------------------- key shortcuts --------------------
    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copy_selected()
            return
        if event.matches(QKeySequence.Cut):
            self.cut_selected()
            return
        if event.matches(QKeySequence.Paste):
            self.paste_into_current()
            return
        if event.key() == Qt.Key_F2:
            self.rename_selected()
            return
        super().keyPressEvent(event)

    # -------------------- connect/disconnect --------------------
    def auto_connect_if_possible(self):
        if CredentialStore.load():
            self.connect_or_disconnect(auto=True)

    def connect_or_disconnect(self, auto=False):
        if self.s3:
            # disconnect
            self.s3 = None
            if self.transfer_mgr:
                self.transfer_mgr.shutdown()
            self.transfer_mgr = None

            self.cache.clear()
            self.tree_model.clear()
            self.table_model.removeRows(0, self.table_model.rowCount())
            self.current_bucket = None
            self.current_prefix = ""
            self.path_text.setText("")
            self.set_connected_state(False)
            self.toast("Disconnected")
            return

        # connect
        if not CredentialStore.load():
            dlg = CredentialDialog()
            if dlg.exec() != QDialog.Accepted:
                if not auto:
                    QMessageBox.warning(self, "Cancelled", "AWS credentials required.")
                return

        try:
            self.s3 = S3Client()
            self.transfer_mgr = TransferManager(self.s3, max_parallel=2)
            self.transfer_mgr.transfer_updated.connect(self.on_transfer_updated)
            self.transfer_mgr.transfer_error.connect(self.on_transfer_error)
            self.transfer_mgr.transfer_done.connect(self.on_transfer_done)

            self.set_connected_state(True)
            self.toast("Connected")
            self.load_buckets_async()
        except Exception as e:
            self.set_connected_state(False)
            QMessageBox.critical(self, "Connection Error", str(e))

    # -------------------- transfer callbacks --------------------
    def on_transfer_updated(self, tid, mode, bucket, key, progress, status):
        # save transfer meta so we can refresh correct folder after done
        self._transfer_meta[tid] = (mode, bucket, key)

        row_progress = progress if progress >= 0 else 0
        self.transfers_drawer.upsert(tid, mode, bucket, key, row_progress, status)

    def on_transfer_error(self, tid, msg):
        self.transfers_drawer.upsert(tid, "ERROR", "", "", 0, msg)
        self.toast("Transfer failed")
        self.transfers_drawer.setVisible(True)
        self.action_transfers.setChecked(True)

    def on_transfer_done(self, tid, local_path):
        self.toast("Transfer done")

        # auto-open for "Open"
        if tid in self.open_after_done:
            self.open_after_done.pop(tid, None)
            QDesktopServices.openUrl(QUrl.fromLocalFile(local_path))

        # refresh correct folder for that transfer (NOT always current folder)
        meta = self._transfer_meta.get(tid)
        if meta:
            mode, bucket, key = meta
            folder_prefix = self._folder_of_key(key)

            # invalidate that folder cache
            self.invalidate_prefix(bucket, folder_prefix)

            # if transfer affects current view, refresh both
            if bucket == self.current_bucket and folder_prefix == self.current_prefix:
                self.load_table_from_prefix(self.current_bucket, self.current_prefix, force_refresh=True)
                self.refresh_tree_node_for_current()

    # -------------------- list buckets (async) --------------------
    def load_buckets_async(self, restore_state=None):
        self._restore_state_after_buckets = restore_state
        self._nav_token += 1
        token = self._nav_token

        w = S3ListWorker(mode="buckets")
        w.buckets_ready.connect(lambda buckets: self._on_buckets_ready(buckets, token))
        w.error.connect(lambda msg: QMessageBox.critical(self, "Error", msg))
        self._run_worker(w)

    def _on_buckets_ready(self, buckets, token):
        if token != self._nav_token:
            return

        self.tree_model.clear()
        self.tree_item_map.clear()

        icon = self.style().standardIcon(QStyle.SP_DriveNetIcon)
        for b in buckets:
            it = QStandardItem(icon, b)
            it.setEditable(False)
            it.setData(("bucket", b))

            ph = QStandardItem("Loading…")
            ph.setEnabled(False)
            it.appendRow(ph)

            self.tree_model.appendRow(it)
            self.tree_item_map[f"b:{b}"] = it

        if getattr(self, "_restore_state_after_buckets", None):
            self.restore_tree_state(self._restore_state_after_buckets)
            self._restore_state_after_buckets = None

    # -------------------- tree expanded --------------------
    def on_tree_expanded(self, index):
        if not self.s3:
            return
        item = self.tree_model.itemFromIndex(index)
        data = item.data()
        if not data:
            return

        t, bucket = data[0], data[1]
        prefix = data[2] if t == "folder" else ""
        self.load_children(item, bucket, prefix, force=True)

    def load_children(self, parent_item, bucket, prefix, force: bool):
        """
        IMPORTANT FIX:
        - Before: even force=True returned cached children (wrong).
        - Now: force=True clears cache and fetches new list.
        """
        cache_key = (bucket, prefix)

        if force:
            self.cache.pop(cache_key, None)

        if (not force) and cache_key in self.cache:
            folders, files = self.cache[cache_key]
            self._apply_children(parent_item, bucket, prefix, folders, files)
            return

        self._nav_token += 1
        token = self._nav_token
        w = S3ListWorker(mode="objects", bucket=bucket, prefix=prefix)
        w.objects_ready.connect(
            lambda folders, files: self._on_children_ready(parent_item, bucket, prefix, folders, files, token)
        )
        w.error.connect(lambda msg: None)
        self._run_worker(w)

    def _on_children_ready(self, parent_item, bucket, prefix, folders, files, token):
        if token != self._nav_token:
            return
        self.cache[(bucket, prefix)] = (folders, files)
        self._apply_children(parent_item, bucket, prefix, folders, files)

    def _apply_children(self, parent_item, bucket, prefix, folders, files):
        parent_item.removeRows(0, parent_item.rowCount())

        folder_icon = self.style().standardIcon(QStyle.SP_DirIcon)
        file_icon = self.style().standardIcon(QStyle.SP_FileIcon)

        for folder in folders:
            name = folder.rstrip("/").split("/")[-1]
            child = QStandardItem(folder_icon, name)
            child.setEditable(False)
            child.setData(("folder", bucket, folder))

            ph = QStandardItem("Loading…")
            ph.setEnabled(False)
            child.appendRow(ph)

            parent_item.appendRow(child)
            self.tree_item_map[f"f:{bucket}:{folder}"] = child

        if self.show_files_in_tree:
            for f in files:
                key = f["Key"]
                name = key.split("/")[-1]
                fi = QStandardItem(file_icon, name)
                fi.setEditable(False)
                fi.setData(("file", bucket, key))
                parent_item.appendRow(fi)

        self.filter_tree(self.search_box.text().strip().lower())

    # -------------------- click tree --------------------
    def on_tree_clicked(self, index):
        if not self.s3:
            return
        item = self.tree_model.itemFromIndex(index)
        data = item.data()
        if not data:
            return

        t, bucket = data[0], data[1]

        if t == "file":
            key = data[2]
            self.current_bucket = bucket
            self.current_prefix = self._folder_of_key(key)
            self.path_text.setText(f"{bucket}/{self.current_prefix}")
            self.open_key(key)
            return

        prefix = data[2] if t == "folder" else ""
        self.current_bucket = bucket
        self.current_prefix = prefix
        self.path_text.setText(f"{bucket}/{prefix}")

        self.load_children(item, bucket, prefix, force=True)
        self.load_table_from_prefix(bucket, prefix, force_refresh=False)

    # -------------------- table loading --------------------
    def load_table_from_prefix(self, bucket, prefix, force_refresh: bool):
        cache_key = (bucket, prefix)

        if force_refresh:
            self.cache.pop(cache_key, None)

        if (not force_refresh) and cache_key in self.cache:
            folders, files = self.cache[cache_key]
            self.current_folders, self.current_files = folders, files
            self.apply_search_filter()
            return

        self._nav_token += 1
        token = self._nav_token
        w = S3ListWorker(mode="objects", bucket=bucket, prefix=prefix)
        w.objects_ready.connect(lambda folders, files: self._on_objects_ready(bucket, prefix, folders, files, token))
        w.error.connect(lambda msg: QMessageBox.critical(self, "Error", msg))
        self._run_worker(w)

    def _on_objects_ready(self, bucket, prefix, folders, files, token):
        if token != self._nav_token:
            return
        self.cache[(bucket, prefix)] = (folders, files)
        self.current_folders, self.current_files = folders, files
        self.apply_search_filter()

    # -------------------- search (table + tree) --------------------
    def apply_search_filter(self):
        term = self.search_box.text().strip().lower()
        self.filter_tree(term)

        if not term:
            folders, files = self.current_folders, self.current_files
        else:
            folders = [f for f in self.current_folders if term in f.lower()]
            files = [f for f in self.current_files if term in f["Key"].lower()]

        self.populate_table(folders, files)

    def filter_tree(self, term: str):
        term = (term or "").strip().lower()

        def recurse(parent_item: QStandardItem, parent_index: QModelIndex) -> bool:
            any_visible = False
            for row in range(parent_item.rowCount()):
                child = parent_item.child(row)
                child_index = child.index()
                child_visible = recurse(child, child_index)
                match = term in child.text().lower() if term else True
                show = True if not term else (match or child_visible)
                self.tree.setRowHidden(row, parent_index, not show)
                if show:
                    any_visible = True
            return any_visible

        recurse(self.tree_model.invisibleRootItem(), QModelIndex())

    def populate_table(self, folders, files):
        self.table_model.removeRows(0, self.table_model.rowCount())

        folder_icon = self.style().standardIcon(QStyle.SP_DirIcon)
        file_icon = self.style().standardIcon(QStyle.SP_FileIcon)

        for folder in folders:
            name = folder.rstrip("/").split("/")[-1]
            icon_item = QStandardItem()
            icon_item.setIcon(folder_icon)

            name_item = QStandardItem(name)
            name_item.setData(folder, self.ROLE_KEY)
            name_item.setData(True, self.ROLE_IS_FOLDER)

            self.table_model.appendRow([
                icon_item, name_item,
                QStandardItem("Folder"),
                QStandardItem(""),
                QStandardItem("")
            ])

        for f in files:
            key = f["Key"]
            name = key.split("/")[-1]
            ext = os.path.splitext(name)[1].lstrip(".").upper() or "FILE"
            size_kb = round(int(f["Size"]) / 1024, 2)
            mod = f["LastModified"].strftime("%Y-%m-%d %H:%M")

            icon_item = QStandardItem()
            icon_item.setIcon(file_icon)

            name_item = QStandardItem(name)
            name_item.setData(key, self.ROLE_KEY)
            name_item.setData(False, self.ROLE_IS_FOLDER)

            self.table_model.appendRow([
                icon_item, name_item,
                QStandardItem(ext),
                QStandardItem(str(size_kb)),
                QStandardItem(mod)
            ])

    # -------------------- double click table --------------------
    def on_table_double_clicked(self, index):
        row = index.row()
        name_item = self.table_model.item(row, self.COL_NAME)
        key_or_prefix = name_item.data(self.ROLE_KEY)
        is_folder = bool(name_item.data(self.ROLE_IS_FOLDER))

        if is_folder:
            self.current_prefix = key_or_prefix
            self.path_text.setText(f"{self.current_bucket}/{self.current_prefix}")
            self.load_table_from_prefix(self.current_bucket, self.current_prefix, force_refresh=False)
        else:
            self.open_key(key_or_prefix)

    # -------------------- open/download --------------------
    def open_key(self, key):
        if not self.transfer_mgr or not self.current_bucket:
            return

        tmp_dir = os.path.join(tempfile.gettempdir(), "S3BrowserApp")
        os.makedirs(tmp_dir, exist_ok=True)
        local_path = os.path.join(tmp_dir, os.path.basename(key))

        tid = self.transfer_mgr.enqueue_download(self.current_bucket, key, local_path)
        self.open_after_done[tid] = True

        self.transfers_drawer.setVisible(True)
        self.action_transfers.setChecked(True)
        self.toast("Downloading to open…")

    def download_key(self, key):
        if not self.transfer_mgr or not self.current_bucket:
            return
        save_path, _ = QFileDialog.getSaveFileName(self, "Save file as", os.path.basename(key))
        if not save_path:
            return
        self.transfer_mgr.enqueue_download(self.current_bucket, key, save_path)
        self.transfers_drawer.setVisible(True)
        self.action_transfers.setChecked(True)
        self.toast("Download queued")

    # -------------------- context menu --------------------
    def show_table_context_menu(self, pos):
        menu = QMenu(self)
        idx = self.table.indexAt(pos)

        # EMPTY area menu
        if not idx.isValid():
            act_paste = menu.addAction("Paste")
            act_paste.setEnabled(bool(self.clipboard_items))
            menu.addSeparator()
            act_refresh = menu.addAction("Refresh")
            act_new_folder = menu.addAction("New Folder")

            chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
            if not chosen:
                return
            if chosen == act_paste:
                self.paste_into_current()
            elif chosen == act_refresh:
                self.refresh_current()
            elif chosen == act_new_folder:
                self.create_new_folder()
            return

        # item menu
        self.table.selectRow(idx.row())
        selection = self._get_selected_items()
        is_single = (len(selection) == 1)
        key_or_prefix, is_folder = selection[0] if is_single else (None, False)

        act_open = menu.addAction("Open")
        act_download = None
        if is_single and (not is_folder):
            act_download = menu.addAction("Download…")

        menu.addSeparator()
        act_cut = menu.addAction("Cut")
        act_copy = menu.addAction("Copy")
        act_paste = menu.addAction("Paste")
        act_paste.setEnabled(bool(self.clipboard_items))
        act_rename = menu.addAction("Rename")
        act_rename.setEnabled(is_single)

        menu.addSeparator()
        act_delete = menu.addAction("Delete")
        menu.addSeparator()
        act_refresh = menu.addAction("Refresh")
        act_new_folder = menu.addAction("New Folder")

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if not chosen:
            return

        if chosen == act_open:
            if is_single and is_folder:
                self.current_prefix = key_or_prefix
                self.path_text.setText(f"{self.current_bucket}/{self.current_prefix}")
                self.load_table_from_prefix(self.current_bucket, self.current_prefix, force_refresh=False)
            elif is_single and (not is_folder):
                self.open_key(key_or_prefix)

        elif chosen == act_download and act_download and is_single:
            self.download_key(key_or_prefix)

        elif chosen == act_cut:
            self.cut_selected()

        elif chosen == act_copy:
            self.copy_selected()

        elif chosen == act_paste:
            self.paste_into_current()

        elif chosen == act_rename:
            if is_single:
                self.rename_item(key_or_prefix, is_folder)

        elif chosen == act_delete:
            self.delete_selected_items()

        elif chosen == act_refresh:
            self.refresh_current()

        elif chosen == act_new_folder:
            self.create_new_folder()

    # -------------------- selection helpers --------------------
    def _get_selected_items(self):
        """Return list of (key_or_prefix, is_folder) from table selection."""
        if not self.current_bucket:
            return []
        rows = self.table.selectionModel().selectedRows()
        out = []
        for idx in rows:
            r = idx.row()
            name_item = self.table_model.item(r, self.COL_NAME)
            key_or_prefix = name_item.data(self.ROLE_KEY)
            is_folder = bool(name_item.data(self.ROLE_IS_FOLDER))
            if key_or_prefix:
                out.append((key_or_prefix, is_folder))
        return out

    # -------------------- clipboard actions --------------------
    def copy_selected(self):
        items = self._get_selected_items()
        if not items or not self.current_bucket:
            return
        self.clipboard_items = [(self.current_bucket, k, is_folder) for (k, is_folder) in items]
        self.clipboard_cut = False
        self.toast(f"Copied {len(items)} item(s)")

    def cut_selected(self):
        items = self._get_selected_items()
        if not items or not self.current_bucket:
            return
        self.clipboard_items = [(self.current_bucket, k, is_folder) for (k, is_folder) in items]
        self.clipboard_cut = True
        self.toast(f"Cut {len(items)} item(s)")

    def paste_into_current(self):
        if not self.s3 or not self.current_bucket:
            return
        if not self.clipboard_items:
            self.toast("Clipboard empty")
            return

        # multi file paste (folder paste later)
        for src_bucket, src_key, is_folder in self.clipboard_items:
            if is_folder:
                QMessageBox.information(self, "Paste", "Folder paste is not enabled yet (needs recursive copy).")
                return

            name = src_key.split("/")[-1]
            dst_key = f"{self.current_prefix}{name}"

            try:
                self.s3.copy_object(src_bucket, src_key, self.current_bucket, dst_key)
                if self.clipboard_cut:
                    self.s3.delete_object(src_bucket, src_key)
            except Exception as e:
                QMessageBox.critical(self, "Paste Error", str(e))
                return

        if self.clipboard_cut:
            self.clipboard_items = []
            self.clipboard_cut = False

        self.toast("Pasted")
        self.invalidate_and_reload_current(reload_tree=True, reload_table=True)

    # -------------------- rename --------------------
    def rename_selected(self):
        items = self._get_selected_items()
        if len(items) != 1:
            return
        key, is_folder = items[0]
        self.rename_item(key, is_folder)

    def rename_item(self, key_or_prefix, is_folder: bool):
        old_name = key_or_prefix.rstrip("/").split("/")[-1]
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=old_name)
        if not ok or not new_name.strip():
            return
        new_name = new_name.strip()

        try:
            if is_folder:
                parent = "/".join(key_or_prefix.rstrip("/").split("/")[:-1])
                parent = (parent + "/") if parent else ""
                new_prefix = parent + new_name + "/"
                self.s3.rename_folder(self.current_bucket, key_or_prefix, new_prefix)
            else:
                parent = "/".join(key_or_prefix.split("/")[:-1])
                parent = (parent + "/") if parent else ""
                new_key = parent + new_name
                self.s3.rename_file(self.current_bucket, key_or_prefix, new_key)
        except Exception as e:
            QMessageBox.critical(self, "Rename Error", str(e))
            return

        self.toast("Renamed")
        self.invalidate_and_reload_current(reload_tree=True, reload_table=True)

    # -------------------- delete --------------------
    def delete_selected_items(self):
        items = self._get_selected_items()
        if not items:
            return

        text = items[0][0] if len(items) == 1 else f"{len(items)} items"
        dlg = ConfirmDialog("Delete", f"Delete?\n\n{text}", "Delete", self)
        if dlg.exec() != QDialog.Accepted:
            return

        # optimistic remove from table immediately
        selected_rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows()}, reverse=True)
        for r in selected_rows:
            self.table_model.removeRow(r)

        # do delete on S3
        for key_or_prefix, is_folder in items:
            try:
                if is_folder:
                    # If you updated S3Client with delete_prefix(), use it:
                    if hasattr(self.s3, "delete_prefix"):
                        self.s3.delete_prefix(self.current_bucket, key_or_prefix)
                    else:
                        keys = self.s3.list_all_keys(self.current_bucket, key_or_prefix)
                        if keys and hasattr(self.s3, "delete_objects"):
                            self.s3.delete_objects(self.current_bucket, keys)
                        else:
                            # fallback
                            for k in keys:
                                self.s3.delete_object(self.current_bucket, k)
                        self.s3.delete_object(self.current_bucket, key_or_prefix)
                else:
                    self.s3.delete_object(self.current_bucket, key_or_prefix)
            except Exception as e:
                QMessageBox.critical(self, "Delete Error", str(e))
                # hard refresh to recover UI
                self.refresh_current()
                return

        self.toast("Deleted")
        self.invalidate_and_reload_current(reload_tree=True, reload_table=True)

    # -------------------- new folder --------------------
    def create_new_folder(self):
        if not self.current_bucket:
            return
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        new_prefix = f"{self.current_prefix}{name}/"

        try:
            self.s3.create_folder(self.current_bucket, new_prefix)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        self.toast("Folder created")
        self.invalidate_and_reload_current(reload_tree=True, reload_table=True)

    # -------------------- drag & drop upload --------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not self.transfer_mgr or not self.current_bucket:
            self.toast("Select a bucket/folder first")
            return

        urls = event.mimeData().urls()
        files = [u.toLocalFile() for u in urls if u.isLocalFile() and os.path.isfile(u.toLocalFile())]
        if not files:
            return

        for p in files:
            filename = os.path.basename(p)
            key = f"{self.current_prefix}{filename}"
            self.transfer_mgr.enqueue_upload(self.current_bucket, key, p)

        self.transfers_drawer.setVisible(True)
        self.action_transfers.setChecked(True)
        self.toast(f"Queued {len(files)} upload(s)")

    # -------------------- refresh (keep state, refresh both sides) --------------------
    def refresh_current(self):
        if not self.s3:
            return

        state = self.save_tree_state()

        # IMPORTANT: clear cache so both sides update
        self.cache.clear()

        self.load_buckets_async(restore_state=state)

        if self.current_bucket is not None:
            self.load_table_from_prefix(self.current_bucket, self.current_prefix, force_refresh=True)

        self.toast("Refreshed")

    def refresh_tree_node_for_current(self):
        """Refresh only left tree children for current node (fast)."""
        if not self.current_bucket:
            return
        idx = self.tree.currentIndex()
        if not idx.isValid():
            return
        item = self.tree_model.itemFromIndex(idx)
        if not item:
            return
        data = item.data()
        if not data:
            return
        if data[0] in ("bucket", "folder"):
            bucket = data[1]
            prefix = data[2] if data[0] == "folder" else ""
            self.cache.pop((bucket, prefix), None)
            self.load_children(item, bucket, prefix, force=True)

    def save_tree_state(self):
        expanded = set()

        def walk(parent_item):
            for r in range(parent_item.rowCount()):
                child = parent_item.child(r)
                if self.tree.isExpanded(child.index()):
                    cid = self.item_id(child)
                    if cid:
                        expanded.add(cid)
                walk(child)

        walk(self.tree_model.invisibleRootItem())

        selected_id = None
        idx = self.tree.currentIndex()
        if idx.isValid():
            selected_id = self.item_id(self.tree_model.itemFromIndex(idx))

        return {"expanded": expanded, "selected": selected_id}

    def restore_tree_state(self, state):
        expanded = list(state.get("expanded", []))
        selected_id = state.get("selected")

        def depth(x):
            if x.startswith("b:"):
                return 0
            parts = x.split(":", 2)
            return parts[2].count("/") if len(parts) == 3 else 0

        expanded.sort(key=depth)
        for eid in expanded:
            item = self.tree_item_map.get(eid)
            if item:
                self.tree.expand(item.index())

        if selected_id and selected_id in self.tree_item_map:
            self.tree.setCurrentIndex(self.tree_item_map[selected_id].index())

    def item_id(self, item: QStandardItem):
        data = item.data()
        if not data:
            return None
        if data[0] == "bucket":
            return f"b:{data[1]}"
        if data[0] == "folder":
            return f"f:{data[1]}:{data[2]}"
        return None

    # -------------------- path enter --------------------
    def on_path_enter(self):
        text = self.path_text.text().strip().replace("\\", "/").lstrip("/")
        if not text:
            return

        if "/" not in text:
            bucket = text.rstrip("/")
            prefix = ""
        else:
            bucket, rest = text.split("/", 1)
            prefix = rest.strip()
            if prefix and not prefix.endswith("/"):
                prefix += "/"

        self.current_bucket = bucket
        self.current_prefix = prefix
        self.load_table_from_prefix(bucket, prefix, force_refresh=False)

    # -------------------- safe shutdown --------------------
    def closeEvent(self, event):
        try:
            if self.transfer_mgr:
                self.transfer_mgr.shutdown()
        except Exception:
            pass
        super().closeEvent(event)
