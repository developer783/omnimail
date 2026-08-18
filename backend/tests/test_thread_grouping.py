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

class TestThreadGrouping(unittest.TestCase):
    def setUp(self):
        # Setup in-memory SQLite database for testing thread grouping logic
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = self.SessionLocal()

        # Create test account
        self.account = ConnectedAccount(
            google_email="chaudharyaayush9832@gmail.com",
            access_token="demo_token",
            refresh_token="demo_refresh",
            sync_status="success"
        )
        self.db.add(self.account)
        self.db.commit()
        self.db.refresh(self.account)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def test_inbound_and_reply_share_same_thread_id(self):
        # 1. Ingest Inbound Email (Spreetail thread)
        thread_id = "thread_spreetail_12345"
        inbound = Email(
            account_id=self.account.id,
            gmail_message_id="msg_inbound_001",
            gmail_thread_id=thread_id,
            message_id_header="<msg_inbound_001@spreetail.com>",
            sender="Alex Schafer <alex.schafer@spreetail.com>",
            recipient=self.account.google_email,
            subject="Interview Opportunity with Spreetail",
            html_body="<p>Hi Chaudharyaayush, let us schedule an interview!</p>",
            received_at=datetime.datetime.utcnow() - datetime.timedelta(hours=2),
            fetched_at=datetime.datetime.utcnow(),
            is_read=False,
            is_starred=False,
            folder_status="inbox"
        )
        self.db.add(inbound)
        self.db.commit()
        self.db.refresh(inbound)

        # 2. Simulate Reply creation
        sent_gmail_id = "msg_reply_002"
        target_thread_id = inbound.gmail_thread_id  # Should match original thread_id

        sent_email = Email(
            account_id=self.account.id,
            gmail_message_id=sent_gmail_id,
            gmail_thread_id=target_thread_id,
            message_id_header=f"<{sent_gmail_id}@mail.gmail.com>",
            sender=f"Me <{self.account.google_email}>",
            recipient=inbound.sender,
            subject=f"Re: {inbound.subject}",
            html_body="<p>Thanks Alex, I am looking forward to it!</p>",
            received_at=datetime.datetime.utcnow(),
            fetched_at=datetime.datetime.utcnow(),
            is_read=True,
            is_starred=False,
            folder_status="replied"
        )
        inbound.folder_status = "replied"
        self.db.add(sent_email)
        self.db.commit()

        # 3. Assert DB state: Both rows share the exact same gmail_thread_id
        emails_in_db = self.db.query(Email).filter(Email.gmail_thread_id == thread_id).all()
        self.assertEqual(len(emails_in_db), 2)
        senders = [e.sender for e in emails_in_db]
        self.assertIn("Alex Schafer <alex.schafer@spreetail.com>", senders)
        self.assertIn("Me <chaudharyaayush9832@gmail.com>", senders)

        # 4. Test query for 'replied' folder: returns both messages
        replied_thread_rows = self.db.query(Email).filter(
            Email.gmail_thread_id.in_(
                self.db.query(Email.gmail_thread_id).filter(Email.folder_status == "replied")
            )
        ).all()
        self.assertEqual(len(replied_thread_rows), 2)

if __name__ == "__main__":
    unittest.main()
