import os
import stat

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import Person, RoleAssignment
from app.models.user import User


def test_bootstrap_admin_creates_person_and_platform_assignment_atomically():
    app = create_app()
    with app.app_context():
        db.create_all()
        result = app.test_cli_runner().invoke(args=[
            "bootstrap-admin", "--username", "first_admin", "--email", "first@example.test",
            "--password", "Secure-bootstrap-2026!",
        ])
        assert result.exit_code == 0, result.output
        user = User.query.filter_by(username="first_admin").one()
        assert user.person_id is not None
        assert db.session.get(Person, user.person_id).primary_email == "first@example.test"
        assignment = RoleAssignment.query.filter_by(user_id=user.id, is_active=True).one()
        assert assignment.role_code == "OIA_FACULTY_ADMINISTRATOR"
        assert not any((assignment.campus_id, assignment.operating_unit_id, assignment.wing_id, assignment.academic_year_id, assignment.project_id))
        db.session.remove()
        db.drop_all()


def test_uat_provisioning_writes_only_private_one_time_credentials(tmp_path):
    app = create_app()
    output = tmp_path / "UAT_CREDENTIALS.txt"
    with app.app_context():
        db.create_all()
        result = app.test_cli_runner().invoke(args=["provision-uat", "--output", str(output)])
        assert result.exit_code == 0, result.output
        assert stat.S_IMODE(output.stat().st_mode) == 0o600
        contents = output.read_text()
        for username in ("uat_faculty_admin", "uat_usc", "uat_igp_head", "uat_icc_events_head", "uat_volunteer"):
            assert username in contents
            user = User.query.filter_by(username=username).one()
            assert user.needs_password_reset is False
            assert RoleAssignment.query.filter_by(user_id=user.id, is_active=True).count() == 1
        assert "123" in contents
        db.session.remove()
        db.drop_all()
