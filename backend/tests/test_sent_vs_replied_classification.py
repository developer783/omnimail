import os
import sys
import datetime
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import ConnectedAccount, Email
from app.schemas import EmailReplyRequest, DraftCreate
from app.routers.emails import get_emails, reply_to_email
from app.routers.drafts import save_or_update_draft, send_draft
from app.security import encrypt_token

class TestSentVsRepliedClassification(unittest.TestCase):
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

    def test_cold_outreach_is_classified_as_sent_not_replied(self):
        # Create a cold outreach draft (composer_mode='compose', no prior email)
        draft_req = DraftCreate(
            account_id=self.account.id,
            to_recipients="recruiter_yashwanth@company.com",
            subject="Available Candidate – Java Full Stack Developer",
            html_body="<p>Hi Yashwanth, please see my attached resume.</p>",
            composer_mode="compose"
        )
        draft = save_or_update_draft(draft_req, self.db, self.current_user)

        sent_email = send_draft(draft.id, self.db, self.current_user)

        # 1. Verify sent email fields
        self.assertFalse(sent_email.is_reply)
        self.assertEqual(sent_email.folder_status, "sent")

        # 2. Query GET /emails?folder=sent
        sent_res = get_emails(self.account.id, "sent", None, 100, 0, self.db, self.current_user)
        self.assertEqual(len(sent_res.items), 1)
        self.assertEqual(sent_res.items[0].subject, "Available Candidate – Java Full Stack Developer")
        self.assertEqual(sent_res.folder_counts.sent, 1)

        # 3. Query GET /emails?folder=replied -> Should be EMPTY (0 count)
        replied_res = get_emails(self.account.id, "replied", None, 100, 0, self.db, self.current_user)
        self.assertEqual(len(replied_res.items), 0)
        self.assertEqual(replied_res.folder_counts.replied, 0)

    def test_reply_to_inbound_is_classified_as_replied(self):
        inbound = Email(
            account_id=self.account.id,
            gmail_message_id="msg_in_100",
            gmail_thread_id="thread_inbound_100",
            sender="Alex <alex@spreetail.com>",
            recipient=self.account.google_email,
            subject="Interview Opportunity",
            html_body="<p>Let's talk tomorrow.</p>",
            received_at=datetime.datetime.now(datetime.timezone.utc),
            fetched_at=datetime.datetime.now(datetime.timezone.utc),
            folder_status="inbox"
        )
        self.db.add(inbound)
        self.db.commit()
        self.db.refresh(inbound)

        reply_req = EmailReplyRequest(
            to="Alex <alex@spreetail.com>",
            body_html="<p>Hi Alex, tomorrow works great!</p>"
        )

        sent_reply = reply_to_email(inbound.id, reply_req, self.db, self.current_user)

        # 1. Verify sent reply fields
        self.assertTrue(sent_reply.is_reply)
        self.assertEqual(sent_reply.folder_status, "replied")

        # 2. Query GET /emails?folder=replied -> Should return thread_inbound_100
        replied_res = get_emails(self.account.id, "replied", None, 100, 0, self.db, self.current_user)
        self.assertEqual(len(replied_res.items), 2) # inbound + outbound reply
        self.assertEqual(replied_res.folder_counts.replied, 1)

        # 3. Query GET /emails?folder=sent -> Should be EMPTY (0 count)
        sent_res = get_emails(self.account.id, "sent", None, 100, 0, self.db, self.current_user)
        self.assertEqual(len(sent_res.items), 0)
        self.assertEqual(sent_res.folder_counts.sent, 0)

if __name__ == "__main__":
    unittest.main()
