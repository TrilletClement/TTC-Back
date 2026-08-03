from pydantic import BaseModel


class RegisterRequest(BaseModel):
    email: str
    password: str
    turnstileToken: str
    preferred_agency: str = ''


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class ResendConfirmRequest(BaseModel):
    email: str


class PreferencesUpdate(BaseModel):
    preferred_agency: str | None = None
    alert_display_pref: str | None = None