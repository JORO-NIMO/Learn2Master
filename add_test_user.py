import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect('instance/users.db')
cursor = conn.cursor()

password_hash = generate_password_hash("Test@1234")

# Insert test user
cursor.execute("""
INSERT INTO Learners (username, password_hash, full_name, school_name, role)
VALUES (?, ?, ?, ?, ?)
""", ("testuser", password_hash, "Test User", "Kigezi High School", "student"))

conn.commit()
conn.close()
print("Test user added successfully.")