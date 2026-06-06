from app.application.ports.package_repository import PackageRepository, Pagination


class ListPackageVersionsUseCase:
    def __init__(self, repository: PackageRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        *,
        package_name: str,
        limit: int,
        offset: int,
    ):
        return await self._repository.list_package_versions(
            package_name,
            pagination=Pagination(limit=limit, offset=offset),
        )
