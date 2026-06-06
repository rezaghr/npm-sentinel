from dataclasses import dataclass

from app.application.ports.package_list_source import PackageListSource
from app.application.use_cases.enqueue_scan import EnqueueScanUseCase


@dataclass(frozen=True)
class EnqueueTopPackagesBatchResult:
    requested: int
    enqueued: int
    skipped: int


class EnqueueTopPackagesBatchUseCase:
    def __init__(
        self,
        *,
        package_list_source: PackageListSource,
        enqueue_scan_use_case: EnqueueScanUseCase,
    ) -> None:
        self._package_list_source = package_list_source
        self._enqueue_scan_use_case = enqueue_scan_use_case

    async def execute(self, *, limit: int, reason: str = "manual_batch") -> EnqueueTopPackagesBatchResult:
        package_names = await self._package_list_source.load_package_names(limit=limit)
        enqueued = 0
        skipped = 0

        for package_name in package_names:
            normalized_name = package_name.strip()
            if not normalized_name:
                skipped += 1
                continue
            try:
                await self._enqueue_scan_use_case.execute(normalized_name, reason=reason)
                enqueued += 1
            except ValueError:
                skipped += 1

        return EnqueueTopPackagesBatchResult(
            requested=len(package_names),
            enqueued=enqueued,
            skipped=skipped,
        )
