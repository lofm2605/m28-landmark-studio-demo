"""CVAT GIẢ: các exception của cvat_sdk.exceptions."""
from .api_client.exceptions import ApiException  # noqa: F401


class CvatSdkException(Exception):
    pass


class IncompatibleVersionException(CvatSdkException):
    pass
