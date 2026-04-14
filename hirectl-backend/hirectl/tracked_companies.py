from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TrackedCompany:
    name: str
    website: str = ""
    career_page_url: str = ""
    greenhouse_token: str = ""
    ashby_slug: str = ""
    github_org: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TrackedPortfolioBoard:
    name: str
    board_url: str
    provider: str = "generic"
    board_id: str = ""
    is_parent: bool = False
    page_size: int = 100
    aliases: tuple[str, ...] = field(default_factory=tuple)


TRACKED_COMPANIES: list[TrackedCompany] = [
    TrackedCompany(
        name="Baseten",
        website="https://www.baseten.co",
        career_page_url="https://www.baseten.co/careers",
        ashby_slug="baseten",
        github_org="basetenlabs",
        aliases=("baseten",),
    ),
    TrackedCompany(
        name="Modal Labs",
        website="https://modal.com",
        career_page_url="https://modal.com/careers",
        ashby_slug="modal",
        aliases=("modal", "modal labs"),
    ),
    TrackedCompany(
        name="Turso",
        website="https://turso.tech",
        career_page_url="https://turso.tech/careers",
        ashby_slug="chiselstrike",
        github_org="tursodatabase",
        aliases=("turso", "libsql"),
    ),
    TrackedCompany(
        name="Fly.io",
        website="https://fly.io",
        career_page_url="https://fly.io/jobs",
        ashby_slug="fly-io",
        github_org="superfly",
        aliases=("fly", "fly.io", "fly io"),
    ),
    TrackedCompany(
        name="Inngest",
        website="https://www.inngest.com",
        career_page_url="https://www.inngest.com/careers",
        ashby_slug="inngest",
        github_org="inngest",
        aliases=("inngest",),
    ),
    TrackedCompany(
        name="Zed Industries",
        website="https://zed.dev",
        career_page_url="https://zed.dev/jobs",
        ashby_slug="zed",
        github_org="zed-industries",
        aliases=("zed", "zed industries"),
    ),
    TrackedCompany(
        name="Render",
        website="https://render.com",
        career_page_url="https://render.com/careers",
        ashby_slug="render",
        github_org="renderinc",
        aliases=("render", "render.com"),
    ),
    TrackedCompany(
        name="Neon",
        website="https://neon.tech",
        ashby_slug="neon",
        github_org="neondatabase",
        aliases=("neon", "neon tech"),
    ),
    TrackedCompany(
        name="PlanetScale",
        website="https://planetscale.com",
        career_page_url="https://planetscale.com/careers",
        greenhouse_token="planetscale",
        github_org="planetscale",
        aliases=("planetscale",),
    ),
    TrackedCompany(
        name="Railway",
        website="https://railway.com",
        career_page_url="https://railway.app/careers",
        ashby_slug="railway",
        aliases=("railway", "railway.app"),
    ),
    TrackedCompany(
        name="Temporal",
        website="https://temporal.io",
        career_page_url="https://temporal.io/careers",
        greenhouse_token="temporal",
        github_org="temporalio",
        aliases=("temporal", "temporal.io"),
    ),
    TrackedCompany(
        name="Dagger",
        website="https://dagger.io",
        career_page_url="https://dagger.io/careers",
        greenhouse_token="dagger",
        github_org="dagger-io",
        aliases=("dagger", "dagger.io"),
    ),
    TrackedCompany(
        name="Replicate",
        website="https://replicate.com",
        career_page_url="https://www.cloudflare.com/careers/jobs/",
        ashby_slug="replicate",
        github_org="replicate",
        aliases=("replicate",),
    ),
    TrackedCompany(
        name="Together AI",
        website="https://www.together.ai",
        career_page_url="https://www.together.ai/careers#roles",
        ashby_slug="together-ai",
        github_org="togethercomputer",
        aliases=("together", "together ai"),
    ),
    TrackedCompany(
        name="Groq",
        website="https://groq.com",
        career_page_url="https://jobs.gem.com/groq?jr_id=695c4ee9f1f8465b79f26b8b",
        ashby_slug="groq",
        aliases=("groq",),
    ),
    TrackedCompany(
        name="Mistral AI",
        website="https://mistral.ai",
        ashby_slug="mistral",
        aliases=("mistral", "mistral ai"),
    ),
    TrackedCompany(
        name="Cohere",
        website="https://cohere.com",
        ashby_slug="cohere",
        aliases=("cohere",),
    ),
    TrackedCompany(
        name="Weaviate",
        website="https://weaviate.io",
        career_page_url="https://weaviate.io/company/careers",
        ashby_slug="weaviate",
        github_org="weaviate",
        aliases=("weaviate",),
    ),
    TrackedCompany(
        name="Qdrant",
        website="https://qdrant.tech",
        ashby_slug="qdrant",
        github_org="qdrant",
        aliases=("qdrant",),
    ),
    TrackedCompany(
        name="Warpstream",
        website="https://www.warpstream.com",
        career_page_url="https://careers.confluent.io/jobs",
        ashby_slug="warpstream",
        aliases=("warpstream",),
    ),
    TrackedCompany(
        name="Tinybird",
        website="https://www.tinybird.co",
        career_page_url="https://www.tinybird.co/about#careers",
        ashby_slug="tinybird",
        aliases=("tinybird",),
    ),
    TrackedCompany(
        name="Buf",
        website="https://buf.build",
        ashby_slug="buf",
        aliases=("buf", "buf build"),
    ),
    TrackedCompany(
        name="LlamaIndex",
        website="https://www.llamaindex.ai",
        ashby_slug="llamaindex",
        github_org="run-llama",
        aliases=("llamaindex", "llama index"),
    ),
    TrackedCompany(
        name="Anyscale",
        website="https://www.anyscale.com",
        career_page_url="https://www.anyscale.com/careers",
        ashby_slug="anyscale",
        github_org="ray-project",
        aliases=("anyscale",),
    ),
    TrackedCompany(
        name="Convex",
        website="https://www.convex.dev",
        career_page_url="https://www.convex.dev/jobs",
        ashby_slug="convex",
        github_org="get-convex",
        aliases=("convex",),
    ),
    TrackedCompany(
        name="Grafbase",
        website="https://grafbase.com",
        ashby_slug="grafbase",
        github_org="grafbase",
        aliases=("grafbase",),
    ),
    TrackedCompany(
        name="Deno",
        website="https://deno.com",
        ashby_slug="deno",
        aliases=("deno",),
    ),
    TrackedCompany(
        name="PartyKit",
        website="https://www.partykit.io",
        ashby_slug="partykit",
        aliases=("partykit", "partykit"),
    ),
    TrackedCompany(
        name="Supabase",
        website="https://supabase.com",
        career_page_url="https://supabase.com/careers",
        ashby_slug="supabase",
        github_org="supabase",
        aliases=("supabase",),
    ),
    TrackedCompany(
        name="PolyMarket",
        website="https://polymarket.com",
        ashby_slug="polymarket",
        aliases=("polymarket", "poly market"),
    ),
    TrackedCompany(
        name="Applied Compute",
        website="https://appliedcompute.ai",
        career_page_url="https://jobs.ashbyhq.com/Applied%20Compute",
        ashby_slug="Applied%20Compute",
        aliases=("applied compute",),
    ),
    TrackedCompany(
        name="Vercel",
        website="https://vercel.com",
        career_page_url="https://vercel.com/careers",
        github_org="vercel",
        aliases=("vercel",),
    ),
    TrackedCompany(
        name="Cloudflare",
        website="https://www.cloudflare.com",
        career_page_url="https://www.cloudflare.com/careers/",
        github_org="cloudflare",
        aliases=("cloudflare",),
    ),
    TrackedCompany(
        name="Cockroach Labs",
        website="https://www.cockroachlabs.com",
        career_page_url="https://www.cockroachlabs.com/careers/",
        github_org="cockroachdb",
        aliases=("cockroach", "cockroach labs", "cockroachdb"),
    ),
    TrackedCompany(
        name="Astral",
        website="https://astral.sh",
        github_org="astral-sh",
        aliases=("astral",),
    ),
    TrackedCompany(
        name="Sourcegraph",
        website="https://sourcegraph.com",
        career_page_url="https://sourcegraph.com/careers",
        github_org="sourcegraph",
        aliases=("sourcegraph",),
    ),
    TrackedCompany(
        name="Dagster",
        website="https://dagster.io",
        github_org="dagster-io",
        aliases=("dagster",),
    ),
    TrackedCompany(
        name="dbt Labs",
        website="https://www.getdbt.com",
        github_org="dbt-labs",
        aliases=("dbt", "dbt labs"),
    ),
    TrackedCompany(
        name="ClickHouse",
        website="https://clickhouse.com",
        career_page_url="https://clickhouse.com/company/careers",
        github_org="ClickHouse",
        aliases=("clickhouse",),
    ),
    TrackedCompany(
        name="Bun",
        website="https://bun.sh",
        aliases=("bun",),
    ),
    TrackedCompany(
        name="StackBitz",
        website="https://stackblitz.com/",
        career_page_url="https://job-boards.greenhouse.io/stackblitz",
        aliases=("stackbitz", "bolt.new"),
    ),
    TrackedCompany(
        name="Notion",
        website="https://www.notion.com",
        career_page_url="https://www.notion.com/careers",
        ashby_slug="notion",
        github_org="notion",
        aliases=("Notion",),
    ),
    TrackedCompany(
        name="ElevenLabs",
        website="https://www.elevenlabs.com",
        career_page_url="https://elevenlabs.io/careers",
        ashby_slug="elevenlabs",
        github_org="elevenlabs",
        aliases=("Elevenlabs",),
    ),
    TrackedCompany(
        name="AfterQuery",
        website="https://www.afterquery.com/",
        career_page_url="https://www.afterquery.com/careers",
        ashby_slug="AfterQuery",
        github_org="afterquery",
        aliases=("AfterQuery",),
    ),
    TrackedCompany(
        name="ReadMe",
        website="https://readme.com/",
        career_page_url="https://readme.com/careers",
        ashby_slug="readme",
        github_org="ReadMe",
        aliases=("ReadMe",),
    ),
    TrackedCompany(
        name="Tradeify",
        website="https://www.tradeify.com/",
        career_page_url="https://tradeify.co/careers",
        ashby_slug="tradeify",
        github_org="tradeify",
        aliases=("Tradeify",),
    ),
    TrackedCompany(
        name="Owner",
        website="https://www.owner.com/",
        career_page_url="https://owner.com/careers",
        ashby_slug="Owner",
        github_org="owner",
        aliases=("Owner",),
    ),
    TrackedCompany(
        name="Runway",
        website="https://runwayml.com/",
        career_page_url="https://runwayml.com/careers",
        ashby_slug="runway-ml",
        github_org="runway-ml",
        aliases=("Runway",),
    ),
     TrackedCompany(
        name="Ambrook",
        website="https://ambrook.com/",
        career_page_url="https://ambrook.com/careers",
        ashby_slug="ambrook",
        github_org="ambrook",
        aliases=("Ambrook",),
    ),
]


TRACKED_PORTFOLIO_BOARDS: list[TrackedPortfolioBoard] = [
    TrackedPortfolioBoard(
        name="a16z Jobs",
        board_url="https://jobs.a16z.com/jobs",
        provider="consider",
        board_id="andreessen-horowitz",
        is_parent=True,
        page_size=100,
        aliases=("a16z", "andreessen horowitz", "andreessen", "a16z jobs"),
    ),
]


def tracked_greenhouse_companies() -> list[tuple[str, str]]:
    return [
        (company.name, company.greenhouse_token)
        for company in TRACKED_COMPANIES
        if company.greenhouse_token
    ]


def tracked_ashby_companies() -> list[tuple[str, str]]:
    return [
        (company.name, company.ashby_slug)
        for company in TRACKED_COMPANIES
        if company.ashby_slug
    ]


def tracked_career_pages() -> list[tuple[str, str]]:
    return [
        (company.name, company.career_page_url)
        for company in TRACKED_COMPANIES
        if company.career_page_url
    ]


def tracked_github_orgs() -> list[tuple[str, str]]:
    return [
        (company.name, company.github_org)
        for company in TRACKED_COMPANIES
        if company.github_org
    ]


def tracked_discovery_candidates() -> list[dict[str, str]]:
    return [
        {
            "name": company.name,
            "website": company.website,
            "career_page_url": company.career_page_url,
        }
        for company in TRACKED_COMPANIES
        if company.website or company.career_page_url
    ]


def tracked_company_aliases() -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {}
    for company in TRACKED_COMPANIES:
        generated = {
            company.name.lower(),
            company.name.lower().replace(".", ""),
            company.name.lower().replace(".", " ").replace("-", " "),
        }
        generated.update(alias.lower() for alias in company.aliases)
        aliases[company.name] = sorted(alias for alias in generated if alias)
    return aliases


def tracked_portfolio_boards() -> list[TrackedPortfolioBoard]:
    return TRACKED_PORTFOLIO_BOARDS.copy()
