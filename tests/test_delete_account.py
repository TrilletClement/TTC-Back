"""AuthService.delete_account — anonymisation, with fake repositories."""
import pytest

import app.orm_models  # noqa: F401 — registers every mapper
from app.core.security.jwt import hash_password
from app.domain.exceptions import ValidationError
from app.orm_models.auth import User
from app.services.authService import AuthService


class _FakeAuthRepo:
    def __init__(self):
        self.archived_for: list[int] = []
        self.push_deleted_for: list[int] = []
        self.commits = 0

    def archive_boards_of(self, user_id: int) -> None:
        self.archived_for.append(user_id)

    def delete_push_data_of(self, user_id: int) -> None:
        self.push_deleted_for.append(user_id)

    def commit(self) -> None:
        self.commits += 1


class _FakeNewsletterRepo:
    def __init__(self, subscriber=None):
        self.subscriber = subscriber
        self.deleted = []

    def get_by_email(self, email):
        return self.subscriber if self.subscriber and self.subscriber.email == email else None

    def delete(self, subscriber):
        self.deleted.append(subscriber)


class _Subscriber:
    def __init__(self, email):
        self.email = email


def _user(password: str | None = "Secret-pass-1") -> User:
    return User(
        id=42, email="Jane@Example.com", active=True, fs_uniquifier="old",
        password=hash_password(password) if password else None, google_id="g-123",
        preferred_agency="STIB", alert_display_pref="banner",
        reset_token="r", confirmation_token="c", oauth_handoff_token="o",
    )


def test_deletes_and_anonymises_everything_personal():
    repo, news = _FakeAuthRepo(), _FakeNewsletterRepo(_Subscriber("Jane@Example.com"))
    user = _user()
    AuthService(repo).delete_account(user, " jane@example.com ", "Secret-pass-1", news)

    assert user.active is False
    assert user.email.endswith("@deleted.invalid") and "jane" not in user.email.lower()
    assert user.password is None and user.google_id is None
    assert user.fs_uniquifier != "old"
    assert user.preferred_agency is None and user.alert_display_pref is None
    assert user.reset_token is None and user.confirmation_token is None and user.oauth_handoff_token is None
    assert repo.archived_for == [42] and repo.commits == 1
    assert repo.push_deleted_for == [42]
    assert len(news.deleted) == 1


def test_wrong_confirmation_email_changes_nothing():
    repo, user = _FakeAuthRepo(), _user()
    with pytest.raises(ValidationError):
        AuthService(repo).delete_account(user, "someone@else.com", "Secret-pass-1", _FakeNewsletterRepo())
    assert user.active is True and repo.commits == 0 and repo.archived_for == []


@pytest.mark.parametrize("password", [None, "", "wrong"])
def test_wrong_password_changes_nothing(password):
    repo, user = _FakeAuthRepo(), _user()
    with pytest.raises(ValidationError):
        AuthService(repo).delete_account(user, "jane@example.com", password, _FakeNewsletterRepo())
    assert user.active is True and repo.commits == 0


def test_google_only_account_needs_no_password():
    repo, user = _FakeAuthRepo(), _user(password=None)
    AuthService(repo).delete_account(user, "jane@example.com", None, _FakeNewsletterRepo())
    assert user.active is False


def test_two_deletions_never_collide_on_email():
    a, b = _user(), _user()
    AuthService(_FakeAuthRepo()).delete_account(a, "jane@example.com", "Secret-pass-1", _FakeNewsletterRepo())
    AuthService(_FakeAuthRepo()).delete_account(b, "jane@example.com", "Secret-pass-1", _FakeNewsletterRepo())
    assert a.email != b.email
