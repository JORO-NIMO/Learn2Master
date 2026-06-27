"""Explainable recommendation engine for Learn2Master."""


def build_recommendation(outcome_name, assessment_type, score, weak_concepts, mastery_score=None):
    weak = ", ".join(weak_concepts) if weak_concepts else "no major weak concept detected"

    if assessment_type == "pretest":
        return {
            "type": "Adaptive Learning Path",
            "reason": (
                f"Pre-test diagnostic for '{outcome_name}' scored {score}%. "
                f"Weak concept(s): {weak}. The system has selected adaptive notes, videos, "
                "and practice questions before the post-test."
            ),
        }

    if assessment_type == "practice":
        return {
            "type": "Practice Support",
            "reason": (
                f"Practice score for '{outcome_name}' is {score}%. Weak concept(s): {weak}. "
                "Revise the adaptive notes and attempt the practice again before the post-test."
            ),
        }

    if mastery_score is not None and mastery_score >= 80:
        return {
            "type": "Unlock Next Outcome",
            "reason": (
                f"Post-test score is {score}% and algorithm mastery is {mastery_score}%. "
                "Mastery has been attained, so the next learning outcome is unlocked."
            ),
        }

    return {
        "type": "Remediation Required",
        "reason": (
            f"Post-test score is {score}% and algorithm mastery is {mastery_score}%. "
            f"Weak concept(s): {weak}. The next learning outcome remains locked. "
            "Review the recommended notes, watch the video, and redo practice before attempting the post-test again."
        ),
    }
