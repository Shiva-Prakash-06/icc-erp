"""Verification for Cloud Scheduler and Cloud Tasks OIDC requests."""

from __future__ import annotations

from flask import current_app, request
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token


def verify_internal_job_request(allowed_accounts):
    if current_app.config.get("TESTING"):
        return {"email": "test-job@example.invalid"}
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise PermissionError("Missing OIDC bearer token.")
    audience = current_app.config.get("INTERNAL_JOB_AUDIENCE")
    if not audience:
        raise PermissionError("Internal job audience is not configured.")
    try:
        claims = id_token.verify_oauth2_token(
            authorization.removeprefix("Bearer "),
            google_requests.Request(),
            audience,
        )
    except (GoogleAuthError, ValueError):
        # Invalid signatures, claims, issuers, and audiences are ordinary
        # authorization denials. Never expose verifier internals as a 500.
        raise PermissionError("OIDC bearer token is invalid.") from None
    email = claims.get("email")
    if not claims.get("email_verified") or email not in set(filter(None, allowed_accounts)):
        raise PermissionError("OIDC service identity is not authorized for this job.")
    return claims
