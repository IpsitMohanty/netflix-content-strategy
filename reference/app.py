import os
import psutil
import mysql.connector
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Netflix Content Strategy Analytics",
    page_icon="🎬",
    layout="wide"
)

st.title("Netflix Content Strategy Analytics Dashboard")
st.caption("Content portfolio, freshness, genre, rating, and geographic analysis")

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", "admin@123"),
    "database": os.getenv("MYSQL_DATABASE", "netflix_db"),
}

@st.cache_data(ttl=300)
def query_df(query, params=None):
    conn = mysql.connector.connect(**MYSQL_CONFIG)
    try:
        return pd.read_sql(query, conn, params=params)
    finally:
        conn.close()

def ram_usage_mb():
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)

try:
    kpi = query_df("SELECT * FROM kpi_summary").iloc[0]
    title_level = query_df("""
        SELECT *
        FROM content_title_level
    """)
    release_year = query_df("""
        SELECT release_year, title_count
        FROM agg_release_year
        ORDER BY release_year
    """)
    release_decade = query_df("""
        SELECT release_decade, title_count
        FROM agg_release_decade
        ORDER BY release_decade
    """)
    content_type = query_df("""
        SELECT type, title_count
        FROM agg_content_type
    """)
    ratings = query_df("""
        SELECT rating, title_count
        FROM agg_rating
        ORDER BY title_count DESC
    """)
    age_groups = query_df("""
        SELECT content_age_group, title_count, avg_content_age
        FROM agg_age_group
    """)
    genres = query_df("""
        SELECT genre, title_count
        FROM agg_genre
        ORDER BY title_count DESC
    """)
    genre_type = query_df("""
        SELECT genre, type, title_count
        FROM agg_genre_type
    """)
    countries = query_df("""
        SELECT primary_country, title_count
        FROM agg_country
        ORDER BY title_count DESC
    """)
    country_genre = query_df("""
        SELECT primary_country, genre, title_count
        FROM agg_country_genre
    """)
    genre_freshness = query_df("""
        SELECT genre, title_count, recent_title_count,
               recent_content_pct, avg_content_age
        FROM agg_genre_freshness
        ORDER BY recent_content_pct DESC
    """)
except Exception as exc:
    st.error("Unable to connect to MySQL or load the analytical tables.")
    st.code(str(exc))
    st.stop()

# Sidebar filters
st.sidebar.header("Filters")

min_year = int(title_level["release_year"].min())
max_year = int(title_level["release_year"].max())

year_range = st.sidebar.slider(
    "Release year",
    min_value=min_year,
    max_value=max_year,
    value=(min_year, max_year)
)

types = sorted(title_level["type"].dropna().unique().tolist())
selected_types = st.sidebar.multiselect(
    "Content type",
    types,
    default=types
)

countries_list = sorted(
    [x for x in title_level["primary_country"].dropna().unique() if x != "Unknown"]
)
selected_country = st.sidebar.selectbox(
    "Primary country",
    ["All"] + countries_list
)

ratings_list = sorted(title_level["rating"].dropna().unique().tolist())
selected_ratings = st.sidebar.multiselect(
    "Rating",
    ratings_list,
    default=ratings_list
)

filtered = title_level[
    title_level["release_year"].between(year_range[0], year_range[1])
    & title_level["type"].isin(selected_types)
    & title_level["rating"].isin(selected_ratings)
].copy()

if selected_country != "All":
    filtered = filtered[filtered["primary_country"] == selected_country]

# Executive KPIs are recalculated from the current title-level filter.
total = len(filtered)
movies = int((filtered["type"] == "Movie").sum())
tv = int((filtered["type"] == "TV Show").sum())
avg_age = filtered["content_age"].mean() if total else 0
recent_pct = filtered["is_recent"].mean() * 100 if total else 0
country_count = filtered["primary_country"].nunique()

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total Titles", f"{total:,}")
c2.metric("Movies", f"{movies:,}")
c3.metric("TV Shows", f"{tv:,}")
c4.metric("Avg Content Age", f"{avg_age:.1f} yrs")
c5.metric("Fresh Content", f"{recent_pct:.1f}%")
c6.metric("Countries", f"{country_count:,}")

st.divider()

# ---------------- Portfolio ----------------
st.subheader("1. Content Portfolio")

portfolio_left, portfolio_right = st.columns(2)

with portfolio_left:
    type_filtered = filtered.groupby("type", as_index=False).size()
    type_filtered.columns = ["type", "title_count"]
    fig = px.pie(
        type_filtered,
        names="type",
        values="title_count",
        hole=0.45,
        title="Content Type Mix"
    )
    st.plotly_chart(fig, use_container_width=True)

with portfolio_right:
    rating_filtered = (
        filtered.groupby("rating", as_index=False)
        .size()
        .rename(columns={"size": "title_count"})
        .sort_values("title_count", ascending=False)
        .head(10)
    )
    fig = px.bar(
        rating_filtered.sort_values("title_count"),
        x="title_count",
        y="rating",
        orientation="h",
        title="Top Content Ratings"
    )
    st.plotly_chart(fig, use_container_width=True)

# ---------------- Evolution ----------------
st.subheader("2. Content Evolution")

evo_left, evo_right = st.columns(2)

with evo_left:
    year_filtered = (
        filtered.groupby("release_year", as_index=False)
        .size()
        .rename(columns={"size": "title_count"})
    )
    fig = px.line(
        year_filtered,
        x="release_year",
        y="title_count",
        markers=True,
        title="Titles by Release Year"
    )
    st.plotly_chart(fig, use_container_width=True)

with evo_right:
    decade_filtered = (
        filtered.groupby("release_decade", as_index=False)
        .size()
        .rename(columns={"size": "title_count"})
        .sort_values("release_decade")
    )
    fig = px.bar(
        decade_filtered,
        x="release_decade",
        y="title_count",
        title="Titles by Release Decade"
    )
    st.plotly_chart(fig, use_container_width=True)

# ---------------- Freshness ----------------
st.subheader("3. Content Freshness")

fresh_left, fresh_right = st.columns(2)

age_order = ["Very Recent", "Recent", "Mature", "Older", "Legacy"]

with fresh_left:
    age_filtered = (
        filtered.groupby("content_age_group", as_index=False)
        .size()
        .rename(columns={"size": "title_count"})
    )
    age_filtered["content_age_group"] = pd.Categorical(
        age_filtered["content_age_group"],
        categories=age_order,
        ordered=True
    )
    age_filtered = age_filtered.sort_values("content_age_group")
    fig = px.bar(
        age_filtered,
        x="content_age_group",
        y="title_count",
        title="Content Age Distribution"
    )
    st.plotly_chart(fig, use_container_width=True)

with fresh_right:
    freshness = (
        filtered.groupby("content_age_group", as_index=False)
        .agg(
            title_count=("title", "count"),
            avg_content_age=("content_age", "mean")
        )
    )
    freshness["content_age_group"] = pd.Categorical(
        freshness["content_age_group"],
        categories=age_order,
        ordered=True
    )
    freshness = freshness.sort_values("content_age_group")
    fig = px.bar(
        freshness,
        x="content_age_group",
        y="avg_content_age",
        title="Average Age by Content Group",
        labels={"avg_content_age": "Average Age (years)"}
    )
    st.plotly_chart(fig, use_container_width=True)

# ---------------- Genre Intelligence ----------------
st.subheader("4. Genre Intelligence")

genre_left, genre_right = st.columns(2)

with genre_left:
    genre_filtered = (
        filtered.merge(
            query_df("SELECT show_id, genre FROM content_strategy_base"),
            on="show_id",
            how="inner"
        )
        .groupby("genre", as_index=False)["show_id"]
        .nunique()
        .rename(columns={"show_id": "title_count"})
        .sort_values("title_count", ascending=False)
        .head(10)
    )
    fig = px.bar(
        genre_filtered.sort_values("title_count"),
        x="title_count",
        y="genre",
        orientation="h",
        title="Top 10 Genres"
    )
    st.plotly_chart(fig, use_container_width=True)

with genre_right:
    gt = query_df("""
        SELECT b.genre, t.type, COUNT(DISTINCT b.show_id) AS title_count
        FROM content_strategy_base b
        JOIN content_title_level t ON b.show_id = t.show_id
        GROUP BY b.genre, t.type
    """)
    gt = gt[gt["genre"].isin(genre_filtered["genre"])]
    fig = px.bar(
        gt,
        x="genre",
        y="title_count",
        color="type",
        barmode="stack",
        title="Genre × Content Type"
    )
    fig.update_xaxes(tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

# Freshness by genre
fg = query_df("""
    SELECT genre, title_count, recent_title_count,
           recent_content_pct, avg_content_age
    FROM agg_genre_freshness
    ORDER BY recent_content_pct DESC
""")
fg = fg[fg["genre"].isin(genre_filtered["genre"])].sort_values(
    "recent_content_pct", ascending=False
)

fig = px.bar(
    fg,
    x="genre",
    y="recent_content_pct",
    title="Recent Content % by Top Genre",
    labels={"recent_content_pct": "Recent Content (%)"}
)
fig.update_xaxes(tickangle=-45)
st.plotly_chart(fig, use_container_width=True)

# ---------------- Geographic ----------------
st.subheader("5. Geographic Analysis")

geo_left, geo_right = st.columns(2)

with geo_left:
    country_filtered = (
        filtered.groupby("primary_country", as_index=False)
        .size()
        .rename(columns={"size": "title_count"})
        .query("primary_country != 'Unknown'")
        .sort_values("title_count", ascending=False)
        .head(10)
    )
    fig = px.bar(
        country_filtered.sort_values("title_count"),
        x="title_count",
        y="primary_country",
        orientation="h",
        title="Top 10 Countries"
    )
    st.plotly_chart(fig, use_container_width=True)

with geo_right:
    if selected_country == "All":
        st.info("Select a country from the sidebar to inspect its genre mix.")
    else:
        cg = query_df("""
            SELECT genre, COUNT(DISTINCT show_id) AS title_count
            FROM content_strategy_base
            WHERE primary_country = %s
            GROUP BY genre
            ORDER BY title_count DESC
            LIMIT 10
        """, params=(selected_country,))
        fig = px.bar(
            cg.sort_values("title_count"),
            x="title_count",
            y="genre",
            orientation="h",
            title=f"Top Genres in {selected_country}"
        )
        st.plotly_chart(fig, use_container_width=True)

# Business interpretation helper
st.subheader("6. Catalogue Snapshot")

if total:
    oldest = filtered.loc[filtered["content_age"].idxmax(), "title"]
    newest = filtered.loc[filtered["content_age"].idxmin(), "title"]
    top_type = filtered["type"].value_counts().idxmax()
    top_rating = filtered["rating"].value_counts().idxmax()
    st.write(
        f"The current selection contains **{total:,} titles**, with **{top_type}** as "
        f"the dominant content type. The most common rating is **{top_rating}**. "
        f"The average content age is **{avg_age:.1f} years**, and **{recent_pct:.1f}%** "
        f"of the selected catalogue qualifies as recent content."
    )
else:
    st.warning("No titles match the selected filters.")

st.sidebar.divider()
st.sidebar.metric("Dashboard RAM", f"{ram_usage_mb():.1f} MB")
st.caption("Netflix Content Strategy Analytics • PySpark + MySQL + Plotly + Streamlit")
