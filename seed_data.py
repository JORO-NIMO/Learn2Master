import json
from flask import Flask
from models import db, User, Subject, Topic, LearningOutcome, LearningResource, Question, SubStrand, PerformanceIndicator
from werkzeug.security import generate_password_hash

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///learn2master.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

def seed():
    with app.app_context():
        db.drop_all()
        db.create_all()

        # Users
        users = [
            User(username='elijah', password_hash=generate_password_hash('12345'), role='student', school='Demo Secondary School'),
            User(username='teacher', password_hash=generate_password_hash('12345'), role='teacher', school='Demo Secondary School'),
            User(username='admin', password_hash=generate_password_hash('12345'), role='admin', school='System')
        ]
        db.session.add_all(users)

        # CBC Hierarchy: Physics
        physics = Subject(name='Physics')
        db.session.add(physics)
        db.session.commit()

        mechanics = Topic(subject_id=physics.id, name='Introduction to Mechanics', order=1)
        db.session.add(mechanics)
        db.session.commit()

        general_physics = SubStrand(strand_id=mechanics.id, name='General Physics Concepts', order=1)
        db.session.add(general_physics)
        db.session.commit()

        lo1 = LearningOutcome(
            topic_id=mechanics.id,
            name='Distance and Displacement',
            description='Understand the difference between distance and displacement.',
            order=1,
            notes='Basic scalar vs vector concepts.'
        )
        db.session.add(lo1)
        db.session.commit()

        # Seed Adaptive Resources for LO1
        res1 = LearningResource(
            learning_outcome_id=lo1.id,
            type='notes',
            title='Introductory Notes',
            content='Foundational concepts for distance and displacement.',
            min_mastery=0.0,
            max_mastery=0.6
        )
        db.session.add(res1)

        pi1 = PerformanceIndicator(
            sub_strand_id=general_physics.id,
            learning_outcome_id=lo1.id,
            description='Distinguish between distance and displacement in straight line motion.',
            order=1
        )
        db.session.add(pi1)
        db.session.commit()

        # Questions for LO1
        q1 = Question(
            learning_outcome_id=lo1.id,
            text='A student walks 3km North and then 4km East. What is their total distance?',
            type='mcq',
            options=json.dumps(['7km', '5km', '1km', '12km']),
            correct_answer='7km'
        )
        q2 = Question(
            learning_outcome_id=lo1.id,
            text='In the previous scenario, what is the magnitude of their displacement?',
            type='mcq',
            options=json.dumps(['7km', '5km', '1km', '0km']),
            correct_answer='5km'
        )
        db.session.add_all([q1, q2])
        db.session.commit()

        # CBC Hierarchy: ICT
        ict = Subject(name='ICT')
        db.session.add(ict)
        db.session.commit()

        comp_systems = Topic(subject_id=ict.id, name='Computer Systems', order=1)
        db.session.add(comp_systems)
        db.session.commit()

        hardware = SubStrand(strand_id=comp_systems.id, name='Hardware Components', order=1)
        db.session.add(hardware)
        db.session.commit()

        lo_ict = LearningOutcome(
            topic_id=comp_systems.id,
            name='Memory Units',
            description='Understand the function and types of primary memory.',
            order=1,
            notes='RAM is volatile, ROM is non-volatile.'
        )
        db.session.add(lo_ict)
        db.session.commit()

        pi_ict = PerformanceIndicator(
            sub_strand_id=hardware.id,
            learning_outcome_id=lo_ict.id,
            description='Compare RAM and ROM in terms of volatility and usage.',
            order=1
        )
        db.session.add(pi_ict)
        db.session.commit()

        q_ict = Question(
            learning_outcome_id=lo_ict.id,
            text='Which of the following is true about RAM?',
            type='mcq',
            options=json.dumps(['It is permanent storage', 'It is volatile', 'It is slower than a hard drive', 'It is non-volatile']),
            correct_answer='It is volatile'
        )
        db.session.add(q_ict)

        db.session.commit()
        print("Data seeded with ICT successfully.")

if __name__ == "__main__":
    seed()
