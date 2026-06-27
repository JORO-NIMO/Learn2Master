import sqlite3
from werkzeug.security import check_password_hash

conn = sqlite3.connect("learn2master.db")
conn.row_factory = sqlite3.Row

user = conn.execute(
    "SELECT password_hash FROM users WHERE username = ?",
    ("elijah",)
).fetchone()

if not user:
    print("User not found")
else:
    print(check_password_hash(user["password_hash"], "12345"))

conn.close()