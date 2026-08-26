import os
import unittest


os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.user import User
from app.services.identity import IdentityProvider, IdentityResult, InternalPasswordIdentityProvider


class _ParentCallingProvider(IdentityProvider):
    def authenticate(self, identifier, secret):
        return super().authenticate(identifier, secret)


class IdentityServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.user = User(
            username="release_user",
            email="release.user@example.org",
            role="Volunteer",
            status="Approved",
            needs_password_reset=False,
        )
        self.user.set_password("A-secure-release-password-2026")
        db.session.add(self.user)
        db.session.commit()
        self.provider = InternalPasswordIdentityProvider()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_internal_provider_rejects_incomplete_or_invalid_credentials(self):
        self.assertIsNone(self.provider.authenticate("", "secret"))
        self.assertIsNone(self.provider.authenticate("release_user", ""))
        self.assertIsNone(self.provider.authenticate("missing", "A-secure-release-password-2026"))
        self.assertIsNone(self.provider.authenticate("release_user", "incorrect-password"))

    def test_internal_provider_accepts_normalized_username_and_email(self):
        by_username = self.provider.authenticate("  RELEASE_USER ", "A-secure-release-password-2026")
        by_email = self.provider.authenticate("RELEASE.USER@EXAMPLE.ORG", "A-secure-release-password-2026")

        self.assertEqual(
            by_username,
            IdentityResult(subject=str(self.user.id), email=self.user.email, display_name=self.user.username),
        )
        self.assertEqual(by_email, by_username)

    def test_identity_provider_contract_is_abstract(self):
        with self.assertRaises(NotImplementedError):
            _ParentCallingProvider().authenticate("release_user", "secret")


if __name__ == "__main__":
    unittest.main()
