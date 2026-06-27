from routes.subjects import subjects_bp
from routes.learning import learning_bp
from routes.student import student_bp
from routes.teacher import teacher_bp
from routes.admin import admin_bp
from routes.framework import framework_bp
from routes.profile import profile_bp
from routes.analytics import analytics_bp
from routes.research import research_bp
from flask import Flask

from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.courses import courses_bp
from routes.mastery import mastery_bp


app = Flask(__name__)
app.secret_key = "learn2master_secret_key"


@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(courses_bp)
app.register_blueprint(mastery_bp)
app.register_blueprint(teacher_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(student_bp)
app.register_blueprint(subjects_bp)
app.register_blueprint(learning_bp)
app.register_blueprint(framework_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(research_bp)


if __name__ == "__main__":
    app.run(debug=True)