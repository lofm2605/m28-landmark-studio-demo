"""CVAT GIẢ (chỉ để test): ResourceType như cvat_sdk.core.proxies.tasks.ResourceType thật."""
import enum


class ResourceType(enum.Enum):
    LOCAL = 0
    SHARE = 1
    REMOTE = 2

    def __str__(self):
        return self.name.lower()
