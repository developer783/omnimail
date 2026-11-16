import os
import sys
import base64
import datetime
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import ConnectedAccount, Email
from app.routers.emails import get_emails
from app.security import encrypt_token
from app.config import settings
from app import gmail_service, scheduler
from app.migrations import run_migrations_and_backfill


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


class TestMemoryLimits(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = self.SessionLocal()
        self.account = ConnectedAccount(
            google_email="me@gmail.com",
            access_token=encrypt_token("demo_token"),
            refresh_token=encrypt_token("demo_refresh"),
            sync_status="success"
        )
        self.db.add(self.account)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def _add_email(self, msg_id, sender="Friend <f@x.com>", age=datetime.timedelta(0), body="<p>Hello there</p>", **kw):
        email = Email(
            account_id=self.account.id, gmail_message_id=msg_id, gmail_thread_id=kw.pop("thread_id", msg_id),
            sender=sender, recipient="me@gmail.com", subject="Subject", html_body=body,
            received_at=_utcnow() - age, fetched_at=_utcnow(), **kw
        )
        self.db.add(email)
        self.db.commit()
        return email

    def test_list_endpoint_omits_bodies_but_returns_snippets(self):
        self._add_email("m1", body="<p>" + "x" * 500_000 + "</p>", snippet="Short preview")
        res = get_emails(account_id=None, folder="inbox", q=None, limit=100, offset=0,
                         db=self.db, current_user={"sub": "admin"})
        self.assertEqual(len(res.items), 1)
        self.assertIsNone(res.items[0].html_body)
        self.assertEqual(res.items[0].snippet, "Short preview")

    def test_large_inline_images_are_linked_not_downloaded(self):
        small_png = base64.urlsafe_b64encode(b"tiny").decode()
        payload = {
            "mimeType": "multipart/related",
            "parts": [
                {"mimeType": "text/html", "body": {"data": base64.urlsafe_b64encode(
                    b'<html><head></head><body><img src="cid:big"><img src="cid:small"></body></html>').decode()}},
                {"mimeType": "image/png", "filename": "big.png", "headers": [{"name": "Content-ID", "value": "<big>"}],
                 "body": {"attachmentId": "ATT-123_abc", "size": 5_000_000}},
                {"mimeType": "image/png", "filename": "small.png", "headers": [{"name": "Content-ID", "value": "<small>"}],
                 "body": {"data": small_png, "size": 4}},
            ],
        }
        with mock.patch.object(gmail_service, "download_attachment_data", side_effect=AssertionError("must not download")):
            body, attachments = gmail_service._extract_body_and_attachments(self.db, self.account, "MSG1", payload)
        self.assertIn('src="/emails/inline/MSG1/ATT-123_abc?mime=image%2Fpng"', body)
        self.assertIn("data:image/png;base64,", body)
        self.assertEqual(attachments, [])

    def test_oversized_bodies_have_data_uris_stripped(self):
        huge = '<img src="data:image/png;base64,' + "A" * (settings.MAX_STORED_BODY_BYTES + 10) + '"><p>text</p>'
        capped = gmail_service._cap_body_size(huge)
        self.assertLess(len(capped), 1000)
        self.assertIn("<p>text</p>", capped)

    def test_purge_drops_outbound_past_retention_and_keeps_recent(self):
        self._add_email("old_sent", sender="Me <me@gmail.com>", age=datetime.timedelta(days=settings.OUTBOUND_RETENTION_DAYS + 1), folder_status="replied")
        self._add_email("recent_sent", sender="Me <me@gmail.com>", age=datetime.timedelta(days=2), folder_status="replied")
        self._add_email("old_inbound", age=datetime.timedelta(hours=30))
        self._add_email("new_inbound", age=datetime.timedelta(hours=1))
        with mock.patch.object(scheduler, "SessionLocal", self.SessionLocal):
            scheduler.purge_expired_inbound_emails()
        remaining = {e.gmail_message_id for e in self.SessionLocal().query(Email).all()}
        self.assertEqual(remaining, {"recent_sent", "new_inbound"})

    def test_scheduled_sync_skips_while_another_sync_runs(self):
        with mock.patch.object(scheduler, "fetch_and_store_emails_for_account") as fetch, \
             mock.patch.object(scheduler, "purge_expired_inbound_emails") as purge:
            with gmail_service.sync_lock:
                scheduler.sync_all_connected_accounts()
            fetch.assert_not_called()
            purge.assert_not_called()

    def test_migration_adds_and_backfills_snippet_and_reclassifies_in_bulk(self):
        self._add_email("in1", thread_id="t1", body="<style>p{}</style><p>Inbound &amp; hello</p>")
        self._add_email("out1", sender="Me <me@gmail.com>", thread_id="t1", folder_status="sent")
        self._add_email("out2", sender="Me <me@gmail.com>", thread_id="t2", folder_status="replied", is_reply=True)
        self.db.execute(text("ALTER TABLE emails DROP COLUMN snippet"))
        self.db.commit()

        run_migrations_and_backfill(self.db)

        rows = {e.gmail_message_id: e for e in self.SessionLocal().query(Email).all()}
        self.assertEqual(rows["in1"].snippet, "Inbound & hello")
        self.assertEqual((rows["out1"].folder_status, rows["out1"].is_reply), ("replied", True))
        self.assertEqual((rows["out2"].folder_status, rows["out2"].is_reply), ("sent", False))


if __name__ == "__main__":
    unittest.main()
