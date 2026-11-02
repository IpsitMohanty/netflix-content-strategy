"""
Step 2 - Load the three processed CSVs into MySQL (database: netflix_db).

Run from the project root:   python etl/02_load_mysql.py
Credentials come from a .env file - never hardcode them.
Re-running is safe: tables are dropped and rebuilt.
"""
import os
import sys
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, types as T
from sqlalchemy.engine import URL

load_dotenv()
cfg = dict(
    host=os.getenv("MYSQL_HOST", "127.0.0.1"),
    port=int(os.getenv("MYSQL_PORT", "3306")),
    username=os.getenv("MYSQL_USER", "root"),
    password=os.getenv("MYSQL_PASSWORD", ""),
)
DB = os.getenv("MYSQL_DATABASE", "netflix_db")
DATA = sys.argv[1] if len(sys.argv) > 1 else "data/processed"


def engine(database=None):
    # URL.create handles special characters (@, #, ...) in passwords safely
    return create_engine(URL.create("mysql+pymysql", database=database, **cfg))


# ---- 1. Create database ----
with engine().begin() as c:
    c.execute(text(f"CREATE DATABASE IF NOT EXISTS `{DB}` CHARACTER SET utf8mb4"))
eng = engine(DB)

# ---- 2. Read CSVs ----
dim_title = pd.read_csv(f"{DATA}/dim_title.csv")
bridge_genre = pd.read_csv(f"{DATA}/bridge_genre.csv")
bridge_country = pd.read_csv(f"{DATA}/bridge_country.csv")
for col in ["year_added", "duration_value"]:            # nullable ints
    dim_title[col] = dim_title[col].astype("Int64")

# ---- 3. Explicit schemas ----
schemas = {
    "dim_title": (dim_title, {
        "show_id": T.String(10), "type": T.String(20), "title": T.String(300),
        "primary_country": T.String(100), "release_year": T.Integer(),
        "release_decade": T.Integer(), "year_added": T.Integer(),
        "rating": T.String(20), "duration_value": T.Integer(),
        "content_age": T.Integer(), "content_age_group": T.String(20),
        "is_recent": T.SmallInteger(), "n_genres": T.SmallInteger()}),
    "bridge_genre": (bridge_genre, {"show_id": T.String(10), "genre": T.String(80)}),
    "bridge_country": (bridge_country, {"show_id": T.String(10), "country": T.String(100)}),
}

# ---- 4. Load (drop children first so foreign keys never block a re-run) ----
with eng.begin() as c:
    for t in ["bridge_genre", "bridge_country", "dim_title"]:
        c.execute(text(f"DROP TABLE IF EXISTS {t}"))
for name in ["dim_title", "bridge_genre", "bridge_country"]:
    df, dtypes = schemas[name]
    df.to_sql(name, eng, if_exists="replace", index=False, dtype=dtypes, chunksize=2000)
    print(f"loaded {name}: {len(df):,} rows")

# ---- 5. Keys and indexes ----
ddl = [
    "ALTER TABLE dim_title ADD PRIMARY KEY (show_id)",
    "ALTER TABLE dim_title ADD INDEX idx_type (type), ADD INDEX idx_year (release_year),"
    " ADD INDEX idx_rating (rating), ADD INDEX idx_pcountry (primary_country),"
    " ADD INDEX idx_decade (release_decade)",
    "ALTER TABLE bridge_genre ADD PRIMARY KEY (show_id, genre), ADD INDEX idx_genre (genre),"
    " ADD FOREIGN KEY (show_id) REFERENCES dim_title(show_id)",
    "ALTER TABLE bridge_country ADD PRIMARY KEY (show_id, country), ADD INDEX idx_country (country),"
    " ADD FOREIGN KEY (show_id) REFERENCES dim_title(show_id)",
]
with eng.begin() as c:
    for stmt in ddl:
        c.execute(text(stmt))
print("keys and indexes created")

# ---- 6. Validation ----
with eng.connect() as c:
    q = lambda s: c.execute(text(s)).scalar()
    checks = {
        "dim_title rows match CSV": q("SELECT COUNT(*) FROM dim_title") == len(dim_title),
        "bridge_genre rows match CSV": q("SELECT COUNT(*) FROM bridge_genre") == len(bridge_genre),
        "bridge_country rows match CSV": q("SELECT COUNT(*) FROM bridge_country") == len(bridge_country),
        "no duplicate show_id": q("SELECT COUNT(*)-COUNT(DISTINCT show_id) FROM dim_title") == 0,
        "no orphan genre rows": q("SELECT COUNT(*) FROM bridge_genre g LEFT JOIN dim_title t "
                                  "ON g.show_id=t.show_id WHERE t.show_id IS NULL") == 0,
    }
for k, ok in checks.items():
    print(("PASS  " if ok else "FAIL  ") + k)
sys.exit(0 if all(checks.values()) else 1)