import os
import json
from functools import wraps
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash
from engine import calculate_bkt, get_recommendation
from models import db, User, Subject, Topic, LearningOutcome, MasteryRecord, Evidence, RecommendationLog, AttemptLog, LearningResource, Question, SubStrand, PerformanceIndicator

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///learn2master.db'

@app.template_filter('from_json')
def from_json_filter(value):
    return json.loads(value)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24))

db.init_app(app)
csrf = CSRFProtect(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if current_user.role not in roles:
                flash("Access denied.")
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'student':
        subjects = Subject.query.all()
        return render_template('student_dashboard.html', subjects=subjects)
    elif current_user.role == 'teacher':
        return render_template('teacher_dashboard.html')
    elif current_user.role == 'admin':
        return render_template('admin_dashboard.html')
    return "Unknown role"

@app.route('/subject/<int:subject_id>')
@login_required
@role_required('student', 'teacher', 'admin')
def view_subject(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    return render_template('subject.html', subject=subject)

@app.route('/learning_outcome/<int:lo_id>')
@login_required
@role_required('student', 'teacher', 'admin')
def view_lo(lo_id):
    lo = LearningOutcome.query.get_or_404(lo_id)

    # Check for sequential locking (only for students)
    is_locked = False
    if current_user.role == 'student':
        previous_los = LearningOutcome.query.filter(
            LearningOutcome.topic_id == lo.topic_id,
            LearningOutcome.order < lo.order
        ).all()

        for prev_lo in previous_los:
            prev_mastery = MasteryRecord.query.filter_by(
                user_id=current_user.id,
                learning_outcome_id=prev_lo.id
            ).first()
            if not prev_mastery or prev_mastery.knowledge_level < 0.85:
                is_locked = True
                break

    mastery = MasteryRecord.query.filter_by(user_id=current_user.id, learning_outcome_id=lo_id).first()
    knowledge_level = mastery.knowledge_level if mastery else 0.0

    # Adaptive resource selection
    resources = LearningResource.query.filter(
        LearningResource.learning_outcome_id == lo_id,
        LearningResource.min_mastery <= knowledge_level,
        LearningResource.max_mastery >= knowledge_level
    ).all()

    rec, expl = get_recommendation(knowledge_level)
    return render_template('learning_outcome.html', lo=lo, knowledge_level=knowledge_level, recommendation=rec, explanation=expl, is_locked=is_locked, resources=resources)

@app.route('/lo/<int:lo_id>/test', methods=['POST'])
@login_required
@role_required('student')
def take_test(lo_id):
    correct = request.form.get('correct') == 'true'
    mastery = MasteryRecord.query.filter_by(user_id=current_user.id, learning_outcome_id=lo_id).first()

    # Initialize with p_init if not exists
    if not mastery:
        p_init = 0.3 # BKT default
        mastery = MasteryRecord(user_id=current_user.id, learning_outcome_id=lo_id, knowledge_level=p_init)
        db.session.add(mastery)

    p_before = mastery.knowledge_level
    new_level, reasoning = calculate_bkt(p_before, correct)
    rec, expl = get_recommendation(new_level)

    # Enrich explanation with AI reasoning for XAI
    full_explanation = f"{expl} | AI Insight: {reasoning['message']}"

    log = RecommendationLog(user_id=current_user.id, learning_outcome_id=lo_id, recommendation=rec, explanation=full_explanation)
    db.session.add(log)

    attempt = AttemptLog(
        user_id=current_user.id,
        learning_outcome_id=lo_id,
        correct=correct,
        p_before=p_before,
        p_after=new_level
    )
    db.session.add(attempt)

    mastery.knowledge_level = new_level
    db.session.commit()
    return redirect(url_for('view_lo', lo_id=lo_id))

@app.route('/teacher/evidence')
@login_required
@role_required('teacher')
def teacher_evidence():
    # Filter by teacher's school for basic multi-tenancy support
    evidences = Evidence.query.join(User).filter(User.school == current_user.school).all()
    return render_template('teacher_evidence.html', evidences=evidences)

@app.route('/teacher/recommendations')
@login_required
@role_required('teacher')
def teacher_recommendations():
    logs = RecommendationLog.query.join(User).filter(User.school == current_user.school).order_by(RecommendationLog.timestamp.desc()).limit(100).all()
    return render_template('teacher_recommendations.html', logs=logs)

@app.route('/admin/users')
@login_required
@role_required('admin')
def admin_users():
    users = User.query.all()
    return render_template('admin_users.html', users=users)

@app.route('/lo/<int:lo_id>/evidence', methods=['POST'])
@login_required
@role_required('student')
def submit_evidence(lo_id):
    content = request.form.get('content')
    evidence_type = request.form.get('type', 'text')

    # AI Feature: Basic NLP Keyword Analysis for Reflection Depth
    keywords = ['learned', 'understand', 'concept', 'difficult', 'mastery', 'demonstrate', 'experiment']
    depth_score = sum(1 for word in keywords if word in content.lower())
    nlp_analysis = f"Reflection Depth Score: {depth_score}/{len(keywords)}"
    content = f"{content} | NLP Analysis: {nlp_analysis}"

    evidence = Evidence(
        user_id=current_user.id,
        learning_outcome_id=lo_id,
        type=evidence_type,
        content=content,
        status='pending'
    )
    db.session.add(evidence)
    db.session.commit()
    flash("Evidence submitted successfully and is awaiting teacher review.")
    return redirect(url_for('view_lo', lo_id=lo_id))

@app.route('/teacher/evidence/<int:evidence_id>/review', methods=['POST'])
@login_required
@role_required('teacher')
def review_evidence(evidence_id):
    evidence = Evidence.query.get_or_404(evidence_id)
    status = request.form.get('status') # approved or rejected
    feedback = request.form.get('feedback')

    evidence.status = status
    evidence.teacher_feedback = feedback

    # If approved, boost mastery to 1.0 (or 0.99)
    if status == 'approved':
        mastery = MasteryRecord.query.filter_by(
            user_id=evidence.user_id,
            learning_outcome_id=evidence.learning_outcome_id
        ).first()
        if not mastery:
            mastery = MasteryRecord(user_id=evidence.user_id, learning_outcome_id=evidence.learning_outcome_id)
            db.session.add(mastery)
        mastery.knowledge_level = 0.99

    db.session.commit()
    flash(f"Evidence {status} successfully.")
    return redirect(url_for('teacher_evidence'))

@app.route('/student/progress')
@login_required
@role_required('student')
def view_progress():
    attempts = AttemptLog.query.filter_by(user_id=current_user.id).order_by(AttemptLog.timestamp.desc()).all()
    return render_template('progress.html', attempts=attempts)

@app.route('/lo/<int:lo_id>/quiz')
@login_required
@role_required('student')
def take_quiz(lo_id):
    lo = LearningOutcome.query.get_or_404(lo_id)
    questions = Question.query.filter_by(learning_outcome_id=lo_id).all()
    return render_template('quiz.html', lo=lo, questions=questions)

@app.route('/quiz/submit', methods=['POST'])
@login_required
@role_required('student')
def submit_quiz():
    lo_id = request.form.get('lo_id')
    questions = Question.query.filter_by(learning_outcome_id=lo_id).all()

    correct_count = 0
    total = len(questions)

    for q in questions:
        answer = request.form.get(f'q_{q.id}')
        if answer == q.correct_answer:
            correct_count += 1

    # Calculate performance for BKT
    # We'll treat the whole quiz as one or more BKT observations
    mastery = MasteryRecord.query.filter_by(user_id=current_user.id, learning_outcome_id=lo_id).first()
    if not mastery:
        mastery = MasteryRecord(user_id=current_user.id, learning_outcome_id=lo_id, knowledge_level=0.3)
        db.session.add(mastery)

    # Update BKT for each question to simulate progression within the quiz
    for q in questions:
        answer = request.form.get(f'q_{q.id}')
        is_correct = (answer == q.correct_answer)
        p_before = mastery.knowledge_level
        new_level, reasoning = calculate_bkt(p_before, is_correct)

        attempt = AttemptLog(
            user_id=current_user.id,
            learning_outcome_id=lo_id,
            correct=is_correct,
            p_before=p_before,
            p_after=new_level
        )
        db.session.add(attempt)
        mastery.knowledge_level = new_level

    db.session.commit()
    flash(f"Quiz submitted. You got {correct_count}/{total} correct. Mastery updated.")
    return redirect(url_for('view_lo', lo_id=lo_id))

@app.route('/admin/research')
@login_required
@role_required('admin')
def research_dashboard():
    # Cohort Analysis for Chapter Four
    total_students = User.query.filter_by(role='student').count()
    avg_mastery = db.session.query(db.func.avg(MasteryRecord.knowledge_level)).scalar() or 0
    total_attempts = AttemptLog.query.count()

    # Mastery counts by subject (basic heatmap logic)
    subjects = Subject.query.all()
    subject_stats = []
    for s in subjects:
        lo_ids = [lo.id for topic in s.topics for lo in topic.learning_outcomes]
        mastered_count = MasteryRecord.query.filter(
            MasteryRecord.learning_outcome_id.in_(lo_ids),
            MasteryRecord.knowledge_level >= 0.85
        ).count()
        subject_stats.append({'name': s.name, 'mastered': mastered_count})

    return render_template('research_dashboard.html',
                           total_students=total_students,
                           avg_mastery=avg_mastery,
                           total_attempts=total_attempts,
                           subject_stats=subject_stats)

@app.route('/admin/audit')
@login_required
@role_required('admin')
def admin_audit():
    attempts = AttemptLog.query.order_by(AttemptLog.timestamp.desc()).limit(200).all()
    recommendations = RecommendationLog.query.order_by(RecommendationLog.timestamp.desc()).limit(200).all()
    return render_template('admin_audit.html', attempts=attempts, recommendations=recommendations)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
