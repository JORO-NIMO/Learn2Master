import json

filepath = 'seed_data.py'
with open(filepath, 'r') as f:
    content = f.read()

search_text = """        db.session.add_all([q1, q2])

        db.session.commit()
        print("Data seeded successfully.")"""

replace_text = """        db.session.add_all([q1, q2])
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
        print("Data seeded with ICT successfully.")"""

if search_text in content:
    new_content = content.replace(search_text, replace_text)
    with open(filepath, 'w') as f:
        f.write(new_content)
    print("seed_data.py updated for ICT.")
else:
    print("Search text not found.")
