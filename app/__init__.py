from flask import Flask
from app.database.db import init_db

def create_app():
    app = Flask(__name__)
    app.config.from_object('app.config.Config')
    
    # Initialize database
    init_db(app)
    
    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.state_admin import state_admin_bp
    from app.routes.question_setter import question_setter_bp
    from app.routes.school_admin import school_admin_bp
    from app.routes.invigilator import invigilator_bp
    from app.routes.student import student_bp
    from app.routes.files import files_bp
    from app.routes.revaluator import revaluator_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(state_admin_bp, url_prefix='/state-admin')
    app.register_blueprint(question_setter_bp, url_prefix='/question-setter')
    app.register_blueprint(school_admin_bp, url_prefix='/school-admin')
    app.register_blueprint(invigilator_bp, url_prefix='/invigilator')
    app.register_blueprint(student_bp, url_prefix='/student')
    app.register_blueprint(files_bp, url_prefix='/files')
    app.register_blueprint(revaluator_bp, url_prefix='/revaluator')
    
    @app.context_processor
    def inject_invigilator_stats():
        from flask import session
        from app.database.db import query_db
        if session.get('user_type') == 'invigilator' and session.get('school_id'):
            try:
                count = query_db('''
                    SELECT COUNT(*) as count
                    FROM student_practical_submissions sp
                    JOIN student_exams se ON sp.student_exam_id = se.id
                    WHERE se.school_id = %s AND sp.score_obtained IS NULL
                ''', (session['school_id'],), one=True)
                return {'invigilator_pending_count': count['count'] if count else 0}
            except:
                return {'invigilator_pending_count': 0}
        return {'invigilator_pending_count': 0}
    
    @app.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('auth.login'))
        
    return app