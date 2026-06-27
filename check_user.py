import sqlite3

conn = sqlite3.connect("learn2master.db")
conn.row_factory = sqlite3.Row

user = conn.execute("""
SELECT users.user_id, users.username, users.full_name, users.password_hash, roles.role_name
FROM users
JOIN roles ON users.role_id = roles.role_id
WHERE users.username = 'elijah'
""").fetchone()

if user:
    print("User found:")
    print("ID:", user["user_id"])
    print("Username:", user["username"])
    print("Full name:", user["full_name"])
    print("Role:", user["role_name"])
    print("Password hash:", user["password_hash"])
else:
    print("User NOT found")

conn.close()