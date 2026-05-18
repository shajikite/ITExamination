from app import create_app
from app.database.db import update_db, query_db

app = create_app()
with app.app_context():
    # Identify students who were reset but are stuck in phase 2
    # theory_status = 'pending' and theory_phase = 2 is a clear sign.
    stuck_students = query_db('''
        SELECT id FROM student_exams 
        WHERE theory_status = 'pending' AND theory_phase = 2
    ''')
    
    if stuck_students:
        print(f"Found {len(stuck_students)} students stuck in Phase 2 with 'pending' status. Fixing...")
        for student in stuck_students:
            update_db('UPDATE student_exams SET theory_phase = 1 WHERE id = %s', (student['id'],))
        print("Fix applied successfully.")
    else:
        print("No stuck students found with 'pending' status.")
        
    # Also check those in_progress but with 0 answers?
    stuck_in_progress = query_db('''
        SELECT se.id FROM student_exams se
        LEFT JOIN student_theory_answers sta ON se.id = sta.student_exam_id
        WHERE se.theory_status = 'in_progress' AND se.theory_phase = 2
        GROUP BY se.id
        HAVING COUNT(sta.id) = 0
    ''')
    
    if stuck_in_progress:
        print(f"Found {len(stuck_in_progress)} students stuck in Phase 2 with 'in_progress' status but 0 answers. Fixing...")
        for student in stuck_in_progress:
            update_db('UPDATE student_exams SET theory_phase = 1 WHERE id = %s', (student['id'],))
        print("Fix applied successfully.")
    else:
        print("No stuck students found with 'in_progress' status and 0 answers.")
