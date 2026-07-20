import asyncio
import html
import traceback as _tb
from typing import Optional

from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from app.core.config import settings

ADMIN_ALERT_RECIPIENTS = ["admin@trillet.be"]

mail_config = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    USE_CREDENTIALS=True
)

fast_mail = FastMail(mail_config)

async def send_reset_email(email: str, reset_url: str):
    message = MessageSchema(
        subject="Réinitialisation de votre mot de passe",
        recipients=[email],
        body=f"""
        <h3>Réinitialisation de mot de passe</h3>
        <p>Cliquez sur ce lien pour réinitialiser votre mot de passe :</p>
        <a href="{reset_url}">{reset_url}</a>
        <p>Ce lien expire dans 1 heure.</p>
        """,
        subtype="html"
    )
    await fast_mail.send_message(message)
    
    
async def send_confirmation_email(email: str, confirmation_url: str):
    html_body = f"""
<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <p>Bonjour,</p>
    <p>Merci de vous être inscrit sur <strong>transport.trillet.be</strong>.</p>
    <p>Veuillez confirmer votre adresse email en cliquant sur le bouton ci-dessous :</p>
    <p style="text-align: center; margin: 30px 0;">
        <a href="{confirmation_url}"
           style="background-color: #4A90E2; color: white; padding: 12px 24px;
                  text-decoration: none; border-radius: 4px; display: inline-block;">
            Confirmer mon email
        </a>
    </p>
    <p>Ou copiez ce lien dans votre navigateur :</p>
    <p style="word-break: break-all; color: #666; font-size: 13px;">{confirmation_url}</p>
    <p>Ce lien expire dans <strong>24 heures</strong>.</p>
    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
    <p style="font-size: 12px; color: #999;">
        Si vous n'avez pas créé de compte sur transport.trillet.be, ignorez cet email.<br>
        transport.trillet.be — Belgique
    </p>
</body>
</html>
    """

    text_body = f"""Bonjour,

Merci de vous être inscrit sur transport.trillet.be.

Confirmez votre adresse email via ce lien :
{confirmation_url}

Ce lien expire dans 24 heures.

Si vous n'avez pas créé de compte, ignorez cet email.
transport.trillet.be — Belgique
    """

    message = MessageSchema(
        subject="Confirmez votre adresse email — transport.trillet.be",
        recipients=[email],
        body=html_body,
        subtype="html",
    )
    await fast_mail.send_message(message)


async def send_gift_email(
    recipient_email: str,
    recipient_name: str,
    buyer_email: str,
    message: Optional[str],
    claim_url: str,
) -> None:
    safe_name    = html.escape(recipient_name)
    safe_buyer   = html.escape(buyer_email)
    message_html = f'<p style="font-style: italic;">« {html.escape(message)} »</p>' if message else ""

    html_body = f"""
<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <p>Bonjour {safe_name},</p>
    <p><strong>{safe_buyer}</strong> vous offre une board sur <strong>transport.trillet.be</strong> !</p>
    {message_html}
    <p>Cliquez sur le bouton ci-dessous pour accepter ce cadeau et le gérer depuis votre propre compte :</p>
    <p style="text-align: center; margin: 30px 0;">
        <a href="{claim_url}"
           style="background-color: #4A90E2; color: white; padding: 12px 24px;
                  text-decoration: none; border-radius: 4px; display: inline-block;">
            Accepter mon cadeau
        </a>
    </p>
    <p>Ou copiez ce lien dans votre navigateur :</p>
    <p style="word-break: break-all; color: #666; font-size: 13px;">{claim_url}</p>
    <p>Ce lien expire dans <strong>30 jours</strong>.</p>
    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
    <p style="font-size: 12px; color: #999;">
        transport.trillet.be — Belgique
    </p>
</body>
</html>
    """

    message_obj = MessageSchema(
        subject=f"{buyer_email} vous offre une board — transport.trillet.be",
        recipients=[recipient_email],
        body=html_body,
        subtype="html",
    )
    await fast_mail.send_message(message_obj)


async def send_support_ticket_alert(
    ticket_id: int,
    subject: str,
    message: str,
    user_email: str,
    order_ref: Optional[str],
) -> None:
    safe_subject = html.escape(subject)
    safe_message = html.escape(message)
    safe_email   = html.escape(user_email)
    order_line   = f"<p><strong>Order:</strong> {html.escape(order_ref)}</p>" if order_ref else ""

    body = f"""
<h3>New support ticket #{ticket_id} — {safe_subject}</h3>
<p><strong>From:</strong> {safe_email}</p>
{order_line}
<p><strong>Message:</strong></p>
<pre style="background:#f5f5f5;padding:12px;border-radius:4px;white-space:pre-wrap;">{safe_message}</pre>
<hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
<p style="font-size:12px;color:#999;">transport.trillet.be — support</p>
"""
    message_obj = MessageSchema(
        subject=f"[transport.trillet.be] Support ticket #{ticket_id} — {subject}",
        recipients=ADMIN_ALERT_RECIPIENTS,
        body=body,
        subtype="html",
    )
    await fast_mail.send_message(message_obj)


async def send_support_reply(user_email: str, subject: str, reply_text: str) -> None:
    safe_subject = html.escape(subject)
    safe_reply   = html.escape(reply_text)

    html_body = f"""
<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <p>Bonjour,</p>
    <p>Vous avez reçu une réponse à votre demande « <strong>{safe_subject}</strong> » :</p>
    <p style="background:#f5f5f5;padding:12px;border-radius:4px;white-space:pre-wrap;">{safe_reply}</p>
    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
    <p style="font-size: 12px; color: #999;">
        transport.trillet.be — Belgique
    </p>
</body>
</html>
    """

    message_obj = MessageSchema(
        subject=f"Réponse à votre demande : {subject} — transport.trillet.be",
        recipients=[user_email],
        body=html_body,
        subtype="html",
    )
    await fast_mail.send_message(message_obj)


async def _send_import_failure_alert(agency_name: str, error: str, traceback_str: str) -> None:
    body = f"""
<h3>Import GTFS échoué — {agency_name}</h3>
<p><strong>Erreur :</strong></p>
<pre style="background:#f5f5f5;padding:12px;border-radius:4px;">{error}</pre>
<p><strong>Traceback :</strong></p>
<pre style="background:#f5f5f5;padding:12px;border-radius:4px;font-size:12px;">{traceback_str}</pre>
<hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
<p style="font-size:12px;color:#999;">transport.trillet.be — alertes automatiques</p>
"""
    message = MessageSchema(
        subject=f"[transport.trillet.be] Import GTFS échoué — {agency_name}",
        recipients=ADMIN_ALERT_RECIPIENTS,
        body=body,
        subtype="html",
    )
    await fast_mail.send_message(message)


def notify_import_failure(agency_name: str, error: Exception) -> None:
    """Sync wrapper — safe to call from the blocking scheduler (no running event loop)."""
    tb_str = _tb.format_exc()
    try:
        asyncio.run(_send_import_failure_alert(agency_name, str(error), tb_str))
        print(f"  [ALERT] Notification envoyée à {ADMIN_ALERT_RECIPIENTS} pour {agency_name}")
    except Exception as mail_err:
        print(f"  [ALERT] Échec envoi mail d'alerte : {mail_err}")