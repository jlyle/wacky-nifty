
from apscheduler.schedulers.background import BackgroundScheduler

_scheduler = None

def _settings(get_db):
    conn = get_db()
    enabled = conn.execute(
        "SELECT value FROM ebay_app_settings WHERE key='auto_scan_enabled'"
    ).fetchone()
    interval = conn.execute(
        "SELECT value FROM ebay_app_settings WHERE key='auto_scan_interval_minutes'"
    ).fetchone()
    conn.close()
    return {
        "enabled": bool(enabled and str(enabled["value"]) == "1"),
        "interval": max(15, int(interval["value"])) if interval else 30,
    }

def _job(app, get_db):
    from services.research_scanner import run_research_scan
    with app.app_context():
        result = run_research_scan(get_db, trigger_type="scheduled")
        if result.get("busy"):
            app.logger.info("Scheduled Wacky eBay scan skipped; scan already running.")

def start_scheduler(app, get_db):
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.start()
    reschedule(app, get_db)
    return _scheduler

def reschedule(app, get_db):
    global _scheduler
    if _scheduler is None:
        return start_scheduler(app, get_db)
    existing = _scheduler.get_job("wacky_ebay_scan")
    if existing:
        _scheduler.remove_job("wacky_ebay_scan")
    settings = _settings(get_db)
    if settings["enabled"]:
        _scheduler.add_job(
            _job, "interval", minutes=settings["interval"],
            args=[app, get_db], id="wacky_ebay_scan",
            replace_existing=True, max_instances=1, coalesce=True,
        )

def status():
    if _scheduler is None:
        return {"running": False, "next_run": None}
    job = _scheduler.get_job("wacky_ebay_scan")
    return {
        "running": bool(job),
        "next_run": job.next_run_time.isoformat() if job and job.next_run_time else None,
    }
