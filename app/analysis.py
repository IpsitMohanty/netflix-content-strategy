"""
Pure-pandas analysis helpers for the dashboard (no Streamlit / Plotly imports,
so they can be tested on their own).

GRAIN RULES (same as sql/03_analytics.sql)
  dim      one row per title            -> KPIs, type / rating / year / age
  bg       one row per title + genre    -> genre analysis (title counted once per genre)
  bc       one row per title + country  -> country analysis ('Unknown' already removed)
"""
import pandas as pd

AGE_ORDER = ["Very Recent", "Recent", "Mature", "Older", "Legacy"]
RATING_ORDER = ["TV-Y", "TV-Y7", "TV-Y7-FV", "TV-G", "G", "TV-PG", "PG",
                "PG-13", "TV-14", "R", "NC-17", "TV-MA", "Not Rated"]

# Netflix genre tags are type-specific ("Dramas" = movies, "TV Dramas" = series).
# To compare Movies vs TV on the same subject we group equivalent tags into a theme.
THEME_MAP = {
    "Dramas": "Drama", "TV Dramas": "Drama",
    "Comedies": "Comedy", "TV Comedies": "Comedy",
    "Action & Adventure": "Action & Adventure", "TV Action & Adventure": "Action & Adventure",
    "Sci-Fi & Fantasy": "Sci-Fi & Fantasy", "TV Sci-Fi & Fantasy": "Sci-Fi & Fantasy",
    "Horror Movies": "Horror", "TV Horror": "Horror",
    "Thrillers": "Thriller", "TV Thrillers": "Thriller",
    "Romantic Movies": "Romance", "Romantic TV Shows": "Romance",
    "Children & Family Movies": "Kids & Family", "Kids' TV": "Kids & Family",
    "Documentaries": "Documentary & Factual", "Docuseries": "Documentary & Factual",
    "Science & Nature TV": "Documentary & Factual",
    "Stand-Up Comedy": "Stand-Up & Talk", "Stand-Up Comedy & Talk Shows": "Stand-Up & Talk",
    "Classic Movies": "Classic & Cult", "Cult Movies": "Classic & Cult",
    "Classic & Cult TV": "Classic & Cult",
    "Anime Features": "Anime", "Anime Series": "Anime",
    "International Movies": "International", "International TV Shows": "International",
}


GENERIC_TAGS = {"Movies", "TV Shows"}                       # catch-all tags, not real genres
CLASSIC_TAGS = {"Classic Movies", "Cult Movies", "Classic & Cult TV"}   # old by definition


def order_ratings(values):
    vals = list(dict.fromkeys(values))
    return [r for r in RATING_ORDER if r in vals] + sorted(r for r in vals if r not in RATING_ORDER)


# ---------------------------------------------------------------- filtering
def apply_filters(dim, bg, bc, year_range, types, ratings, countries=(), genres=()):
    """Filter at title level, then keep only matching rows in the bridge tables.
    A country/genre filter keeps titles that have ANY selected value; the bridge
    tables then still list all of those titles' genres/countries."""
    d = dim[dim.release_year.between(*year_range) & dim.type.isin(types) & dim.rating.isin(ratings)]
    if len(countries):
        d = d[d.show_id.isin(bc.loc[bc.country.isin(countries), "show_id"])]
    if len(genres):
        d = d[d.show_id.isin(bg.loc[bg.genre.isin(genres), "show_id"])]
    return d.copy(), bg[bg.show_id.isin(d.show_id)].copy(), bc[bc.show_id.isin(d.show_id)].copy()


# --------------------------------------------------------------------- KPIs
def compute_kpis(dim, bg, bc):
    n = len(dim)
    movies = int((dim.type == "Movie").sum())
    tv = int((dim.type == "TV Show").sum())
    cc = bc.country.value_counts()
    return {
        "total": n, "movies": movies, "tv": tv,
        "ratio": movies / tv if tv else None,
        "movie_pct": 100 * movies / n if n else 0.0,
        "tv_pct": 100 * tv / n if n else 0.0,
        "avg_age": float(dim.content_age.mean()) if n else 0.0,
        "recent_pct": 100 * float(dim.is_recent.mean()) if n else 0.0,
        "n_genres": int(bg.genre.nunique()),
        "n_countries": int(bc.country.nunique()),
        "top_rating": dim.rating.value_counts().idxmax() if n else "-",
        "top_country": cc.index[0] if len(cc) else "-",
    }


# ------------------------------------------------------------ joined frames
_TITLE_COLS = ["show_id", "type", "content_age", "content_age_group", "is_recent",
               "release_year", "release_decade", "rating"]


def genre_frame(dim, bg):
    return bg.merge(dim[_TITLE_COLS], on="show_id")


def country_frame(dim, bc):
    return bc.merge(dim[_TITLE_COLS], on="show_id")


def genre_summary(gf):
    return (gf.groupby("genre")
              .agg(titles=("show_id", "nunique"),
                   recent_pct=("is_recent", lambda s: 100 * s.mean()),
                   avg_age=("content_age", "mean"),
                   movie_pct=("type", lambda s: 100 * (s == "Movie").mean()))
              .reset_index())


def country_summary(cf):
    return (cf.groupby("country")
              .agg(titles=("show_id", "nunique"),
                   tv_pct=("type", lambda s: 100 * (s == "TV Show").mean()),
                   avg_age=("content_age", "mean"))
              .reset_index())


def genre_pairs(bg, top=10):
    m = bg.merge(bg, on="show_id")
    m = m[m.genre_x < m.genre_y]
    out = m.groupby(["genre_x", "genre_y"]).size().reset_index(name="titles")
    out["pair"] = out.genre_x + " + " + out.genre_y
    return out.nlargest(top, "titles")


def theme_summary(gf):
    """Movies vs TV titles per theme, for themes that exist in both formats."""
    t = gf.assign(theme=gf.genre.map(THEME_MAP)).dropna(subset=["theme"])
    p = (t.groupby(["theme", "type"]).show_id.nunique()
          .unstack(fill_value=0).reindex(columns=["Movie", "TV Show"], fill_value=0))
    p = p.rename(columns={"Movie": "movies", "TV Show": "tv"}).reset_index()
    p["movie_to_tv"] = p.movies / p.tv.where(p.tv > 0)
    return p


# ---------------------------------------------------------------- insights
def build_insights(dim, bg, bc, min_genre=30, min_country=30):
    """Data-driven findings. Every number is computed from the CURRENT filter.

    UNDERREPRESENTATION RULES (explicit, so they can be challenged):
      * Niche genre   : a genre with >= 15 titles that is among the 3 smallest
                        (floor of 15 keeps one-off tags out; the generic "Movies" and
                        "TV Shows" catch-all tags are not genres and are ignored).
      * Format gap    : a theme (Movie/TV tags grouped, see THEME_MAP) with
                        >= `min_genre` titles in EACH format and the most lopsided
                        movie:TV ratio. Lopsided = relatively under-served format.
      * Market gap    : a country with >= `min_country` titles whose TV Show share is
                        lowest, plus the long tail of countries with < 10 titles.
      The data has no audience or demand figures, so these are catalogue gaps,
      not proof of unmet demand.
    """
    n = len(dim)
    if n == 0:
        return []
    out = []
    k = compute_kpis(dim, bg, bc)
    gf, cf = genre_frame(dim, bg), country_frame(dim, bc)
    gs, cs = genre_summary(gf), country_summary(cf)
    big = gs[(gs.titles >= min_genre) & ~gs.genre.isin(GENERIC_TAGS)]
    big_fresh = big[~big.genre.isin(CLASSIC_TAGS)]       # classics are old by definition

    # 1. Portfolio
    dom = "Movies" if k["movies"] >= k["tv"] else "TV Shows"
    ratio = (f" (about {k['ratio']:.1f} movies for every TV show)" if k["ratio"] else "")
    out.append(("Portfolio mix",
                f"{dom} dominate the selection: {k['movie_pct']:.1f}% Movies and "
                f"{k['tv_pct']:.1f}% TV Shows across {n:,} titles{ratio}."))

    # 2. Strongest genres
    top = gs.nlargest(3, "titles")
    txt = "; ".join(f"{r.genre} ({r.titles:,} titles, {100 * r.titles / n:.0f}% of the catalogue)"
                    for r in top.itertuples())
    out.append(("Strongest genres", f"{txt}. Titles carry several genre tags, so shares add to more than 100%."))

    # 3. Freshness
    old_share = 100 * dim.content_age_group.isin(["Older", "Legacy"]).mean()
    txt = (f"The average title is {k['avg_age']:.1f} years old (measured from the newest release year in the data); "
           f"{k['recent_pct']:.0f}% were released in the last 5 years and {old_share:.0f}% are Older or Legacy (11+ years).")
    if len(big_fresh) >= 2:
        fresh, old = big_fresh.loc[big_fresh.recent_pct.idxmax()], big_fresh.loc[big_fresh.avg_age.idxmax()]
        txt += (f" Freshest genre: {fresh.genre} ({fresh.recent_pct:.0f}% recent). "
                f"Oldest-skewing genre (excluding classics): {old.genre} (average age {old.avg_age:.1f} years).")
    out.append(("Catalogue freshness", txt))

    # 4. Evolution
    dec = dim.groupby("release_decade").agg(n=("show_id", "size"), tv=("type", lambda s: 100 * (s == "TV Show").mean()))
    dec = dec[dec.n >= 50]
    txt = f"Release volume peaks in {int(dim.release_year.value_counts().idxmax())}."
    if len(dec) >= 2:
        a, b = dec.iloc[0], dec.iloc[-1]
        txt += (f" TV Shows were {a.tv:.0f}% of titles released in the {int(dec.index[0])}s and "
                f"{b.tv:.0f}% in the {int(dec.index[-1])}s.")
    out.append(("Catalogue evolution", txt))

    # 5. Geography
    if len(cs):
        vc = cf.groupby("country").show_id.nunique().sort_values(ascending=False)
        top3 = ", ".join(vc.index[:3])
        tail = int((vc < 10).sum())
        out.append(("Geographic concentration",
                    f"{vc.index[0]} appears on {100 * vc.iloc[0] / n:.0f}% of titles; the top 3 ({top3}) account for "
                    f"{100 * vc.iloc[:3].sum() / vc.sum():.0f}% of all country credits. "
                    f"{tail} of {len(vc)} countries have fewer than 10 titles, a long tail of small markets."))

    # 6. Underrepresentation
    parts = []
    niche = gs[(gs.titles >= 15) & ~gs.genre.isin(GENERIC_TAGS)].nsmallest(3, "titles")
    if len(niche):
        parts.append("Niche genres: " + ", ".join(f"{r.genre} ({r.titles})" for r in niche.itertuples()) + ".")
    ts = theme_summary(gf)
    ts = ts[(ts.movies >= min_genre) & (ts.tv >= min_genre)]
    if len(ts):
        mh = ts.loc[ts.movie_to_tv.idxmax()]
        sh = ts.loc[ts.movie_to_tv.idxmin()]
        parts.append(f"Most movie-heavy theme: {mh.theme} ({int(mh.movies):,} movies vs {int(mh.tv):,} series).")
        if sh.movie_to_tv < 1:
            parts.append(f"Most series-heavy theme: {sh.theme} ({int(sh.tv):,} series vs {int(sh.movies):,} movies).")
    cbig = cs[cs.titles >= min_country]
    if len(cbig):
        lo = cbig.loc[cbig.tv_pct.idxmin()]
        parts.append(f"Market with the fewest TV Shows: {lo.country} ({lo.tv_pct:.0f}% TV across {lo.titles} titles).")
    if parts:
        out.append(("Possible underrepresentation", " ".join(parts)))

    # 7. Opportunities
    opp = []
    if len(ts):
        mh = ts.loc[ts.movie_to_tv.idxmax()]
        opp.append(f"Develop more series in {mh.theme}: it has {mh.movie_to_tv:.1f}x as many movies as series.")
    if len(big_fresh) >= 2:
        old = big_fresh.loc[big_fresh.avg_age.idxmax()]
        opp.append(f"Refresh {old.genre} with newer titles: it is the oldest-skewing genre ({old.avg_age:.1f} years on average).")
    ref = int(dim.release_year.max())
    last5 = gf[gf.release_year >= ref - 4].groupby("genre").show_id.nunique()
    prev5 = gf[(gf.release_year >= ref - 9) & (gf.release_year < ref - 4)].groupby("genre").show_id.nunique()
    gr = pd.concat([last5.rename("last5"), prev5.rename("prev5")], axis=1).fillna(0)
    gr = gr[(gr.prev5 >= 20) & (gr.last5 >= 20)]
    if len(gr):
        gr["growth"] = 100 * (gr.last5 / gr.prev5 - 1)
        g = gr.growth.idxmax()
        opp.append(f"Double down on {g}: titles released in {ref - 4}-{ref} are up {gr.growth.max():.0f}% on the previous five years.")
    if len(cbig) >= 3 and len(vc):
        opp.append("Broaden the market mix: acquire or commission from countries in the long tail, where the catalogue is thinnest.")
    if opp:
        out.append(("Content opportunities", "\n".join(f"{i}. {o}" for i, o in enumerate(opp[:3], 1))))
    return out
