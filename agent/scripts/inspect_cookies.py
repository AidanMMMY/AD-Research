import sqlite3
from pathlib import Path
p = Path("/profile/Default/Cookies")
print(f"File size: {p.stat().st_size}")
conn = sqlite3.connect(str(p))
cur = conn.cursor()
cur.execute("SELECT name, host_key FROM cookies ORDER BY host_key")
rows = cur.fetchall()
print(f"Total: {len(rows)} cookies")
for n, h in rows:
    print(f"  {h} | {n}")
