import os
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.application.ports.package_repository import (
    FindingCreate,
    FindingFilters,
    PackageListFilters,
    PackageVersionMetadata,
    Pagination,
    ScanResultFilters,
)
from app.core.config import Settings
from app.infrastructure.db.models import FindingModel, PackageModel, PackageVersionModel, ScanResultModel
from app.infrastructure.db.repositories import SqlAlchemyPackageRepository
from app.infrastructure.db.session import create_database_engine

pytestmark = pytest.mark.asyncio


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
async def db_session(database_url: str):
    engine = create_database_engine(database_url)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async with engine.begin() as connection:
        await connection.execute(
            text("TRUNCATE findings, scan_results, package_versions, packages RESTART IDENTITY CASCADE")
        )

    async with session_factory() as session:
        yield session

    await engine.dispose()


async def count_rows(session, model: type) -> int:
    result = await session.execute(select(func.count()).select_from(model))
    return result.scalar_one()


async def test_create_and_fetch_package(db_session) -> None:
    repo = SqlAlchemyPackageRepository(db_session)

    async with db_session.begin():
        package = await repo.upsert_package("lodash")
        fetched = await repo.get_by_name("lodash")

    assert fetched is not None
    assert fetched.id == package.id
    assert fetched.name == "lodash"


async def test_package_upsert_is_idempotent(db_session) -> None:
    repo = SqlAlchemyPackageRepository(db_session)

    async with db_session.begin():
        first = await repo.upsert_package("lodash")
        second = await repo.upsert_package("lodash")

    assert first.id == second.id
    assert await count_rows(db_session, PackageModel) == 1


async def test_package_version_persists_jsonb_metadata(db_session) -> None:
    repo = SqlAlchemyPackageRepository(db_session)
    metadata = PackageVersionMetadata(
        published_at=datetime(2026, 5, 27, tzinfo=UTC),
        tarball_url="https://registry.npmjs.org/lodash/-/lodash-4.17.21.tgz",
        integrity="sha512-example",
        unpacked_size=123456,
        file_count=42,
        package_json={"name": "lodash", "version": "4.17.21"},
        dependencies={"left-pad": "^1.3.0"},
        scripts={"postinstall": "node install.js"},
    )

    async with db_session.begin():
        package = await repo.upsert_package("lodash")
        version = await repo.upsert_package_version(package.id, "4.17.21", metadata)

    assert version.package_id == package.id
    assert version.package_json["version"] == "4.17.21"
    assert version.dependencies == {"left-pad": "^1.3.0"}
    assert version.scripts == {"postinstall": "node install.js"}


async def test_package_version_upsert_is_idempotent_and_updates_metadata(db_session) -> None:
    repo = SqlAlchemyPackageRepository(db_session)

    async with db_session.begin():
        package = await repo.upsert_package("lodash")
        first = await repo.upsert_package_version(
            package.id,
            "4.17.21",
            PackageVersionMetadata(file_count=10, package_json={"version": "4.17.21"}),
        )
        second = await repo.upsert_package_version(
            package.id,
            "4.17.21",
            PackageVersionMetadata(file_count=11, package_json={"version": "4.17.21", "updated": True}),
        )

    assert first.id == second.id
    assert second.file_count == 11
    assert second.package_json["updated"] is True
    assert await count_rows(db_session, PackageVersionModel) == 1


async def test_scan_result_create_records_separate_attempts_for_same_comparison(db_session) -> None:
    repo = SqlAlchemyPackageRepository(db_session)

    async with db_session.begin():
        package = await repo.upsert_package("lodash")
        first = await repo.create_scan_result(package.id, "4.17.21", "4.17.20")
        second = await repo.create_scan_result(package.id, "4.17.21", "4.17.20")

    assert first.id != second.id
    assert second.status == "running"
    assert await count_rows(db_session, ScanResultModel) == 2


async def test_scan_result_create_allows_pending_metadata_attempt(db_session) -> None:
    repo = SqlAlchemyPackageRepository(db_session)

    async with db_session.begin():
        package = await repo.upsert_package("brand-new-package")
        scan = await repo.create_scan_result(package.id, None, None)

    assert scan.latest_version is None
    assert scan.previous_version is None
    assert await count_rows(db_session, ScanResultModel) == 1


async def test_set_scan_versions_updates_running_scan(db_session) -> None:
    repo = SqlAlchemyPackageRepository(db_session)

    async with db_session.begin():
        package = await repo.upsert_package("versioned-package")
        scan = await repo.create_scan_result(package.id, None, None)
        await repo.set_scan_versions(scan.id, "2.0.0", "1.0.0")

    await db_session.refresh(scan)
    assert scan.latest_version == "2.0.0"
    assert scan.previous_version == "1.0.0"


async def test_mark_scan_completed(db_session) -> None:
    repo = SqlAlchemyPackageRepository(db_session)

    async with db_session.begin():
        package = await repo.upsert_package("lodash")
        scan = await repo.create_scan_result(package.id, "4.17.21", "4.17.20")
        await repo.mark_scan_completed(scan.id, score=75, risk_level="high")

    await db_session.refresh(scan)
    assert scan.status == "completed"
    assert scan.score == 75
    assert scan.risk_level == "high"
    assert scan.error_message is None
    assert scan.finished_at is not None


async def test_mark_scan_failed(db_session) -> None:
    repo = SqlAlchemyPackageRepository(db_session)

    async with db_session.begin():
        package = await repo.upsert_package("lodash")
        scan = await repo.create_scan_result(package.id, "4.17.21", "4.17.20")
        await repo.mark_scan_failed(scan.id, "registry timeout")

    await db_session.refresh(scan)
    assert scan.status == "failed"
    assert scan.error_message == "registry timeout"
    assert scan.finished_at is not None


async def test_mark_scan_failed_does_not_overwrite_completed_scan(db_session) -> None:
    repo = SqlAlchemyPackageRepository(db_session)

    async with db_session.begin():
        package = await repo.upsert_package("lodash")
        scan = await repo.create_scan_result(package.id, "4.17.21", "4.17.20")
        await repo.mark_scan_completed(scan.id, score=75, risk_level="high")
        await repo.mark_scan_failed(scan.id, "late retry failed")

    await db_session.refresh(scan)
    assert scan.status == "completed"
    assert scan.error_message is None


async def test_add_findings(db_session) -> None:
    repo = SqlAlchemyPackageRepository(db_session)

    async with db_session.begin():
        package = await repo.upsert_package("lodash")
        scan = await repo.create_scan_result(package.id, "4.17.21", "4.17.20")
        await repo.add_findings(
            scan.id,
            [
                FindingCreate(
                    finding_type="INSTALL_HOOK_PRESENT",
                    severity="medium",
                    category="scripts",
                    file_path=None,
                    description="Package contains an install hook.",
                    evidence="postinstall",
                ),
                FindingCreate(
                    finding_type="EXECUTABLE_BINARY",
                    severity="high",
                    category="binary",
                    file_path="bin/tool",
                    description="Executable binary found.",
                ),
            ],
        )

    result = await db_session.execute(select(FindingModel).order_by(FindingModel.id))
    findings = result.scalars().all()

    assert len(findings) == 2
    assert {finding.scan_result_id for finding in findings} == {scan.id}
    assert findings[0].evidence == "postinstall"
    assert findings[1].file_path == "bin/tool"


async def test_list_packages_filters_by_latest_completed_risk_level(db_session) -> None:
    repo = SqlAlchemyPackageRepository(db_session)
    metadata = PackageVersionMetadata(package_json={"name": "pkg"}, dependencies={}, scripts={})

    async with db_session.begin():
        high_package = await repo.upsert_package("high-risk")
        low_package = await repo.upsert_package("low-risk")

        await repo.upsert_package_version(high_package.id, "1.0.0", metadata)
        await repo.upsert_package_version(low_package.id, "1.0.0", metadata)

        high_scan = await repo.create_scan_result(high_package.id, "1.0.0", None)
        low_scan = await repo.create_scan_result(low_package.id, "1.0.0", None)

        await repo.mark_scan_completed(high_scan.id, score=90, risk_level="high")
        await repo.mark_scan_completed(low_scan.id, score=10, risk_level="low")

    items, total = await repo.list_packages(
        filters=PackageListFilters(risk_level="high"),
        pagination=Pagination(limit=20, offset=0),
    )

    assert total == 1
    assert [item.name for item in items] == ["high-risk"]
    assert items[0].latest_scan_risk_level == "high"


async def test_get_package_detail_returns_latest_scan(db_session) -> None:
    repo = SqlAlchemyPackageRepository(db_session)
    metadata = PackageVersionMetadata(package_json={"name": "pkg"}, dependencies={}, scripts={})

    async with db_session.begin():
        package = await repo.upsert_package("detail-package")
        await repo.upsert_package_version(package.id, "1.0.0", metadata)
        scan = await repo.create_scan_result(package.id, "1.0.0", None)
        await repo.mark_scan_completed(scan.id, score=72, risk_level="medium")
        await repo.add_findings(
            scan.id,
            [
                FindingCreate(
                    finding_type="OBFUSCATED_CODE",
                    severity="medium",
                    category="code",
                    description="Detected eval usage",
                    evidence="eval(",
                )
            ],
        )

    detail = await repo.get_package_detail("detail-package")

    assert detail is not None
    assert detail.name == "detail-package"
    assert detail.latest_scan is not None
    assert detail.latest_scan.status == "completed"
    assert detail.versions_count == 1
    assert detail.findings_count == 1


async def test_list_package_versions_returns_latest_first(db_session) -> None:
    repo = SqlAlchemyPackageRepository(db_session)

    async with db_session.begin():
        package = await repo.upsert_package("version-list-package")
        await repo.upsert_package_version(
            package.id,
            "1.0.0",
            PackageVersionMetadata(
                published_at=datetime(2026, 1, 1, tzinfo=UTC),
                unpacked_size=100,
                package_json={"name": "version-list-package", "version": "1.0.0"},
                dependencies={"dep-a": "^1.0.0"},
                scripts={"preinstall": "echo old"},
            ),
        )
        await repo.upsert_package_version(
            package.id,
            "1.1.0",
            PackageVersionMetadata(
                published_at=datetime(2026, 2, 1, tzinfo=UTC),
                unpacked_size=150,
                package_json={"name": "version-list-package", "version": "1.1.0"},
                dependencies={"dep-a": "^1.1.0"},
                scripts={"postinstall": "echo new"},
            ),
        )

    items, total = await repo.list_package_versions(
        "version-list-package",
        pagination=Pagination(limit=10, offset=0),
    )

    assert total == 2
    assert [item.version for item in items] == ["1.1.0", "1.0.0"]
    assert items[0].unpacked_size == 150
    assert items[1].scripts["preinstall"] == "echo old"


async def test_list_scan_results_filters_by_status(db_session) -> None:
    repo = SqlAlchemyPackageRepository(db_session)

    async with db_session.begin():
        package = await repo.upsert_package("scan-filter-package")
        completed = await repo.create_scan_result(package.id, "1.0.0", None)
        failed = await repo.create_scan_result(package.id, "1.1.0", "1.0.0")
        await repo.mark_scan_completed(completed.id, score=20, risk_level="low")
        await repo.mark_scan_failed(failed.id, "download failed")

    items, total = await repo.list_scan_results(
        filters=ScanResultFilters(status="failed"),
        pagination=Pagination(limit=20, offset=0),
    )

    assert total == 1
    assert len(items) == 1
    assert items[0].status == "failed"
    assert items[0].package_name == "scan-filter-package"


async def test_list_findings_filters_by_severity(db_session) -> None:
    repo = SqlAlchemyPackageRepository(db_session)

    async with db_session.begin():
        package = await repo.upsert_package("finding-filter-package")
        scan = await repo.create_scan_result(package.id, "1.0.0", None)
        await repo.add_findings(
            scan.id,
            [
                FindingCreate(
                    finding_type="EXECUTABLE_BINARY",
                    severity="high",
                    category="binary",
                    description="Binary present",
                ),
                FindingCreate(
                    finding_type="INSTALL_HOOK_PRESENT",
                    severity="low",
                    category="scripts",
                    description="Hook present",
                ),
            ],
        )

    items, total = await repo.list_findings(
        filters=FindingFilters(severity="high"),
        pagination=Pagination(limit=20, offset=0),
    )

    assert total == 1
    assert len(items) == 1
    assert items[0].severity == "high"
    assert items[0].finding_type == "EXECUTABLE_BINARY"
