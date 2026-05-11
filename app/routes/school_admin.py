from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash
from app.database.db import query_db, insert_db, update_db
from app.routes.auth import login_required

school_admin_bp = Blueprint('school_admin', __name__)

@school_admin_bp.route('/dashboard')
@login_required(role='school_admin')
def dashboard():
    school_id = session['school_id']
    
    # Get exam statistics
    stats = {
        'ongoing_exams': query_db('''
            SELECT COUNT(DISTINCT e.id) as count 
            FROM student_exams se
            JOIN examinations e ON se.exam_id = e.id
            WHERE se.school_id = %s AND e.status = 'ongoing'
        ''', (school_id,))[0]['count'],
        
        'total_students': query_db('''
            SELECT COUNT(*) as count 
            FROM users 
            WHERE school_id = %s AND user_type = 'student'
        ''', (school_id,))[0]['count'],
        
        'completed_exams': query_db('''
            SELECT COUNT(DISTINCT e.id) as count 
            FROM student_exams se
            JOIN examinations e ON se.exam_id = e.id
            WHERE se.school_id = %s AND e.status = 'completed'
        ''', (school_id,))[0]['count']
    }
    
    # Get ongoing exams
    ongoing_exams = query_db('''
        SELECT e.exam_name, e.start_date, e.end_date,
               COUNT(se.id) as total_assigned,
               COUNT(CASE WHEN se.theory_status = 'completed' THEN 1 END) as theory_completed,
               COUNT(CASE WHEN se.practical_status = 'completed' THEN 1 END) as practical_completed
        FROM examinations e
        JOIN student_exams se ON e.id = se.exam_id
        WHERE se.school_id = %s AND e.status = 'ongoing'
        GROUP BY e.id, e.exam_name, e.start_date, e.end_date
    ''', (school_id,))
    
    return render_template('school_admin/dashboard.html', stats=stats, ongoing_exams=ongoing_exams)

@school_admin_bp.route('/create-invigilator', methods=['GET', 'POST'])
@login_required(role='school_admin')
def create_invigilator():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        full_name = request.form['full_name']
        email = request.form.get('email', '')
        phone = request.form.get('phone', '')
        
        password_hash = generate_password_hash(password)
        
        insert_db('''
            INSERT INTO users (username, password_hash, full_name, email, phone, 
                             user_type, school_id, created_by)
            VALUES (%s, %s, %s, %s, %s, 'invigilator', %s, %s)
        ''', (username, password_hash, full_name, email, phone, 
              session['school_id'], session['user_id']))
        
        flash('Invigilator created successfully!', 'success')
        return redirect(url_for('school_admin.create_invigilator'))
    
    invigilators = query_db('''
        SELECT * FROM users 
        WHERE user_type = 'invigilator' AND school_id = %s
        ORDER BY created_at DESC
    ''', (session['school_id'],))
    
    return render_template('school_admin/create_invigilator.html', invigilators=invigilators)

@school_admin_bp.route('/exam-status')
@login_required(role='school_admin')
def exam_status():
    school_id = session['school_id']
    
    status_data = query_db('''
        SELECT e.exam_name, e.status as exam_status,
               u.full_name as student_name,
               se.theory_status, se.practical_status,
               se.theory_start_time, se.practical_start_time
        FROM student_exams se
        JOIN examinations e ON se.exam_id = e.id
        JOIN users u ON se.student_id = u.id
        WHERE se.school_id = %s
        ORDER BY e.exam_name, u.full_name
    ''', (school_id,))
    
    return render_template('school_admin/exam_status.html', status_data=status_data)

@school_admin_bp.route('/prepare-marklist', methods=['GET', 'POST'])
@login_required(role='school_admin')
def prepare_marklist():
    school_id = session['school_id']
    
    if request.method == 'POST':
        exam_id = request.form['exam_id']
        
        # Check for pending practical evaluations
        pending_evaluations = query_db('''
            SELECT COUNT(*) as count
            FROM student_practical_submissions sp
            JOIN student_exams se ON sp.student_exam_id = se.id
            WHERE se.exam_id = %s AND se.school_id = %s AND sp.score_obtained IS NULL
        ''', (exam_id, school_id), one=True)
        
        if pending_evaluations and pending_evaluations['count'] > 0:
            flash(f'Cannot prepare mark list. There are {pending_evaluations["count"]} pending practical evaluations for this examination. All submissions must be evaluated first.', 'danger')
            return redirect(url_for('school_admin.prepare_marklist'))
        
        # Calculate and create marklist entries for all completed students
        student_exams = query_db('''
            SELECT se.id as student_exam_id, se.student_id,
                   COALESCE((SELECT SUM(score_obtained) FROM student_theory_answers WHERE student_exam_id = se.id AND is_correct = TRUE), 0) as theory_total,
                   COALESCE((SELECT SUM(score_obtained) FROM student_practical_submissions WHERE student_exam_id = se.id), 0) as practical_total
            FROM student_exams se
            WHERE se.exam_id = %s AND se.school_id = %s
            AND se.theory_status = 'completed' AND se.practical_status = 'completed'
        ''', (exam_id, school_id))
        
        for se in student_exams:
            total_score = se['theory_total'] + se['practical_total']
            
            # Calculate total possible marks dynamically based on assigned questions
            exam = query_db('''
                SELECT total_theory_questions, total_practical_questions,
                       easy_questions, average_questions, difficult_questions
                FROM examinations WHERE id = %s
            ''', (exam_id,), one=True)
            
            import random
            rng = random.Random(se['student_exam_id'])
            
            # Calculate theory max score
            theory_raw = query_db('SELECT id, max_score, difficulty_level FROM questions WHERE exam_id=%s AND question_type=%s ORDER BY id', (exam_id, 'theory'))
            easy_pool = [q for q in theory_raw if q['difficulty_level'] == 'easy']
            avg_pool = [q for q in theory_raw if q['difficulty_level'] == 'average']
            diff_pool = [q for q in theory_raw if q['difficulty_level'] == 'difficult']
            
            selected_theory = []
            selected_theory.extend(rng.sample(easy_pool, min(exam['easy_questions'] or 0, len(easy_pool))))
            selected_theory.extend(rng.sample(avg_pool, min(exam['average_questions'] or 0, len(avg_pool))))
            selected_theory.extend(rng.sample(diff_pool, min(exam['difficult_questions'] or 0, len(diff_pool))))
            
            shortfall = (exam['total_theory_questions'] or 0) - len(selected_theory)
            if shortfall > 0:
                current_ids = {q['id'] for q in selected_theory}
                rem_pool = [q for q in theory_raw if q['id'] not in current_ids]
                selected_theory.extend(rng.sample(rem_pool, min(shortfall, len(rem_pool))))
                
            total_theory_max = sum(q['max_score'] for q in selected_theory)
            
            # Calculate practical max score
            prac_raw = query_db('SELECT id, max_score FROM questions WHERE exam_id=%s AND question_type=%s ORDER BY id', (exam_id, 'practical'))
            selected_prac = rng.sample(prac_raw, min(exam['total_practical_questions'] or 0, len(prac_raw)))
            total_prac_max = sum(q['max_score'] for q in selected_prac)
            
            total_possible = total_theory_max + total_prac_max
            percentage = (total_score / total_possible * 100) if total_possible > 0 else 0
            
            # Assign grade
            grade = 'A' if percentage >= 80 else 'B' if percentage >= 60 else 'C' if percentage >= 40 else 'D'
            
            # Check if marklist already exists
            existing = query_db('''
                SELECT id FROM mark_lists WHERE student_exam_id = %s
            ''', (se['student_exam_id'],), one=True)
            
            if existing:
                update_db('''
                    UPDATE mark_lists 
                    SET theory_score=%s, practical_score=%s, total_score=%s, 
                        percentage=%s, grade=%s, status='finalized'
                    WHERE id=%s
                ''', (se['theory_total'], se['practical_total'], total_score, 
                      percentage, grade, existing['id']))
            else:
                insert_db('''
                    INSERT INTO mark_lists 
                    (student_exam_id, theory_score, practical_score, total_score, 
                     percentage, grade, prepared_by, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'finalized')
                ''', (se['student_exam_id'], se['theory_total'], se['practical_total'],
                      total_score, percentage, grade, session['user_id']))
        
        flash('Marklist prepared successfully!', 'success')
        return redirect(url_for('school_admin.view_marklist', exam_id=exam_id))
    
    exams = query_db('''
        SELECT DISTINCT e.id, e.exam_name 
        FROM examinations e
        JOIN student_exams se ON e.id = se.exam_id
        WHERE se.school_id = %s AND e.status IN ('published', 'ongoing', 'completed')
    ''', (school_id,))
    
    return render_template('school_admin/prepare_marklist.html', exams=exams)

@school_admin_bp.route('/view-marklist')
@login_required(role='school_admin')
def view_marklist():
    exam_id = request.args.get('exam_id')
    school_id = session['school_id']
    
    marklist = query_db('''
        SELECT u.full_name as student_name, u.username,
               ml.theory_score, ml.practical_score, ml.total_score,
               ml.percentage, ml.grade, e.exam_name
        FROM mark_lists ml
        JOIN student_exams se ON ml.student_exam_id = se.id
        JOIN users u ON se.student_id = u.id
        JOIN examinations e ON se.exam_id = e.id
        WHERE se.school_id = %s
        ''' + (' AND e.id = %s' if exam_id else '') + '''
        ORDER BY e.exam_name, ml.total_score DESC
    ''', (school_id, exam_id) if exam_id else (school_id,))
    
    exams = query_db('''
        SELECT DISTINCT e.id, e.exam_name 
        FROM examinations e
        JOIN student_exams se ON e.id = se.exam_id
        WHERE se.school_id = %s
    ''', (school_id,))
    
    return render_template('school_admin/view_marklist.html', marklist=marklist, 
                         exams=exams, selected_exam=exam_id)

@school_admin_bp.route('/students')
@login_required(role='school_admin')
def view_students():
    school_id = session['school_id']
    class_id = request.args.get('class_id')
    
    classes = query_db('SELECT * FROM classes ORDER BY class_name')
    
    query = '''
        SELECT u.id, u.username, u.full_name, u.email, u.phone, u.created_at, u.class_id, c.class_name
        FROM users u
        LEFT JOIN classes c ON u.class_id = c.id
        WHERE u.user_type = 'student' AND u.school_id = %s
    '''
    params = [school_id]
    
    if class_id:
        query += ' AND u.class_id = %s'
        params.append(class_id)
        
    query += ' ORDER BY c.class_name, u.full_name'
    students = query_db(query, params)
    
    return render_template('school_admin/view_students.html', 
                           students=students, 
                           classes=classes,
                           selected_class_id=int(class_id) if class_id else None)