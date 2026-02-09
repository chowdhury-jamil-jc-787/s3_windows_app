import keyring
import json

SERVICE_NAME = "S3BrowserApp"


class CredentialStore:
    @staticmethod
    def save(access_key, secret_key, region):
        data = {
            "access_key": access_key,
            "secret_key": secret_key,
            "region": region,
        }
        keyring.set_password(
            SERVICE_NAME,
            "aws_credentials",
            json.dumps(data)
        )

    @staticmethod
    def load():
        data = keyring.get_password(
            SERVICE_NAME,
            "aws_credentials"
        )
        if not data:
            return None
        return json.loads(data)

    @staticmethod
    def clear():
        try:
            keyring.delete_password(
                SERVICE_NAME,
                "aws_credentials"
            )
        except keyring.errors.PasswordDeleteError:
            pass