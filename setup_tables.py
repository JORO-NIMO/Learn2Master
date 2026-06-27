import sqlite3

with open("add_dashboard_tables.sql", "r") as f:
    sql_script = f.read()

conn = sqlite3.connect("instance/users.db")
cursor = conn.cursor()
cursor.executescript(sql_script)
conn.commit()
conn.close()

print("Tables created successfully.")