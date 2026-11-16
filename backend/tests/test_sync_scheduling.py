import os
import sys
import time
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import ConnectedAccount
from app.config import settings
from app import scheduler, gmail_service
from app.routers.emails import trigger_manual_email_sync


class TestSyncScheduling(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{os.path.join(self.tmpdir.name, 'sync.db')}",
            connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        db = self.SessionLocal()
        for i in range(8):
            db.add(ConnectedAccount(google_email=f"user{i}@gmail.com", access_token="", refresh_token=""))
        db.commit()
        db.close()
        self.patches = [
            mock.patch.object(scheduler, "SessionLocal", self.SessionLocal),
            mock.patch.object(scheduler, "purge_expired_inbound_emails"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.engine.dispose()
        self.tmpdir.cleanup()

    def test_accounts_sync_in_parallel(self):
        synced = []

        def slow_fetch(db, acc):
            time.sleep(0.3)
            synced.append(acc.google_email)
            return 1

        with mock.patch.object(scheduler, "fetch_and_store_emails_for_account", side_effect=slow_fetch), \
             mock.patch.object(settings, "SYNC_CONCURRENCY", 4):
            started = time.monotonic()
            scheduler.sync_all_connected_accounts()
            elapsed = time.monotonic() - started

        self.assertEqual(len(synced), 8)
        # 8 accounts x 0.3s sequentially would be 2.4s; 4 at a time is ~0.6s
        self.assertLess(elapsed, 1.5)
        self.assertFalse(gmail_service.sync_lock.locked())

    def test_failing_account_does_not_stop_others(self):
        def fetch(db, acc):
            if acc.google_email == "user3@gmail.com":
                raise RuntimeError("boom")
            return 1

        with mock.patch.object(scheduler, "fetch_and_store_emails_for_account", side_effect=fetch) as m:
            scheduler.sync_all_connected_accounts()
        self.assertEqual(m.call_count, 8)
        self.assertFalse(gmail_service.sync_lock.locked())

    def test_manual_sync_returns_immediately_and_runs_in_background(self):
        release = threading.Event()
        calls = []

        def blocking_fetch(db, acc):
            calls.append(acc.id)
            release.wait(5)
            return 0

        with mock.patch.object(scheduler, "fetch_and_store_emails_for_account", side_effect=blocking_fetch):
            db = self.SessionLocal()
            started = time.monotonic()
            res = trigger_manual_email_sync(db=db, current_user={"sub": "admin"})
            self.assertLess(time.monotonic() - started, 1.0)
            self.assertEqual(res.status, "success")
            self.assertIn("Checking 8 mailbox", res.message)

            # A second click while the first sync is running doesn't start another
            res2 = trigger_manual_email_sync(db=db, current_user={"sub": "admin"})
            self.assertIn("already running", res2.message)

            release.set()
            deadline = time.monotonic() + 5
            while gmail_service.sync_lock.locked() and time.monotonic() < deadline:
                time.sleep(0.05)
            db.close()
        self.assertEqual(len(calls), 8)
        self.assertFalse(gmail_service.sync_lock.locked())


if __name__ == "__main__":
    unittest.main()
