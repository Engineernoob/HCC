"""
HIRE INTEL CLI

Usage:
    hirectl ingest [--source yc_jobs|greenhouse|ashby|github|funding|career_page|social|portfolio_boards]
    hirectl automate
    hirectl dataset build --as-of-start YYYY-MM-DD --as-of-end YYYY-MM-DD
    hirectl model train --dataset artifacts/hiring_velocity_dataset.csv
    hirectl model refresh
    hirectl score --company <name>
    hirectl brief --company <name>
    hirectl outreach --company <name>
    hirectl digest
    hirectl scheduler start
    hirectl api
    hirectl db init
    hirectl status
"""

import asyncio
import logging
from datetime import date
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich import print as rprint

app = typer.Typer(
    name="hirectl",
    help="Real-time hiring intelligence that identifies high-signal opportunities and tells you exactly how to act before they get saturated.",
    rich_markup_mode="rich",
)

console = Console()


# ── Ingest ─────────────────────────────────────────────────────────


@app.command()
def ingest(
    source: Optional[str] = typer.Option(
        None,
        "--source",
        "-s",
        help="Source to run: yc_jobs | greenhouse | ashby | github | funding | career_page | social | portfolio_boards | all",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run ingestion, persist results, and rescore affected companies."""
    logging.basicConfig(level="DEBUG" if verbose else "INFO")

    async def _run():
        from hirectl.ingestion.ashby import AshbyAdapter
        from hirectl.ingestion.career_page import CareerPageCrawler
        from hirectl.ingestion.funding import FundingFeedAdapter
        from hirectl.ingestion.github_watcher import GitHubWatcher
        from hirectl.ingestion.greenhouse import GreenhouseAdapter
        from hirectl.ingestion.portfolio_boards import PortfolioBoardsAdapter
        from hirectl.ingestion.service import IngestionService
        from hirectl.ingestion.social import SocialSignalAdapter
        from hirectl.ingestion.yc_jobs import YCJobsAdapter

        adapters = {
            "yc_jobs": YCJobsAdapter,
            "greenhouse": GreenhouseAdapter,
            "ashby": AshbyAdapter,
            "github": GitHubWatcher,
            "funding": FundingFeedAdapter,
            "career_page": CareerPageCrawler,
            "social": SocialSignalAdapter,
            "portfolio_boards": PortfolioBoardsAdapter,
        }

        to_run = (
            {source: adapters[source]} if source and source in adapters else adapters
        )
        service = IngestionService()

        for name, cls in to_run.items():
            with console.status(f"[dim]Running {name}...[/dim]"):
                result = await cls().run()

            if result.ok:
                summary = await service.process(result)
                rprint(
                    f"[green]✓[/green] [bold]{name}[/bold] — "
                    f"{len(result.companies)} companies, "
                    f"{len(result.roles)} roles, "
                    f"{len(result.signals)} signals "
                    f"[dim]({result.duration_seconds:.1f}s)[/dim]\n"
                    f"    persisted: "
                    f"{summary['companies_upserted']} companies, "
                    f"{summary['signals_new']} new signals, "
                    f"{summary['roles_new']} new roles, "
                    f"{summary['companies_rescored']} rescored"
                )
            else:
                rprint(f"[red]✗[/red] [bold]{name}[/bold] — {result.error}")

    asyncio.run(_run())


# ── Score ──────────────────────────────────────────────────────────


@app.command()
def automate():
    """Run the rules-based automation pass now."""

    async def _run():
        from hirectl.automation.service import AutomationService

        with console.status("[dim]Running automation...[/dim]"):
            summary = await AutomationService().run()
        rprint(
            f"[green]✓[/green] Automation complete — "
            f"{summary.get('companies_scanned', 0)} scanned, "
            f"{summary.get('watchlist_added', 0)} watchlisted, "
            f"{summary.get('watchlist_removed', 0)} removed, "
            f"{summary.get('priority_updated', 0)} reprioritized, "
            f"{summary.get('outreach_created', 0)} outreach drafts created"
        )

    asyncio.run(_run())


# ── Score ──────────────────────────────────────────────────────────


@app.command()
def dataset(
    action: str = typer.Argument(help="build"),
    as_of_start: str = typer.Option(..., "--as-of-start", help="Inclusive start date (YYYY-MM-DD)"),
    as_of_end: str = typer.Option(..., "--as-of-end", help="Inclusive end date (YYYY-MM-DD)"),
    output: str = typer.Option(
        "artifacts/hiring_velocity_dataset.csv",
        "--output",
        help="CSV output path",
    ),
    step_days: int = typer.Option(7, "--step-days", min=1, help="Snapshot stride in days"),
):
    """Build a Phase 2.5 training dataset from historical snapshots."""
    if action != "build":
        rprint(f"[red]Unknown dataset action: {action}[/red]")
        raise typer.Exit(code=1)

    try:
        start_date = date.fromisoformat(as_of_start)
        end_date = date.fromisoformat(as_of_end)
    except ValueError as exc:
        rprint(f"[red]Invalid date: {exc}[/red]")
        raise typer.Exit(code=1)

    async def _run():
        from hirectl.analytics.history import HistoricalAnalyticsService

        with console.status("[dim]Building historical dataset...[/dim]"):
            summary = await HistoricalAnalyticsService().export_dataset(
                as_of_start=start_date,
                as_of_end=end_date,
                output_path=output,
                step_days=step_days,
            )
        rprint(
            f"[green]✓[/green] Dataset built — "
            f"{summary['rows_written']} rows written to "
            f"[bold]{summary['output_path']}[/bold] "
            f"[dim]({summary['feature_version']}, stride={summary['step_days']}d)[/dim]"
        )

    asyncio.run(_run())


# ── Score ──────────────────────────────────────────────────────────


@app.command()
def model(
    action: str = typer.Argument(help="train | refresh"),
    dataset: str = typer.Option(
        "artifacts/hiring_velocity_dataset.csv",
        "--dataset",
        help="Training dataset CSV for model train",
    ),
    artifact: Optional[str] = typer.Option(
        None,
        "--artifact",
        help="Output model artifact path",
    ),
):
    """Train or refresh the Phase 3 hiring velocity model."""
    from hirectl.config import settings

    artifact_path = artifact or settings.model_artifact_path

    if action == "train":
        from hirectl.modeling.baseline import train_baseline_model

        with console.status("[dim]Training baseline model...[/dim]"):
            summary = train_baseline_model(
                dataset_path=dataset,
                artifact_path=artifact_path,
            )
        metrics = summary["metrics"]
        rprint(
            f"[green]✓[/green] Model trained — "
            f"{summary['rows']} rows, "
            f"artifact [bold]{summary['artifact_path']}[/bold]\n"
            f"    valid: mae={metrics['valid_mae']}, rmse={metrics['valid_rmse']}, r2={metrics['valid_r2']}"
        )
        return

    if action == "refresh":
        async def _run():
            from hirectl.ingestion.service import IngestionService

            with console.status("[dim]Refreshing model-blended company scores...[/dim]"):
                return await IngestionService().refresh_all_company_scores()

        summary = asyncio.run(_run())
        rprint(
            f"[green]✓[/green] Model refresh complete — "
            f"{summary['companies_refreshed']} companies rescored"
        )
        return

    rprint(f"[red]Unknown model action: {action}[/red]")
    raise typer.Exit(code=1)


# ── Score ──────────────────────────────────────────────────────────


@app.command()
def score(
    company: str = typer.Argument(help="Company name to score"),
):
    """Show the score breakdown for a company."""
    from hirectl.scoring.engine import ScoringEngine, UserProfile
    from datetime import datetime, timedelta

    engine = ScoringEngine(UserProfile())

    # Demo score — in production, load from DB
    result = engine.score_company(
        company_name=company,
        role_types=["backend", "distributed"],
        required_skills=["go", "python", "kubernetes"],
        funding_stage="series_b",
        last_funding_date=datetime.utcnow() - timedelta(days=5),
        last_role_posted=datetime.utcnow() - timedelta(days=2),
        oldest_open_role_days=8,
        has_founder_post=False,
        founder_post_date=None,
        github_spike_date=datetime.utcnow() - timedelta(days=1),
        github_spike_sigma=2.8,
        has_engineering_blog=True,
        remote_us=True,
        headcount=45,
        funding_amount_usd=67_000_000,
    )

    console.print(engine.explain(result))


# ── Brief ──────────────────────────────────────────────────────────


@app.command()
def brief(
    company: str = typer.Argument(help="Company name"),
    provider: Optional[str] = typer.Option(
        None, "--provider", "-p", help="Override AI provider"
    ),
):
    """Generate an AI intelligence brief for a company."""
    from hirectl.ai.engine import AIEngine, CompanyContext

    if provider:
        import os

        os.environ["AI_PROVIDER"] = provider

    engine = AIEngine()
    ctx = CompanyContext(
        name=company,
        recent_signals=["Recent funding", "New engineering roles posted"],
        fit_score=85.0,
        urgency_label="high",
    )

    async def _run():
        with console.status("[dim]Generating brief...[/dim]"):
            text = await engine.generate_brief(ctx)
        console.print(f"\n[bold gold1]{company} — Intelligence Brief[/bold gold1]")
        console.print("─" * 60)
        console.print(text)
        console.print()

    asyncio.run(_run())


@app.command("brief-refresh")
def brief_refresh(
    limit: int = typer.Option(8, "--limit", "-l", min=1, help="Maximum briefs to refresh"),
):
    """Refresh cached AI briefs outside the ingest path."""

    async def _run():
        from hirectl.ingestion.service import IngestionService

        with console.status("[dim]Refreshing AI briefs...[/dim]"):
            summary = await IngestionService().refresh_company_briefs(limit=limit)

        rprint(
            f"[green]✓[/green] Brief refresh — "
            f"{summary.get('updated', 0)} updated / {summary.get('candidates', 0)} candidates"
        )

    asyncio.run(_run())


# ── Outreach ───────────────────────────────────────────────────────


@app.command()
def outreach(
    company: str = typer.Argument(help="Company name"),
    contact: str = typer.Option("engineering lead", "--contact", "-c"),
    angle: str = typer.Option(
        "", "--angle", "-a", help="Specific technical angle to reference"
    ),
):
    """Generate a cold outreach draft for a company."""
    from hirectl.ai.engine import AIEngine, CompanyContext

    engine = AIEngine()
    ctx = CompanyContext(
        name=company,
        recent_signals=["Recent activity detected"],
        fit_score=80.0,
        urgency_label="high",
    )

    async def _run():
        with console.status("[dim]Drafting outreach...[/dim]"):
            draft = await engine.generate_outreach_draft(ctx, contact, angle)
        console.print(f"\n[bold gold1]Outreach Draft — {company}[/bold gold1]")
        console.print("─" * 60)
        console.print(draft)
        console.print()

    asyncio.run(_run())


# ── Digest ─────────────────────────────────────────────────────────


@app.command()
def digest(
    send: bool = typer.Option(False, "--send", help="Actually send email"),
):
    """Generate (and optionally send) the daily digest."""
    from hirectl.alerts.digest import EmailDigest, DigestData

    email = EmailDigest()
    data = DigestData(
        top_companies=[
            {
                "name": "Baseten",
                "score": 94,
                "urgency": "critical",
                "tagline": "ML Infra",
                "stage": "Series B",
                "signals": ["Batch ATS posting"],
            },
            {
                "name": "Modal Labs",
                "score": 91,
                "urgency": "critical",
                "tagline": "GPU Compute",
                "stage": "Series B",
                "signals": ["$67M Series B closed"],
            },
        ],
        new_signals=[
            {
                "type": "funding",
                "company": "Modal Labs",
                "headline": "Closed $67M Series B",
            },
            {
                "type": "founder_post",
                "company": "Turso",
                "headline": "Founder urgent hire post",
            },
        ],
        outreach_due=[],
        stats={"companies": 34, "new_signals": 12},
    )

    async def _run():
        if send:
            await email.send(data)
        else:
            text = email._render_text(data)
            console.print(text)
            console.print("\n[dim]Pass --send to actually send via email[/dim]")

    asyncio.run(_run())


# ── API ────────────────────────────────────────────────────────────


@app.command()
def api(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload"),
):
    """Start the FastAPI server."""
    import uvicorn

    uvicorn.run(
        "hirectl.api.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


# ── Scheduler ──────────────────────────────────────────────────────


@app.command()
def scheduler():
    """Start the ingestion scheduler."""
    from hirectl.scheduler import main

    asyncio.run(main())


# ── DB ─────────────────────────────────────────────────────────────


@app.command()
def db(
    action: str = typer.Argument(help="init | reset | status"),
):
    """Database management commands."""

    async def _run():
        from hirectl.db.session import create_tables, check_connection

        if action == "init":
            with console.status("[dim]Creating tables...[/dim]"):
                await create_tables()
            rprint("[green]✓[/green] Database tables created")
        elif action == "status":
            ok = await check_connection()
            rprint(
                f"[{'green' if ok else 'red'}]{'✓' if ok else '✗'}[/] Database: {'connected' if ok else 'unreachable'}"
            )
        else:
            rprint(f"[red]Unknown action: {action}[/red]")

    asyncio.run(_run())


# ── Status ─────────────────────────────────────────────────────────


@app.command()
def status():
    """Show system status — DB, AI, GitHub, last ingest."""
    from hirectl.config import settings

    table = Table(title="HIRE INTEL — System Status", border_style="dim")
    table.add_column("Component", style="dim")
    table.add_column("Status")
    table.add_column("Detail")

    async def _run():
        from hirectl.db.session import check_connection

        db_ok = await check_connection()

        table.add_row(
            "Database",
            "[green]Connected[/]" if db_ok else "[red]Unreachable[/]",
            settings.database_url.split("@")[-1],
        )
        table.add_row(
            "AI Provider",
            (
                "[yellow]Best effort[/]"
                if settings.ai_provider == "ollama"
                else "[green]Ready[/]" if settings.ai_available else "[yellow]Not configured[/]"
            ),
            (
                f"{settings.ai_provider} / {settings.ai_model} @ {settings.ollama_base_url}"
                if settings.ai_provider == "ollama"
                else f"{settings.ai_provider} / {settings.ai_model}"
            ),
        )
        table.add_row(
            "GitHub",
            (
                "[green]Token set[/]"
                if settings.github_available
                else "[yellow]No token (rate limited)[/]"
            ),
            "5000 req/hr" if settings.github_available else "60 req/hr",
        )
        table.add_row(
            "Email",
            (
                "[green]Configured[/]"
                if settings.resend_api_key
                else "[dim]Not configured[/]"
            ),
            settings.alert_email_to or "—",
        )
        table.add_row(
            "Environment",
            settings.environment,
            "",
        )
        console.print(table)

    asyncio.run(_run())


if __name__ == "__main__":
    app()
