"""
Step 3 runner - executes sql/03_analytics.sql against MySQL and prints the validation + KPIs.
Run from the project root:   python etl/03_run_sql.py
"""
import os
import sys
import pandas as pd
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

sql = open(sys.argv[1] if len(sys.argv) > 1 else "sql/03_analytics.sql", encoding="utf-8").read()
# drop comment lines, then split into statements
body = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
statements = [s.strip() for s in body.split(";") if s.strip()]

validation = None
with eng.begin() as c:
    for s in statements:
        if s.upper().startswith("SELECT"):
            validation = pd.read_sql(text(s), c)      # the final validation query
        else:
            c.execute(text(s))
print(f"ran {len(statements) - 1} DDL statements\n")
print(validation.to_string(index=False))
print("\nKPI summary:")
print(pd.read_sql("SELECT * FROM kpi_summary", eng).T.to_string(header=False))
sys.exit(0 if (validation["result"] == "PASS").all() else 1)
