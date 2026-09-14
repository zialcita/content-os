from uuid import uuid4
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException


class FieldError(BaseModel):
    model_config = ConfigDict(extra='forbid')
    field: str
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    field_errors: list[FieldError]
    retryable: bool
    correlation_id: str


class APIError(Exception):
    def __init__(self, code, status=422, message=None):
        self.code, self.status, self.message = code, status, message or code.replace('_', ' ').capitalize()


STATUS = {
    'UNAUTHENTICATED': 401, 'INVALID_LOGIN': 401, 'CSRF_INVALID': 403, 'ORIGIN_INVALID': 403,
    'NOT_FOUND': 404, 'FORBIDDEN': 403, 'ONBOARDING_DENIED': 403,
    'INVITATION_IDENTITY_MISMATCH': 403, 'OWNER_PROTECTED': 409,
    'STALE_VERSION': 409, 'IDEMPOTENCY_CONFLICT': 409, 'MEMBERSHIP_EXISTS': 409,
    'PRECONDITION_REQUIRED': 428, 'RATE_LIMITED': 429, 'INVITATION_INVALID': 422,
    'INVALID_INPUT': 422, 'IDEMPOTENCY_KEY_REQUIRED': 422,
}


def response(request, code, status, message=None, fields=None):
    correlation = getattr(request.state, 'correlation_id', str(uuid4()))
    headers = {'X-Correlation-ID': correlation, 'Cache-Control': 'no-store'}
    if status == 429:
        headers['Retry-After'] = '60'
    return JSONResponse(status_code=status, headers=headers, content={
        'code': code, 'message': message or code.replace('_', ' ').capitalize(),
        'field_errors': fields or [], 'retryable': status in (429, 503), 'correlation_id': correlation,
    })


def install_errors(app):
    @app.exception_handler(APIError)
    async def api_error(request: Request, exc: APIError):
        return response(request, exc.code, exc.status, exc.message)

    @app.exception_handler(DBAPIError)
    async def db_error(request: Request, exc: DBAPIError):
        # Never stringify SQLAlchemy exceptions (SQL params may be opaque credentials).
        code = getattr(getattr(exc.orig, 'diag', None), 'message_primary', '')
        if code not in STATUS:
            state = getattr(exc.orig, 'sqlstate', '')
            code = 'INVALID_INPUT' if state in ('23514', '23503', '23505', '22P02') else 'DATABASE_UNAVAILABLE'
        return response(request, code, STATUS.get(code, 503))

    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, exc: RequestValidationError):
        fields = [{'field': '.'.join(map(str, e['loc'])), 'code': 'INVALID_FIELD', 'message': 'Invalid field'} for e in exc.errors()]
        return response(request, 'VALIDATION_ERROR', 422, fields=fields)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return response(request, 'NOT_FOUND' if exc.status_code == 404 else 'HTTP_ERROR', exc.status_code)

    @app.exception_handler(Exception)
    async def internal(request: Request, exc: Exception):
        return response(request, 'INTERNAL_ERROR', 500)
