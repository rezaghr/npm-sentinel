import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.application.ports.package_registry import PackageRegistryMetadata, PackageVersionMetadata
from app.application.use_cases.scan_package import ScanPackageUseCase
from app.core.config import Settings
from app.core.exceptions import NpmRegistryTimeoutError, TarballDownloadTimeoutError
from app.infrastructure.db.models import FindingModel, PackageModel, PackageVersionModel, ScanResultModel
from app.infrastructure.db.session import create_database_engine
from app.infrastructure.db.unit_of_work import SqlAlchemyRepositoryUnitOfWorkFactory
from app.infrastructure.npm.tarball_downloader import TarballDownloader
from app.infrastructure.scanner.analyzer import StaticPackageAnalyzer
from app.infrastructure.scanner.extractor import SafeExtractor

pytestmark = pytest.mark.asyncio

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "tarballs"


class FakePackageRegistry:
    def __init__(self, metadata: PackageRegistryMetadata | None = None, error: Exception | None = None) -> None:
        self._metadata = metadata
        self._error = error

    async def fetch_metadata(self, package_name: str) -> PackageRegistryMetadata:
        if self._error is not None:
            raise self._error
        if self._metadata is None:
            raise RuntimeError("metadata not configured")
        return self._metadata


class FakeTarballDownloader(TarballDownloader):
    def __init__(self, fixtures_by_url: dict[str, Path], error_by_url: dict[str, Exception] | None = None) -> None:
        super().__init__(timeout_seconds=1.0, max_bytes=50_000_000, http_client=None)
        self._fixtures_by_url = fixtures_by_url
        self._error_by_url = error_by_url or {}

    async def download(self, tarball_url: str, destination_dir: Path, *, integrity: str | None = None) -> Path:
        if tarball_url in self._error_by_url:
            raise self._error_by_url[tarball_url]

        destination_dir.mkdir(parents=True, exist_ok=True)
        source = self._fixtures_by_url[tarball_url]
        target = destination_dir / source.name
        shutil.copyfile(source, target)
        return target


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or Settings().database_url
    os.environ["DATABASE_URL"] = url

    config = Config("alembic.ini")
    try:
        alembic_command.upgrade(config, "head")
    except Exception as exc:
        pytest.skip(f"PostgreSQL integration database is not available: {exc}")

    return url


@pytest_asyncio.fixture
async def session_factory(database_url: str):
    engine = create_database_engine(database_url)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async with engine.begin() as connection:
        await connection.execute(
            text("TRUNCATE findings, scan_results, package_versions, packages RESTART IDENTITY CASCADE")
        )

    yield factory
    await engine.dispose()


async def _row_count(session_factory, model: type) -> int:
    async with session_factory() as session:
        result = await session.execute(select(func.count()).select_from(model))
        return result.scalar_one()


def _metadata(
    *,
    package_name: str = "fixture-package",
    latest_url: str,
    previous_url: str | None = "https://example.test/previous.tgz",
    latest_scripts: dict[str, str] | None = None,
    previous_scripts: dict[str, str] | None = None,
    latest_size: int | None = 1000,
    previous_size: int | None = 1000,
) -> PackageRegistryMetadata:
    latest = PackageVersionMetadata(
        package_name=package_name,
        version="2.0.0",
        published_at=datetime(2026, 1, 2, tzinfo=UTC),
        tarball_url=latest_url,
        integrity="sha512-latest",
        unpacked_size=latest_size,
        file_count=10,
        package_json={"name": package_name, "version": "2.0.0"},
        dependencies={},
        scripts=latest_scripts or {},
    )
    previous = None
    if previous_url is not None:
        previous = PackageVersionMetadata(
            package_name=package_name,
            version="1.0.0",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            tarball_url=previous_url,
            integrity="sha512-previous",
            unpacked_size=previous_size,
            file_count=8,
            package_json={"name": package_name, "version": "1.0.0"},
            dependencies={},
            scripts=previous_scripts or {},
        )
    return PackageRegistryMetadata(
        package_name=package_name,
        latest_version=latest,
        previous_version=previous,
    )


def _use_case(
    *,
    session_factory,
    package_registry: FakePackageRegistry,
    tarball_downloader: FakeTarballDownloader,
) -> ScanPackageUseCase:
    return ScanPackageUseCase(
        repository_unit_of_work_factory=SqlAlchemyRepositoryUnitOfWorkFactory(session_factory),
        package_registry=package_registry,
        tarball_downloader=tarball_downloader,
        extractor=SafeExtractor(),
        analyzer=StaticPackageAnalyzer(),
    )


async def test_fake_package_scan_completes_successfully(session_factory) -> None:
    latest_url = "https://example.test/latest.tgz"
    previous_url = "https://example.test/previous.tgz"
    use_case = _use_case(
        session_factory=session_factory,
        package_registry=FakePackageRegistry(
            _metadata(latest_url=latest_url, previous_url=previous_url),
        ),
        tarball_downloader=FakeTarballDownloader(
            fixtures_by_url={
                latest_url: FIXTURES_DIR / "minimal_valid.tgz",
                previous_url: FIXTURES_DIR / "scan_clean_previous.tgz",
            }
        ),
    )

    await use_case.execute("fixture-package", "manual")

    assert await _row_count(session_factory, PackageModel) == 1
    assert await _row_count(session_factory, PackageVersionModel) == 2
    assert await _row_count(session_factory, ScanResultModel) == 1

    async with session_factory() as session:
        result = await session.execute(select(ScanResultModel))
        scan_result = result.scalar_one()
        assert scan_result.status == "completed"
        assert scan_result.score is not None
        assert scan_result.risk_level in {"low", "medium", "high"}

        package_result = await session.execute(select(PackageModel))
        package = package_result.scalar_one()
        assert package.latest_scanned_version == "2.0.0"
        assert package.last_scanned_at is not None


async def test_fake_package_with_install_hook_produces_finding(session_factory) -> None:
    latest_url = "https://example.test/latest-hook.tgz"
    previous_url = "https://example.test/previous-hook.tgz"
    use_case = _use_case(
        session_factory=session_factory,
        package_registry=FakePackageRegistry(
            _metadata(
                latest_url=latest_url,
                previous_url=previous_url,
                latest_scripts={"postinstall": "node postinstall.js"},
                previous_scripts={},
            )
        ),
        tarball_downloader=FakeTarballDownloader(
            fixtures_by_url={
                latest_url: FIXTURES_DIR / "scan_postinstall_latest.tgz",
                previous_url: FIXTURES_DIR / "scan_clean_previous.tgz",
            }
        ),
    )

    await use_case.execute("fixture-package", "manual")

    async with session_factory() as session:
        result = await session.execute(select(FindingModel.finding_type))
        finding_types = {item[0] for item in result.all()}
        assert "INSTALL_HOOK_ADDED" in finding_types


async def test_fake_package_with_binary_produces_finding(session_factory) -> None:
    latest_url = "https://example.test/latest-binary.tgz"
    previous_url = "https://example.test/previous-binary.tgz"
    use_case = _use_case(
        session_factory=session_factory,
        package_registry=FakePackageRegistry(
            _metadata(latest_url=latest_url, previous_url=previous_url),
        ),
        tarball_downloader=FakeTarballDownloader(
            fixtures_by_url={
                latest_url: FIXTURES_DIR / "scan_binary_latest.tgz",
                previous_url: FIXTURES_DIR / "scan_clean_previous.tgz",
            }
        ),
    )

    await use_case.execute("fixture-package", "manual")

    async with session_factory() as session:
        result = await session.execute(select(FindingModel.finding_type))
        finding_types = {item[0] for item in result.all()}
        assert "EXECUTABLE_BINARY" in finding_types


async def test_metadata_fetch_failure_marks_pending_scan_failed(session_factory) -> None:
    use_case = _use_case(
        session_factory=session_factory,
        package_registry=FakePackageRegistry(error=NpmRegistryTimeoutError("registry timeout")),
        tarball_downloader=FakeTarballDownloader(fixtures_by_url={}),
    )

    with pytest.raises(NpmRegistryTimeoutError):
        await use_case.execute("fixture-package", "manual")

    assert await _row_count(session_factory, PackageModel) == 1
    assert await _row_count(session_factory, PackageVersionModel) == 0
    assert await _row_count(session_factory, ScanResultModel) == 1
    assert await _row_count(session_factory, FindingModel) == 0
    async with session_factory() as session:
        result = await session.execute(select(ScanResultModel))
        scan_result = result.scalar_one()
        assert scan_result.status == "failed"
        assert scan_result.latest_version is None
        assert scan_result.error_message == "registry timeout"


async def test_post_metadata_failure_marks_running_scan_failed(session_factory) -> None:
    latest_url = "https://example.test/latest-fail.tgz"
    previous_url = "https://example.test/previous-fail.tgz"
    use_case = _use_case(
        session_factory=session_factory,
        package_registry=FakePackageRegistry(
            _metadata(latest_url=latest_url, previous_url=previous_url),
        ),
        tarball_downloader=FakeTarballDownloader(
            fixtures_by_url={
                latest_url: FIXTURES_DIR / "minimal_valid.tgz",
                previous_url: FIXTURES_DIR / "scan_clean_previous.tgz",
            },
            error_by_url={latest_url: TarballDownloadTimeoutError("download timeout")},
        ),
    )

    with pytest.raises(TarballDownloadTimeoutError):
        await use_case.execute("fixture-package", "manual")

    assert await _row_count(session_factory, ScanResultModel) == 1
    async with session_factory() as session:
        result = await session.execute(select(ScanResultModel))
        scan_result = result.scalar_one()
        assert scan_result.status == "failed"
        assert scan_result.error_message


async def test_duplicate_scan_creates_independent_attempts(session_factory) -> None:
    latest_url = "https://example.test/latest-dup.tgz"
    previous_url = "https://example.test/previous-dup.tgz"
    metadata = _metadata(
        latest_url=latest_url,
        previous_url=previous_url,
        latest_size=1000,
        previous_size=1000,
    )
    use_case = _use_case(
        session_factory=session_factory,
        package_registry=FakePackageRegistry(metadata),
        tarball_downloader=FakeTarballDownloader(
            fixtures_by_url={
                latest_url: FIXTURES_DIR / "scan_binary_latest.tgz",
                previous_url: FIXTURES_DIR / "scan_clean_previous.tgz",
            }
        ),
    )

    await use_case.execute("fixture-package", "manual")
    await use_case.execute("fixture-package", "manual")

    assert await _row_count(session_factory, ScanResultModel) == 2
    assert await _row_count(session_factory, FindingModel) == 2
