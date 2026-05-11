import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash
import os

combinations = [
    "postgresql://exam_user:exam_password@localhost:5432/exam_db",
    "dbname=exam_db user=exam_user password=exam_password",
    "dbname=gkdata user=gkadmin",
    "dbname=exam_db user=shaji",
    "dbname=postgres user=shaji"
]

def check_admin():
    conn = None
    for dsn in combinations:
        try:
            print(f"Trying DSN: {dsn}")
            conn = psycopg2.connect(dsn)
            print("Connected successfully!")
            break
        except Exception as e:
            print(f"Failed: {e}")
    
    if not conn:
        print("Could not connect to database.")
        return

    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # Check if table 'users' exists
    cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'users')")
    if not cur.fetchone()[0]:
        print("Table 'users' does not exist.")
        cur.close()
        conn.close()
        return

    cur.execute("SELECT * FROM users WHERE user_type = 'state_admin'")
    admins = cur.fetchall()
    
    if not admins:
        print("No admin found. Creating one...")
        pw_hash = generate_password_hash('admin123')
        cur.execute('''
            INSERT INTO users (username, password_hash, full_name, user_type, is_active)
            VALUES (%s, %s, %s, %s, %s)
        ''', ('admin', pw_hash, 'System Admin', 'state_admin', True))
        conn.commit()
        print("Admin created: admin / admin123")
    else:
        print("Found admins:")
        for admin in admins:
            print(f"- {admin['username']}")
            # Reset password for easy testing
            cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (generate_password_hash('admin123'), admin['id']))
            conn.commit()
            print(f"Password reset for {admin['username']} to 'admin123'")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    check_admin()
