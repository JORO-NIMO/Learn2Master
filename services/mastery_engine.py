"""Evidence-based mastery engine for Learn2Master.

Mastery is not based on planted percentages. It is calculated from learner evidence:
pre-test completion, adaptive practice, weak concept resolution, post-test performance,
and optional teacher verification.
"""


def calculate_percentage(correct_count, total_count):
    if total_count <= 0:
        return 0
    return round((correct_count / total_count) * 100)


def mastery_level(score):
    if score >= 90:
        return "Advanced"
    if score >= 80:
        return "Proficient"
    if score >= 70:
        return "Developing"
    return "Beginning"


def mastery_status(score, threshold=80):
    return "Mastered" if score >= threshold else "Not Yet Mastered"


def calculate_mastery(pretest_score, practice_score, posttest_score):
    """Backward-compatible mastery calculation without improvement weighting.

    Improvement is returned as 0 because learning gain belongs to analytics,
    not the learner mastery decision.
    """
    mastery_score = round((practice_score * 0.35) + (posttest_score * 0.65))
    return min(100, mastery_score), 0


def evidence_based_mastery(
    pretest_done,
    activity_done,
    practice_score,
    weak_concepts_resolved,
    posttest_score,
    teacher_verified=False,
    threshold=80,
):
    # activity_done means CBC reflection / learning evidence has been submitted.
    evidence = {
        "pretest_completed": bool(pretest_done),
        "reflection_completed": bool(activity_done),
        "adaptive_practice_completed": practice_score >= 70,
        "weak_concepts_resolved": bool(weak_concepts_resolved),
        "posttest_passed": posttest_score >= threshold,
        "teacher_verified": bool(teacher_verified),
    }

    ai_confidence = 0
    if evidence["pretest_completed"]:
        ai_confidence += 10
    if evidence["reflection_completed"]:
        ai_confidence += 15
    if evidence["adaptive_practice_completed"]:
        ai_confidence += 20
    if evidence["weak_concepts_resolved"]:
        ai_confidence += 20
    if evidence["posttest_passed"]:
        ai_confidence += 30
    if evidence["teacher_verified"]:
        ai_confidence += 5

    required_passed = (
        evidence["pretest_completed"]
        and evidence["reflection_completed"]
        and evidence["adaptive_practice_completed"]
        and evidence["weak_concepts_resolved"]
        and evidence["posttest_passed"]
    )

    return {
        "mastery_score": round(ai_confidence),
        "mastery_status": "Mastered" if required_passed else "Not Yet Mastered",
        "mastery_level": mastery_level(posttest_score),
        "ai_confidence": round(ai_confidence),
        "evidence": evidence,
    }
