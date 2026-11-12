"""Envoi du lien de réinitialisation. Les accès SMTP viennent de l'environnement."""
import os
import smtplib
from email.message import EmailMessage


class MailNotConfiguredError(RuntimeError):
    """SMTP_HOST, SMTP_USER ou SMTP_PASSWORD est absent."""


class MailDeliveryError(RuntimeError):
    """Le serveur de messagerie a refusé ou n'a pas répondu."""


def send_password_reset(to: str, token: str) -> None:
    """Envoie le lien valable 30 minutes. N'inscrit pas le jeton dans les logs."""
    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    sender = os.getenv("SMTP_FROM", "").strip() or user
    if not host or not user or not password or not sender:
        raise MailNotConfiguredError("SMTP non configuré")

    port = int(os.getenv("SMTP_PORT", "587"))
    public = os.getenv("APP_PUBLIC_URL", "http://localhost:3000").rstrip("/")
    link = f"{public}/mot-de-passe-oublie?token={token}"

    message = EmailMessage()
    message["Subject"] = "Réinitialisation de votre mot de passe"
    message["From"] = sender
    message["To"] = to
    message.set_content(
        "Vous avez demandé un nouveau mot de passe pour la salle de marché.\n\n"
        "Ouvrez ce lien. Il est valable 30 minutes et ne sert qu'une fois :\n"
        f"{link}\n\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.\n"
    )
    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(user, password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailDeliveryError(type(exc).__name__) from None
