import os
import sys
import datetime
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import ConnectedAccount, Email
from app.schemas import EmailReplyRequest
from app.routers.emails import get_emails, reply_to_email

class TestThreadingAndRepliedFilter(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = self.SessionLocal()

        from app.security import encrypt_token
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

    def test_replied_filter_only_includes_threads_with_outbound_messages(self):
        # 1. Thread A: Inbound only, marked as folder_status 'inbox'
        msg_a = Email(
            account_id=self.account.id,
            gmail_message_id="msg_a_001",
            gmail_thread_id="thread_a",
            sender="Recruiter <recruiter@company.com>",
            recipient=self.account.google_email,
            subject="Job Opportunity",
            html_body="<p>Are you interested?</p>",
            received_at=datetime.datetime.now(datetime.timezone.utc),
            fetched_at=datetime.datetime.now(datetime.timezone.utc),
            folder_status="inbox"
        )
        self.db.add(msg_a)

        # 2. Thread B: Inbound + Outbound reply sent by Me
        msg_b_in = Email(
            account_id=self.account.id,
            gmail_message_id="msg_b_001",
            gmail_thread_id="thread_b",
            sender="Alex <alex@spreetail.com>",
            recipient=self.account.google_email,
            subject="Interview Next Steps",
            html_body="<p>Let's schedule a call.</p>",
            received_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1),
            fetched_at=datetime.datetime.now(datetime.timezone.utc),
            folder_status="replied"
        )
        msg_b_out = Email(
            account_id=self.account.id,
            gmail_message_id="msg_b_002",
            gmail_thread_id="thread_b",
            sender=f"Me <{self.account.google_email}>",
            recipient="Alex <alex@spreetail.com>",
            subject="Re: Interview Next Steps",
            html_body="<p>Sure, tomorrow works!</p>",
            received_at=datetime.datetime.now(datetime.timezone.utc),
            fetched_at=datetime.datetime.now(datetime.timezone.utc),
            folder_status="replied"
        )
        self.db.add(msg_b_in)
        self.db.add(msg_b_out)
        self.db.commit()

        # Query GET /emails for folder='replied'
        res = get_emails(
            account_id=self.account.id,
            folder="replied",
            q=None,
            limit=100,
            offset=0,
            db=self.db,
            current_user=self.current_user
        )

        # Thread B emails should be returned, Thread A should NOT be returned
        thread_ids = set(e.gmail_thread_id for e in res.items)
        self.assertIn("thread_b", thread_ids)
        self.assertNotIn("thread_a", thread_ids)
        self.assertEqual(res.folder_counts.replied, 1)

    def test_idempotent_reply_prevents_duplicate_insertion(self):
        msg_in = Email(
            account_id=self.account.id,
            gmail_message_id="msg_c_001",
            gmail_thread_id="thread_c",
            sender="Hiring Team <hr@tech.com>",
            recipient=self.account.google_email,
            subject="Status Update",
            html_body="<p>Please review attached offer.</p>",
            received_at=datetime.datetime.now(datetime.timezone.utc),
            fetched_at=datetime.datetime.now(datetime.timezone.utc),
            folder_status="inbox"
        )
        self.db.add(msg_in)
        self.db.commit()
        self.db.refresh(msg_in)

        reply_req = EmailReplyRequest(
            to="Hiring Team <hr@tech.com>",
            body_html="<p>Received with thanks!</p>"
        )

        res1 = reply_to_email(
            email_id=msg_in.id,
            reply_req=reply_req,
            db=self.db,
            current_user=self.current_user
        )

        # Simulate second rapid click with exact same parameters
        res2 = reply_to_email(
            email_id=msg_in.id,
            reply_req=reply_req,
            db=self.db,
            current_user=self.current_user
        )

        self.assertEqual(res1.id, res2.id)
        outbound_count = self.db.query(Email).filter(Email.gmail_thread_id == "thread_c", Email.sender.ilike("Me %")).count()
        self.assertEqual(outbound_count, 1)

if __name__ == "__main__":
    unittest.main()
