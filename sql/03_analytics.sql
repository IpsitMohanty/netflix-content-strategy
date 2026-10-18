-- =====================================================================
-- Step 3 - Analytical tables for the dashboard  (MySQL 8)
-- Source tables: dim_title (1 row/title), bridge_genre, bridge_country
--
-- GRAIN RULES
--   * Title counts / KPIs         -> dim_title only
--   * Genre counts                -> COUNT(DISTINCT show_id) via bridge_genre.
--                                    A title in 3 genres counts once in EACH,
--                                    so genre totals exceed the title total.
--   * Country counts              -> bridge_country (all producing countries).
--                                    'Unknown' is excluded from country analysis.
-- Safe to re-run: every table is dropped and rebuilt.
-- =====================================================================

-- ---------- A. PORTFOLIO ----------
DROP TABLE IF EXISTS agg_genre;
CREATE TABLE agg_genre AS
SELECT g.genre, COUNT(DISTINCT g.show_id) AS titles
FROM bridge_genre g
GROUP BY g.genre;

DROP TABLE IF EXISTS agg_genre_type;
CREATE TABLE agg_genre_type AS
SELECT g.genre, t.type, COUNT(DISTINCT g.show_id) AS titles
FROM bridge_genre g
JOIN dim_title t ON t.show_id = g.show_id
GROUP BY g.genre, t.type;

DROP TABLE IF EXISTS agg_genre_pairs;
CREATE TABLE agg_genre_pairs AS
SELECT a.genre AS genre_a, b.genre AS genre_b, COUNT(*) AS titles
FROM bridge_genre a
JOIN bridge_genre b ON a.show_id = b.show_id AND a.genre < b.genre
GROUP BY a.genre, b.genre;

DROP TABLE IF EXISTS agg_country;
CREATE TABLE agg_country AS
SELECT c.country,
       COUNT(DISTINCT c.show_id) AS titles,
       ROUND(100.0 * COUNT(DISTINCT c.show_id) / (SELECT COUNT(*) FROM dim_title), 2) AS pct_of_titles
FROM bridge_country c
WHERE c.country <> 'Unknown'
GROUP BY c.country;

DROP TABLE IF EXISTS agg_country_type;
CREATE TABLE agg_country_type AS
SELECT c.country, t.type, COUNT(DISTINCT c.show_id) AS titles
FROM bridge_country c
JOIN dim_title t ON t.show_id = c.show_id
WHERE c.country <> 'Unknown'
GROUP BY c.country, t.type;

DROP TABLE IF EXISTS agg_country_genre;
CREATE TABLE agg_country_genre AS
SELECT c.country, g.genre, COUNT(DISTINCT c.show_id) AS titles
FROM bridge_country c
JOIN bridge_genre g ON g.show_id = c.show_id
WHERE c.country <> 'Unknown'
GROUP BY c.country, g.genre;

-- ---------- B. RATINGS ----------
DROP TABLE IF EXISTS agg_rating;
CREATE TABLE agg_rating AS
SELECT rating, COUNT(*) AS titles
FROM dim_title
GROUP BY rating;

DROP TABLE IF EXISTS agg_rating_type;
CREATE TABLE agg_rating_type AS
SELECT rating, type, COUNT(*) AS titles
FROM dim_title
GROUP BY rating, type;

DROP TABLE IF EXISTS agg_rating_genre;
CREATE TABLE agg_rating_genre AS
SELECT t.rating, g.genre, COUNT(DISTINCT g.show_id) AS titles
FROM bridge_genre g
JOIN dim_title t ON t.show_id = g.show_id
GROUP BY t.rating, g.genre;

DROP TABLE IF EXISTS agg_rating_country;
CREATE TABLE agg_rating_country AS
SELECT t.rating, c.country, COUNT(DISTINCT c.show_id) AS titles
FROM bridge_country c
JOIN dim_title t ON t.show_id = c.show_id
WHERE c.country <> 'Unknown'
GROUP BY t.rating, c.country;

-- ---------- C. FRESHNESS ----------
DROP TABLE IF EXISTS agg_age_group_type;
CREATE TABLE agg_age_group_type AS
SELECT type, content_age_group, COUNT(*) AS titles,
       ROUND(AVG(content_age), 1) AS avg_content_age
FROM dim_title
GROUP BY type, content_age_group;

DROP TABLE IF EXISTS agg_genre_freshness;
CREATE TABLE agg_genre_freshness AS
SELECT g.genre,
       COUNT(DISTINCT g.show_id)                              AS titles,
       SUM(t.is_recent)                                       AS recent_titles,
       ROUND(100.0 * SUM(t.is_recent) / COUNT(*), 1)          AS recent_pct,
       ROUND(AVG(t.content_age), 1)                           AS avg_content_age
FROM bridge_genre g
JOIN dim_title t ON t.show_id = g.show_id
GROUP BY g.genre;

DROP TABLE IF EXISTS agg_genre_age_group;
CREATE TABLE agg_genre_age_group AS
SELECT g.genre, t.content_age_group, COUNT(DISTINCT g.show_id) AS titles
FROM bridge_genre g
JOIN dim_title t ON t.show_id = g.show_id
GROUP BY g.genre, t.content_age_group;

-- ---------- D. EVOLUTION ----------
DROP TABLE IF EXISTS agg_type_year;
CREATE TABLE agg_type_year AS
SELECT release_year, type, COUNT(*) AS titles
FROM dim_title
GROUP BY release_year, type;

DROP TABLE IF EXISTS agg_type_decade;
CREATE TABLE agg_type_decade AS
SELECT release_decade, type, COUNT(*) AS titles,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY release_decade), 1) AS pct_of_decade
FROM dim_title
GROUP BY release_decade, type;

DROP TABLE IF EXISTS agg_genre_decade;
CREATE TABLE agg_genre_decade AS
SELECT t.release_decade, g.genre, COUNT(DISTINCT g.show_id) AS titles
FROM bridge_genre g
JOIN dim_title t ON t.show_id = g.show_id
GROUP BY t.release_decade, g.genre;

DROP TABLE IF EXISTS agg_country_decade;
CREATE TABLE agg_country_decade AS
SELECT t.release_decade, c.country, COUNT(DISTINCT c.show_id) AS titles
FROM bridge_country c
JOIN dim_title t ON t.show_id = c.show_id
WHERE c.country <> 'Unknown'
GROUP BY t.release_decade, c.country;

DROP TABLE IF EXISTS agg_added_year;
CREATE TABLE agg_added_year AS
SELECT year_added, type, COUNT(*) AS titles
FROM dim_title
WHERE year_added IS NOT NULL
GROUP BY year_added, type;

-- ---------- E. KPI SUMMARY (title grain) ----------
DROP TABLE IF EXISTS kpi_summary;
CREATE TABLE kpi_summary AS
SELECT
    COUNT(*)                                                         AS total_titles,
    SUM(CASE WHEN type = 'Movie'   THEN 1 ELSE 0 END)                AS movies,
    SUM(CASE WHEN type = 'TV Show' THEN 1 ELSE 0 END)                AS tv_shows,
    ROUND(SUM(CASE WHEN type = 'Movie' THEN 1 ELSE 0 END) * 1.0
        / NULLIF(SUM(CASE WHEN type = 'TV Show' THEN 1 ELSE 0 END), 0), 2) AS movie_to_tv_ratio,
    ROUND(100.0 * SUM(CASE WHEN type = 'Movie'   THEN 1 ELSE 0 END) / COUNT(*), 1) AS movie_pct,
    ROUND(100.0 * SUM(CASE WHEN type = 'TV Show' THEN 1 ELSE 0 END) / COUNT(*), 1) AS tv_pct,
    ROUND(AVG(content_age), 1)                                       AS avg_content_age,
    SUM(is_recent)                                                   AS recent_titles,
    ROUND(100.0 * SUM(is_recent) / COUNT(*), 1)                      AS recent_pct,
    (SELECT COUNT(*) FROM agg_genre)                                 AS distinct_genres,
    (SELECT COUNT(*) FROM agg_country)                               AS countries_represented,
    COUNT(DISTINCT rating)                                           AS distinct_ratings,
    (SELECT rating  FROM agg_rating  ORDER BY titles DESC LIMIT 1)   AS top_rating,
    (SELECT country FROM agg_country ORDER BY titles DESC LIMIT 1)   AS top_country
FROM dim_title;

-- ---------- F. VALIDATION (every row should say PASS) ----------
SELECT 'type counts sum to total titles' AS check_name,
       CASE WHEN (SELECT SUM(titles) FROM agg_type_year) = (SELECT total_titles FROM kpi_summary)
            THEN 'PASS' ELSE 'FAIL' END AS result
UNION ALL
SELECT 'rating counts sum to total titles',
       CASE WHEN (SELECT SUM(titles) FROM agg_rating) = (SELECT total_titles FROM kpi_summary)
            THEN 'PASS' ELSE 'FAIL' END
UNION ALL
SELECT 'age-group counts sum to total titles',
       CASE WHEN (SELECT SUM(titles) FROM agg_age_group_type) = (SELECT total_titles FROM kpi_summary)
            THEN 'PASS' ELSE 'FAIL' END
UNION ALL
SELECT 'genre rows >= total titles (multi-genre expected)',
       CASE WHEN (SELECT SUM(titles) FROM agg_genre) >= (SELECT total_titles FROM kpi_summary)
            THEN 'PASS' ELSE 'FAIL' END
UNION ALL
SELECT 'movies + tv = total',
       CASE WHEN (SELECT movies + tv_shows FROM kpi_summary) = (SELECT total_titles FROM kpi_summary)
            THEN 'PASS' ELSE 'FAIL' END
UNION ALL
SELECT 'decade type-shares sum to ~100 per decade',
       CASE WHEN (SELECT MAX(ABS(s - 100)) FROM
                    (SELECT SUM(pct_of_decade) AS s FROM agg_type_decade GROUP BY release_decade) x) < 0.5
            THEN 'PASS' ELSE 'FAIL' END;
