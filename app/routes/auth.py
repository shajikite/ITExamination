from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from app.database.db import get_db
import psycopg2.extras

auth_bp = Blueprint('auth', __name__)

from functools import wraps

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('auth.login'))
            if role and session.get('user_type') != role:
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('auth.login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        try:
            db = get_db()
            cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Find user
            cur.execute('SELECT * FROM users WHERE username = %s AND is_active = TRUE', (username,))
            user = cur.fetchone()
            cur.close()
            
            if user and check_password_hash(user['password_hash'], password):
                # Set session
                session['user_id'] = user['id']
                session['user_type'] = user['user_type']
                session['full_name'] = user['full_name']
                session['school_id'] = user['school_id']
                
                # Redirect based on user role
                if user['user_type'] == 'state_admin':
                    return redirect(url_for('state_admin.dashboard'))
                elif user['user_type'] == 'question_setter':
                    return redirect(url_for('question_setter.dashboard'))
                elif user['user_type'] == 'school_admin':
                    return redirect(url_for('school_admin.dashboard'))
                elif user['user_type'] == 'invigilator':
                    return redirect(url_for('invigilator.dashboard'))
                elif user['user_type'] == 'revaluator':
                    return redirect(url_for('revaluator.dashboard'))
                elif user['user_type'] == 'student':
                    session.clear()
                    error = 'Students must be logged in by an invigilator.'
                else:
                    error = 'Invalid user type'
            else:
                error = 'Invalid username or password'
                
        except Exception as e:
            error = f'Database error: {str(e)}'
    
    return render_template('login.html', error=error)

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
