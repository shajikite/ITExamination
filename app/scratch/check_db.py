from app import create_app
from app.database.db import query_db

app = create_app()
with app.app_context():
    exams = query_db("SELECT id, exam_name, total_theory_questions, total_practical_questions FROM examinations")
    print(f"Exams: {exams}")
    
    questions = query_db("SELECT id, exam_id, question_type, language FROM questions LIMIT 5")
    print(f"Questions: {questions}")
