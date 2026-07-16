"""Idempotent in-app and email notification delivery."""

from __future__ import annotations

import re
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from flask import current_app
from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2

from app.database import db
from app.models.erp import ChecklistItemStatus, DocumentRecord, WorkTask
from app.models.production import Notification, NotificationDeliveryAttempt, NotificationPreference


SENSITIVE_TEXT = re.compile(r"https://(?:drive|docs)\.google\.com/\S+|\b(?:passport|visa|c-form)\b", re.IGNORECASE)


def _safe_text(value):
    return SENSITIVE_TEXT.sub("[restricted operational reference]", (value or "").strip())


def _preference(user_id, event_type):
    return NotificationPreference.query.filter_by(user_id=user_id, event_type=event_type).first()


def queue_notification(*, user, event_type, title, body, idempotency_key, project=None, action_url=None, severity="Info", critical=False):
    existing = Notification.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        return existing, False
    preference = _preference(user.id, event_type)
    in_app_enabled = critical or preference is None or preference.in_app_enabled
    if not in_app_enabled:
        return None, False
    notification = Notification(
        user_id=user.id,
        project_id=getattr(project, "id", None),
        event_type=event_type,
        severity=severity,
        title=_safe_text(title)[:180],
        body=_safe_text(body),
        action_url=action_url,
        idempotency_key=idempotency_key,
        is_critical=critical,
    )
    db.session.add(notification)
    db.session.flush()
    _enqueue_delivery_task(notification)
    return notification, True


def _enqueue_delivery_task(notification):
    if current_app.config.get("APP_ENV") != "production":
        return None
    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(
        current_app.config["GCP_PROJECT_ID"],
        current_app.config["GCP_REGION"],
        current_app.config["CLOUD_TASKS_QUEUE"],
    )
    schedule_time = timestamp_pb2.Timestamp()
    schedule_time.FromDatetime(datetime.now(timezone.utc) + timedelta(seconds=10))
    task = {
        "name": f"{parent}/tasks/notification-{notification.public_id}",
        "schedule_time": schedule_time,
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{current_app.config['INTERNAL_JOB_BASE_URL'].rstrip('/')}/internal/jobs/notifications/deliver",
            "oidc_token": {
                "service_account_email": current_app.config["TASKS_SERVICE_ACCOUNT"],
                "audience": current_app.config["INTERNAL_JOB_AUDIENCE"],
            },
        },
    }
    try:
        return client.create_task(parent=parent, task=task)
    except Exception:
        # The database row remains pending and Scheduler provides recovery.
        return None


def _record_attempt(notification, channel, status, error=None, reference=None):
    attempt_number = NotificationDeliveryAttempt.query.filter_by(
        notification_id=notification.id, channel=channel
    ).count() + 1
    attempt = NotificationDeliveryAttempt(
        notification_id=notification.id,
        channel=channel,
        attempt_number=attempt_number,
        status=status,
        provider_reference=reference,
        error_summary=(error or "")[:500] or None,
    )
    db.session.add(attempt)
    return attempt


def deliver_email(notification):
    user = db.session.get(__import__("app.models.user", fromlist=["User"]).User, notification.user_id)
    preference = _preference(notification.user_id, notification.event_type)
    if not notification.is_critical and preference and not preference.email_enabled:
        _record_attempt(notification, "email", "Suppressed")
        notification.delivery_status = "InAppOnly"
        return "Suppressed"
    if current_app.config.get("NOTIFICATION_EMAIL_MODE") != "smtp":
        _record_attempt(notification, "email", "Disabled")
        notification.delivery_status = "InAppOnly"
        return "Disabled"
    message = EmailMessage()
    message["Subject"] = notification.title
    message["From"] = current_app.config["SMTP_FROM_ADDRESS"]
    message["To"] = user.email
    message.set_content(notification.body)
    try:
        with smtplib.SMTP(current_app.config["SMTP_HOST"], current_app.config["SMTP_PORT"], timeout=15) as server:
            if current_app.config.get("SMTP_USE_TLS"):
                server.starttls()
            if current_app.config.get("SMTP_USERNAME"):
                server.login(current_app.config["SMTP_USERNAME"], current_app.config["SMTP_PASSWORD"])
            response = server.send_message(message)
        _record_attempt(notification, "email", "Delivered", reference=str(response)[:255])
        notification.delivery_status = "Delivered"
        return "Delivered"
    except (OSError, smtplib.SMTPException) as error:
        _record_attempt(notification, "email", "Failed", error=str(error))
        attempts = NotificationDeliveryAttempt.query.filter_by(notification_id=notification.id, channel="email").count()
        notification.delivery_status = "DeadLetter" if attempts >= 5 else "Retry"
        return notification.delivery_status


def deliver_pending(limit=100):
    items = Notification.query.filter(Notification.delivery_status.in_(["Pending", "Retry"])).order_by(Notification.id).limit(limit).all()
    outcomes = {"processed": 0, "delivered": 0, "retry": 0, "dead_letter": 0}
    for notification in items:
        result = deliver_email(notification)
        outcomes["processed"] += 1
        if result == "Delivered":
            outcomes["delivered"] += 1
        elif result == "Retry":
            outcomes["retry"] += 1
        elif result == "DeadLetter":
            outcomes["dead_letter"] += 1
    db.session.commit()
    return outcomes


def generate_deadline_notifications(now=None):
    now = now or datetime.now(timezone.utc)
    horizon = now + timedelta(hours=48)
    created = 0
    tasks = WorkTask.query.filter(WorkTask.due_at.isnot(None), WorkTask.due_at <= horizon, ~WorkTask.status.in_(["Approved", "Completed"])).all()
    for task in tasks:
        person = db.session.get(__import__("app.models.erp", fromlist=["Person"]).Person, task.owner_person_id) if task.owner_person_id else None
        if not person or not person.user_account:
            continue
        notification, inserted = queue_notification(
            user=person.user_account,
            project=task.project,
            event_type="task.deadline",
            title="Task deadline approaching",
            body=f"{task.title} is due soon.",
            action_url=f"/erp/projects/{task.project.public_id}",
            severity="Warning",
            idempotency_key=f"task-deadline:{task.public_id}:{task.due_at.isoformat()}",
        )
        created += int(inserted)
    for item in ChecklistItemStatus.query.filter(ChecklistItemStatus.due_at.isnot(None), ChecklistItemStatus.due_at <= horizon, ~ChecklistItemStatus.status.in_(["Approved", "Completed"])).all():
        person = db.session.get(__import__("app.models.erp", fromlist=["Person"]).Person, item.owner_person_id) if item.owner_person_id else None
        if not person or not person.user_account:
            continue
        project = item.checklist.project
        _, inserted = queue_notification(
            user=person.user_account,
            project=project,
            event_type="checklist.deadline",
            title="Checklist requirement due soon",
            body=f"{item.template_item.title} requires attention.",
            action_url=f"/erp/projects/{project.public_id}",
            severity="Warning",
            idempotency_key=f"checklist-deadline:{item.public_id}:{item.due_at.isoformat()}",
        )
        created += int(inserted)
    expired = DocumentRecord.query.filter(DocumentRecord.expires_on.isnot(None), DocumentRecord.expires_on <= now.date()).all()
    for document in expired:
        if document.status == "Expired":
            continue
        document.status = "Expired"
        document.version += 1
    db.session.commit()
    return {"created": created, "expired_documents": len(expired)}
