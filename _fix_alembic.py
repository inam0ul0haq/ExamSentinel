"""Restore alembic_version stamp after truncate."""
import psycopg2

conn = psycopg2.connect(
    host="shinkansen.proxy.rlwy.net",
    port=58351,
    dbname="railway",
    user="postgres",
    password="JOKekKUODjPqlFriwMHLNNZcpePEkwKj",
    sslmode="require",
)
cur = conn.cursor()
cur.execute("DELETE FROM alembic_version")
cur.execute("INSERT INTO alembic_version (version_num) VALUES ('0ef080486833')")
conn.commit()
cur.execute("SELECT version_num FROM alembic_version")
print("alembic_version:", cur.fetchone())
conn.close()
print("FIXED — Railway deploy should succeed now.")
