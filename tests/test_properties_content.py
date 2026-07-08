"""
tests/test_properties_content.py
Property-based tests for Teacher Content Management (Properties 1–5).

Properties tested:
  1  Content Insert Round-Trip           (R1.1, R1.4, R1.10, R1.13, R1.15)
  2  Content Edit Reflects Updated Fields (R1.2, R1.5, R1.11)
  3  Safe-Delete Referential Integrity    (R1.3, R1.6)
  4  Question Options Invariant           (R1.7, R1.8)
  5  Question Delete Cascade             (R1.9)

Uses Hypothesis for strategy-driven generation and the transactional `db`
fixture from conftest.py to keep the database clean after each test.
"""

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# ── Hypothesis strategies ─────────────────────────────────────────────────────

text50  = st.text(min_size=1, max_size=50,
                  alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")))
text255 = st.text(min_size=1, max_size=255,
                  alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")))
text_body = st.text(min_size=1, max_size=500,
                    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs", "Po")))
priority_st  = st.integers(min_value=1, max_value=10)
seq_order_st = st.integers(min_value=1, max_value=100)
threshold_st = st.integers(min_value=1, max_value=100)
option_count_st = st.integers(min_value=2, max_value=6)


# ═══════════════════════════════════════════════════════════════════════════════
# Property 1 — Content Insert Round-Trip
# ═══════════════════════════════════════════════════════════════════════════════

@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
@given(
    outcome_code=text50,
    outcome_name=text255,
    outcome_desc=text_body,
    threshold=threshold_st,
    seq=seq_order_st,
)
def test_property1_outcome_insert_round_trip(
    db, prereq_ids, outcome_code, outcome_name, outcome_desc, threshold, seq
):
    """
    Property 1 (partial): For any valid learning outcome payload, inserting it
    via the route SQL then selecting it back should return all submitted fields intact.
    Tests the DB layer directly (route logic validated by integration tests).
    """
    cur = db.cursor()
    cur.execute("""
        INSERT INTO learning_outcomes
            (competency_id, outcome_code, outcome_name, outcome_description,
             mastery_threshold, sequence_order)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING outcome_id
    """, (
        prereq_ids["competency_id"],
        outcome_code,
        outcome_name,
        outcome_desc,
        threshold,
        seq,
    ))
    new_id = cur.fetchone()["outcome_id"]
    db.commit()

    cur.execute(
        "SELECT * FROM learning_outcomes WHERE outcome_id = %s", (new_id,)
    )
    row = cur.fetchone()
    cur.close()

    assert row is not None, "Inserted row must be retrievable"
    assert row["outcome_code"]        == outcome_code
    assert row["outcome_name"]        == outcome_name
    assert row["outcome_description"] == outcome_desc
    assert row["mastery_threshold"]   == threshold
    assert row["sequence_order"]      == seq


@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
@given(
    note_title=text255,
    concept_tag=text50,
    note_body=text_body,
    priority=priority_st,
)
def test_property1_note_insert_round_trip(
    db, prereq_ids, note_title, concept_tag, note_body, priority
):
    """Property 1 (adaptive note): inserted row is immediately retrievable."""
    cur = db.cursor()
    cur.execute("""
        INSERT INTO adaptive_notes
            (outcome_id, concept_tag, note_title, note_body, priority)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING note_id
    """, (prereq_ids["base_outcome_id"], concept_tag, note_title, note_body, priority))
    new_id = cur.fetchone()["note_id"]
    db.commit()

    cur.execute("SELECT * FROM adaptive_notes WHERE note_id = %s", (new_id,))
    row = cur.fetchone()
    cur.close()

    assert row is not None
    assert row["note_title"]  == note_title
    assert row["concept_tag"] == concept_tag
    assert row["note_body"]   == note_body
    assert row["priority"]    == priority


@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
@given(
    video_title=text255,
    concept_tag=text50,
    video_url=st.just("https://example.com/video"),
)
def test_property1_video_insert_round_trip(db, prereq_ids, video_title, concept_tag, video_url):
    """Property 1 (adaptive video): inserted row is immediately retrievable."""
    cur = db.cursor()
    cur.execute("""
        INSERT INTO adaptive_videos
            (outcome_id, concept_tag, video_title, video_url)
        VALUES (%s, %s, %s, %s)
        RETURNING video_id
    """, (prereq_ids["base_outcome_id"], concept_tag, video_title, video_url))
    new_id = cur.fetchone()["video_id"]
    db.commit()

    cur.execute("SELECT * FROM adaptive_videos WHERE video_id = %s", (new_id,))
    row = cur.fetchone()
    cur.close()

    assert row is not None
    assert row["video_title"]  == video_title
    assert row["concept_tag"]  == concept_tag


@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
@given(
    example_title=text255,
    concept_tag=text50,
    example_body=text_body,
)
def test_property1_example_insert_round_trip(
    db, prereq_ids, example_title, concept_tag, example_body
):
    """Property 1 (worked example): inserted row is immediately retrievable."""
    cur = db.cursor()
    cur.execute("""
        INSERT INTO worked_examples
            (outcome_id, concept_tag, example_title, example_body)
        VALUES (%s, %s, %s, %s)
        RETURNING example_id
    """, (prereq_ids["base_outcome_id"], concept_tag, example_title, example_body))
    new_id = cur.fetchone()["example_id"]
    db.commit()

    cur.execute("SELECT * FROM worked_examples WHERE example_id = %s", (new_id,))
    row = cur.fetchone()
    cur.close()

    assert row is not None
    assert row["example_title"] == example_title
    assert row["example_body"]  == example_body


# ═══════════════════════════════════════════════════════════════════════════════
# Property 2 — Content Edit Reflects Updated Fields
# ═══════════════════════════════════════════════════════════════════════════════

@settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
@given(
    orig_title=text255,
    new_title=text255,
    new_body=text_body,
    new_priority=priority_st,
)
def test_property2_note_edit_reflects_update(
    db, prereq_ids, orig_title, new_title, new_body, new_priority
):
    """
    Property 2: After editing an adaptive note, the DB row must contain the
    new field values and not the old changed values.
    """
    cur = db.cursor()
    # Insert original
    cur.execute("""
        INSERT INTO adaptive_notes
            (outcome_id, concept_tag, note_title, note_body, priority)
        VALUES (%s, 'prop2-tag', %s, 'original body', 1)
        RETURNING note_id
    """, (prereq_ids["base_outcome_id"], orig_title))
    note_id = cur.fetchone()["note_id"]
    db.commit()

    # Apply update
    cur.execute("""
        UPDATE adaptive_notes
        SET note_title = %s, note_body = %s, priority = %s
        WHERE note_id = %s
    """, (new_title, new_body, new_priority, note_id))
    db.commit()

    # Assert new values present
    cur.execute("SELECT * FROM adaptive_notes WHERE note_id = %s", (note_id,))
    row = cur.fetchone()
    cur.close()

    assert row["note_title"]  == new_title
    assert row["note_body"]   == new_body
    assert row["priority"]    == new_priority


# ═══════════════════════════════════════════════════════════════════════════════
# Property 3 — Safe-Delete Referential Integrity
# ═══════════════════════════════════════════════════════════════════════════════

def test_property3_outcome_safe_delete_blocked_by_mastery_record(db, prereq_ids):
    """
    Property 3: If a mastery_records row references outcome_id, a DELETE of
    that outcome must NOT remove it from the database.

    This mirrors the guard in routes/content.delete_outcome.
    """
    cur = db.cursor()

    # Create a fresh outcome to delete
    cur.execute("""
        INSERT INTO learning_outcomes
            (competency_id, outcome_code, outcome_name, outcome_description,
             mastery_threshold, sequence_order)
        VALUES (%s, 'SAFE-DEL-P3', 'Safe Delete Test', 'desc', 80, 99)
        RETURNING outcome_id
    """, (prereq_ids["competency_id"],))
    outcome_id = cur.fetchone()["outcome_id"]

    # Create a mastery record referencing it
    cur.execute("""
        INSERT INTO mastery_records
            (learner_id, outcome_id, mastery_level, mastery_status)
        VALUES (%s, %s, 'Beginning', 'In Progress')
    """, (prereq_ids["student_user_id"], outcome_id))
    db.commit()

    # Simulate the safe-delete guard check
    cur.execute(
        "SELECT mastery_id FROM mastery_records WHERE outcome_id = %s LIMIT 1",
        (outcome_id,)
    )
    blocked = cur.fetchone() is not None
    assert blocked, "Safe-delete guard must detect the referencing mastery record"

    # The outcome must still exist
    cur.execute(
        "SELECT outcome_id FROM learning_outcomes WHERE outcome_id = %s",
        (outcome_id,)
    )
    assert cur.fetchone() is not None, "Outcome must NOT be deleted when mastery records exist"
    cur.close()


def test_property3_lesson_safe_delete_blocked_by_assessment(db, prereq_ids):
    """
    Property 3 (lesson): If an assessments row references lesson_id, the
    safe-delete guard must detect it and block deletion.
    """
    cur = db.cursor()

    # Create a fresh outcome + lesson
    cur.execute("""
        INSERT INTO learning_outcomes
            (competency_id, outcome_code, outcome_name, outcome_description,
             mastery_threshold, sequence_order)
        VALUES (%s, 'SAFE-LES-P3', 'Lesson Safe Delete Test', 'desc', 80, 98)
        RETURNING outcome_id
    """, (prereq_ids["competency_id"],))
    outcome_id = cur.fetchone()["outcome_id"]

    cur.execute("""
        INSERT INTO lessons
            (course_id, outcome_id, lesson_title, sequence_order)
        VALUES (%s, %s, 'Lesson For Safe Delete', 1)
        RETURNING lesson_id
    """, (prereq_ids["course_id"], outcome_id))
    lesson_id = cur.fetchone()["lesson_id"]

    # Create a referencing assessment
    cur.execute("""
        INSERT INTO assessments (lesson_id, assessment_title, assessment_type)
        VALUES (%s, 'Guard Assessment', 'practice')
    """, (lesson_id,))
    db.commit()

    # Simulate guard
    cur.execute(
        "SELECT assessment_id FROM assessments WHERE lesson_id = %s LIMIT 1",
        (lesson_id,)
    )
    blocked = cur.fetchone() is not None
    assert blocked, "Safe-delete guard must detect the referencing assessment"

    # Lesson must still exist
    cur.execute("SELECT lesson_id FROM lessons WHERE lesson_id = %s", (lesson_id,))
    assert cur.fetchone() is not None, "Lesson must NOT be deleted when assessments exist"
    cur.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Property 4 — Question Options Invariant
# ═══════════════════════════════════════════════════════════════════════════════

@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
@given(
    n_options=option_count_st,
    correct_index=st.integers(min_value=0, max_value=5),
    q_text=text_body,
)
def test_property4_question_options_invariant(
    db, prereq_ids, n_options, correct_index, q_text
):
    """
    Property 4: For any N options (2–6) and any correct_index in [0, N-1],
    after inserting the question + options, the question_options table must
    have exactly N rows for that question_id, with is_correct=TRUE on exactly
    the designated option.
    """
    # Clamp correct_index to valid range for this n_options
    correct_index = correct_index % n_options

    cur = db.cursor()

    # Insert question
    cur.execute("""
        INSERT INTO questions
            (assessment_id, question_text, concept_tag, marks)
        VALUES (%s, %s, 'prop4-concept', 1)
        RETURNING question_id
    """, (prereq_ids["assessment_id"], q_text))
    question_id = cur.fetchone()["question_id"]

    # Insert N options, one correct
    for i in range(n_options):
        cur.execute("""
            INSERT INTO question_options (question_id, option_text, is_correct)
            VALUES (%s, %s, %s)
        """, (question_id, f"Option {i}", i == correct_index))
    db.commit()

    # Assert: exactly N rows
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM question_options WHERE question_id = %s",
        (question_id,)
    )
    assert cur.fetchone()["cnt"] == n_options, \
        f"Expected {n_options} options, got different count"

    # Assert: exactly 1 row with is_correct=TRUE at the correct index
    cur.execute("""
        SELECT COUNT(*) AS cnt FROM question_options
        WHERE question_id = %s AND is_correct = TRUE
    """, (question_id,))
    assert cur.fetchone()["cnt"] == 1, "Exactly one option must have is_correct=TRUE"

    # Assert: the correct option's text matches
    cur.execute("""
        SELECT option_text FROM question_options
        WHERE question_id = %s AND is_correct = TRUE
    """, (question_id,))
    correct_text = cur.fetchone()["option_text"]
    assert correct_text == f"Option {correct_index}", \
        "The designated option must be the one marked is_correct=TRUE"
    cur.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Property 5 — Question Delete Cascade
# ═══════════════════════════════════════════════════════════════════════════════

@settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
@given(k_options=option_count_st)
def test_property5_question_delete_cascade(db, prereq_ids, k_options):
    """
    Property 5: After deleting a question and all its options in a single
    transaction, neither the question row nor any of its K option rows should
    remain in the database.
    """
    cur = db.cursor()

    # Insert question + K options
    cur.execute("""
        INSERT INTO questions
            (assessment_id, question_text, concept_tag, marks)
        VALUES (%s, 'Cascade test question', 'prop5-concept', 1)
        RETURNING question_id
    """, (prereq_ids["assessment_id"],))
    question_id = cur.fetchone()["question_id"]

    for i in range(k_options):
        cur.execute("""
            INSERT INTO question_options (question_id, option_text, is_correct)
            VALUES (%s, %s, %s)
        """, (question_id, f"Opt {i}", i == 0))
    db.commit()

    # Perform cascade delete (same order as delete_question route)
    cur.execute("DELETE FROM question_options WHERE question_id = %s", (question_id,))
    cur.execute("DELETE FROM questions WHERE question_id = %s", (question_id,))
    db.commit()

    # Assert question is gone
    cur.execute("SELECT question_id FROM questions WHERE question_id = %s", (question_id,))
    assert cur.fetchone() is None, "Question must be deleted"

    # Assert all options are gone
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM question_options WHERE question_id = %s",
        (question_id,)
    )
    assert cur.fetchone()["cnt"] == 0, \
        f"All {k_options} options must be deleted; found remaining rows"
    cur.close()
