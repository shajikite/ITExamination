import os
import psycopg2
from urllib.parse import urlparse

def migrate():
    db_url = os.environ.get('DATABASE_URL', 'postgresql://exam_user:exam_password@db:5432/exam_db')
    
    # Handle the case where the script is run outside of the docker network
    if 'db' in db_url and os.environ.get('RUNNING_IN_DOCKER') != 'true':
        db_url = db_url.replace('@db:', '@localhost:')

    print(f"Connecting to {db_url}...")
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    
    try:
        print("Adding medium column to users table...")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS medium VARCHAR(20) DEFAULT 'English'")
        cur.execute("ALTER TABLE users ADD CONSTRAINT users_medium_check CHECK (medium IN ('English', 'Malayalam', 'Kannada', 'Tamil'))")
    except Exception as e:
        print(f"Note: {e}")
        conn.rollback()
        cur = conn.cursor()

    try:
        print("Adding class_id column to users table if missing...")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS class_id INTEGER")
    except Exception as e:
        print(f"Note: {e}")
        conn.rollback()
        cur = conn.cursor()

    try:
        print("Adding language column to questions table...")
        cur.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS language VARCHAR(20) DEFAULT 'English'")
        cur.execute("ALTER TABLE questions ADD CONSTRAINT questions_language_check CHECK (language IN ('English', 'Malayalam', 'Kannada', 'Tamil'))")
    except Exception as e:
        print(f"Note: {e}")
        conn.rollback()
        cur = conn.cursor()

    conn.commit()
    cur.close()
    conn.close()
    print("Migration completed successfully.")

if __name__ == "__main__":
    migrate()
