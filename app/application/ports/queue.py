from typing import Protocol


class ScanJobQueue(Protocol):
    def enqueue_scan_package(
        self,
        package_name: str,
        reason: str = "manual",
        *,
        task_id: str | None = None,
    ) -> str:
        ...

    def enqueue_top_packages_batch(self, limit: int, reason: str = "manual_batch", *, task_id: str | None = None) -> str:
        ...
