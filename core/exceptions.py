"""Custom exception hierarchy.

Every exception maps to an HTTP status code and carries a user-friendly
Arabic message plus a developer-friendly English detail string.
"""


class AppError(Exception):
    """Base application error."""

    status_code = 500
    message = 'حدث خطأ غير متوقع'
    detail = 'Internal server error'

    def __init__(self, message=None, detail=None):
        self.message = message or self.__class__.message
        self.detail = detail or self.__class__.detail
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    message = 'العنصر غير موجود'
    detail = 'Resource not found'


class AuthenticationError(AppError):
    """Not authenticated — login required (HTTP 401)."""

    status_code = 401
    message = 'يرجى تسجيل الدخول أولاً'
    detail = 'Authentication required'


class AuthorizationError(AppError):
    """Authenticated but lacks permission (HTTP 403)."""

    status_code = 403
    message = 'ليس لديك صلاحية للوصول'
    detail = 'Authorization denied'


# ── Backward-compatible aliases (removed once all call sites are migrated) ────
UnauthorizedError = AuthenticationError
ForbiddenError = AuthorizationError


class ValidationError(AppError):
    status_code = 422
    message = 'بيانات غير صحيحة'
    detail = 'Validation error'

    def __init__(self, errors=None, **kwargs):
        self.errors = errors or {}
        super().__init__(**kwargs)


class ConflictError(AppError):
    status_code = 409
    message = 'البيانات موجودة مسبقاً'
    detail = 'Resource conflict'


class ProtectedAccountError(AppError):
    """An account protected against destructive operations (the super-admin).

    Thrown by the service/repository layer so that even a direct request to a
    delete/deactivate/demote endpoint is refused, not merely hidden in the UI.
    """

    status_code = 403
    message = 'هذا الحساب محمي ولا يمكن تعديله'
    detail = 'Protected account'


class RateLimitError(AppError):
    status_code = 429
    message = 'تم تجاوز الحد المسموح، حاول لاحقاً'
    detail = 'Rate limit exceeded'


class DatabaseError(AppError):
    status_code = 500
    message = 'خطأ في قاعدة البيانات'
    detail = 'Database error'
