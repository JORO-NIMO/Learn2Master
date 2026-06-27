import os
import json

filepath = 'seed_data.py'
with open(filepath, 'r') as f:
    content = f.read()

if "from models import db, User, Subject, Topic, LearningOutcome, LearningResource" in content:
    content = content.replace(
        "from models import db, User, Subject, Topic, LearningOutcome, LearningResource",
        "from models import db, User, Subject, Topic, LearningOutcome, LearningResource, Question"
    )

search_text = """        db.session.add_all([res1, res2])

        db.session.commit()
        print("Data seeded successfully.")"""

replace_text = """        db.session.add_all([res1, res2])
        db.session.commit()

        # Seed Questions for LO1
        q1 = Question(
            learning_outcome_id=lo1.id,
            text='A student walks 3km North and then 4km East. What is their total distance?',
            type='mcq',
            options=json.dumps(['7km', '5km', '1km', '12km']),
            correct_answer='7km'
        )
        q2 = Question(
            learning_outcome_id=lo1.id,
            text='In the previous scenario (3km North, 4km East), what is the magnitude of their displacement?',
            type='mcq',
            options=json.dumps(['7km', '5km', '1km', '0km']),
            correct_answer='5km'
        )
        db.session.add_all([q1, q2])

        db.session.commit()
        print("Data seeded successfully.")"""

if search_text in content:
    new_content = content.replace(search_text, replace_text)
    with open(filepath, 'w') as f:
        f.write(new_content)
    print("seed_data.py updated with questions.")
else:
    print("Search text not found.")
