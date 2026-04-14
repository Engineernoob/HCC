"""
Broader social signal detection.

The umbrella `social` source aggregates several classes of signals:
  1. company-owned blogs and founder feeds
  2. broader media/news RSS feeds
  3. recent Hacker News discussions from the official API

Everything still normalizes into the same `SignalResult` shape so the
existing DB persistence, SSE stream, scheduler, and frontend do not
need a separate code path.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_datetime

from hirectl.ingestion.base import (
    BaseIngestionAdapter,
    CompanyResult,
    IngestResult,
    SignalResult,
    SignalType,
)
from hirectl.tracked_companies import tracked_company_aliases

logger = logging.getLogger(__name__)

RECENT_WINDOW_DAYS = 14
HACKER_NEWS_STORY_LIMIT = 60
HACKER_NEWS_API_BASE = "https://hacker-news.firebaseio.com/v0"

HIRING_KEYWORDS: dict[str, float] = {
    "we're hiring": 36.0,
    "we are hiring": 36.0,
    "hiring": 24.0,
    "join us": 18.0,
    "join our team": 18.0,
    "open roles": 20.0,
    "careers": 14.0,
    "come work": 20.0,
    "we raised and are hiring": 28.0,
    "we're growing": 16.0,
    "team is growing": 16.0,
    "engineering team": 14.0,
    "eng org": 14.0,
}

ENGINEERING_KEYWORDS: dict[str, float] = {
    "backend": 8.0,
    "distributed systems": 12.0,
    "platform": 8.0,
    "infra": 8.0,
    "infrastructure": 8.0,
    "systems": 6.0,
    "developer tools": 10.0,
    "database": 8.0,
    "ai": 4.0,
    "ml": 4.0,
    "staff engineer": 14.0,
    "senior engineer": 10.0,
    "principal engineer": 14.0,
}

DOWNRANK_KEYWORDS: dict[str, float] = {
    "customer story": -18.0,
    "case study": -18.0,
    "webinar": -12.0,
    "podcast": -10.0,
    "event recap": -10.0,
    "product roundup": -6.0,
}


@dataclass(frozen=True)
class SocialFeedSpec:
    company_name: str
    feed_url: str
    source_label: str
    signal_type: SignalType = SignalType.BLOG_POST
    actor_name: str = ""
    actor_role: str = ""
    min_score: float = 48.0


@dataclass(frozen=True)
class DiscoveryFeedSpec:
    feed_url: str
    source_label: str
    signal_type: SignalType = SignalType.NEWS
    min_score: float = 42.0


@dataclass
class FeedEntry:
    title: str
    link: str
    summary: str
    published_at: datetime
    author: str = ""


OWNED_SOCIAL_FEEDS: list[SocialFeedSpec] = [
    SocialFeedSpec(
        company_name="Convex",
        feed_url="https://stack.convex.dev/rss/",
        source_label="Convex Stack",
        signal_type=SignalType.FOUNDER_POST,
        actor_name="Convex founders",
        actor_role="Founder",
        min_score=46.0,
    ),
    SocialFeedSpec(
        company_name="Supabase",
        feed_url="https://supabase.com/blog/rss.xml",
        source_label="Supabase Blog",
        signal_type=SignalType.BLOG_POST,
    ),
    SocialFeedSpec(
        company_name="Turso",
        feed_url="https://turso.tech/blog/rss.xml",
        source_label="Turso Blog",
        signal_type=SignalType.BLOG_POST,
    ),
    SocialFeedSpec(
        company_name="Modal Labs",
        feed_url="https://modal.com/blog/rss.xml",
        source_label="Modal Blog",
        signal_type=SignalType.BLOG_POST,
    ),
    SocialFeedSpec(
        company_name="Baseten",
        feed_url="https://www.baseten.co/blog/rss.xml",
        source_label="Baseten Blog",
        signal_type=SignalType.BLOG_POST,
    ),
    SocialFeedSpec(
        company_name="Render",
        feed_url="https://render.com/blog/rss.xml",
        source_label="Render Blog",
        signal_type=SignalType.BLOG_POST,
    ),
    SocialFeedSpec(
        company_name="Fly.io",
        feed_url="https://fly.io/blog/feed.xml",
        source_label="Fly.io Blog",
        signal_type=SignalType.BLOG_POST,
    ),
    SocialFeedSpec(
        company_name="Temporal",
        feed_url="https://temporal.io/blog/rss.xml",
        source_label="Temporal Blog",
        signal_type=SignalType.BLOG_POST,
    ),
    SocialFeedSpec(
        company_name="Dagger",
        feed_url="https://dagger.io/blog/rss.xml",
        source_label="Dagger Blog",
        signal_type=SignalType.BLOG_POST,
    ),
    SocialFeedSpec(
        company_name="Inngest",
        feed_url="https://www.inngest.com/blog/rss.xml",
        source_label="Inngest Blog",
        signal_type=SignalType.BLOG_POST,
    ),
]

DISCOVERY_FEEDS: list[DiscoveryFeedSpec] = [
    DiscoveryFeedSpec(
        feed_url="https://techcrunch.com/feed/",
        source_label="TechCrunch",
        signal_type=SignalType.NEWS,
        min_score=40.0,
    ),
    DiscoveryFeedSpec(
        feed_url="https://thenewstack.io/feed/",
        source_label="The New Stack",
        signal_type=SignalType.NEWS,
        min_score=40.0,
    ),
    DiscoveryFeedSpec(
        feed_url="https://www.ycombinator.com/blog/rss/",
        source_label="Y Combinator Blog",
        signal_type=SignalType.NEWS,
        min_score=40.0,
    ),
]

COMPANY_ALIASES: dict[str, list[str]] = tracked_company_aliases() | {
    "Convex": ["convex", "stack.convex"],
    "Turso": ["turso", "libsql"],
    "Modal Labs": ["modal labs", "modal.com", "modal"],
    "Render": ["render.com", "render"],
    "Fly.io": ["fly.io", "fly io", "fly"],
    "Temporal": ["temporal.io", "temporal"],
    "Dagger": ["dagger.io", "dagger"],
}


class SocialSignalAdapter(BaseIngestionAdapter):
    """Aggregate broader social/community/media hiring signals."""

    source_name = "social"

    def __init__(
        self,
        owned_feeds: list[SocialFeedSpec] | None = None,
        discovery_feeds: list[DiscoveryFeedSpec] | None = None,
    ):
        super().__init__()
        self.owned_feeds = owned_feeds or OWNED_SOCIAL_FEEDS
        self.discovery_feeds = discovery_feeds or DISCOVERY_FEEDS
        self.company_websites = {
            feed.company_name: self._site_origin(feed.feed_url) for feed in self.owned_feeds
        }

    async def fetch(self) -> IngestResult:
        result = IngestResult(source=self.source_name)
        seen_companies: set[str] = set()
        seen_urls: set[str] = set()

        for feed in self.owned_feeds:
            try:
                entries = await self._fetch_feed_entries(feed.feed_url)
            except Exception as exc:
                logger.debug(f"Owned social feed fetch failed for {feed.company_name}: {exc}")
                continue

            for entry in entries:
                self._append_signal_from_entry(
                    result=result,
                    seen_companies=seen_companies,
                    seen_urls=seen_urls,
                    company_name=feed.company_name,
                    website=self.company_websites.get(feed.company_name, ""),
                    signal_type=feed.signal_type,
                    source_label=feed.source_label,
                    actor_name=feed.actor_name,
                    actor_role=feed.actor_role,
                    min_score=feed.min_score,
                    entry=entry,
                )

        for feed in self.discovery_feeds:
            try:
                entries = await self._fetch_feed_entries(feed.feed_url)
            except Exception as exc:
                logger.debug(f"Discovery social feed fetch failed for {feed.source_label}: {exc}")
                continue

            for entry in entries:
                company_name = self._match_company_name(f"{entry.title}\n{entry.summary}")
                if not company_name:
                    continue
                self._append_signal_from_entry(
                    result=result,
                    seen_companies=seen_companies,
                    seen_urls=seen_urls,
                    company_name=company_name,
                    website=self.company_websites.get(company_name, ""),
                    signal_type=feed.signal_type,
                    source_label=feed.source_label,
                    actor_name=entry.author,
                    actor_role="",
                    min_score=feed.min_score,
                    entry=entry,
                )

        try:
            hacker_news_entries = await self._fetch_hacker_news_entries()
        except Exception as exc:
            logger.debug(f"Hacker News social fetch failed: {exc}")
            hacker_news_entries = []

        for company_name, entry in hacker_news_entries:
            self._append_signal_from_entry(
                result=result,
                seen_companies=seen_companies,
                seen_urls=seen_urls,
                company_name=company_name,
                website=self.company_websites.get(company_name, ""),
                signal_type=SignalType.NEWS,
                source_label="Hacker News",
                actor_name=entry.author,
                actor_role="",
                min_score=42.0,
                entry=entry,
            )

        return result

    async def _fetch_feed_entries(self, url: str) -> list[FeedEntry]:
        response = await self._get(url)
        root = ElementTree.fromstring(response.text)

        if self._local_name(root.tag) == "feed":
            return self._parse_atom(root)
        return self._parse_rss(root)

    async def _fetch_hacker_news_entries(self) -> list[tuple[str, FeedEntry]]:
        response = await self._get(f"{HACKER_NEWS_API_BASE}/newstories.json")
        story_ids = response.json()
        if not isinstance(story_ids, list):
            return []

        cutoff = datetime.utcnow() - timedelta(days=RECENT_WINDOW_DAYS)
        entries: list[tuple[str, FeedEntry]] = []

        for story_id in story_ids[:HACKER_NEWS_STORY_LIMIT]:
            item_response = await self._get(f"{HACKER_NEWS_API_BASE}/item/{story_id}.json")
            item = item_response.json()
            if not isinstance(item, dict):
                continue
            if item.get("type") not in {"story", "comment"}:
                continue
            if item.get("dead") or item.get("deleted"):
                continue

            published_at = self._parse_hn_timestamp(item.get("time"))
            if published_at < cutoff:
                continue

            title = self._clean_text(str(item.get("title") or ""))
            summary = self._sanitize_html(str(item.get("text") or title))
            body = f"{title}\n{summary}"
            company_name = self._match_company_name(body)
            if not company_name:
                continue

            entries.append(
                (
                    company_name,
                    FeedEntry(
                        title=title or summary[:180],
                        link=str(item.get("url") or f"https://news.ycombinator.com/item?id={story_id}"),
                        summary=summary,
                        published_at=published_at,
                        author=str(item.get("by") or ""),
                    ),
                )
            )

        return entries

    def _parse_rss(self, root: ElementTree.Element) -> list[FeedEntry]:
        channel = root.find("channel")
        if channel is None:
            return []

        cutoff = datetime.utcnow() - timedelta(days=RECENT_WINDOW_DAYS)
        entries: list[FeedEntry] = []
        for item in channel.findall("item")[:40]:
            title = self._child_text(item, "title")
            link = self._child_text(item, "link")
            summary = self._sanitize_html(
                self._child_text(item, "description", "encoded")
            )
            author = self._child_text(item, "creator", "author")
            published_at = self._parse_date(
                self._child_text(item, "pubDate", "published", "updated")
            )
            if not title or not link or published_at < cutoff:
                continue
            entries.append(
                FeedEntry(
                    title=title,
                    link=link,
                    summary=summary,
                    published_at=published_at,
                    author=author,
                )
            )
        return entries

    def _parse_atom(self, root: ElementTree.Element) -> list[FeedEntry]:
        cutoff = datetime.utcnow() - timedelta(days=RECENT_WINDOW_DAYS)
        entries: list[FeedEntry] = []
        for entry in [child for child in root if self._local_name(child.tag) == "entry"][:40]:
            title = self._child_text(entry, "title")
            link = self._atom_link(entry)
            summary = self._sanitize_html(
                self._child_text(entry, "summary", "content")
            )
            author = self._atom_author(entry)
            published_at = self._parse_date(
                self._child_text(entry, "published", "updated")
            )
            if not title or not link or published_at < cutoff:
                continue
            entries.append(
                FeedEntry(
                    title=title,
                    link=link,
                    summary=summary,
                    published_at=published_at,
                    author=author,
                )
            )
        return entries

    def _append_signal_from_entry(
        self,
        *,
        result: IngestResult,
        seen_companies: set[str],
        seen_urls: set[str],
        company_name: str,
        website: str,
        signal_type: SignalType,
        source_label: str,
        actor_name: str,
        actor_role: str,
        min_score: float,
        entry: FeedEntry,
    ) -> None:
        if entry.link in seen_urls:
            return

        score, hits = self._score_entry(signal_type, actor_role, entry)
        if score < min_score:
            return

        company_key = company_name.lower()
        if company_key not in seen_companies:
            seen_companies.add(company_key)
            result.companies.append(
                CompanyResult(
                    name=company_name,
                    website=website,
                )
            )

        result.signals.append(
            SignalResult(
                company_name=company_name,
                type=signal_type,
                headline=self._headline(signal_type, actor_role, entry),
                detail=self._detail(
                    source_label=source_label,
                    actor_name=actor_name,
                    entry=entry,
                    hits=hits,
                    company_name=company_name,
                ),
                source_url=entry.link,
                raw_content=entry.summary,
                signal_date=entry.published_at,
                score=score,
                poster_handle=actor_name or entry.author or None,
            )
        )
        seen_urls.add(entry.link)

    def _score_entry(
        self,
        signal_type: SignalType,
        actor_role: str,
        entry: FeedEntry,
    ) -> tuple[float, list[str]]:
        title_lower = entry.title.lower()
        text_lower = f"{entry.title}\n{entry.summary}".lower()
        score = 12.0 if signal_type == SignalType.FOUNDER_POST else 6.0
        hits: list[str] = []

        for phrase, weight in HIRING_KEYWORDS.items():
            if phrase in text_lower:
                score += weight
                hits.append(phrase)

        for phrase, weight in ENGINEERING_KEYWORDS.items():
            if phrase in text_lower:
                score += weight
                hits.append(phrase)

        for phrase, weight in DOWNRANK_KEYWORDS.items():
            if phrase in text_lower:
                score += weight

        if any(term in title_lower for term in ("hiring", "careers", "join", "engineering")):
            score += 8.0

        if actor_role:
            score += 4.0

        unique_hits = list(dict.fromkeys(hits))
        if not any(phrase in text_lower for phrase in ("hiring", "join", "careers", "open roles")):
            score -= 16.0

        return max(0.0, min(score, 95.0)), unique_hits

    def _headline(self, signal_type: SignalType, actor_role: str, entry: FeedEntry) -> str:
        if signal_type == SignalType.FOUNDER_POST and actor_role:
            return f"{entry.title} — {actor_role.lower()} hiring signal"
        return entry.title[:200]

    def _detail(
        self,
        *,
        source_label: str,
        actor_name: str,
        entry: FeedEntry,
        hits: list[str],
        company_name: str,
    ) -> str:
        actor = actor_name or entry.author
        actor_prefix = f"{actor} · " if actor else ""
        keyword_text = ", ".join(hits[:4]) if hits else "team growth language"
        excerpt = entry.summary[:220]
        return (
            f"Source: {source_label}. Company: {company_name}. {actor_prefix}"
            f"Matched on {keyword_text}. {excerpt}"
        ).strip()

    def _match_company_name(self, text: str) -> str | None:
        haystack = text.lower()
        matches: list[tuple[int, str]] = []
        for company_name, aliases in COMPANY_ALIASES.items():
            for alias in aliases:
                pattern = self._alias_pattern(alias)
                if re.search(pattern, haystack):
                    matches.append((len(alias), company_name))
                    break
        if not matches:
            return None
        matches.sort(reverse=True)
        return matches[0][1]

    def _alias_pattern(self, alias: str) -> str:
        escaped = re.escape(alias.lower())
        return rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"

    def _sanitize_html(self, html: str) -> str:
        if not html:
            return ""
        text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
        return self._clean_text(text)

    def _clean_text(self, text: str) -> str:
        return " ".join(text.split())

    def _site_origin(self, link: str) -> str:
        parsed = urlparse(link)
        if not parsed.scheme or not parsed.netloc:
            return ""
        return f"{parsed.scheme}://{parsed.netloc}"

    def _parse_date(self, raw: str) -> datetime:
        if not raw:
            return datetime.utcnow()
        try:
            return parse_datetime(raw).replace(tzinfo=None)
        except Exception:
            return datetime.utcnow()

    def _parse_hn_timestamp(self, raw: object) -> datetime:
        if not raw:
            return datetime.utcnow()
        try:
            return datetime.utcfromtimestamp(int(raw))
        except (TypeError, ValueError, OSError):
            return datetime.utcnow()

    def _atom_link(self, entry: ElementTree.Element) -> str:
        for child in entry:
            if self._local_name(child.tag) != "link":
                continue
            href = child.attrib.get("href", "")
            rel = child.attrib.get("rel", "alternate")
            if href and rel in ("alternate", ""):
                return href
        return ""

    def _atom_author(self, entry: ElementTree.Element) -> str:
        for child in entry:
            if self._local_name(child.tag) != "author":
                continue
            return self._child_text(child, "name")
        return ""

    def _child_text(self, parent: ElementTree.Element, *names: str) -> str:
        wanted = set(names)
        for child in parent:
            if self._local_name(child.tag) in wanted and child.text:
                return child.text.strip()
        return ""

    def _local_name(self, tag: str) -> str:
        return tag.rsplit("}", 1)[-1]
