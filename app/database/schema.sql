-- Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    email VARCHAR(200),
    phone VARCHAR(20),
    user_type VARCHAR(20) CHECK (user_type IN ('state_admin', 'question_setter', 'school_admin', 'invigilator', 'student')) NOT NULL,
    school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
    class_id INTEGER REFERENCES classes(id),
    medium VARCHAR(20) DEFAULT 'English' CHECK (medium IN ('English', 'Malayalam', 'Kannada', 'Tamil')),
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Schools table
CREATE TABLE schools (
    id SERIAL PRIMARY KEY,
    school_name VARCHAR(255) NOT NULL,
    school_code VARCHAR(50) UNIQUE NOT NULL,
    address TEXT,
    phone VARCHAR(20),
    email VARCHAR(200),
    state_admin_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Classes
CREATE TABLE classes (
    id SERIAL PRIMARY KEY,
    class_name VARCHAR(100) NOT NULL,
    description TEXT
);

-- Subjects
CREATE TABLE subjects (
    id SERIAL PRIMARY KEY,
    subject_name VARCHAR(200) NOT NULL,
    subject_code VARCHAR(50) UNIQUE NOT NULL,
    description TEXT
);

-- Chapters
CREATE TABLE chapters (
    id SERIAL PRIMARY KEY,
    subject_id INTEGER REFERENCES subjects(id),
    chapter_name VARCHAR(255) NOT NULL,
    chapter_number INTEGER,
    description TEXT
);

-- Examinations
CREATE TABLE examinations (
    id SERIAL PRIMARY KEY,
    exam_name VARCHAR(255) NOT NULL,
    class_id INTEGER REFERENCES classes(id),
    subject_id INTEGER REFERENCES subjects(id),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    duration_minutes INTEGER NOT NULL,
    total_theory_questions INTEGER NOT NULL,
    total_short_answer_questions INTEGER DEFAULT 0,
    total_practical_questions INTEGER NOT NULL,
    easy_questions INTEGER,
    average_questions INTEGER,
    difficult_questions INTEGER,
    max_score INTEGER DEFAULT 0,
    is_multiple_correct_allowed BOOLEAN DEFAULT FALSE,
    created_by INTEGER REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'ongoing', 'completed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Exam Chapters (many-to-many)
CREATE TABLE exam_chapters (
    id SERIAL PRIMARY KEY,
    exam_id INTEGER REFERENCES examinations(id) ON DELETE CASCADE,
    chapter_id INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    easy_count INTEGER DEFAULT 0,
    average_count INTEGER DEFAULT 0,
    difficult_count INTEGER DEFAULT 0
);

-- Question Setters Assignment
CREATE TABLE question_setter_assignments (
    id SERIAL PRIMARY KEY,
    exam_id INTEGER REFERENCES examinations(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    assigned_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Questions
CREATE TABLE questions (
    id SERIAL PRIMARY KEY,
    exam_id INTEGER REFERENCES examinations(id) ON DELETE CASCADE,
    question_type VARCHAR(20) CHECK (question_type IN ('theory', 'practical', 'short_answer')) NOT NULL,
    question_image_path VARCHAR(500),
    image_blob BYTEA,
    image_mimetype VARCHAR(50),
    difficulty_level VARCHAR(20) CHECK (difficulty_level IN ('easy', 'average', 'difficult')),
    max_score INTEGER NOT NULL,
    question_text TEXT,
    is_multiple_correct BOOLEAN DEFAULT FALSE,
    uploaded_by INTEGER REFERENCES users(id),
    chapter_id INTEGER REFERENCES chapters(id) ON DELETE SET NULL,
    language VARCHAR(20) DEFAULT 'English' CHECK (language IN ('English', 'Malayalam', 'Kannada', 'Tamil')),
    resource_file_blob BYTEA,
    resource_file_name VARCHAR(255),
    resource_file_mimetype VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- MCQ Options
CREATE TABLE question_options (
    id SERIAL PRIMARY KEY,
    question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,
    option_text TEXT NOT NULL,
    option_image_path VARCHAR(500),
    is_correct BOOLEAN DEFAULT FALSE,
    option_order CHAR(1) -- A, B, C, D etc.
);

-- Student-Exam Assignment
CREATE TABLE student_exams (
    id SERIAL PRIMARY KEY,
    student_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    exam_id INTEGER REFERENCES examinations(id) ON DELETE CASCADE,
    school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
    assigned_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    theory_status VARCHAR(20) DEFAULT 'pending' CHECK (theory_status IN ('pending', 'in_progress', 'completed')),
    practical_status VARCHAR(20) DEFAULT 'pending' CHECK (practical_status IN ('pending', 'in_progress', 'completed')),
    theory_start_time TIMESTAMP,
    theory_end_time TIMESTAMP,
    practical_start_time TIMESTAMP,
    practical_end_time TIMESTAMP,
    active_time_used INTEGER DEFAULT 0,
    last_heartbeat_time TIMESTAMP
);

-- Student Theory Answers
CREATE TABLE student_theory_answers (
    id SERIAL PRIMARY KEY,
    student_exam_id INTEGER REFERENCES student_exams(id) ON DELETE CASCADE,
    question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,
    selected_options TEXT, -- Comma-separated option IDs
    is_correct BOOLEAN,
    score_obtained INTEGER DEFAULT 0,
    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Student Practical Submissions
CREATE TABLE student_practical_submissions (
    id SERIAL PRIMARY KEY,
    student_exam_id INTEGER REFERENCES student_exams(id) ON DELETE CASCADE,
    question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,
    file_path VARCHAR(500),
    file_name VARCHAR(255),
    file_blob BYTEA,
    file_mimetype VARCHAR(50),
    evaluated_by INTEGER REFERENCES users(id),
    score_obtained INTEGER,
    remarks TEXT,
    submission_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    evaluation_time TIMESTAMP
);

-- Mark Lists
CREATE TABLE mark_lists (
    id SERIAL PRIMARY KEY,
    student_exam_id INTEGER REFERENCES student_exams(id) ON DELETE CASCADE,
    theory_score INTEGER DEFAULT 0,
    practical_score INTEGER DEFAULT 0,
    total_score INTEGER DEFAULT 0,
    percentage DECIMAL(5,2),
    grade VARCHAR(5),
    prepared_by INTEGER REFERENCES users(id),
    prepared_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'finalized'))
);

-- Sessions for exam lockdown
CREATE TABLE exam_sessions (
    id SERIAL PRIMARY KEY,
    student_exam_id INTEGER REFERENCES student_exams(id),
    session_token VARCHAR(255) UNIQUE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);