import os
import sys
import datetime
import unittest
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import ConnectedAccount, Email, Draft
from app.routers.google_oauth import delete_connected_account, google_oauth_start
from app.config import settings


class TestRemoveAccount(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def test_remove_logged_out_account_with_undecryptable_tokens(self):
        # A logged-out account whose tokens were encrypted with an old key must still be removable
        account = ConnectedAccount(
            google_email="stale@gmail.com",
            access_token="not-a-valid-fernet-token",
            refresh_token="also-invalid",
            sync_status="needs_reauth"
        )
        self.db.add(account)
        self.db.commit()
        now = datetime.datetime.now(datetime.timezone.utc)
        email = Email(
            account_id=account.id, gmail_message_id="m1", gmail_thread_id="t1",
            sender="a@x.com", recipient="stale@gmail.com", subject="s", html_body="<p>b</p>",
            received_at=now, fetched_at=now, folder_status="inbox"
        )
        self.db.add(email)
        self.db.commit()
        self.db.add(Draft(account_id=account.id, email_id=email.id, html_body="<p>d</p>"))
        self.db.commit()

        delete_connected_account(account.id, db=self.db, current_user={"username": "admin"})

        self.assertEqual(self.db.query(ConnectedAccount).count(), 0)
        self.assertEqual(self.db.query(Email).count(), 0)
        self.assertEqual(self.db.query(Draft).count(), 0)

    def test_fix_preselects_account_in_google_chooser(self):
        settings.GOOGLE_CLIENT_ID = "test-client-id"
        url = google_oauth_start(json_mode=True, state="add_account", login_hint="stale@gmail.com")["url"]
        self.assertEqual(parse_qs(urlparse(url).query)["login_hint"], ["stale@gmail.com"])


if __name__ == "__main__":
    unittest.main()
