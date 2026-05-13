from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, flash
from app.database.db import query_db, insert_db, update_db
from app.routes.auth import login_required
from werkzeug.utils import secure_filename
import os

question_setter_bp = Blueprint('question_setter', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@question_setter_bp.route('/dashboard')
@login_required(role='question_setter')
def dashboard():
    # Get assigned examinations
    exams = query_db('''
        SELECT e.*, c.class_name, s.subject_name 
        FROM examinations e
        JOIN question_setter_assignments qsa ON e.id = qsa.exam_id
        JOIN classes c ON e.class_id = c.id
        JOIN subjects s ON e.subject_id = s.id
        WHERE qsa.user_id = %s
        ORDER BY e.created_at DESC
    ''', (session['user_id'],))
    
    return render_template('question_setter/dashboard.html', exams=exams)

@question_setter_bp.route('/upload-questions/<int:exam_id>', methods=['GET', 'POST'])
@login_required(role='question_setter')
def upload_questions(exam_id):
    # Check if assigned to this exam
    assignment = query_db('''
        SELECT * FROM question_setter_assignments 
        WHERE exam_id=%s AND user_id=%s
    ''', (exam_id, session['user_id']), one=True)
    
    if not assignment:
        flash('You are not assigned to this examination!', 'error')
        return redirect(url_for('question_setter.dashboard'))
    
    exam = query_db('SELECT * FROM examinations WHERE id=%s', (exam_id,), one=True)
    if not exam:
        flash('Examination not found.', 'error')
        return redirect(url_for('question_setter.dashboard'))
    
    if exam['status'] != 'draft':
        flash('This examination is published. Access to questions is locked.', 'warning')
        return redirect(url_for('question_setter.dashboard'))
    
    if request.method == 'POST':
        if exam['status'] != 'draft':
            flash('This examination is published and cannot be modified.', 'error')
            return redirect(url_for('question_setter.upload_questions', exam_id=exam_id))
        
        question_type = request.form['question_type']
        difficulty = request.form['difficulty_level']
        max_score = request.form['max_score']
        question_text = request.form.get('question_text', '')
        is_multiple = request.form.get('is_multiple_correct', False)
        
        # Handle image upload
        image_blob = None
        image_mimetype = None
        if 'question_image' in request.files:
            file = request.files['question_image']
            if file and allowed_file(file.filename):
                file_data = file.read()
                from app.utils.crypto import encrypt_data
                image_blob = encrypt_data(file_data)
                image_mimetype = file.mimetype

        # Handle resource file upload
        resource_blob = None
        resource_mimetype = None
        resource_filename = None
        if 'resource_file' in request.files:
            rfile = request.files['resource_file']
            if rfile and rfile.filename:
                rfile_data = rfile.read()
                from app.utils.crypto import encrypt_data
                resource_blob = encrypt_data(rfile_data)
                resource_mimetype = rfile.mimetype
                resource_filename = secure_filename(rfile.filename)
        
        language = request.form.get('language', 'English')
        chapter_id = request.form.get('chapter_id')
        
        question_id = insert_db('''
            INSERT INTO questions 
            (exam_id, question_type, image_blob, image_mimetype, difficulty_level, 
             max_score, question_text, is_multiple_correct, uploaded_by, language, chapter_id,
             resource_file_blob, resource_file_mimetype, resource_file_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (exam_id, question_type, image_blob, image_mimetype, difficulty, max_score, 
              question_text, bool(is_multiple), session['user_id'], language, chapter_id,
              resource_blob, resource_mimetype, resource_filename))
        
        # Add MCQ options if theory or short_answer question
        if question_type in ['theory', 'short_answer']:
            options = request.form.getlist('options[]')
            correct_answers = request.form.getlist('correct_answers[]')
            
            option_labels = ['A', 'B', 'C', 'D', 'E', 'F']
            for i, option in enumerate(options):
                if option.strip():
                    insert_db('''
                        INSERT INTO question_options 
                        (question_id, option_text, is_correct, option_order)
                        VALUES (%s, %s, %s, %s)
                    ''', (question_id, option, str(i) in correct_answers, option_labels[i]))
        
        flash('Question uploaded successfully!', 'success')
        return redirect(url_for('question_setter.upload_questions', exam_id=exam_id))
    
    # Get existing questions for this exam
    questions = query_db('''
        SELECT q.*, c.chapter_name 
        FROM questions q
        LEFT JOIN chapters c ON q.chapter_id = c.id
        WHERE q.exam_id=%s AND q.uploaded_by=%s
        ORDER BY q.question_type, q.created_at DESC
    ''', (exam_id, session['user_id']))

    # Fetch chapters assigned to this exam
    chapters = query_db('''
        SELECT c.* FROM chapters c
        JOIN exam_chapters ec ON c.id = ec.chapter_id
        WHERE ec.exam_id = %s
    ''', (exam_id,))
    
    return render_template('question_setter/upload_questions.html', 
                         exam=exam, questions=questions, exam_id=exam_id, chapters=chapters)

@question_setter_bp.route('/get-question/<int:question_id>')
@login_required(role='question_setter')
def get_question(question_id):
    question = query_db('''
        SELECT q.*, c.chapter_name 
        FROM questions q
        LEFT JOIN chapters c ON q.chapter_id = c.id
        WHERE q.id=%s AND (q.uploaded_by=%s OR q.is_global=TRUE)
    ''', (question_id, session['user_id']), one=True)
    
    if not question:
        flash('Question not found.', 'error')
        return redirect(url_for('question_setter.dashboard'))

    # Check if exam is published
    if question['exam_id']:
        exam = query_db('SELECT status FROM examinations WHERE id=%s', (question['exam_id'],), one=True)
        if exam and exam['status'] != 'draft':
            return jsonify({'error': 'Examination is published. Access locked.'}), 403

    options = query_db('SELECT * FROM question_options WHERE question_id=%s ORDER BY option_order',
                      (question_id,))
    
    q_dict = dict(question)
    q_dict['has_image'] = bool(q_dict.get('image_blob'))
    q_dict['has_resource'] = bool(q_dict.get('resource_file_blob'))
    q_dict['resource_name'] = q_dict.get('resource_file_name')
    q_dict.pop('image_blob', None)
    q_dict.pop('resource_file_blob', None)
        
    return jsonify({
        'question': q_dict,
        'chapter_name': question['chapter_name'],
        'options': [dict(opt) for opt in options]
    })

@question_setter_bp.route('/delete-question/<int:question_id>', methods=['POST'])
@login_required(role='question_setter')
def delete_question(question_id):
    # Verify ownership
    question = query_db('SELECT * FROM questions WHERE id=%s AND uploaded_by=%s', 
                       (question_id, session['user_id']), one=True)
    if not question:
        flash('Unauthorized to delete this question.', 'error')
        return redirect(url_for('question_setter.dashboard'))
        
    exam_id = question['exam_id']
    exam = query_db('SELECT status FROM examinations WHERE id=%s', (exam_id,), one=True)
    if exam and exam['status'] != 'draft':
        flash('This examination is published and questions cannot be deleted.', 'error')
        return redirect(url_for('question_setter.upload_questions', exam_id=exam_id))

    try:
        update_db('DELETE FROM questions WHERE id=%s', (question_id,))
        flash('Question deleted successfully!', 'success')
    except Exception as e:
        flash(f'Cannot delete question: it may have been answered by students or have related data. Error: {str(e)[:120]}', 'error')
    return redirect(url_for('question_setter.upload_questions', exam_id=exam_id))

@question_setter_bp.route('/question-bank')
@login_required(role='question_setter')
def question_bank():
    # My private bank questions
    my_questions = query_db('''
        SELECT q.*, c.chapter_name 
        FROM questions q
        LEFT JOIN chapters c ON q.chapter_id = c.id
        WHERE q.is_bank = TRUE AND q.is_global = FALSE AND q.uploaded_by = %s
        ORDER BY q.created_at DESC
    ''', (session['user_id'],))
    
    # Global bank questions (excluding my own if already in my_questions)
    global_questions = query_db('''
        SELECT q.*, c.chapter_name, u.full_name as setter_name
        FROM questions q
        LEFT JOIN chapters c ON q.chapter_id = c.id
        LEFT JOIN users u ON q.uploaded_by = u.id
        WHERE q.is_bank = TRUE AND q.is_global = TRUE
        ORDER BY q.created_at DESC
    ''')
    
    if request.args.get('json'):
        def serialize_q(q):
            d = dict(q)
            if d.get('created_at'):
                d['created_at'] = d['created_at'].strftime('%Y-%m-%d %H:%M')
            if d.get('image_blob'):
                d['has_image'] = True
                d.pop('image_blob', None)
            else:
                d['has_image'] = False
            
            if d.get('resource_file_blob'):
                d['has_resource'] = True
                d['resource_name'] = d.get('resource_file_name')
                d.pop('resource_file_blob', None)
            else:
                d['has_resource'] = False
            return d
            
        return jsonify({
            'my_questions': [serialize_q(q) for q in my_questions],
            'global_questions': [serialize_q(q) for q in global_questions]
        })
        
    subjects = query_db('SELECT * FROM subjects ORDER BY subject_name')
    return render_template('question_setter/question_bank.html', 
                         my_questions=my_questions, 
                         global_questions=global_questions,
                         subjects=subjects)

@question_setter_bp.route('/add-to-bank', methods=['POST'])
@login_required(role='question_setter')
def add_to_bank():
    question_type = request.form['question_type']
    difficulty = request.form['difficulty_level']
    max_score = request.form['max_score']
    question_text = request.form.get('question_text', '')
    is_multiple = request.form.get('is_multiple_correct', False)
    is_global = request.form.get('is_global') == 'true'
    
    # Handle image upload
    image_blob = None
    image_mimetype = None
    if 'question_image' in request.files:
        file = request.files['question_image']
        if file and allowed_file(file.filename):
            file_data = file.read()
            from app.utils.crypto import encrypt_data
            image_blob = encrypt_data(file_data)
            image_mimetype = file.mimetype
    
    # Handle resource file upload
    resource_blob = None
    resource_mimetype = None
    resource_filename = None
    if 'resource_file' in request.files:
        rfile = request.files['resource_file']
        if rfile and rfile.filename:
            rfile_data = rfile.read()
            from app.utils.crypto import encrypt_data
            resource_blob = encrypt_data(rfile_data)
            resource_mimetype = rfile.mimetype
            resource_filename = secure_filename(rfile.filename)

    language = request.form.get('language', 'English')
    chapter_id = request.form.get('chapter_id')
    
    question_id = insert_db('''
        INSERT INTO questions 
        (question_type, image_blob, image_mimetype, difficulty_level, 
         max_score, question_text, is_multiple_correct, uploaded_by, language, chapter_id, is_bank, is_global,
         resource_file_blob, resource_file_mimetype, resource_file_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s)
        RETURNING id
    ''', (question_type, image_blob, image_mimetype, difficulty, max_score, 
          question_text, bool(is_multiple), session['user_id'], language, chapter_id, is_global,
          resource_blob, resource_mimetype, resource_filename))
    
    if question_type in ['theory', 'short_answer']:
        options = request.form.getlist('options[]')
        correct_answers = request.form.getlist('correct_answers[]')
        option_labels = ['A', 'B', 'C', 'D', 'E', 'F']
        for i, option in enumerate(options):
            if option.strip():
                insert_db('''
                    INSERT INTO question_options 
                    (question_id, option_text, is_correct, option_order)
                    VALUES (%s, %s, %s, %s)
                ''', (question_id, option, str(i) in correct_answers, option_labels[i]))
    
    flash('Question added to bank successfully!', 'success')
    return redirect(url_for('question_setter.question_bank'))

@question_setter_bp.route('/save-to-bank/<int:question_id>', methods=['POST'])
@login_required(role='question_setter')
def save_to_bank(question_id):
    is_global = request.form.get('is_global') == 'true'
    
    # Get original question
    q = query_db('SELECT * FROM questions WHERE id=%s AND uploaded_by=%s', 
                (question_id, session['user_id']), one=True)
    if not q:
        flash('Unauthorized or question not found.', 'error')
        return redirect(url_for('question_setter.dashboard'))
    
    # Create copy in bank
    new_q_id = insert_db('''
        INSERT INTO questions 
        (question_type, image_blob, image_mimetype, difficulty_level, 
         max_score, question_text, is_multiple_correct, uploaded_by, language, chapter_id, is_bank, is_global,
         resource_file_blob, resource_file_mimetype, resource_file_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s)
        RETURNING id
    ''', (q['question_type'], q['image_blob'], q['image_mimetype'], q['difficulty_level'], 
          q['max_score'], q['question_text'], q['is_multiple_correct'], session['user_id'], 
          q['language'], q['chapter_id'], is_global,
          q['resource_file_blob'], q['resource_file_mimetype'], q['resource_file_name']))
    
    # Copy options
    options = query_db('SELECT * FROM question_options WHERE question_id=%s', (question_id,))
    for opt in options:
        insert_db('''
            INSERT INTO question_options (question_id, option_text, is_correct, option_order)
            VALUES (%s, %s, %s, %s)
        ''', (new_q_id, opt['option_text'], opt['is_correct'], opt['option_order']))
    
    flash('Question saved to bank!', 'success')
    return redirect(url_for('question_setter.upload_questions', exam_id=q['exam_id']))

@question_setter_bp.route('/import-from-bank/<int:exam_id>', methods=['POST'])
@login_required(role='question_setter')
def import_from_bank(exam_id):
    exam = query_db('SELECT status FROM examinations WHERE id=%s', (exam_id,), one=True)
    if not exam:
        flash('Examination not found.', 'error')
        return redirect(url_for('question_setter.dashboard'))
        
    if exam['status'] != 'draft':
        flash('This examination is published and questions cannot be imported.', 'error')
        return redirect(url_for('question_setter.upload_questions', exam_id=exam_id))

    bank_question_id = request.form.get('bank_question_id')
    chapter_id = request.form.get('chapter_id')
    
    # Get bank question
    q = query_db('''
        SELECT * FROM questions 
        WHERE id=%s AND is_bank = TRUE 
        AND (uploaded_by=%s OR is_global=TRUE)
    ''', (bank_question_id, session['user_id']), one=True)
    
    if not q:
        flash('Question not found in bank.', 'error')
        return redirect(url_for('question_setter.upload_questions', exam_id=exam_id))
    
    # Create copy in exam
    new_q_id = insert_db('''
        INSERT INTO questions 
        (exam_id, question_type, image_blob, image_mimetype, difficulty_level, 
         max_score, question_text, is_multiple_correct, uploaded_by, language, chapter_id, is_bank,
         resource_file_blob, resource_file_mimetype, resource_file_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s, %s)
        RETURNING id
    ''', (exam_id, q['question_type'], q['image_blob'], q['image_mimetype'], q['difficulty_level'], 
          q['max_score'], q['question_text'], q['is_multiple_correct'], session['user_id'], 
          q['language'], chapter_id,
          q['resource_file_blob'], q['resource_file_mimetype'], q['resource_file_name']))
    
    # Copy options
    options = query_db('SELECT * FROM question_options WHERE question_id=%s', (bank_question_id,))
    for opt in options:
        insert_db('''
            INSERT INTO question_options (question_id, option_text, is_correct, option_order)
            VALUES (%s, %s, %s, %s)
        ''', (new_q_id, opt['option_text'], opt['is_correct'], opt['option_order']))
    
    flash('Question imported from bank!', 'success')
    return redirect(url_for('question_setter.upload_questions', exam_id=exam_id))