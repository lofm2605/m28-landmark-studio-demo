"""CVAT GIẢ: ApiException có status/reason/body như bản thật."""


class OpenApiException(Exception):
    pass


class ApiException(OpenApiException):
    def __init__(self, status=None, reason=None, http_resp=None):
        self.status, self.reason, self.body, self.headers = status, reason, None, None
        if http_resp is not None:
            self.status, self.reason, self.body = http_resp.status, http_resp.reason, http_resp.data

    def __str__(self):
        return f"Status Code: {self.status}\nReason: {self.reason}\n" + (f"HTTP response body: {self.body}\n" if self.body else "")
