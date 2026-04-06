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
    message = MessageSchema(
        subject="Confirmez votre inscription",
        recipients=[email],
        body=f"""
        <h3>Bienvenue !</h3>
        <p>Merci de vous être inscrit. Cliquez sur ce lien pour confirmer votre email :</p>
        <a href="{confirmation_url}">{confirmation_url}</a>
        <p>Ce lien expire dans 24 heures.</p>
        """,
        subtype="html"
    )
    await fast_mail.send_message(message)