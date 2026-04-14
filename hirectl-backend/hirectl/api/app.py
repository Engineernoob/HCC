"""
FastAPI application — REST API for HIRE INTEL frontend.

All endpoints are async. DB queries go through repositories.
Falls back to mock data when DB is unavailable (dev without Postgres).
"""

import logging
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Request, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from hirectl.config import settings
from hirectl.db.session import check_connection, create_tables
from hirectl.signals.payloads import signal_payload_from_model, TYPE_LABELS, score_variant
from hirectl.signals.stream import signal_stream_broker

logger = logging.getLogger(__name__)


async def require_admin(authorization: str = Header(default="")) -> None:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not settings.admin_token_is_valid(token):
        raise HTTPException(status_code=401, detail="Invalid admin token")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("HIRE INTEL API starting")
    if await check_connection():
        await create_tables()
        logger.info("Database ready")
    else:
        logger.warning("Database unreachable — mock mode active")
    yield
    logger.info("HIRE INTEL API shutting down")


app = FastAPI(
    title="HIRE INTEL API",
    version="1.0.0",
    description="A real-time hiring intelligence system that identifies high-signal opportunities and tells you exactly how to act before they get saturated.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Response models ────────────────────────────────────────────────


class CompanyOut(BaseModel):
    id: str
    name: str
    slug: str
    tagline: str
    stage: str
    funding_amount: Optional[float]
    funding_label: str
    remote_us: bool
    remote_label: str
    fit_score: float
    urgency_score: float
    composite_score: float
    urgency_label: str
    open_roles_count: int
    signal_count: int
    tech_stack: dict
    chips: list[dict]
    description: str
    ai_brief: Optional[str]
    on_watchlist: bool
    last_signal_at: Optional[datetime]


class SignalOut(BaseModel):
    id: str
    company_id: str
    company_name: str
    type: str
    type_label: str
    headline: str
    detail: str
    score: float
    score_variant: str  # "high" | "medium" | "low"
    signal_date: datetime
    source_url: str


class RoleOut(BaseModel):
    id: str
    company_id: str
    company_name: str
    title: str
    url: str
    role_type: str
    seniority: str
    is_remote: bool
    is_remote_us: bool
    location: str
    fit_score: float
    days_open: int
    required_skills: list[str]


class StatsOut(BaseModel):
    companies_total: int
    companies_watchlist: int
    open_roles: int
    signals_total: int
    signals_last_24h: int
    outreach_due: int
    avg_fit_score: float
    last_ingest: Optional[datetime]


class BriefRequest(BaseModel):
    regenerate: bool = False


class OutreachRequest(BaseModel):
    contact_role: str = "engineering lead"
    specific_angle: str = ""


class WatchlistRequest(BaseModel):
    on_watchlist: bool


class CandidateProfileOut(BaseModel):
    preferredRoles: list[str]
    preferredSkills: list[str]
    preferredStages: list[str]
    remoteOnly: bool
    preferredLocations: list[str]
    targetCompanyIds: list[str] = []
    avoidCompanyIds: list[str] = []


class CandidateProfileUpdate(BaseModel):
    preferredRoles: list[str] = []
    preferredSkills: list[str] = []
    preferredStages: list[str] = []
    remoteOnly: bool = True
    preferredLocations: list[str] = []
    targetCompanyIds: list[str] = []
    avoidCompanyIds: list[str] = []


class ExecutionEventOut(BaseModel):
    id: str
    company_id: str
    status: str
    status_label: str
    label: str
    notes: str
    target_role_title: str
    target_role_url: str
    follow_up_due: Optional[datetime]
    occurred_at: datetime


class ExecutionOut(BaseModel):
    id: str
    company_id: str
    company_name: str
    status: str
    status_label: str
    notes: str
    target_role_title: str
    target_role_url: str
    follow_up_due: Optional[datetime]
    last_event_at: Optional[datetime]
    updated_at: Optional[datetime]
    events: list[ExecutionEventOut] = Field(default_factory=list)


class ExecutionUpdateRequest(BaseModel):
    status: str
    label: str = ""
    notes: str = ""
    target_role_title: str = ""
    target_role_url: str = ""
    follow_up_due: Optional[datetime] = None


# ── Health ─────────────────────────────────────────────────────────


@app.get("/healthz")
async def health():
    db_ok = await check_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "connected" if db_ok else "unreachable",
        "ai_provider": settings.ai_provider,
        "ai_available": settings.ai_available,
        "github_available": settings.github_available,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Stats ──────────────────────────────────────────────────────────


@app.get("/api/stats", response_model=StatsOut)
async def get_stats():
    if not await check_connection():
        return _mock_stats()
    try:
        from hirectl.db.session import get_session
        from hirectl.db.repository import (
            CompanyRepo,
            ExecutionRepo,
            SignalRepo,
            RoleRepo,
            OutreachRepo,
        )

        async with get_session() as session:
            outreach_due = await OutreachRepo(session).count_due()
            execution_due = await ExecutionRepo(session).count_follow_up_due()
            return StatsOut(
                companies_total=await CompanyRepo(session).count(),
                companies_watchlist=await CompanyRepo(session).count_watchlist(),
                open_roles=await RoleRepo(session).count_active(),
                signals_total=await SignalRepo(session).count_total(),
                signals_last_24h=await SignalRepo(session).count_last_24h(),
                outreach_due=outreach_due + execution_due,
                avg_fit_score=0.0,
                last_ingest=datetime.utcnow(),
            )
    except Exception as e:
        logger.warning(f"Stats DB error: {e}")
        return _mock_stats()


# ── Companies ──────────────────────────────────────────────────────


@app.get("/api/companies", response_model=list[CompanyOut])
async def list_companies(
    stage: Optional[str] = Query(None),
    remote_us: Optional[bool] = Query(None),
    min_score: float = Query(0.0),
    role_type: Optional[str] = Query(None),
    watchlist_only: bool = Query(False),
    search: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
):
    if not await check_connection():
        return _mock_companies()
    try:
        from hirectl.db.session import get_session
        from hirectl.db.repository import CompanyRepo, SignalRepo, RoleRepo

        async with get_session() as session:
            companies = await CompanyRepo(session).list_ranked(
                stage=stage,
                remote_us=remote_us,
                min_score=min_score,
                role_type=role_type,
                watchlist_only=watchlist_only,
                limit=limit,
                offset=offset,
            )
            result = []
            for co in companies:
                # Apply search filter
                if search and search.lower() not in co.name.lower():
                    continue

                roles = await RoleRepo(session).list_active(company_id=co.id, limit=20)
                signals = await SignalRepo(session).list_recent(
                    company_id=co.id, limit=10
                )
                result.append(_company_to_out(co, roles, signals))
            return result
    except Exception as e:
        logger.warning(f"Companies DB error: {e}")
        return _mock_companies()


@app.get("/api/companies/{company_id}", response_model=CompanyOut)
async def get_company(company_id: str):
    if not await check_connection():
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        from hirectl.db.session import get_session
        from hirectl.db.repository import CompanyRepo, SignalRepo, RoleRepo

        async with get_session() as session:
            try:
                uid = UUID(company_id)
                company = await CompanyRepo(session).get_by_id(uid)
            except ValueError:
                company = await CompanyRepo(session).get_by_slug(company_id)

            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            roles = await RoleRepo(session).list_active(company_id=company.id, limit=20)
            signals = await SignalRepo(session).list_recent(
                company_id=company.id, limit=20
            )
            return _company_to_out(company, roles, signals)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/companies/{company_id}/brief")
async def generate_brief(
    company_id: str,
    req: BriefRequest,
    background_tasks: BackgroundTasks,
):
    """Generate or return a cached AI intelligence brief."""
    if not await check_connection():
        # Run AI without DB in dev mode
        from hirectl.ai.engine import AIEngine, CompanyContext

        engine = AIEngine()
        ctx = CompanyContext(
            name=company_id.replace("-", " ").title(),
            fit_score=80.0,
            urgency_label="high",
        )
        brief = await engine.generate_brief(ctx)
        return {"brief": brief, "cached": False}

    try:
        from hirectl.db.session import get_session
        from hirectl.db.repository import CompanyRepo
        from hirectl.ai.engine import AIEngine, CompanyContext
        from uuid import UUID

        async with get_session() as session:
            try:
                uid = UUID(company_id)
                company = await CompanyRepo(session).get_by_id(uid)
            except ValueError:
                company = await CompanyRepo(session).get_by_slug(company_id)

            if not company:
                raise HTTPException(status_code=404, detail="Not found")

            # Return cached brief if fresh and not forced regen
            if company.ai_brief and not req.regenerate:
                return {
                    "brief": company.ai_brief,
                    "cached": True,
                    "generated_at": company.ai_brief_generated_at,
                }

            engine = AIEngine()
            ctx = CompanyContext(
                name=company.name,
                description=company.description or "",
                funding_stage=(
                    company.funding_stage.value if company.funding_stage else ""
                ),
                funding_amount=company.funding_amount_usd,
                tech_stack=company.tech_stack or {},
                remote_us=company.remote_us or False,
                headcount=company.headcount,
                fit_score=company.fit_score,
                urgency_score=company.urgency_score,
                urgency_label=(
                    company.urgency.value if hasattr(company, "urgency") else "medium"
                ),
            )

            brief = await engine.generate_brief(ctx)
            await CompanyRepo(session).update_scores(
                company.id,
                fit_score=company.fit_score,
                urgency_score=company.urgency_score,
                composite_score=company.composite_score,
                ai_brief=brief,
            )
            return {"brief": brief, "cached": False, "generated_at": datetime.utcnow()}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/companies/{company_id}/outreach")
async def generate_outreach(company_id: str, req: OutreachRequest):
    """Generate a cold outreach draft."""
    from hirectl.ai.engine import AIEngine, CompanyContext

    engine = AIEngine()

    # Load company context if DB available
    ctx = CompanyContext(
        name=company_id.replace("-", " ").title(),
        fit_score=80.0,
        urgency_label="high",
    )

    if await check_connection():
        try:
            from hirectl.db.session import get_session
            from hirectl.db.repository import CompanyRepo
            from uuid import UUID

            async with get_session() as session:
                try:
                    uid = UUID(company_id)
                    co = await CompanyRepo(session).get_by_id(uid)
                except ValueError:
                    co = await CompanyRepo(session).get_by_slug(company_id)
                if co:
                    ctx = CompanyContext(
                        name=co.name,
                        description=co.description or "",
                        tech_stack=co.tech_stack or {},
                        remote_us=co.remote_us or False,
                        fit_score=co.fit_score,
                        urgency_label="high",
                    )
        except Exception:
            pass

    draft = await engine.generate_outreach_draft(
        company=ctx,
        contact_role=req.contact_role,
        specific_angle=req.specific_angle,
    )
    return {"draft": draft, "generated_at": datetime.utcnow()}


@app.put("/api/companies/{company_id}/watchlist")
async def set_watchlist(company_id: str, req: WatchlistRequest):
    if not await check_connection():
        return {"company_id": company_id, "on_watchlist": req.on_watchlist}
    try:
        from hirectl.db.session import get_session
        from hirectl.db.repository import CompanyRepo
        from uuid import UUID

        async with get_session() as session:
            try:
                uid = UUID(company_id)
            except ValueError:
                co = await CompanyRepo(session).get_by_slug(company_id)
                uid = co.id if co else None
            if uid:
                await CompanyRepo(session).set_watchlist(uid, req.on_watchlist)
        return {"company_id": company_id, "on_watchlist": req.on_watchlist}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Candidate profile ─────────────────────────────────────────────


@app.get("/api/profile", response_model=CandidateProfileOut)
async def get_candidate_profile():
    if not await check_connection():
        return _default_candidate_profile()
    try:
        from hirectl.db.session import get_session
        from hirectl.db.repository import ProfileRepo

        async with get_session() as session:
            profile = await ProfileRepo(session).get()
            if not profile:
                return _default_candidate_profile()
            return _profile_to_out(profile)
    except Exception as e:
        logger.warning(f"Profile DB error: {e}")
        return _default_candidate_profile()


@app.put("/api/profile", response_model=CandidateProfileOut)
async def update_candidate_profile(req: CandidateProfileUpdate):
    if not await check_connection():
        return CandidateProfileOut(**req.model_dump())
    try:
        from hirectl.db.session import get_session
        from hirectl.db.repository import ProfileRepo

        async with get_session() as session:
            profile = await ProfileRepo(session).upsert(
                primary_skills=_dedupe_case_insensitive(req.preferredSkills[:6]),
                secondary_skills=_dedupe_case_insensitive(req.preferredSkills[6:20]),
                domains=_dedupe_case_insensitive(req.preferredRoles),
                preferred_stages=_normalize_stage_list(req.preferredStages),
                preferred_remote=req.remoteOnly,
                preferred_locations=_dedupe_case_insensitive(req.preferredLocations),
            )
            return _profile_to_out(profile)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Execution ledger ──────────────────────────────────────────────


@app.get("/api/execution", response_model=list[ExecutionOut])
async def list_execution(
    company_id: Optional[str] = Query(None),
    limit: int = Query(100, le=200),
):
    if not await check_connection():
        return []
    try:
        from hirectl.db.session import get_session
        from hirectl.db.repository import CompanyRepo, ExecutionRepo
        from uuid import UUID

        async with get_session() as session:
            cid = None
            if company_id:
                try:
                    cid = UUID(company_id)
                except ValueError:
                    co = await CompanyRepo(session).get_by_slug(company_id)
                    cid = co.id if co else None

            records = await ExecutionRepo(session).list(company_id=cid, limit=limit)
            return [_execution_to_out(record) for record in records]
    except Exception as e:
        logger.warning(f"Execution DB error: {e}")
        return []


@app.put("/api/execution/{company_id}", response_model=ExecutionOut)
async def update_execution(company_id: str, req: ExecutionUpdateRequest):
    if not await check_connection():
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        from hirectl.db.session import get_session
        from hirectl.db.repository import CompanyRepo, ExecutionRepo
        from hirectl.db.models import ExecutionStatus
        from uuid import UUID

        try:
            status = ExecutionStatus(req.status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid execution status: {req.status}") from exc

        async with get_session() as session:
            try:
                uid = UUID(company_id)
                company = await CompanyRepo(session).get_by_id(uid)
            except ValueError:
                company = await CompanyRepo(session).get_by_slug(company_id)

            if not company:
                raise HTTPException(status_code=404, detail="Company not found")

            record = await ExecutionRepo(session).upsert(
                company_id=company.id,
                status=status,
                label=req.label,
                notes=req.notes,
                target_role_title=req.target_role_title,
                target_role_url=req.target_role_url,
                follow_up_due=req.follow_up_due,
            )
            return _execution_to_out(record)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Signals ────────────────────────────────────────────────────────


@app.get("/api/signals", response_model=list[SignalOut])
async def list_signals(
    company_id: Optional[str] = Query(None),
    signal_type: Optional[str] = Query(None),
    min_score: float = Query(0.0),
    hours: int = Query(24 * 7),
    limit: int = Query(50, le=200),
):
    if not await check_connection():
        return _mock_signals()
    try:
        from hirectl.db.session import get_session
        from hirectl.db.models import Company
        from hirectl.db.repository import SignalRepo, CompanyRepo
        from uuid import UUID

        async with get_session() as session:
            cid = None
            if company_id:
                try:
                    cid = UUID(company_id)
                except ValueError:
                    co = await CompanyRepo(session).get_by_slug(company_id)
                    cid = co.id if co else None

            signals = await SignalRepo(session).list_recent(
                company_id=cid,
                signal_type=signal_type,
                min_score=min_score,
                hours=hours,
                limit=limit,
            )
            company_ids = list({signal.company_id for signal in signals})
            company_rows = await session.execute(
                select(Company.id, Company.name).where(Company.id.in_(company_ids))
            )
            company_names = {company_id: name for company_id, name in company_rows.all()}
            return [_signal_to_out(s, company_names.get(s.company_id, "")) for s in signals]
    except Exception as e:
        logger.warning(f"Signals DB error: {e}")
        return _mock_signals()


@app.get("/api/signals/stream")
async def stream_signals(request: Request):
    queue = await signal_stream_broker.subscribe()

    async def event_stream():
        try:
            yield "event: ready\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: signal\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
        finally:
            await signal_stream_broker.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Roles ──────────────────────────────────────────────────────────


@app.get("/api/roles", response_model=list[RoleOut])
async def list_roles(
    company_id: Optional[str] = Query(None),
    role_type: Optional[str] = Query(None),
    remote_us: Optional[bool] = Query(None),
    min_fit: float = Query(0.0),
    limit: int = Query(50),
):
    if not await check_connection():
        return []
    try:
        from hirectl.db.session import get_session
        from hirectl.db.models import Company
        from hirectl.db.repository import RoleRepo, CompanyRepo
        from uuid import UUID

        async with get_session() as session:
            cid = None
            if company_id:
                try:
                    cid = UUID(company_id)
                except ValueError:
                    co = await CompanyRepo(session).get_by_slug(company_id)
                    cid = co.id if co else None

            roles = await RoleRepo(session).list_active(
                company_id=cid,
                role_type=role_type,
                remote_us=remote_us,
                min_fit=min_fit,
                limit=limit,
            )
            company_ids = list({role.company_id for role in roles})
            company_rows = await session.execute(
                select(Company.id, Company.name).where(Company.id.in_(company_ids))
            )
            company_names = {company_id: name for company_id, name in company_rows.all()}
            return [_role_to_out(r, company_names.get(r.company_id, "")) for r in roles]
    except Exception as e:
        logger.warning(f"Roles DB error: {e}")
        return []


# ── Admin triggers ─────────────────────────────────────────────────


async def run_ingest_now(source: Optional[str] = None) -> dict:
    from hirectl.ingestion.yc_jobs import YCJobsAdapter
    from hirectl.ingestion.greenhouse import GreenhouseAdapter
    from hirectl.ingestion.ashby import AshbyAdapter
    from hirectl.ingestion.github_watcher import GitHubWatcher
    from hirectl.ingestion.funding import FundingFeedAdapter
    from hirectl.ingestion.career_page import CareerPageCrawler
    from hirectl.ingestion.portfolio_boards import PortfolioBoardsAdapter
    from hirectl.ingestion.social import SocialSignalAdapter
    from hirectl.ingestion.service import IngestionService

    adapters = {
        "yc_jobs": YCJobsAdapter,
        "greenhouse": GreenhouseAdapter,
        "ashby": AshbyAdapter,
        "github": GitHubWatcher,
        "funding": FundingFeedAdapter,
        "career_page": CareerPageCrawler,
        "portfolio_boards": PortfolioBoardsAdapter,
        "social": SocialSignalAdapter,
    }

    if source and source not in adapters:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}")

    to_run = {source: adapters[source]} if source else adapters
    results = {}
    service = IngestionService()

    for name, cls in to_run.items():
        adapter = cls()
        result = await adapter.run()
        summary = await service.process(result)
        results[name] = summary

    return {"triggered_at": datetime.utcnow(), "results": results}


@app.post("/api/admin/ingest", dependencies=[Depends(require_admin)])
async def trigger_admin_ingest(source: Optional[str] = Query(None)):
    return await run_ingest_now(source)


@app.post("/api/ingest/run", dependencies=[Depends(require_admin)])
async def trigger_ingest(source: Optional[str] = Query(None)):
    return await run_ingest_now(source)


async def run_automation_now() -> dict:
    from hirectl.automation.service import AutomationService

    summary = await AutomationService().run()
    return {"triggered_at": datetime.utcnow(), "summary": summary}


@app.post("/api/admin/automate", dependencies=[Depends(require_admin)])
async def trigger_admin_automation():
    return await run_automation_now()


@app.post("/api/automation/run", dependencies=[Depends(require_admin)])
async def trigger_automation():
    return await run_automation_now()


@app.post("/api/admin/model-refresh", dependencies=[Depends(require_admin)])
async def trigger_admin_model_refresh():
    from hirectl.ingestion.service import IngestionService

    summary = await IngestionService().refresh_all_company_scores()
    return {"triggered_at": datetime.utcnow(), "summary": summary}


# ── Helpers ────────────────────────────────────────────────────────


def _company_to_out(company, roles, signals) -> CompanyOut:
    """Convert ORM Company to API response model."""
    stage = company.funding_stage.value if company.funding_stage else "unknown"
    amt = company.funding_amount_usd
    funding_label = ""
    if amt:
        funding_label = f"${amt/1e6:.0f}M {stage}"
    elif stage and stage != "unknown":
        funding_label = stage.replace("_", " ").title()

    chips = []
    if funding_label:
        chips.append({"label": funding_label, "variant": "gold"})
    if company.remote_us:
        chips.append({"label": "Remote US", "variant": "green"})
    stack = company.tech_stack or {}
    if stack.get("languages"):
        chips.append(
            {
                "label": " · ".join(stack["languages"][:3]),
                "variant": "blue",
            }
        )

    role_desc_parts = []
    if roles:
        role_desc_parts.append(
            f"{len(roles)} target-role opening{'s' if len(roles) != 1 else ''}"
        )
    if company.description:
        role_desc_parts.append(company.description[:120])

    return CompanyOut(
        id=str(company.id),
        name=company.name,
        slug=company.slug,
        tagline=company.tagline or "",
        stage=stage,
        funding_amount=amt,
        funding_label=funding_label,
        remote_us=company.remote_us or False,
        remote_label="Remote US" if company.remote_us else "On-site",
        fit_score=company.fit_score or 0.0,
        urgency_score=company.urgency_score or 0.0,
        composite_score=company.composite_score or 0.0,
        urgency_label=_urgency_label(company.urgency_score or 0.0),
        open_roles_count=len(roles),
        signal_count=len(signals),
        tech_stack=company.tech_stack or {},
        chips=chips,
        description=" · ".join(role_desc_parts),
        ai_brief=company.ai_brief,
        on_watchlist=company.on_watchlist or False,
        last_signal_at=company.last_signal_at,
    )


def _signal_to_out(signal, company_name: str = "") -> SignalOut:
    type_val = signal.type.value if hasattr(signal.type, "value") else str(signal.type)
    score = signal.score or 0.0
    payload = signal_payload_from_model(signal, company_name)
    return SignalOut(
        id=payload["id"],
        company_id=payload["company_id"],
        company_name=payload["company_name"],
        type=type_val,
        type_label=TYPE_LABELS.get(type_val, type_val.replace("_", " ").title()),
        headline=payload["headline"],
        detail=payload["detail"],
        score=score,
        score_variant=score_variant(score),
        signal_date=signal.signal_date,
        source_url=payload["source_url"],
    )


def _role_to_out(role, company_name: str = "") -> RoleOut:
    return RoleOut(
        id=str(role.id),
        company_id=str(role.company_id),
        company_name=company_name,
        title=role.title,
        url=role.url,
        role_type=role.role_type.value if role.role_type else "unknown",
        seniority=role.seniority or "unknown",
        is_remote=role.is_remote or False,
        is_remote_us=role.is_remote_us or False,
        location=role.location or "",
        fit_score=role.fit_score or 0.0,
        days_open=role.days_open or 0,
        required_skills=role.required_skills or [],
    )


def _urgency_label(score: float) -> str:
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def _dedupe_case_insensitive(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        candidate = value.strip()
        if not candidate:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(candidate)
    return normalized


def _stage_to_api(value: str) -> str:
    return value.replace("_", " ").strip().lower()


def _stage_from_api(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _normalize_stage_list(values: list[str]) -> list[str]:
    normalized = [_stage_from_api(value) for value in values if value.strip()]
    return _dedupe_case_insensitive(normalized)


def _default_candidate_profile() -> CandidateProfileOut:
    return CandidateProfileOut(
        preferredRoles=["backend", "distributed", "infra", "platform", "ai_ml"],
        preferredSkills=[
            "python",
            "typescript",
            "node",
            "postgres",
            "docker",
            "kubernetes",
            "aws",
            "fastapi",
            "react",
        ],
        preferredStages=["seed", "series a", "series b", "series c"],
        remoteOnly=True,
        preferredLocations=["remote"],
        targetCompanyIds=[],
        avoidCompanyIds=[],
    )


def _profile_to_out(profile) -> CandidateProfileOut:
    skills = _dedupe_case_insensitive(
        list(profile.primary_skills or []) + list(profile.secondary_skills or [])
    )
    roles = _dedupe_case_insensitive(list(profile.domains or []))
    stages = [_stage_to_api(stage) for stage in list(profile.preferred_stages or [])]
    locations = _dedupe_case_insensitive(list(profile.preferred_locations or []))

    return CandidateProfileOut(
        preferredRoles=roles or _default_candidate_profile().preferredRoles,
        preferredSkills=skills or _default_candidate_profile().preferredSkills,
        preferredStages=stages or _default_candidate_profile().preferredStages,
        remoteOnly=profile.preferred_remote if profile.preferred_remote is not None else True,
        preferredLocations=locations or (["remote"] if profile.preferred_remote else []),
        targetCompanyIds=[],
        avoidCompanyIds=[],
    )


def _execution_status_label(status: str) -> str:
    mapping = {
        "tracking": "Tracking",
        "reached_out": "Reached out",
        "applied": "Applied",
        "follow_up": "Follow-up due",
        "interview": "Interview",
        "offer": "Offer",
        "closed": "Closed",
    }
    return mapping.get(status, status.replace("_", " ").title())


def _execution_event_to_out(event) -> ExecutionEventOut:
    status = event.status.value if hasattr(event.status, "value") else str(event.status)
    return ExecutionEventOut(
        id=str(event.id),
        company_id=str(event.company_id),
        status=status,
        status_label=_execution_status_label(status),
        label=event.label or _execution_status_label(status),
        notes=event.notes or "",
        target_role_title=event.target_role_title or "",
        target_role_url=event.target_role_url or "",
        follow_up_due=event.follow_up_due,
        occurred_at=event.occurred_at,
    )


def _execution_to_out(record) -> ExecutionOut:
    status = record.status.value if hasattr(record.status, "value") else str(record.status)
    company = getattr(record, "company", None)
    events = sorted(
        list(record.events or []),
        key=lambda event: event.occurred_at or datetime.utcnow(),
        reverse=True,
    )
    return ExecutionOut(
        id=str(record.id),
        company_id=str(record.company_id),
        company_name=company.name if company else "",
        status=status,
        status_label=_execution_status_label(status),
        notes=record.notes or "",
        target_role_title=record.target_role_title or "",
        target_role_url=record.target_role_url or "",
        follow_up_due=record.follow_up_due,
        last_event_at=record.last_event_at,
        updated_at=record.updated_at,
        events=[_execution_event_to_out(event) for event in events[:12]],
    )


# ── Mock data (dev without DB) ─────────────────────────────────────


def _mock_stats() -> StatsOut:
    return StatsOut(
        companies_total=34,
        companies_watchlist=8,
        open_roles=127,
        signals_total=847,
        signals_last_24h=12,
        outreach_due=6,
        avg_fit_score=81.0,
        last_ingest=datetime.utcnow(),
    )


def _mock_companies() -> list[CompanyOut]:
    from uuid import uuid4

    rows = [
        (
            "Baseten",
            "ML Inference Infrastructure",
            "series_b",
            85e6,
            True,
            94.0,
            88.0,
            "critical",
            3,
            6,
            {
                "languages": ["Go", "Python"],
                "frameworks": ["gRPC"],
                "infra": ["CUDA", "K8s"],
            },
        ),
        (
            "Modal Labs",
            "Serverless GPU Compute",
            "series_b",
            67e6,
            True,
            91.0,
            92.0,
            "critical",
            2,
            5,
            {
                "languages": ["Python"],
                "frameworks": ["gRPC"],
                "infra": ["GPU", "Firecracker"],
            },
        ),
        (
            "Turso",
            "Edge SQLite / Distributed DB",
            "seed",
            None,
            True,
            88.0,
            75.0,
            "high",
            1,
            4,
            {"languages": ["Rust", "C"], "frameworks": ["libSQL"], "infra": ["Edge"]},
        ),
        (
            "Fly.io",
            "Global Edge Platform",
            "series_a",
            None,
            True,
            84.0,
            55.0,
            "medium",
            2,
            3,
            {"languages": ["Rust", "Go"], "frameworks": ["Anycast"], "infra": ["BGP"]},
        ),
        (
            "Inngest",
            "Workflow / Event-Driven Infra",
            "seed",
            None,
            True,
            79.0,
            48.0,
            "medium",
            1,
            3,
            {
                "languages": ["TypeScript", "Go"],
                "frameworks": [],
                "infra": ["Queues", "Redis"],
            },
        ),
        (
            "Zed Industries",
            "Collaborative Code Editor",
            "unknown",
            None,
            True,
            71.0,
            30.0,
            "low",
            2,
            2,
            {"languages": ["Rust"], "frameworks": ["CRDT"], "infra": ["WebRTC"]},
        ),
    ]
    out = []
    for (
        name,
        tagline,
        stage,
        amt,
        remote,
        fit,
        urg,
        urg_lbl,
        roles,
        sigs,
        stack,
    ) in rows:
        chips = []
        if amt:
            chips.append(
                {
                    "label": f"${amt/1e6:.0f}M {stage.replace('_',' ').title()}",
                    "variant": "gold",
                }
            )
        if remote:
            chips.append({"label": "Remote US", "variant": "green"})
        if stack.get("languages"):
            chips.append(
                {"label": " · ".join(stack["languages"][:3]), "variant": "blue"}
            )

        out.append(
            CompanyOut(
                id=str(uuid4()),
                name=name,
                slug=name.lower().replace(" ", "-"),
                tagline=tagline,
                stage=stage,
                funding_amount=amt,
                funding_label=f"${amt/1e6:.0f}M {stage}" if amt else stage,
                remote_us=remote,
                remote_label="Remote US" if remote else "On-site",
                fit_score=fit,
                urgency_score=urg,
                composite_score=round(fit * 0.6 + urg * 0.4, 1),
                urgency_label=urg_lbl,
                open_roles_count=roles,
                signal_count=sigs,
                tech_stack=stack,
                chips=chips,
                description=f"{roles} target-role opening{'s' if roles != 1 else ''} · {tagline}",
                ai_brief=None,
                on_watchlist=False,
                last_signal_at=datetime.utcnow(),
            )
        )
    return out


def _mock_signals() -> list[SignalOut]:
    from uuid import uuid4

    rows = [
        (
            "Modal Labs",
            "funding",
            "Funding Event",
            "Closed $67M Series B — doubled engineering headcount planned",
            91.0,
        ),
        (
            "Turso",
            "founder_post",
            "Founder Post",
            "Founder posted urgent need for systems engineers — not yet on ATS",
            88.0,
        ),
        (
            "Baseten",
            "ats_greenhouse",
            "ATS — Greenhouse",
            "Three new engineering roles posted simultaneously — batch posting",
            94.0,
        ),
        (
            "Fly.io",
            "github_spike",
            "GitHub Activity",
            "47 commits / 72h — new infra repository opened",
            76.0,
        ),
        (
            "Inngest",
            "career_page",
            "Career Page Diff",
            "Backend Engineer (AI integrations) — direct listing, not syndicated",
            72.0,
        ),
        (
            "Zed Industries",
            "career_page",
            "Career Page",
            "Distributed Systems Engineer — Rust, CRDT, remote-only",
            60.0,
        ),
    ]
    return [
        SignalOut(
            id=str(uuid4()),
            company_id=str(uuid4()),
            company_name=co,
            type=t,
            type_label=tl,
            headline=h,
            detail="Captured from public source.",
            score=score,
            score_variant="high" if score >= 75 else "medium" if score >= 50 else "low",
            signal_date=datetime.utcnow(),
            source_url="",
        )
        for co, t, tl, h, score in rows
    ]
