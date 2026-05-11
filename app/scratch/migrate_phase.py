import psycopg2
import os

# Manual migration script
db_url = 'postgresql://exam_user:exam_password@localhost:5432/exam_db'

try:
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("ALTER TABLE student_exams ADD COLUMN IF NOT EXISTS theory_phase INTEGER DEFAULT 1;")
    print("Migration successful: added theory_phase to student_exams")
    cur.close()
    conn.close()
except Exception as e:
    print(f"Migration failed: {e}")
