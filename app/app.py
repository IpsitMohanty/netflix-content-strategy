"""
Netflix Content Strategy Analytics - Streamlit + Plotly dashboard.

Run from the project root:   streamlit run app/app.py
Data comes from MySQL (database netflix_db, built by etl/02 and etl/03).
Every KPI and chart is computed from the FILTERED title / genre / country tables,
so the sidebar filters change everything on the page.
"""
import os

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

import analysis as an

load_dotenv()
st.set_page_config(page_title="Netflix Content Strategy", page_icon="🎬", layout="wide")

TYPE_COLORS = {"Movie": "#E50914", "TV Show": "#4C78A8"}
AGE_COLORS = dict(zip(an.AGE_ORDER, ["#E50914", "#F4A582", "#92C5DE", "#4393C3", "#1F3A5F"]))
_NEW_ST = tuple(int(x) for x in st.__version__.split(".")[:2]) >= (1, 50)


def show(fig, height=380):
    """Render a Plotly figure full-width (works on old and new Streamlit)."""
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=50, b=10), legend_title_text="")
    if _NEW_ST:
        st.plotly_chart(fig, width="stretch")
    else:
        st.plotly_chart(fig, use_container_width=True)


def bar_pct(*args, **kwargs):
    """px.bar drawn as a 100% stacked bar (barnorm is a layout setting, not a px.bar argument)."""
    fig = px.bar(*args, **kwargs)
    fig.update_layout(barnorm="percent")
    return fig


# ------------------------------------------------------------------- data
@st.cache_data(ttl=600, show_spinner="Loading data from MySQL...")
def load_data():
    eng = create_engine(URL.create(
        "mysql+pymysql",
        username=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=os.getenv("MYSQL_DATABASE", "netflix_db"),
    ))
    dim = pd.read_sql("SELECT * FROM dim_title", eng)
    bg = pd.read_sql("SELECT show_id, genre FROM bridge_genre", eng)
    bc = pd.read_sql("SELECT show_id, country FROM bridge_country WHERE country <> 'Unknown'", eng)
    kpi = pd.read_sql("SELECT * FROM kpi_summary", eng).iloc[0].to_dict()   # whole-catalogue baseline
    return dim, bg, bc, kpi


try:
    dim, bg, bc, base = load_data()
except Exception as exc:
    st.error("Could not load data from MySQL. Check your .env file and that steps 02 and 03 ran.")
    st.code(str(exc))
    st.stop()

# ---------------------------------------------------------------- sidebar
st.sidebar.header("Filters")
y0, y1 = int(dim.release_year.min()), int(dim.release_year.max())
year_range = st.sidebar.slider("Release year", y0, y1, (y0, y1))
types = st.sidebar.multiselect("Content type", sorted(dim.type.unique()), default=sorted(dim.type.unique()))
all_ratings = an.order_ratings(dim.rating.unique())
ratings = st.sidebar.multiselect("Rating", all_ratings, default=all_ratings)
countries = st.sidebar.multiselect("Country (any of)", sorted(bc.country.unique()),
                                   help="Leave empty for all countries. Keeps titles that list any selected country.")
genres = st.sidebar.multiselect("Genre (any of)", sorted(bg.genre.unique()),
                                help="Leave empty for all genres. Keeps titles tagged with any selected genre.")

d, g, c = an.apply_filters(dim, bg, bc, year_range, types, ratings, countries, genres)

st.title("🎬 Netflix Content Strategy Analytics")
st.caption("Catalogue composition, freshness, evolution, genres, geography and ratings. "
           "Counts are distinct titles; a title with several genres or countries is counted once in each.")

if d.empty:
    st.warning("No titles match the current filters. Widen the filters in the sidebar.")
    st.stop()

# -------------------------------------------------------------------- KPIs
k = an.compute_kpis(d, g, c)
r1 = st.columns(6)
r1[0].metric("Total titles", f"{k['total']:,}", help=f"Whole catalogue: {int(base['total_titles']):,}")
r1[1].metric("Movies", f"{k['movies']:,}", help=f"Whole catalogue: {int(base['movies']):,}")
r1[2].metric("TV Shows", f"{k['tv']:,}", help=f"Whole catalogue: {int(base['tv_shows']):,}")
r1[3].metric("Movie : TV ratio", f"{k['ratio']:.2f}" if k["ratio"] else "n/a", help=f"Whole catalogue: {base['movie_to_tv_ratio']}")
r1[4].metric("% Movies", f"{k['movie_pct']:.1f}%", help=f"Whole catalogue: {base['movie_pct']}%")
r1[5].metric("% TV Shows", f"{k['tv_pct']:.1f}%", help=f"Whole catalogue: {base['tv_pct']}%")
r2 = st.columns(6)
r2[0].metric("Avg content age", f"{k['avg_age']:.1f} yrs", help=f"Whole catalogue: {base['avg_content_age']} yrs. Age = newest release year in data minus release year.")
r2[1].metric("Recent (≤5 yrs)", f"{k['recent_pct']:.1f}%", help=f"Whole catalogue: {base['recent_pct']}%")
r2[2].metric("Distinct genres", k["n_genres"], help=f"Whole catalogue: {int(base['distinct_genres'])}")
r2[3].metric("Countries", k["n_countries"], help=f"Whole catalogue: {int(base['countries_represented'])}")
r2[4].metric("Top rating", k["top_rating"], help=f"Whole catalogue: {base['top_rating']}")
r2[5].metric("Top country", k["top_country"], help=f"Whole catalogue: {base['top_country']}")
st.divider()

gf, cf = an.genre_frame(d, g), an.country_frame(d, c)
gs, cs = an.genre_summary(gf), an.country_summary(cf)
tabs = st.tabs([
    "Portfolio", "Freshness", "Evolution", "Genres", "Geography", "Ratings", "Insights",
    "Catalogue Analytics (API)",
])

# --------------------------------------------------------------- Portfolio
with tabs[0]:
    a, b = st.columns(2)
    with a:
        tm = d.type.value_counts().reset_index()
        tm.columns = ["type", "titles"]
        show(px.pie(tm, names="type", values="titles", hole=0.5, color="type",
                    color_discrete_map=TYPE_COLORS, title="Content type mix (titles)"))
    with b:
        dt = d.groupby(["release_decade", "type"]).size().reset_index(name="titles")
        show(px.bar(dt, x="release_decade", y="titles", color="type", color_discrete_map=TYPE_COLORS,
                    title="Titles by release decade", labels={"release_decade": "Release decade", "titles": "Titles"}))
    a, b = st.columns(2)
    with a:
        tg = gs.nlargest(12, "titles").sort_values("titles")
        show(px.bar(tg, x="titles", y="genre", orientation="h", text="titles",
                    title="Top 12 genres (titles per genre)", labels={"titles": "Titles", "genre": ""}))
    with b:
        tc = cs.nlargest(12, "titles").sort_values("titles")
        show(px.bar(tc, x="titles", y="country", orientation="h", text="titles",
                    title="Top 12 countries (titles crediting the country)", labels={"titles": "Titles", "country": ""}))
    tre = gf.groupby(["type", "genre"]).show_id.nunique().reset_index(name="titles")
    show(px.treemap(tre, path=["type", "genre"], values="titles", color="type", color_discrete_map=TYPE_COLORS,
                    title="Genre composition by content type (box size = titles)"), height=450)

# --------------------------------------------------------------- Freshness
with tabs[1]:
    st.caption("Age = newest release year in the data (2021) minus release year. "
               "Very Recent ≤2 yrs, Recent ≤5, Mature ≤10, Older ≤20, Legacy >20.")
    a, b = st.columns(2)
    with a:
        ag = d.groupby(["content_age_group", "type"]).size().reset_index(name="titles")
        show(px.bar(ag, x="content_age_group", y="titles", color="type", barmode="group",
                    color_discrete_map=TYPE_COLORS, category_orders={"content_age_group": an.AGE_ORDER},
                    title="Content age groups by type", labels={"content_age_group": "Age group", "titles": "Titles"}))
    with b:
        show(px.box(d, x="type", y="content_age", color="type", color_discrete_map=TYPE_COLORS,
                    title="Content age distribution by type", labels={"content_age": "Age (years)", "type": ""}))
    min_t = st.slider("Minimum titles per genre (hides tiny genres)", 10, 200, 30, step=10)
    big = gs[(gs.titles >= min_t) & ~gs.genre.isin(an.GENERIC_TAGS)]
    if len(big) >= 2:
        a, b = st.columns(2)
        with a:
            f = big.nlargest(10, "recent_pct").sort_values("recent_pct")
            show(px.bar(f, x="recent_pct", y="genre", orientation="h", text=f.recent_pct.round(0),
                        title="Genres with the most recent content (% released in last 5 yrs)",
                        labels={"recent_pct": "% recent", "genre": ""}))
        with b:
            o = big.nlargest(10, "avg_age").sort_values("avg_age")
            show(px.bar(o, x="avg_age", y="genre", orientation="h", text=o.avg_age.round(1),
                        title="Genres with the oldest content (average age, years)",
                        labels={"avg_age": "Average age (yrs)", "genre": ""}))
        top12 = gs.nlargest(12, "titles").genre
        ga = gf[gf.genre.isin(top12)].groupby(["genre", "content_age_group"]).show_id.nunique().reset_index(name="titles")
        show(bar_pct(ga, x="genre", y="titles", color="content_age_group",
                    color_discrete_map=AGE_COLORS, category_orders={"content_age_group": an.AGE_ORDER},
                    title="Age mix of the 12 biggest genres (100% stacked)",
                    labels={"titles": "% of genre titles", "genre": ""}), height=430)
    else:
        st.info("Not enough genres meet the minimum-titles setting for the genre freshness charts.")

# --------------------------------------------------------------- Evolution
with tabs[2]:
    a, b = st.columns(2)
    with a:
        ty = d.groupby(["release_year", "type"]).size().reset_index(name="titles")
        show(px.line(ty, x="release_year", y="titles", color="type", color_discrete_map=TYPE_COLORS,
                     title="Titles by release year", labels={"release_year": "Release year", "titles": "Titles"}))
    with b:
        td = d.groupby(["release_decade", "type"]).size().reset_index(name="titles")
        td = td[td.groupby("release_decade").titles.transform("sum") >= 50]   # tiny decades give meaningless shares
        show(bar_pct(td, x="release_decade", y="titles", color="type",
                    color_discrete_map=TYPE_COLORS, title="Movie vs TV Show share by release decade (100% stacked; decades with <50 titles hidden)",
                    labels={"release_decade": "Release decade", "titles": "% of titles"}))
    st.caption("Titles added per year: 2021 is a partial year (the source data ends in late September 2021).")
    ya = d.dropna(subset=["year_added"]).groupby(["year_added", "type"]).size().reset_index(name="titles")
    if len(ya):
        show(px.area(ya, x="year_added", y="titles", color="type", color_discrete_map=TYPE_COLORS,
                     title="Titles added to Netflix per year",
                     labels={"year_added": "Year added", "titles": "Titles added"}))
    top_g = gs.nlargest(6, "titles").genre.tolist()
    pick = st.multiselect("Genres to compare over time", sorted(gs.genre.unique()), default=top_g)
    if pick:
        gy = gf[gf.genre.isin(pick) & (gf.release_year >= max(year_range[0], 1990))]
        gy = gy.groupby(["release_year", "genre"]).show_id.nunique().reset_index(name="titles")
        show(px.line(gy, x="release_year", y="titles", color="genre", markers=True,
                     title="Genre growth by release year (1990 onwards)",
                     labels={"release_year": "Release year", "titles": "Titles"}), height=420)
    top_c = cs.nlargest(8, "titles").country.tolist()
    cd = cf[cf.country.isin(top_c)].groupby(["release_decade", "country"]).show_id.nunique().reset_index(name="titles")
    show(px.bar(cd, x="release_decade", y="titles", color="country",
                title="Contribution of the top 8 countries by release decade",
                labels={"release_decade": "Release decade", "titles": "Titles"}), height=420)

# ------------------------------------------------------------------ Genres
with tabs[3]:
    st.caption("Genre tags are type-specific (e.g. 'Dramas' = movies, 'TV Dramas' = series), so the Movie/TV split "
               "within a single genre is almost always 100/0. Themes group the matching tags to compare formats.")
    a, b = st.columns(2)
    with a:
        gt = gf[gf.genre.isin(gs.nlargest(15, "titles").genre)].groupby(["genre", "type"]).show_id.nunique().reset_index(name="titles")
        show(px.bar(gt, x="genre", y="titles", color="type", color_discrete_map=TYPE_COLORS,
                    title="Top 15 genres by content type", labels={"titles": "Titles", "genre": ""}))
    with b:
        gp = an.genre_pairs(g, top=10).sort_values("titles")
        show(px.bar(gp, x="titles", y="pair", orientation="h",
                    title="Most common genre combinations", labels={"titles": "Titles sharing both tags", "pair": ""}))
    sc = gs[~gs.genre.isin(an.GENERIC_TAGS)]
    fig_sc = px.scatter(sc, x="titles", y="recent_pct", size="titles", color="movie_pct", hover_name="genre",
                    log_x=True, color_continuous_scale="RdBu_r",
                    title="Genre size vs freshness (colour = % movies; bubble = titles)",
                    labels={"titles": "Titles (log scale)", "recent_pct": "% recent (≤5 yrs)", "movie_pct": "% movies"})
    fig_sc.update_xaxes(tickvals=[10, 30, 100, 300, 1000, 3000], ticktext=["10", "30", "100", "300", "1,000", "3,000"])
    show(fig_sc, height=450)
    st.caption("Reading the bubble chart: genres further right are bigger; higher means a larger share of recent titles.")
    ts = an.theme_summary(gf)
    ts = ts[(ts.movies > 0) & (ts.tv > 0)]
    if len(ts):
        tl = ts.melt(id_vars="theme", value_vars=["movies", "tv"], var_name="format", value_name="titles")
        tl["format"] = tl["format"].map({"movies": "Movie", "tv": "TV Show"})
        order = ts.assign(t=ts.movies + ts.tv).sort_values("t", ascending=False).theme
        show(px.bar(tl, x="theme", y="titles", color="format", barmode="group", color_discrete_map=TYPE_COLORS,
                    category_orders={"theme": order.tolist()},
                    title="Movies vs TV Shows within the same theme", labels={"theme": "", "titles": "Titles"}), height=420)

# --------------------------------------------------------------- Geography
with tabs[4]:
    if cs.empty:
        st.info("No country information for the current selection.")
    else:
        show(px.choropleth(cs, locations="country", locationmode="country names", color="titles",
                           color_continuous_scale="Reds", hover_name="country",
                           range_color=(0, max(float(cs.titles.quantile(0.95)), 1.0)),
                           title="Titles by producing country (colour scale capped at the 95th percentile)",
                           labels={"titles": "Titles"}), height=450)
        a, b = st.columns(2)
        with a:
            tc12 = cs.nlargest(12, "titles").country
            ct = cf[cf.country.isin(tc12)].groupby(["country", "type"]).show_id.nunique().reset_index(name="titles")
            show(bar_pct(ct, y="country", x="titles", color="type", orientation="h",
                        color_discrete_map=TYPE_COLORS, category_orders={"country": tc12.tolist()[::-1]},
                        title="Movie vs TV Show mix in the top 12 countries (100% stacked)",
                        labels={"titles": "% of titles", "country": ""}), height=430)
        with b:
            bands = pd.cut(cs.titles, [0, 4, 9, 49, 199, 10**6], labels=["1-4", "5-9", "10-49", "50-199", "200+"])
            bd = bands.value_counts().reindex(["1-4", "5-9", "10-49", "50-199", "200+"]).reset_index()
            bd.columns = ["titles_band", "countries"]
            show(px.bar(bd, x="titles_band", y="countries", text="countries",
                        title="Market depth: how many countries have how many titles",
                        labels={"titles_band": "Titles per country", "countries": "Countries"}), height=430)
        t10c = cs.nlargest(10, "titles").country
        t12g = gs.nlargest(12, "titles").genre
        cg = cf.merge(g, on="show_id")
        cg = cg[cg.country.isin(t10c) & cg.genre.isin(t12g)].groupby(["country", "genre"]).show_id.nunique().unstack(fill_value=0)
        if not cg.empty:
            share = cg.div(cf[cf.country.isin(cg.index)].groupby("country").show_id.nunique(), axis=0).mul(100)
            show(px.imshow(share.loc[:, [x for x in t12g if x in share.columns]], text_auto=".0f", aspect="auto",
                           color_continuous_scale="Reds",
                           title="Genre mix by country: % of each country's titles carrying the genre",
                           labels={"x": "Genre", "y": "Country", "color": "% of titles"}), height=450)

# ----------------------------------------------------------------- Ratings
with tabs[5]:
    a, b = st.columns(2)
    rt = d.rating.value_counts().reset_index()
    rt.columns = ["rating", "titles"]
    with a:
        show(px.bar(rt, x="rating", y="titles", text="titles", category_orders={"rating": an.order_ratings(rt.rating)},
                    title="Titles by rating (ordered from kids to mature)", labels={"rating": "Rating", "titles": "Titles"}))
    with b:
        rty = d.groupby(["rating", "type"]).size().reset_index(name="titles")
        show(bar_pct(rty, x="rating", y="titles", color="type", color_discrete_map=TYPE_COLORS,
                    category_orders={"rating": an.order_ratings(rty.rating)},
                    title="Movie vs TV Show share within each rating (100% stacked)",
                    labels={"rating": "Rating", "titles": "% of titles"}))
    a, b = st.columns(2)
    with a:
        rg = gf[gf.genre.isin(gs.nlargest(12, "titles").genre)].groupby(["genre", "rating"]).show_id.nunique().unstack(fill_value=0)
        if not rg.empty:
            rg = rg.div(rg.sum(axis=1), axis=0).mul(100)
            show(px.imshow(rg[an.order_ratings(rg.columns)], text_auto=".0f", aspect="auto", color_continuous_scale="Blues",
                           title="Rating mix by genre (% of each genre's titles)",
                           labels={"x": "Rating", "y": "Genre", "color": "%"}), height=450)
    with b:
        rc = cf[cf.country.isin(cs.nlargest(10, "titles").country)].groupby(["country", "rating"]).show_id.nunique().unstack(fill_value=0)
        if not rc.empty:
            rc = rc.div(rc.sum(axis=1), axis=0).mul(100)
            show(px.imshow(rc[an.order_ratings(rc.columns)], text_auto=".0f", aspect="auto", color_continuous_scale="Blues",
                           title="Rating mix by country (% of each country's titles)",
                           labels={"x": "Rating", "y": "Country", "color": "%"}), height=450)

# ---------------------------------------------------------------- Insights
with tabs[6]:
    st.caption("Written automatically from the CURRENT filter selection, so the numbers update as you filter. "
               "Under-representation means a gap within this catalogue (rules documented in app/analysis.py); "
               "the dataset has no audience or demand data, so treat these as leads to investigate, not proof.")
    for title, text in an.build_insights(d, g, c):
        st.markdown(f"#### {title}")
        st.markdown(text)

with tabs[7]:
    st.header("Catalogue Analytics (API)")
    st.caption("These catalogue-wide analytics are served by the FastAPI backend.")
    api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")

    @st.cache_data(ttl=600, show_spinner="Loading catalogue analytics from the API...")
    def load_api_analytics(base_url):
        def get_json(path, params=None):
            response = requests.get(f"{base_url}{path}", params=params, timeout=10)
            response.raise_for_status()
            return response.json()

        return (
            get_json("/kpis/release-years"),
            get_json("/content/growth-by-year"),
            get_json("/content/country-type", {"top_n": 10}),
            get_json("/content/genre-type", {"top_n": 10}),
        )

    try:
        release_kpis, growth, country_type_data, genre_type_data = load_api_analytics(api_base_url)
    except requests.RequestException:
        st.error(
            f"Could not reach the analytics API at {api_base_url}. "
            "Check that the API is running and API_BASE_URL is correct."
        )
        st.stop()
    except ValueError:
        st.error("The analytics API returned an invalid response. Check the API logs and try again.")
        st.stop()

    kpi_cards = st.columns(2)
    kpi_cards[0].metric("Average Release Year", f"{release_kpis['avg_release_year']:.1f}")
    kpi_cards[1].metric("Content Release Range", release_kpis["range_label"])

    growth_frame = pd.DataFrame(growth)
    if growth_frame.empty:
        st.info("The API returned no release-year data.")
    else:
        growth_chart = px.line(
            growth_frame,
            x="release_year",
            y="titles",
            markers=True,
            title="Titles by release year",
            labels={"release_year": "Release year", "titles": "Titles"},
        )
        show(growth_chart, height=420)
        peak_year = growth_frame.loc[growth_frame["titles"].idxmax()]
        latest_year = growth_frame.loc[growth_frame["release_year"].idxmax()]
        st.markdown(
            f"**Business insight:** Release volume peaks in {int(peak_year['release_year'])} "
            f"({int(peak_year['titles']):,} titles). The latest-year drop in "
            f"{int(latest_year['release_year'])} likely reflects the dataset being collected "
            "part-way through that year, rather than a real decline."
        )

    if country_type_data:
        country_frame = pd.DataFrame(country_type_data)
        country_chart_frame = country_frame.rename(columns={"movies": "Movies", "tv_shows": "TV Shows"})
        country_chart = px.bar(
            country_chart_frame,
            x="country",
            y=["Movies", "TV Shows"],
            barmode="group",
            title="Movies vs TV Shows by leading country",
            labels={"country": "Country", "value": "Titles", "variable": "Content type"},
            color_discrete_map={"Movies": TYPE_COLORS["Movie"], "TV Shows": TYPE_COLORS["TV Show"]},
        )
        country_chart.update_xaxes(title_text="Country", tickangle=-45)
        country_chart.update_yaxes(title_text="Titles")
        show(country_chart, height=430)
        country_leader = country_frame.iloc[0]
        st.markdown(
            f"**Business insight:** {country_leader['country']} leads among the returned "
            f"countries with {int(country_leader['total']):,} title associations "
            f"({int(country_leader['movies']):,} Movies and "
            f"{int(country_leader['tv_shows']):,} TV Shows)."
        )
    else:
        st.info("The API returned no country-by-type data.")

    if genre_type_data:
        genre_frame = pd.DataFrame(genre_type_data)
        genre_chart_frame = genre_frame.rename(columns={"movies": "Movies", "tv_shows": "TV Shows"})
        genre_chart = px.bar(
            genre_chart_frame,
            x="genre",
            y=["Movies", "TV Shows"],
            barmode="group",
            title="Movies vs TV Shows by leading genre",
            labels={"genre": "Genre", "value": "Titles", "variable": "Content type"},
            color_discrete_map={"Movies": TYPE_COLORS["Movie"], "TV Shows": TYPE_COLORS["TV Show"]},
        )
        genre_chart.update_xaxes(title_text="Genre", tickangle=-45)
        genre_chart.update_yaxes(title_text="Titles")
        show(genre_chart, height=430)
        genre_leader = genre_frame.iloc[0]
        st.markdown(
            f"**Business insight:** {genre_leader['genre']} leads among the returned "
            f"genres with {int(genre_leader['total']):,} titles "
            f"({int(genre_leader['movies']):,} Movies and "
            f"{int(genre_leader['tv_shows']):,} TV Shows)."
        )
    else:
        st.info("The API returned no genre-by-type data.")

st.sidebar.divider()
st.sidebar.caption("PySpark → MySQL → Plotly → Streamlit")
