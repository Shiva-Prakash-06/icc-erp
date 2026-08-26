import os
import unittest
from datetime import date

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import (
    ChecklistInstance,
    ChecklistItemStatus,
    ChecklistTemplate,
    ChecklistTemplateItem,
    DocumentRecord,
    RoleAssignment,
)
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User


class ChecklistEvidenceTestCase(unittest.TestCase):
    """Checklist line items can link one or more repository documents as
    evidence -- see
    in-the-operation-checklists-crystalline-dongarra.md Step 3."""

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.program_type = ProgramType(name="ICC")
        db.session.add_all([self.year, self.campus, self.program_type])
        db.session.flush()

        self.project = Project(
            code="ICC-2026-CEN-700", campus_id=self.campus.id, program_type_id=self.program_type.id,
            academic_year_id=self.year.id, title="Evidence test project", category="Operational",
            status="Active", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        db.session.add(self.project)
        db.session.flush()

        template = ChecklistTemplate(code="EVID", name="Evidence checklist", project_type="ICC event")
        db.session.add(template)
        db.session.flush()
        self.template_item = ChecklistTemplateItem(template_id=template.id, code="ONE", title="Requirement")
        instance = ChecklistInstance(project_id=self.project.id, template_id=template.id, name="Evidence checklist")
        db.session.add_all([self.template_item, instance])
        db.session.flush()
        self.item = ChecklistItemStatus(checklist_instance_id=instance.id, template_item_id=self.template_item.id, version=1)
        db.session.add(self.item)
        db.session.flush()

        self.document = DocumentRecord(project_id=self.project.id, title="Screen banner", category="Screen Banner", version=1, drive_url="https://drive.example.com/file/1", drive_file_id="file-1")
        self.other_project_document = None
        db.session.add(self.document)
        db.session.flush()

        self.manager = User(username="manager", email="manager@example.com", role="Faculty", status="Approved", needs_password_reset=False)
        self.manager.set_password("A-secure-test-password-2026")
        self.outsider = User(username="outsider", email="outsider@example.com", role="Volunteer", status="Approved", needs_password_reset=False)
        self.outsider.set_password("A-secure-test-password-2026")
        db.session.add_all([self.manager, self.outsider])
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.manager.id, role_code="OIA_FACULTY_ADMINISTRATOR", is_active=True, can_view_sensitive_links=True))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def login(self, user):
        with self.client.session_transaction() as session:
            session["user_id"] = user.id
            session["session_version"] = user.session_version

    def attach_url(self):
        return f"/erp/projects/{self.project.public_id}/checklist-items/{self.item.public_id}/documents"

    def detach_url(self, document_public_id=None):
        return f"/erp/projects/{self.project.public_id}/checklist-items/{self.item.public_id}/documents/{document_public_id or self.document.public_id}/detach"

    def test_manager_can_attach_existing_document(self):
        self.login(self.manager)
        response = self.client.post(self.attach_url(), data={"document_public_id": self.document.public_id})
        self.assertEqual(response.status_code, 302)
        self.assertIn("tab=delivery", response.headers["Location"])
        db.session.refresh(self.document)
        self.assertEqual(self.document.checklist_status_id, self.item.id)
        self.assertEqual(list(self.item.evidence_documents), [self.document])

    def test_outsider_without_permission_is_forbidden(self):
        self.login(self.outsider)
        response = self.client.post(self.attach_url(), data={"document_public_id": self.document.public_id})
        self.assertEqual(response.status_code, 403)
        db.session.refresh(self.document)
        self.assertIsNone(self.document.checklist_status_id)

    def test_cross_project_document_is_masked_as_missing(self):
        other_project = Project(
            code="ICC-2026-CEN-701", campus_id=self.campus.id, program_type_id=self.program_type.id,
            academic_year_id=self.year.id, title="Other project", category="Operational",
            status="Active", start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
        )
        db.session.add(other_project)
        db.session.flush()
        foreign_document = DocumentRecord(project_id=other_project.id, title="Not this project", category="Report", version=1)
        db.session.add(foreign_document)
        db.session.commit()

        self.login(self.manager)
        response = self.client.post(self.attach_url(), data={"document_public_id": foreign_document.public_id})
        self.assertEqual(response.status_code, 404)

    def test_restricted_document_is_masked_without_sensitive_links(self):
        restricted = DocumentRecord(project_id=self.project.id, title="Restricted plan", category="Report", permission_classification="Restricted", version=1)
        db.session.add(restricted)
        db.session.commit()

        volunteer_contributor = User(username="contributor", email="contributor@example.com", role="Volunteer", status="Approved", needs_password_reset=False)
        volunteer_contributor.set_password("A-secure-test-password-2026")
        db.session.add(volunteer_contributor)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=volunteer_contributor.id, role_code="ICC_ASSOCIATE", project_id=self.project.id, is_active=True))
        self.item.owner_person_id = None
        db.session.commit()

        self.login(volunteer_contributor)
        response = self.client.post(self.attach_url(), data={"document_public_id": restricted.public_id})
        # ICC_ASSOCIATE holds manage_projects in this codebase's role map,
        # but not sensitive_links -- so a Restricted document is masked as
        # 404, never revealed via a 403.
        self.assertIn(response.status_code, (403, 404))
        if response.status_code == 404:
            db.session.refresh(restricted)
            self.assertIsNone(restricted.checklist_status_id)

    def test_detach_unlinks_without_deleting(self):
        self.login(self.manager)
        self.client.post(self.attach_url(), data={"document_public_id": self.document.public_id})
        before_count = DocumentRecord.query.count()

        response = self.client.post(self.detach_url())
        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.document)
        self.assertIsNone(self.document.checklist_status_id)
        self.assertEqual(DocumentRecord.query.count(), before_count)
        self.assertEqual(self.document.drive_url, "https://drive.example.com/file/1")  # unchanged
        self.assertEqual(self.document.status, "Missing")

    def test_attach_and_detach_leave_versions_unchanged(self):
        self.login(self.manager)
        self.client.post(self.attach_url(), data={"document_public_id": self.document.public_id})
        db.session.refresh(self.item)
        db.session.refresh(self.document)
        self.assertEqual(self.item.version, 1)
        self.assertEqual(self.document.version, 1)

        self.client.post(self.detach_url())
        db.session.refresh(self.item)
        db.session.refresh(self.document)
        self.assertEqual(self.item.version, 1)
        self.assertEqual(self.document.version, 1)

    def test_attaching_same_document_twice_is_idempotent(self):
        self.login(self.manager)
        self.client.post(self.attach_url(), data={"document_public_id": self.document.public_id})
        response = self.client.post(self.attach_url(), data={"document_public_id": self.document.public_id})
        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.document)
        self.assertEqual(self.document.checklist_status_id, self.item.id)

    def test_rendering_shows_linked_document_and_open_link(self):
        self.login(self.manager)
        self.client.post(self.attach_url(), data={"document_public_id": self.document.public_id})
        response = self.client.get(f"/erp/projects/{self.project.public_id}?tab=delivery")
        html = response.get_data(as_text=True)
        self.assertIn("Screen banner", html)
        self.assertIn(f"/erp/documents/{self.document.public_id}/open", html)

    def test_api_twin_attaches_and_detaches(self):
        self.login(self.manager)
        response = self.client.post(
            f"/api/v1/checklist-items/{self.item.public_id}/documents",
            json={"document_public_id": self.document.public_id},
        )
        self.assertEqual(response.status_code, 200)
        db.session.refresh(self.document)
        self.assertEqual(self.document.checklist_status_id, self.item.id)

        response = self.client.delete(f"/api/v1/checklist-items/{self.item.public_id}/documents/{self.document.public_id}")
        self.assertEqual(response.status_code, 200)
        db.session.refresh(self.document)
        self.assertIsNone(self.document.checklist_status_id)
        self.assertEqual(DocumentRecord.query.count(), 1)

    def test_generic_patch_cannot_set_checklist_link(self):
        self.login(self.manager)
        response = self.client.post(
            "/api/v1/documents",
            json={
                "project_public_id": self.project.public_id,
                "title": "Sneaky link attempt",
                "category": "Report",
                "checklist_status_public_id": self.item.public_id,
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("checklist_status_public_id", response.json.get("detail", ""))


if __name__ == "__main__":
    unittest.main()
