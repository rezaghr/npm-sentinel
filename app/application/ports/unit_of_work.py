from typing import Protocol

from app.application.ports.package_repository import PackageRepository


class RepositoryUnitOfWork(Protocol):
    async def __aenter__(self) -> PackageRepository:
        ...

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        ...


class RepositoryUnitOfWorkFactory(Protocol):
    def __call__(self) -> RepositoryUnitOfWork:
        ...
