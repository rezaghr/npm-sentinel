from app.application.ports.package_repository import (
    PackageListFilters,
    PackageListItem,
    PackageRepository,
    Pagination,
)


class ListPackagesUseCase:
    def __init__(self, repository: PackageRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        *,
        limit: int,
        offset: int,
        risk_level: str | None = None,
        name_query: str | None = None,
    ) -> tuple[list[PackageListItem], int]:
        return await self._repository.list_packages(
            filters=PackageListFilters(risk_level=risk_level, name_query=name_query),
            pagination=Pagination(limit=limit, offset=offset),
        )
