# Netflix Content Strategy Analytics Dashboard — Solution Files

This solution extends the existing Netflix ETL + MySQL + Plotly + Streamlit workflow.

## Files

- `01_Netflix_Content_Strategy_ETL.ipynb` — extended PySpark ETL with content-age, freshness, release-decade, and age-group features.
- `02_Prepare_Content_Strategy_Data.ipynb` — prepares analytical subsets/CSV for the dashboard.
- `netflix_content_strategy.sql` — creates the analytical tables and KPI queries in MySQL.
- `app.py` — interactive Streamlit + Plotly dashboard.
- `requirements.txt` — Python dependencies.
- `content_strategy_data.csv` — prepared solution dataset generated from the supplied demo data.

## Expected input

The ETL notebook expects the original Netflix titles CSV (`netflix_titles.csv`). If you already have the demo's `clean_netflix.csv`, the second notebook can be used directly.

## MySQL setup

1. Create/use the `netflix_db` database.
2. Load the existing cleaned dataset into a table named `clean_netflix`.
3. Run `netflix_content_strategy.sql`.
4. Update the MySQL credentials at the top of `app.py`.
5. Run:

```bash
streamlit run app.py
```

The SQL solution uses `COUNT(DISTINCT show_id)` for title-level metrics so that exploded genre rows do not inflate title counts.

## Dashboard sections

- Executive Summary
- Content Portfolio
- Content Freshness
- Genre Intelligence
- Geographic Analysis
- Interactive filters for release year, content type, country, and rating

## Important grain consideration

The cleaned dataset contains one row per title-genre association. Therefore:

- title-level metrics should use `COUNT(DISTINCT show_id)`
- genre-association metrics may use `COUNT(*)`
- the dashboard uses distinct-title logic for KPIs and title-level charts
