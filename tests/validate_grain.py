"""
Validation - checks the grain rules and data quality directly in MySQL.
Run from the project root:   python tests/validate_grain.py
Exit code 0 = all checks passed.
"""
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

load_dotenv()
eng = create_engine(URL.create(
    "mysql+pymysql",
    username=os.getenv("MYSQL_USER", "root"),
    password=os.getenv("MYSQL_PASSWORD", ""),
    host=os.getenv("MYSQL_HOST", "127.0.0.1"),
    port=int(os.getenv("MYSQL_PORT", "3306")),
    database=os.getenv("MYSQL_DATABASE", "netflix_db"),
))

CHECKS = [
    ("dim_title: one row per show_id",
     "SELECT COUNT(*) - COUNT(DISTINCT show_id) FROM dim_title", lambda v: v == 0),
    ("kpi_summary total = dim_title rows",
     "SELECT (SELECT total_titles FROM kpi_summary) - COUNT(*) FROM dim_title", lambda v: v == 0),
    ("movies + TV shows = total titles",
     "SELECT (SELECT movies + tv_shows FROM kpi_summary) - COUNT(*) FROM dim_title", lambda v: v == 0),
    ("genre credits >= titles (titles carry several genres)",
     "SELECT (SELECT SUM(titles) FROM agg_genre) - COUNT(*) FROM dim_title", lambda v: v >= 0),
    ("every genre row has a parent title",
     "SELECT COUNT(*) FROM bridge_genre g LEFT JOIN dim_title t ON t.show_id = g.show_id WHERE t.show_id IS NULL",
     lambda v: v == 0),
    ("every country row has a parent title",
     "SELECT COUNT(*) FROM bridge_country c LEFT JOIN dim_title t ON t.show_id = c.show_id WHERE t.show_id IS NULL",
     lambda v: v == 0),
    ("no empty country values",
     "SELECT COUNT(*) FROM bridge_country WHERE country IS NULL OR TRIM(country) = ''", lambda v: v == 0),
    ("all 5 content-age groups are populated",
     "SELECT COUNT(DISTINCT content_age_group) FROM dim_title", lambda v: v == 5),
    ("no duration text left in the rating column",
     "SELECT COUNT(*) FROM dim_title WHERE rating LIKE '% min'", lambda v: v == 0),
    ("content_age is never negative",
     "SELECT COUNT(*) FROM dim_title WHERE content_age < 0", lambda v: v == 0),
    ("is_recent agrees with content_age <= 5",
     "SELECT COUNT(*) FROM dim_title WHERE is_recent <> (content_age <= 5)", lambda v: v == 0),
    ("decade type-shares sum to ~100 in every decade",
     "SELECT COALESCE(MAX(ABS(s - 100)), 0) FROM (SELECT SUM(pct_of_decade) AS s FROM agg_type_decade GROUP BY release_decade) x",
     lambda v: float(v) < 0.5),
]

failed = 0
with eng.connect() as c:
    for name, sql, ok in CHECKS:
        value = c.execute(text(sql)).scalar()
        passed = bool(ok(value))
        failed += not passed
        print(f"{'PASS' if passed else 'FAIL'}  {name}  (value={value})")
print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} checks passed")
sys.exit(1 if failed else 0)
