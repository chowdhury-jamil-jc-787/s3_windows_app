import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config

from services.credential_store import CredentialStore


class S3Client:
    def __init__(self):
        creds = CredentialStore.load()
        if not creds:
            raise RuntimeError("AWS credentials not configured")

        boto_config = Config(
            region_name=creds["region"],
            retries={"max_attempts": 10, "mode": "adaptive"},
            max_pool_connections=50,
            connect_timeout=10,
            read_timeout=60,
            tcp_keepalive=True,
        )

        session = boto3.session.Session(
            aws_access_key_id=creds["access_key"],
            aws_secret_access_key=creds["secret_key"],
            region_name=creds["region"],
        )
        self.s3 = session.client("s3", config=boto_config)

        self.transfer_config = TransferConfig(
            multipart_threshold=32 * 1024 * 1024,
            multipart_chunksize=32 * 1024 * 1024,
            max_concurrency=20,
            use_threads=True,
            num_download_attempts=10,
        )

    # ---------------- listing ----------------
    def list_buckets(self):
        r = self.s3.list_buckets()
        return [b["Name"] for b in r.get("Buckets", [])]

    def list_objects(self, bucket_name, prefix=""):
        r = self.s3.list_objects_v2(
            Bucket=bucket_name,
            Prefix=prefix,
            Delimiter="/",
        )
        folders = [p["Prefix"] for p in r.get("CommonPrefixes", [])]
        files = [o for o in r.get("Contents", []) if o["Key"] != prefix]
        return folders, files

    def list_all_keys(self, bucket_name, prefix=""):
        """Pagination: list EVERYTHING under a prefix (no delimiter)."""
        keys = []
        token = None
        while True:
            kwargs = dict(Bucket=bucket_name, Prefix=prefix)
            if token:
                kwargs["ContinuationToken"] = token
            r = self.s3.list_objects_v2(**kwargs)
            for o in r.get("Contents", []):
                keys.append(o["Key"])
            if r.get("IsTruncated"):
                token = r.get("NextContinuationToken")
            else:
                break
        return keys

    # ---------------- transfers ----------------
    def upload_file(self, local_path, bucket, key, progress_cb=None):
        self.s3.upload_file(
            Filename=local_path,
            Bucket=bucket,
            Key=key,
            Callback=progress_cb,
            Config=self.transfer_config,
        )

    def download_file(self, bucket, key, local_path, progress_cb=None):
        self.s3.download_file(
            Bucket=bucket,
            Key=key,
            Filename=local_path,
            Callback=progress_cb,
            Config=self.transfer_config,
        )

    def get_object_size(self, bucket, key) -> int:
        r = self.s3.head_object(Bucket=bucket, Key=key)
        return int(r["ContentLength"])

    # ---------------- object ops ----------------
    def delete_object(self, bucket, key):
        self.s3.delete_object(Bucket=bucket, Key=key)

    def delete_objects(self, bucket, keys):
        """Batch delete keys in chunks of 1000 (S3 limit)."""
        if not keys:
            return
        for i in range(0, len(keys), 1000):
            chunk = keys[i:i + 1000]
            self.s3.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": x} for x in chunk], "Quiet": True},
            )

    def copy_object(self, src_bucket, src_key, dst_bucket, dst_key):
        self.s3.copy_object(
            Bucket=dst_bucket,
            Key=dst_key,
            CopySource={"Bucket": src_bucket, "Key": src_key},
        )

    # ---------------- folder semantics ----------------
    def create_folder(self, bucket, prefix):
        """Create S3 'folder' marker object ending with /"""
        if not prefix.endswith("/"):
            prefix += "/"
        self.s3.put_object(Bucket=bucket, Key=prefix, Body=b"")

    def delete_prefix(self, bucket, prefix):
        """Delete everything under prefix + marker."""
        if not prefix.endswith("/"):
            prefix += "/"
        keys = self.list_all_keys(bucket, prefix)

        # delete all objects under prefix
        self.delete_objects(bucket, keys)

        # delete marker too
        self.delete_object(bucket, prefix)

    # ---------------- rename semantics ----------------
    def rename_file(self, bucket, old_key, new_key):
        self.copy_object(bucket, old_key, bucket, new_key)
        self.delete_object(bucket, old_key)

    def rename_folder(self, bucket, old_prefix, new_prefix):
        if not old_prefix.endswith("/"):
            old_prefix += "/"
        if not new_prefix.endswith("/"):
            new_prefix += "/"

        keys = self.list_all_keys(bucket, old_prefix)

        # copy all keys to new prefix
        for k in keys:
            suffix = k[len(old_prefix):]
            dst = new_prefix + suffix
            self.copy_object(bucket, k, bucket, dst)

        # delete old keys + marker
        self.delete_objects(bucket, keys)
        self.delete_object(bucket, old_prefix)
