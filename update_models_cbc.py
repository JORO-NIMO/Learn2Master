import os

filepath = 'models.py'
with open(filepath, 'r') as f:
    content = f.read()

# I'll just add the classes to the end of models.py
new_classes = """
class SubStrand(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    strand_id = db.Column(db.Integer, db.ForeignKey('topic.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    order = db.Column(db.Integer)
    performance_indicators = db.relationship("PerformanceIndicator", backref="sub_strand", lazy=True)

class PerformanceIndicator(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sub_strand_id = db.Column(db.Integer, db.ForeignKey('sub_strand.id'), nullable=False)
    learning_outcome_id = db.Column(db.Integer, db.ForeignKey('learning_outcome.id'), nullable=False)
    description = db.Column(db.Text, nullable=False)
    order = db.Column(db.Integer)
"""

if "class PerformanceIndicator" not in content:
    with open(filepath, 'a') as f:
        f.write(new_classes)
    print("models.py updated with deeper CBC hierarchy.")
else:
    print("CBC hierarchy already exists.")
