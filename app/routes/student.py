from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, flash
from app.database.db import query_db, insert_db, update_db
from app.routes.auth import login_required
from werkzeug.utils import secure_filename
import os
from datetime import datetime

student_bp = Blueprint('student', __name__)

@student_bp.route('/dashboard')
@login_required(role='student')
def dashboard():
    # Get assigned exams
    exams = query_db('''
        SELECT se.*, e.exam_name, e.start_date, e.end_date, e.duration_minutes,
               e.total_theory_questions, e.total_short_answer_questions, e.total_practical_questions,
               e.max_score, s.subject_name, e.status
        FROM student_exams se
        JOIN examinations e ON se.exam_id = e.id
        JOIN subjects s ON e.subject_id = s.id
        WHERE se.student_id = %s
        ORDER BY e.start_date
    ''', (session['user_id'],))
    
    return render_template('student/dashboard.html', exams=exams)

@student_bp.route('/attend-theory/<int:student_exam_id>')
@login_required(role='student')
def attend_theory(student_exam_id):
    # Verify this exam belongs to student
    exam_data = query_db('''
        SELECT se.*, e.exam_name, e.duration_minutes, e.total_theory_questions,
               e.total_short_answer_questions, e.max_score,
               e.easy_questions, e.average_questions, e.difficult_questions,
               u.medium, e.status
        FROM student_exams se
        JOIN examinations e ON se.exam_id = e.id
        JOIN users u ON se.student_id = u.id
        WHERE se.id = %s AND se.student_id = %s
    ''', (student_exam_id, session['user_id']), one=True)
    
    if not exam_data:
        flash('Invalid exam!', 'error')
        return redirect(url_for('student.dashboard'))
    if exam_data["status"] == "draft":
        flash("This examination has not been published yet.", "error")
        return redirect(url_for("student.dashboard"))

    
    if exam_data['theory_status'] == 'completed':
        flash('You have already completed the theory exam!', 'error')
        return redirect(url_for('student.dashboard'))
    
    # Start exam if not started
    if exam_data['theory_status'] == 'pending':
        update_db('''
            UPDATE student_exams 
            SET theory_status = 'in_progress', theory_start_time = CURRENT_TIMESTAMP,
                last_heartbeat_time = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (student_exam_id,))
        theory_elapsed = 0
    else:
        # Update last_heartbeat_time to now so we don't count the offline gap
        update_db('''
            UPDATE student_exams 
            SET last_heartbeat_time = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (student_exam_id,))
        theory_elapsed = int(exam_data['active_time_used'] or 0)
        
    duration_seconds = exam_data['duration_minutes'] * 60
    remaining_seconds = int(duration_seconds - theory_elapsed)
    
    if remaining_seconds <= 0:
        update_db('''
            UPDATE student_exams 
            SET theory_status = 'completed', theory_end_time = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (student_exam_id,))
        flash('Theory exam time has expired!', 'error')
        return redirect(url_for('student.dashboard'))
    
    # Get theory questions (including short_answer)
    questions_raw = query_db('''
        SELECT q.*, string_agg(qo.option_text, '|||' ORDER BY qo.option_order) as options,
               string_agg(qo.id::text, ',' ORDER BY qo.option_order) as option_ids,
               string_agg(qo.option_order, ',' ORDER BY qo.option_order) as option_orders
        FROM questions q
        LEFT JOIN question_options qo ON q.id = qo.question_id
        WHERE q.exam_id = %s AND q.question_type IN ('theory', 'short_answer') AND q.language = %s
        GROUP BY q.id
        ORDER BY q.id
    ''', (exam_data['exam_id'], exam_data['medium']))
    
    # Get chapter-wise difficulty configuration
    exam_chapters_cfg = query_db('''
        SELECT * FROM exam_chapters WHERE exam_id = %s
    ''', (exam_data['exam_id'],))
    
    import random
    rng = random.Random(student_exam_id)
    
    max_exam_score = exam_data.get('max_score') or 0
    current_total_score = 0
    selected_questions = []
    
    # Organize questions by chapter and difficulty
    pools = {} # chapter_id -> {easy: [], average: [], difficult: []}
    for q in questions_raw:
        cid = q['chapter_id']
        diff = q['difficulty_level']
        if cid not in pools:
            pools[cid] = {'easy': [], 'average': [], 'difficult': []}
        if diff in pools[cid]:
            pools[cid][diff].append(q)
    
    # Pick questions based on chapter configuration
    for cfg in exam_chapters_cfg:
        cid = cfg['chapter_id']
        if cid not in pools:
            continue
            
        # For each difficulty level in this chapter
        for diff_level in ['easy', 'average', 'difficult']:
            needed = cfg[f'{diff_level}_count'] or 0
            available = pools[cid][diff_level]
            
            if needed > 0 and available:
                picked = rng.sample(available, min(needed, len(available)))
                for q in picked:
                    # Check Max Score constraint
                    if max_exam_score > 0 and (current_total_score + q['max_score']) > max_exam_score:
                        continue
                    
                    selected_questions.append(q)
                    current_total_score += q['max_score']
    
    # Fallback: fill up to global targets if chapter counts weren't enough
    total_theory_needed = exam_data.get('total_theory_questions') or 0
    total_short_needed = exam_data.get('total_short_answer_questions') or 0
    
    current_theory_count = sum(1 for q in selected_questions if q['question_type'] == 'theory')
    current_short_count = sum(1 for q in selected_questions if q['question_type'] == 'short_answer')
    
    already_selected_ids = {q['id'] for q in selected_questions}
    remaining_pool = [q for q in questions_raw if q['id'] not in already_selected_ids]
    rng.shuffle(remaining_pool)
    
    # Fill Short Answer first
    for q in remaining_pool:
        if current_short_count >= total_short_needed:
            break
        if q['question_type'] == 'short_answer':
            if max_exam_score > 0 and (current_total_score + q['max_score']) > max_exam_score:
                continue
            selected_questions.append(q)
            current_total_score += q['max_score']
            current_short_count += 1
            already_selected_ids.add(q['id'])
            
    # Then fill Theory
    remaining_pool = [q for q in questions_raw if q['id'] not in already_selected_ids]
    for q in remaining_pool:
        if current_theory_count >= total_theory_needed:
            break
        if q['question_type'] == 'theory':
            if max_exam_score > 0 and (current_total_score + q['max_score']) > max_exam_score:
                continue
            selected_questions.append(q)
            current_total_score += q['max_score']
            current_theory_count += 1
            already_selected_ids.add(q['id'])
    
    # Finally, sort selected_questions so that Theory (MCQs) come first, then Short Answer
    selected_questions.sort(key=lambda x: (0 if x['question_type'] == 'theory' else 1, x['id']))
    
    # Prune to ensure strict counts as per global configuration
    final_theory = [q for q in selected_questions if q['question_type'] == 'theory'][:total_theory_needed]
    final_short  = [q for q in selected_questions if q['question_type'] == 'short_answer'][:total_short_needed]
    selected_questions = final_theory + final_short
    
    # Filter questions based on the current theory phase
    current_phase = exam_data.get('theory_phase', 1)
    if current_phase == 1:
        # Phase 1: Only MCQ (theory)
        filtered_questions = [q for q in selected_questions if q['question_type'] == 'theory']
    else:
        # Phase 2: Only Short Answer
        filtered_questions = [q for q in selected_questions if q['question_type'] == 'short_answer']
    
    # Fetch previously saved answers
    saved_answers_raw = query_db('''
        SELECT question_id, selected_options 
        FROM student_theory_answers 
        WHERE student_exam_id = %s
    ''', (student_exam_id,))
    
    saved_answers = {}
    for row in saved_answers_raw:
        opts = row['selected_options']
        if opts and opts.strip():
            saved_answers[str(row['question_id'])] = opts.split(',')
        else:
            saved_answers[str(row['question_id'])] = []
    
    return render_template('student/attend_theory.html', 
                         exam=exam_data, questions=filtered_questions, 
                         student_exam_id=student_exam_id, remaining_seconds=remaining_seconds,
                         saved_answers=saved_answers, current_phase=current_phase)

@student_bp.route('/submit-theory', methods=['POST'])
@login_required(role='student')
def submit_theory():
    student_exam_id = request.form['student_exam_id']
    answers = request.form.to_dict(flat=False)
    
    # Process answers
    for key, values in answers.items():
        if key.startswith('question_'):
            question_id = key.replace('question_', '')
            selected_options = ','.join(values)  # Join all selected option IDs (fixes multi-select)
            
            # Check if correct
            correct_options = query_db('''
                SELECT id FROM question_options 
                WHERE question_id = %s AND is_correct = TRUE
                ORDER BY id
            ''', (question_id,))
            
            correct_ids = set(str(opt['id']) for opt in correct_options)
            selected_ids = set(selected_options.split(','))
            
            is_correct = correct_ids == selected_ids
            
            # Calculate score
            question = query_db('SELECT max_score FROM questions WHERE id=%s', 
                              (question_id,), one=True)
            score = question['max_score'] if is_correct else 0
            # Check if answer already exists
            existing = query_db('SELECT id FROM student_theory_answers WHERE student_exam_id=%s AND question_id=%s',
                              (student_exam_id, question_id), one=True)
                              
            if existing:
                update_db('''
                    UPDATE student_theory_answers 
                    SET selected_options=%s, is_correct=%s, score_obtained=%s, answered_at=CURRENT_TIMESTAMP
                    WHERE id=%s
                ''', (selected_options, is_correct, score, existing['id']))
            else:
                insert_db('''
                    INSERT INTO student_theory_answers 
                    (student_exam_id, question_id, selected_options, is_correct, score_obtained)
                VALUES (%s, %s, %s, %s, %s)
            ''', (student_exam_id, question_id, selected_options, is_correct, score))
    
    # Get current phase
    exam_info = query_db('SELECT theory_phase FROM student_exams WHERE id = %s', (student_exam_id,), one=True)
    current_phase = exam_info['theory_phase'] if exam_info else 1
    
    if current_phase == 1:
        # Move to Phase 2 (Short Answer)
        update_db('''
            UPDATE student_exams 
            SET theory_phase = 2
            WHERE id = %s
        ''', (student_exam_id,))
        flash('MCQ section submitted successfully. Now starting Short Answer section.', 'success')
        return redirect(url_for('student.attend_theory', student_exam_id=student_exam_id))
    else:
        # Phase 2 completed -> Finish theory exam
        update_db('''
            UPDATE student_exams 
            SET theory_status = 'completed', theory_end_time = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (student_exam_id,))
        
        return redirect(url_for('student.exam_complete', type='theory'))

@student_bp.route('/attend-practical/<int:student_exam_id>')
@login_required(role='student')
def attend_practical(student_exam_id):
    exam_data = query_db('''
        SELECT se.*, e.exam_name, e.duration_minutes, e.total_practical_questions,
               u.medium, e.status
        FROM student_exams se
        JOIN examinations e ON se.exam_id = e.id
        JOIN users u ON se.student_id = u.id
        WHERE se.id = %s AND se.student_id = %s
    ''', (student_exam_id, session['user_id']), one=True)
    
    if not exam_data:
        flash('Invalid exam!', 'error')
        return redirect(url_for('student.dashboard'))
    
    if exam_data['status'] == 'draft':
        flash('This examination has not been published yet.', 'error')
        return redirect(url_for('student.dashboard'))
    
    if exam_data['theory_status'] != 'completed':
        flash('You must complete theory exam first!', 'error')
        return redirect(url_for('student.dashboard'))
    
    if exam_data['practical_status'] == 'completed':
        flash('You have already completed the practical exam!', 'error')
        return redirect(url_for('student.dashboard'))
    
    # Start practical exam
    if exam_data['practical_status'] == 'pending':
        update_db('''
            UPDATE student_exams 
            SET practical_status = 'in_progress', practical_start_time = CURRENT_TIMESTAMP,
                last_heartbeat_time = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (student_exam_id,))
    else:
        # Update last_heartbeat_time to now so we don't count the offline gap
        update_db('''
            UPDATE student_exams 
            SET last_heartbeat_time = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (student_exam_id,))
        
    total_elapsed = int(exam_data['active_time_used'] or 0)
    
    # Shared duration logic: The total duration is for both theory and practical combined.
    duration_seconds = exam_data['duration_minutes'] * 60
    remaining_seconds = int(duration_seconds - total_elapsed)
    
    if remaining_seconds <= 0:
        update_db('''
            UPDATE student_exams 
            SET practical_status = 'completed', practical_end_time = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (student_exam_id,))
        flash('Practical exam time has expired!', 'error')
        return redirect(url_for('student.dashboard'))
    
    # Get practical questions
    questions_raw = query_db('''
        SELECT * FROM questions 
        WHERE exam_id = %s AND question_type = 'practical' AND status = 'active'
        AND language = %s
        ORDER BY id
    ''', (exam_data['exam_id'], exam_data['medium']))
    
    import random
    rng = random.Random(student_exam_id)
    total_practical_slots = exam_data.get('total_practical_questions') or 0
    needed_questions = total_practical_slots * 2
    
    # Shuffle and pick questions for the slots
    shuffled_pool = list(questions_raw)
    rng.shuffle(shuffled_pool)
    picked_questions = shuffled_pool[:min(needed_questions, len(shuffled_pool))]
    
    # Group into slots (pairs)
    practical_slots = []
    for i in range(0, len(picked_questions), 2):
        slot = {
            'q1': picked_questions[i],
            'q2': picked_questions[i+1] if i+1 < len(picked_questions) else None
        }
        practical_slots.append(slot)
    
    # Fetch existing submissions
    submissions_raw = query_db('''
        SELECT question_id, file_name FROM student_practical_submissions
        WHERE student_exam_id = %s
    ''', (student_exam_id,))
    
    submissions = {str(s['question_id']): dict(s) for s in submissions_raw}
    
    return render_template('student/attend_practical.html', 
                          exam=exam_data, slots=practical_slots,
                          student_exam_id=student_exam_id, remaining_seconds=remaining_seconds,
                          submissions=submissions)

@student_bp.route('/upload-practical-work', methods=['POST'])
@login_required(role='student')
def upload_practical_work():
    student_exam_id = request.form['student_exam_id']
    question_id = request.form['question_id']
    
    if 'practical_file' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'}), 400
    
    file = request.files['practical_file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'}), 400
    
    filename = secure_filename(f"{session['user_id']}_{question_id}_{file.filename}")
    file_data = file.read()
    from app.utils.crypto import encrypt_data
    file_blob = encrypt_data(file_data)
    file_mimetype = file.mimetype
    
    option_id = request.form.get('option_id')
    
    insert_db('''
        INSERT INTO student_practical_submissions 
        (student_exam_id, question_id, option_id, file_name, file_blob, file_mimetype)
        VALUES (%s, %s, %s, %s, %s, %s)
    ''', (student_exam_id, question_id, option_id, filename, file_blob, file_mimetype))
    
    return jsonify({'success': True, 'message': 'File uploaded successfully'})

@student_bp.route('/complete-practical', methods=['POST'])
@login_required(role='student')
def complete_practical():
    student_exam_id = request.form['student_exam_id']
    
    update_db('''
        UPDATE student_exams 
        SET practical_status = 'completed', practical_end_time = CURRENT_TIMESTAMP
        WHERE id = %s
    ''', (student_exam_id,))
    
    return redirect(url_for('student.exam_complete', type='practical'))

@student_bp.route('/exam-complete/<type>')
@login_required(role='student')
def exam_complete(type):
    return render_template('student/exam_complete.html', exam_type=type)

@student_bp.route('/results')
@login_required(role='student')
def results():
    results = query_db('''
        SELECT ml.*, e.exam_name, s.subject_name
        FROM mark_lists ml
        JOIN student_exams se ON ml.student_exam_id = se.id
        JOIN examinations e ON se.exam_id = e.id
        JOIN subjects s ON e.subject_id = s.id
        WHERE se.student_id = %s AND ml.status = 'finalized'
        ORDER BY ml.prepared_at DESC
    ''', (session['user_id'],))
    
    return render_template('student/results.html', results=results)

@student_bp.route('/api/heartbeat', methods=['POST'])
@login_required(role='student')
def heartbeat():
    data = request.get_json()
    if not data or 'student_exam_id' not in data:
        return jsonify({'success': False, 'message': 'Missing student_exam_id'}), 400
        
    student_exam_id = data['student_exam_id']
    
    # Get current state
    exam_data = query_db('''
        SELECT se.active_time_used, EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - se.last_heartbeat_time)) as seconds_since_last, e.duration_minutes
        FROM student_exams se
        JOIN examinations e ON se.exam_id = e.id
        WHERE se.id = %s AND se.student_id = %s
    ''', (student_exam_id, session['user_id']), one=True)
    
    if not exam_data:
        return jsonify({'success': False, 'message': 'Invalid exam'}), 404
        
    seconds_since_last = exam_data['seconds_since_last']
    current_active_time = exam_data['active_time_used'] or 0
    
    # If the time since last heartbeat is reasonable (e.g. <= 10 seconds), add it
    # If it's too long, they were likely offline/inactive, so just add a standard heartbeat interval (5 seconds)
    if seconds_since_last is None:
        added_time = 0
    elif seconds_since_last <= 10:
        added_time = int(seconds_since_last)
    else:
        added_time = 5
        
    new_active_time = current_active_time + added_time
    
    duration_seconds = exam_data['duration_minutes'] * 60
    remaining_seconds = max(0, int(duration_seconds - new_active_time))
    
    update_db('''
        UPDATE student_exams 
        SET active_time_used = %s, last_heartbeat_time = CURRENT_TIMESTAMP
        WHERE id = %s
    ''', (new_active_time, student_exam_id))
    
    return jsonify({
        'success': True,
        'remaining_seconds': remaining_seconds
    })

@student_bp.route('/api/save-answer', methods=['POST'])
@login_required(role='student')
def save_answer():
    data = request.get_json()
    if not data or 'student_exam_id' not in data or 'question_id' not in data:
        return jsonify({'success': False, 'message': 'Missing data'}), 400
        
    student_exam_id = data['student_exam_id']
    question_id = data['question_id']
    selected_options = data.get('selected_options', '')
    
    # Calculate correctness
    correct_options = query_db('''
        SELECT id FROM question_options 
        WHERE question_id = %s AND is_correct = TRUE
        ORDER BY id
    ''', (question_id,))
    
    correct_ids = set(str(opt['id']) for opt in correct_options)
    selected_ids = set(selected_options.split(',')) if selected_options else set()
    
    is_correct = correct_ids == selected_ids if selected_ids else False
    
    question = query_db('SELECT max_score FROM questions WHERE id=%s', (question_id,), one=True)
    score = question['max_score'] if is_correct else 0
    
    existing = query_db('SELECT id FROM student_theory_answers WHERE student_exam_id=%s AND question_id=%s',
                      (student_exam_id, question_id), one=True)
                      
    if existing:
        update_db('''
            UPDATE student_theory_answers 
            SET selected_options=%s, is_correct=%s, score_obtained=%s, answered_at=CURRENT_TIMESTAMP
            WHERE id=%s
        ''', (selected_options, is_correct, score, existing['id']))
    else:
        insert_db('''
            INSERT INTO student_theory_answers 
            (student_exam_id, question_id, selected_options, is_correct, score_obtained)
            VALUES (%s, %s, %s, %s, %s)
        ''', (student_exam_id, question_id, selected_options, is_correct, score))
        
    return jsonify({'success': True})

@student_bp.route('/api/save-answers-batch', methods=['POST'])
@login_required(role='student')
def save_answers_batch():
    """Batch save multiple answers in one request. Used by beforeunload and periodic save."""
    data = request.get_json()
    if not data or 'student_exam_id' not in data or 'answers' not in data:
        return jsonify({'success': False, 'message': 'Missing data'}), 400
    
    student_exam_id = data['student_exam_id']
    answers = data['answers']  # list of {question_id, selected_options}
    saved_count = 0
    
    for answer in answers:
        question_id = answer.get('question_id')
        selected_options = answer.get('selected_options', '')
        
        if not question_id:
            continue
        
        # Calculate correctness
        correct_options = query_db('''
            SELECT id FROM question_options 
            WHERE question_id = %s AND is_correct = TRUE
            ORDER BY id
        ''', (question_id,))
        
        correct_ids = set(str(opt['id']) for opt in correct_options)
        selected_ids = set(selected_options.split(',')) if selected_options else set()
        
        is_correct = correct_ids == selected_ids if selected_ids else False
        
        question = query_db('SELECT max_score FROM questions WHERE id=%s', (question_id,), one=True)
        if not question:
            continue
        score = question['max_score'] if is_correct else 0
        
        existing = query_db('SELECT id FROM student_theory_answers WHERE student_exam_id=%s AND question_id=%s',
                          (student_exam_id, question_id), one=True)
        
        if existing:
            update_db('''
                UPDATE student_theory_answers 
                SET selected_options=%s, is_correct=%s, score_obtained=%s, answered_at=CURRENT_TIMESTAMP
                WHERE id=%s
            ''', (selected_options, is_correct, score, existing['id']))
        else:
            insert_db('''
                INSERT INTO student_theory_answers 
                (student_exam_id, question_id, selected_options, is_correct, score_obtained)
                VALUES (%s, %s, %s, %s, %s)
            ''', (student_exam_id, question_id, selected_options, is_correct, score))
        saved_count += 1
    
    return jsonify({'success': True, 'saved_count': saved_count})