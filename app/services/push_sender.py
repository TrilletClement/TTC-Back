"""Sends push notifications to phones through Firebase Cloud Messaging.

Only the scheduler sends (departure alerts) — plus the API's "test
notification". Needs FIREBASE_CREDENTIALS_FILE (service-account JSON, a
secret never committed); without it sending is a logged no-op, so local
setups and tests run without Firebase.
"""
import logging
import os
from dataclasses import dataclass, field

from app.core.config import settings

logger = logging.getLogger(__name__)

ANDROID_CHANNEL = "departures"


@dataclass
class Push:
    token: str
    title: str
    body: str
    data: dict[str, str] = field(default_factory=dict)


class PushSender:
    def __init__(self):
        self._app = None
        self._disabled = False

    def _firebase(self):
        if self._app is not None or self._disabled:
            return self._app
        path = settings.FIREBASE_CREDENTIALS_FILE
        if not path or not os.path.isfile(path):
            logger.warning("FIREBASE_CREDENTIALS_FILE not set or missing: push notifications disabled")
            self._disabled = True
            return None
        import firebase_admin
        from firebase_admin import credentials
        self._app = firebase_admin.initialize_app(credentials.Certificate(path), name="push")
        return self._app

    @property
    def enabled(self) -> bool:
        return self._firebase() is not None

    def send(self, pushes: list[Push]) -> list[str]:
        """Sends; returns the tokens FCM says are dead (app uninstalled…) so the caller drops them."""
        app = self._firebase()
        if app is None or not pushes:
            return []
        from firebase_admin import messaging
        messages = [
            messaging.Message(
                token=p.token,
                notification=messaging.Notification(title=p.title, body=p.body),
                data=p.data,
                android=messaging.AndroidConfig(
                    priority="high",
                    # A departure is useless once missed.
                    ttl=600,
                    notification=messaging.AndroidNotification(channel_id=ANDROID_CHANNEL),
                ),
            )
            for p in pushes
        ]
        dead = []
        # send_each accepts at most 500 messages per call.
        for start in range(0, len(messages), 500):
            batch = messages[start:start + 500]
            response = messaging.send_each(batch, app=app)
            for msg, r in zip(batch, response.responses):
                if r.success:
                    continue
                if isinstance(r.exception, (messaging.UnregisteredError, messaging.SenderIdMismatchError)):
                    dead.append(msg.token)
                else:
                    logger.warning("Push to a device failed: %s", r.exception)
        return dead


push_sender = PushSender()
