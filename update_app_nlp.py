import os

filepath = 'app.py'
with open(filepath, 'r') as f:
    content = f.read()

# Add simple NLP analysis logic for evidence submission
search_text = """@app.route('/lo/<int:lo_id>/evidence', methods=['POST'])
@login_required
@role_required('student')
def submit_evidence(lo_id):
    content = request.form.get('content')
    evidence_type = request.form.get('type', 'text')"""

replace_text = """@app.route('/lo/<int:lo_id>/evidence', methods=['POST'])
@login_required
@role_required('student')
def submit_evidence(lo_id):
    content = request.form.get('content')
    evidence_type = request.form.get('type', 'text')

    # AI Feature: Basic NLP Keyword Analysis for Reflection Depth
    keywords = ['learned', 'understand', 'concept', 'difficult', 'mastery', 'demonstrate', 'experiment']
    depth_score = sum(1 for word in keywords if word in content.lower())
    nlp_analysis = f"Reflection Depth Score: {depth_score}/{len(keywords)}"
    content = f"{content} | NLP Analysis: {nlp_analysis}" """

if search_text in content:
    new_content = content.replace(search_text, replace_text)
    with open(filepath, 'w') as f:
        f.write(new_content)
    print("app.py updated with NLP analysis.")
else:
    print("Search text not found.")
