from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.db.repositories import SqlAlchemyPackageRepository


class SqlAlchemyRepositoryUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._transaction = None

    async def __aenter__(self) -> SqlAlchemyPackageRepository:
        self._session = self._session_factory()
        self._transaction = self._session.begin()
        await self._transaction.__aenter__()
        return SqlAlchemyPackageRepository(self._session)

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._transaction is not None:
            await self._transaction.__aexit__(exc_type, exc, traceback)
        if self._session is not None:
            await self._session.close()


class SqlAlchemyRepositoryUnitOfWorkFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyRepositoryUnitOfWork:
        return SqlAlchemyRepositoryUnitOfWork(self._session_factory)
