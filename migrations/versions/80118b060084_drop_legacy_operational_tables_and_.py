"""drop legacy operational tables and project_participants

Revision ID: 80118b060084
Revises: 21c74aca53ae
Create Date: 2026-08-01 22:43:27.171195

"""
from alembic import op
import sqlalchemy as sa
import hashlib
import json
import re
import uuid
from datetime import date, datetime, time, timezone


# revision identifiers, used by Alembic.
revision = '80118b060084'
down_revision = '21c74aca53ae'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    legacy_tables = [
        "project_participants", "attendance_records", "contributions",
        "documents", "feedback", "reports", "volunteers",
    ]
    present = [name for name in legacy_tables if inspector.has_table(name)]
    if not present:
        return

    if not inspector.has_table("legacy_migration_reconciliation"):
        op.create_table(
            "legacy_migration_reconciliation",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_table", sa.String(80), nullable=False),
            sa.Column("source_id", sa.String(120), nullable=False),
            sa.Column("source_fingerprint", sa.String(64), nullable=False),
            sa.Column("target_table", sa.String(80), nullable=False),
            sa.Column("target_id", sa.Integer(), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("source_table", "source_fingerprint", name="uq_legacy_reconciliation_fingerprint"),
        )

    metadata = sa.MetaData()
    metadata.reflect(bind=bind)
    tables = metadata.tables
    reconciliation = tables["legacy_migration_reconciliation"]
    unresolved = []

    def json_default(value):
        if isinstance(value, (date, datetime, time)):
            return value.isoformat()
        return str(value)

    def fingerprint(table_name, row):
        payload = json.dumps(dict(row), sort_keys=True, separators=(",", ":"), default=json_default)
        return hashlib.sha256(f"{table_name}:{payload}".encode("utf-8")).hexdigest()

    def values_for(table_name, values):
        return {key: value for key, value in values.items() if key in tables[table_name].c}

    def insert(table_name, values):
        result = bind.execute(tables[table_name].insert().values(**values_for(table_name, values)))
        return result.inserted_primary_key[0]

    def first(table_name, *criteria):
        statement = sa.select(tables[table_name])
        for criterion in criteria:
            statement = statement.where(criterion)
        return bind.execute(statement.limit(1)).mappings().first()

    def person_for_user(user_id):
        user = first("users", tables["users"].c.id == user_id)
        if not user:
            raise ValueError(f"user {user_id} does not exist")
        if user.get("person_id"):
            person = first("people", tables["people"].c.id == user["person_id"])
            if person:
                return person["id"]
        person = None
        if user.get("email"):
            person = first("people", sa.func.lower(tables["people"].c.primary_email) == user["email"].lower())
        if not person:
            person_id = insert("people", {
                "public_id": str(uuid.uuid4()), "first_name": user.get("username") or "Legacy user",
                "primary_email": user.get("email"), "campus_id": user.get("campus_id"),
                "person_type": "Platform User", "consent_status": "Not Recorded",
                "privacy_classification": "Internal", "contact_visibility": {},
                "is_archived": False, "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            })
        else:
            person_id = person["id"]
        bind.execute(tables["users"].update().where(tables["users"].c.id == user_id).values(person_id=person_id))
        return person_id

    def record(source_table, row, target_table, target_id, extra=None):
        source_fingerprint = fingerprint(source_table, row)
        existing = first(
            "legacy_migration_reconciliation",
            reconciliation.c.source_table == source_table,
            reconciliation.c.source_fingerprint == source_fingerprint,
        )
        if existing:
            target = first(target_table, tables[target_table].c.id == existing["target_id"])
            if not target:
                raise ValueError("previously reconciled target is missing")
            return
        insert("legacy_migration_reconciliation", {
            "source_table": source_table, "source_id": str(row.get("id", "")),
            "source_fingerprint": source_fingerprint, "target_table": target_table,
            "target_id": target_id, "metadata_json": extra or {},
            "reconciled_at": datetime.now(timezone.utc),
        })

    def each(table_name):
        return bind.execute(sa.select(tables[table_name]).order_by(tables[table_name].c.id)).mappings().all()

    def migrate(table_name, handler):
        if table_name not in present:
            return
        for source_row in each(table_name):
            row = dict(source_row)
            try:
                existing = first(
                    "legacy_migration_reconciliation",
                    reconciliation.c.source_table == table_name,
                    reconciliation.c.source_fingerprint == fingerprint(table_name, row),
                )
                if existing and first(existing["target_table"], tables[existing["target_table"]].c.id == existing["target_id"]):
                    continue
                handler(row)
            except Exception as error:
                unresolved.append(f"{table_name} id={row.get('id')}: {error}")

    def migrate_participant(row):
        person_id = row.get("person_id") or person_for_user(row["user_id"])
        current = first(
            "team_assignments", tables["team_assignments"].c.project_id == row["project_id"],
            tables["team_assignments"].c.person_id == person_id,
        )
        target_id = current["id"] if current else insert("team_assignments", {
            "public_id": row.get("public_id") or str(uuid.uuid4()), "person_id": person_id,
            "user_id": row.get("user_id"), "project_id": row["project_id"],
            "cohort_id": row.get("cohort_id"), "assignment_type": row.get("participant_type") or "Participant",
            "nationality": row.get("nationality"), "status": row.get("status") or "Active",
            "recruitment_status": "Selected", "version": row.get("version") or 1,
            "starts_on": row.get("registration_date").date() if isinstance(row.get("registration_date"), datetime) else None,
            "created_at": row.get("registration_date") or datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
        })
        record("project_participants", row, "team_assignments", target_id)

    def migrate_attendance(row):
        person_id = person_for_user(row["user_id"])
        attendance_date = row["date"]
        code = f"LEGACY-{attendance_date.isoformat()}"
        session = first(
            "project_sessions", tables["project_sessions"].c.project_id == row["project_id"],
            tables["project_sessions"].c.code == code,
        )
        if session:
            session_id = session["id"]
        else:
            starts_at = datetime.combine(attendance_date, time.min)
            session_id = insert("project_sessions", {
                "public_id": str(uuid.uuid4()), "project_id": row["project_id"], "code": code,
                "title": f"Legacy attendance — {attendance_date.isoformat()}", "session_type": "Legacy attendance",
                "starts_at": starts_at, "ends_at": starts_at, "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            })
        current = first(
            "session_attendance", tables["session_attendance"].c.session_id == session_id,
            tables["session_attendance"].c.person_id == person_id,
        )
        target_id = current["id"] if current else insert("session_attendance", {
            "public_id": str(uuid.uuid4()), "session_id": session_id, "person_id": person_id,
            "status": row["status"], "verified_by_id": row.get("verified_by_id"),
            "verified_at": row.get("timestamp"), "version": 1,
            "created_at": row.get("timestamp") or datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
        })
        record("attendance_records", row, "session_attendance", target_id, {"synthetic_session_code": code})

    def migrate_contribution(row):
        person_id = person_for_user(row["user_id"])
        division = (row.get("division") or "").strip()
        wing = first("wings", sa.or_(sa.func.lower(tables["wings"].c.code) == division.lower(), sa.func.lower(tables["wings"].c.name) == division.lower())) if division else None
        description = row.get("description") or "Legacy contribution"
        target_id = insert("contribution_records", {
            "public_id": str(uuid.uuid4()), "project_id": row["project_id"], "person_id": person_id,
            "wing_id": wing["id"] if wing else None, "activity_type": row.get("activity_type") or "Legacy contribution",
            "description": description, "duration_hours": row.get("duration_hours") or 0,
            "evidence_reference": None if wing or not division else f"Legacy division: {division}",
            "approval_status": row.get("approval_status") or "Pending", "approved_by_id": row.get("approved_by_id"),
            "approved_at": row.get("approved_at"), "version": 1,
            "created_at": row.get("approved_at") or datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
        })
        record("contributions", row, "contribution_records", target_id, {"legacy_division": division, "division_mapped": bool(wing)})

    def drive_id(url):
        match = re.search(r"(?:/d/|[?&]id=)([-\w]{10,})", url or "")
        return match.group(1) if match else None

    def migrate_document(row):
        url = row.get("google_drive_link")
        target_id = insert("document_records", {
            "public_id": str(uuid.uuid4()), "project_id": row["project_id"],
            "category": row.get("document_type") or "Other", "title": row["title"], "version_label": "1",
            "status": "Submitted", "drive_file_id": drive_id(url), "drive_url": url,
            "permission_classification": "Internal", "drive_permission_metadata": [],
            "drive_validation_status": "Pending validation", "approved_by_id": row.get("uploaded_by_id"),
            "mandatory_for_closure": False, "waived": False, "version": 1,
            "created_at": row.get("created_at") or datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
        })
        record("documents", row, "document_records", target_id, {"drive_identifier_extracted": bool(drive_id(url))})

    def migrate_feedback(row):
        form = first("feedback_forms", tables["feedback_forms"].c.project_id == row["project_id"], tables["feedback_forms"].c.title == "Legacy feedback")
        form_id = form["id"] if form else insert("feedback_forms", {
            "public_id": str(uuid.uuid4()), "project_id": row["project_id"], "title": "Legacy feedback",
            "response_policy": "Legacy import", "is_anonymous": False,
            "questions_json": [{"key": "rating", "type": "scale", "min": 1, "max": 5, "label": "Overall rating"}, {"key": "q_1", "type": "text", "label": "Comments"}, {"key": "q_2", "type": "text", "label": "Suggestions"}],
            "is_open": False, "version": 1, "created_at": row.get("created_at") or datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
        rating = int(row["rating"])
        if rating not in range(1, 6):
            raise ValueError("rating is outside the canonical 1–5 range")
        target_id = insert("feedback_responses", {
            "public_id": str(uuid.uuid4()), "form_id": form_id, "person_id": person_for_user(row["user_id"]),
            "answers_json": {"rating": rating, "q_1": row.get("comments") or "", "q_2": row.get("suggestions") or ""},
            "publication_consent": False, "moderation_status": "Approved",
            "created_at": row.get("created_at") or datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
        })
        record("feedback", row, "feedback_responses", target_id, {"legacy_submission_type": row.get("submission_type")})

    def migrate_report(row):
        filters = {
            key: (row.get(key).isoformat() if isinstance(row.get(key), (date, datetime)) else row.get(key))
            for key in ("campus_id", "program_type_id", "start_date", "end_date")
            if row.get(key) is not None
        }
        target_id = insert("report_snapshots", {
            "public_id": str(uuid.uuid4()), "project_id": row.get("project_id"), "report_type": row["report_type"],
            "title": row["title"], "version": 1, "filters_json": filters,
            "snapshot_json": {"legacy_description": row.get("description")}, "source_references": ["legacy:reports"],
            "approval_status": "Draft", "generated_by_id": row.get("generated_by_id"),
            "publication_status": "Unpublished", "created_at": row.get("created_at") or datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
        record("reports", row, "report_snapshots", target_id, {"rollup_filters": filters})

    def migrate_volunteer(row):
        person_id = person_for_user(row["user_id"])
        bind.execute(tables["people"].update().where(tables["people"].c.id == person_id).values(skills=row.get("skills"), interests=row.get("interests"), updated_at=datetime.now(timezone.utc)))
        record("volunteers", row, "people", person_id, {"legacy_status": row.get("current_status")})

    migrate("project_participants", migrate_participant)
    migrate("attendance_records", migrate_attendance)
    migrate("contributions", migrate_contribution)
    migrate("documents", migrate_document)
    migrate("feedback", migrate_feedback)
    migrate("reports", migrate_report)
    migrate("volunteers", migrate_volunteer)

    for table_name in present:
        source_count = bind.execute(sa.select(sa.func.count()).select_from(tables[table_name])).scalar_one()
        target_count = bind.execute(
            sa.select(sa.func.count()).select_from(reconciliation).where(reconciliation.c.source_table == table_name)
        ).scalar_one()
        if source_count != target_count:
            unresolved.append(f"{table_name}: source={source_count}, reconciled={target_count}")
    if unresolved:
        raise RuntimeError("Legacy migration aborted; unresolved rows:\n" + "\n".join(unresolved))

    for table_name in reversed(present):
        op.drop_table(table_name)


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('reports',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('report_type', sa.VARCHAR(length=50), nullable=False),
    sa.Column('title', sa.VARCHAR(length=150), nullable=False),
    sa.Column('description', sa.TEXT(), nullable=True),
    sa.Column('campus_id', sa.INTEGER(), nullable=True),
    sa.Column('program_type_id', sa.INTEGER(), nullable=True),
    sa.Column('project_id', sa.INTEGER(), nullable=True),
    sa.Column('start_date', sa.DATE(), nullable=True),
    sa.Column('end_date', sa.DATE(), nullable=True),
    sa.Column('generated_by_id', sa.INTEGER(), nullable=True),
    sa.Column('created_at', sa.DATETIME(), nullable=True),
    sa.ForeignKeyConstraint(['campus_id'], ['campuses.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['generated_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['program_type_id'], ['program_types.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('contributions',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('project_id', sa.INTEGER(), nullable=False),
    sa.Column('user_id', sa.INTEGER(), nullable=False),
    sa.Column('activity_type', sa.VARCHAR(length=50), nullable=False),
    sa.Column('description', sa.TEXT(), nullable=True),
    sa.Column('division', sa.VARCHAR(length=50), nullable=True),
    sa.Column('duration_hours', sa.FLOAT(), nullable=False),
    sa.Column('approval_status', sa.VARCHAR(length=20), nullable=False),
    sa.Column('approved_by_id', sa.INTEGER(), nullable=True),
    sa.Column('approved_at', sa.DATETIME(), nullable=True),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('attendance_records',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('project_id', sa.INTEGER(), nullable=False),
    sa.Column('user_id', sa.INTEGER(), nullable=False),
    sa.Column('date', sa.DATE(), nullable=False),
    sa.Column('status', sa.VARCHAR(length=20), nullable=False),
    sa.Column('verified_by_id', sa.INTEGER(), nullable=True),
    sa.Column('timestamp', sa.DATETIME(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['verified_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('documents',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('project_id', sa.INTEGER(), nullable=False),
    sa.Column('title', sa.VARCHAR(length=150), nullable=False),
    sa.Column('document_type', sa.VARCHAR(length=50), nullable=False),
    sa.Column('google_drive_link', sa.VARCHAR(length=500), nullable=False),
    sa.Column('uploaded_by_id', sa.INTEGER(), nullable=True),
    sa.Column('created_at', sa.DATETIME(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('project_participants',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('project_id', sa.INTEGER(), nullable=False),
    sa.Column('user_id', sa.INTEGER(), nullable=True),
    sa.Column('participant_type', sa.VARCHAR(length=50), nullable=False),
    sa.Column('nationality', sa.VARCHAR(length=100), nullable=True),
    sa.Column('status', sa.VARCHAR(length=20), nullable=False),
    sa.Column('registration_date', sa.DATETIME(), nullable=True),
    sa.Column('public_id', sa.VARCHAR(length=36), nullable=False),
    sa.Column('person_id', sa.INTEGER(), nullable=True),
    sa.Column('cohort_id', sa.INTEGER(), nullable=True),
    sa.Column('version', sa.INTEGER(), server_default=sa.text("'1'"), nullable=False),
    sa.CheckConstraint('user_id IS NOT NULL OR person_id IS NOT NULL', name=op.f('ck_participant_identity')),
    sa.ForeignKeyConstraint(['cohort_id'], ['cohorts.id'], name=op.f('fk_participant_cohort'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['person_id'], ['people.id'], name=op.f('fk_participant_person'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'person_id', name=op.f('uq_project_person_participant')),
    sa.UniqueConstraint('public_id', name=op.f('uq_project_participants_public_id'))
    )
    op.create_table('feedback',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('project_id', sa.INTEGER(), nullable=False),
    sa.Column('user_id', sa.INTEGER(), nullable=False),
    sa.Column('rating', sa.INTEGER(), nullable=False),
    sa.Column('comments', sa.TEXT(), nullable=True),
    sa.Column('suggestions', sa.TEXT(), nullable=True),
    sa.Column('submission_type', sa.VARCHAR(length=50), nullable=False),
    sa.Column('created_at', sa.DATETIME(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('volunteers',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('user_id', sa.INTEGER(), nullable=False),
    sa.Column('skills', sa.TEXT(), nullable=True),
    sa.Column('interests', sa.TEXT(), nullable=True),
    sa.Column('current_status', sa.VARCHAR(length=50), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.drop_table('legacy_migration_reconciliation')
    # ### end Alembic commands ###
