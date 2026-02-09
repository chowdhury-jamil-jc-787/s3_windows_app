import os
import time
from PySide6.QtCore import QThread, Signal


class TransferWorker(QThread):
    progress = Signal(int)          # 0-100
    status = Signal(str)            # text
    error = Signal(str)
    done = Signal(str)              # emits local_path when finished

    def __init__(self, s3_client, mode: str, bucket: str, key: str, local_path: str):
        super().__init__()
        self.s3 = s3_client
        self.mode = mode            # "upload" | "download"
        self.bucket = bucket
        self.key = key
        self.local_path = local_path

        self._total = 0
        self._seen = 0
        self._t0 = 0.0
        self._last_emit = 0.0

        # ✅ safer cancel mechanism (don't throw inside boto callback)
        self._cancel_requested = False

    # ---------------- callback from boto3 ----------------
    def _cb(self, bytes_amount: int):
        # ✅ best-effort cancel: don't raise inside boto callback
        if self.isInterruptionRequested():
            self._cancel_requested = True
            return

        self._seen += int(bytes_amount)
        if not self._total:
            return

        now = time.time()

        # throttle UI updates
        if now - self._last_emit < 0.12:
            return
        self._last_emit = now

        pct = int((self._seen / self._total) * 100)
        pct = max(0, min(100, pct))

        elapsed = max(0.001, now - self._t0)
        speed_bps = self._seen / elapsed
        speed_mb = speed_bps / (1024 * 1024)

        self.progress.emit(pct)
        self.status.emit(f"{self.mode.upper()} {pct}%  ({speed_mb:.2f} MB/s)")

    # ---------------- main thread function ----------------
    def run(self):
        try:
            self._seen = 0
            self._last_emit = 0.0
            self._t0 = time.time()
            self._cancel_requested = False

            if self.mode == "download":
                self.status.emit("Starting download…")

                # ✅ ensure destination folder exists
                os.makedirs(os.path.dirname(self.local_path) or ".", exist_ok=True)

                self._total = int(self.s3.get_object_size(self.bucket, self.key))

                self.s3.download_file(
                    self.bucket,
                    self.key,
                    self.local_path,
                    progress_cb=self._cb
                )

                # ✅ if cancel requested during transfer
                if self._cancel_requested:
                    # best effort: remove partial file
                    try:
                        if os.path.exists(self.local_path):
                            os.remove(self.local_path)
                    except Exception:
                        pass
                    raise RuntimeError("Transfer cancelled")

                # ✅ verify download actually exists
                if not os.path.exists(self.local_path):
                    raise RuntimeError("Download finished but file not found on disk")

            elif self.mode == "upload":
                self.status.emit("Starting upload…")

                if not os.path.exists(self.local_path):
                    raise RuntimeError("Local file not found for upload")

                self._total = int(os.path.getsize(self.local_path))

                self.s3.upload_file(
                    self.local_path,
                    self.bucket,
                    self.key,
                    progress_cb=self._cb
                )

                if self._cancel_requested:
                    raise RuntimeError("Transfer cancelled")

            else:
                raise RuntimeError("Invalid transfer mode")

            # final emit
            self.progress.emit(100)
            self.status.emit("Done")

            # ✅ return local_path so UI can open after download
            self.done.emit(self.local_path)

        except Exception as e:
            self.status.emit("Failed")
            self.error.emit(str(e))
