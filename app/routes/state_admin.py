from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash
from app.database.db import query_db, insert_db, update_db
from app.routes.auth import login_required
import os
from datetime import datetime
import csv
import io

state_admin_bp = Blueprint('state_admin', __name__)

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@state_admin_bp.route('/dashboard')
@login_required(role='state_admin')
def dashboard():
    stats = {
        'total_schools': query_db('SELECT COUNT(*) as count FROM schools')[0]['count'],
        'total_exams': query_db('SELECT COUNT(*) as count FROM examinations')[0]['count'],
        'total_students': query_db("SELECT COUNT(*) as count FROM users WHERE user_type='student'")[0]['count'],
        'active_exams': query_db("SELECT COUNT(*) as count FROM examinations WHERE status='ongoing'")[0]['count']
    }

    recent_exams = query_db('''
        SELECT e.*, c.class_name, s.subject_name
        FROM examinations e
        JOIN classes c ON e.class_id = c.id
        JOIN subjects s ON e.subject_id = s.id
        ORDER BY e.created_at DESC LIMIT 10
    ''')

    return render_template('state_admin/dashboard.html', stats=stats, recent_exams=recent_exams)

# ---------------------------------------------------------------------------
# Schools — Create / List / Edit / Toggle / Delete
# ---------------------------------------------------------------------------

@state_admin_bp.route('/manage-schools', methods=['GET', 'POST'])
@login_required(role='state_admin')
def manage_schools():
    if request.method == 'POST':
        school_name = request.form['school_name']
        school_code = request.form['school_code']
        address = request.form.get('address', '')
        phone = request.form.get('phone', '')
        email = request.form.get('email', '')

        insert_db('''
            INSERT INTO schools (school_name, school_code, address, phone, email, state_admin_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (school_name, school_code, address, phone, email, session['user_id']))

        flash('School created successfully!', 'success')
        return redirect(url_for('state_admin.manage_schools'))

    schools = query_db('SELECT * FROM schools ORDER BY created_at DESC')
    return render_template('state_admin/manage_schools.html', schools=schools)


@state_admin_bp.route('/edit-school/<int:school_id>', methods=['POST'])
@login_required(role='state_admin')
def edit_school(school_id):
    school_name = request.form['school_name']
    school_code = request.form['school_code']
    address = request.form.get('address', '')
    phone = request.form.get('phone', '')
    email = request.form.get('email', '')

    update_db('''
        UPDATE schools SET school_name=%s, school_code=%s, address=%s, phone=%s, email=%s
        WHERE id=%s
    ''', (school_name, school_code, address, phone, email, school_id))

    flash('School updated successfully!', 'success')
    return redirect(url_for('state_admin.manage_schools'))


@state_admin_bp.route('/toggle-school/<int:school_id>', methods=['POST'])
@login_required(role='state_admin')
def toggle_school(school_id):
    school = query_db('SELECT is_active FROM schools WHERE id=%s', (school_id,), one=True)
    if school:
        new_state = not school['is_active']
        update_db('UPDATE schools SET is_active=%s WHERE id=%s', (new_state, school_id))
        status_label = 'activated' if new_state else 'deactivated'
        flash(f'School {status_label} successfully!', 'success')
    return redirect(url_for('state_admin.manage_schools'))


@state_admin_bp.route('/delete-school/<int:school_id>', methods=['POST'])
@login_required(role='state_admin')
def delete_school(school_id):
    try:
        update_db('DELETE FROM schools WHERE id=%s', (school_id,))
        flash('School deleted successfully!', 'success')
    except Exception as e:
        flash(f'Cannot delete school: there may be related data still attached. Error: {str(e)[:120]}', 'error')
    return redirect(request.referrer or url_for('state_admin.manage_schools'))


@state_admin_bp.route('/bulk-upload-schools', methods=['POST'])
@login_required(role='state_admin')
def bulk_upload_schools():
    if 'csv_file' not in request.files:
        flash('No file provided', 'error')
        return redirect(url_for('state_admin.manage_schools'))

    file = request.files['csv_file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('state_admin.manage_schools'))

    if not file.filename.endswith('.csv'):
        flash('Please upload a CSV file', 'error')
        return redirect(url_for('state_admin.manage_schools'))

    try:
        stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
        csv_input = csv.DictReader(stream, skipinitialspace=True)

        success_count = 0
        error_count = 0

        for row in csv_input:
            # Clean keys to lowercase and strip whitespace
            r_clean = {str(k).strip().lower() if k else '': v for k, v in row.items()}
            
            school_name = (r_clean.get('school_name') or '').strip()
            school_code = (r_clean.get('school_code') or '').strip()
            address = (r_clean.get('address') or '').strip()
            phone = (r_clean.get('phone') or '').strip()
            email = (r_clean.get('email') or '').strip()

            if not school_name or not school_code:
                error_count += 1
                continue

            # Check if school_code already exists
            existing = query_db('SELECT id FROM schools WHERE school_code = %s', (school_code,), one=True)
            if existing:
                error_count += 1
                continue

            insert_db('''
                INSERT INTO schools (school_name, school_code, address, phone, email, state_admin_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (school_name, school_code, address, phone, email, session['user_id']))
            success_count += 1

        flash(f'Successfully added {success_count} schools. Errors/Duplicates skipped: {error_count}.',
              'success' if success_count > 0 else 'warning')

    except Exception as e:
        flash(f'Error processing file: {str(e)}', 'error')

    return redirect(url_for('state_admin.manage_schools'))

# ---------------------------------------------------------------------------
# School Admins — Create / List / Edit / Toggle / Delete
# ---------------------------------------------------------------------------

@state_admin_bp.route('/create-school-admin', methods=['GET', 'POST'])
@login_required(role='state_admin')
def create_school_admin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        full_name = request.form['full_name']
        email = request.form.get('email', '')
        phone = request.form.get('phone', '')
        school_id = request.form['school_id']

        # Check duplicate username
        existing = query_db('SELECT id FROM users WHERE username=%s', (username,), one=True)
        if existing:
            flash('Username already exists. Please choose another.', 'error')
            return redirect(url_for('state_admin.create_school_admin'))

        password_hash = generate_password_hash(password)

        insert_db('''
            INSERT INTO users (username, password_hash, full_name, email, phone, user_type, school_id, created_by)
            VALUES (%s, %s, %s, %s, %s, 'school_admin', %s, %s)
        ''', (username, password_hash, full_name, email, phone, school_id, session['user_id']))

        flash('School Admin created successfully!', 'success')
        return redirect(url_for('state_admin.create_school_admin'))

    schools = query_db('SELECT * FROM schools ORDER BY school_name')
    admins = query_db('''
        SELECT u.*, s.school_name
        FROM users u
        JOIN schools s ON u.school_id = s.id
        WHERE u.user_type = 'school_admin'
        ORDER BY u.created_at DESC
    ''')
    # Calculate summary stats
    stats = {
        'total': len(admins),
        'active': sum(1 for a in admins if a['is_active']),
        'schools_count': len(schools),
        'schools_with_admins': len(set(a['school_id'] for a in admins if a['school_id']))
    }
    return render_template('state_admin/create_school_admin.html', schools=schools, admins=admins, stats=stats)


@state_admin_bp.route('/bulk-upload-school-admins', methods=['POST'])
@login_required(role='state_admin')
def bulk_upload_school_admins():
    if 'csv_file' not in request.files:
        flash('No file provided', 'error')
        return redirect(url_for('state_admin.create_school_admin'))

    file = request.files['csv_file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('state_admin.create_school_admin'))

    if not file.filename.endswith('.csv'):
        flash('Please upload a CSV file', 'error')
        return redirect(url_for('state_admin.create_school_admin'))

    try:
        stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
        csv_input = csv.DictReader(stream, skipinitialspace=True)

        success_count = 0
        error_count = 0

        for row in csv_input:
            r_clean = {str(k).strip().lower() if k else '': v for k, v in row.items()}
            
            school_code = (r_clean.get('school_code') or '').strip()
            username = (r_clean.get('username') or '').strip()
            password = (r_clean.get('password') or '').strip()
            full_name = (r_clean.get('full_name') or '').strip()
            email = (r_clean.get('email') or '').strip()
            phone = (r_clean.get('phone') or '').strip()

            if not all([school_code, username, password, full_name]):
                error_count += 1
                continue

            # Resolve school_id
            school = query_db('SELECT id FROM schools WHERE school_code = %s', (school_code,), one=True)
            if not school:
                error_count += 1
                continue

            # Check duplicate username
            existing = query_db('SELECT id FROM users WHERE username = %s', (username,), one=True)
            if existing:
                error_count += 1
                continue

            password_hash = generate_password_hash(password)

            insert_db('''
                INSERT INTO users (username, password_hash, full_name, email, phone, user_type, school_id, created_by)
                VALUES (%s, %s, %s, %s, %s, 'school_admin', %s, %s)
            ''', (username, password_hash, full_name, email, phone, school['id'], session['user_id']))
            success_count += 1

        flash(f'Successfully added {success_count} school admins. Errors/Duplicates skipped: {error_count}.',
              'success' if success_count > 0 else 'warning')

    except Exception as e:
        flash(f'Error processing file: {str(e)}', 'error')

    return redirect(url_for('state_admin.create_school_admin'))


@state_admin_bp.route('/edit-user/<int:user_id>', methods=['POST'])
@login_required(role='state_admin')
def edit_user(user_id):
    full_name = request.form['full_name']
    email = request.form.get('email', '')
    phone = request.form.get('phone', '')
    school_id = request.form.get('school_id') or None
    class_id = request.form.get('class_id') or None
    medium = request.form.get('medium', 'English')
    new_password = request.form.get('new_password', '').strip()

    if new_password:
        password_hash = generate_password_hash(new_password)
        update_db('''
            UPDATE users SET full_name=%s, email=%s, phone=%s, school_id=%s, class_id=%s, medium=%s, password_hash=%s
            WHERE id=%s
        ''', (full_name, email, phone, school_id, class_id, medium, password_hash, user_id))
    else:
        update_db('''
            UPDATE users SET full_name=%s, email=%s, phone=%s, school_id=%s, class_id=%s, medium=%s
            WHERE id=%s
        ''', (full_name, email, phone, school_id, class_id, medium, user_id))

    flash('User updated successfully!', 'success')
    return redirect(request.referrer or url_for('state_admin.dashboard'))


@state_admin_bp.route('/toggle-user/<int:user_id>', methods=['POST'])
@login_required(role='state_admin')
def toggle_user(user_id):
    user = query_db('SELECT is_active, user_type FROM users WHERE id=%s', (user_id,), one=True)
    if user:
        new_state = not user['is_active']
        update_db('UPDATE users SET is_active=%s WHERE id=%s', (new_state, user_id))
        status_label = 'activated' if new_state else 'deactivated'
        flash(f'User {status_label} successfully!', 'success')
    return redirect(request.referrer or url_for('state_admin.dashboard'))


@state_admin_bp.route('/delete-user/<int:user_id>', methods=['POST'])
@login_required(role='state_admin')
def delete_user(user_id):
    referrer = request.referrer or url_for('state_admin.dashboard')
    try:
        update_db('DELETE FROM users WHERE id=%s', (user_id,))
        flash('User deleted successfully!', 'success')
    except Exception as e:
        flash(f'Cannot delete user: related records still exist. Error: {str(e)[:120]}', 'error')
    return redirect(referrer)

# ---------------------------------------------------------------------------
# Question Setters — Create / List / (Edit & Toggle reuse /edit-user & /toggle-user)
# ---------------------------------------------------------------------------

@state_admin_bp.route('/create-question-setter', methods=['GET', 'POST'])
@login_required(role='state_admin')
def create_question_setter():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        full_name = request.form['full_name']
        email = request.form.get('email', '')
        phone = request.form.get('phone', '')

        existing = query_db('SELECT id FROM users WHERE username=%s', (username,), one=True)
        if existing:
            flash('Username already exists. Please choose another.', 'error')
            return redirect(url_for('state_admin.create_question_setter'))

        password_hash = generate_password_hash(password)

        insert_db('''
            INSERT INTO users (username, password_hash, full_name, email, phone, user_type, created_by)
            VALUES (%s, %s, %s, %s, %s, 'question_setter', %s)
        ''', (username, password_hash, full_name, email, phone, session['user_id']))

        flash('Question Setter created successfully!', 'success')
        return redirect(url_for('state_admin.create_question_setter'))

    setters = query_db('''
        SELECT * FROM users
        WHERE user_type = 'question_setter'
        ORDER BY created_at DESC
    ''')
    return render_template('state_admin/create_question_setter.html', setters=setters)
    
# ---------------------------------------------------------------------------
# Revaluators — Create / List
# ---------------------------------------------------------------------------

@state_admin_bp.route('/manage-revaluators', methods=['GET', 'POST'])
@login_required(role='state_admin')
def manage_revaluators():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        full_name = request.form['full_name']
        email = request.form.get('email', '')
        phone = request.form.get('phone', '')

        existing = query_db('SELECT id FROM users WHERE username=%s', (username,), one=True)
        if existing:
            flash('Username already exists. Please choose another.', 'error')
            return redirect(url_for('state_admin.manage_revaluators'))

        password_hash = generate_password_hash(password)

        insert_db('''
            INSERT INTO users (username, password_hash, full_name, email, phone, user_type, created_by)
            VALUES (%s, %s, %s, %s, %s, 'revaluator', %s)
        ''', (username, password_hash, full_name, email, phone, session['user_id']))

        flash('Revaluator created successfully!', 'success')
        return redirect(url_for('state_admin.manage_revaluators'))

    revaluators = query_db('''
        SELECT * FROM users
        WHERE user_type = 'revaluator'
        ORDER BY created_at DESC
    ''')
    return render_template('state_admin/manage_revaluators.html', revaluators=revaluators)

# ---------------------------------------------------------------------------
# Students — Create / List / Bulk Upload / (Edit & Toggle reuse shared routes)
# ---------------------------------------------------------------------------

@state_admin_bp.route('/manage-students', methods=['GET', 'POST'])
@login_required(role='state_admin')
def manage_students():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        full_name = request.form['full_name']
        school_id = request.form['school_id']
        class_id = request.form.get('class_id') or None
        email = request.form.get('email', '')
        phone = request.form.get('phone', '')

        medium = request.form.get('medium', 'English')

        existing = query_db('SELECT id FROM users WHERE username=%s', (username,), one=True)
        if existing:
            flash('Username already exists.', 'error')
            return redirect(url_for('state_admin.manage_students'))

        password_hash = generate_password_hash(password)

        insert_db('''
            INSERT INTO users (username, password_hash, full_name, email, phone, user_type, school_id, class_id, medium, created_by)
            VALUES (%s, %s, %s, %s, %s, 'student', %s, %s, %s, %s)
        ''', (username, password_hash, full_name, email, phone, school_id, class_id, medium, session['user_id']))

        flash('Student added successfully!', 'success')
        return redirect(url_for('state_admin.manage_students'))

    schools = query_db('SELECT * FROM schools ORDER BY school_name')
    classes = query_db('SELECT * FROM classes ORDER BY class_name')
    students = query_db('''
        SELECT u.*, s.school_name, c.class_name
        FROM users u
        JOIN schools s ON u.school_id = s.id
        LEFT JOIN classes c ON u.class_id = c.id
        WHERE u.user_type = 'student'
        ORDER BY u.created_at DESC
    ''')
    return render_template('state_admin/manage_students.html', schools=schools, students=students, classes=classes)


@state_admin_bp.route('/bulk-upload-students', methods=['POST'])
@login_required(role='state_admin')
def bulk_upload_students():
    if 'csv_file' not in request.files:
        flash('No file provided', 'error')
        return redirect(url_for('state_admin.manage_students'))

    file = request.files['csv_file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('state_admin.manage_students'))

    if not file.filename.endswith('.csv'):
        flash('Please upload a CSV file', 'error')
        return redirect(url_for('state_admin.manage_students'))

    try:
        stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)

        sample = stream.readline()
        stream.seek(0)
        has_header = 'school_code' in sample.lower() or 'register_number' in sample.lower()

        success_count = 0
        error_count = 0

        rows = []
        if has_header:
            csv_input = csv.DictReader(stream, skipinitialspace=True)
            for r in csv_input:
                r_clean = {str(k).strip().lower() if k else '': v for k, v in r.items()}
                rows.append({
                    'school_code': r_clean.get('school_code', ''),
                    'register_number': r_clean.get('register_number', ''),
                    'full_name': r_clean.get('full_name', ''),
                    'email': r_clean.get('email', ''),
                    'phone': r_clean.get('phone', ''),
                    'password': r_clean.get('password', ''),
                    'class_name': r_clean.get('class_name', ''),
                    'medium': r_clean.get('medium', 'English')
                })
        else:
            csv_input = csv.reader(stream, skipinitialspace=True)
            for r in csv_input:
                if not r or len(r) == 0 or (len(r) == 1 and not r[0].strip()):
                    continue
                if len(r) >= 3:
                    rows.append({
                        'school_code': r[0],
                        'register_number': r[1],
                        'full_name': r[2],
                        'email': r[3] if len(r) > 3 else '',
                        'phone': r[4] if len(r) > 4 else '',
                        'password': r[5] if len(r) > 5 else '',
                        'class_name': r[6] if len(r) > 6 else '',
                        'medium': r[7] if len(r) > 7 else 'English'
                    })
                else:
                    error_count += 1

        for row in rows:
            school_code = str(row.get('school_code') or '').strip()
            username = str(row.get('register_number') or '').strip()
            full_name = str(row.get('full_name') or '').strip()
            email = str(row.get('email') or '').strip()
            phone = str(row.get('phone') or '').strip()
            password = str(row.get('password') or '').strip()
            class_name_csv = str(row.get('class_name') or '').strip()

            if not password:
                password = username

            if not all([school_code, username, full_name]):
                error_count += 1
                continue

            school = query_db('SELECT id FROM schools WHERE school_code = %s', (school_code,), one=True)
            if not school:
                error_count += 1
                continue

            existing = query_db('SELECT id FROM users WHERE username = %s', (username,), one=True)
            if existing:
                error_count += 1
                continue

            # Resolve class_id from class_name if provided
            class_id = None
            if class_name_csv:
                cls = query_db('SELECT id FROM classes WHERE LOWER(class_name) = LOWER(%s)', (class_name_csv,), one=True)
                if cls:
                    class_id = cls['id']

            password_hash = generate_password_hash(password)
            medium = str(row.get('medium') or 'English').strip()

            insert_db('''
                INSERT INTO users (username, password_hash, full_name, email, phone, user_type, school_id, class_id, medium, created_by)
                VALUES (%s, %s, %s, %s, %s, 'student', %s, %s, %s, %s)
            ''', (username, password_hash, full_name, email, phone, school['id'], class_id, medium, session['user_id']))

            success_count += 1

        flash(f'Successfully added {success_count} students. Errors skipped: {error_count}.',
              'success' if success_count > 0 else 'warning')

    except Exception as e:
        flash(f'Error processing file: {str(e)}', 'error')

    return redirect(url_for('state_admin.manage_students'))

# ---------------------------------------------------------------------------
# Examinations — Create / List / Publish / Delete
# ---------------------------------------------------------------------------

@state_admin_bp.route('/get-chapters/<int:subject_id>')
@login_required(role='state_admin')
def get_chapters(subject_id):
    chapters = query_db('SELECT * FROM chapters WHERE subject_id = %s ORDER BY chapter_number', (subject_id,))
    return jsonify([dict(c) for c in chapters])

@state_admin_bp.route('/create-examination', methods=['GET', 'POST'])
@login_required(role='state_admin')
def create_examination():
    if request.method == 'POST':
        exam_name = request.form['exam_name']
        class_id = request.form['class_id']
        subject_id = request.form['subject_id']
        start_date = request.form['start_date']
        end_date = request.form['end_date']
        duration_minutes = request.form['duration_minutes']
        total_theory = request.form['total_theory_questions']
        total_short_answer = request.form.get('total_short_answer_questions', 0)
        total_practical = request.form['total_practical_questions']
        easy_q = request.form.get('easy_questions', 0)
        average_q = request.form.get('average_questions', 0)
        difficult_q = request.form.get('difficult_questions', 0)
        is_multiple = request.form.get('is_multiple_correct_allowed', False)
        max_score = request.form.get('max_score', 0)
        chapters = request.form.getlist('chapters')

        exam_id = insert_db('''
            INSERT INTO examinations
            (exam_name, class_id, subject_id, start_date, end_date, duration_minutes,
             total_theory_questions, total_short_answer_questions, total_practical_questions, 
             easy_questions, average_questions, difficult_questions, 
             is_multiple_correct_allowed, created_by, max_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (exam_name, class_id, subject_id, start_date, end_date, duration_minutes,
              total_theory, total_short_answer, total_practical, easy_q, average_q, difficult_q,
              bool(is_multiple), session['user_id'], max_score))

        for chapter_id in chapters:
            easy = request.form.get(f'easy_count_{chapter_id}', 0)
            avg = request.form.get(f'avg_count_{chapter_id}', 0)
            diff = request.form.get(f'diff_count_{chapter_id}', 0)
            
            insert_db('''
                INSERT INTO exam_chapters (exam_id, chapter_id, easy_count, average_count, difficult_count)
                VALUES (%s, %s, %s, %s, %s)
            ''', (exam_id, chapter_id, easy, avg, diff))

        # Handle custom chapters
        custom_chapter_names = request.form.getlist('custom_chapter_names[]')
        custom_chapter_ids = request.form.getlist('custom_chapter_ids[]')
        custom_chapters_check = request.form.getlist('custom_chapters_check[]')
        
        for idx_str in custom_chapters_check:
            try:
                idx = int(idx_str)
                list_idx = custom_chapter_ids.index(str(idx))
                name = custom_chapter_names[list_idx]
                
                if not name.strip():
                    continue
                    
                # Insert into chapters table
                new_ch_id = insert_db('''
                    INSERT INTO chapters (subject_id, chapter_name, chapter_number)
                    VALUES (%s, %s, (SELECT COALESCE(MAX(chapter_number), 0) + 1 FROM chapters WHERE subject_id = %s))
                    RETURNING id
                ''', (subject_id, name.strip(), subject_id))
                
                # Get counts
                easy = request.form.get(f'custom_easy_count_{idx}', 0)
                avg = request.form.get(f'custom_avg_count_{idx}', 0)
                diff = request.form.get(f'custom_diff_count_{idx}', 0)
                
                insert_db('''
                    INSERT INTO exam_chapters (exam_id, chapter_id, easy_count, average_count, difficult_count)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (exam_id, new_ch_id, easy, avg, diff))
            except (ValueError, IndexError):
                continue

        flash('Examination created successfully!', 'success')
        return redirect(url_for('state_admin.create_examination'))

    classes = query_db('SELECT * FROM classes ORDER BY class_name')
    subjects = query_db('SELECT * FROM subjects ORDER BY subject_name')

    exams = query_db('''
        SELECT e.*, c.class_name, s.subject_name
        FROM examinations e
        JOIN classes c ON e.class_id = c.id
        JOIN subjects s ON e.subject_id = s.id
        ORDER BY e.created_at DESC
    ''')

    return render_template('state_admin/create_examination.html',
                           classes=classes, subjects=subjects, exams=exams)


@state_admin_bp.route('/edit-examination/<int:exam_id>', methods=['GET', 'POST'])
@login_required(role='state_admin')
def edit_examination(exam_id):
    exam = query_db('SELECT * FROM examinations WHERE id = %s', (exam_id,), one=True)
    if not exam:
        flash('Examination not found.', 'error')
        return redirect(url_for('state_admin.create_examination'))
    
    if exam['status'] != 'draft':
        flash('Only draft examinations can be edited.', 'error')
        return redirect(url_for('state_admin.create_examination'))

    if request.method == 'POST':
        exam_name = request.form['exam_name']
        class_id = request.form['class_id']
        subject_id = request.form['subject_id']
        start_date = request.form['start_date']
        end_date = request.form['end_date']
        duration_minutes = request.form['duration_minutes']
        total_theory = request.form['total_theory_questions']
        total_short_answer = request.form.get('total_short_answer_questions', 0)
        total_practical = request.form['total_practical_questions']
        easy_q = request.form.get('easy_questions', 0)
        average_q = request.form.get('average_questions', 0)
        difficult_q = request.form.get('difficult_questions', 0)
        is_multiple = request.form.get('is_multiple_correct_allowed', False)
        max_score = request.form.get('max_score', 0)
        chapters = request.form.getlist('chapters')

        update_db('''
            UPDATE examinations SET
            exam_name=%s, class_id=%s, subject_id=%s, start_date=%s, end_date=%s, duration_minutes=%s,
            total_theory_questions=%s, total_short_answer_questions=%s, total_practical_questions=%s, 
            easy_questions=%s, average_questions=%s, difficult_questions=%s, 
            is_multiple_correct_allowed=%s, max_score=%s
            WHERE id=%s
        ''', (exam_name, class_id, subject_id, start_date, end_date, duration_minutes,
              total_theory, total_short_answer, total_practical, easy_q, average_q, difficult_q,
              bool(is_multiple), max_score, exam_id))

        # Clear and re-add chapters
        update_db('DELETE FROM exam_chapters WHERE exam_id = %s', (exam_id,))
        
        for chapter_id in chapters:
            easy = request.form.get(f'easy_count_{chapter_id}', 0)
            avg = request.form.get(f'avg_count_{chapter_id}', 0)
            diff = request.form.get(f'diff_count_{chapter_id}', 0)
            
            insert_db('''
                INSERT INTO exam_chapters (exam_id, chapter_id, easy_count, average_count, difficult_count)
                VALUES (%s, %s, %s, %s, %s)
            ''', (exam_id, chapter_id, easy, avg, diff))

        # Handle custom chapters
        custom_chapter_names = request.form.getlist('custom_chapter_names[]')
        custom_chapter_ids = request.form.getlist('custom_chapter_ids[]')
        custom_chapters_check = request.form.getlist('custom_chapters_check[]')
        
        for idx_str in custom_chapters_check:
            try:
                idx = int(idx_str)
                list_idx = custom_chapter_ids.index(str(idx))
                name = custom_chapter_names[list_idx]
                
                if not name.strip():
                    continue
                    
                new_ch_id = insert_db('''
                    INSERT INTO chapters (subject_id, chapter_name, chapter_number)
                    VALUES (%s, %s, (SELECT COALESCE(MAX(chapter_number), 0) + 1 FROM chapters WHERE subject_id = %s))
                    RETURNING id
                ''', (subject_id, name.strip(), subject_id))
                
                easy = request.form.get(f'custom_easy_count_{idx}', 0)
                avg = request.form.get(f'custom_avg_count_{idx}', 0)
                diff = request.form.get(f'custom_diff_count_{idx}', 0)
                
                insert_db('''
                    INSERT INTO exam_chapters (exam_id, chapter_id, easy_count, average_count, difficult_count)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (exam_id, new_ch_id, easy, avg, diff))
            except (ValueError, IndexError):
                continue

        flash('Examination updated successfully!', 'success')
        return redirect(url_for('state_admin.create_examination'))

    classes = query_db('SELECT * FROM classes ORDER BY class_name')
    subjects = query_db('SELECT * FROM subjects ORDER BY subject_name')
    
    # Fetch assigned chapters for this exam
    assigned_chapters = query_db('''
        SELECT ec.*, c.chapter_name, c.chapter_number
        FROM exam_chapters ec
        JOIN chapters c ON ec.chapter_id = c.id
        WHERE ec.exam_id = %s
    ''', (exam_id,))

    return render_template('state_admin/edit_examination.html',
                           exam=exam, classes=classes, subjects=subjects,
                           assigned_chapters=assigned_chapters)


@state_admin_bp.route('/publish-examination/<int:exam_id>', methods=['POST'])
@login_required(role='state_admin')
def publish_examination(exam_id):
    update_db("UPDATE examinations SET status = 'published' WHERE id = %s", (exam_id,))
    flash('Examination published successfully!', 'success')
    return redirect(url_for('state_admin.create_examination'))


@state_admin_bp.route('/delete-examination/<int:exam_id>', methods=['POST'])
@login_required(role='state_admin')
def delete_examination(exam_id):
    try:
        update_db("DELETE FROM examinations WHERE id = %s", (exam_id,))
        flash('Examination deleted successfully!', 'success')
    except Exception as e:
        flash(f'Cannot delete examination: related data still exists. Error: {str(e)[:120]}', 'error')
    return redirect(url_for('state_admin.create_examination'))

# ---------------------------------------------------------------------------
# Exam Questions Management (Admin View)
# ---------------------------------------------------------------------------

@state_admin_bp.route('/exam-questions/<int:exam_id>')
@login_required(role='state_admin')
def exam_questions(exam_id):
    exam = query_db('''
        SELECT e.*, c.class_name, s.subject_name
        FROM examinations e
        JOIN classes c ON e.class_id = c.id
        JOIN subjects s ON e.subject_id = s.id
        WHERE e.id = %s
    ''', (exam_id,), one=True)

    if not exam:
        flash('Examination not found.', 'error')
        return redirect(url_for('state_admin.create_examination'))

    questions = query_db('''
        SELECT q.*, u.full_name as setter_name
        FROM questions q
        LEFT JOIN users u ON q.uploaded_by = u.id
        WHERE q.exam_id = %s
        ORDER BY q.question_type, q.created_at
    ''', (exam_id,))

    # Attach options to each question
    questions_with_opts = []
    for q in questions:
        q_dict = dict(q)
        q_dict['has_image'] = bool(q_dict.get('image_blob'))
        q_dict.pop('image_blob', None)  # strip blob from template context
        opts = query_db(
            'SELECT * FROM question_options WHERE question_id=%s ORDER BY option_order',
            (q['id'],)
        )
        q_dict['options'] = [dict(o) for o in opts]
        questions_with_opts.append(q_dict)

    theory_count = sum(1 for q in questions_with_opts if q['question_type'] in ['theory', 'short_answer'])
    practical_count = sum(1 for q in questions_with_opts if q['question_type'] == 'practical')

    return render_template('state_admin/exam_questions.html',
                           exam=exam,
                           questions=questions_with_opts,
                           theory_count=theory_count,
                           practical_count=practical_count)


ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def _allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


@state_admin_bp.route('/edit-question/<int:question_id>', methods=['GET', 'POST'])
@login_required(role='state_admin')
def edit_question(question_id):
    question = query_db('SELECT * FROM questions WHERE id=%s', (question_id,), one=True)
    if not question:
        flash('Question not found.', 'error')
        return redirect(url_for('state_admin.create_examination'))

    if request.method == 'POST':
        question_text = request.form.get('question_text', '')
        value_points = request.form.get('value_points', '')
        difficulty_level = request.form['difficulty_level']
        max_score = request.form['max_score']
        remove_image = request.form.get('remove_image') == '1'
        remove_resource = request.form.get('remove_resource') == '1'

        # --- Handle image ---
        new_image_blob = None
        new_image_mimetype = None
        image_changed = False

        uploaded_file = request.files.get('question_image')
        if uploaded_file and uploaded_file.filename and _allowed_image(uploaded_file.filename):
            from app.utils.crypto import encrypt_data
            file_data = uploaded_file.read()
            new_image_blob = encrypt_data(file_data)
            new_image_mimetype = uploaded_file.mimetype
            image_changed = True
        elif remove_image:
            # Explicitly clear the image
            new_image_blob = None
            new_image_mimetype = None
            image_changed = True

        # --- Handle resource file ---
        new_resource_blob = None
        new_resource_mimetype = None
        new_resource_name = None
        resource_changed = False

        uploaded_resource = request.files.get('resource_file')
        if uploaded_resource and uploaded_resource.filename:
            from app.utils.crypto import encrypt_data
            from werkzeug.utils import secure_filename
            rfile_data = uploaded_resource.read()
            new_resource_blob = encrypt_data(rfile_data)
            new_resource_mimetype = uploaded_resource.mimetype
            new_resource_name = secure_filename(uploaded_resource.filename)
            resource_changed = True
        elif remove_resource:
            new_resource_blob = None
            new_resource_mimetype = None
            new_resource_name = None
            resource_changed = True

        language = request.form.get('language', 'English')

        # Construct dynamic update query based on what changed
        fields = ["question_text=%s", "value_points=%s", "difficulty_level=%s", "max_score=%s", "language=%s"]
        params = [question_text, value_points, difficulty_level, max_score, language]

        if image_changed:
            fields.append("image_blob=%s")
            fields.append("image_mimetype=%s")
            params.extend([new_image_blob, new_image_mimetype])
        
        if resource_changed:
            fields.append("resource_file_blob=%s")
            fields.append("resource_file_mimetype=%s")
            fields.append("resource_file_name=%s")
            params.extend([new_resource_blob, new_resource_mimetype, new_resource_name])

        params.append(question_id)
        query = f"UPDATE questions SET {', '.join(fields)} WHERE id=%s"
        update_db(query, tuple(params))

        # --- Update MCQ options for theory/short_answer questions ---
        if question['question_type'] in ['theory', 'short_answer']:
            options = request.form.getlist('options[]')
            correct_answers = request.form.getlist('correct_answers[]')
            
            update_db('DELETE FROM question_options WHERE question_id=%s', (question_id,))
            
            option_labels = ['A', 'B', 'C', 'D', 'E', 'F']
            for i, option_text in enumerate(options):
                if option_text.strip():
                    insert_db('''
                        INSERT INTO question_options (question_id, option_text, is_correct, option_order)
                        VALUES (%s, %s, %s, %s)
                    ''', (question_id, option_text.strip(), str(i) in correct_answers, option_labels[i]))

        flash('Question updated successfully!', 'success')
        return redirect(url_for('state_admin.exam_questions', exam_id=question['exam_id']))

    options = query_db(
        'SELECT * FROM question_options WHERE question_id=%s ORDER BY option_order',
        (question_id,)
    )
    q_dict = dict(question)
    q_dict['has_image'] = bool(q_dict.get('image_blob'))
    q_dict['has_resource'] = bool(q_dict.get('resource_file_blob'))
    q_dict['resource_name'] = q_dict.get('resource_file_name')
    q_dict.pop('image_blob', None)
    q_dict.pop('resource_file_blob', None)

    return render_template('state_admin/edit_question.html',
                           question=q_dict,
                           options=[dict(o) for o in options])


@state_admin_bp.route('/toggle-question/<int:question_id>', methods=['POST'])
@login_required(role='state_admin')
def toggle_question(question_id):
    question = query_db('SELECT status, exam_id FROM questions WHERE id=%s', (question_id,), one=True)
    if question:
        new_status = 'inactive' if (question['status'] or 'active') == 'active' else 'active'
        update_db('UPDATE questions SET status=%s WHERE id=%s', (new_status, question_id))
        label = 'activated' if new_status == 'active' else 'deactivated'
        flash(f'Question {label} successfully!', 'success')
        return redirect(url_for('state_admin.exam_questions', exam_id=question['exam_id']))
    flash('Question not found.', 'error')
    return redirect(url_for('state_admin.create_examination'))


@state_admin_bp.route('/admin-delete-question/<int:question_id>', methods=['POST'])
@login_required(role='state_admin')
def admin_delete_question(question_id):
    question = query_db('SELECT exam_id FROM questions WHERE id=%s', (question_id,), one=True)
    if not question:
        flash('Question not found.', 'error')
        return redirect(url_for('state_admin.create_examination'))

    exam_id = question['exam_id']
    try:
        update_db('DELETE FROM questions WHERE id=%s', (question_id,))
        flash('Question deleted successfully!', 'success')
    except Exception as e:
        flash(f'Cannot delete question: it may have been answered by students or have related data. Error: {str(e)[:120]}', 'error')
    return redirect(url_for('state_admin.exam_questions', exam_id=exam_id))

# ---------------------------------------------------------------------------
# Assign Students to Exam
# ---------------------------------------------------------------------------

@state_admin_bp.route('/assign-students-exam', methods=['GET', 'POST'])
@login_required(role='state_admin')
def assign_students_exam():
    if request.method == 'POST':
        exam_id = request.form['exam_id']
        school_id = request.form['school_id']

        # Fetch the exam's class_id so we only assign matching-class students
        exam = query_db('SELECT class_id FROM examinations WHERE id=%s', (exam_id,), one=True)
        if not exam:
            flash('Examination not found.', 'error')
            return redirect(url_for('state_admin.assign_students_exam'))

        exam_class_id = exam['class_id']

        # Only students whose class matches the exam's class
        students = query_db('''
            SELECT id FROM users
            WHERE user_type='student' AND school_id=%s AND class_id=%s
        ''', (school_id, exam_class_id))

        assigned_count = 0
        for student in students:
            existing = query_db('''
                SELECT id FROM student_exams
                WHERE student_id=%s AND exam_id=%s
            ''', (student['id'], exam_id), one=True)

            if not existing:
                insert_db('''
                    INSERT INTO student_exams (student_id, exam_id, school_id)
                    VALUES (%s, %s, %s)
                ''', (student['id'], exam_id, school_id))
                assigned_count += 1

        if assigned_count > 0:
            flash(f'{assigned_count} student(s) from the matching class assigned to the examination.', 'success')
        else:
            flash('No eligible students found (no students in this school match the exam\'s class, or all are already assigned).', 'warning')
        return redirect(url_for('state_admin.assign_students_exam'))

    exams = query_db('''
        SELECT e.*, c.class_name
        FROM examinations e
        LEFT JOIN classes c ON e.class_id = c.id
        WHERE e.status IN ('draft', 'published')
        ORDER BY e.exam_name
    ''')
    schools = query_db('SELECT * FROM schools ORDER BY school_name')
    return render_template('state_admin/assign_students_exam.html', exams=exams, schools=schools)

# ---------------------------------------------------------------------------
# Assign Revaluators to Exam
# ---------------------------------------------------------------------------

@state_admin_bp.route('/assign-revaluators', methods=['GET', 'POST'])
@login_required(role='state_admin')
def assign_revaluators():
    if request.method == 'POST':
        exam_id = request.form.get('exam_id')
        revaluator_ids = request.form.getlist('revaluators')
        
        # Clear existing assignments for this exam
        update_db('DELETE FROM revaluator_assignments WHERE exam_id = %s', (exam_id,))
        
        # Add new assignments
        for rev_id in revaluator_ids:
            insert_db('INSERT INTO revaluator_assignments (exam_id, user_id) VALUES (%s, %s)',
                      (exam_id, rev_id))
        
        flash('Revaluator assignments updated successfully!', 'success')
        return redirect(url_for('state_admin.assign_revaluators'))

    # Fetch exams with their assigned revaluators
    exams_raw = query_db('''
        SELECT e.*, c.class_name, s.subject_name,
               STRING_AGG(u.full_name, ', ') as assigned_revaluators,
               ARRAY_AGG(u.id) as assigned_ids
        FROM examinations e
        JOIN classes c ON e.class_id = c.id
        JOIN subjects s ON e.subject_id = s.id
        LEFT JOIN revaluator_assignments ra ON e.id = ra.exam_id
        LEFT JOIN users u ON ra.user_id = u.id
        GROUP BY e.id, c.class_name, s.subject_name
        ORDER BY e.created_at DESC
    ''')
    
    # Process assigned_ids to handle potential [None] or nulls from ARRAY_AGG on empty join
    exams = []
    for exam in exams_raw:
        e_dict = dict(exam)
        # ARRAY_AGG with LEFT JOIN returns [None] if no rows match
        if e_dict['assigned_ids'] == [None]:
            e_dict['assigned_ids'] = []
        exams.append(e_dict)
    
    # Fetch all revaluators
    revaluators = query_db("SELECT * FROM users WHERE user_type='revaluator' ORDER BY full_name")
    
    return render_template('state_admin/assign_revaluators.html', exams=exams, revaluators=revaluators)


@state_admin_bp.route('/select-students-revaluation/<int:exam_id>', methods=['GET', 'POST'])
@login_required(role='state_admin')
def select_students_revaluation(exam_id):
    exam = query_db('SELECT * FROM examinations WHERE id = %s', (exam_id,), one=True)
    if not exam:
        flash('Examination not found.', 'error')
        return redirect(url_for('state_admin.assign_revaluators'))
    
    if request.method == 'POST':
        student_exam_ids = request.form.getlist('student_exam_ids')
        
        # Reset all for this exam
        update_db('''
            UPDATE student_practical_submissions 
            SET needs_revaluation = FALSE 
            WHERE student_exam_id IN (SELECT id FROM student_exams WHERE exam_id = %s)
        ''', (exam_id,))
        
        if student_exam_ids:
            # Set selected
            placeholders = ', '.join(['%s'] * len(student_exam_ids))
            update_db(f'''
                UPDATE student_practical_submissions 
                SET needs_revaluation = TRUE 
                WHERE student_exam_id IN ({placeholders})
            ''', tuple(student_exam_ids))
            
        flash(f'Successfully updated revaluation list for {exam["exam_name"]}.', 'success')
        return redirect(url_for('state_admin.assign_revaluators'))

    # Get students who have practical submissions
    students = query_db('''
        SELECT u.full_name, u.username, se.id as student_exam_id, s.school_name,
               bool_or(sps.needs_revaluation) as is_selected,
               COUNT(sps.id) as submission_count,
               SUM(CASE WHEN sps.score_obtained IS NOT NULL THEN 1 ELSE 0 END) as evaluated_count
        FROM student_exams se
        JOIN users u ON se.student_id = u.id
        JOIN schools s ON se.school_id = s.id
        LEFT JOIN student_practical_submissions sps ON se.id = sps.student_exam_id
        WHERE se.exam_id = %s
        GROUP BY u.id, u.full_name, u.username, se.id, s.school_name
        HAVING COUNT(sps.id) > 0
        ORDER BY s.school_name, u.full_name
    ''', (exam_id,))

    return render_template('state_admin/select_students_revaluation.html', 
                           exam=exam, students=students)


@state_admin_bp.route('/assign-question-setters', methods=['GET', 'POST'])
@login_required(role='state_admin')
def assign_question_setters():
    if request.method == 'POST':
        exam_id = request.form.get('exam_id')
        setter_ids = request.form.getlist('setters')
        
        # Clear existing assignments for this exam
        update_db('DELETE FROM question_setter_assignments WHERE exam_id = %s', (exam_id,))
        
        # Add new assignments
        for setter_id in setter_ids:
            insert_db('INSERT INTO question_setter_assignments (exam_id, user_id) VALUES (%s, %s)',
                      (exam_id, setter_id))
        
        flash('Question setter assignments updated successfully!', 'success')
        return redirect(url_for('state_admin.assign_question_setters'))

    # Fetch exams with their assigned question setters
    exams_raw = query_db('''
        SELECT e.*, c.class_name, s.subject_name,
               STRING_AGG(u.full_name, ', ') as assigned_setters,
               ARRAY_AGG(u.id) as assigned_ids
        FROM examinations e
        JOIN classes c ON e.class_id = c.id
        JOIN subjects s ON e.subject_id = s.id
        LEFT JOIN question_setter_assignments qsa ON e.id = qsa.exam_id
        LEFT JOIN users u ON qsa.user_id = u.id
        GROUP BY e.id, c.class_name, s.subject_name
        ORDER BY e.created_at DESC
    ''')
    
    # Process assigned_ids to handle potential [None] or nulls from ARRAY_AGG on empty join
    exams = []
    for exam in exams_raw:
        e_dict = dict(exam)
        # ARRAY_AGG with LEFT JOIN returns [None] if no rows match
        if e_dict['assigned_ids'] == [None]:
            e_dict['assigned_ids'] = []
        exams.append(e_dict)
    
    # Fetch all question setters
    setters = query_db("SELECT * FROM users WHERE user_type='question_setter' ORDER BY full_name")
    
    return render_template('state_admin/assign_question_setters.html', exams=exams, setters=setters)

# ---------------------------------------------------------------------------
# Reports & Mark List
# ---------------------------------------------------------------------------

@state_admin_bp.route('/reports')
@login_required(role='state_admin')
def reports():
    exam_id = request.args.get('exam_id')
    school_id = request.args.get('school_id')
    
    exams = query_db('SELECT id, exam_name FROM examinations ORDER BY created_at DESC')
    schools = query_db('SELECT id, school_name FROM schools ORDER BY school_name')
    
    school_reports = []
    totals = None
    
    if exam_id:
        query = '''
            SELECT 
                s.school_name,
                COUNT(se.id) as registered,
                SUM(CASE WHEN se.theory_status = 'completed' AND se.practical_status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE 
                    WHEN (se.theory_status = 'completed' AND se.practical_status = 'completed') THEN 0
                    WHEN (se.theory_status = 'pending' AND se.practical_status = 'pending') THEN 0
                    ELSE 1 
                END) as ongoing,
                SUM(CASE WHEN se.theory_status = 'completed' AND se.practical_status = 'completed' AND ml.status = 'finalized' THEN 1 ELSE 0 END) as evaluation_completed,
                AVG(ml.total_score) as avg_score
            FROM schools s
            JOIN student_exams se ON s.id = se.school_id
            LEFT JOIN mark_lists ml ON se.id = ml.student_exam_id
            WHERE se.exam_id = %s
        '''
        params = [exam_id]
        
        if school_id:
            query += ' AND s.id = %s'
            params.append(school_id)
            
        query += ' GROUP BY s.id, s.school_name ORDER BY s.school_name'
        
        school_reports = query_db(query, params)
        
        if school_reports:
            totals = {
                'registered': sum(r['registered'] or 0 for r in school_reports),
                'completed': sum(r['completed'] or 0 for r in school_reports),
                'ongoing': sum(r['ongoing'] or 0 for r in school_reports),
                'evaluation_completed': sum(r['evaluation_completed'] or 0 for r in school_reports),
                'avg_score': (sum(r['avg_score'] or 0 for r in school_reports) / len([r for r in school_reports if r['avg_score'] is not None])) if any(r['avg_score'] is not None for r in school_reports) else 0
            }

    return render_template('state_admin/reports.html', 
                           school_reports=school_reports, 
                           exams=exams, 
                           schools=schools,
                           selected_exam_id=int(exam_id) if exam_id else None,
                           selected_school_id=int(school_id) if school_id else None,
                           totals=totals)


@state_admin_bp.route('/revaluation-report')
@login_required(role='state_admin')
def revaluation_report():
    exam_id = request.args.get('exam_id')
    
    exams = query_db('SELECT id, exam_name FROM examinations ORDER BY created_at DESC')
    
    query = '''
        SELECT sps.*, 
               u.full_name as student_name, u.username as student_reg,
               e.exam_name, q.question_text,
               eval.full_name as invigilator_name,
               rev.full_name as revaluator_name
        FROM student_practical_submissions sps
        JOIN student_exams se ON sps.student_exam_id = se.id
        JOIN users u ON se.student_id = u.id
        JOIN examinations e ON se.exam_id = e.id
        JOIN questions q ON sps.question_id = q.id
        LEFT JOIN users eval ON sps.evaluated_by = eval.id
        LEFT JOIN users rev ON sps.revaluated_by = rev.id
        WHERE sps.revaluated_by IS NOT NULL
    '''
    params = []
    
    if exam_id:
        query += ' AND e.id = %s'
        params.append(exam_id)
        
    query += ' ORDER BY sps.revaluation_time DESC'
    
    revaluations = query_db(query, params)
    
    return render_template('state_admin/revaluation_report.html', 
                         revaluations=revaluations, 
                         exams=exams, 
                         selected_exam=exam_id)


# ---------------------------------------------------------------------------
# Exam Result Analysis
# ---------------------------------------------------------------------------

@state_admin_bp.route('/exam-analysis/<int:exam_id>')
@login_required(role='state_admin')
def exam_analysis(exam_id):
    import json
    from decimal import Decimal

    # Helper to make Decimal JSON-serializable
    def dec(val):
        if val is None:
            return 0
        return float(val)

    # ── Exam info ──────────────────────────────────────────────────────────
    exam = query_db('''
        SELECT e.*, c.class_name, s.subject_name
        FROM examinations e
        JOIN classes c ON e.class_id = c.id
        JOIN subjects s ON e.subject_id = s.id
        WHERE e.id = %s
    ''', (exam_id,), one=True)

    if not exam:
        flash('Examination not found.', 'error')
        return redirect(url_for('state_admin.create_examination'))

    max_score = dec(exam['max_score']) or 1  # avoid division by zero

    # ── Overview stats ─────────────────────────────────────────────────────
    overview = query_db('''
        SELECT
            COUNT(se.id) as total_students,
            SUM(CASE WHEN se.theory_status = 'completed' AND se.practical_status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN se.theory_status = 'pending' AND se.practical_status = 'pending' THEN 1 ELSE 0 END) as not_started
        FROM student_exams se
        WHERE se.exam_id = %s
    ''', (exam_id,), one=True)

    mark_stats = query_db('''
        SELECT
            COUNT(ml.id) as graded_count,
            AVG(ml.total_score) as avg_score,
            AVG(ml.percentage) as avg_percentage,
            MAX(ml.total_score) as highest_score,
            MIN(ml.total_score) as lowest_score,
            SUM(CASE WHEN ml.percentage >= 40 THEN 1 ELSE 0 END) as pass_count,
            SUM(CASE WHEN ml.percentage < 40 THEN 1 ELSE 0 END) as fail_count
        FROM mark_lists ml
        JOIN student_exams se ON ml.student_exam_id = se.id
        WHERE se.exam_id = %s
    ''', (exam_id,), one=True)

    # Median score
    median_row = query_db('''
        SELECT ml.total_score
        FROM mark_lists ml
        JOIN student_exams se ON ml.student_exam_id = se.id
        WHERE se.exam_id = %s
        ORDER BY ml.total_score
        LIMIT 1 OFFSET (
            SELECT COUNT(*) / 2 FROM mark_lists ml2
            JOIN student_exams se2 ON ml2.student_exam_id = se2.id
            WHERE se2.exam_id = %s
        )
    ''', (exam_id, exam_id), one=True)

    stats = {
        'total_students': overview['total_students'] or 0,
        'completed': overview['completed'] or 0,
        'not_started': overview['not_started'] or 0,
        'graded': mark_stats['graded_count'] or 0,
        'avg_score': round(dec(mark_stats['avg_score']), 2),
        'avg_percentage': round(dec(mark_stats['avg_percentage']), 1),
        'highest_score': dec(mark_stats['highest_score']),
        'lowest_score': dec(mark_stats['lowest_score']),
        'median_score': dec(median_row['total_score']) if median_row else 0,
        'pass_count': mark_stats['pass_count'] or 0,
        'fail_count': mark_stats['fail_count'] or 0,
    }
    graded = stats['graded'] or 1
    stats['pass_rate'] = round((stats['pass_count'] / graded) * 100, 1)

    # ── Grade distribution ─────────────────────────────────────────────────
    grade_rows = query_db('''
        SELECT ml.grade, COUNT(*) as cnt
        FROM mark_lists ml
        JOIN student_exams se ON ml.student_exam_id = se.id
        WHERE se.exam_id = %s AND ml.grade IS NOT NULL
        GROUP BY ml.grade
        ORDER BY ml.grade
    ''', (exam_id,))

    grade_dist = {r['grade']: r['cnt'] for r in grade_rows}

    # ── Score histogram (percentage buckets) ───────────────────────────────
    bucket_rows = query_db('''
        SELECT
            CASE
                WHEN ml.percentage < 10 THEN '0-10'
                WHEN ml.percentage < 20 THEN '10-20'
                WHEN ml.percentage < 30 THEN '20-30'
                WHEN ml.percentage < 40 THEN '30-40'
                WHEN ml.percentage < 50 THEN '40-50'
                WHEN ml.percentage < 60 THEN '50-60'
                WHEN ml.percentage < 70 THEN '60-70'
                WHEN ml.percentage < 80 THEN '70-80'
                WHEN ml.percentage < 90 THEN '80-90'
                ELSE '90-100'
            END as bucket,
            COUNT(*) as cnt
        FROM mark_lists ml
        JOIN student_exams se ON ml.student_exam_id = se.id
        WHERE se.exam_id = %s
        GROUP BY bucket
        ORDER BY bucket
    ''', (exam_id,))

    all_buckets = ['0-10','10-20','20-30','30-40','40-50','50-60','60-70','70-80','80-90','90-100']
    bucket_map = {r['bucket']: r['cnt'] for r in bucket_rows}
    score_histogram = {b: bucket_map.get(b, 0) for b in all_buckets}

    # ── School-wise performance ────────────────────────────────────────────
    school_perf = query_db('''
        SELECT
            s.id as school_id, s.school_name,
            COUNT(se.id) as student_count,
            SUM(CASE WHEN se.theory_status = 'completed' AND se.practical_status = 'completed' THEN 1 ELSE 0 END) as completed,
            AVG(ml.total_score) as avg_score,
            AVG(ml.percentage) as avg_percentage,
            MAX(ml.total_score) as highest,
            MIN(ml.total_score) as lowest,
            SUM(CASE WHEN ml.percentage >= 40 THEN 1 ELSE 0 END) as pass_count
        FROM student_exams se
        JOIN schools s ON se.school_id = s.id
        LEFT JOIN mark_lists ml ON se.id = ml.student_exam_id
        WHERE se.exam_id = %s
        GROUP BY s.id, s.school_name
        ORDER BY avg_percentage DESC NULLS LAST
    ''', (exam_id,))

    school_data = []
    for sp in school_perf:
        graded_in_school = sp['pass_count'] or 0
        total_in_school = sp['student_count'] or 1
        completed_in_school = sp['completed'] or 0
        school_data.append({
            'school_name': sp['school_name'],
            'student_count': sp['student_count'] or 0,
            'completed': completed_in_school,
            'avg_score': round(dec(sp['avg_score']), 2),
            'avg_percentage': round(dec(sp['avg_percentage']), 1),
            'highest': dec(sp['highest']),
            'lowest': dec(sp['lowest']),
            'pass_count': graded_in_school,
            'pass_rate': round((graded_in_school / max(completed_in_school, 1)) * 100, 1),
        })

    # School-wise grade breakdown
    school_grade_rows = query_db('''
        SELECT s.school_name, ml.grade, COUNT(*) as cnt
        FROM student_exams se
        JOIN schools s ON se.school_id = s.id
        JOIN mark_lists ml ON se.id = ml.student_exam_id
        WHERE se.exam_id = %s AND ml.grade IS NOT NULL
        GROUP BY s.school_name, ml.grade
        ORDER BY s.school_name, ml.grade
    ''', (exam_id,))

    school_grade_map = {}
    for r in school_grade_rows:
        name = r['school_name']
        if name not in school_grade_map:
            school_grade_map[name] = {}
        school_grade_map[name][r['grade']] = r['cnt']

    # ── Most frequently incorrect questions ────────────────────────────────
    incorrect_qs = query_db('''
        SELECT
            q.id, q.question_text,
            COUNT(sta.id) as total_attempts,
            SUM(CASE WHEN sta.is_correct = FALSE THEN 1 ELSE 0 END) as incorrect_count,
            ROUND(
                SUM(CASE WHEN sta.is_correct = FALSE THEN 1 ELSE 0 END)::numeric
                / NULLIF(COUNT(sta.id), 0) * 100, 1
            ) as incorrect_pct
        FROM student_theory_answers sta
        JOIN questions q ON sta.question_id = q.id
        JOIN student_exams se ON sta.student_exam_id = se.id
        WHERE se.exam_id = %s
        GROUP BY q.id, q.question_text
        HAVING SUM(CASE WHEN sta.is_correct = FALSE THEN 1 ELSE 0 END) > 0
        ORDER BY incorrect_pct DESC, incorrect_count DESC
        LIMIT 15
    ''', (exam_id,))

    incorrect_questions = [{
        'id': q['id'],
        'question_text': (q['question_text'] or 'Image-based Question')[:120],
        'is_image': not bool(q['question_text']),
        'total_attempts': q['total_attempts'],
        'incorrect_count': q['incorrect_count'],
        'incorrect_pct': dec(q['incorrect_pct']),
    } for q in incorrect_qs]

    # ── Most frequently correct questions ──────────────────────────────────
    correct_qs = query_db('''
        SELECT
            q.id, q.question_text,
            COUNT(sta.id) as total_attempts,
            SUM(CASE WHEN sta.is_correct = TRUE THEN 1 ELSE 0 END) as correct_count,
            ROUND(
                SUM(CASE WHEN sta.is_correct = TRUE THEN 1 ELSE 0 END)::numeric
                / NULLIF(COUNT(sta.id), 0) * 100, 1
            ) as correct_pct
        FROM student_theory_answers sta
        JOIN questions q ON sta.question_id = q.id
        JOIN student_exams se ON sta.student_exam_id = se.id
        WHERE se.exam_id = %s
        GROUP BY q.id, q.question_text
        HAVING SUM(CASE WHEN sta.is_correct = TRUE THEN 1 ELSE 0 END) > 0
        ORDER BY correct_pct DESC, correct_count DESC
        LIMIT 15
    ''', (exam_id,))

    correct_questions = [{
        'id': q['id'],
        'question_text': (q['question_text'] or 'Image-based Question')[:120],
        'is_image': not bool(q['question_text']),
        'total_attempts': q['total_attempts'],
        'correct_count': q['correct_count'],
        'correct_pct': dec(q['correct_pct']),
    } for q in correct_qs]

    # ── Difficulty-wise analysis ───────────────────────────────────────────
    difficulty_rows = query_db('''
        SELECT
            q.difficulty_level,
            COUNT(sta.id) as attempts,
            AVG(sta.score_obtained) as avg_obtained,
            AVG(q.max_score) as avg_max
        FROM student_theory_answers sta
        JOIN questions q ON sta.question_id = q.id
        JOIN student_exams se ON sta.student_exam_id = se.id
        WHERE se.exam_id = %s AND q.difficulty_level IS NOT NULL
        GROUP BY q.difficulty_level
    ''', (exam_id,))

    difficulty_data = [{
        'level': r['difficulty_level'],
        'attempts': r['attempts'],
        'avg_obtained': round(dec(r['avg_obtained']), 2),
        'avg_max': round(dec(r['avg_max']), 2),
    } for r in difficulty_rows]

    # ── Chapter-wise performance ───────────────────────────────────────────
    chapter_rows = query_db('''
        SELECT
            ch.chapter_name,
            COUNT(sta.id) as attempts,
            AVG(sta.score_obtained) as avg_obtained,
            AVG(q.max_score) as avg_max
        FROM student_theory_answers sta
        JOIN questions q ON sta.question_id = q.id
        JOIN student_exams se ON sta.student_exam_id = se.id
        LEFT JOIN chapters ch ON q.chapter_id = ch.id
        WHERE se.exam_id = %s AND ch.id IS NOT NULL
        GROUP BY ch.id, ch.chapter_name
        ORDER BY ch.chapter_name
    ''', (exam_id,))

    chapter_data = [{
        'chapter': r['chapter_name'],
        'attempts': r['attempts'],
        'avg_obtained': round(dec(r['avg_obtained']), 2),
        'avg_max': round(dec(r['avg_max']), 2),
    } for r in chapter_rows]

    # ── Practical submission stats ─────────────────────────────────────────
    practical_stats = query_db('''
        SELECT
            COUNT(sps.id) as total_submissions,
            SUM(CASE WHEN sps.score_obtained IS NOT NULL THEN 1 ELSE 0 END) as evaluated,
            AVG(sps.score_obtained) as avg_practical_score
        FROM student_practical_submissions sps
        JOIN student_exams se ON sps.student_exam_id = se.id
        WHERE se.exam_id = %s
    ''', (exam_id,), one=True)

    practical = {
        'total_submissions': practical_stats['total_submissions'] or 0,
        'evaluated': practical_stats['evaluated'] or 0,
        'avg_score': round(dec(practical_stats['avg_practical_score']), 2),
    }

    # ── Serialize for template ─────────────────────────────────────────────
    all_grades = sorted(set(list(grade_dist.keys()) +
                            [g for sg in school_grade_map.values() for g in sg.keys()]))

    return render_template('state_admin/exam_analysis.html',
                           exam=exam,
                           stats=stats,
                           grade_dist=grade_dist,
                           score_histogram=score_histogram,
                           school_data=school_data,
                           school_grade_map=school_grade_map,
                           all_grades=all_grades,
                           incorrect_questions=incorrect_questions,
                           correct_questions=correct_questions,
                           difficulty_data=difficulty_data,
                           chapter_data=chapter_data,
                           practical=practical,
                           # JSON for JS charts
                           grade_dist_json=json.dumps(grade_dist),
                           score_histogram_json=json.dumps(score_histogram),
                           school_data_json=json.dumps(school_data),
                           school_grade_json=json.dumps(school_grade_map),
                           all_grades_json=json.dumps(all_grades),
                           difficulty_json=json.dumps(difficulty_data),
                           chapter_json=json.dumps(chapter_data))


@state_admin_bp.route('/mark-list')
@login_required(role='state_admin')
def mark_list():
    exam_id   = request.args.get('exam_id')
    school_id = request.args.get('school_id')
    class_id  = request.args.get('class_id')

    query = '''
        SELECT u.full_name as student_name, s.school_name, e.exam_name,
               c.class_name,
               ml.theory_score, ml.practical_score, ml.total_score,
               ml.percentage, ml.grade, se.id as student_exam_id
        FROM mark_lists ml
        JOIN student_exams se ON ml.student_exam_id = se.id
        JOIN users u ON se.student_id = u.id
        JOIN schools s ON se.school_id = s.id
        JOIN examinations e ON se.exam_id = e.id
        JOIN classes c ON e.class_id = c.id
        WHERE 1=1
    '''
    params = []

    if exam_id:
        query += ' AND e.id = %s'
        params.append(exam_id)
    if school_id:
        query += ' AND s.id = %s'
        params.append(school_id)
    if class_id:
        query += ' AND e.class_id = %s'
        params.append(class_id)

    query += ' ORDER BY c.class_name, s.school_name, u.full_name'
    results = query_db(query, params)

    exams   = query_db('SELECT * FROM examinations ORDER BY exam_name')
    schools = query_db('SELECT * FROM schools ORDER BY school_name')
    classes = query_db('SELECT * FROM classes ORDER BY class_name')

    return render_template('state_admin/mark_list.html', results=results,
                           exams=exams, schools=schools, classes=classes)

# ---------------------------------------------------------------------------
# Manage Student Status / Reset Exam
# ---------------------------------------------------------------------------

@state_admin_bp.route('/manage-status')
@login_required(role='state_admin')
def manage_status():
    exam_id = request.args.get('exam_id')
    school_id = request.args.get('school_id')
    
    exams = query_db('SELECT id, exam_name FROM examinations ORDER BY created_at DESC')
    schools = query_db('SELECT id, school_name FROM schools ORDER BY school_name')
    
    students = []
    if exam_id and school_id:
        students = query_db('''
            SELECT se.id as student_exam_id, u.full_name, u.username,
                   se.theory_status, se.practical_status
            FROM student_exams se
            JOIN users u ON se.student_id = u.id
            WHERE se.exam_id = %s AND se.school_id = %s
            ORDER BY u.full_name
        ''', (exam_id, school_id))
        
    return render_template('state_admin/manage_status.html',
                           exams=exams, schools=schools, students=students,
                           selected_exam_id=int(exam_id) if exam_id else None,
                           selected_school_id=int(school_id) if school_id else None)

@state_admin_bp.route('/reset-exam-status', methods=['POST'])
@login_required(role='state_admin')
def reset_exam_status():
    student_exam_id = request.form.get('student_exam_id')
    
    if not student_exam_id:
        flash('No student selected.', 'error')
        return redirect(request.referrer or url_for('state_admin.manage_status'))
        
    # Start resetting
    try:
        # 1. Update student_exams
        update_db('''
            UPDATE student_exams 
            SET theory_status = 'pending', practical_status = 'pending',
                theory_phase = 1,
                theory_start_time = NULL, theory_end_time = NULL,
                practical_start_time = NULL, practical_end_time = NULL,
                active_time_used = 0, last_heartbeat_time = NULL
            WHERE id = %s
        ''', (student_exam_id,))
        
        # 2. Delete theory answers
        update_db('DELETE FROM student_theory_answers WHERE student_exam_id = %s', (student_exam_id,))
        
        # 3. Delete practical submissions
        update_db('DELETE FROM student_practical_submissions WHERE student_exam_id = %s', (student_exam_id,))
        
        # 4. Delete marklist entries
        update_db('DELETE FROM mark_lists WHERE student_exam_id = %s', (student_exam_id,))
        
        # 5. Delete active sessions
        update_db('DELETE FROM exam_sessions WHERE student_exam_id = %s', (student_exam_id,))
        
        flash('Examination status reset successfully for the student.', 'success')
    except Exception as e:
        flash(f'Error resetting status: {str(e)}', 'error')
        
    return redirect(request.referrer or url_for('state_admin.manage_status'))

@state_admin_bp.route('/student-performance/<int:student_exam_id>')
@login_required(role='state_admin')
def student_performance_review(student_exam_id):
    # 1. Basic Info
    student_exam = query_db('''
        SELECT se.*, u.full_name, u.username, e.exam_name, e.max_score
        FROM student_exams se
        JOIN users u ON se.student_id = u.id
        JOIN examinations e ON se.exam_id = e.id
        WHERE se.id = %s
    ''', (student_exam_id,), one=True)
    
    if not student_exam:
        flash('Performance record not found.', 'danger')
        return redirect(url_for('state_admin.dashboard'))
    
    # 2. Activity Logs
    logs = query_db('''
        SELECT * FROM activity_logs 
        WHERE student_exam_id = %s 
        ORDER BY created_at DESC
    ''', (student_exam_id,))
    
    # 3. Theory Analysis
    theory_answers_raw = query_db('''
        SELECT sta.*, q.question_text, q.max_score,
               (SELECT string_agg(option_text, ', ' ORDER BY option_order) 
                FROM question_options 
                WHERE id::text = ANY(string_to_array(sta.selected_options, ','))) as student_answer_text,
               (SELECT string_agg(option_text, ', ' ORDER BY option_order) 
                FROM question_options 
                WHERE question_id = q.id AND is_correct = TRUE) as correct_answer_text
        FROM student_theory_answers sta
        JOIN questions q ON sta.question_id = q.id
        WHERE sta.student_exam_id = %s
        ORDER BY sta.answered_at
    ''', (student_exam_id,))
    
    # 4. Practical Analysis
    practical_submissions = query_db('''
        SELECT sps.*, q.question_text, q.max_score,
               eval.full_name as evaluator_name,
               rev.full_name as revaluator_name
        FROM student_practical_submissions sps
        JOIN questions q ON sps.question_id = q.id
        LEFT JOIN users eval ON sps.evaluated_by = eval.id
        LEFT JOIN users rev ON sps.revaluated_by = rev.id
        WHERE sps.student_exam_id = %s
        ORDER BY sps.submission_time
    ''', (student_exam_id,))
    
    # 5. Marklist details
    ml = query_db('SELECT * FROM mark_lists WHERE student_exam_id = %s', (student_exam_id,), one=True)
    
    total_score = ml['total_score'] if ml else (
        sum(float(a['score_obtained'] or 0) for a in theory_answers_raw) + 
        sum(float(p['score_obtained'] or 0) for p in practical_submissions)
    )
    
    percentage = ml['percentage'] if ml else 0
    if not ml and student_exam['max_score'] > 0:
        percentage = (float(total_score) / student_exam['max_score']) * 100
    
    grade = ml['grade'] if ml else ('A' if percentage >= 80 else 'B' if percentage >= 60 else 'C' if percentage >= 40 else 'D')

    return render_template('admin/student_performance_review.html',
                           student_exam=student_exam,
                           student={'full_name': student_exam['full_name'], 'username': student_exam['username']},
                           exam={'exam_name': student_exam['exam_name'], 'max_score': student_exam['max_score']},
                           logs=logs,
                           theory_answers=theory_answers_raw,
                           practical_submissions=practical_submissions,
                           total_score=total_score,
                           percentage=percentage,
                           grade=grade,
                           back_url=request.referrer or url_for('state_admin.dashboard'))