from app.application.ports.package_repository import FindingFilters, FindingRead, PackageRepository, Pagination


_FINDING_TYPE_ALIASES = {
    "install_hook_added": "INSTALL_HOOK_ADDED",
    "install_hook_removed": "INSTALL_HOOK_REMOVED",
    "install_hook_present": "INSTALL_HOOK_PRESENT",
    "size_increase_medium": "SIZE_INCREASE_MEDIUM",
    "size_increase_high": "SIZE_INCREASE_HIGH",
    "executable_binary": "EXECUTABLE_BINARY",
    "obfuscated_code": "OBFUSCATED_CODE",
    "command_execution_pattern": "COMMAND_EXECUTION_PATTERN",
}


class ListFindingsUseCase:
    def __init__(self, repository: PackageRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        *,
        limit: int,
        offset: int,
        severity: str | None = None,
        finding_type: str | None = None,
        package_name: str | None = None,
    ) -> tuple[list[FindingRead], int]:
        normalized_type = self._normalize_finding_type(finding_type)
        return await self._repository.list_findings(
            filters=FindingFilters(
                severity=severity,
                finding_type=normalized_type,
                package_name=package_name,
            ),
            pagination=Pagination(limit=limit, offset=offset),
        )

    @staticmethod
    def _normalize_finding_type(finding_type: str | None) -> str | None:
        if not finding_type:
            return None
        lowered = finding_type.strip().lower()
        if lowered in _FINDING_TYPE_ALIASES:
            return _FINDING_TYPE_ALIASES[lowered]
        return finding_type.strip().upper()
