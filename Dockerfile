# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt && pip uninstall -y setuptools

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8080

RUN addgroup --system app && adduser --system --ingroup app app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv

# Allowlisted runtime copies only -- never `COPY . .`. This is the primary
# defense against shipping credentials, backups, node_modules, or test
# fixtures in the image; .dockerignore is a secondary backstop, not the
# only guard. See PLAN.md "Additional release blockers" finding.
COPY --chown=app:app app app
COPY --chown=app:app migrations migrations
COPY --chown=app:app run.py .

USER app

EXPOSE 8080
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 60 --access-logfile - --error-logfile - run:app"]
