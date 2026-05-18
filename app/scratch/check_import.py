from flask import Flask
from app.routes.student import student_bp

app = Flask(__name__)
app.register_blueprint(student_bp)
print("Import successful")
