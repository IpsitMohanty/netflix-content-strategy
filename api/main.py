import os
from functools import lru_cache
from typing import Annotated, Generator

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

load_dotenv()


class ReleaseYearKpis(BaseModel):
    avg_release_year: float
    min_year: int
    max_year: int
    range_label: str


class GrowthByYear(BaseModel):
    release_year: int
    titles: int
    yoy_change: float | None


class CountryTypeCounts(BaseModel):
    country: str
    movies: int
    tv_shows: int
    total: int


class GenreTypeCounts(BaseModel):
    genre: str
    movies: int
    tv_shows: int
    total: int


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        URL.create(
            "mysql+pymysql",
            username=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD", ""),
            host=os.getenv("MYSQL_HOST", "127.0.0.1"),
            port=int(os.getenv("MYSQL_PORT", "3306")),
            database=os.getenv("MYSQL_DATABASE", "netflix_db"),
        ),
        pool_pre_ping=True,
    )


def get_connection() -> Generator[Connection, None, None]:
    with get_engine().connect() as connection:
        yield connection


ConnectionDependency = Annotated[Connection, Depends(get_connection)]
app = FastAPI(title="Netflix Content Strategy API", version="1.0.0")


def validate_type_totals(rows: list[dict]) -> None:
    for row in rows:
        if row["movies"] + row["tv_shows"] != row["total"]:
            raise HTTPException(
                status_code=500,
                detail="Content type counts do not reconcile with the distinct-title total.",
            )


@app.get("/health")
def health() -> dict[str, str]:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable.") from exc
    return {"status": "ok"}


@app.get("/kpis/release-years", response_model=ReleaseYearKpis)
def release_year_kpis(connection: ConnectionDependency) -> ReleaseYearKpis:
    row = connection.execute(
        text(
            "SELECT ROUND(AVG(release_year), 1) AS avg_release_year, "
            "MIN(release_year) AS min_year, MAX(release_year) AS max_year "
            "FROM dim_title WHERE release_year IS NOT NULL"
        )
    ).mappings().one()
    if row["min_year"] is None or row["max_year"] is None:
        raise HTTPException(status_code=404, detail="No release-year data is available.")
    min_year, max_year = int(row["min_year"]), int(row["max_year"])
    return ReleaseYearKpis(
        avg_release_year=float(row["avg_release_year"]),
        min_year=min_year,
        max_year=max_year,
        range_label=f"{min_year} – {max_year}",
    )


@app.get("/content/growth-by-year", response_model=list[GrowthByYear])
def growth_by_year(connection: ConnectionDependency) -> list[GrowthByYear]:
    rows = connection.execute(
        text(
            "SELECT release_year, COUNT(DISTINCT show_id) AS titles "
            "FROM dim_title WHERE release_year IS NOT NULL "
            "GROUP BY release_year ORDER BY release_year"
        )
    ).mappings().all()
    titles_by_year = {int(row["release_year"]): int(row["titles"]) for row in rows}
    return [
        GrowthByYear(
            release_year=year,
            titles=titles,
            yoy_change=(
                round((titles - titles_by_year[year - 1]) * 100.0 / titles_by_year[year - 1], 1)
                if titles_by_year.get(year - 1, 0) > 0
                else None
            ),
        )
        for year, titles in titles_by_year.items()
    ]


@app.get("/content/country-type", response_model=list[CountryTypeCounts])
def country_type(
    connection: ConnectionDependency,
    top_n: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[CountryTypeCounts]:
    rows = connection.execute(
        text(
            "SELECT TRIM(c.country) AS country, "
            "COUNT(DISTINCT CASE WHEN t.type = 'Movie' THEN t.show_id END) AS movies, "
            "COUNT(DISTINCT CASE WHEN t.type = 'TV Show' THEN t.show_id END) AS tv_shows, "
            "COUNT(DISTINCT t.show_id) AS total "
            "FROM bridge_country c JOIN dim_title t ON t.show_id = c.show_id "
            "WHERE TRIM(c.country) <> '' AND TRIM(c.country) <> 'Unknown' "
            "GROUP BY TRIM(c.country) ORDER BY total DESC, country LIMIT :top_n"
        ),
        {"top_n": top_n},
    ).mappings().all()
    validate_type_totals(rows)
    return [CountryTypeCounts(**dict(row)) for row in rows]


@app.get("/content/genre-type", response_model=list[GenreTypeCounts])
def genre_type(
    connection: ConnectionDependency,
    top_n: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[GenreTypeCounts]:
    rows = connection.execute(
        text(
            "SELECT TRIM(g.genre) AS genre, "
            "COUNT(DISTINCT CASE WHEN t.type = 'Movie' THEN t.show_id END) AS movies, "
            "COUNT(DISTINCT CASE WHEN t.type = 'TV Show' THEN t.show_id END) AS tv_shows, "
            "COUNT(DISTINCT t.show_id) AS total "
            "FROM bridge_genre g JOIN dim_title t ON t.show_id = g.show_id "
            "WHERE TRIM(g.genre) <> '' "
            "GROUP BY TRIM(g.genre) ORDER BY total DESC, genre LIMIT :top_n"
        ),
        {"top_n": top_n},
    ).mappings().all()
    validate_type_totals(rows)
    return [GenreTypeCounts(**dict(row)) for row in rows]
