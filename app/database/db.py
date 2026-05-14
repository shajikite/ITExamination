import psycopg2
import psycopg2.extras
from flask import g, current_app
import time

def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(current_app.config['DATABASE_URL'])
        g.db.autocommit = True
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def run_migrations(app):
    """Run safe ALTER TABLE migrations on startup."""
    migrations = [
        # Add status column to questions for soft-deactivate
        "ALTER TABLE questions ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active'",
        # Add is_active column to schools
        "ALTER TABLE schools ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
        # Add class_id to users (students carry a class)
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS class_id INTEGER REFERENCES classes(id)",
        # Add max_score to examinations
        "ALTER TABLE examinations ADD COLUMN IF NOT EXISTS max_score INTEGER DEFAULT 0",
        # Add total_short_answer_questions to examinations
        "ALTER TABLE examinations ADD COLUMN IF NOT EXISTS total_short_answer_questions INTEGER DEFAULT 0",
        # Add difficulty counts to exam_chapters
        "ALTER TABLE exam_chapters ADD COLUMN IF NOT EXISTS easy_count INTEGER DEFAULT 0",
        "ALTER TABLE exam_chapters ADD COLUMN IF NOT EXISTS average_count INTEGER DEFAULT 0",
        "ALTER TABLE exam_chapters ADD COLUMN IF NOT EXISTS difficult_count INTEGER DEFAULT 0",
        # Update questions question_type check constraint
        "ALTER TABLE questions DROP CONSTRAINT IF EXISTS questions_question_type_check",
        "ALTER TABLE questions ADD CONSTRAINT questions_question_type_check CHECK (question_type IN ('theory', 'practical', 'short_answer'))",
        # Add chapter_id to questions
        "ALTER TABLE questions ADD COLUMN IF NOT EXISTS chapter_id INTEGER REFERENCES chapters(id) ON DELETE SET NULL",
        # Add is_bank and is_global to questions
        "ALTER TABLE questions ADD COLUMN IF NOT EXISTS is_bank BOOLEAN DEFAULT FALSE",
        "ALTER TABLE questions ADD COLUMN IF NOT EXISTS is_global BOOLEAN DEFAULT FALSE",
        # Add option_id to student_practical_submissions to track Choice A/B
        "ALTER TABLE student_practical_submissions ADD COLUMN IF NOT EXISTS option_id INTEGER REFERENCES question_options(id) ON DELETE SET NULL",
        # Add image support to question_options for alternative tasks
        "ALTER TABLE question_options ADD COLUMN IF NOT EXISTS option_image_blob BYTEA",
        "ALTER TABLE question_options ADD COLUMN IF NOT EXISTS option_image_mimetype VARCHAR(50)",
        # Add theory_phase to student_exams for step-by-step flow
        "ALTER TABLE student_exams ADD COLUMN IF NOT EXISTS theory_phase INTEGER DEFAULT 1",
        # Add resource file columns to questions
        "ALTER TABLE questions ADD COLUMN IF NOT EXISTS resource_file_blob BYTEA",
        "ALTER TABLE questions ADD COLUMN IF NOT EXISTS resource_file_name VARCHAR(255)",
        # Revaluator role and assignments
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_user_type_check",
        "ALTER TABLE users ADD CONSTRAINT users_user_type_check CHECK (user_type IN ('state_admin', 'question_setter', 'school_admin', 'invigilator', 'student', 'revaluator'))",
        "CREATE TABLE IF NOT EXISTS revaluator_assignments (id SERIAL PRIMARY KEY, exam_id INTEGER REFERENCES examinations(id) ON DELETE CASCADE, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, assigned_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        "ALTER TABLE student_practical_submissions ADD COLUMN IF NOT EXISTS revaluated_by INTEGER REFERENCES users(id) ON DELETE SET NULL",
        "ALTER TABLE student_practical_submissions ADD COLUMN IF NOT EXISTS revaluation_time TIMESTAMP",
        "ALTER TABLE student_practical_submissions ADD COLUMN IF NOT EXISTS revaluation_remarks TEXT",
        "ALTER TABLE student_practical_submissions ADD COLUMN IF NOT EXISTS initial_score INTEGER",
        "UPDATE student_practical_submissions SET initial_score = score_obtained WHERE initial_score IS NULL AND score_obtained IS NOT NULL",
        "ALTER TABLE student_practical_submissions ADD COLUMN IF NOT EXISTS needs_revaluation BOOLEAN DEFAULT FALSE",
        "ALTER TABLE questions ADD COLUMN IF NOT EXISTS value_points TEXT",
    ]

    # Cascade FK migrations — each is a pair (drop old constraint, add new with CASCADE)
    # These are idempotent because we use IF EXISTS / try-except.
    cascade_migrations = [
        # student_exams.school_id → schools ON DELETE CASCADE
        ("ALTER TABLE student_exams DROP CONSTRAINT IF EXISTS student_exams_school_id_fkey",
         "ALTER TABLE student_exams ADD CONSTRAINT student_exams_school_id_fkey "
         "FOREIGN KEY (school_id) REFERENCES schools(id) ON DELETE CASCADE"),
        # student_exams.student_id → users ON DELETE CASCADE
        ("ALTER TABLE student_exams DROP CONSTRAINT IF EXISTS student_exams_student_id_fkey",
         "ALTER TABLE student_exams ADD CONSTRAINT student_exams_student_id_fkey "
         "FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE"),
        # student_exams.exam_id → examinations ON DELETE CASCADE
        ("ALTER TABLE student_exams DROP CONSTRAINT IF EXISTS student_exams_exam_id_fkey",
         "ALTER TABLE student_exams ADD CONSTRAINT student_exams_exam_id_fkey "
         "FOREIGN KEY (exam_id) REFERENCES examinations(id) ON DELETE CASCADE"),
        # questions.uploaded_by → users ON DELETE SET NULL
        ("ALTER TABLE questions DROP CONSTRAINT IF EXISTS questions_uploaded_by_fkey",
         "ALTER TABLE questions ADD CONSTRAINT questions_uploaded_by_fkey "
         "FOREIGN KEY (uploaded_by) REFERENCES users(id) ON DELETE SET NULL"),
        # mark_lists.prepared_by → users ON DELETE SET NULL
        ("ALTER TABLE mark_lists DROP CONSTRAINT IF EXISTS mark_lists_prepared_by_fkey",
         "ALTER TABLE mark_lists ADD CONSTRAINT mark_lists_prepared_by_fkey "
         "FOREIGN KEY (prepared_by) REFERENCES users(id) ON DELETE SET NULL"),
        # student_practical_submissions.evaluated_by → users ON DELETE SET NULL
        ("ALTER TABLE student_practical_submissions "
         "DROP CONSTRAINT IF EXISTS student_practical_submissions_evaluated_by_fkey",
         "ALTER TABLE student_practical_submissions "
         "ADD CONSTRAINT student_practical_submissions_evaluated_by_fkey "
         "FOREIGN KEY (evaluated_by) REFERENCES users(id) ON DELETE SET NULL"),
        # users.school_id → schools ON DELETE CASCADE (admins/students belong to school)
        ("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_school_id_fkey",
         "ALTER TABLE users ADD CONSTRAINT users_school_id_fkey "
         "FOREIGN KEY (school_id) REFERENCES schools(id) ON DELETE CASCADE"),
        # users.created_by → users ON DELETE SET NULL
        ("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_created_by_fkey",
         "ALTER TABLE users ADD CONSTRAINT users_created_by_fkey "
         "FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL"),
        # schools.state_admin_id → users ON DELETE SET NULL
        ("ALTER TABLE schools DROP CONSTRAINT IF EXISTS schools_state_admin_id_fkey",
         "ALTER TABLE schools ADD CONSTRAINT schools_state_admin_id_fkey "
         "FOREIGN KEY (state_admin_id) REFERENCES users(id) ON DELETE SET NULL"),
        # student_theory_answers.student_exam_id already cascaded via student_exams,
        # but ensure question_id is SET NULL so answer records survive question deletion
        ("ALTER TABLE student_theory_answers "
         "DROP CONSTRAINT IF EXISTS student_theory_answers_student_exam_id_fkey",
         "ALTER TABLE student_theory_answers "
         "ADD CONSTRAINT student_theory_answers_student_exam_id_fkey "
         "FOREIGN KEY (student_exam_id) REFERENCES student_exams(id) ON DELETE CASCADE"),
        ("ALTER TABLE student_practical_submissions "
         "DROP CONSTRAINT IF EXISTS student_practical_submissions_student_exam_id_fkey",
         "ALTER TABLE student_practical_submissions "
         "ADD CONSTRAINT student_practical_submissions_student_exam_id_fkey "
         "FOREIGN KEY (student_exam_id) REFERENCES student_exams(id) ON DELETE CASCADE"),
        ("ALTER TABLE mark_lists "
         "DROP CONSTRAINT IF EXISTS mark_lists_student_exam_id_fkey",
         "ALTER TABLE mark_lists "
         "ADD CONSTRAINT mark_lists_student_exam_id_fkey "
         "FOREIGN KEY (student_exam_id) REFERENCES student_exams(id) ON DELETE CASCADE"),
        ("ALTER TABLE exam_sessions "
         "DROP CONSTRAINT IF EXISTS exam_sessions_student_exam_id_fkey",
         "ALTER TABLE exam_sessions "
         "ADD CONSTRAINT exam_sessions_student_exam_id_fkey "
         "FOREIGN KEY (student_exam_id) REFERENCES student_exams(id) ON DELETE CASCADE"),
        # question_setter_assignments already ON DELETE CASCADE in schema,
        # but re-declare to be safe
        ("ALTER TABLE question_setter_assignments "
         "DROP CONSTRAINT IF EXISTS question_setter_assignments_user_id_fkey",
         "ALTER TABLE question_setter_assignments "
         "ADD CONSTRAINT question_setter_assignments_user_id_fkey "
         "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE"),
        # Cleanup existing orphan users and records
        ("DELETE FROM users WHERE user_type IN ('school_admin', 'student', 'invigilator') AND school_id IS NULL",
         "SELECT 1"),
        ("DELETE FROM student_exams WHERE school_id IS NULL OR exam_id IS NULL",
         "SELECT 1"),
        ("DELETE FROM mark_lists WHERE student_exam_id NOT IN (SELECT id FROM student_exams)",
         "SELECT 1"),
    ]



    with app.app_context():
        # Wait for DB to be ready (retry up to 30 s)
        for attempt in range(15):
            try:
                cur = get_db().cursor()
                break
            except Exception:
                print(f"DB not ready, retrying ({attempt+1}/15)...")
                time.sleep(2)
                g.pop('db', None)  # Clear cached broken connection
        else:
            print("ERROR: Could not connect to DB for migrations after 30s.")
            return

        # Simple column migrations
        for sql in migrations:
            try:
                cur.execute(sql)
            except Exception as e:
                print(f"Migration warning: {e}")
        # CASCADE FK migrations (each pair: drop then add)
        for drop_sql, add_sql in cascade_migrations:
            try:
                cur.execute(drop_sql)
                cur.execute(add_sql)
            except Exception as e:
                print(f"Cascade migration warning: {e}")
        get_db().commit()
        cur.close()

def init_db(app):
    app.teardown_appcontext(close_db)
    run_migrations(app)

def query_db(query, args=(), one=False):
    cur = get_db().cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def insert_db(query, args=()):
    cur = get_db().cursor()
    cur.execute(query, args)
    get_db().commit()
    last_id = cur.fetchone()[0] if cur.description else None
    cur.close()
    return last_id

def update_db(query, args=()):
    cur = get_db().cursor()
    cur.execute(query, args)
    get_db().commit()
    cur.close()