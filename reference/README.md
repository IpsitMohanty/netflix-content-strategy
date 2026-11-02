# Netflix Content Strategy Analytics

An end-to-end analytics project exploring Netflix's content portfolio, freshness, genre distribution, geographic reach, and release trends using PySpark, MySQL, SQL, Plotly, and Streamlit.

## Project Overview

This project transforms Netflix title data into an analytical dataset and dashboard. It focuses on understanding the composition and evolution of the content catalogue through title-level KPIs, genre analysis, country distribution, ratings, and content-age metrics.

The pipeline separates data preparation, analytical modelling, validation, and dashboard visualisation.

## Project Structure

```text
.
├── app/
│   ├── analysis.py
│   └── app.py
├── data/
│   └── processed/
├── docs/
│   ├── evolution.png
│   ├── freshness.png
│   ├── genres.png
│   ├── geography.png
│   ├── insight.png
│   ├── portfolio.png
│   └── ratings.png
├── etl/
│   ├── 01_etl.py
│   ├── 02_load_mysql.py
│   └── 03_run_sql.py
├── reference/
├── sql/
│   └── 03_analytics.sql
├── tests/
│   └── validate_grain.py
├── .gitignore
├── README.md
└── requirements.txt