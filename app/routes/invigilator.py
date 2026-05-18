from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash
from app.database.db import query_db, insert_db, update_db, log_activity
from app.routes.auth import login_required
from werkzeug.utils import secure_filename
import os

invigilator_bp = Blueprint('invigilator', __name__)

@invigilator_bp.route('/dashboard')
@login_required(role='invigilator')
def dashboard():
    school_id = session['school_id']
    
    # Get students for this school
    students = query_db('''
        SELECT u.id, u.full_name, u.username
        FROM users u
        WHERE u.user_type = 'student' AND u.school_id = %s
        ORDER BY u.full_name
    ''', (school_id,))
    
    # Get exams that need practical evaluation
    evaluation_pending = query_db('''
        SELECT se.id as student_exam_id, u.full_name as student_name,
               e.exam_name, sp.question_id, sp.file_path, sp.id as submission_id,
               q.question_text, CASE WHEN q.image_blob IS NOT NULL THEN 1 ELSE 0 END as has_image
        FROM student_practical_submissions sp
        JOIN student_exams se ON sp.student_exam_id = se.id
        JOIN users u ON se.student_id = u.id
        JOIN examinations e ON se.exam_id = e.id
        JOIN questions q ON sp.question_id = q.id
        WHERE se.school_id = %s AND sp.score_obtained IS NULL
        ORDER BY sp.submission_time
    ''', (school_id,))
    
    return render_template('invigilator/dashboard.html', 
                         students=students, evaluation_pending=evaluation_pending)

@invigilator_bp.route('/student-login', methods=['POST'])
@login_required(role='invigilator')
def student_login():
    from werkzeug.security import check_password_hash
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    invigilator_school_id = session['school_id']

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required.'}), 400

    # Authenticate: must be a student at the same school
    student = query_db(
        "SELECT * FROM users WHERE username=%s AND user_type='student' AND school_id=%s AND is_active=TRUE",
        (username, invigilator_school_id), one=True
    )

    if not student:
        return jsonify({'success': False, 'message': 'Invalid credentials or student not from this school.'}), 401

    if not check_password_hash(student['password_hash'], password):
        return jsonify({'success': False, 'message': 'Incorrect password.'}), 401

    # Preserve invigilator identity before switching session
    invigilator_id = session['user_id']
    invigilator_name = session['full_name']

    # Switch to student session but keep invigilator restore info
    session.clear()
    session['user_id'] = student['id']
    session['user_type'] = 'student'
    session['full_name'] = student['full_name']
    session['school_id'] = student['school_id']
    # Store invigilator info for session restoration after student finishes
    session['invigilator_id'] = invigilator_id
    session['invigilator_name'] = invigilator_name
    session['invigilator_school_id'] = invigilator_school_id
    
    log_activity(student['id'], None, 'student_login', f"Student {student['username']} logged in by invigilator {invigilator_name}", request.remote_addr)

    return jsonify({
        'success': True,
        'redirect_url': url_for('student.dashboard')
    })


@invigilator_bp.route('/student-logout', methods=['POST'])
def student_logout():
    """Called after a student finishes their exam to restore the invigilator session."""
    invigilator_id = session.get('invigilator_id')
    invigilator_name = session.get('invigilator_name')
    invigilator_school_id = session.get('invigilator_school_id')
    student_id = session.get('user_id')
    student_name = session.get('full_name')

    if student_id:
        log_activity(student_id, None, 'student_logout', f"Student {student_name} session ended/restored to invigilator", request.remote_addr)

    if not invigilator_id:
        # No invigilator to restore — go to main login
        session.clear()
        from flask import redirect, url_for
        return redirect(url_for('auth.login'))

    # Restore invigilator session
    session.clear()
    session['user_id'] = invigilator_id
    session['user_type'] = 'invigilator'
    session['full_name'] = invigilator_name
    session['school_id'] = invigilator_school_id

    from flask import redirect, url_for
    return redirect(url_for('invigilator.dashboard'))

@invigilator_bp.route('/evaluate-practical', methods=['GET', 'POST'])
@login_required(role='invigilator')
def evaluate_practical():
    school_id = session['school_id']
    
    if request.method == 'POST':
        submission_id = request.form['submission_id']
        score = request.form['score']
        remarks = request.form.get('remarks', '')
        
        # Check if locked
        locked_check = query_db('''
            SELECT ml.status 
            FROM mark_lists ml
            JOIN student_exams se ON ml.student_exam_id = se.id
            JOIN student_practical_submissions sp ON sp.student_exam_id = se.id
            WHERE sp.id = %s AND ml.status = 'finalized'
        ''', (submission_id,), one=True)
        
        if locked_check:
            flash('This evaluation is locked because the mark list has been finalized.', 'danger')
            return redirect(url_for('invigilator.evaluate_practical'))
        
        update_db('''
            UPDATE student_practical_submissions 
            SET score_obtained = %s, initial_score = COALESCE(initial_score, %s), 
                evaluated_by = %s, remarks = %s,
                evaluation_time = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (score, score, session['user_id'], remarks, submission_id))
        
        flash('Evaluation submitted successfully!', 'success')
        return redirect(url_for('invigilator.evaluate_practical'))
    
    # GET - handle filters
    exam_filter = request.args.get('exam_id')
    status_filter = request.args.get('status')
    class_filter = request.args.get('class_id')
    student_query = request.args.get('student_query')
    
    # Base query for submissions
    query = '''
        SELECT sp.id as submission_id, sp.file_path, sp.file_name,
               sp.submission_time, u.full_name as student_name, u.username,
               e.exam_name, q.max_score, sp.remarks, q.question_text,
               sp.question_id, CASE WHEN q.image_blob IS NOT NULL THEN 1 ELSE 0 END as has_image,
               q.resource_file_name, q.value_points,
               CASE WHEN ml.status = 'finalized' THEN 1 ELSE 0 END as is_locked,
               c.class_name
        FROM student_practical_submissions sp
        JOIN student_exams se ON sp.student_exam_id = se.id
        JOIN users u ON se.student_id = u.id
        JOIN examinations e ON se.exam_id = e.id
        JOIN questions q ON sp.question_id = q.id
        LEFT JOIN classes c ON u.class_id = c.id
        LEFT JOIN mark_lists ml ON ml.student_exam_id = se.id
        WHERE se.school_id = %s
    '''
    params = [school_id]
    
    if exam_filter:
        query += ' AND e.id = %s'
        params.append(exam_filter)
    
    if status_filter == 'pending':
        query += ' AND sp.score_obtained IS NULL'
    elif status_filter == 'evaluated':
        query += ' AND sp.score_obtained IS NOT NULL'
        
    if class_filter:
        query += ' AND u.class_id = %s'
        params.append(class_filter)
        
    if student_query:
        query += ' AND (u.full_name ILIKE %s OR u.username ILIKE %s)'
        params.extend([f'%{student_query}%', f'%{student_query}%'])
        
    query += ' ORDER BY sp.score_obtained NULLS FIRST, sp.submission_time'
    
    submissions = query_db(query, params)
    
    # Get options for filters
    exams = query_db('''
        SELECT DISTINCT e.id, e.exam_name 
        FROM examinations e
        JOIN student_exams se ON e.id = se.exam_id
        WHERE se.school_id = %s
    ''', (school_id,))
    
    classes = query_db('SELECT * FROM classes ORDER BY class_name')
    
    return render_template('invigilator/evaluate_practical.html', 
                         submissions=submissions,
                         exams=exams,
                         classes=classes,
                         filters={
                             'exam_id': exam_filter,
                             'status': status_filter,
                             'class_id': class_filter,
                             'student_query': student_query
                         })