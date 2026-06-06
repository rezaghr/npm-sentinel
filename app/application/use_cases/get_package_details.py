from app.application.ports.package_repository import PackageDetail, PackageRepository


class GetPackageDetailsUseCase:
    def __init__(self, repository: PackageRepository) -> None:
        self._repository = repository

    async def execute(self, package_name: str) -> PackageDetail | None:
        return await self._repository.get_package_detail(package_name)
