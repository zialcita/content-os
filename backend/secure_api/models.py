from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Role(str, Enum):
    ADMIN = 'ADMIN'
    EDITOR = 'EDITOR'
    REVIEWER = 'REVIEWER'
    PUBLISHER = 'PUBLISHER'
    VIEWER = 'VIEWER'


class LoginStart(Model):
    return_path: str = Field(min_length=1, max_length=1000)

    @field_validator('return_path')
    @classmethod
    def safe_path(cls, value):
        if not value.startswith('/') or value.startswith('//') or '\\' in value or any(ord(c) < 32 for c in value) or '%' in value:
            raise ValueError('Local absolute path required')
        return value


class AuthRedirect(Model):
    authorization_url: str
    expires_at: datetime


class User(Model):
    user_id: UUID
    oidc_subject: str
    display_name: str
    verified_email: str
    state: Literal['ACTIVE', 'SUSPENDED', 'DELETED']


class Session(Model):
    user: User
    active_workspace_id: UUID | None
    expires_at: datetime
    csrf_token: str


class Acknowledgement(Model):
    accepted: Literal[True]
    correlation_id: UUID


class WorkspaceSwitch(Model):
    workspace_id: UUID


class NamedTimezone(Model):
    name: str = Field(min_length=1, max_length=200)
    timezone: str = Field(min_length=1, max_length=100)

    @field_validator('timezone')
    @classmethod
    def timezone_valid(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Unknown IANA timezone') from None
        return value


class WorkspaceCreate(NamedTimezone):
    challenge_id: UUID


class Workspace(NamedTimezone):
    workspace_id: UUID
    owner_user_id: UUID
    revision: int
    state: str


class BrandWrite(NamedTimezone):
    pass


class Brand(NamedTimezone):
    brand_id: UUID
    workspace_id: UUID
    current_profile_version_id: UUID | None
    revision: int


class Membership(Model):
    membership_id: UUID
    workspace_id: UUID
    user_id: UUID
    roles: list[Role]
    state: str
    revision: int


class MembershipEdit(Model):
    roles: list[Role] = Field(min_length=1, max_length=5)
    # Foundation supports REVOKED rather than SUSPENDED. Reject unsupported state,
    # do not pretend that a suspension was persisted.
    state: Literal['ACTIVE']

    @field_validator('roles')
    @classmethod
    def unique_roles(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('Duplicate roles')
        return value


class BrandGrantEdit(Model):
    can_connect_social: bool


class BrandGrant(BrandGrantEdit):
    membership_id: UUID
    workspace_id: UUID
    brand_id: UUID


class InviteCreate(Model):
    email: str = Field(min_length=3, max_length=320)
    roles: list[Role] = Field(min_length=1, max_length=5)
    brand_ids: list[UUID] = Field(min_length=1, max_length=100)

    @field_validator('email')
    @classmethod
    def email_valid(cls, value):
        if '@' not in value or any(c.isspace() for c in value):
            raise ValueError('Invalid email')
        return value

    @field_validator('roles', 'brand_ids')
    @classmethod
    def unique_values(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('Duplicate value')
        return value


class Invitation(Model):
    revision: int = Field(ge=1)
    invitation_id: UUID
    workspace_id: UUID
    email: str
    roles: list[Role]
    brand_ids: list[UUID]
    expires_at: datetime
    state: str


class LocalInvitationReceipt(Model):
    invitation: Invitation
    delivery: Literal['LOCAL_RECEIPT_NOT_SENT']
    token: str


class InviteAccept(Model):
    token: str = Field(min_length=32, max_length=256)


class OnboardingStart(Model):
    access_code: str = Field(min_length=32, max_length=256)
    email: str = Field(min_length=3, max_length=320)


class OnboardingChallenge(Model):
    challenge_id: UUID
    expires_at: datetime
    next_action: Literal['VERIFY_IDENTITY']


T = TypeVar('T')


class Page(Model, Generic[T]):
    items: list[T]
    next_cursor: str | None
    has_more: bool
