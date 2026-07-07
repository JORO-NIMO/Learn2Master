"""
wsgi.py — WSGI entry point for production deployment.

Used by gunicorn (Render, Railway, Fly.io, Heroku):
    gunicorn wsgi:app

Loads .env automatically via app.py → python-dotenv.
"""
from app import app

if __name__ == "__main__":
    app.run()
