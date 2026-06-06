class NpmRegistryError(Exception):
    """Base error for NPM registry failures."""


class NpmPackageNotFoundError(NpmRegistryError):
    """Raised when package does not exist in registry."""


class NpmRegistryTimeoutError(NpmRegistryError):
    """Raised when registry request times out."""


class NpmRegistryMalformedResponseError(NpmRegistryError):
    """Raised when registry response does not match expected shape."""


class PackageListSourceError(Exception):
    """Base error for top package list source failures."""


class PackageListSourceTimeoutError(PackageListSourceError):
    """Raised when top package source request times out."""


class PackageListSourceMalformedContentError(PackageListSourceError):
    """Raised when top package source content cannot be parsed."""


class QueuePublishError(Exception):
    """Raised when a scan job cannot be published to the queue."""


class TarballDownloadError(Exception):
    """Base error for tarball download failures."""


class TarballDownloadTimeoutError(TarballDownloadError):
    """Raised when tarball download request times out."""


class TarballSizeLimitExceededError(TarballDownloadError):
    """Raised when downloaded tarball exceeds configured max bytes."""


class TarballIntegrityError(TarballDownloadError):
    """Raised when a downloaded tarball does not match its integrity metadata."""


class TarballExtractError(Exception):
    """Base error for tarball extraction failures."""


class TarballUnsafeMemberError(TarballExtractError):
    """Raised when an archive member is unsafe to extract."""


class TarballMalformedArchiveError(TarballExtractError):
    """Raised when tarball content is malformed or unreadable."""


class TarballExtractionLimitExceededError(TarballExtractError):
    """Raised when an archive exceeds configured extraction safety limits."""


class ScannerLimitExceededError(Exception):
    """Raised when static analysis exceeds configured file traversal limits."""
