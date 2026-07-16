from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models.user import User
from app.database import db


@dataclass(frozen=True)
class IdentityResult:
    subject: str
    email: str
    display_name: str | None = None


class IdentityProvider(ABC):
    @abstractmethod
    def authenticate(self, identifier: str, secret: str) -> IdentityResult | None:
        raise NotImplementedError


class InternalPasswordIdentityProvider(IdentityProvider):
    def authenticate(self, identifier, secret):
        if not identifier or not secret:
            return None
        normalized = identifier.strip().lower()
        user = User.query.filter((db.func.lower(User.username) == normalized) | (db.func.lower(User.email) == normalized)).first()
        if not user or not user.check_password(secret):
            return None
        return IdentityResult(subject=str(user.id), email=user.email, display_name=user.username)


class ExternalDirectoryIdentityProvider(IdentityProvider):
    """Extension point for CHRIST directory or Google Workspace SSO."""

    def authenticate(self, identifier, secret):  # pragma: no cover - future adapter
        raise NotImplementedError("Institutional identity provider is not configured.")
