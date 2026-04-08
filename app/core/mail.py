from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from app.core.config import settings

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