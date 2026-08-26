"""Password policy and k-anonymous breached-password verification."""

from __future__ import annotations

import hashlib
import secrets
import smtplib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import requests
from flask import current_app

from app.database import db


_RESET_DELIVERY_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="password-reset-delivery")


COMMON_PASSWORDS = {
    "password", "password123", "12345678", "christ123", "qwerty123",
    "letmein", "welcome123", "admin123", "iloveyou", "changeme",
}


def validate_password(password):
    if len(password or "") < 12:
        raise ValueError("Password must contain at least 12 characters.")
    if password.lower() in COMMON_PASSWORDS:
        raise ValueError("This password is too common.")
    if current_app.config.get("BREACHED_PASSWORD_CHECK_MODE", "disabled") != "live":
        return True
    digest = hashlib.sha1(password.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    response = requests.get(
        f"https://api.pwnedpasswords.com/range/{digest[:5]}",
        headers={"Add-Padding": "true", "User-Agent": "ICC-OIA-ERP"},
        timeout=5,
    )
    response.raise_for_status()
    suffix = digest[5:]
    if any(line.split(":", 1)[0] == suffix for line in response.text.splitlines()):
        raise ValueError("This password appears in a known breach and cannot be used.")
    return True


def issue_reset_token(user):
    token = secrets.token_urlsafe(32)
    user.password_reset_token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    db.session.commit()
    return token


def find_user_for_reset(token):
    from app.models.user import User

    digest = hashlib.sha256((token or "").encode("utf-8")).hexdigest()
    user = User.query.filter_by(password_reset_token_hash=digest).first()
    if not user or not user.password_reset_expires_at:
        return None
    expires = user.password_reset_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return user if expires > datetime.now(timezone.utc) else None


def send_reset_email(user, reset_url):
    if current_app.config.get("NOTIFICATION_EMAIL_MODE") != "smtp":
        return False
    message = EmailMessage()
    message["Subject"] = "ICC/OIA ERP password reset"
    message["From"] = current_app.config["SMTP_FROM_ADDRESS"]
    message["To"] = user.email
    message.set_content(f"Use this one-time link within 30 minutes to reset your password:\n\n{reset_url}\n")
    with smtplib.SMTP(current_app.config["SMTP_HOST"], current_app.config["SMTP_PORT"], timeout=15) as server:
        if current_app.config.get("SMTP_USE_TLS"):
            server.starttls()
        if current_app.config.get("SMTP_USERNAME"):
            server.login(current_app.config["SMTP_USERNAME"], current_app.config["SMTP_PASSWORD"])
        server.send_message(message)
    return True


def enqueue_reset_email(user, reset_url):
    """Queue SMTP work outside the request path using an immutable config snapshot."""
    config = {
        key: current_app.config.get(key)
        for key in (
            "NOTIFICATION_EMAIL_MODE", "SMTP_HOST", "SMTP_PORT", "SMTP_FROM_ADDRESS",
            "SMTP_USE_TLS", "SMTP_USERNAME", "SMTP_PASSWORD",
        )
    }
    recipient = getattr(user, "email", None)

    def deliver():
        if config["NOTIFICATION_EMAIL_MODE"] != "smtp" or not recipient:
            return False
        message = EmailMessage()
        message["Subject"] = "ICC/OIA ERP password reset"
        message["From"] = config["SMTP_FROM_ADDRESS"]
        message["To"] = recipient
        message.set_content(f"Use this one-time link within 30 minutes to reset your password:\n\n{reset_url}\n")
        try:
            with smtplib.SMTP(config["SMTP_HOST"], config["SMTP_PORT"], timeout=15) as server:
                if config["SMTP_USE_TLS"]:
                    server.starttls()
                if config["SMTP_USERNAME"]:
                    server.login(config["SMTP_USERNAME"], config["SMTP_PASSWORD"])
                server.send_message(message)
            return True
        except (OSError, smtplib.SMTPException):
            return False

    return _RESET_DELIVERY_EXECUTOR.submit(deliver)
