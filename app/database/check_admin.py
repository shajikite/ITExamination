import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash
import os

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/it_exam')

def check_admin():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
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
            # I can't see the password, but I can reset it if I want.
            # cur.execute("UPDATE users SET password_hash = %s WHERE username = %s", (generate_password_hash('admin123'), admin['username']))
            # conn.commit()
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    check_admin()
