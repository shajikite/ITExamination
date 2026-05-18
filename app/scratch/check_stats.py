from app import create_app
from app.database.db import query_db

app = create_app()
with app.app_context():
    stats = query_db("""
        SELECT e.id, e.exam_name, e.total_theory_questions, 
               (SELECT COUNT(*) FROM questions q WHERE q.exam_id = e.id AND q.question_type = 'theory') as actual_theory,
               (SELECT COUNT(*) FROM questions q WHERE q.exam_id = e.id AND q.question_type = 'short_answer') as actual_short,
               (SELECT COUNT(*) FROM questions q WHERE q.exam_id = e.id AND q.question_type = 'practical') as actual_practical
        FROM examinations e
    """)
    print(f"Stats: {stats}")
