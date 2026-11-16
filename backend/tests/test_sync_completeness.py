import os
import sys
import base64
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import ConnectedAccount, Email
from app import gmail_service


class FakeResponse:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data
        self.text = str(data)

    def json(self):
        return self._data


def make_message(msg_id, to_header="me@gmail.com"):
    body = base64.urlsafe_b64encode(f"<p>Body of {msg_id}</p>".encode()).decode()
    return {
        "id": msg_id, "threadId": f"t_{msg_id}", "labelIds": ["INBOX"], "snippet": f"Body of {msg_id}",
        "internalDate": "1700000000000",
        "payload": {
            "mimeType": "text/html",
            "headers": [
                {"name": "From", "value": "Recruiter <r@corp.com>"},
                {"name": "To", "value": to_header},
                {"name": "Subject", "value": f"Subject {msg_id}"},
            ],
            "body": {"data": body},
        },
    }


class FakeGmailClient:
    """Two pages of message ids; m2 has a huge To header, m4 is rate-limited once."""
    def __init__(self, *a, **kw):
        self.calls = []
        self.rate_limited = set()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, headers=None, params=None):
        self.calls.append((url, dict(params or {})))
        if url.endswith("/messages"):
            if params.get("pageToken") == "page2":
                return FakeResponse(200, {"messages": [{"id": "m4"}, {"id": "m5"}]})
            return FakeResponse(200, {"messages": [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}], "nextPageToken": "page2"})
        msg_id = url.rsplit("/", 1)[-1]
        if msg_id == "m4" and msg_id not in self.rate_limited:
            self.rate_limited.add(msg_id)
            return FakeResponse(429, {"error": "rate limited"})
        to = ", ".join(f"person{i}@example.com" for i in range(100)) if msg_id == "m2" else "me@gmail.com"
        return FakeResponse(200, make_message(msg_id, to))


class TestSyncCompleteness(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)()
        self.account = ConnectedAccount(google_email="me@gmail.com", access_token="x", refresh_token="y")
        self.db.add(self.account)
        self.db.commit()
        self.patches = [
            mock.patch.object(gmail_service, "get_valid_access_token", return_value="real_token"),
            mock.patch.object(gmail_service.httpx, "Client", FakeGmailClient),
            mock.patch.object(gmail_service.time, "sleep"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def stored_ids(self):
        return {e.gmail_message_id for e in self.db.query(Email).all()}

    def test_syncs_every_page_trims_long_headers_and_retries_rate_limits(self):
        count = gmail_service.fetch_and_store_emails_for_account(self.db, self.account)
        self.assertEqual(count, 5)
        self.assertEqual(self.stored_ids(), {"m1", "m2", "m3", "m4", "m5"})
        m2 = self.db.query(Email).filter(Email.gmail_message_id == "m2").one()
        self.assertLessEqual(len(m2.recipient), 512)
        self.assertEqual(self.account.sync_status, "success")

    def test_one_rejected_message_does_not_drop_the_others(self):
        def reject_m3(mapper, connection, target):
            if target.gmail_message_id == "m3":
                raise ValueError("value too long for type character varying(512)")

        event.listen(Email, "before_insert", reject_m3)
        try:
            count = gmail_service.fetch_and_store_emails_for_account(self.db, self.account)
        finally:
            event.remove(Email, "before_insert", reject_m3)

        self.assertEqual(count, 4)
        self.assertEqual(self.stored_ids(), {"m1", "m2", "m4", "m5"})
        self.assertEqual(self.account.sync_status, "success")

        # The rejected message is retried (and stored) on the next run
        gmail_service.fetch_and_store_emails_for_account(self.db, self.account)
        self.assertIn("m3", self.stored_ids())

    def test_already_stored_messages_are_not_refetched(self):
        gmail_service.fetch_and_store_emails_for_account(self.db, self.account)
        with mock.patch.object(FakeGmailClient, "get", autospec=True, side_effect=FakeGmailClient.get) as get:
            count = gmail_service.fetch_and_store_emails_for_account(self.db, self.account)
        self.assertEqual(count, 0)
        fetched_urls = [c.args[1] for c in get.call_args_list]
        self.assertTrue(all(u.endswith("/messages") for u in fetched_urls), fetched_urls)


if __name__ == "__main__":
    unittest.main()
