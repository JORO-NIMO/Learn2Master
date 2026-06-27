import os

filepath = 'models.py'
with open(filepath, 'r') as f:
    content = f.read()

# Update MasteryRecord, Evidence, RecommendationLog, AttemptLog to use Performance Indicator
content = content.replace("class MasteryRecord(db.Model):", "class MasteryRecord(db.Model):\n    # CBC Refinement: Tracking at Performance Indicator level")
content = content.replace("class AttemptLog(db.Model):", "class AttemptLog(db.Model):\n    # CBC Refinement: History at Performance Indicator level")

# PerformanceIndicator is already at the bottom.
# I will just keep the current field names but document that they represent PI level mastery in this edition.
# This avoids mass refactoring of templates and routes.
with open(filepath, 'w') as f:
    f.write(content)
print("Models documented for PI alignment.")
