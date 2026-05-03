-- =============================================================================
-- trending_tags_queries.sql
-- Optimised PostgreSQL queries for the Trending Tags scoring pipeline.
-- All queries filter posts to Hindi-speaking users only.
-- Designed to be run on a scheduler (every 15–30 min) and written into
-- the `tag_trend_metrics` materialised staging table.
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 0. PREREQUISITE INDEXES
--    Run once at schema setup; critical for query performance.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_posts_created_at   ON posts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_user_id       ON posts (user_id);
CREATE INDEX IF NOT EXISTS idx_users_language      ON users (language);
CREATE INDEX IF NOT EXISTS idx_searches_timestamp  ON searches (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_searches_user_id    ON searches (user_id);

-- GIN index for tag array lookups (if tags is text[])
CREATE INDEX IF NOT EXISTS idx_posts_tags_gin ON posts USING GIN (tags);


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. TAG TREND METRICS  (writes into staging table every 15–30 min)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO tag_trend_metrics (
    tag,
    current_2h_posts,
    prev_2h_posts,
    avg_2h_posts_7d,
    avg_likes_24h,
    avg_shares_24h,
    avg_comments_24h,
    avg_likes_7d,
    avg_shares_7d,
    avg_comments_7d,
    searches_today,
    avg_searches_7d,
    computed_at
)
WITH

-- ── Filter: Hindi users only ──────────────────────────────────────────────
hindi_users AS (
    SELECT user_id
    FROM   users
    WHERE  language = 'hindi'
),

-- ── Explode tag arrays, join to Hindi users ───────────────────────────────
-- Posts table has: tags (text[]), created_at, likes, shares, comments,
--                  image_url, video_url
hindi_posts AS (
    SELECT
        UNNEST(p.tags) AS tag,
        p.post_id,
        p.created_at,
        p.likes,
        p.shares,
        p.comments
    FROM   posts       p
    INNER JOIN hindi_users u ON u.user_id = p.user_id
    -- Outer window covers all time ranges we need in one scan
    WHERE  p.created_at >= NOW() - INTERVAL '7 days'
),

-- ── 2-hour volume windows ─────────────────────────────────────────────────

-- Current burst: last 2 hours
current_2h AS (
    SELECT tag, COUNT(*) AS current_2h_posts
    FROM   hindi_posts
    WHERE  created_at >= NOW() - INTERVAL '2 hours'
    GROUP  BY tag
),

-- Previous 2-hour slots in the last 24h (excluding current 2h) — 11 slots
-- Used for Growth = current_2h / prev_2h
prev_2h AS (
    SELECT
        tag,
        -- Average posts across all completed 2h slots in last 22h
        COUNT(*) * 1.0 / 11 AS prev_2h_posts
    FROM   hindi_posts
    WHERE  created_at >= NOW() - INTERVAL '24 hours'
      AND  created_at <  NOW() - INTERVAL '2 hours'
    GROUP  BY tag
),

-- 7-day average 2h volume: total posts ÷ 84 slots (7 days × 12 slots/day)
-- Used for Spike = current_2h / avg_2h_7d
avg_2h_7d AS (
    SELECT
        tag,
        COUNT(*) * 1.0 / 84 AS avg_2h_posts_7d
    FROM   hindi_posts
    WHERE  created_at >= NOW() - INTERVAL '7 days'
    GROUP  BY tag
),

-- ── Engagement signals ────────────────────────────────────────────────────

-- 24h window: average likes, shares, comments per post
engagement_24h AS (
    SELECT
        tag,
        AVG(likes)    AS avg_likes_24h,
        AVG(shares)   AS avg_shares_24h,
        AVG(comments) AS avg_comments_24h
    FROM   hindi_posts
    WHERE  created_at >= NOW() - INTERVAL '24 hours'
    GROUP  BY tag
),

-- 7d window: baseline average likes, shares, comments per post
engagement_7d AS (
    SELECT
        tag,
        AVG(likes)    AS avg_likes_7d,
        AVG(shares)   AS avg_shares_7d,
        AVG(comments) AS avg_comments_7d
    FROM   hindi_posts
    WHERE  created_at >= NOW() - INTERVAL '7 days'
    GROUP  BY tag
),

-- ── Search signals ────────────────────────────────────────────────────────

-- Total searches today by Hindi users
searches_today_cte AS (
    SELECT
        s.tag_query          AS tag,
        COUNT(*)             AS searches_today
    FROM   searches    s
    INNER JOIN hindi_users u ON u.user_id = s.user_id
    WHERE  s.timestamp >= CURRENT_DATE
    GROUP  BY s.tag_query
),

-- 7-day average daily searches
searches_7d_cte AS (
    SELECT
        s.tag_query              AS tag,
        COUNT(*) * 1.0 / 7      AS avg_searches_7d
    FROM   searches    s
    INNER JOIN hindi_users u ON u.user_id = s.user_id
    WHERE  s.timestamp >= NOW() - INTERVAL '7 days'
    GROUP  BY s.tag_query
)

-- ── Final join — left joins so tags with no history still appear ──────────
SELECT
    c.tag,
    c.current_2h_posts,
    p.prev_2h_posts,
    a.avg_2h_posts_7d,
    COALESCE(e24.avg_likes_24h,    0)  AS avg_likes_24h,
    COALESCE(e24.avg_shares_24h,   0)  AS avg_shares_24h,
    COALESCE(e24.avg_comments_24h, 0)  AS avg_comments_24h,
    e7d.avg_likes_7d,
    e7d.avg_shares_7d,
    e7d.avg_comments_7d,
    COALESCE(st.searches_today, 0)     AS searches_today,
    s7.avg_searches_7d,
    NOW()                              AS computed_at
FROM  current_2h          c
LEFT  JOIN prev_2h        p   ON p.tag  = c.tag
LEFT  JOIN avg_2h_7d      a   ON a.tag  = c.tag
LEFT  JOIN engagement_24h e24 ON e24.tag = c.tag
LEFT  JOIN engagement_7d  e7d ON e7d.tag = c.tag
LEFT  JOIN searches_today_cte st ON st.tag = c.tag
LEFT  JOIN searches_7d_cte    s7 ON s7.tag = c.tag
WHERE  c.current_2h_posts >= 10   -- minimum volume gate: suppress noise / spam

ON CONFLICT (tag) DO UPDATE SET
    current_2h_posts  = EXCLUDED.current_2h_posts,
    prev_2h_posts     = EXCLUDED.prev_2h_posts,
    avg_2h_posts_7d   = EXCLUDED.avg_2h_posts_7d,
    avg_likes_24h     = EXCLUDED.avg_likes_24h,
    avg_shares_24h    = EXCLUDED.avg_shares_24h,
    avg_comments_24h  = EXCLUDED.avg_comments_24h,
    avg_likes_7d      = EXCLUDED.avg_likes_7d,
    avg_shares_7d     = EXCLUDED.avg_shares_7d,
    avg_comments_7d   = EXCLUDED.avg_comments_7d,
    searches_today    = EXCLUDED.searches_today,
    avg_searches_7d   = EXCLUDED.avg_searches_7d,
    computed_at       = EXCLUDED.computed_at;


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. GLOBAL BASELINES  (recomputed hourly, cached in app memory)
-- ─────────────────────────────────────────────────────────────────────────────

SELECT
    AVG(current_2h_posts)  AS global_avg_2h_posts,
    AVG(searches_today)    AS global_avg_searches,
    AVG(avg_likes_24h)     AS global_avg_likes,
    AVG(avg_shares_24h)    AS global_avg_shares,
    AVG(avg_comments_24h)  AS global_avg_comments
FROM tag_trend_metrics
WHERE computed_at >= NOW() - INTERVAL '1 hour';


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. HERO IMAGE/VIDEO FETCH  (used by /get-trend-details)
--    Returns the single most-engaged post for a given tag.
--    Engagement rank: likes + shares + comments
-- ─────────────────────────────────────────────────────────────────────────────

-- :tag_name is the bound parameter (e.g. '#IPL2026')
SELECT
    p.post_id,
    p.image_url,
    p.video_url,
    (p.likes + p.shares + p.comments)  AS engagement_score,
    p.likes,
    p.shares,
    p.comments
FROM   posts p
INNER JOIN hindi_users_view u ON u.user_id = p.user_id   -- reusable view
WHERE  :tag_name = ANY(p.tags)
  AND  p.created_at >= NOW() - INTERVAL '24 hours'
  AND  (p.image_url IS NOT NULL OR p.video_url IS NOT NULL)
ORDER  BY engagement_score DESC
LIMIT  1;


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. RELATED FEED  (used by /get-trend-details — mini-feed for trend page)
--    Most recent posts for a tag, with engagement counts.
-- ─────────────────────────────────────────────────────────────────────────────

SELECT
    p.post_id,
    p.user_id,
    u_profile.display_name,
    u_profile.avatar_url,
    p.content,
    p.image_url,
    p.video_url,
    p.likes,
    p.shares,
    p.comments,
    p.created_at
FROM   posts        p
INNER JOIN users    u_profile ON u_profile.user_id = p.user_id
INNER JOIN (SELECT user_id FROM users WHERE language = 'hindi') hf
        ON hf.user_id = p.user_id
WHERE  :tag_name = ANY(p.tags)
ORDER  BY p.created_at DESC
LIMIT  20;


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. HELPER VIEW: hindi_users_view  (create once, used in queries 3 & 4)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW hindi_users_view AS
    SELECT user_id FROM users WHERE language = 'hindi';
