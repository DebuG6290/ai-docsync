class DocSyncError(Exception):
    """Base error intended to be shown clearly by the CLI."""


class GitError(DocSyncError):
    pass


class MappingError(DocSyncError):
    pass


class ModelError(DocSyncError):
    """A failed provider/API call or invalid model response contract."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "MODEL_CONTRACT_ERROR",
        retryable: bool = False,
        diagnostics: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.retryable = retryable
        self.diagnostics = diagnostics or {}


class ConflictError(DocSyncError):
    pass

