from typing import Protocol


class PackageListSource(Protocol):
    async def load_package_names(self, limit: int | None = None) -> list[str]:
        ...
