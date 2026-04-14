"""
Funding feed ingestion.

Sources:
  1. Crunchbase API (primary) — structured funding data, requires API key
  2. SEC Form D quarterly datasets (supplemental structured source)
  3. Structured startup directories and funding-news pages (supplemental)
  4. TechCrunch / Axios RSS (fallback)

Funding events are the highest-urgency signal in the system:
a Series A/B close almost always precedes an engineering hiring wave.
"""

import csv
import io
import logging
import re
import zipfile
from html import unescape
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import urljoin
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from hirectl.config import settings
from hirectl.ingestion.base import (
    BaseIngestionAdapter,
    CompanyResult,
    IngestResult,
    SignalResult,
    SignalType,
    make_client,
)
from hirectl.db.models import FundingStage

logger = logging.getLogger(__name__)

TECHCRUNCH_MAIN_RSS = "https://techcrunch.com/feed/"
SEC_FORM_D_DATASETS_PAGE = "https://www.sec.gov/data-research/sec-markets-data/form-d-data-sets"
CRUNCHBASE_API = "https://api.crunchbase.com/api/v4"
TOPSTARTUPS_SERIES_B_URL = "https://topstartups.io/?funding_round=Series+B"
TOPSTARTUPS_SEED_URL = "https://topstartups.io/?funding_round=Seed"
FUNDRAISE_INSIDER_SERIES_B_URL = "https://fundraiseinsider.com/blog/series-b-startups/"
FUNDRAISE_INSIDER_SEED_URL = "https://fundraiseinsider.com/blog/seed-startups/"
PYMNTS_HOME_URL = "https://www.pymnts.com/"
CRESCENDO_AI_FUNDING_URL = "https://www.crescendo.ai/news/latest-vc-investment-deals-in-ai-startups"
CRUNCHBASE_NEWS_URL = "https://news.crunchbase.com/"

# Keywords that indicate engineering-relevant funding
RELEVANT_INVESTOR_KEYWORDS = [
    "a16z", "andreessen", "sequoia", "benchmark", "accel",
    "yc", "y combinator", "lightspeed", "general catalyst",
    "index ventures", "greylock", "kleiner", "bessemer",
    "founders fund", "tiger global", "coatue", "insight",
]

TECH_COMPANY_SIGNALS = [
    "ai", "ml", "infrastructure", "platform", "developer tools",
    "devtools", "database", "api", "backend", "cloud", "security",
    "data", "analytics", "fintech", "b2b", "saas", "open source",
]


class FundingFeedAdapter(BaseIngestionAdapter):
    """
    Ingests recent funding events and scores them by relevance
    to backend/AI/infra engineering hiring.
    """

    source_name = "funding"

    async def fetch(self) -> IngestResult:
        result = IngestResult(source=self.source_name)
        records_before = result.total_records
        self._seen_company_names: set[str] = set()
        self._seen_funding_events: set[tuple[str, str, int, str]] = set()

        # Try Crunchbase first when configured, but do not let one bad API key or
        # schema issue zero out the entire funding ingest.
        if self._has_valid_crunchbase_key():
            await self._fetch_crunchbase(result)
        elif settings.crunchbase_api_key:
            logger.warning("Crunchbase API key is not valid ASCII; skipping Crunchbase")

        if settings.sec_form_d_enabled:
            await self._fetch_sec_form_d(result)

        await self._fetch_topstartups_pages(result)
        await self._fetch_fundraise_insider_pages(result)
        await self._fetch_crescendo_ai_funding_page(result)
        await self._fetch_crunchbase_news_homepage(result)
        await self._fetch_pymnts_homepage(result)

        if result.total_records == records_before:
            await self._fetch_techcrunch_rss(result)
            await self._fetch_axios_rss(result)

        return result

    async def _fetch_sec_form_d(self, result: IngestResult) -> None:
        """Pull recent offerings from the latest SEC Form D quarterly dataset."""
        if not settings.sec_user_agent.strip():
            logger.info("SEC Form D skipped: SEC_USER_AGENT is not configured")
            return

        try:
            page_html = await self._sec_get_text(SEC_FORM_D_DATASETS_PAGE)
            dataset_url = self._extract_latest_sec_zip_url(page_html)
            if not dataset_url:
                logger.warning("SEC Form D dataset page did not expose a ZIP download")
                return
            archive_bytes = await self._sec_get_bytes(dataset_url)
            rows = self._parse_sec_form_d_rows(archive_bytes)
        except Exception as e:
            logger.warning(f"SEC Form D fetch failed: {e}")
            return

        cutoff = datetime.utcnow() - timedelta(days=120)
        seen_companies: set[str] = set()

        for row in rows:
            try:
                company_name = self._sec_value(
                    row,
                    "primaryIssuerEntityName",
                    "issuerName",
                    "entityName",
                    "entity_name",
                    "nameOfIssuer",
                )
                if not company_name:
                    continue

                filing_date = self._parse_sec_date(
                    self._sec_value(
                        row,
                        "dateOfFirstSale",
                        "dateOfFirstSaleValue",
                        "filingDate",
                        "submissionDate",
                    )
                )
                if filing_date and filing_date < cutoff:
                    continue
                if filing_date is None:
                    filing_date = datetime.utcnow()

                amount_offered = self._parse_money(
                    self._sec_value(
                        row,
                        "totalOfferingAmount",
                        "totalOfferingAmountValue",
                        "offeringAmount",
                    )
                )
                amount_sold = self._parse_money(
                    self._sec_value(
                        row,
                        "totalAmountSold",
                        "totalAmountSoldValue",
                        "amountSold",
                    )
                )
                amount_usd = amount_sold or amount_offered
                if amount_usd is None or amount_usd < 5_000_000:
                    continue

                context = " ".join(
                    filter(
                        None,
                        [
                            company_name,
                            self._sec_value(row, "industryGroupType", "industry_group_type"),
                            self._sec_value(row, "industryGroupDescription", "industry_group_description"),
                            self._sec_value(row, "issuerSizeRevenueRange", "revenueRange"),
                        ],
                    )
                )
                score = self._score_funding_event(amount_usd, "private offering", context)
                if score < 35:
                    continue

                if company_name.lower() not in seen_companies:
                    result.companies.append(
                        CompanyResult(
                            name=company_name,
                            funding_stage=FundingStage.UNKNOWN,
                            funding_amount_usd=amount_usd,
                            last_funding_date=filing_date,
                            description=self._sec_value(
                                row,
                                "industryGroupDescription",
                                "industryGroupType",
                                "industry_group_description",
                            ),
                        )
                    )
                    seen_companies.add(company_name.lower())

                detail_bits = ["Source: SEC Form D quarterly dataset."]
                if amount_sold and amount_offered and amount_sold != amount_offered:
                    detail_bits.append(
                        f"Reported ${amount_sold/1_000_000:.0f}M sold of ${amount_offered/1_000_000:.0f}M offered."
                    )
                else:
                    detail_bits.append("Private offering reported through Regulation D.")

                result.signals.append(
                    SignalResult(
                        company_name=company_name,
                        type=SignalType.FUNDING,
                        headline=self._format_headline(company_name, amount_usd, "private offering"),
                        detail=" ".join(detail_bits),
                        source_url=dataset_url,
                        signal_date=filing_date,
                        score=score,
                        funding_amount_usd=amount_usd,
                        funding_round="private offering",
                    )
                )
            except Exception as e:
                logger.debug(f"Failed to parse SEC Form D row: {e}")

    async def _sec_get_text(self, url: str) -> str:
        async with make_client(timeout=30.0) as client:
            client.headers["User-Agent"] = settings.sec_user_agent.strip()
            client.headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    async def _sec_get_bytes(self, url: str) -> bytes:
        async with make_client(timeout=60.0) as client:
            client.headers["User-Agent"] = settings.sec_user_agent.strip()
            client.headers["Accept"] = "application/zip,application/octet-stream,*/*"
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    def _extract_latest_sec_zip_url(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        for link in soup.select("a[href]"):
            label = " ".join(link.get_text(" ", strip=True).split())
            href = link.get("href", "")
            if re.match(r"^\d{4}\s+Q[1-4]$", label) and href:
                return urljoin(SEC_FORM_D_DATASETS_PAGE, href)
        for link in soup.select("a[href$='.zip']"):
            href = link.get("href", "")
            if href:
                return urljoin(SEC_FORM_D_DATASETS_PAGE, href)
        return ""

    def _parse_sec_form_d_rows(self, archive_bytes: bytes) -> list[dict[str, str]]:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
            tables: list[list[dict[str, str]]] = []
            for name in zf.namelist():
                lower = name.lower()
                if not lower.endswith((".csv", ".tsv", ".txt")):
                    continue
                if "readme" in lower or "doc" in lower:
                    continue
                rows = self._read_tabular_rows(zf, name)
                if rows:
                    tables.append(rows)

        if not tables:
            return []

        for rows in tables:
            sample_keys = {self._normalize_key(k) for k in rows[0].keys()}
            has_name = any("issuer" in key or "entity" in key for key in sample_keys)
            has_amount = any("amount" in key for key in sample_keys)
            if has_name and has_amount:
                return rows

        return max(tables, key=len)

    def _read_tabular_rows(self, zf: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
        text = zf.read(name).decode("utf-8-sig", errors="ignore")
        lines = text.splitlines()
        if not lines:
            return []
        delimiter = "\t" if "\t" in lines[0] else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        return [dict(row) for row in reader if row]

    def _sec_value(self, row: dict[str, Any], *candidates: str) -> str:
        normalized = {self._normalize_key(k): v for k, v in row.items()}
        for candidate in candidates:
            value = normalized.get(self._normalize_key(candidate))
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    def _normalize_key(self, key: str) -> str:
        return re.sub(r"[^a-z0-9]", "", key.lower())

    def _parse_sec_date(self, value: str) -> Optional[datetime]:
        if not value:
            return None
        try:
            from dateutil.parser import parse
            return parse(value).replace(tzinfo=None)
        except Exception:
            return None

    def _parse_money(self, value: str) -> Optional[float]:
        if not value:
            return None
        cleaned = value.strip().replace("$", "").replace(",", "")
        if cleaned.lower() in {"na", "n/a", "none"}:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    async def _fetch_techcrunch_rss(self, result: IngestResult) -> None:
        """Parse TechCrunch's current main feed for recent funding news."""
        try:
            resp = await self._get(TECHCRUNCH_MAIN_RSS)
            root = ElementTree.fromstring(resp.text)
        except Exception as e:
            logger.warning(f"TechCrunch RSS failed: {e}")
            return

        channel = root.find("channel")
        if not channel:
            return

        cutoff = datetime.utcnow() - timedelta(days=14)

        for item in channel.findall("item")[:50]:
            try:
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                description = item.findtext("description", "") or ""
                pub_date_str = item.findtext("pubDate", "")
                combined = f"{title} {description}".lower()

                if not any(keyword in combined for keyword in (
                    "raise",
                    "raised",
                    "funding",
                    "fund",
                    "seed",
                    "series",
                    "investment",
                )):
                    continue

                # Parse date
                try:
                    from dateutil.parser import parse
                    pub_date = parse(pub_date_str).replace(tzinfo=None)
                    if pub_date < cutoff:
                        continue
                except Exception:
                    pub_date = datetime.utcnow()

                # Extract funding data from headline
                funding_data = self._parse_funding_headline(title, description)
                if not funding_data:
                    continue

                company_name = funding_data["company_name"]
                amount = funding_data["amount_usd"]
                round_type = funding_data["round_type"]

                # Score based on amount + round relevance
                score = self._score_funding_event(amount, round_type, title + description)
                if score < 30:
                    continue

                self._append_funding_event(
                    result,
                    company_name=company_name,
                    amount_usd=amount,
                    round_type=round_type,
                    signal_date=pub_date,
                    source_url=link,
                    detail=(
                        "Source: TechCrunch. Funding events of this size typically "
                        "precede engineering headcount growth within 30–60 days."
                    ),
                    score=score,
                )

            except Exception as e:
                logger.debug(f"Failed to parse RSS item: {e}")
                continue

    async def _fetch_axios_rss(self, result: IngestResult) -> None:
        """Parse Axios Pro Rata RSS for additional funding coverage."""
        try:
            resp = await self._get("https://www.axios.com/feeds/feed.rss")
            root = ElementTree.fromstring(resp.text)
        except Exception:
            return  # Axios RSS optional

        for item in root.findall(".//item")[:30]:
            title = item.findtext("title", "") or ""
            if not any(k in title.lower() for k in ["raises", "funding", "series", "seed"]):
                continue

            link = item.findtext("link", "")
            desc = item.findtext("description", "") or ""
            funding_data = self._parse_funding_headline(title, desc)
            if not funding_data:
                continue

            score = self._score_funding_event(
                funding_data["amount_usd"],
                funding_data["round_type"],
                title + desc,
            )
            if score < 35:
                continue

            self._append_funding_event(
                result,
                company_name=funding_data["company_name"],
                amount_usd=funding_data["amount_usd"],
                round_type=funding_data["round_type"],
                signal_date=datetime.utcnow(),
                source_url=link,
                detail="Source: Axios. Engineering hiring wave likely within 30–60 days.",
                score=score,
            )

    async def _fetch_crunchbase(self, result: IngestResult) -> None:
        """Fetch from Crunchbase API when key is available."""
        try:
            resp = await self._post(
                f"{CRUNCHBASE_API}/searches/funding_rounds",
                json={
                    "field_ids": [
                        "identifier", "funded_organization_identifier",
                        "announced_on", "money_raised", "investment_type",
                        "funded_organization_location",
                    ],
                    "query": [
                        {
                            "type": "predicate",
                            "field_id": "announced_on",
                            "operator_id": "gte",
                            "values": [
                                (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%d")
                            ],
                        },
                        {
                            "type": "predicate",
                            "field_id": "investment_type",
                            "operator_id": "includes",
                            "values": ["seed", "series_a", "series_b", "series_c"],
                        },
                    ],
                    "order": [{"field_id": "announced_on", "sort": "desc"}],
                    "limit": 100,
                },
                headers={"X-cb-user-key": settings.crunchbase_api_key.strip()},
            )
            data = resp.json()

            for entity in data.get("entities", []):
                props = entity.get("properties", {})
                company_name = (
                    props.get("funded_organization_identifier", {})
                    .get("value", "")
                )
                amount = props.get("money_raised", {}).get("value_usd")
                round_type = props.get("investment_type", "")
                announced_on = props.get("announced_on")

                if not company_name:
                    continue

                try:
                    from dateutil.parser import parse
                    sig_date = parse(announced_on) if announced_on else datetime.utcnow()
                    sig_date = sig_date.replace(tzinfo=None)
                except Exception:
                    sig_date = datetime.utcnow()

                score = self._score_funding_event(amount, round_type, company_name)

                self._append_funding_event(
                    result,
                    company_name=company_name,
                    amount_usd=amount,
                    round_type=round_type,
                    signal_date=sig_date,
                    source_url="",
                    detail="Source: Crunchbase. Engineering headcount growth expected.",
                    score=score,
                )

        except Exception as e:
            logger.warning(f"Crunchbase API failed: {e}")

    async def _fetch_topstartups_pages(self, result: IngestResult) -> None:
        for url, default_round in (
            (TOPSTARTUPS_SERIES_B_URL, "series b"),
            (TOPSTARTUPS_SEED_URL, "seed"),
        ):
            try:
                resp = await self._get(url)
                self._parse_topstartups_page(result, resp.text, url, default_round)
            except Exception as e:
                logger.warning(f"TopStartups funding source failed ({url}): {e}")

    async def _fetch_crescendo_ai_funding_page(self, result: IngestResult) -> None:
        try:
            resp = await self._get(CRESCENDO_AI_FUNDING_URL)
        except Exception as e:
            logger.warning(f"Crescendo AI funding source failed: {e}")
            return

        soup = BeautifulSoup(resp.text, "lxml")
        for heading in soup.find_all(["h2", "h3"]):
            title = self._normalize_text(heading.get_text(" ", strip=True))
            if not any(keyword in title.lower() for keyword in ("raises", "raised", "series", "seed", "funding")):
                continue

            parsed = self._parse_funding_headline(title, "")
            if not parsed:
                continue

            block_text = self._collect_sibling_block_text(heading)
            when_match = re.search(r"When:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", block_text)
            signal_date = self._parse_flexible_date(when_match.group(1) if when_match else "") or datetime.utcnow()
            recipient_match = re.search(r"Recipient Company:\s*([^\n(]+)", block_text)
            company_name = (
                self._clean_company_name(recipient_match.group(1))
                if recipient_match
                else parsed["company_name"]
            )
            details = self._extract_labeled_block(
                block_text,
                "Details:",
                ("Reference:", "When:", "Recipient Company:"),
            )

            self._append_funding_event(
                result,
                company_name=company_name,
                amount_usd=parsed["amount_usd"],
                round_type=parsed["round_type"],
                signal_date=signal_date,
                source_url=CRESCENDO_AI_FUNDING_URL,
                detail=f"Source: Crescendo AI funding roundup. {details or title}",
                score=self._score_funding_event(
                    parsed["amount_usd"],
                    parsed["round_type"],
                    f"{title} {block_text}",
                ),
            )

    async def _fetch_crunchbase_news_homepage(self, result: IngestResult) -> None:
        await self._fetch_generic_funding_headlines_page(
            result,
            url=CRUNCHBASE_NEWS_URL,
            source_label="Crunchbase News",
        )

    async def _fetch_pymnts_homepage(self, result: IngestResult) -> None:
        await self._fetch_generic_funding_headlines_page(
            result,
            url=PYMNTS_HOME_URL,
            source_label="PYMNTS",
        )

    async def _fetch_generic_funding_headlines_page(
        self,
        result: IngestResult,
        *,
        url: str,
        source_label: str,
    ) -> None:
        try:
            resp = await self._get(url)
        except Exception as e:
            logger.warning(f"{source_label} funding source failed: {e}")
            return

        soup = BeautifulSoup(resp.text, "lxml")
        seen_titles: set[str] = set()

        for anchor in soup.find_all("a", href=True):
            title = self._normalize_text(anchor.get_text(" ", strip=True))
            title_key = title.lower()
            if title_key in seen_titles or len(title) < 20:
                continue
            if not any(keyword in title_key for keyword in ("raises", "raised", "series", "seed", "funding", "investment")):
                continue

            parsed = self._parse_funding_headline(title, "")
            if not parsed:
                continue

            seen_titles.add(title_key)
            href = urljoin(url, anchor.get("href", ""))
            block_text = self._normalize_text(anchor.parent.get_text(" ", strip=True)) if anchor.parent else title
            signal_date = self._parse_flexible_date(block_text) or datetime.utcnow()

            self._append_funding_event(
                result,
                company_name=parsed["company_name"],
                amount_usd=parsed["amount_usd"],
                round_type=parsed["round_type"],
                signal_date=signal_date,
                source_url=href,
                detail=f"Source: {source_label}. {title}",
                score=self._score_funding_event(parsed["amount_usd"], parsed["round_type"], block_text),
            )

    async def _fetch_fundraise_insider_pages(self, result: IngestResult) -> None:
        for url, default_round in (
            (FUNDRAISE_INSIDER_SERIES_B_URL, "series b"),
            (FUNDRAISE_INSIDER_SEED_URL, "seed"),
        ):
            try:
                resp = await self._get(url)
                self._parse_fundraise_insider_page(result, resp.text, url, default_round)
            except Exception as e:
                logger.warning(f"Fundraise Insider funding source failed ({url}): {e}")

    def _parse_topstartups_page(
        self,
        result: IngestResult,
        html: str,
        source_url: str,
        default_round_type: str,
    ) -> None:
        soup = BeautifulSoup(html, "lxml")
        for heading in soup.find_all("h3"):
            company_name = self._clean_company_name(heading.get_text(" ", strip=True))
            if not company_name or company_name.lower().startswith(("get newly funded", "filter")):
                continue

            block_text = self._collect_sibling_block_text(heading)
            if "Funding:" not in block_text:
                continue

            funding_text = self._extract_labeled_block(block_text, "Funding:", ("Take action:",))
            if not funding_text:
                continue

            parsed = self._parse_structured_funding_text(company_name, funding_text, default_round_type)
            if not parsed:
                continue

            description = self._extract_labeled_block(block_text, "What they do:", ("Quick facts:", "Funding:"))
            hq_text = self._extract_labeled_block(block_text, "HQ:", ("Funding:", "Take action:", "Founded:"))

            self._append_funding_event(
                result,
                company_name=company_name,
                amount_usd=parsed["amount_usd"],
                round_type=parsed["round_type"],
                signal_date=self._approximate_year_date(parsed["year"]),
                source_url=source_url,
                detail=f"Source: TopStartups directory. {description or 'Recently funded startup profile.'}",
                score=self._score_funding_event(
                    parsed["amount_usd"],
                    parsed["round_type"],
                    f"{company_name} {description} {funding_text} {hq_text}",
                ),
                company_description=description,
                hq_city=self._extract_hq_city(hq_text),
            )

    def _parse_fundraise_insider_page(
        self,
        result: IngestResult,
        html: str,
        source_url: str,
        default_round_type: str,
    ) -> None:
        soup = BeautifulSoup(html, "lxml")
        lines = [line.strip(" *\t") for line in soup.get_text("\n", strip=True).splitlines() if line.strip()]
        in_large_section = False

        for line in lines:
            lowered = line.lower()
            if "exceptionally large" in lowered:
                in_large_section = True
                continue
            if in_large_section and "exceptionally small" in lowered:
                break
            if not in_large_section:
                continue

            parsed = self._parse_fundraise_insider_bullet(line, default_round_type)
            if not parsed:
                continue

            self._append_funding_event(
                result,
                company_name=parsed["company_name"],
                amount_usd=parsed["amount_usd"],
                round_type=parsed["round_type"],
                signal_date=parsed["signal_date"],
                source_url=source_url,
                detail="Source: Fundraise Insider funding roundup.",
                score=self._score_funding_event(parsed["amount_usd"], parsed["round_type"], line),
            )

    def _has_valid_crunchbase_key(self) -> bool:
        key = settings.crunchbase_api_key.strip()
        if not key:
            return False
        try:
            key.encode("ascii")
        except UnicodeEncodeError:
            return False
        return True

    # ── Parsers ────────────────────────────────────────────────────

    AMOUNT_PATTERN = re.compile(
        r"\$(\d+(?:\.\d+)?)\s*(million|billion|m\b|b\b)",
        re.IGNORECASE,
    )

    ROUND_PATTERN = re.compile(
        r"\b(seed|pre-seed|series [a-f]|series[a-f]|growth|bridge)\b",
        re.IGNORECASE,
    )

    COMPANY_ACTION_PATTERN = re.compile(
        r"^([A-Z][A-Za-z0-9\s&\'\.\-,]+?)\s+"
        r"(?:raises?|raised|secures?|secured|closes?|closed|lands?|landed|"
        r"captures?|captured|charts?|charted|wins?|won|nabs?|nabbed|"
        r"locks\s+down|locked\s+down)\b",
        re.MULTILINE | re.IGNORECASE,
    )
    BACKED_PREFIX_PATTERN = re.compile(
        r"^[A-Z][A-Za-z0-9\s&\'\.\-,]+-backed\s+",
        re.IGNORECASE,
    )
    EDITORIAL_PREFIX_PATTERN = re.compile(
        r"^(?:Exclusive|Report|Reports|Breaking|Analysis|Update|Opinion):\s+",
        re.IGNORECASE,
    )
    PREFIXED_COMPANY_ACTION_PATTERN = re.compile(
        r"^(?:Exclusive:\s*)?([A-Z][A-Za-z0-9\s&\'\.\-]+?)(?:,|:)\s.*?\b"
        r"(?:raises?|raised|secures?|secured|closes?|closed|lands?|landed|"
        r"captures?|captured|charts?|charted|wins?|won|nabs?|nabbed|"
        r"locks\s+down|locked\s+down)\b",
        re.IGNORECASE,
    )

    def _parse_funding_headline(
        self,
        title: str,
        description: str,
    ) -> Optional[dict[str, Any]]:
        """Extract company name, amount, and round type from text."""
        title = self._normalize_text(title)
        description = self._normalize_text(description)
        title_for_company = self._strip_editorial_prefix(title)
        full_text = f"{title} {description}"

        # Extract amount
        amount_match = self.AMOUNT_PATTERN.search(full_text)
        if not amount_match:
            return None

        value = float(amount_match.group(1))
        unit = amount_match.group(2).lower()
        amount_usd = value * 1_000_000 if unit in ("million", "m") else value * 1_000_000_000

        # Only care about $5M–$500M range (seed through Series C)
        if not (5_000_000 <= amount_usd <= 500_000_000):
            return None

        # Extract round type
        round_match = self.ROUND_PATTERN.search(full_text)
        round_type = round_match.group(1).lower() if round_match else "unknown"

        # Extract company name
        company_match = self.COMPANY_ACTION_PATTERN.search(title_for_company)
        if not company_match:
            company_match = self.PREFIXED_COMPANY_ACTION_PATTERN.search(title_for_company)
        if not company_match:
            return None

        company_name = self._clean_company_name(company_match.group(1))
        if len(company_name) < 2 or len(company_name) > 80:
            return None

        return {
            "company_name": company_name,
            "amount_usd": amount_usd,
            "round_type": round_type,
        }

    def _normalize_text(self, value: str) -> str:
        value = unescape(value or "")
        value = re.sub(r"<[^>]+>", " ", value)
        return " ".join(value.split())

    def _clean_company_name(self, value: str) -> str:
        company_name = self._normalize_text(value).rstrip(",")
        company_name = self._strip_editorial_prefix(company_name)
        company_name = self.BACKED_PREFIX_PATTERN.sub("", company_name)
        company_name = re.sub(r"^(?:How|Why)\s+", "", company_name, flags=re.IGNORECASE)
        return company_name.strip()

    def _strip_editorial_prefix(self, value: str) -> str:
        return self.EDITORIAL_PREFIX_PATTERN.sub("", value).strip()

    def _score_funding_event(
        self,
        amount_usd: Optional[float],
        round_type: str,
        context_text: str,
    ) -> float:
        """
        Score a funding event by likelihood of engineering hiring.

        Factors:
          - Round type (Series A/B = highest signal for hiring)
          - Amount (larger = more hiring budget)
          - Tech sector signals in description
        """
        if amount_usd is None:
            return 30.0

        # Base score by round type
        round_scores = {
            "seed": 45.0,
            "pre-seed": 30.0,
            "series a": 70.0,
            "series b": 80.0,
            "series c": 65.0,
            "series d": 50.0,
            "growth": 55.0,
        }
        base = round_scores.get(round_type.lower(), 40.0)

        # Amount bonus
        if amount_usd >= 50_000_000:
            base += 15.0
        elif amount_usd >= 20_000_000:
            base += 10.0
        elif amount_usd >= 10_000_000:
            base += 5.0

        # Tech sector signal
        text_lower = context_text.lower()
        if any(k in text_lower for k in TECH_COMPANY_SIGNALS):
            base += 10.0

        return min(base, 95.0)

    def _format_headline(
        self,
        company: str,
        amount: Optional[float],
        round_type: str,
    ) -> str:
        if amount:
            if amount >= 1_000_000_000:
                amount_str = f"${amount/1_000_000_000:.1f}B"
            else:
                amount_str = f"${amount/1_000_000:.0f}M"
            return f"Raised {amount_str} {round_type.title()} — engineering hiring wave expected"
        return f"Funding event ({round_type.title()}) — engineering hiring expected"

    def _round_to_stage(self, round_type: str) -> FundingStage:
        r = round_type.lower()
        if "seed" in r:
            return FundingStage.SEED
        if "series a" in r:
            return FundingStage.SERIES_A
        if "series b" in r:
            return FundingStage.SERIES_B
        if "series c" in r:
            return FundingStage.SERIES_C
        if "series d" in r or "growth" in r:
            return FundingStage.SERIES_D_PLUS
        return FundingStage.UNKNOWN

    def _append_funding_event(
        self,
        result: IngestResult,
        *,
        company_name: str,
        amount_usd: Optional[float],
        round_type: str,
        signal_date: datetime,
        source_url: str,
        detail: str,
        score: float,
        company_description: str = "",
        hq_city: str = "",
    ) -> None:
        company_name = self._clean_company_name(company_name)
        if not company_name:
            return

        event_key = (
            company_name.lower(),
            round_type.lower().strip() or "unknown",
            int((amount_usd or 0) / 1_000_000),
            signal_date.date().isoformat(),
        )
        if event_key in self._seen_funding_events:
            return
        self._seen_funding_events.add(event_key)

        company_key = company_name.lower()
        if company_key not in self._seen_company_names:
            result.companies.append(
                CompanyResult(
                    name=company_name,
                    description=company_description,
                    funding_stage=self._round_to_stage(round_type),
                    funding_amount_usd=amount_usd,
                    last_funding_date=signal_date,
                    hq_city=hq_city,
                )
            )
            self._seen_company_names.add(company_key)

        result.signals.append(
            SignalResult(
                company_name=company_name,
                type=SignalType.FUNDING,
                headline=self._format_headline(company_name, amount_usd, round_type),
                detail=detail,
                source_url=source_url,
                signal_date=signal_date,
                score=score,
                funding_amount_usd=amount_usd,
                funding_round=round_type,
            )
        )

    def _collect_sibling_block_text(self, element: Any) -> str:
        blocks: list[str] = []
        for sibling in element.next_siblings:
            name = getattr(sibling, "name", None)
            if name in {"h2", "h3"}:
                break
            if hasattr(sibling, "get_text"):
                text = sibling.get_text("\n", strip=True)
            else:
                text = str(sibling).strip()
            if text:
                blocks.append(text)
        return "\n".join(blocks)

    def _extract_labeled_block(
        self,
        text: str,
        label: str,
        stop_labels: tuple[str, ...],
    ) -> str:
        if label not in text:
            return ""
        start = text.index(label) + len(label)
        tail = text[start:]
        end = len(tail)
        for stop_label in stop_labels:
            idx = tail.find(stop_label)
            if idx != -1:
                end = min(end, idx)
        return self._normalize_text(tail[:end])

    def _parse_structured_funding_text(
        self,
        company_name: str,
        funding_text: str,
        default_round_type: str,
    ) -> Optional[dict[str, Any]]:
        funding_text = self._normalize_text(funding_text)
        amount_match = self.AMOUNT_PATTERN.search(funding_text)
        amount_usd: Optional[float] = None
        if amount_match:
            value = float(amount_match.group(1))
            unit = amount_match.group(2).lower()
            amount_usd = value * 1_000_000 if unit in ("million", "m") else value * 1_000_000_000

        round_match = self.ROUND_PATTERN.search(funding_text)
        round_type = round_match.group(1).lower() if round_match else default_round_type
        year_match = re.search(r"\b(20\d{2})\b", funding_text)
        year = int(year_match.group(1)) if year_match else datetime.utcnow().year

        if amount_usd is None and round_type == "unknown":
            return None

        return {
            "company_name": company_name,
            "amount_usd": amount_usd,
            "round_type": round_type,
            "year": year,
        }

    def _parse_fundraise_insider_bullet(
        self,
        line: str,
        default_round_type: str,
    ) -> Optional[dict[str, Any]]:
        match = re.search(
            r"^(?P<company>[A-Z0-9][A-Za-z0-9\s&\'\.\-]+?)\s+\([^)]+\):\s+\$(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>[KMB])\s+on\s+(?P<date>[A-Za-z]+\s+\d{1,2},\s+\d{4})",
            line,
        )
        if not match:
            return None

        amount = float(match.group("amount"))
        unit = match.group("unit").upper()
        multiplier = 1_000 if unit == "K" else 1_000_000 if unit == "M" else 1_000_000_000
        amount_usd = amount * multiplier
        if amount_usd < 5_000_000:
            return None

        signal_date = self._parse_flexible_date(match.group("date")) or datetime.utcnow()
        return {
            "company_name": self._clean_company_name(match.group("company")),
            "amount_usd": amount_usd,
            "round_type": default_round_type,
            "signal_date": signal_date,
        }

    def _approximate_year_date(self, year: int) -> datetime:
        return datetime(max(2000, year), 7, 1)

    def _parse_flexible_date(self, value: str) -> Optional[datetime]:
        if not value:
            return None
        try:
            from dateutil.parser import parse
            return parse(value, fuzzy=True).replace(tzinfo=None)
        except Exception:
            return None

    def _extract_hq_city(self, value: str) -> str:
        value = self._normalize_text(value)
        if value.lower().startswith("remote"):
            return "Remote"
        return value.split(",")[0].strip()
