import datetime
import gc
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.database import SessionLocal
from app.models import ConnectedAccount, Email
from app.config import settings
from app.gmail_service import fetch_and_store_emails_for_account, sync_lock

logger = logging.getLogger("scheduler")

scheduler = AsyncIOScheduler()

def purge_expired_inbound_emails():
    """
    Background rolling purge job:
    Deletes inbound emails received more than 24 hours ago (received_at < NOW() - 24 hours).
    Sent replies / outbound emails (folder_status == 'replied' or sender starting with 'Me ') are EXCLUDED
    from deletion so thread history is preserved.
    """
    db = SessionLocal()
    try:
        cutoff_24h = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
        
        # Scope deletion to inbound emails older than 24h
        deleted_count = db.query(Email).filter(
            Email.received_at < cutoff_24h,
            Email.folder_status != "replied",
            ~Email.sender.ilike("Me %")
        ).delete(synchronize_session=False)


        # Sent/replied messages outlive the 24h window only as thread context; past the retention
        # period they can no longer appear in any view, so drop them to keep the database small.
        retention_cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=settings.OUTBOUND_RETENTION_DAYS)
        deleted_outbound = db.query(Email).filter(
            Email.received_at < retention_cutoff
        ).delete(synchronize_session=False)

        db.commit()
        if deleted_count > 0 or deleted_outbound > 0:
            logger.info(
                f"[Purge Job] Auto-deleted {deleted_count} inbound email(s) older than 24 hours and "
                f"{deleted_outbound} sent/replied email(s) older than {settings.OUTBOUND_RETENTION_DAYS} days."
            )
    except Exception as e:
        logger.error(f"[Purge Job Error] Failed executing 24h rolling email purge: {e}")
    finally:
        db.close()

def _sync_one_account(account_id: int) -> int:
    """Syncs a single account in its own DB session (sessions aren't shared across threads)."""
    db = SessionLocal()
    try:
        acc = db.query(ConnectedAccount).filter(ConnectedAccount.id == account_id).first()
        if not acc:
            return 0
        try:
            return fetch_and_store_emails_for_account(db, acc)
        except Exception as e:
            logger.error(f"Error background syncing account {acc.google_email}: {e}")
            return 0
    finally:
        db.close()

def sync_all_connected_accounts():
    """
    Purges expired mail, then syncs every connected account. Accounts are synced a few at a
    time in parallel so a full run over many mailboxes finishes well within one interval;
    a run that overlapped the next one would make APScheduler skip it and delay new mail.
    """
    if not sync_lock.acquire(blocking=False):
        logger.info("Skipping sync: another sync is still running.")
        return
    started = time.monotonic()
    try:
        purge_expired_inbound_emails()

        db = SessionLocal()
        try:
            account_ids = [row[0] for row in db.query(ConnectedAccount.id).all()]
        finally:
            db.close()

        logger.info(f"Syncing {len(account_ids)} connected Google account(s), {settings.SYNC_CONCURRENCY} at a time...")
        with ThreadPoolExecutor(max_workers=max(1, settings.SYNC_CONCURRENCY), thread_name_prefix="gmail-sync") as pool:
            total_fetched = sum(pool.map(_sync_one_account, account_ids))
        logger.info(f"Sync complete in {time.monotonic() - started:.1f}s. {total_fetched} new email(s) stored.")
    finally:
        sync_lock.release()
        # Return memory from parsed Gmail payloads promptly instead of waiting for the next
        # automatic collection, keeping the steady-state footprint low between runs.
        gc.collect()

def trigger_sync_in_background() -> bool:
    """Starts a full sync on a background thread. Returns False if one is already running."""
    if sync_lock.locked():
        return False
    threading.Thread(target=sync_all_connected_accounts, name="manual-sync", daemon=True).start()
    return True

def start_scheduler():
    """Starts the periodic sync, with the first run shortly after startup."""
    scheduler.add_job(
        sync_all_connected_accounts,
        trigger="interval",
        minutes=settings.SYNC_INTERVAL_MINUTES,
        # Run soon after boot instead of one full interval later: after a restart or an idle
        # spin-down, mail would otherwise stay stale until the first interval elapsed.
        next_run_time=datetime.datetime.now() + datetime.timedelta(seconds=10),
        id="gmail_sync_job",
        replace_existing=True,
        max_instances=1,
        coalesce=True
    )
    scheduler.start()
    logger.info(f"APScheduler started ({settings.SYNC_INTERVAL_MINUTES}-minute interval for sync & purge).")

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler shut down.")
