"""
APScheduler-based ingestion scheduler.

Runs all ingestion pipelines on configurable cron schedules.
Can be run as a standalone process or embedded in the FastAPI app.

Usage:
    python -m hirectl.scheduler          # standalone
    hirectl scheduler start              # via CLI
"""

import asyncio
import logging
from contextlib import suppress
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from hirectl.config import settings

logger = logging.getLogger(__name__)
HEARTBEAT_PATH = Path("/tmp/hirectl_scheduler_heartbeat")


async def _run_adapter(name: str, adapter) -> None:
    from hirectl.ingestion.service import IngestionService

    result = await adapter.run()
    if not result.ok:
        logger.warning(f"{name}: ingest failed: {result.error}")
        return

    summary = await IngestionService().process(result)
    logger.info(
        f"{name}: {summary['signals_new']} new signals, "
        f"{summary['roles_new']} new roles, "
        f"{summary['companies_rescored']} rescored"
    )


async def run_yc_jobs():
    from hirectl.ingestion.yc_jobs import YCJobsAdapter

    if not settings.yc_jobs_enabled:
        return
    await _run_adapter("YC Jobs", YCJobsAdapter())


async def run_greenhouse():
    from hirectl.ingestion.greenhouse import GreenhouseAdapter

    await _run_adapter("Greenhouse", GreenhouseAdapter())


async def run_ashby():
    from hirectl.ingestion.ashby import AshbyAdapter

    await _run_adapter("Ashby", AshbyAdapter())


async def run_github():
    from hirectl.ingestion.github_watcher import GitHubWatcher

    await _run_adapter("GitHub", GitHubWatcher())


async def run_funding():
    from hirectl.ingestion.funding import FundingFeedAdapter

    await _run_adapter("Funding", FundingFeedAdapter())


async def run_career_pages():
    from hirectl.ingestion.career_page import CareerPageCrawler

    await _run_adapter("Career Pages", CareerPageCrawler())


async def run_social():
    from hirectl.ingestion.social import SocialSignalAdapter

    if not settings.social_enabled:
        return
    await _run_adapter("Social", SocialSignalAdapter())


async def run_portfolio_boards():
    from hirectl.ingestion.portfolio_boards import PortfolioBoardsAdapter

    await _run_adapter("Portfolio Boards", PortfolioBoardsAdapter())


async def run_daily_rollups():
    from hirectl.analytics.history import HistoricalAnalyticsService

    summary = await HistoricalAnalyticsService().rollup_day()
    logger.info(
        f"Daily rollups: {summary['companies_rolled_up']} companies "
        f"for {summary['as_of_date']}"
    )


async def run_automation():
    from hirectl.automation.service import AutomationService

    summary = await AutomationService().run()
    logger.info(
        f"Automation: scanned={summary.get('companies_scanned', 0)} "
        f"watchlisted={summary.get('watchlist_added', 0)} "
        f"outreach_created={summary.get('outreach_created', 0)}"
    )


async def run_model_refresh():
    from hirectl.ingestion.service import IngestionService
    from hirectl.modeling.service import HiringVelocityModelService

    if not HiringVelocityModelService().is_available():
        logger.info("Model refresh skipped: no trained artifact")
        return

    summary = await IngestionService().refresh_all_company_scores()
    logger.info(f"Model refresh: {summary['companies_refreshed']} companies rescored")


async def run_brief_refresh():
    from hirectl.ingestion.service import IngestionService

    summary = await IngestionService().refresh_company_briefs()
    logger.info(
        "Brief refresh: candidates=%s updated=%s",
        summary.get("candidates", 0),
        summary.get("updated", 0),
    )


async def run_daily_digest():
    """Generate and send the daily morning digest."""
    logger.info("Generating daily digest...")
    from hirectl.alerts.digest import EmailDigest, DigestData

    # In production: load from DB
    # For now: generate with whatever's available
    digest = EmailDigest()

    data = DigestData(
        top_companies=[],
        new_signals=[],
        outreach_due=[],
        stats={"companies": 0, "new_signals": 0},
    )

    await digest.send(data)
    logger.info("Daily digest sent")


async def run_all():
    """Run all ingestion sources once (for manual triggering)."""
    logger.info("Running full ingestion sweep...")
    jobs = [
        run_yc_jobs,
        run_greenhouse,
        run_ashby,
        run_github,
        run_funding,
        run_career_pages,
        run_social,
        run_portfolio_boards,
        run_daily_rollups,
        run_model_refresh,
        run_brief_refresh,
        run_automation,
    ]
    for job in jobs:
        try:
            await job()
        except Exception as exc:
            logger.warning(f"{job.__name__}: startup run failed: {exc}")
    logger.info("Full ingestion sweep complete")


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance."""
    scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)

    # Parse cron expressions from settings
    def cron(expr: str) -> CronTrigger:
        parts = expr.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {expr}")
        return CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )

    def add_job(func, expr: str, job_id: str) -> None:
        scheduler.add_job(
            func,
            cron(expr),
            id=job_id,
            max_instances=settings.scheduler_job_max_instances,
            coalesce=settings.scheduler_job_coalesce,
            misfire_grace_time=settings.scheduler_job_misfire_grace_seconds,
        )

    add_job(run_yc_jobs, settings.cron_job_boards, "yc_jobs")
    add_job(run_greenhouse, settings.cron_job_boards, "greenhouse")
    add_job(run_ashby, settings.cron_job_boards, "ashby")
    add_job(run_github, settings.cron_github, "github")
    add_job(run_funding, settings.cron_funding, "funding")
    add_job(run_social, settings.cron_social, "social")
    add_job(run_portfolio_boards, settings.cron_job_boards, "portfolio_boards")
    add_job(run_career_pages, settings.cron_career_pages, "career_pages")
    add_job(run_automation, settings.cron_automation, "automation")
    add_job(run_daily_rollups, settings.cron_daily_rollups, "daily_rollups")
    add_job(run_model_refresh, settings.cron_model_refresh, "model_refresh")
    add_job(run_brief_refresh, settings.cron_brief_refresh, "brief_refresh")
    add_job(run_daily_digest, settings.cron_daily_digest, "digest")

    return scheduler


async def main():
    """Run the scheduler as a standalone process."""
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logging.getLogger("apscheduler").setLevel(settings.apscheduler_log_level.upper())
    logger.info("Starting HIRE INTEL scheduler")
    logger.info("Scheduler timezone: %s", settings.scheduler_timezone)

    if settings.scheduler_run_on_startup:
        await run_all()

    scheduler = create_scheduler()
    scheduler.start()
    heartbeat_task = asyncio.create_task(_heartbeat_loop())

    logger.info("Scheduler running. Press Ctrl+C to stop.")
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task
        scheduler.shutdown()
        with suppress(FileNotFoundError):
            HEARTBEAT_PATH.unlink()
        logger.info("Scheduler stopped")


async def _heartbeat_loop() -> None:
    """Write a heartbeat file so Docker can healthcheck the scheduler process."""
    while True:
        HEARTBEAT_PATH.write_text("ok")
        await asyncio.sleep(15)


if __name__ == "__main__":
    asyncio.run(main())
