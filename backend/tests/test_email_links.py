import os
import sys
import base64
import datetime
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import gmail_service as g


class TestEmailLinks(unittest.TestCase):
    def test_plain_text_urls(self):
        for text, href in [
            ("See <https://x.com/a>", "https://x.com/a"),
            ("https://x.com/r?user=me@gmail.com&k=1", "https://x.com/r?user=me@gmail.com&amp;k=1"),
            ("https://x.com/a_(b)", "https://x.com/a_(b)"),
            ("(go https://x.com/a).", "https://x.com/a"),
            ("www.x.com/jobs, now", "https://www.x.com/jobs"),
            ("mail a@b.com.", "mailto:a@b.com"),
        ]:
            out = g._linkify_plain_text(text)
            self.assertIn(f'href="{href}"', out, text)
            self.assertEqual(out.count("<a "), 1, text)

    def test_markup_is_escaped(self):
        self.assertNotIn("<script", g._linkify_plain_text("<script>alert(1)</script> https://x.com"))

    def test_html_body_with_content_id_is_kept(self):
        data = base64.urlsafe_b64encode(b'<a href="https://x.com">x</a>').decode()
        part = {"mimeType": "text/html", "headers": [{"name": "Content-ID", "value": "<b>"}], "body": {"data": data}}
        body, attachments = g._extract_body_and_attachments(None, None, "m", part)
        self.assertIn("https://x.com", body)
        self.assertEqual(attachments, [])

    def test_large_body_is_downloaded(self):
        part = {"mimeType": "text/html", "body": {"attachmentId": "A1", "size": 900000}}
        with mock.patch.object(g, "download_attachment_data", return_value=b'<a href="https://x.com">x</a>'):
            body, attachments = g._extract_body_and_attachments(None, None, "m", part)
        self.assertIn("https://x.com", body)
        self.assertEqual(attachments, [])

    def test_cid_file_is_attachment_unless_body_shows_it(self):
        def part(name, mime, cid):
            return {"mimeType": mime, "filename": name, "headers": [{"name": "X-Attachment-Id", "value": cid}],
                    "body": {"attachmentId": "A_" + cid, "size": 9}}
        data = base64.urlsafe_b64encode(b'<img src="cid:logo1">').decode()
        payload = {"mimeType": "multipart/mixed", "parts": [
            {"mimeType": "text/html", "body": {"data": data}},
            part("logo.png", "image/png", "logo1"),
            part("other.png", "image/png", "logo"),
            part("resume.pdf", "application/pdf", "f_1"),
        ]}
        body, attachments = g._extract_body_and_attachments(None, None, "m", payload)
        self.assertIn("/emails/inline/m/A_logo1", body)
        self.assertEqual([a["filename"] for a in attachments], ["other.png", "resume.pdf"])

    def test_damaged_body_detection(self):
        for body in ["<em>(No body content available)</em>", '<a href="https://x?u=<a href="mailto:a@b.c">', '<a href="https://x&gt" t>']:
            self.assertTrue(g.is_damaged_body(body), body)
        self.assertFalse(g.is_damaged_body('<a href="https://x.com">x</a> <a href="mailto:a@b.c">m</a>'))

    def test_opening_a_damaged_email_repairs_it_and_failure_is_harmless(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.database import Base
        from app.models import ConnectedAccount, Email
        from app.routers.emails import get_email_by_id
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        db = sessionmaker(bind=engine)()
        acc = ConnectedAccount(google_email="me@x.com", access_token="a", refresh_token="b")
        db.add(acc)
        db.commit()
        now = datetime.datetime.now(datetime.timezone.utc)
        email = Email(account_id=acc.id, gmail_message_id="m", sender="s", subject="s", received_at=now, fetched_at=now,
                      html_body="<em>(No body content available)</em>")
        db.add(email)
        db.commit()
        with mock.patch.object(g, "get_valid_access_token", side_effect=ValueError("revoked")):
            self.assertIn("No body", get_email_by_id(email.id, db=db, current_user={}).html_body)
        data = base64.urlsafe_b64encode(b'<a href="https://x.com">x</a>').decode()
        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"payload": {"mimeType": "text/html", "body": {"data": data}}}
        with mock.patch.object(g, "get_valid_access_token", return_value="t"), mock.patch.object(g, "_gmail_get", return_value=resp):
            self.assertIn("https://x.com", get_email_by_id(email.id, db=db, current_user={}).html_body)
        db.close()


if __name__ == "__main__":
    unittest.main()
