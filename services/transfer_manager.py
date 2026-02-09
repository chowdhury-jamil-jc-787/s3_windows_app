import uuid
import heapq
import itertools
from dataclasses import dataclass
from typing import Optional, Tuple

from PySide6.QtCore import QObject, Signal

from workers.transfer_worker import TransferWorker


@dataclass(order=True)
class _QueueItem:
    # heapq sorts by: priority, seq, ...
    priority: int
    seq: int
    tid: str
    mode: str          # "UPLOAD" | "DOWNLOAD" | "OPEN"
    bucket: str
    key: str
    local_path: str


class TransferManager(QObject):
    """
    Priority transfer queue like OneDrive:
      1) OPEN / VIEW  (highest)
      2) DOWNLOAD
      3) UPLOAD       (lowest)

    - Runs up to max_parallel workers at once
    - New high-priority tasks jump ahead of uploads
    - UI stays responsive because work is in QThreads
    """

    # id, mode, bucket, key, progress(0-100 or -1), status
    transfer_updated = Signal(str, str, str, str, int, str)

    # (transfer_id, local_path)
    transfer_done = Signal(str, str)

    # (transfer_id, message)
    transfer_error = Signal(str, str)

    # priorities (lower = higher priority)
    PRI_OPEN = 0
    PRI_DOWNLOAD = 1
    PRI_UPLOAD = 2

    def __init__(self, s3_client, max_parallel: int = 2):
        super().__init__()
        self.s3 = s3_client
        self.max_parallel = max_parallel

        self._pq = []                    # heap of _QueueItem
        self._seq = itertools.count()    # stable ordering
        self.active = {}                 # tid -> worker
        self._all_workers = set()        # keep refs alive

        # optional: allow "paused" later
        self._paused = False

    # ---------------- enqueue API ----------------
    def enqueue_upload(self, bucket: str, key: str, local_path: str) -> str:
        return self._enqueue(self.PRI_UPLOAD, "UPLOAD", bucket, key, local_path)

    def enqueue_download(self, bucket: str, key: str, local_path: str) -> str:
        return self._enqueue(self.PRI_DOWNLOAD, "DOWNLOAD", bucket, key, local_path)

    def enqueue_open(self, bucket: str, key: str, local_path: str) -> str:
        """
        Use this for "Open/View" so it jumps ahead of uploads.
        """
        return self._enqueue(self.PRI_OPEN, "OPEN", bucket, key, local_path)

    def _enqueue(self, priority: int, mode: str, bucket: str, key: str, local_path: str) -> str:
        tid = str(uuid.uuid4())[:8]
        item = _QueueItem(
            priority=priority,
            seq=next(self._seq),
            tid=tid,
            mode=mode,
            bucket=bucket,
            key=key,
            local_path=local_path,
        )
        heapq.heappush(self._pq, item)
        self.transfer_updated.emit(tid, mode, bucket, key, 0, "Queued")
        self._pump()
        return tid

    # ---------------- internal queue runner ----------------
    def _pump(self):
        if self._paused:
            return

        while len(self.active) < self.max_parallel and self._pq:
            item = heapq.heappop(self._pq)
            tid, mode, bucket, key, local_path = item.tid, item.mode, item.bucket, item.key, item.local_path

            # Worker only understands upload/download.
            # OPEN is a DOWNLOAD with higher priority.
            worker_mode = "download" if mode in ("DOWNLOAD", "OPEN") else "upload"

            w = TransferWorker(
                s3_client=self.s3,
                mode=worker_mode,
                bucket=bucket,
                key=key,
                local_path=local_path,
            )

            self.active[tid] = w
            self._all_workers.add(w)

            # progress
            w.progress.connect(
                lambda p, _tid=tid, _m=mode, _b=bucket, _k=key:
                self.transfer_updated.emit(_tid, _m, _b, _k, p, "Running")
            )

            # status (speed text etc)
            w.status.connect(
                lambda s, _tid=tid, _m=mode, _b=bucket, _k=key:
                self.transfer_updated.emit(_tid, _m, _b, _k, -1, s)
            )

            # error
            def on_err(msg, _tid=tid, _m=mode, _b=bucket, _k=key):
                self.active.pop(_tid, None)

                if "cancel" in str(msg).lower():
                    self.transfer_updated.emit(_tid, _m, _b, _k, -1, "Cancelled")
                else:
                    self.transfer_updated.emit(_tid, _m, _b, _k, -1, "Failed")

                self.transfer_error.emit(_tid, str(msg))
                self._pump()

            # done (worker emits local_path)
            def on_done(worker_local_path, _tid=tid, _m=mode, _b=bucket, _k=key):
                self.active.pop(_tid, None)
                self.transfer_updated.emit(_tid, _m, _b, _k, 100, "Done")
                self.transfer_done.emit(_tid, worker_local_path)
                self._pump()

            w.error.connect(on_err)
            w.done.connect(on_done)

            # cleanup only once when finished
            w.finished.connect(lambda _w=w: self._cleanup_worker(_w))

            w.start()

    # ---------------- controls ----------------
    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False
        self._pump()

    def clear_queue(self):
        self._pq.clear()

    def queued_count(self) -> int:
        return len(self._pq)

    def active_count(self) -> int:
        return len(self.active)

    # ---------------- cleanup ----------------
    def _cleanup_worker(self, w):
        self._all_workers.discard(w)
        try:
            w.deleteLater()
        except RuntimeError:
            pass

    # ---------------- shutdown ----------------
    def shutdown(self):
        self._paused = True
        self._pq.clear()

        for w in list(self._all_workers):
            try:
                if w.isRunning():
                    w.requestInterruption()
                    w.quit()
                    w.wait(1500)
            except Exception:
                pass
