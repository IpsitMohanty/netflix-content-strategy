CREATE DATABASE IF NOT EXISTS netflix_db;
USE netflix_db;

-- The existing demo should already contain clean_netflix.
-- The table is expected to contain:
-- show_id, type, title, director, cast, country, date_added,
-- release_year, rating, duration, listed_in, description,
-- content_age, primary_country, genre

DROP TABLE IF EXISTS content_strategy_base;

CREATE TABLE content_strategy_base AS
SELECT
    show_id,
    title,
    type,
    primary_country,
    release_year,
    rating,
    genre,
    content_age,
    CASE
        WHEN content_age <= 2 THEN 'Very Recent'
        WHEN content_age <= 5 THEN 'Recent'
        WHEN content_age <= 10 THEN 'Mature'
        WHEN content_age <= 20 THEN 'Older'
        ELSE 'Legacy'
    END AS content_age_group,
    FLOOR(release_year / 10) * 10 AS release_decade,
    CASE
        WHEN content_age <= 5 THEN 1
        ELSE 0
    END AS is_recent
FROM clean_netflix
WHERE release_year IS NOT NULL
  AND release_year >= 2008;

-- One row per title for title-level KPIs.
DROP TABLE IF EXISTS content_title_level;

CREATE TABLE content_title_level AS
SELECT
    show_id,
    MAX(title) AS title,
    MAX(type) AS type,
    MAX(primary_country) AS primary_country,
    MAX(release_year) AS release_year,
    MAX(rating) AS rating,
    MAX(content_age) AS content_age,
    MAX(
        CASE
            WHEN content_age <= 2 THEN 'Very Recent'
            WHEN content_age <= 5 THEN 'Recent'
            WHEN content_age <= 10 THEN 'Mature'
            WHEN content_age <= 20 THEN 'Older'
            ELSE 'Legacy'
        END
    ) AS content_age_group,
    MAX(FLOOR(release_year / 10) * 10) AS release_decade,
    MAX(CASE WHEN content_age <= 5 THEN 1 ELSE 0 END) AS is_recent
FROM content_strategy_base
GROUP BY show_id;

-- 1. Content by release year
DROP TABLE IF EXISTS agg_release_year;
CREATE TABLE agg_release_year AS
SELECT
    release_year,
    COUNT(*) AS title_count
FROM content_title_level
GROUP BY release_year
ORDER BY release_year;

-- 2. Content by release decade
DROP TABLE IF EXISTS agg_release_decade;
CREATE TABLE agg_release_decade AS
SELECT
    release_decade,
    COUNT(*) AS title_count
FROM content_title_level
GROUP BY release_decade
ORDER BY release_decade;

-- 3. Content type
DROP TABLE IF EXISTS agg_content_type;
CREATE TABLE agg_content_type AS
SELECT
    type,
    COUNT(*) AS title_count
FROM content_title_level
GROUP BY type;

-- 4. Ratings
DROP TABLE IF EXISTS agg_rating;
CREATE TABLE agg_rating AS
SELECT
    rating,
    COUNT(*) AS title_count
FROM content_title_level
GROUP BY rating
ORDER BY title_count DESC;

-- 5. Content age groups
DROP TABLE IF EXISTS agg_age_group;
CREATE TABLE agg_age_group AS
SELECT
    content_age_group,
    COUNT(*) AS title_count,
    ROUND(AVG(content_age), 1) AS avg_content_age
FROM content_title_level
GROUP BY content_age_group;

-- 6. Genres
DROP TABLE IF EXISTS agg_genre;
CREATE TABLE agg_genre AS
SELECT
    genre,
    COUNT(DISTINCT show_id) AS title_count
FROM content_strategy_base
GROUP BY genre
ORDER BY title_count DESC;

-- 7. Genre x content type
DROP TABLE IF EXISTS agg_genre_type;
CREATE TABLE agg_genre_type AS
SELECT
    genre,
    type,
    COUNT(DISTINCT show_id) AS title_count
FROM content_strategy_base
GROUP BY genre, type
ORDER BY genre, type;

-- 8. Country
DROP TABLE IF EXISTS agg_country;
CREATE TABLE agg_country AS
SELECT
    primary_country,
    COUNT(*) AS title_count
FROM content_title_level
WHERE primary_country IS NOT NULL
  AND primary_country <> 'Unknown'
GROUP BY primary_country
ORDER BY title_count DESC;

-- 9. Country x genre
DROP TABLE IF EXISTS agg_country_genre;
CREATE TABLE agg_country_genre AS
SELECT
    primary_country,
    genre,
    COUNT(DISTINCT show_id) AS title_count
FROM content_strategy_base
WHERE primary_country IS NOT NULL
  AND primary_country <> 'Unknown'
GROUP BY primary_country, genre;

-- 10. Genre freshness
DROP TABLE IF EXISTS agg_genre_freshness;
CREATE TABLE agg_genre_freshness AS
SELECT
    genre,
    COUNT(DISTINCT show_id) AS title_count,
    SUM(CASE WHEN is_recent = 1 THEN 1 ELSE 0 END) AS recent_title_count,
    ROUND(
        100.0 * SUM(CASE WHEN is_recent = 1 THEN 1 ELSE 0 END)
        / COUNT(DISTINCT show_id),
        1
    ) AS recent_content_pct,
    ROUND(AVG(content_age), 1) AS avg_content_age
FROM content_strategy_base
GROUP BY genre
ORDER BY recent_content_pct DESC;

-- 11. Country x content type
DROP TABLE IF EXISTS agg_country_type;
CREATE TABLE agg_country_type AS
SELECT
    primary_country,
    type,
    COUNT(*) AS title_count
FROM content_title_level
WHERE primary_country IS NOT NULL
  AND primary_country <> 'Unknown'
GROUP BY primary_country, type;

-- 12. KPI summary
DROP TABLE IF EXISTS kpi_summary;
CREATE TABLE kpi_summary AS
SELECT
    COUNT(*) AS total_titles,
    SUM(CASE WHEN type = 'Movie' THEN 1 ELSE 0 END) AS movies,
    SUM(CASE WHEN type = 'TV Show' THEN 1 ELSE 0 END) AS tv_shows,
    ROUND(
        100.0 * SUM(CASE WHEN type = 'Movie' THEN 1 ELSE 0 END) / COUNT(*),
        1
    ) AS movie_pct,
    ROUND(
        100.0 * SUM(CASE WHEN type = 'TV Show' THEN 1 ELSE 0 END) / COUNT(*),
        1
    ) AS tv_show_pct,
    ROUND(AVG(content_age), 1) AS avg_content_age,
    SUM(CASE WHEN is_recent = 1 THEN 1 ELSE 0 END) AS recent_titles,
    ROUND(
        100.0 * SUM(CASE WHEN is_recent = 1 THEN 1 ELSE 0 END) / COUNT(*),
        1
    ) AS recent_content_pct,
    COUNT(DISTINCT primary_country) AS countries_represented,
    COUNT(DISTINCT rating) AS distinct_ratings
FROM content_title_level;

-- Useful validation queries
SELECT * FROM kpi_summary;
SELECT * FROM agg_content_type;
SELECT * FROM agg_release_decade;
SELECT * FROM agg_age_group;
SELECT * FROM agg_rating;
SELECT * FROM agg_genre LIMIT 15;
SELECT * FROM agg_country LIMIT 15;
