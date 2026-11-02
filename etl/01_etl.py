"""
Step 1 - PySpark ETL: raw netflix_titles.csv -> three analytical tables (CSV).

Grain of the outputs (this is the key design decision):
  dim_title      one row per title        -> KPIs, type/rating/year/age analysis
  bridge_genre   one row per title+genre  -> genre analysis
  bridge_country one row per title+country-> country analysis (multi-country titles)

Run:  python etl/01_etl.py data/netflix_titles.csv data/processed
"""
import sys
from pyspark.sql import SparkSession, functions as F

raw_path = sys.argv[1] if len(sys.argv) > 1 else "data/netflix_titles.csv"
out_dir = sys.argv[2] if len(sys.argv) > 2 else "data/processed"

spark = (
    SparkSession.builder.appName("Netflix-Content-Strategy-ETL")
    .config("spark.driver.bindAddress", "127.0.0.1")
    .config("spark.driver.host", "127.0.0.1")
    .getOrCreate()
)

raw = (
    spark.read.option("header", True).option("multiLine", True)
    .option("escape", '"').csv(raw_path)
)
print("raw rows:", raw.count())

# ---------- 1. Clean ----------
df = (
    raw.dropna(subset=["show_id", "title"])
    .dropDuplicates(["show_id"])
    # 3 rows have the duration shifted into the rating column ("74 min")
    .withColumn("duration", F.when(F.col("rating").rlike(r"\d+ min$"), F.col("rating"))
                             .otherwise(F.col("duration")))
    .withColumn("rating", F.when(F.col("rating").rlike(r"\d+ min$"), None)
                           .otherwise(F.trim(F.col("rating"))))
    # NR / UR / missing all mean "not rated"
    .withColumn("rating", F.when(F.col("rating").isNull() | F.col("rating").isin("NR", "UR"),
                                 "Not Rated").otherwise(F.col("rating")))
    .withColumn("release_year", F.col("release_year").cast("int"))
    .withColumn("date_added", F.coalesce(                    # raw: "September 24, 2021"; cleaned: "2021-09-24"
        F.to_date(F.trim("date_added"), "MMMM d, yyyy"),
        F.to_date(F.trim("date_added"), "yyyy-MM-dd")))
    .na.fill({"country": "Unknown", "director": "Unknown", "cast": "Unknown", "listed_in": "Unknown"})
)

# ---------- 2. Derived attributes ----------
# Age is anchored to the newest release year in the data (not today's date),
# so the buckets don't drift empty as the calendar moves on.
ref_year = df.agg(F.max("release_year")).first()[0]
print("reference year:", ref_year)

age = F.lit(ref_year) - F.col("release_year")
dim_title = (
    df.filter(F.col("release_year").isNotNull())      # keep ALL years: old content is part of the story
    .withColumn("content_age", age)
    .withColumn("content_age_group",
        F.when(age <= 2, "Very Recent")   # last 3 release years
         .when(age <= 5, "Recent")
         .when(age <= 10, "Mature")
         .when(age <= 20, "Older")
         .otherwise("Legacy"))
    .withColumn("release_decade", (F.floor(F.col("release_year") / 10) * 10).cast("int"))
    .withColumn("is_recent", F.when(age <= 5, 1).otherwise(0))
    .withColumn("year_added", F.year("date_added"))
    .withColumn("primary_country", F.trim(F.split("country", ",").getItem(0)))
    .withColumn("n_genres", F.size(F.split("listed_in", r",\s*")))
    .withColumn("duration_value", F.regexp_extract("duration", r"(\d+)", 1).cast("int"))
    .select("show_id", "type", "title", "primary_country", "release_year", "release_decade",
            "year_added", "rating", "duration_value", "content_age", "content_age_group",
            "is_recent", "n_genres")
)

# ---------- 3. Bridge tables (one row per title+value) ----------
keep = dim_title.select("show_id")
bridge_genre = (
    df.join(keep, "show_id")
    .select("show_id", F.explode(F.split("listed_in", r",\s*")).alias("genre"))
    .withColumn("genre", F.trim("genre")).distinct()
)
bridge_country = (
    df.join(keep, "show_id")
    .select("show_id", F.explode(F.split("country", r",\s*")).alias("country"))
    .withColumn("country", F.trim("country"))
    .filter(F.col("country") != "").distinct()
)

# ---------- 4. Validate grain ----------
n_titles = dim_title.count()
assert n_titles == dim_title.select("show_id").distinct().count(), "dim_title must be unique per show_id"
print("titles:", n_titles, "| genre rows:", bridge_genre.count(), "| country rows:", bridge_country.count())

# ---------- 5. Save ----------
for name, d in [("dim_title", dim_title), ("bridge_genre", bridge_genre), ("bridge_country", bridge_country)]:
    d.toPandas().to_csv(f"{out_dir}/{name}.csv", index=False)
    print("saved", name)
spark.stop()
