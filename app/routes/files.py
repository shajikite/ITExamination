import io
from flask import Blueprint, session, abort, send_file
from app.database.db import query_db
from app.utils.crypto import decrypt_data
from app.routes.auth import login_required

files_bp = Blueprint('files', __name__)

@files_bp.route('/question/<int:question_id>')
@login_required()
def get_question_image(question_id):
    # Only authenticated users can fetch question images.
    # Note: Additional checks can be added if we only want assigned students/invigilators/setters to see it.
    question = query_db('SELECT image_blob, image_mimetype FROM questions WHERE id = %s', (question_id,), one=True)
    if not question or not question['image_blob']:
        abort(404)
        
    decrypted_data = decrypt_data(question['image_blob'].tobytes() if hasattr(question['image_blob'], 'tobytes') else bytes(question['image_blob']))
    if not decrypted_data:
        abort(404)
        
    return send_file(
        io.BytesIO(decrypted_data),
        mimetype=question['image_mimetype'] or 'image/png'
    )

@files_bp.route('/submission/<int:submission_id>')
@login_required()
def get_submission_file(submission_id):
    # Fetch submission
    submission = query_db('''
        SELECT file_blob, file_mimetype, file_name, student_exam_id 
        FROM student_practical_submissions 
        WHERE id = %s
    ''', (submission_id,), one=True)
    
    if not submission or not submission['file_blob']:
        abort(404)
        
    # Verify authorization
    user_type = session.get('user_type')
    user_id = session.get('user_id')
    
    # Allow invigilators, state_admin, school_admin, or the student themselves
    if user_type == 'student':
        # Check if the submission belongs to the current student
        student_exam = query_db('SELECT student_id FROM student_exams WHERE id = %s', 
                                (submission['student_exam_id'],), one=True)
        if not student_exam or student_exam['student_id'] != user_id:
            abort(403)
            
    decrypted_data = decrypt_data(submission['file_blob'].tobytes() if hasattr(submission['file_blob'], 'tobytes') else bytes(submission['file_blob']))
    if not decrypted_data:
        abort(404)
        
    return send_file(
        io.BytesIO(decrypted_data),
        mimetype=submission['file_mimetype'] or 'application/octet-stream',
        as_attachment=True,
        download_name=submission['file_name']
    )

@files_bp.route('/option/<int:option_id>')
@login_required()
def get_option_image(option_id):
    option = query_db('SELECT option_image_blob, option_image_mimetype FROM question_options WHERE id = %s', (option_id,), one=True)
    if not option or not option['option_image_blob']:
        abort(404)
        
    decrypted_data = decrypt_data(option['option_image_blob'].tobytes() if hasattr(option['option_image_blob'], 'tobytes') else bytes(option['option_image_blob']))
    if not decrypted_data:
        abort(404)
        
    return send_file(
        io.BytesIO(decrypted_data),
        mimetype=option['option_image_mimetype'] or 'image/png'
    )

@files_bp.route('/resource/<int:question_id>')
@login_required()
def get_resource_file(question_id):
    question = query_db('SELECT resource_file_blob, resource_file_mimetype, resource_file_name FROM questions WHERE id = %s', (question_id,), one=True)
    if not question or not question['resource_file_blob']:
        abort(404)
        
    decrypted_data = decrypt_data(question['resource_file_blob'].tobytes() if hasattr(question['resource_file_blob'], 'tobytes') else bytes(question['resource_file_blob']))
    if not decrypted_data:
        abort(404)
        
    return send_file(
        io.BytesIO(decrypted_data),
        mimetype=question['resource_file_mimetype'] or 'application/octet-stream',
        as_attachment=True,
        download_name=question['resource_file_name']
    )

