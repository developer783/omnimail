import os
import sys
import datetime
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import ConnectedAccount, Email, Draft
from app.schemas import DraftCreate
from app.routers.drafts import save_or_update_draft, get_drafts, delete_draft, send_draft
from app.routers.emails import get_emails
from app.security import encrypt_token

class TestDraftsApi(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = self.SessionLocal()

        self.account = ConnectedAccount(
            google_email="chaudharyaayush9832@gmail.com",
            access_token=encrypt_token("demo_token"),
            refresh_token=encrypt_token("demo_refresh"),
            sync_status="success"
        )
        self.db.add(self.account)
        self.db.commit()
        self.db.refresh(self.account)

        self.current_user = {"username": "admin"}

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def test_draft_lifecycle(self):
        # 1. Create a draft
        draft_req = DraftCreate(
            account_id=self.account.id,
            to_recipients="recruiter@tech.com",
            subject="Re: Interview Schedule",
            html_body="<p>I am available on Monday at 10 AM.</p>",
            composer_mode="reply"
        )

        saved_draft = save_or_update_draft(
            draft_req=draft_req,
            db=self.db,
            current_user=self.current_user
        )

        self.assertIsNotNone(saved_draft.id)
        self.assertEqual(saved_draft.subject, "Re: Interview Schedule")

        # 2. Check GET /drafts and FolderCounts.drafts
        drafts_list = get_drafts(
            account_id=self.account.id,
            db=self.db,
            current_user=self.current_user
        )
        self.assertEqual(drafts_list.total, 1)

        emails_res = get_emails(
            account_id=self.account.id,
            folder="inbox",
            q=None,
            limit=100,
            offset=0,
            db=self.db,
            current_user=self.current_user
        )
        self.assertEqual(emails_res.folder_counts.drafts, 1)

        # 3. Confirm draft is NOT returned in GET /emails or Replied view
        replied_res = get_emails(
            account_id=self.account.id,
            folder="replied",
            q=None,
            limit=100,
            offset=0,
            db=self.db,
            current_user=self.current_user
        )
        self.assertEqual(len(replied_res.items), 0)

        # 4. Update the draft (autosave simulation)
        update_req = DraftCreate(
            id=saved_draft.id,
            account_id=self.account.id,
            to_recipients="recruiter@tech.com",
            subject="Re: Interview Schedule",
            html_body="<p>I am available on Monday at 10 AM or Tuesday at 2 PM.</p>",
            composer_mode="reply"
        )
        updated_draft = save_or_update_draft(
            draft_req=update_req,
            db=self.db,
            current_user=self.current_user
        )
        self.assertIn("Tuesday at 2 PM", updated_draft.html_body)

        # 5. Send the draft
        sent_email = send_draft(
            draft_id=saved_draft.id,
            db=self.db,
            current_user=self.current_user
        )
        self.assertEqual(sent_email.folder_status, "replied")
        self.assertIn("Tuesday at 2 PM", sent_email.html_body)

        # Verify draft is deleted from drafts table
        remaining_drafts = get_drafts(
            account_id=self.account.id,
            db=self.db,
            current_user=self.current_user
        )
        self.assertEqual(remaining_drafts.total, 0)

        # Verify sent email appears in Replied folder
        replied_after = get_emails(
            account_id=self.account.id,
            folder="replied",
            q=None,
            limit=100,
            offset=0,
            db=self.db,
            current_user=self.current_user
        )
        self.assertEqual(len(replied_after.items), 1)

    def test_discard_draft(self):
        draft_req = DraftCreate(
            account_id=self.account.id,
            to_recipients="discard@test.com",
            subject="Draft to Discard",
            html_body="<p>Temporary text</p>"
        )
        saved = save_or_update_draft(
            draft_req=draft_req,
            db=self.db,
            current_user=self.current_user
        )

        res = delete_draft(
            draft_id=saved.id,
            db=self.db,
            current_user=self.current_user
        )
        self.assertEqual(res["message"], "Draft deleted successfully")

        drafts_after = get_drafts(
            account_id=self.account.id,
            db=self.db,
            current_user=self.current_user
        )
        self.assertEqual(drafts_after.total, 0)

if __name__ == "__main__":
    unittest.main()
