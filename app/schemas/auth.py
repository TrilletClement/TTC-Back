import re

from pydantic import BaseModel, field_validator

PASSWORD_MIN_LENGTH = 8


def validate_password_strength(password: str) -> str:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f'Password must be at least {PASSWORD_MIN_LENGTH} characters long.')
    if not re.search(r'[A-Z]', password):
        raise ValueError('Password must contain at least one uppercase letter.')
    if not re.search(r'[a-z]', password):
        raise ValueError('Password must contain at least one lowercase letter.')
    if not re.search(r'[0-9]', password):
        raise ValueError('Password must contain at least one digit.')
    if not re.search(r'[^A-Za-z0-9\s]', password):
        raise ValueError('Password must contain at least one special character.')
    return password


class RegisterRequest(BaseModel):
    email: str
    password: str
    turnstileToken: str
    preferred_agency: str = ''

    @field_validator('password')
    @classmethod
    def _check_password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str

    @field_validator('password')
    @classmethod
    def _check_password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class ResendConfirmRequest(BaseModel):
    email: str


class PreferencesUpdate(BaseModel):
    preferred_agency: str | None = None
    alert_display_pref: str | None = None


class GoogleExchangeRequest(BaseModel):
    code: str