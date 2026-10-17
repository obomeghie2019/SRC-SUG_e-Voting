class ServiceError(Exception):
    """Business-rule error. Both APIs turn it into {"detail": message} with the given HTTP status."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message, self.status = message, status
