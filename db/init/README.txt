10-netflix_db.sql is a mysqldump of the populated local netflix_db. It contains
the three core tables and all analytics aggregate tables used by the API and
dashboard. Do not replace it with fabricated or placeholder data.

The exact command to regenerate the dump is documented in README.md. MySQL's
entrypoint only runs initialization files when mysql_data is empty.
