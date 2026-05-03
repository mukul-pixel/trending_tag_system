"""
Trending Tags — FastAPI Backend Service  (v3 — Redis Caching)
=============================================================
Two endpoints:
  GET /get-trending-feed   — ranked, enriched trending tags (Redis-cached, 5 min TTL)
  GET /get-trend-details   — deep-dive for a single tag (hero media, context, feed)

Redis caching strategy
──────────────────────
• The full pipeline (SQL → score → LLM enrich) is expensive.
  Under a sudden spike (app opens at 8 AM for 100k users) every request
  would hit the DB and Claude API simultaneously — caching prevents that.

• Pattern used: Cache-Aside + Distributed Lock + Stale-While-Revalidate
    1. Request arrives → check Redis for CACHE_KEY.
    2. Cache HIT  → return cached payload instantly  [X-Cache: HIT]
    3. Cache MISS → acquire a short-lived LOCK_KEY (SET NX EX 30s).
       • Lock acquired   → run pipeline, write to Redis with 5-min TTL, release lock.
       • Lock NOT acquired (another worker is already recomputing) →
           serve STALE data if available, else wait briefly and retry once.
    4. Redis itself is unavailable → fall through to live pipeline (degrade gracefully).

This means under a thundering-herd scenario only ONE worker runs the
expensive pipeline; every other concurrent request gets the cached result.

Dependencies:
    pip install fastapi uvicorn asyncpg anthropic "redis[hiredis]" python-dotenv
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
import redis.asyncio as aioredis
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

# ── Config ────────────────────────────────────────────────────────────────────
DATABASE_URL  = os.environ.get("DATABASE_URL",  "postgresql://user:pass@localhost/db")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
REDIS_URL     = os.environ.get("REDIS_URL",     "redis://localhost:6379/0")
MODEL         = "claude-sonnet-4-20250514"

# Cache keys & TTLs
FEED_CACHE_KEY  = "trending:feed:hindi"   # stores the final JSON payload
FEED_LOCK_KEY   = "trending:feed:lock"    # distributed lock during recompute
STALE_CACHE_KEY = "trending:feed:stale"   # last-known-good copy, no TTL

FEED_TTL_SECS   = 300    # 5 minutes — all users served from cache until refresh
LOCK_TTL_SECS   = 30     # max seconds a worker can hold the lock
LOCK_WAIT_SECS  = 2      # time a waiting worker sleeps before one retry

MIN_VOLUME_GATE = 10     # minimum 2h posts to enter scoring pipeline
_BASELINE_TTL   = 3600   # 1 hour baseline refresh


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="Trending Tags API", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ===========================================================================
# 1. DATA CONTRACTS
# ===========================================================================

@dataclass
class TagMetrics:
    tag:               str
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
    heat_score:    float = 0.0
    rank:          int   = 0
    spike:         float = 0.0
    volume_log:    float = 0.0
    growth:        float = 0.0
    search_growth: float = 0.0
    engagement:    float = 0.0
    posts_signal:  float = 0.0
    search_signal: float = 0.0
    eng_signal:    float = 0.0


# ===========================================================================
# 2. SCORING ENGINE
# ===========================================================================

def _coalesce(primary: Optional[float], fallback: float) -> float:
    if primary is not None and primary > 0:
        return primary
    return fallback


def score_tag(m: TagMetrics, b: GlobalBaselines) -> Optional[ScoredTag]:
    """
    TrendScore = Spike x log(Volume+1) x Growth x SearchGrowth x Engagement
    Engagement = (likes + 2xshares + 3xcomments) weighted ratio vs 7d baseline.
    """
    if m.current_2h_posts < MIN_VOLUME_GATE:
        return None

    spike      = m.current_2h_posts / _coalesce(m.avg_2h_posts_7d, b.global_avg_2h_posts)
    volume_log = math.log(m.current_2h_posts + 1)
    growth     = m.current_2h_posts / _coalesce(m.prev_2h_posts,   b.global_avg_2h_posts)

    search_growth = (
        max(m.searches_today, 1)
        / _coalesce(m.avg_searches_7d, b.global_avg_searches)
    )

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
        trend_score   = round(trend_score,      6),
        spike         = round(spike,            4),
        volume_log    = round(volume_log,       4),
        growth        = round(growth,           4),
        search_growth = round(search_growth,    4),
        engagement    = round(engagement,       4),
        posts_signal  = round(max(spike, growth), 4),
        search_signal = round(search_growth,    4),
        eng_signal    = round(engagement,       4),
    )


def normalise_heat(scored: list[ScoredTag]) -> list[ScoredTag]:
    if not scored:
        return scored
    lo  = min(s.trend_score for s in scored)
    hi  = max(s.trend_score for s in scored)
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
# 3. PRIMARY SIGNAL — argmax
# ===========================================================================

SIGNAL_THRESHOLDS = {"posts": 2.0, "searches": 2.0, "engagement": 1.5}
SIGNAL_LABELS_HI  = {
    "posts":      "अत्यधिक उपयोग",
    "searches":   "अत्यधिक खोजा गया",
    "engagement": "बहुत लोकप्रिय",
}


def assign_primary_signal(s: ScoredTag) -> str:
    margins = {
        "posts":      s.posts_signal  - SIGNAL_THRESHOLDS["posts"],
        "searches":   s.search_signal - SIGNAL_THRESHOLDS["searches"],
        "engagement": s.eng_signal    - SIGNAL_THRESHOLDS["engagement"],
    }
    above = {k: v for k, v in margins.items() if v > 0}
    if above:
        winner = max(above, key=above.get)
    else:
        raw    = {"posts": s.posts_signal, "searches": s.search_signal, "engagement": s.eng_signal}
        winner = max(raw, key=raw.get)
    return SIGNAL_LABELS_HI[winner]


# ===========================================================================
# 4. LLM CLIENT — guaranteed JSON-only output
# ===========================================================================

class LLMClient:
    def __init__(self, api_key: str = ANTHROPIC_KEY):
        self._client = anthropic.Anthropic(api_key=api_key)

    def _call(self, system: str, user: str, max_tokens: int = 2048) -> str:
        resp = self._client.messages.create(
            model=MODEL, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text.strip()

    @staticmethod
    def _parse_json(raw: str) -> object:
        text = raw
        if text.startswith("```"):
            parts = text.split("```")
            text  = parts[1]
            if text.lower().startswith("json"):
                text = text[4:]
        return json.loads(text.strip())

    def check_relevance_batch(self, tags: list[str]) -> dict[str, int]:
        system = (
            "You are a cultural relevance filter for a Hindi-language social platform in India. "
            "Given hashtags, classify each as 1 (culturally relevant to India) or 0 (obscure global trend). "
            "Return ONLY a JSON object {tag: 0|1}. No markdown, no preamble."
        )
        raw    = self._call(system, "Classify:\n" + "\n".join(tags), max_tokens=512)
        result = self._parse_json(raw)
        return {t: int(result.get(t, 0)) for t in tags}

    def generate_metadata_batch(self, tags: list[str]) -> dict[str, dict]:
        system = (
            "You generate metadata for a Hindi social media platform. "
            "Return a JSON object where each key is a tag and the value has: "
            '"description_hindi" (one punchy Hindi sentence, max 15 words, format: "<tag> - <Hindi context>") '
            'and "category" (one of: Sports, News, Entertainment, Lifestyle, Finance, Tech). '
            "Return ONLY valid JSON. No markdown."
        )
        raw = self._call(system, "Generate metadata for:\n" + "\n".join(tags))
        return self._parse_json(raw)

    def generate_trend_context(self, tag: str, post_count: int, samples: list[str]) -> str:
        system = (
            "You write Hindi content for a social news platform. "
            "Write an paragraph: exactly 50-70 Hindi words, "
            "informative + engaging, flowing prose, no bullet points. "
            "Return ONLY the Hindi paragraph. No JSON, no English."
        )
        sample_text = "\n".join(f"- {p}" for p in samples[:5]) or "No samples."
        user = f"Tag: {tag}\nPosts last 2h: {post_count}\nSamples:\n{sample_text}\n\nWrite the paragraph."
        return self._call(system, user, max_tokens=256)


# ===========================================================================
# 5. REDIS CACHE LAYER
# ===========================================================================

class RedisCache:
    """
    Async Redis cache with three keys per feed:

    Key                   TTL        Purpose
    ─────────────────────────────────────────────────────────────────────────
    trending:feed:hindi   5 min      Primary served payload. Expires naturally.
    trending:feed:stale   none       Last-known-good copy. Never expires.
                                     Served to concurrent requests while a
                                     worker is recomputing under the lock.
    trending:feed:lock    30 s       Distributed mutex. SET NX EX ensures only
                                     one worker runs the expensive pipeline at
                                     a time. Auto-expires to recover from crashes.
    """

    def __init__(self, redis: aioredis.Redis):
        self._r = redis

    # ── Read ─────────────────────────────────────────────────────────────────

    async def get_feed(self) -> Optional[dict]:
        """Return cached feed payload or None on miss / Redis error."""
        try:
            raw = await self._r.get(FEED_CACHE_KEY)
            if raw:
                logger.info("Cache HIT  key=%s", FEED_CACHE_KEY)
                return json.loads(raw)
        except Exception as exc:
            logger.warning("Redis GET failed: %s", exc)
        return None

    async def get_stale_feed(self) -> Optional[dict]:
        """Return stale copy — used while lock is held by another worker."""
        try:
            raw = await self._r.get(STALE_CACHE_KEY)
            if raw:
                logger.info("Serving STALE copy while recompute in progress")
                return json.loads(raw)
        except Exception as exc:
            logger.warning("Redis STALE GET failed: %s", exc)
        return None

    # ── Write ────────────────────────────────────────────────────────────────

    async def set_feed(self, payload: dict) -> None:
        """
        Atomically write fresh payload to both the primary (TTL=5min) and
        the stale (no TTL) keys using a pipeline to avoid partial writes.
        """
        serialised = json.dumps(payload, ensure_ascii=False)
        try:
            pipe = self._r.pipeline()
            pipe.setex(FEED_CACHE_KEY,  FEED_TTL_SECS, serialised)  # expires in 5 min
            pipe.set(STALE_CACHE_KEY,   serialised)                  # never expires
            await pipe.execute()
            logger.info(
                "Cache SET  key=%s  TTL=%ds  bytes=%d",
                FEED_CACHE_KEY, FEED_TTL_SECS, len(serialised),
            )
        except Exception as exc:
            logger.error("Redis SET failed (result still returned): %s", exc)

    # ── Distributed lock ─────────────────────────────────────────────────────

    async def acquire_lock(self) -> bool:
        """
        Atomic SET NX EX — returns True if this worker won the lock.

        NX  = set only if key does NOT exist  (exactly one winner)
        EX  = auto-expire after LOCK_TTL_SECS (protects against crashed workers)
        """
        try:
            result = await self._r.set(
                FEED_LOCK_KEY, "1",
                nx=True,           # only set if NOT exists
                ex=LOCK_TTL_SECS,  # auto-release after 30s
            )
            acquired = result is True
            logger.info("Lock %s  key=%s", "ACQUIRED" if acquired else "CONTESTED", FEED_LOCK_KEY)
            return acquired
        except Exception as exc:
            # Redis down: allow worker to proceed rather than hang indefinitely
            logger.warning("Redis lock acquire failed (%s) — proceeding unlocked", exc)
            return True

    async def release_lock(self) -> None:
        try:
            await self._r.delete(FEED_LOCK_KEY)
            logger.info("Lock RELEASED  key=%s", FEED_LOCK_KEY)
        except Exception as exc:
            # Lock has LOCK_TTL_SECS auto-expiry — safe to ignore release failure
            logger.warning("Redis lock release failed (will auto-expire): %s", exc)

    async def ttl(self) -> int:
        """Seconds remaining on the primary cache key. -2 = key not set."""
        try:
            return await self._r.ttl(FEED_CACHE_KEY)
        except Exception:
            return -2


# ===========================================================================
# 6. SINGLETONS — initialised once at startup
# ===========================================================================

_db_pool:         Optional[asyncpg.Pool]  = None
_redis_client:    Optional[aioredis.Redis] = None
_cache:           Optional[RedisCache]     = None
_llm:             Optional[LLMClient]      = None
_baselines_cache: Optional[GlobalBaselines] = None


@app.on_event("startup")
async def startup():
    global _db_pool, _redis_client, _cache, _llm

    _llm = LLMClient()
    logger.info("LLMClient ready")

    try:
        _db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
        logger.info("DB pool ready")
    except Exception as exc:
        logger.warning("DB unavailable (%s) — using mock data", exc)

    try:
        _redis_client = aioredis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,   # fail fast — don't block startup
            socket_timeout=2,
        )
        await _redis_client.ping()
        _cache = RedisCache(_redis_client)
        logger.info("Redis ready  url=%s", REDIS_URL)
    except Exception as exc:
        logger.warning("Redis unavailable (%s) — caching disabled", exc)
        _cache = None


@app.on_event("shutdown")
async def shutdown():
    if _db_pool:
        await _db_pool.close()
    if _redis_client:
        await _redis_client.aclose()


# ===========================================================================
# 7. DATABASE HELPERS
# ===========================================================================

async def fetch_tag_metrics() -> list[TagMetrics]:
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
    global _baselines_cache
    if _baselines_cache and (time.time() - _baselines_cache.cached_at) < _BASELINE_TTL:
        return _baselines_cache
    if not _db_pool:
        _baselines_cache = GlobalBaselines()
        return _baselines_cache
    row = await _db_pool.fetchrow("""
        SELECT AVG(current_2h_posts) AS global_avg_2h_posts,
               AVG(searches_today)   AS global_avg_searches,
               AVG(avg_likes_24h)    AS global_avg_likes,
               AVG(avg_shares_24h)   AS global_avg_shares,
               AVG(avg_comments_24h) AS global_avg_comments
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
    if not _db_pool:
        return {"image_url": "https://images.unsplash.com/photo-1531415074968-036ba1b575da?w=800&q=80",
                "video_url": None, "likes": 5100, "shares": 1800, "comments": 1240, "engagement_score": 8140}
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
    if not _db_pool:
        return _mock_feed(tag)
    rows = await _db_pool.fetch("""
        SELECT p.post_id, p.user_id, u.display_name, u.avatar_url,
               p.content, p.image_url, p.video_url,
               p.likes, p.shares, p.comments, p.created_at
        FROM   posts p
        INNER JOIN users u ON u.user_id = p.user_id
        INNER JOIN (SELECT user_id FROM users WHERE language='hindi') hf
               ON hf.user_id = p.user_id
        WHERE  $1 = ANY(p.tags)
        ORDER  BY p.created_at DESC
        LIMIT  $2
    """, tag, limit)
    return [dict(r) for r in rows]


async def fetch_post_text_samples(tag: str, n: int = 5) -> list[str]:
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
# 8. PIPELINE  — expensive; runs at most once per FEED_TTL_SECS
# ===========================================================================

async def _run_pipeline(limit: int) -> dict:
    """
    Full SQL -> score -> LLM enrich pipeline.
    Called only when the cache is cold AND this worker holds the lock.
    """
    t0 = time.perf_counter()

    metrics   = await fetch_tag_metrics()
    baselines = await fetch_global_baselines()
    scored    = rank_tags(metrics, baselines, top_n=limit * 2)

    if not scored:
        return {"tags": [], "total_scored": 0, "total_relevant": 0,
                "generated_at": _now(), "pipeline_ms": 0}

    tags_list = [s.tag for s in scored]

    # Step A-1: Relevance filter (LLM)
    try:
        relevance = _llm.check_relevance_batch(tags_list)
    except Exception as exc:
        logger.error("Relevance check failed: %s", exc)
        relevance = {t: 1 for t in tags_list}

    relevant = [s for s in scored if relevance.get(s.tag, 0) == 1]

    # Step A-2: Hindi description + category (LLM)
    try:
        metadata = _llm.generate_metadata_batch([s.tag for s in relevant])
    except Exception as exc:
        logger.error("Metadata generation failed: %s", exc)
        metadata = {s.tag: {"description_hindi": f"{s.tag} — विवरण उपलब्ध नहीं।",
                             "category": "News"} for s in relevant}

    # Step B: Primary signal (pure Python)
    output = []
    for s in relevant[:limit]:
        meta = metadata.get(s.tag, {})
        output.append({
            "rank":              s.rank,
            "tag":               s.tag,
            "description_hindi": meta.get("description_hindi", f"{s.tag} — विवरण उपलब्ध नहीं।"),
            "category":          meta.get("category", "News"),
            "heat_score":        s.heat_score,
            "primary_signal":    assign_primary_signal(s),
            "score_breakdown": {
                "spike":         s.spike,
                "growth":        s.growth,
                "search_growth": s.search_growth,
                "engagement":    s.engagement,
            },
        })

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    logger.info("Pipeline done  %dms  tags=%d", elapsed_ms, len(output))

    return {
        "tags":           output,
        "total_scored":   len(scored),
        "total_relevant": len(relevant),
        "generated_at":   _now(),
        "pipeline_ms":    elapsed_ms,
    }


# ===========================================================================
# 9. ENDPOINT #1: GET /get-trending-feed  (Redis-cached, 5-min TTL)
# ===========================================================================

@app.get("/get-trending-feed")
async def get_trending_feed(limit: int = Query(default=10, ge=1, le=30)):
    """
    Cache-Aside + Distributed Lock + Stale-While-Revalidate

    Decision tree for every incoming request:

        Redis offline?
          YES  -> run pipeline live, return  [X-Cache: BYPASS]

        Cache HIT?
          YES  -> return cached payload      [X-Cache: HIT]

        Cache MISS + lock acquired?
          YES  -> run pipeline, write cache, [X-Cache: MISS]
                  release lock, return

        Cache MISS + lock CONTESTED?
          stale copy exists? -> return stale [X-Cache: STALE]
          no stale?          -> sleep 2s, retry cache once
            cache now populated? -> return  [X-Cache: HIT]
            still empty?         -> run pipeline as last resort

    Result: under a thundering herd, only ONE worker runs the expensive
    pipeline. Every other concurrent request gets the cached result with
    zero additional DB or LLM cost.
    """

    # ── Redis offline: degrade gracefully ────────────────────────────────
    if _cache is None:
        logger.warning("Redis offline — live pipeline (no cache)")
        payload = await _run_pipeline(limit)
        payload["cache_status"] = "BYPASS"
        return JSONResponse(content=payload, headers={"X-Cache": "BYPASS", "X-Cache-TTL": "0"})

    # ── Cache HIT ─────────────────────────────────────────────────────────
    cached = await _cache.get_feed()
    if cached is not None:
        remaining = await _cache.ttl()
        cached["cache_status"] = "HIT"
        return JSONResponse(
            content=cached,
            headers={"X-Cache": "HIT", "X-Cache-TTL": str(max(remaining, 0))},
        )

    # ── Cache MISS: race for the recompute lock ────────────────────────
    lock_acquired = await _cache.acquire_lock()

    if not lock_acquired:
        # Another worker holds the lock and is recomputing right now.
        # Serve stale immediately — no point waiting when we have prior data.
        stale = await _cache.get_stale_feed()
        if stale is not None:
            stale["cache_status"] = "STALE"
            return JSONResponse(
                content=stale,
                headers={"X-Cache": "STALE", "X-Cache-TTL": "0"},
            )

        # First-ever cold start under high concurrency — no stale data yet.
        # Sleep briefly and retry once before giving up and running ourselves.
        logger.info("No stale data — waiting %.1fs for lock holder to finish", LOCK_WAIT_SECS)
        await asyncio.sleep(LOCK_WAIT_SECS)
        fresh = await _cache.get_feed()
        if fresh is not None:
            fresh["cache_status"] = "HIT_AFTER_WAIT"
            return JSONResponse(
                content=fresh,
                headers={"X-Cache": "HIT", "X-Cache-TTL": str(FEED_TTL_SECS)},
            )
        logger.warning("Lock wait expired with no data — running pipeline as fallback")

    # ── Lock held (or Redis lock unavailable): run the pipeline ──────────
    try:
        payload = await _run_pipeline(limit)
        payload["cache_status"] = "MISS"
        await _cache.set_feed(payload)          # write primary + stale atomically
        return JSONResponse(
            content=payload,
            headers={"X-Cache": "MISS", "X-Cache-TTL": str(FEED_TTL_SECS)},
        )
    finally:
        # Always release — even if _run_pipeline raised an exception
        if lock_acquired:
            await _cache.release_lock()


# ===========================================================================
# 10. ENDPOINT #2: GET /get-trend-details  (live — per-tag, not cached)
# ===========================================================================

@app.get("/get-trend-details")
async def get_trend_details(tag_name: str = Query(..., description="e.g. #IPL2026")):
    if not tag_name.startswith("#"):
        tag_name = f"#{tag_name}"

    hero_result, feed_result, sample_result = await asyncio.gather(
        fetch_hero_media(tag_name),
        fetch_related_feed(tag_name),
        fetch_post_text_samples(tag_name),
        return_exceptions=True,
    )
    hero    = hero_result   if not isinstance(hero_result,   Exception) else None
    feed    = feed_result   if not isinstance(feed_result,   Exception) else []
    samples = sample_result if not isinstance(sample_result, Exception) else []

    try:
        context_hindi = _llm.generate_trend_context(tag_name, len(feed or []), samples)
    except Exception as exc:
        logger.error("Context generation failed: %s", exc)
        context_hindi = f"{tag_name} इस समय भारत में चर्चा में है।"

    serialised_feed = []
    for p in (feed or []):
        entry = dict(p)
        if isinstance(entry.get("created_at"), datetime):
            entry["created_at"] = entry["created_at"].isoformat()
        serialised_feed.append(entry)

    return JSONResponse(content={
        "tag":           tag_name,
        "hero_media":    hero,
        "context_hindi": context_hindi,
        "related_feed":  serialised_feed,
        "generated_at":  _now(),
    })


# ===========================================================================
# 11. CACHE MANAGEMENT ENDPOINTS
# ===========================================================================

@app.get("/cache/status")
async def cache_status():
    """Inspect current cache state — for ops dashboards."""
    if _cache is None:
        return {"redis": "offline", "feed_cached": False}
    ttl = await _cache.ttl()
    return {
        "redis":         "online",
        "feed_cached":   ttl > 0,
        "ttl_seconds":   ttl,
        "ttl_human":     f"{ttl}s remaining" if ttl > 0 else "expired / not set",
        "feed_key":      FEED_CACHE_KEY,
        "stale_key":     STALE_CACHE_KEY,
        "lock_key":      FEED_LOCK_KEY,
        "feed_ttl_cfg":  FEED_TTL_SECS,
    }


@app.post("/cache/invalidate")
async def cache_invalidate():
    """
    Force-expire the feed cache.
    Use after manual data corrections or LLM prompt changes.
    Protect with auth middleware in production.
    """
    if _cache is None:
        return {"invalidated": False, "reason": "Redis offline"}
    try:
        deleted = await _redis_client.delete(FEED_CACHE_KEY)
        logger.info("Cache manually invalidated  deleted=%d", deleted)
        return {"invalidated": bool(deleted), "key": FEED_CACHE_KEY,
                "note": "stale copy retained for in-flight requests"}
    except Exception as exc:
        return {"invalidated": False, "reason": str(exc)}


# ===========================================================================
# 12. HEALTH CHECK
# ===========================================================================

@app.get("/health")
async def health():
    redis_ok = False
    if _redis_client:
        try:
            await _redis_client.ping()
            redis_ok = True
        except Exception:
            pass
    return {
        "status": "ok",
        "db":     "online" if _db_pool  else "offline (mock data)",
        "redis":  "online" if redis_ok  else "offline (bypass mode)",
        "model":  MODEL,
        "time":   _now(),
    }


# ===========================================================================
# 13. HELPERS + MOCK DATA
# ===========================================================================

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mock_metrics() -> list[TagMetrics]:
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
         "content": f"क्या शानदार मैच! {tag}", "image_url": "https://images.unsplash.com/photo-1531415074968-036ba1b575da?w=400&q=70",
         "video_url": None, "likes": 5100, "shares": 1800, "comments": 1240, "created_at": _now()},
        {"post_id": "p002", "display_name": "Priya S", "avatar_url": None,
         "content": f"बेहतरीन प्रदर्शन {tag}", "image_url": None,
         "video_url": None, "likes": 2800, "shares": 790, "comments": 610, "created_at": _now()},
    ]


# ===========================================================================
# 14. RUN (dev)
# ===========================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
