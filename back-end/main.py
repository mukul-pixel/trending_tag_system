"""
Trending Tags — FastAPI Backend Service
========================================
Two endpoints:
  GET /get-trending-feed   — ranked trending tags with LLM enrichment
  GET /get-trend-details   — deep-dive for a single tag (hero media, context, feed)

Dependencies:
    pip install fastapi uvicorn asyncpg anthropic python-dotenv
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import anthropic
import asyncpg
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

app = FastAPI(title="Trending Tags API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

DATABASE_URL  = os.environ.get("DATABASE_URL", "postgresql://user:pass@localhost/db")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL         = "claude-sonnet-4-20250514"

# Minimum 2h posts for a tag to enter the scoring pipeline
MIN_VOLUME_GATE = 10

# ===========================================================================
# 1. DATA CONTRACTS
# ===========================================================================

@dataclass
class TagMetrics:
    """One row from tag_trend_metrics staging table."""
    tag: str
    current_2h_posts:  int
    prev_2h_posts:     Optional[float] = None
    avg_2h_posts_7d:   Optional[float] = None
    avg_likes_24h:     float = 0.0
    avg_shares_24h:    float = 0.0
    avg_comments_24h:  float = 0.0
    avg_likes_7d:      Optional[float] = None
    avg_shares_7d:     Optional[float] = None
    avg_comments_7d:   Optional[float] = None
    searches_today:    int   = 0
    avg_searches_7d:   Optional[float] = None


@dataclass
class GlobalBaselines:
    """Platform-wide fallback averages — recomputed hourly."""
    global_avg_2h_posts:  float = 50.0
    global_avg_searches:  float = 100.0
    global_avg_likes:     float = 5.0
    global_avg_shares:    float = 2.0
    global_avg_comments:  float = 1.0
    cached_at: float = field(default_factory=time.time)


@dataclass
class ScoredTag:
    tag:           str
    trend_score:   float
    heat_score:    float  = 0.0   # normalised 0-100 after batch
    rank:          int    = 0
    spike:         float  = 0.0
    volume_log:    float  = 0.0
    growth:        float  = 0.0
    search_growth: float  = 0.0
    engagement:    float  = 0.0
    # raw signal values for argmax
    posts_signal:  float  = 0.0   # max(spike, growth)
    search_signal: float  = 0.0   # search_growth
    eng_signal:    float  = 0.0   # engagement


# Baseline cache (refreshed hourly)
_baselines_cache: Optional[GlobalBaselines] = None
_BASELINE_TTL = 3600


# ===========================================================================
# 2. SCORING ENGINE
# ===========================================================================

def _coalesce(primary: Optional[float], fallback: float) -> float:
    """COALESCE logic: use own history if valid, else global average."""
    if primary is not None and primary > 0:
        return primary
    return fallback


def score_tag(m: TagMetrics, b: GlobalBaselines) -> Optional[ScoredTag]:
    """
    TrendScore = Spike × log(Volume+1) × Growth × SearchGrowth × Engagement

    Engagement is computed as weighted combo of likes, shares, comments
    (mirroring the image-selection formula: likes + 2×shares + 3×comments).
    """
    if m.current_2h_posts < MIN_VOLUME_GATE:
        return None

    # ── Spike: how unusual is this burst vs. 7-day own history ──────────
    spike = m.current_2h_posts / _coalesce(m.avg_2h_posts_7d, b.global_avg_2h_posts)

    # ── Volume: log-dampened raw count ───────────────────────────────────
    volume_log = math.log(m.current_2h_posts + 1)

    # ── Growth: momentum vs. previous 2h window ──────────────────────────
    growth = m.current_2h_posts / _coalesce(m.prev_2h_posts, b.global_avg_2h_posts)

    # ── SearchGrowth: search intent today vs. 7d average ─────────────────
    search_growth = (
        max(m.searches_today, 1)
        / _coalesce(m.avg_searches_7d, b.global_avg_searches)
    )

    # ── Engagement: weighted combo vs. 7d baseline ───────────────────────
    # likes + 2×shares + 3×comments per post (consistent with image scoring)
    baseline_eng = (
        _coalesce(m.avg_likes_7d,    b.global_avg_likes)
        + 2 * _coalesce(m.avg_shares_7d,   b.global_avg_shares)
        + 3 * _coalesce(m.avg_comments_7d, b.global_avg_comments)
    )
    current_eng = m.avg_likes_24h + 2 * m.avg_shares_24h + 3 * m.avg_comments_24h
    engagement  = max(current_eng, 0.01) / baseline_eng

    trend_score = spike * volume_log * growth * search_growth * engagement

    return ScoredTag(
        tag           = m.tag,
        trend_score   = round(trend_score, 6),
        spike         = round(spike,        4),
        volume_log    = round(volume_log,   4),
        growth        = round(growth,       4),
        search_growth = round(search_growth,4),
        engagement    = round(engagement,   4),
        posts_signal  = round(max(spike, growth), 4),
        search_signal = round(search_growth, 4),
        eng_signal    = round(engagement, 4),
    )


def normalise_heat(scored: list[ScoredTag]) -> list[ScoredTag]:
    """Min-max normalise trend_score → heat_score (0–100)."""
    if not scored:
        return scored
    lo = min(s.trend_score for s in scored)
    hi = max(s.trend_score for s in scored)
    rng = hi - lo or 1.0
    for s in scored:
        s.heat_score = round(((s.trend_score - lo) / rng) * 100, 1)
    return scored


def rank_tags(
    metrics:   list[TagMetrics],
    baselines: GlobalBaselines,
    top_n:     int = 20,
) -> list[ScoredTag]:
    scored = [score_tag(m, baselines) for m in metrics]
    scored = [s for s in scored if s is not None]
    scored.sort(key=lambda s: s.trend_score, reverse=True)
    scored = scored[:top_n]
    scored = normalise_heat(scored)
    for i, s in enumerate(scored, start=1):
        s.rank = i
    return scored


# ===========================================================================
# 3. PRIMARY SIGNAL — argmax logic
# ===========================================================================

SIGNAL_THRESHOLDS = {
    "posts":      2.0,   # threshold for max(spike, growth)
    "searches":   2.0,   # threshold for search_growth
    "engagement": 1.5,   # threshold for engagement
}

SIGNAL_LABELS_HI = {
    "posts":      "अत्यधिक उपयोग",
    "searches":   "अत्यधिक खोजा गया",
    "engagement": "बहुत लोकप्रिय",
}


def assign_primary_signal(s: ScoredTag) -> str:
    """
    argmax: whichever signal exceeded its threshold by the greatest margin
    is the primary signal. Falls back to the raw max if none exceed threshold.
    """
    margins = {
        "posts":      s.posts_signal  - SIGNAL_THRESHOLDS["posts"],
        "searches":   s.search_signal - SIGNAL_THRESHOLDS["searches"],
        "engagement": s.eng_signal    - SIGNAL_THRESHOLDS["engagement"],
    }
    # Keep only signals that cleared their threshold
    above = {k: v for k, v in margins.items() if v > 0}

    if above:
        winner = max(above, key=above.get)
    else:
        # None cleared threshold — pick raw max as fallback
        raw = {
            "posts":      s.posts_signal,
            "searches":   s.search_signal,
            "engagement": s.eng_signal,
        }
        winner = max(raw, key=raw.get)

    return SIGNAL_LABELS_HI[winner]


# ===========================================================================
# 4. LLM CLIENT — guaranteed JSON-only output
# ===========================================================================

class LLMClient:
    """
    Wraps Anthropic API calls.
    All methods return parsed Python objects (never raw strings).
    """

    def __init__(self, api_key: str = ANTHROPIC_KEY):
        self._client = anthropic.Anthropic(api_key=api_key)

    def _call(self, system: str, user: str, max_tokens: int = 2048) -> str:
        resp = self._client.messages.create(
            model      = MODEL,
            max_tokens = max_tokens,
            system     = system,
            messages   = [{"role": "user", "content": user}],
        )
        return resp.content[0].text.strip()

    @staticmethod
    def _parse_json(raw: str) -> object:
        """Strip markdown fences if present, then parse JSON."""
        text = raw
        if text.startswith("```"):
            parts = text.split("```")
            # parts[1] may start with 'json\n'
            text = parts[1]
            if text.lower().startswith("json"):
                text = text[4:]
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM did not return valid JSON: {exc}\nRaw: {raw[:300]}")

    # ── Step A-1: Relevance check ────────────────────────────────────────
    def check_relevance_batch(self, tags: list[str]) -> dict[str, int]:
        """
        Returns {tag: 0|1} — 1 = culturally relevant to India.
        Single API call for the full batch.
        """
        system = """
You are a cultural relevance filter for a Hindi-language social platform in India.
Given a list of hashtags, classify each as:
  1 = Culturally relevant to India (Indian events, people, places, sports, politics, entertainment, festivals, etc.)
  0 = Obscure global trend unlikely to resonate with Hindi-speaking Indian audience

Return ONLY a JSON object mapping each tag to 0 or 1.
No preamble, no markdown, no explanation.
Example: {"#IPL2026": 1, "#NordicSkiChampionship": 0}
""".strip()

        user = (
            "Classify these tags for Indian cultural relevance:\n"
            + "\n".join(tags)
        )
        raw = self._call(system, user, max_tokens=512)
        result = self._parse_json(raw)
        # Ensure all tags present, default to 0 if LLM missed one
        return {t: int(result.get(t, 0)) for t in tags}

    # ── Step A-2: Metadata generation (description + category) ──────────
    def generate_metadata_batch(
        self, tags: list[str]
    ) -> dict[str, dict]:
        """
        Returns {tag: {description_hindi, category}} for relevant tags.
        """
        system = """
You are a content metadata generator for a Hindi social media platform.
Given trending hashtags, return a JSON object where each key is a tag and the value has:
  "description_hindi": one punchy Hindi sentence (max 15 words) explaining why it's trending.
                       Format: "<tag> — <Hindi context>"
  "category": one of exactly: Sports, News, Entertainment, Lifestyle, Finance, Tech

Return ONLY valid JSON. No markdown, no preamble.
Use natural, conversational Hindi. Keep it snappy — this shows in a mobile feed.
""".strip()

        user = (
            "Generate Hindi descriptions and categories for these trending tags:\n"
            + "\n".join(tags)
        )
        raw = self._call(system, user, max_tokens=1024)
        return self._parse_json(raw)

    # ── Step B: Trend context summary (for /get-trend-details) ──────────
    def generate_trend_context(self, tag: str, post_count: int, top_posts_sample: list[str]) -> str:
        """
        Returns a 50-70 word Hindi context paragraph about the trend.
        """
        system = """
You are a Hindi content writer for a social news platform.
Write an "इस ट्रेंड के बारे में" (About this trend) section.
Requirements:
  - Exactly 50-70 Hindi words.
  - Informative and engaging tone.
  - Explain why the tag is trending right now in India.
  - NO bullet points. Flowing paragraph only.
  - Return ONLY the Hindi paragraph text. No JSON, no labels, no English.
""".strip()

        sample_text = "\n".join(f"- {p}" for p in post_samples[:5]) if (post_samples := top_posts_sample) else "No sample posts available."
        user = (
            f"Tag: {tag}\n"
            f"Post count in last 2 hours: {post_count}\n"
            f"Sample post text:\n{sample_text}\n\n"
            "Write the Hindi trend context paragraph."
        )
        return self._call(system, user, max_tokens=256)


# Singleton LLM client (initialised once at startup)
_llm: Optional[LLMClient] = None


@app.on_event("startup")
async def startup():
    global _llm
    _llm = LLMClient()
    logger.info("LLMClient initialised")


# ===========================================================================
# 5. DATABASE HELPERS
# ===========================================================================

async def get_db_pool() -> asyncpg.Pool:
    """Return (or create) the connection pool. Call once at startup in prod."""
    return await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)


_db_pool: Optional[asyncpg.Pool] = None


@app.on_event("startup")
async def init_db():
    global _db_pool
    try:
        _db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
        logger.info("DB pool created")
    except Exception as exc:
        logger.warning("DB unavailable (%s) — endpoints will use mock data", exc)


async def fetch_tag_metrics() -> list[TagMetrics]:
    """Read pre-aggregated metrics from staging table."""
    if not _db_pool:
        return _mock_metrics()

    rows = await _db_pool.fetch("""
        SELECT tag, current_2h_posts, prev_2h_posts, avg_2h_posts_7d,
               avg_likes_24h, avg_shares_24h, avg_comments_24h,
               avg_likes_7d, avg_shares_7d, avg_comments_7d,
               searches_today, avg_searches_7d
        FROM   tag_trend_metrics
        WHERE  computed_at >= NOW() - INTERVAL '30 minutes'
        ORDER  BY current_2h_posts DESC
        LIMIT  200
    """)
    return [TagMetrics(**dict(r)) for r in rows]


async def fetch_global_baselines() -> GlobalBaselines:
    """Cache baselines for 1 hour."""
    global _baselines_cache
    if _baselines_cache and (time.time() - _baselines_cache.cached_at) < _BASELINE_TTL:
        return _baselines_cache

    if not _db_pool:
        _baselines_cache = GlobalBaselines()
        return _baselines_cache

    row = await _db_pool.fetchrow("""
        SELECT AVG(current_2h_posts)  AS global_avg_2h_posts,
               AVG(searches_today)    AS global_avg_searches,
               AVG(avg_likes_24h)     AS global_avg_likes,
               AVG(avg_shares_24h)    AS global_avg_shares,
               AVG(avg_comments_24h)  AS global_avg_comments
        FROM   tag_trend_metrics
        WHERE  computed_at >= NOW() - INTERVAL '1 hour'
    """)
    _baselines_cache = GlobalBaselines(
        global_avg_2h_posts = float(row["global_avg_2h_posts"] or 50),
        global_avg_searches = float(row["global_avg_searches"]  or 100),
        global_avg_likes    = float(row["global_avg_likes"]     or 5),
        global_avg_shares   = float(row["global_avg_shares"]    or 2),
        global_avg_comments = float(row["global_avg_comments"]  or 1),
    )
    return _baselines_cache


async def fetch_hero_media(tag: str) -> Optional[dict]:
    """Most-engaged post with image/video for a tag (last 24h)."""
    if not _db_pool:
        return {"image_url": "https://images.unsplash.com/photo-1531415074968-036ba1b575da?w=800&q=80",
                "video_url": None, "likes": 5100, "shares": 1800, "comments": 1240,
                "engagement_score": 5100 + 1800 + 1240}

    row = await _db_pool.fetchrow("""
        SELECT p.post_id, p.image_url, p.video_url,
               (p.likes + p.shares + p.comments) AS engagement_score,
               p.likes, p.shares, p.comments
        FROM   posts p
        INNER JOIN (SELECT user_id FROM users WHERE language='hindi') u
               ON u.user_id = p.user_id
        WHERE  $1 = ANY(p.tags)
          AND  p.created_at >= NOW() - INTERVAL '24 hours'
          AND  (p.image_url IS NOT NULL OR p.video_url IS NOT NULL)
        ORDER  BY engagement_score DESC
        LIMIT  1
    """, tag)
    return dict(row) if row else None


async def fetch_related_feed(tag: str, limit: int = 20) -> list[dict]:
    """Recent posts for the trend mini-feed."""
    if not _db_pool:
        return _mock_feed(tag)

    rows = await _db_pool.fetch("""
        SELECT p.post_id, p.user_id, u.display_name, u.avatar_url,
               p.content, p.image_url, p.video_url,
               p.likes, p.shares, p.comments, p.created_at
        FROM   posts  p
        INNER JOIN users u ON u.user_id = p.user_id
        INNER JOIN (SELECT user_id FROM users WHERE language='hindi') hf
               ON  hf.user_id = p.user_id
        WHERE  $1 = ANY(p.tags)
        ORDER  BY p.created_at DESC
        LIMIT  $2
    """, tag, limit)
    return [dict(r) for r in rows]


async def fetch_post_text_samples(tag: str, n: int = 5) -> list[str]:
    """Sample post text for LLM context generation."""
    if not _db_pool:
        return ["क्रिकेट का रोमांचक मैच आज रात", "शानदार प्रदर्शन, दर्शक झूमे"]

    rows = await _db_pool.fetch("""
        SELECT content FROM posts
        WHERE  $1 = ANY(tags)
          AND  created_at >= NOW() - INTERVAL '2 hours'
          AND  content IS NOT NULL
        ORDER  BY (likes + shares + comments) DESC
        LIMIT  $2
    """, tag, n)
    return [r["content"] for r in rows]


# ===========================================================================
# 6. ENDPOINT #1: GET /get-trending-feed
# ===========================================================================

@app.get("/get-trending-feed")
async def get_trending_feed(limit: int = Query(default=10, ge=1, le=30)):
    """
    3-step pipeline:
      Step A — LLM relevance check + metadata generation
      Step B — Python argmax primary signal assignment
      Returns ranked, enriched trending tags for Hindi users in India.
    """
    # ── Fetch & score ─────────────────────────────────────────────────────
    metrics   = await fetch_tag_metrics()
    baselines = await fetch_global_baselines()
    scored    = rank_tags(metrics, baselines, top_n=limit * 2)  # over-fetch for filtering

    if not scored:
        return JSONResponse(content={"tags": [], "generated_at": _now()})

    tags_list = [s.tag for s in scored]

    # ── Step A-1: Relevance check ─────────────────────────────────────────
    try:
        relevance = _llm.check_relevance_batch(tags_list)
    except Exception as exc:
        logger.error("Relevance check failed: %s", exc)
        relevance = {t: 1 for t in tags_list}   # fail-open: keep all tags

    relevant_tags = [s for s in scored if relevance.get(s.tag, 0) == 1]

    # ── Step A-2: Metadata generation ─────────────────────────────────────
    relevant_names = [s.tag for s in relevant_tags]
    try:
        metadata = _llm.generate_metadata_batch(relevant_names)
    except Exception as exc:
        logger.error("Metadata generation failed: %s", exc)
        metadata = {t: {"description_hindi": f"{t} — विवरण उपलब्ध नहीं।",
                        "category": "News"}
                    for t in relevant_names}

    # ── Step B: Primary signal assignment ────────────────────────────────
    output = []
    for s in relevant_tags[:limit]:
        meta    = metadata.get(s.tag, {})
        signal  = assign_primary_signal(s)
        output.append({
            "rank":              s.rank,
            "tag":               s.tag,
            "description_hindi": meta.get("description_hindi", f"{s.tag} — विवरण उपलब्ध नहीं।"),
            "category":          meta.get("category", "News"),
            "heat_score":        s.heat_score,
            "primary_signal":    signal,
            "score_breakdown": {
                "spike":         s.spike,
                "growth":        s.growth,
                "search_growth": s.search_growth,
                "engagement":    s.engagement,
            },
        })

    return JSONResponse(content={
        "tags":          output,
        "total_scored":  len(scored),
        "total_relevant":len(relevant_tags),
        "generated_at":  _now(),
    })


# ===========================================================================
# 7. ENDPOINT #2: GET /get-trend-details
# ===========================================================================

@app.get("/get-trend-details")
async def get_trend_details(tag_name: str = Query(..., description="e.g. #IPL2026")):
    """
    Deep-dive for a single tag:
      1. Hero image/video (most engaged post, last 24h)
      2. LLM context summary in Hindi (50-70 words)
      3. Related mini-feed (20 most recent posts)
    """
    if not tag_name.startswith("#"):
        tag_name = f"#{tag_name}"

    # Parallelise I/O-bound fetches
    hero_task, feed_task, sample_task = await asyncio.gather(
        fetch_hero_media(tag_name),
        fetch_related_feed(tag_name),
        fetch_post_text_samples(tag_name),
        return_exceptions=True,
    )

    hero   = hero_task   if not isinstance(hero_task,   Exception) else None
    feed   = feed_task   if not isinstance(feed_task,   Exception) else []
    samples= sample_task if not isinstance(sample_task, Exception) else []

    # LLM context summary
    post_count = len(feed) if feed else 0
    try:
        context_hindi = _llm.generate_trend_context(tag_name, post_count, samples)
    except Exception as exc:
        logger.error("Context generation failed: %s", exc)
        context_hindi = f"{tag_name} इस समय भारत में चर्चा में है।"

    # Serialise feed (datetime → ISO string)
    serialised_feed = []
    for p in (feed or []):
        entry = dict(p)
        if isinstance(entry.get("created_at"), datetime):
            entry["created_at"] = entry["created_at"].isoformat()
        serialised_feed.append(entry)

    return JSONResponse(content={
        "tag":             tag_name,
        "hero_media":      hero,
        "context_hindi":   context_hindi,
        "related_feed":    serialised_feed,
        "generated_at":    _now(),
    })


# ===========================================================================
# 8. HEALTH CHECK
# ===========================================================================

@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL, "time": _now()}


# ===========================================================================
# 9. HELPERS
# ===========================================================================

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mock_metrics() -> list[TagMetrics]:
    """Returned when DB is unavailable — useful for local dev / smoke tests."""
    return [
        TagMetrics(tag="#भारतvsऑस्ट्रेलिया", current_2h_posts=980,  prev_2h_posts=None,   avg_2h_posts_7d=None,   avg_likes_24h=22.0, avg_shares_24h=8.0,  avg_comments_24h=5.0, avg_likes_7d=None, searches_today=4400, avg_searches_7d=None),
        TagMetrics(tag="#MumbaiRains",         current_2h_posts=560,  prev_2h_posts=40.0,   avg_2h_posts_7d=30.0,   avg_likes_24h=12.0, avg_shares_24h=4.0,  avg_comments_24h=3.0, avg_likes_7d=5.0,  searches_today=2800, avg_searches_7d=200.0),
        TagMetrics(tag="#IPL2026",             current_2h_posts=720,  prev_2h_posts=90.0,   avg_2h_posts_7d=95.0,   avg_likes_24h=20.0, avg_shares_24h=7.0,  avg_comments_24h=4.0, avg_likes_7d=8.0,  searches_today=3100, avg_searches_7d=430.0),
        TagMetrics(tag="#NewMovie2026",        current_2h_posts=310,  prev_2h_posts=None,   avg_2h_posts_7d=None,   avg_likes_24h=18.0, avg_shares_24h=6.0,  avg_comments_24h=4.0, avg_likes_7d=None, searches_today=870,  avg_searches_7d=None),
        TagMetrics(tag="#BudgetSession",       current_2h_posts=430,  prev_2h_posts=60.0,   avg_2h_posts_7d=50.0,   avg_likes_24h=9.0,  avg_shares_24h=3.0,  avg_comments_24h=2.0, avg_likes_7d=6.0,  searches_today=1900, avg_searches_7d=300.0),
        TagMetrics(tag="#NordicSkiChampion",   current_2h_posts=25,   prev_2h_posts=20.0,   avg_2h_posts_7d=22.0,   avg_likes_24h=2.0,  avg_shares_24h=0.5,  avg_comments_24h=0.3, avg_likes_7d=2.0,  searches_today=30,   avg_searches_7d=25.0),
        TagMetrics(tag="#TechLayoffs",         current_2h_posts=330,  prev_2h_posts=60.0,   avg_2h_posts_7d=40.0,   avg_likes_24h=15.0, avg_shares_24h=5.0,  avg_comments_24h=3.0, avg_likes_7d=9.0,  searches_today=1200, avg_searches_7d=300.0),
        TagMetrics(tag="#SpaceXLaunch",        current_2h_posts=145,  prev_2h_posts=50.0,   avg_2h_posts_7d=None,   avg_likes_24h=14.0, avg_shares_24h=5.0,  avg_comments_24h=2.0, avg_likes_7d=None, searches_today=600,  avg_searches_7d=None),
        TagMetrics(tag="#GoodMorning",         current_2h_posts=1500, prev_2h_posts=1480.0, avg_2h_posts_7d=1450.0, avg_likes_24h=4.0,  avg_shares_24h=1.0,  avg_comments_24h=0.5, avg_likes_7d=4.2,  searches_today=3000, avg_searches_7d=2950.0),
        TagMetrics(tag="#StartupExit",         current_2h_posts=200,  prev_2h_posts=85.0,   avg_2h_posts_7d=70.0,   avg_likes_24h=11.0, avg_shares_24h=4.0,  avg_comments_24h=2.0, avg_likes_7d=6.0,  searches_today=500,  avg_searches_7d=180.0),
    ]


def _mock_feed(tag: str) -> list[dict]:
    return [
        {"post_id": "p001", "display_name": "Rahul M", "avatar_url": None,
         "content": f"क्या शानदार मैच! {tag} 🔥", "image_url": "https://images.unsplash.com/photo-1531415074968-036ba1b575da?w=400&q=70",
         "video_url": None, "likes": 5100, "shares": 1800, "comments": 1240, "created_at": _now()},
        {"post_id": "p002", "display_name": "Priya S", "avatar_url": None,
         "content": f"बेहतरीन प्रदर्शन {tag}", "image_url": None,
         "video_url": None, "likes": 2800, "shares": 790, "comments": 610, "created_at": _now()},
    ]


# ===========================================================================
# 10. RUN (dev)
# ===========================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
