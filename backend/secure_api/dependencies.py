"""Feature integration: request-managed READ COMMITTED, session-authenticated connection.

Use only inside a router installed on create_app(). Never commit/rollback this
connection or retain it outside the request. Never obtain auth/admin engines in
feature modules. Scope is not authority after this transaction ends.
"""
from dataclasses import dataclass
from uuid import UUID
from fastapi import Request
from sqlalchemy.engine import Connection
from sqlalchemy import text
from .errors import APIError


@dataclass(frozen=True)
class Scope:
    user_id: UUID
    workspace_id: UUID
    brand_id: UUID | None
    membership_id: UUID
    connection: Connection


def get_scope(request: Request, workspace_id: UUID, brand_id: UUID | None, action: str = 'read') -> Scope:
    connection = getattr(request.state, 'identity_connection', None)
    user = getattr(request.state, 'identity_user_id', None)
    if connection is None or user is None or not connection.in_transaction():
        raise APIError('UNAUTHENTICATED', 401)
    if action != 'read' and request.method in ('GET', 'HEAD', 'OPTIONS'):
        raise APIError('UNSAFE_METHOD', 403)
    membership = connection.execute(text('SELECT cos_v6.api_authorize(:w,:b,:a)'),
                                    {'w': workspace_id, 'b': brand_id, 'a': action}).scalar_one()
    return Scope(user, workspace_id, brand_id, membership, connection)


def connection(request: Request) -> Connection:
    value = getattr(request.state, 'identity_connection', None)
    if value is None:
        raise APIError('UNAUTHENTICATED', 401)
    return value
