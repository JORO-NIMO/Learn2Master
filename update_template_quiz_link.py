import os

filepath = 'templates/learning_outcome.html'
with open(filepath, 'r') as f:
    content = f.read()

search_text = """                <form action="{{ url_for('take_test', lo_id=lo.id) }}" method="POST" class="mb-2">"""

replace_text = """                <a href="{{ url_for('take_quiz', lo_id=lo.id) }}" class="btn btn-warning w-100 mb-3">Start Real Assessment</a>
                <form action="{{ url_for('take_test', lo_id=lo.id) }}" method="POST" class="mb-2">"""

content = content.replace(search_text, replace_text)

with open(filepath, 'w') as f:
    f.write(content)
print("Template updated with quiz link.")
