from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base application error carrying a stable error_code for API clients."""

    def __init__(self, message: str, error_code: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str, error_code: str = "NOT_FOUND"):
        super().__init__(message, error_code, status.HTTP_404_NOT_FOUND)


class PermissionDeniedError(AppError):
    def __init__(self, message: str = "You do not have permission to perform this action", error_code: str = "PERMISSION_DENIED"):
        super().__init__(message, error_code, status.HTTP_403_FORBIDDEN)


class ConflictError(AppError):
    def __init__(self, message: str, error_code: str = "CONFLICT"):
        super().__init__(message, error_code, status.HTTP_409_CONFLICT)


def _envelope(message: str, error_code: str) -> dict:
    return {"success": False, "message": message, "error_code": error_code}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=_envelope(exc.message, exc.error_code))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope("Invalid request data", "VALIDATION_ERROR") | {"details": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        # Never leak internal stack traces to the client (spec #46).
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("An unexpected error occurred", "INTERNAL_ERROR"),
        )
