from PySide6.QtCore import QThread, Signal
from services.s3_client import S3Client


class S3ListWorker(QThread):
    buckets_ready = Signal(list)
    objects_ready = Signal(list, list)  # folders, files
    error = Signal(str)

    def __init__(self, mode: str, bucket: str = "", prefix: str = ""):
        super().__init__()
        self.mode = mode
        self.bucket = bucket
        self.prefix = prefix

    def run(self):
        try:
            client = S3Client()

            if self.mode == "buckets":
                self.buckets_ready.emit(client.list_buckets())
            elif self.mode == "objects":
                folders, files = client.list_objects(self.bucket, self.prefix)
                self.objects_ready.emit(folders, files)

        except Exception as e:
            self.error.emit(str(e))
