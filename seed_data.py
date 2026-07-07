"""
seed_data.py — Populate Learn2Master with curriculum and demo users.

Supabase/PostgreSQL edition:
- ? placeholders → %s
- INSERT OR IGNORE → INSERT ... ON CONFLICT DO NOTHING
- INSERT INTO ... SELECT ... WHERE NOT EXISTS → INSERT ... ON CONFLICT DO NOTHING
- conn.execute() → cursor pattern with explicit commit

Usage:  python seed_data.py
"""
import os
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL is not set in .env")

conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
conn.autocommit = False
cur = conn.cursor()


def get_id(sql, params=()):
    cur.execute(sql, params)
    row = cur.fetchone()
    return list(row.values())[0] if row else None


# ── Roles, school, class, users ──────────────────────────────────────────────
student_role = get_id("SELECT role_id FROM roles WHERE role_name='student'")
teacher_role = get_id("SELECT role_id FROM roles WHERE role_name='teacher'")
admin_role   = get_id("SELECT role_id FROM roles WHERE role_name='admin'")
school_id    = get_id("SELECT school_id FROM schools WHERE school_name='Kigezi High School'")

cur.execute(
    "INSERT INTO classes (class_name, school_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
    ("Senior One", school_id)
)
class_id = get_id("SELECT class_id FROM classes WHERE class_name='Senior One'")

users = [
    ("Tukamushaba Elijah", "elijah",  "elijah@example.com",  "12345", student_role, school_id),
    ("ICT Physics Teacher","teacher", "teacher@example.com", "12345", teacher_role, school_id),
    ("System Administrator","admin",  "admin@example.com",   "12345", admin_role,   school_id),
]
for full_name, username, email, password, role_id, sid in users:
    cur.execute("""
        INSERT INTO users (full_name, username, email, password_hash, role_id, school_id)
        VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (username) DO NOTHING
    """, (full_name, username, email, generate_password_hash(password), role_id, sid))

conn.commit()

learner_id = get_id("SELECT user_id FROM users WHERE username='elijah'")
cur.execute(
    "INSERT INTO enrollments (learner_id, class_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
    (learner_id, class_id)
)
cur.execute("""
    INSERT INTO learner_profiles
        (learner_id, class_level, learning_style, learning_pace, preferred_support, ai_profile_summary)
    VALUES (%s, 'Senior One', 'Adaptive / Mixed', 'Not yet classified',
            'Notes, video, worked examples and guided practice',
            'Initial learner profile. The AI profile updates after pre-test, practice, reflection and post-test evidence.')
    ON CONFLICT (learner_id) DO NOTHING
""", (learner_id,))

conn.commit()

# ── Subjects & competencies ──────────────────────────────────────────────────
ict_subject     = get_id("SELECT subject_id FROM subjects WHERE subject_name='ICT'")
physics_subject = get_id("SELECT subject_id FROM subjects WHERE subject_name='Physics'")

competencies = [
    (ict_subject,     "ICT-S1-T1", "Introduction to ICT",
     "Senior One Term One: Computer Systems. Learners understand ICT, common ICT tools, computer applications, safety, and responsible use."),
    (physics_subject, "PHY-S1-T1", "Measurements in Physics",
     "Senior One Term One: Mechanics and Properties of Matter. Learners apply SI units, measuring instruments, accuracy, and recording of measurements."),
]
for subject_id, code, name, desc in competencies:
    cur.execute("""
        INSERT INTO competencies (subject_id, competency_code, competency_name, competency_description)
        VALUES (%s, %s, %s, %s) ON CONFLICT (subject_id, competency_code) DO NOTHING
    """, (subject_id, code, name, desc))

conn.commit()

ict_comp = get_id("SELECT competency_id FROM competencies WHERE competency_code='ICT-S1-T1'")
phy_comp = get_id("SELECT competency_id FROM competencies WHERE competency_code='PHY-S1-T1'")

# ── Courses ──────────────────────────────────────────────────────────────────
courses = [
    (ict_subject,     "Introduction to ICT",
     "Senior One Term One topic from the NCDC ICT syllabus. Focus: ICT meaning, tools, applications, information processing, laboratory safety, and responsible use.",
     "Senior One"),
    (physics_subject, "Measurements in Physics",
     "Senior One Term One topic from the NCDC Physics syllabus. Focus: physical quantities, SI units, measuring instruments, accuracy, and practical recording of measurements.",
     "Senior One"),
]
for subject_id, title, desc, level in courses:
    cur.execute("""
        INSERT INTO courses (subject_id, course_title, course_description, difficulty_level)
        SELECT %s, %s, %s, %s
        WHERE NOT EXISTS (SELECT 1 FROM courses WHERE subject_id=%s AND course_title=%s)
    """, (subject_id, title, desc, level, subject_id, title))

conn.commit()

ict_course = get_id("SELECT course_id FROM courses WHERE course_title='Introduction to ICT'")
phy_course = get_id("SELECT course_id FROM courses WHERE course_title='Measurements in Physics'")

# ── Learning outcomes ────────────────────────────────────────────────────────
outcomes = [
    (ict_comp, "ICT-LO1", "Explain ICT and related terminologies",
     "Explain ICT, data, information, communication, computer, hardware, software, and information processing cycle.", 80, 1),
    (ict_comp, "ICT-LO2", "Identify ICT tools, uses, and safety precautions",
     "Identify common ICT tools, explain their uses in society, and apply safety precautions in the computer laboratory.", 80, 2),
    (phy_comp, "PHY-LO1", "Use SI units and physical quantities",
     "Identify physical quantities, SI units, symbols, and appropriate units used in measurement.", 80, 1),
    (phy_comp, "PHY-LO2", "Use measuring instruments accurately",
     "Select and use measuring instruments, read scales correctly, and record measurements accurately.", 80, 2),
]
for item in outcomes:
    cur.execute("""
        INSERT INTO learning_outcomes
            (competency_id, outcome_code, outcome_name, outcome_description, mastery_threshold, sequence_order)
        VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (competency_id, outcome_code) DO NOTHING
    """, item)

conn.commit()

# ── Lessons ──────────────────────────────────────────────────────────────────
lessons = [
    (ict_course, "ICT-LO1", "Meaning of ICT and Information Processing",
     "ICT means Information and Communication Technology. It involves using digital tools to create, process, store, communicate, and share information. Data are raw facts, while information is processed data that is meaningful. The information processing cycle involves input, processing, storage, output, and communication.", 20),
    (ict_course, "ICT-LO2", "ICT Tools, Applications, and Safety",
     "ICT tools include computers, smartphones, cameras, printers, projectors, scanners, and storage devices. ICT is used in education, health, banking, business, agriculture, communication, and transport. Safe use includes proper sitting posture, avoiding liquids near computers, protecting passwords, and following laboratory rules.", 25),
    (phy_course, "PHY-LO1", "Physical Quantities and SI Units",
     "Measurement in Physics begins with physical quantities such as length, mass, time, temperature, area, volume, and density. Standard SI units help scientists communicate measurements accurately. Examples include metre for length, kilogram for mass, second for time, and kelvin or degree Celsius for temperature in school experiments.", 30),
    (phy_course, "PHY-LO2", "Measuring Instruments and Accuracy",
     "Choosing the correct measuring instrument improves accuracy. A metre rule measures length, a stopwatch measures time, a measuring cylinder measures liquid volume, a thermometer measures temperature, and a beam balance measures mass. Good measurement requires correct units, careful reading of scales, and repeated readings where possible.", 35),
]
for course_id, outcome_code, title, content, minutes in lessons:
    outcome_id = get_id("SELECT outcome_id FROM learning_outcomes WHERE outcome_code=%s", (outcome_code,))
    cur.execute("""
        INSERT INTO lessons (course_id, outcome_id, lesson_title, lesson_content, video_url, estimated_minutes, sequence_order)
        SELECT %s, %s, %s, %s, '', %s, 1
        WHERE NOT EXISTS (SELECT 1 FROM lessons WHERE outcome_id=%s AND lesson_title=%s)
    """, (course_id, outcome_id, title, content, minutes, outcome_id, title))

conn.commit()

# ── Learning activities ──────────────────────────────────────────────────────
activities = {
    "ICT-LO1": [
        ("Concept sorting",     "Classify examples as data, information, hardware, software, input, process, storage, output, or communication.", "Practice"),
        ("Real-life ICT mapping","List five ICT tools used at school and explain what information task each one performs.", "Reflection"),
    ],
    "ICT-LO2": [
        ("ICT tools walk-through","Identify ICT tools in a computer laboratory and state one correct use for each.", "Practical"),
        ("Safety checklist",    "Create a checklist of computer laboratory safety rules and explain why each rule matters.", "Reflection"),
    ],
    "PHY-LO1": [
        ("Unit matching",       "Match physical quantities to their SI units and symbols.", "Practice"),
        ("Measurement diary",   "Record five measurements around the classroom and write the correct units.", "Practical"),
    ],
    "PHY-LO2": [
        ("Instrument selection","Choose the best instrument for measuring length, mass, volume, time, and temperature.", "Practice"),
        ("Scale reading practical","Read sample scales and record values with correct units.", "Practical"),
    ],
}
for outcome_code, rows in activities.items():
    outcome_id = get_id("SELECT outcome_id FROM learning_outcomes WHERE outcome_code=%s", (outcome_code,))
    for title, desc, typ in rows:
        cur.execute("""
            INSERT INTO learning_activities (outcome_id, activity_title, activity_description, activity_type)
            SELECT %s, %s, %s, %s
            WHERE NOT EXISTS (SELECT 1 FROM learning_activities WHERE outcome_id=%s AND activity_title=%s)
        """, (outcome_id, title, desc, typ, outcome_id, title))

conn.commit()

# ── Adaptive notes & videos ──────────────────────────────────────────────────
notes = {
    "ICT-LO1": [
        ("ict_meaning",     "What ICT Means",              "ICT combines information handling and communication using technology. Think of ICT as tools and methods used to collect, process, store, and share information."),
        ("data_information","Data vs Information",          "Data are raw facts such as 12, Elijah, or 35°C. Information is data that has been processed and given meaning, such as 'Elijah scored 12 out of 15'."),
        ("processing_cycle","Information Processing Cycle", "The cycle moves from input to processing, storage, output, and communication. A keyboard enters data, the CPU processes it, storage keeps it, and a screen or printer outputs it."),
    ],
    "ICT-LO2": [
        ("ict_tools", "Common ICT Tools",   "Computers, printers, cameras, projectors, scanners, phones, routers, and storage devices are ICT tools used to create, process, store, and communicate information."),
        ("ict_uses",  "Applications of ICT","ICT is used in education for learning platforms, in health for patient records, in banking for ATMs and mobile money, and in agriculture for weather and market information."),
        ("ict_safety","ICT Safety",         "Avoid liquids near computers, use good posture, keep passwords private, report faulty cables, and take breaks to reduce eye strain."),
    ],
    "PHY-LO1": [
        ("physical_quantities","Physical Quantities",   "A physical quantity is something that can be measured, such as length, mass, time, temperature, area, volume, or density."),
        ("si_units",           "SI Units",              "SI units are standard units used in science. Examples include metre (m), kilogram (kg), second (s), ampere (A), and kelvin (K)."),
        ("unit_symbols",       "Writing Units Correctly","Use the correct unit symbol and do not pluralize symbols. Write 5 m, not 5 metres when using symbols; write 10 kg, not 10 kgs."),
    ],
    "PHY-LO2": [
        ("instruments",  "Choosing Measuring Instruments","Use a metre rule for length, stopwatch for time, thermometer for temperature, measuring cylinder for liquid volume, and beam balance for mass."),
        ("scale_reading","Reading Scales",               "Read a scale at eye level to avoid parallax error. Identify the smallest division before recording the measurement."),
        ("accuracy",     "Accuracy and Recording",       "Accurate measurements use suitable instruments, correct units, repeated readings, and careful recording to the appropriate precision."),
    ],
}
videos = {
    "ict_meaning":        ("What is ICT?",               "https://www.youtube.com/results?search_query=what+is+ICT+for+students",                  "Introductory video on ICT meaning."),
    "data_information":   ("Data and Information",        "https://www.youtube.com/results?search_query=data+versus+information+ICT",               "Video support for data and information."),
    "processing_cycle":   ("Information Processing Cycle","https://www.youtube.com/results?search_query=information+processing+cycle+ICT",          "Video support for input, process, storage, output."),
    "ict_tools":          ("ICT Tools",                   "https://www.youtube.com/results?search_query=common+ICT+tools+for+students",             "Video support for identifying ICT tools."),
    "ict_uses":           ("Uses of ICT",                 "https://www.youtube.com/results?search_query=uses+of+ICT+in+society",                    "Video support for ICT applications."),
    "ict_safety":         ("Computer Lab Safety",         "https://www.youtube.com/results?search_query=computer+lab+safety+rules+for+students",    "Video support for safety."),
    "physical_quantities":("Physical Quantities",         "https://www.youtube.com/results?search_query=physical+quantities+and+units+physics",     "Video support for physical quantities."),
    "si_units":           ("SI Units",                    "https://www.youtube.com/results?search_query=SI+units+physics+for+students",             "Video support for SI units."),
    "unit_symbols":       ("Unit Symbols",                "https://www.youtube.com/results?search_query=physics+unit+symbols+SI+units",             "Video support for unit symbols."),
    "instruments":        ("Measuring Instruments",       "https://www.youtube.com/results?search_query=measuring+instruments+in+physics",          "Video support for instruments."),
    "scale_reading":      ("Reading Measuring Scales",    "https://www.youtube.com/results?search_query=how+to+read+measuring+scales+physics",     "Video support for reading scales."),
    "accuracy":           ("Accuracy in Measurement",     "https://www.youtube.com/results?search_query=accuracy+and+precision+in+measurement+physics","Video support for accuracy."),
}
for outcome_code, rows in notes.items():
    outcome_id = get_id("SELECT outcome_id FROM learning_outcomes WHERE outcome_code=%s", (outcome_code,))
    for concept, title, body in rows:
        cur.execute("""
            INSERT INTO adaptive_notes (outcome_id, concept_tag, note_title, note_body)
            SELECT %s, %s, %s, %s
            WHERE NOT EXISTS (SELECT 1 FROM adaptive_notes WHERE outcome_id=%s AND concept_tag=%s AND note_title=%s)
        """, (outcome_id, concept, title, body, outcome_id, concept, title))
        vtitle, vurl, vdesc = videos[concept]
        cur.execute("""
            INSERT INTO adaptive_videos (outcome_id, concept_tag, video_title, video_url, video_description)
            SELECT %s, %s, %s, %s, %s
            WHERE NOT EXISTS (SELECT 1 FROM adaptive_videos WHERE outcome_id=%s AND concept_tag=%s AND video_title=%s)
        """, (outcome_id, concept, vtitle, vurl, vdesc, outcome_id, concept, vtitle))

conn.commit()
print("Adaptive notes and videos seeded.")

# ── Assessments & questions ──────────────────────────────────────────────────
assessments_data = {
    "ICT-LO1": {
        "pretest": [
            ("What does ICT stand for?",                                           "ict_meaning",    [("Information and Communication Technology",1),("Internet Computer Training",0),("Internal Control Technology",0)]),
            ("Which statement best describes data?",                               "data_information",[("Raw facts before processing",1),("Only printed reports",0),("A computer monitor",0)]),
            ("Which stage comes after input in the information processing cycle?", "processing_cycle",[("Processing",1),("Sweeping",0),("Painting",0)]),
        ],
        "practice": [
            ("A learner types marks into a spreadsheet. This is mainly which stage?","processing_cycle",[("Input",1),("Output",0),("Communication",0)]),
            ("The final class average displayed after calculations is best called?", "data_information", [("Information",1),("Raw data",0),("Hardware",0)]),
            ("ICT helps people mainly by",                                          "ict_meaning",      [("processing and communicating information",1),("removing all teachers",0),("making books unnecessary",0)]),
        ],
        "posttest": [
            ("Which example shows ICT communication?",           "ict_meaning",    [("Sending an email",1),("Lifting a chair",0),("Sharpening a pencil",0)]),
            ("Processed data that has meaning is called",         "data_information",[("Information",1),("Noise",0),("Keyboard",0)]),
            ("A printer mainly performs which stage?",            "processing_cycle",[("Output",1),("Input",0),("Processing",0)]),
        ],
    },
    "ICT-LO2": {
        "pretest": [
            ("Which of these is an ICT tool?",                  "ict_tools", [("Projector",1),("Broom",0),("Chalk duster",0)]),
            ("Which field uses ICT for patient records?",        "ict_uses",  [("Health",1),("Only football",0),("Only sweeping",0)]),
            ("Why should learners avoid drinks near computers?", "ict_safety",[("To prevent damage and electrical risks",1),("To increase screen brightness",0),("To make typing faster",0)]),
        ],
        "practice": [
            ("Which device captures photos and videos?",         "ict_tools", [("Camera",1),("Stapler",0),("Basin",0)]),
            ("Mobile money is an example of ICT use in",         "ict_uses",  [("Banking and finance",1),("Only gardening",0),("Only football",0)]),
            ("A safe password should be",                        "ict_safety",[("kept private",1),("shared with everyone",0),("written on the monitor",0)]),
        ],
        "posttest": [
            ("Which device displays information to many learners?","ict_tools",[("Projector",1),("Hoe",0),("Cup",0)]),
            ("ICT can support agriculture by providing",          "ict_uses",  [("weather and market information",1),("only chalk",0),("only chairs",0)]),
            ("Good posture when using computers helps to",        "ict_safety",[("reduce body strain",1),("destroy the chair",0),("hide information",0)]),
        ],
    },
    "PHY-LO1": {
        "pretest": [
            ("What is a physical quantity?",                  "physical_quantities",[("Something that can be measured",1),("A story only",0),("A colour only",0)]),
            ("What is the SI unit of length?",                "si_units",           [("metre",1),("kilogram",0),("second",0)]),
            ("Which is the correct symbol for metre?",        "unit_symbols",       [("m",1),("kg",0),("s",0)]),
        ],
        "practice": [
            ("Mass is an example of",                         "physical_quantities",[("physical quantity",1),("software",0),("a network",0)]),
            ("The SI unit of time is",                        "si_units",           [("second",1),("metre",0),("kilogram",0)]),
            ("The correct symbol for kilogram is",            "unit_symbols",       [("kg",1),("kgs",0),("km",0)]),
        ],
        "posttest": [
            ("Length, mass and time are examples of",         "physical_quantities",[("physical quantities",1),("computer programs",0),("laboratory rules",0)]),
            ("Which unit is used for mass?",                  "si_units",           [("kilogram",1),("second",0),("metre",0)]),
            ("Which expression is written correctly?",        "unit_symbols",       [("5 m",1),("5 ms for length",0),("5 kgs",0)]),
        ],
    },
    "PHY-LO2": {
        "pretest": [
            ("Which instrument measures temperature?",        "instruments",   [("Thermometer",1),("Beam balance",0),("Measuring cylinder",0)]),
            ("Why should the eye be level with the scale?",   "scale_reading", [("To avoid parallax error",1),("To decorate the instrument",0),("To increase mass",0)]),
            ("Why are repeated readings useful?",             "accuracy",      [("They improve reliability",1),("They remove units",0),("They make instruments heavier",0)]),
        ],
        "practice": [
            ("Which instrument measures liquid volume?",      "instruments",   [("Measuring cylinder",1),("Stopwatch",0),("Metre rule",0)]),
            ("Before reading a scale, first identify",        "scale_reading", [("the smallest division",1),("the colour of the table",0),("the brand name only",0)]),
            ("A suitable instrument helps improve",           "accuracy",      [("accuracy",1),("carelessness",0),("noise",0)]),
        ],
        "posttest": [
            ("Which instrument measures mass?",               "instruments",   [("Beam balance",1),("Thermometer",0),("Stopwatch",0)]),
            ("Parallax error is reduced by",                  "scale_reading", [("reading at eye level",1),("closing both eyes",0),("changing units randomly",0)]),
            ("Accurate recording should include",             "accuracy",      [("value and correct unit",1),("only a number",0),("only a drawing",0)]),
        ],
    },
}
for outcome_code, by_type in assessments_data.items():
    outcome_id = get_id("SELECT outcome_id FROM learning_outcomes WHERE outcome_code=%s", (outcome_code,))
    lesson_id  = get_id("SELECT lesson_id FROM lessons WHERE outcome_id=%s", (outcome_id,))
    for assessment_type, qs in by_type.items():
        title = f"{outcome_code} {assessment_type.title()}"
        cur.execute("""
            INSERT INTO assessments (lesson_id, assessment_title, assessment_type, total_marks)
            SELECT %s, %s, %s, %s
            WHERE NOT EXISTS (SELECT 1 FROM assessments WHERE lesson_id=%s AND assessment_type=%s)
        """, (lesson_id, title, assessment_type, len(qs), lesson_id, assessment_type))
        assessment_id = get_id("SELECT assessment_id FROM assessments WHERE lesson_id=%s AND assessment_type=%s", (lesson_id, assessment_type))
        for question_text, concept, options in qs:
            cur.execute("""
                INSERT INTO questions (assessment_id, question_text, concept_tag, marks)
                SELECT %s, %s, %s, 1
                WHERE NOT EXISTS (SELECT 1 FROM questions WHERE assessment_id=%s AND question_text=%s)
            """, (assessment_id, question_text, concept, assessment_id, question_text))
            qid = get_id("SELECT question_id FROM questions WHERE assessment_id=%s AND question_text=%s", (assessment_id, question_text))
            for option_text, is_correct in options:
                cur.execute("""
                    INSERT INTO question_options (question_id, option_text, is_correct)
                    SELECT %s, %s, %s
                    WHERE NOT EXISTS (SELECT 1 FROM question_options WHERE question_id=%s AND option_text=%s)
                """, (qid, option_text, bool(is_correct), qid, option_text))

conn.commit()
print("Assessment questions seeded.")

# ── Worked examples ──────────────────────────────────────────────────────────
worked_examples = {
    "ICT-LO1": [
        ("ict_meaning",     "ICT in a school office",       "A bursar enters fees payments into a computer and sends receipts by email.",                              "Step 1: Identify the information task. Step 2: Identify the technology used. Step 3: Explain that computers and email support information processing and communication."),
        ("data_information","From raw marks to class average","Marks 45, 60 and 75 are data. After calculating an average of 60, the result becomes information.",   "Data are raw facts. Processing gives meaning. The average helps a teacher make a decision."),
        ("processing_cycle","Typing and printing a report", "A learner types text using a keyboard, the computer processes it, saves it, then prints it.",            "Keyboard=input, CPU=processing, disk=storage, printer=output."),
    ],
    "ICT-LO2": [
        ("ict_tools", "Choosing tools for a presentation","A projector, laptop and flash disk can be used to present group work.",                                    "Choose tool according to task: laptop prepares, flash disk stores, projector displays."),
        ("ict_uses",  "ICT in health",                   "A hospital uses computers to store patient records and send appointment messages.",                         "Identify sector, information handled, and benefit."),
        ("ict_safety","Preventing lab accidents",         "A learner finds a loose cable and reports it instead of touching it.",                                     "Recognize risk, avoid contact, report to teacher/lab attendant."),
    ],
    "PHY-LO1": [
        ("physical_quantities","Identifying measurable properties","A desk has length, mass and volume. These are measurable, so they are physical quantities.",      "Ask: Can it be measured? If yes, identify suitable unit."),
        ("si_units",           "Selecting SI units",              "A learner records length in metres and time in seconds during an experiment.",                     "Identify quantity first, then select the correct SI unit."),
        ("unit_symbols",       "Writing units correctly",         "The correct way to record a length is 5 m, not 5 metres when using symbols.",                     "Use standard symbols and avoid pluralizing symbols."),
    ],
    "PHY-LO2": [
        ("instruments",  "Selecting the best instrument","To measure liquid volume, use a measuring cylinder, not a metre rule.",                                     "Identify what is being measured, then select the instrument designed for that quantity."),
        ("scale_reading","Avoiding parallax error",      "When reading a measuring cylinder, place the eye level with the meniscus.",                                 "Eye level reduces parallax and improves reading accuracy."),
        ("accuracy",     "Improving reliability",        "Repeating a time measurement three times and averaging can reduce random error.",                           "Repeat readings, compare values, and record final value with correct unit."),
    ],
}
for outcome_code, rows in worked_examples.items():
    outcome_id = get_id("SELECT outcome_id FROM learning_outcomes WHERE outcome_code=%s", (outcome_code,))
    for concept, title, body, steps in rows:
        cur.execute("""
            INSERT INTO worked_examples (outcome_id, concept_tag, example_title, example_body, step_by_step_solution)
            SELECT %s, %s, %s, %s, %s
            WHERE NOT EXISTS (SELECT 1 FROM worked_examples WHERE outcome_id=%s AND concept_tag=%s AND example_title=%s)
        """, (outcome_id, concept, title, body, steps, outcome_id, concept, title))

conn.commit()
print("Worked examples seeded.")

# ── Extra adaptive practice questions ───────────────────────────────────────
# These concept-targeted questions let the engine serve weak-concept-specific
# practice immediately after the pretest identifies gaps.
extra_practice = {
    "ICT-LO1": {
        "ict_meaning": [
            ("Which activity is an example of ICT use?",
             [("Sending a typed report by email", 1), ("Carrying a desk", 0), ("Sweeping a compound", 0)]),
            ("ICT mainly deals with",
             [("information and communication using technology", 1), ("only physical exercise", 0), ("only chalk writing", 0)]),
        ],
        "data_information": [
            ("A list of unprocessed temperature readings is",
             [("data", 1), ("a monitor", 0), ("a printer", 0)]),
            ("A report showing the hottest day from readings is",
             [("information", 1), ("raw data", 0), ("hardware", 0)]),
        ],
        "processing_cycle": [
            ("Saving a document on a flash disk is mainly",
             [("storage", 1), ("input", 0), ("sweeping", 0)]),
            ("A monitor showing results represents",
             [("output", 1), ("storage only", 0), ("raw facts only", 0)]),
        ],
    },
    "ICT-LO2": {
        "ict_tools": [
            ("Which ICT tool scans paper documents into digital form?",
             [("Scanner", 1), ("Cup", 0), ("Desk", 0)]),
            ("Which device stores digital files?",
             [("Flash disk", 1), ("Broom", 0), ("Chalk", 0)]),
        ],
        "ict_uses": [
            ("ICT in education can support",
             [("online learning and research", 1), ("only carrying water", 0), ("only sweeping", 0)]),
            ("ICT in transport can support",
             [("ticket booking and tracking", 1), ("cooking food only", 0), ("washing clothes only", 0)]),
        ],
        "ict_safety": [
            ("Reporting a damaged cable is important because it",
             [("reduces electrical risk", 1), ("makes typing slower", 0), ("increases dust", 0)]),
            ("Taking breaks when using computers helps reduce",
             [("eye strain and fatigue", 1), ("storage space", 0), ("keyboard letters", 0)]),
        ],
    },
    "PHY-LO1": {
        "physical_quantities": [
            ("Which of these can be measured?",
             [("Time", 1), ("Happiness only", 0), ("Beauty only", 0)]),
            ("Volume is a physical quantity because it",
             [("can be measured", 1), ("is only a story", 0), ("has no unit", 0)]),
        ],
        "si_units": [
            ("Which is the SI unit of mass?",
             [("kilogram", 1), ("metre", 0), ("second", 0)]),
            ("Which is the SI unit of time?",
             [("second", 1), ("kilogram", 0), ("metre", 0)]),
        ],
        "unit_symbols": [
            ("Which is the correct symbol for second?",
             [("s", 1), ("sec(s)", 0), ("kg", 0)]),
            ("Which unit symbol is correctly written?",
             [("10 kg", 1), ("10 kgs", 0), ("10 Kilogrammes", 0)]),
        ],
    },
    "PHY-LO2": {
        "instruments": [
            ("Which instrument measures time in an experiment?",
             [("Stopwatch", 1), ("Thermometer", 0), ("Measuring cylinder", 0)]),
            ("Which instrument measures length?",
             [("Metre rule", 1), ("Beam balance", 0), ("Clock only", 0)]),
        ],
        "scale_reading": [
            ("The smallest division on a scale helps determine",
             [("precision of reading", 1), ("colour of the instrument", 0), ("mass of the learner", 0)]),
            ("Parallax error occurs when",
             [("the eye is not level with the scale", 1), ("the unit is written", 0), ("readings are repeated", 0)]),
        ],
        "accuracy": [
            ("Repeating readings helps to",
             [("improve reliability", 1), ("remove all units", 0), ("make values random", 0)]),
            ("A good measurement record should include",
             [("value and unit", 1), ("only the learner name", 0), ("only the date", 0)]),
        ],
    },
}

for outcome_code, concept_groups in extra_practice.items():
    outcome_id = get_id("SELECT outcome_id FROM learning_outcomes WHERE outcome_code=%s", (outcome_code,))
    lesson_id  = get_id("SELECT lesson_id FROM lessons WHERE outcome_id=%s", (outcome_id,))
    assessment_id = get_id(
        "SELECT assessment_id FROM assessments WHERE lesson_id=%s AND assessment_type='practice'",
        (lesson_id,)
    )
    for concept, rows in concept_groups.items():
        for question_text, options in rows:
            cur.execute("""
                INSERT INTO questions (assessment_id, question_text, concept_tag, marks)
                SELECT %s, %s, %s, 1
                WHERE NOT EXISTS (SELECT 1 FROM questions WHERE assessment_id=%s AND question_text=%s)
            """, (assessment_id, question_text, concept, assessment_id, question_text))
            qid = get_id(
                "SELECT question_id FROM questions WHERE assessment_id=%s AND question_text=%s",
                (assessment_id, question_text)
            )
            for option_text, is_correct in options:
                cur.execute("""
                    INSERT INTO question_options (question_id, option_text, is_correct)
                    SELECT %s, %s, %s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM question_options WHERE question_id=%s AND option_text=%s
                    )
                """, (qid, option_text, bool(is_correct), qid, option_text))

conn.commit()
print("Extra adaptive practice questions seeded.")
print("\nAll seed data complete. Ready for Supabase deployment.")
print("Demo: elijah/12345 (student)  teacher/12345  admin/12345")

cur.close()
conn.close()
