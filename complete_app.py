from flask import Flask, render_template, request, redirect, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'
DATABASE = os.path.join(app.instance_path, 'users.db')

def get_db():
    if not os.path.exists(app.instance_path):
        os.makedirs(app.instance_path)
    conn = sqlite3.connect(DATABASE)
    return conn

@app.route('/')
def home():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Learners WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    if user and check_password_hash(user[2], password):
        session['user_id'] = user[0]
        session['username'] = user[1]
        return redirect(url_for('dashboard'))
    else:
        flash('Invalid username or password')
        return redirect(url_for('home'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form['full_name']
        username = request.form['username']
        password = request.form['password']
        school_name = request.form['school_name']
        role = request.form['role']
        password_hash = generate_password_hash(password)

        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO Learners (username, password_hash, full_name, school_name, role) VALUES (?, ?, ?, ?, ?)",
                (username, password_hash, full_name, school_name, role)
            )
            conn.commit()
            conn.close()
            flash('Registration successful! Please log in.')
            return redirect(url_for('home'))
        except sqlite3.IntegrityError:
            flash('Username already exists. Please choose another one.')
            return redirect(url_for('register'))
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    user_id = session['user_id']
    conn = get_db()
    cursor = conn.cursor()

    # Get user info
    cursor.execute("SELECT full_name, school_name, role FROM Learners WHERE learner_id = ?", (user_id,))
    user_row = cursor.fetchone()
    user = {
        'full_name': user_row[0],
        'school_name': user_row[1],
        'role': user_row[2]
    }

    # Get progress data
    cursor.execute("""
        SELECT T.topic_name, P.completion_status, P.score
        FROM Progress P
        JOIN Topics T ON P.topic_id = T.topic_id
        WHERE P.learner_id = ?
    """, (user_id,))
    progress = [
        {'topic_name': row[0], 'completion_status': row[1], 'score': row[2]}
        for row in cursor.fetchall()
    ]

    # Get recommended topic (next uncompleted topic)
    cursor.execute("""
        SELECT T.topic_name, T.difficulty_level, T.content_url
        FROM Topics T
        LEFT JOIN Progress P ON T.topic_id = P.topic_id AND P.learner_id = ?
        WHERE P.completion_status IS NULL OR P.completion_status != 'completed'
        LIMIT 1
    """, (user_id,))
    row = cursor.fetchone()
    recommended = None
    if row:
        recommended = {
            'topic_name': row[0],
            'difficulty_level': row[1],
            'content_url': row[2]
        }

    conn.close()
    return render_template('dashboard.html', user=user, progress=progress, recommended=recommended)

if __name__ == '__main__':
    os.makedirs(app.instance_path, exist_ok=True)
    app.run(debug=True)