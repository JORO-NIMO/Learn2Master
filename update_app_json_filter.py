import os
import json

filepath = 'app.py'
with open(filepath, 'r') as f:
    content = f.read()

search_text = """app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///learn2master.db'"""

replace_text = """app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///learn2master.db'

@app.template_filter('from_json')
def from_json_filter(value):
    return json.loads(value)"""

if "import os" in content:
    content = content.replace("import os", "import os\nimport json")

if search_text in content:
    new_content = content.replace(search_text, replace_text)
    with open(filepath, 'w') as f:
        f.write(new_content)
    print("app.py updated with json filter.")
else:
    print("Search text not found.")
