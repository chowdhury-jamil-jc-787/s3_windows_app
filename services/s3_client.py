import boto3
from botocore.exceptions import ClientError, NoCredentialsError


class S3Client:
    def __init__(self, region_name=None):
        """
        Uses AWS credentials from:
        - aws configure
        - environment variables
        - IAM role (if any)
        """
        try:
            self.s3 = boto3.client("s3", region_name=region_name)
        except Exception as e:
            raise RuntimeError(f"Failed to create S3 client: {e}")

    # -----------------------------
    # List all buckets
    # -----------------------------
    def list_buckets(self):
        try:
            response = self.s3.list_buckets()
            return [b["Name"] for b in response.get("Buckets", [])]
        except NoCredentialsError:
            raise RuntimeError("AWS credentials not found")
        except ClientError as e:
            raise RuntimeError(str(e))

    # -----------------------------
    # List folders & files
    # -----------------------------
    def list_objects(self, bucket_name, prefix=""):
        """
        Returns:
        - folders: list of folder names
        - files: list of file dicts
        """
        try:
            response = self.s3.list_objects_v2(
                Bucket=bucket_name,
                Prefix=prefix,
                Delimiter="/"
            )

            folders = []
            files = []

            # Subfolders
            for cp in response.get("CommonPrefixes", []):
                folders.append(cp["Prefix"])

            # Files
            for obj in response.get("Contents", []):
                if obj["Key"] != prefix:
                    files.append(obj)

            return folders, files

        except ClientError as e:
            raise RuntimeError(str(e))
