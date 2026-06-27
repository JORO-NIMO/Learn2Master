# check_tables.py

import sqlite3

conn = sqlite3.connect("learn2master.db")
cursor = conn.cursor()

cursor.execute("""
SELECT name
FROM sqlite_master
WHERE type='table';
""")

for table in cursor.fetchall():
    print(table[0])

conn.close()