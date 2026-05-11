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
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(state_admin_bp, url_prefix='/state-admin')
    app.register_blueprint(question_setter_bp, url_prefix='/question-setter')
    app.register_blueprint(school_admin_bp, url_prefix='/school-admin')
    app.register_blueprint(invigilator_bp, url_prefix='/invigilator')
    app.register_blueprint(student_bp, url_prefix='/student')
    
    return app