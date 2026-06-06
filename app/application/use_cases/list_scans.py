from app.application.ports.package_repository import (
    PackageRepository,
    Pagination,
    ScanResultFilters,
    ScanResultRead,
)


class ListScansUseCase:
    def __init__(self, repository: PackageRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        risk_level: str | None = None,
        package_name: str | None = None,
    ) -> tuple[list[ScanResultRead], int]:
        return await self._repository.list_scan_results(
            filters=ScanResultFilters(status=status, risk_level=risk_level, package_name=package_name),
            pagination=Pagination(limit=limit, offset=offset),
        )
