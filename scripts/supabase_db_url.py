"""Print a short-lived DATABASE_URL for the linked Supabase project.

Vercel will not show the hosted DATABASE_URL again, so coordinator jobs such
as `flask seed-beta` use the Supabase CLI's temporary login instead:

    export DATABASE_URL="$(python3 scripts/supabase_db_url.py)"

Needs `supabase login` and `supabase link` once. Print it only into a
variable: it is a working password for the hosted database.
"""
import re
import subprocess
import sys
from urllib.parse import quote

out = subprocess.run(
    ["supabase", "db", "dump", "--linked", "--dry-run"], capture_output=True, text=True
).stdout
env = dict(re.findall(r'export (PG\w+)="?([^"\n]*)"?', out))
if not all(k in env for k in ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE")):
    sys.exit("Could not get a login from the Supabase CLI. Run `supabase login` and `supabase link`.")
user, password = quote(env["PGUSER"], safe=""), quote(env["PGPASSWORD"], safe="")
# The temporary login can read nothing itself; it acts as the postgres role.
print(
    f"postgresql+psycopg://{user}:{password}@{env['PGHOST']}:{env['PGPORT']}/{env['PGDATABASE']}"
    "?sslmode=require&options=-c%20role%3Dpostgres"
)
