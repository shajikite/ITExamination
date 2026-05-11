from app import create_app
from app.database.db import get_db, query_db
import json
from flask import session

app = create_app()

with app.test_request_context(
    '/student/api/save-answer',
    method='POST',
    json={'student_exam_id': 15, 'question_id': '11', 'selected_options': '43'}
):
    # Mock session
    session['user_id'] = 5 # arbitrary student id
    session['user_type'] = 'student'
    
    try:
        from app.routes.student import save_answer
        resp = save_answer()
        print("Response:", resp.get_json())
    except Exception as e:
        import traceback
        traceback.print_exc()
