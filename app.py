from flask import Flask, render_template, request, url_for
import json
import snowflake.connector
import spacy
from fuzzywuzzy import process
import os

app = Flask(__name__)

nlp = spacy.load("en_core_web_sm")

CONNECTION_PARAMETERS = {
    "user": os.environ.get('SNOWFLAKE_USER'),
    "password": os.environ.get('SNOWFLAKE_PASSWORD'),
    "account": os.environ.get('SNOWFLAKE_ACCOUNT'),
    "role": os.environ.get('SNOWFLAKE_ROLE'),
    "warehouse": os.environ.get('SNOWFLAKE_WAREHOUSE'),
    "database": os.environ.get('SNOWFLAKE_DATABASE'),
    "schema": os.environ.get('SNOWFLAKE_SCHEMA')
}
conn = snowflake.connector.connect(**CONNECTION_PARAMETERS)

levels = {
    'beginner': ['beginner', 'novice', 'easy', 'starting'],
    'intermediate': ['intermediate', 'mid-level', 'medium'],
    'expert': ['advanced', 'expert', 'hard', 'difficult']
}

equipments = {
    'barbell': ['barbell', 'bar'],
    'dumbbell': ['dumbbell'],
    'other': ['other'],
    'body_only': ['body only', 'body'],
    'cable': ['cable', 'cable machine'],
    'machine': ['machine'],
    'kettlebells': ['kettlebells', 'kettlebell'],
    'bands': ['bands', 'tension band', 'rubber ban', 'stretch band'],
    'medicine_ball': ['medicine ball', 'medicine'],
    'exercise_ball': ['exercise ball'],
    'foam_roll': ['foam roll', 'roller'],
    'e-z_curl_bar': ['e-z curl bar', 'ez bar']
}

muscles = {
    'abdominals': ['abdominals', 'abs', 'core'],
    'hamstrings': ['hamstrings', 'hams', 'legs'],
    'adductors': ['adductors'],
    'quadriceps': ['quadriceps', 'quads', 'legs', 'leg'],
    'biceps': ['biceps', 'bicep'],
    'shoulders': ['shoulders', 'deltoids'],
    'chest': ['chest'],
    'middle_back': ['middle back', 'back'],
    'calves': ['calves', 'calf', 'legs'],
    'glutes': ['glutes', 'butt'],
    'lower_back': ['lower back', 'back'],
    'triceps': ['triceps', 'back of arm'],
    'forearms': ['forearms'],
    'neck': ['neck'],
    'traps': ['traps'],
    'abductors': ['abductors'],
    'lats': ['lats']
}

def extract_parameters(query):
    doc = nlp(query.lower())

    level = None
    equipment = None
    primarymuscles = None

    level_keywords = list(levels.keys())
    equipment_keywords = list(equipments.keys())
    muscle_keywords = list(muscles.keys())

    stopwords = {'for', 'and', 'the', 'in', 'on', 'to', 'of'}

    for token in doc:
        if token.text in stopwords:
            continue

        if token.text in levels['expert']:
            level = 'expert'
            continue

        level_match = process.extractOne(token.text, level_keywords)
        if level_match and level_match[1] >= 85:
            level = level_match[0]

        equipment_match = process.extractOne(token.text, equipment_keywords)
        if equipment_match and equipment_match[1] >= 85:
            equipment = equipment_match[0]

        muscle_match = process.extractOne(token.text, muscle_keywords)
        if muscle_match and muscle_match[1] >= 90:
            primarymuscles = muscle_match[0]

    return level, equipment, primarymuscles

def db_search(level, equipment, primarymuscles):
    cursor = conn.cursor()

    query_conditions = []
    if level:
        query_conditions.append("level ILIKE %s")
    if equipment:
        query_conditions.append("equipment ILIKE %s")
    if primarymuscles:
        query_conditions.append("primarymuscles ILIKE %s")

    where_clause = " AND ".join(query_conditions) if query_conditions else "1=1"

    query_string = f"""
    SELECT * FROM exercise_db.exercise_schema.exercise_table
    WHERE {where_clause};
    """

    params = []
    if level:
        params.append(f'%{level}%')
    if equipment:
        params.append(f'%{equipment}%')
    if primarymuscles:
        params.append(f'%{primarymuscles}%')

    cursor.execute(query_string, params)

    exercises = cursor.fetchall()
    
    cursor.close()

    formatted_exercises = []
    for exercise in exercises:
        instructions = exercise[5]
        if isinstance(instructions, str):
            try:
                instructions = json.loads(instructions)
            except json.JSONDecodeError:
                instructions = []

        numbered_instructions = []
        for i, instruction in enumerate(instructions, 1):
            numbered_instructions.append(f"{i}. {instruction}")
        
        formatted_instructions = '\n'.join(numbered_instructions)

        image_filenames = exercise[4]
        if isinstance(image_filenames, str):
            try:
                image_filenames = json.loads(image_filenames)
            except (ValueError, SyntaxError):
                image_filenames = []

        image_urls = []
        for image_filename in image_filenames:
            image_urls.append(url_for('static', filename=f'images/{image_filename}'))

        formatted_exercises.append({
            'name': exercise[8].title(),
            'category': exercise[0].title(),
            'instructions': formatted_instructions.strip(),
            'images': image_urls
        })

    return formatted_exercises

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query')
    page = int(request.args.get('page', 1))
    results_per_page = 10

    if query:
        level, equipment, primarymuscles = extract_parameters(query)

        all_exercises = db_search(level, equipment, primarymuscles)

        start_index = (page - 1) * results_per_page
        end_index = start_index + results_per_page
        paginated_results = all_exercises[start_index:end_index]

        return render_template('results.html', exercises=paginated_results, 
                               equipment=equipment, level=level, muscle=primarymuscles, 
                               current_page=page, total_results=len(all_exercises))

    return render_template('results.html', exercises=[], equipment=None, level=None, muscle=None)


if __name__ == '__main__':
    app.run(debug=True)
