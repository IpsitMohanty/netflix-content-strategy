from collections.abc import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from api.main import app, get_connection


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    with engine.begin() as connection:
        statements = """
            CREATE TABLE dim_title (show_id TEXT, type TEXT, release_year INTEGER);
            CREATE TABLE bridge_country (show_id TEXT, country TEXT);
            CREATE TABLE bridge_genre (show_id TEXT, genre TEXT);
            INSERT INTO dim_title VALUES
                ('m1', 'Movie', 2000), ('m1', 'Movie', 2000),
                ('m2', 'Movie', 2001), ('t1', 'TV Show', 2001);
            INSERT INTO bridge_country VALUES
                ('m1', 'United States'), ('m1', 'United States'),
                ('m2', ' United States '), ('t1', 'United States'),
                ('m2', 'Unknown'), ('t1', '   ');
            INSERT INTO bridge_genre VALUES
                ('m1', 'Drama'), ('m1', ' Drama '), ('m2', 'Drama'),
                ('t1', 'Comedy'), ('t1', ' ');
            """
        for statement in statements.strip().split(";"):
            if statement.strip():
                connection.exec_driver_sql(statement)
    connection = engine.connect()

    def override_connection() -> Generator[Connection, None, None]:
        yield connection

    app.dependency_overrides[get_connection] = override_connection
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        connection.close()
        engine.dispose()


def test_health_returns_ok_without_a_live_mysql_service(client: TestClient) -> None:
    engine = create_engine("sqlite://")
    try:
        with patch("api.main.get_engine", return_value=engine):
            response = client.get("/health")
    finally:
        engine.dispose()
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_release_year_kpis(client: TestClient) -> None:
    assert client.get("/kpis/release-years").json() == {
        "avg_release_year": 2000.5,
        "min_year": 2000,
        "max_year": 2001,
        "range_label": "2000 – 2001",
    }


def test_growth_by_year_is_sorted_and_has_year_over_year_change(client: TestClient) -> None:
    assert client.get("/content/growth-by-year").json() == [
        {"release_year": 2000, "titles": 1, "yoy_change": None},
        {"release_year": 2001, "titles": 2, "yoy_change": 100.0},
    ]


def test_country_counts_are_distinct_and_exclude_unknown_and_empty(client: TestClient) -> None:
    response = client.get("/content/country-type?top_n=10")
    assert response.status_code == 200
    rows = response.json()
    assert rows == [
        {"country": "United States", "movies": 2, "tv_shows": 1, "total": 3}
    ]
    assert all(row["movies"] + row["tv_shows"] == row["total"] for row in rows)


def test_genre_counts_are_distinct_and_exclude_empty(client: TestClient) -> None:
    response = client.get("/content/genre-type?top_n=10")
    assert response.status_code == 200
    rows = response.json()
    assert rows[0] == {
        "genre": "Drama",
        "movies": 2,
        "tv_shows": 0,
        "total": 2,
    }
    assert all(row["movies"] + row["tv_shows"] == row["total"] for row in rows)


def test_top_n_is_bounded(client: TestClient) -> None:
    assert client.get("/content/country-type?top_n=0").status_code == 422


def test_health_reports_database_unavailable(client: TestClient) -> None:
    with patch("api.main.get_engine", side_effect=SQLAlchemyError("database unavailable")):
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable."}
