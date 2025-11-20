"""
Simple SQLite Database Layer
Lightweight alternative to MySQL for local development
"""

import sqlite3
import json
from datetime import datetime, timedelta
import os

class Database:
    def __init__(self, db_path='studyplanner.db'):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self._last_rowid = None  # Store last insert ID safely
        self.connect()
        self.init_schema()
    
    def connect(self):
        """Connect to SQLite database"""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row  # Return rows as dictionaries
            self.cursor = self.conn.cursor()
            print(f"✓ Connected to SQLite database: {self.db_path}")
        except Exception as e:
            print(f"✗ Database connection failed: {e}")
            raise
    
    def init_schema(self):
        """Create all tables if they don't exist"""
        try:
            # Users table
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    phone TEXT UNIQUE NOT NULL,
                    score INTEGER DEFAULT 0,
                    streak INTEGER DEFAULT 0,
                    preferences TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tasks table
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    deadline DATE NOT NULL,
                    importance TEXT DEFAULT 'medium',
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Sessions table
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    task_id INTEGER,
                    duration_hours REAL NOT NULL,
                    session_date DATE NOT NULL,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                )
            ''')
            
            # Flashcards table
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS flashcards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    topic TEXT,
                    module_name TEXT,
                    note_id INTEGER,
                    batch_id INTEGER,
                    source_path TEXT,
                    next_review DATE,
                    review_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Friends table
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS friends (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    friend_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (friend_id) REFERENCES users(id)
                )
            ''')
            
            # Notes table
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Class schedules table (for regular classes)
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS class_schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    day_of_week TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    location TEXT,
                    instructor TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Exam schedules table (for one-time exams)
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS exam_schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    subject TEXT NOT NULL,
                    exam_date DATE NOT NULL,
                    start_time TEXT NOT NULL,
                    duration_minutes INTEGER,
                    location TEXT,
                    exam_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Announcements table (for project deadlines, presentations, etc.)
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    announcement_type TEXT NOT NULL,
                    subject TEXT,
                    content TEXT NOT NULL,
                    deadline DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Study sessions table (for tracking study sessions and topics)
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS study_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    topic TEXT NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    duration_minutes INTEGER,
                    notes_image_path TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Flashcard reviews table (for spaced repetition tracking)
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS flashcard_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    flashcard_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    review_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    difficulty TEXT,
                    correct BOOLEAN,
                    next_review_date DATE,
                    FOREIGN KEY (flashcard_id) REFERENCES flashcards(id),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Study notes table (for storing PDF/text notes content)
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS study_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_type TEXT DEFAULT 'text',
                    source_path TEXT,
                    module_name TEXT,
                    topic TEXT,
                    study_session_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (study_session_id) REFERENCES study_sessions(id)
                )
            ''')
            
            # Study topics table (for organizing flashcards by topic)
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS study_topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    topic_name TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            # Flashcard batch table (group uploads into modules/topics)
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS flashcard_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    module_name TEXT,
                    topic TEXT,
                    note_id INTEGER,
                    source_path TEXT,
                    flashcard_count INTEGER DEFAULT 0,
                    quiz_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            # Quiz questions generated from flashcards
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS quiz_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    batch_id INTEGER,
                    question TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    correct_index INTEGER NOT NULL,
                    explanation TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            # Quiz attempts table for scoring and weekly points
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS quiz_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    batch_id INTEGER NOT NULL,
                    correct_count INTEGER,
                    total_questions INTEGER,
                    awarded_points INTEGER,
                    submitted_answers TEXT,
                    duration_ms INTEGER,
                    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            # Schema evolution for legacy databases
            self._add_column_if_missing('users', 'weekly_points', 'INTEGER DEFAULT 0')
            self._add_column_if_missing('users', 'weekly_points_reset_at', 'TEXT')
            self._add_column_if_missing('flashcards', 'topic', 'TEXT')
            self._add_column_if_missing('flashcards', 'module_name', 'TEXT')
            self._add_column_if_missing('flashcards', 'note_id', 'INTEGER')
            self._add_column_if_missing('flashcards', 'batch_id', 'INTEGER')
            self._add_column_if_missing('flashcards', 'source_path', 'TEXT')
            self._add_column_if_missing('study_notes', 'module_name', 'TEXT')
            self._add_column_if_missing('study_notes', 'topic', 'TEXT')
            
            self.conn.commit()
            print("✓ Database schema initialized successfully")
            
        except Exception as e:
            print(f"✗ Error initializing schema: {e}")
            raise

    def _column_exists(self, table, column):
        """Check if a column exists on the given table"""
        cursor = self.conn.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]
        cursor.close()
        return column in columns

    def _add_column_if_missing(self, table, column, definition):
        """Idempotently add a column to a table"""
        if not self._column_exists(table, column):
            self.cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            self.conn.commit()

    @staticmethod
    def _current_week_start():
        today = datetime.now().date()
        return today - timedelta(days=today.weekday())

    def _ensure_weekly_points_reset(self, user):
        """Reset weekly points counter if we crossed a calendar week boundary"""
        if not user:
            return user
        week_start = self._current_week_start().isoformat()
        reset_at = user.get('weekly_points_reset_at') if isinstance(user, dict) else None
        if not reset_at or reset_at < week_start:
            self.execute(
                "UPDATE users SET weekly_points = 0, weekly_points_reset_at = ? WHERE id = ?",
                (week_start, user['id'])
            )
            user = {**user, 'weekly_points': 0, 'weekly_points_reset_at': week_start}
        return user
    
    def execute(self, query, params=None):
        """Execute a query and return cursor"""
        try:
            cursor = self.conn.cursor()  # Create fresh cursor for each query
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            self.conn.commit()
            
            # Store last insert ID before cursor might be closed
            self._last_rowid = cursor.lastrowid
            self.cursor = cursor  # Keep reference for backward compatibility
            
            return cursor
        except Exception as e:
            print(f"✗ Query error: {e}")
            print(f"Query: {query}")
            raise
    
    def fetchone(self, query, params=None):
        """Fetch one result"""
        cursor = self.execute(query, params)
        row = cursor.fetchone()
        cursor.close()  # Close cursor after use
        return dict(row) if row else None
    
    def fetchall(self, query, params=None):
        """Fetch all results"""
        cursor = self.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()  # Close cursor after use
        return [dict(row) for row in rows]
    
    def lastrowid(self):
        """Get last inserted row ID"""
        return self._last_rowid
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            print("✓ Database connection closed")
    
    # ==================== USER OPERATIONS ====================
    
    def create_user(self, name, phone, preferences=None):
        """Create new user"""
        try:
            prefs_json = json.dumps(preferences) if preferences else json.dumps({})
            self.execute(
                "INSERT INTO users (name, phone, preferences) VALUES (?, ?, ?)",
                (name, phone, prefs_json)
            )
            return self.lastrowid()
        except Exception as e:
            print(f"Error creating user: {e}")
            return None
    
    def get_user_by_phone(self, phone):
        """Get user by phone number"""
        return self.fetchone("SELECT * FROM users WHERE phone = ?", (phone,))
    
    def get_user(self, user_id):
        """Get user by ID"""
        return self.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
    
    def get_user_by_id(self, user_id):
        """Alias for get_user() - for backward compatibility"""
        return self.get_user(user_id)
    
    def update_user_score(self, user_id, points):
        """Add points to user score"""
        try:
            user = self.get_user(user_id)
            if user:
                user = self._ensure_weekly_points_reset(user)
                new_score = user.get('score', 0) + points
                weekly_points = (user.get('weekly_points') or 0) + max(points, 0)
                week_start = user.get('weekly_points_reset_at') or self._current_week_start().isoformat()
                self.execute(
                    "UPDATE users SET score = ?, weekly_points = ?, weekly_points_reset_at = ? WHERE id = ?",
                    (new_score, weekly_points, week_start, user_id)
                )
                return new_score
        except Exception as e:
            print(f"Error updating score: {e}")
        return None
    
    def update_user_streak(self, user_id, streak):
        """Update user streak"""
        try:
            self.execute("UPDATE users SET streak = ? WHERE id = ?", (streak, user_id))
            return True
        except Exception as e:
            print(f"Error updating streak: {e}")
            return False
    
    # ==================== TASK OPERATIONS ====================
    
    def create_task(self, user_id, title, deadline=None, importance='medium', description=None, status='pending'):
        """Create new task"""
        try:
            self.execute(
                "INSERT INTO tasks (user_id, title, description, deadline, importance, status) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, title, description, deadline, importance, status)
            )
            return self.lastrowid()
        except Exception as e:
            print(f"Error creating task: {e}")
            return None
    
    def get_user_tasks(self, user_id, status=None):
        """Get user tasks, optionally filtered by status"""
        try:
            if status:
                return self.fetchall(
                    "SELECT * FROM tasks WHERE user_id = ? AND status = ? ORDER BY deadline ASC",
                    (user_id, status)
                )
            else:
                return self.fetchall(
                    "SELECT * FROM tasks WHERE user_id = ? ORDER BY deadline ASC",
                    (user_id,)
                )
        except Exception as e:
            print(f"Error getting tasks: {e}")
            return []
    
    def update_task_status(self, task_id, status):
        """Update task status"""
        try:
            completed_at = None
            if status == 'completed':
                completed_at = datetime.now().isoformat()
            
            self.execute(
                "UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?",
                (status, completed_at, task_id)
            )
            return True
        except Exception as e:
            print(f"Error updating task: {e}")
            return False
    
    # ==================== SESSION OPERATIONS ====================
    
    def create_session(self, user_id, task_id, duration_hours, session_date=None):
        """Create study session"""
        try:
            if session_date is None:
                session_date = datetime.now().date()
            
            self.execute(
                "INSERT INTO sessions (user_id, task_id, duration_hours, session_date) VALUES (?, ?, ?, ?)",
                (user_id, task_id, duration_hours, session_date)
            )
            return self.lastrowid()
        except Exception as e:
            print(f"Error creating session: {e}")
            return None
    
    def get_user_sessions(self, user_id, days=None, limit=50):
        """Get user study sessions with optional day-range filter"""
        try:
            if days is not None:
                cutoff = (datetime.now() - timedelta(days=days)).date()
                query = """
                    SELECT * FROM sessions
                    WHERE user_id = ? AND session_date >= ?
                    ORDER BY session_date DESC
                    LIMIT ?
                """
                params = (user_id, cutoff, limit)
            else:
                query = "SELECT * FROM sessions WHERE user_id = ? ORDER BY session_date DESC LIMIT ?"
                params = (user_id, limit)
            return self.fetchall(query, params)
        except Exception as e:
            print(f"Error getting sessions: {e}")
            return []
    
    # ==================== FLASHCARD OPERATIONS ====================
    
    def create_flashcard(self, user_id, question, answer, topic=None, module_name=None,
                         note_id=None, batch_id=None, source_path=None):
        """Create flashcard with optional metadata"""
        try:
            self.execute(
                """INSERT INTO flashcards
                       (user_id, question, answer, topic, module_name, note_id, batch_id, source_path)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, question, answer, topic, module_name, note_id, batch_id, source_path)
            )
            return self.lastrowid()
        except Exception as e:
            print(f"Error creating flashcard: {e}")
            return None
    
    def get_user_flashcards(self, user_id, limit=50, batch_id=None):
        """Get user flashcards, optionally filtered by batch"""
        try:
            if batch_id:
                return self.fetchall(
                    """SELECT * FROM flashcards
                           WHERE user_id = ? AND batch_id = ?
                           ORDER BY created_at DESC LIMIT ?""",
                    (user_id, batch_id, limit)
                )
            return self.fetchall(
                "SELECT * FROM flashcards WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            )
        except Exception as e:
            print(f"Error getting flashcards: {e}")
            return []

    # Backwards compatibility - some callers expect add_flashcard
    add_flashcard = create_flashcard

    # ==================== FLASHCARD BATCH & QUIZ OPERATIONS ====================

    def create_flashcard_batch(self, user_id, module_name=None, topic=None, note_id=None,
                               source_path=None, flashcard_count=0, quiz_count=0):
        """Create a logical batch that ties flashcards + quiz to one upload"""
        try:
            self.execute(
                """INSERT INTO flashcard_batches
                       (user_id, module_name, topic, note_id, source_path, flashcard_count, quiz_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, module_name, topic, note_id, source_path, flashcard_count, quiz_count)
            )
            return self.lastrowid()
        except Exception as e:
            print(f"Error creating flashcard batch: {e}")
            return None

    def update_flashcard_batch_counts(self, batch_id, flashcard_count=None, quiz_count=None):
        """Update aggregate counts for a batch"""
        try:
            updates = []
            params = []
            if flashcard_count is not None:
                updates.append("flashcard_count = ?")
                params.append(flashcard_count)
            if quiz_count is not None:
                updates.append("quiz_count = ?")
                params.append(quiz_count)
            if not updates:
                return False
            params.append(batch_id)
            self.execute(
                f"UPDATE flashcard_batches SET {', '.join(updates)} WHERE id = ?",
                tuple(params)
            )
            return True
        except Exception as e:
            print(f"Error updating batch counts: {e}")
            return False

    def get_flashcard_batches(self, user_id, limit=20):
        """Return most recent flashcard batches with quiz metadata"""
        try:
            return self.fetchall(
                """SELECT b.*,
                           (SELECT COUNT(*) FROM flashcards f WHERE f.batch_id = b.id) as flashcards_generated,
                           (SELECT COUNT(*) FROM quiz_questions q WHERE q.batch_id = b.id) as quiz_generated,
                           (SELECT MAX(completed_at) FROM quiz_attempts qa WHERE qa.batch_id = b.id) as last_attempt_at,
                           (SELECT MAX(CASE WHEN qa.total_questions > 0 THEN CAST(qa.correct_count AS REAL)/qa.total_questions ELSE 0 END)
                                FROM quiz_attempts qa WHERE qa.batch_id = b.id) as best_accuracy
                    FROM flashcard_batches b
                    WHERE b.user_id = ?
                    ORDER BY b.created_at DESC
                    LIMIT ?""",
                (user_id, limit)
            )
        except Exception as e:
            print(f"Error fetching flashcard batches: {e}")
            return []

    def save_quiz_question(self, user_id, batch_id, question, options, correct_index, explanation=None):
        """Persist generated quiz question options as JSON"""
        try:
            options_json = json.dumps(options)
            self.execute(
                """INSERT INTO quiz_questions
                       (user_id, batch_id, question, options_json, correct_index, explanation)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, batch_id, question, options_json, correct_index, explanation)
            )
            return self.lastrowid()
        except Exception as e:
            print(f"Error saving quiz question: {e}")
            return None

    def get_quiz_questions_for_batch(self, batch_id, limit=None):
        """Fetch quiz questions for a given batch"""
        try:
            if limit:
                return self.fetchall(
                    "SELECT * FROM quiz_questions WHERE batch_id = ? ORDER BY created_at DESC LIMIT ?",
                    (batch_id, limit)
                )
            return self.fetchall(
                "SELECT * FROM quiz_questions WHERE batch_id = ? ORDER BY created_at DESC",
                (batch_id,)
            )
        except Exception as e:
            print(f"Error getting quiz questions: {e}")
            return []

    def record_quiz_attempt(self, user_id, batch_id, correct_count, total_questions, awarded_points, submitted_answers, duration_ms=None):
        """Store quiz attempt results and return attempt id"""
        try:
            answers_json = json.dumps(submitted_answers)
            self.execute(
                """INSERT INTO quiz_attempts
                       (user_id, batch_id, correct_count, total_questions, awarded_points, submitted_answers, duration_ms)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, batch_id, correct_count, total_questions, awarded_points, answers_json, duration_ms)
            )
            return self.lastrowid()
        except Exception as e:
            print(f"Error recording quiz attempt: {e}")
            return None

    def get_latest_quiz_attempt(self, batch_id, user_id=None):
        """Fetch the latest quiz attempt for the user/batch pair"""
        try:
            if user_id:
                return self.fetchone(
                    """SELECT * FROM quiz_attempts WHERE batch_id = ? AND user_id = ?
                           ORDER BY completed_at DESC LIMIT 1""",
                    (batch_id, user_id)
                )
            return self.fetchone(
                "SELECT * FROM quiz_attempts WHERE batch_id = ? ORDER BY completed_at DESC LIMIT 1",
                (batch_id,)
            )
        except Exception as e:
            print(f"Error getting latest quiz attempt: {e}")
            return None

    def get_user_weekly_points(self, user_id):
        """Return the user weekly points tally"""
        user = self.get_user(user_id)
        if not user:
            return 0
        user = self._ensure_weekly_points_reset(user)
        return user.get('weekly_points', 0) or 0
    
    # ==================== STUDY SESSION OPERATIONS ====================
    
    def create_study_session(self, user_id, topic, start_time=None, notes_image_path=None):
        """Create a new study session"""
        try:
            if start_time is None:
                start_time = datetime.now().isoformat()
            
            self.execute(
                """INSERT INTO study_sessions (user_id, topic, start_time, notes_image_path, status) 
                   VALUES (?, ?, ?, ?, 'active')""",
                (user_id, topic, start_time, notes_image_path)
            )
            return self.lastrowid()
        except Exception as e:
            print(f"Error creating study session: {e}")
            return None
    
    def end_study_session(self, session_id):
        """End a study session and calculate duration"""
        try:
            session = self.fetchone("SELECT * FROM study_sessions WHERE id = ?", (session_id,))
            if not session:
                return False
            
            end_time = datetime.now()
            start_time = datetime.fromisoformat(session['start_time'])
            duration_minutes = int((end_time - start_time).total_seconds() / 60)
            
            self.execute(
                """UPDATE study_sessions 
                   SET end_time = ?, duration_minutes = ?, status = 'completed' 
                   WHERE id = ?""",
                (end_time.isoformat(), duration_minutes, session_id)
            )
            return True
        except Exception as e:
            print(f"Error ending study session: {e}")
            return False
    
    def get_active_study_session(self, user_id):
        """Get the active study session for a user"""
        try:
            return self.fetchone(
                "SELECT * FROM study_sessions WHERE user_id = ? AND status = 'active' ORDER BY start_time DESC LIMIT 1",
                (user_id,)
            )
        except Exception as e:
            print(f"Error getting active session: {e}")
            return None
    
    def get_user_study_sessions(self, user_id, limit=20):
        """Get user's study sessions"""
        try:
            return self.fetchall(
                "SELECT * FROM study_sessions WHERE user_id = ? ORDER BY start_time DESC LIMIT ?",
                (user_id, limit)
            )
        except Exception as e:
            print(f"Error getting study sessions: {e}")
            return []
    
    # ==================== FLASHCARD REVIEW OPERATIONS ====================
    
    def create_flashcard_review(self, flashcard_id, user_id, correct, difficulty='medium'):
        """Record a flashcard review"""
        try:
            # Calculate next review date based on spaced repetition
            from datetime import timedelta
            next_review = datetime.now().date()
            
            if difficulty == 'easy':
                next_review += timedelta(days=7)
            elif difficulty == 'medium':
                next_review += timedelta(days=3)
            else:  # hard
                next_review += timedelta(days=1)
            
            self.execute(
                """INSERT INTO flashcard_reviews 
                   (flashcard_id, user_id, difficulty, correct, next_review_date) 
                   VALUES (?, ?, ?, ?, ?)""",
                (flashcard_id, user_id, difficulty, correct, next_review.isoformat())
            )
            return self.lastrowid()
        except Exception as e:
            print(f"Error creating flashcard review: {e}")
            return None
    
    def get_flashcards_for_review(self, user_id, limit=10):
        """Get flashcards due for review"""
        try:
            today = datetime.now().date().isoformat()
            return self.fetchall(
                """SELECT f.* FROM flashcards f
                   LEFT JOIN flashcard_reviews fr ON f.id = fr.flashcard_id
                   WHERE f.user_id = ? 
                   AND (fr.next_review_date IS NULL OR fr.next_review_date <= ?)
                   ORDER BY f.created_at DESC
                   LIMIT ?""",
                (user_id, today, limit)
            )
        except Exception as e:
            print(f"Error getting flashcards for review: {e}")
            return []
    
    # ==================== STUDY TOPICS OPERATIONS ====================
    
    def create_study_topic(self, user_id, topic_name, description=None):
        """Create a study topic"""
        try:
            self.execute(
                "INSERT INTO study_topics (user_id, topic_name, description) VALUES (?, ?, ?)",
                (user_id, topic_name, description)
            )
            return self.lastrowid()
        except Exception as e:
            print(f"Error creating study topic: {e}")
            return None
    
    def get_user_study_topics(self, user_id):
        """Get user's study topics"""
        try:
            return self.fetchall(
                "SELECT * FROM study_topics WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            )
        except Exception as e:
            print(f"Error getting study topics: {e}")
            return []
    
    # ==================== STUDY NOTES OPERATIONS ====================
    
    def create_study_note(self, user_id, title, content, source_type='text', source_path=None,
                          study_session_id=None, module_name=None, topic=None):
        """Store study notes content extracted from PDF or text"""
        try:
            self.execute(
                """INSERT INTO study_notes 
                   (user_id, title, content, source_type, source_path, study_session_id, module_name, topic) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, title, content, source_type, source_path, study_session_id, module_name, topic)
            )
            return self.lastrowid()
        except Exception as e:
            print(f"Error creating study note: {e}")
            return None
    
    def get_user_study_notes(self, user_id, limit=50):
        """Get user's study notes"""
        try:
            return self.fetchall(
                """SELECT * FROM study_notes 
                   WHERE user_id = ? 
                   ORDER BY created_at DESC 
                   LIMIT ?""",
                (user_id, limit)
            )
        except Exception as e:
            print(f"Error getting study notes: {e}")
            return []
    
    def get_recent_study_notes(self, user_id, days=7):
        """Get study notes from last N days for quiz generation"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            return self.fetchall(
                """SELECT * FROM study_notes 
                   WHERE user_id = ? AND created_at >= ?
                   ORDER BY created_at DESC""",
                (user_id, cutoff_date)
            )
        except Exception as e:
            print(f"Error getting recent study notes: {e}")
            return []
    
    # ==================== SCHEDULE OPERATIONS ====================
    
    def create_class_schedule(self, user_id, day_of_week, subject, start_time, end_time, location=None, instructor=None):
        """Add recurring class to schedule"""
        try:
            self.execute(
                """INSERT INTO class_schedules 
                   (user_id, day_of_week, subject, start_time, end_time, location, instructor) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, day_of_week, subject, start_time, end_time, location, instructor)
            )
            return self.lastrowid()
        except Exception as e:
            print(f"Error creating class schedule: {e}")
            return None
    
    def get_class_schedules(self, user_id, day_of_week=None):
        """Get user's class schedules, optionally filtered by day"""
        try:
            if day_of_week:
                return self.fetchall(
                    "SELECT * FROM class_schedules WHERE user_id = ? AND day_of_week = ? ORDER BY start_time",
                    (user_id, day_of_week)
                )
            else:
                return self.fetchall(
                    "SELECT * FROM class_schedules WHERE user_id = ? ORDER BY day_of_week, start_time",
                    (user_id,)
                )
        except Exception as e:
            print(f"Error getting class schedules: {e}")
            return []

    def delete_class_schedules_for_days(self, user_id, day_names):
        """Remove stored class schedules for the provided day names."""
        if not day_names:
            return 0

        normalized_days = []
        for name in day_names:
            if not name:
                continue
            normalized_days.append(name.strip().title())

        if not normalized_days:
            return 0

        placeholders = ','.join('?' for _ in normalized_days)
        params = [user_id] + normalized_days

        try:
            cursor = self.execute(
                f"DELETE FROM class_schedules WHERE user_id = ? AND day_of_week IN ({placeholders})",
                params
            )
            deleted = cursor.rowcount
            cursor.close()
            return deleted or 0
        except Exception as e:
            print(f"Error clearing class schedules: {e}")
            return 0
    
    def create_exam_schedule(self, user_id, subject, exam_date, start_time, duration_minutes=None, location=None, exam_type=None):
        """Add exam to schedule"""
        try:
            self.execute(
                """INSERT INTO exam_schedules 
                   (user_id, subject, exam_date, start_time, duration_minutes, location, exam_type) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, subject, exam_date, start_time, duration_minutes, location, exam_type)
            )
            return self.lastrowid()
        except Exception as e:
            print(f"Error creating exam schedule: {e}")
            return None
    
    def get_exam_schedules(self, user_id, start_date=None, end_date=None):
        """Get user's exam schedules, optionally filtered by date range"""
        try:
            if start_date and end_date:
                return self.fetchall(
                    "SELECT * FROM exam_schedules WHERE user_id = ? AND exam_date BETWEEN ? AND ? ORDER BY exam_date, start_time",
                    (user_id, start_date, end_date)
                )
            elif start_date:
                return self.fetchall(
                    "SELECT * FROM exam_schedules WHERE user_id = ? AND exam_date >= ? ORDER BY exam_date, start_time",
                    (user_id, start_date)
                )
            else:
                return self.fetchall(
                    "SELECT * FROM exam_schedules WHERE user_id = ? ORDER BY exam_date, start_time",
                    (user_id,)
                )
        except Exception as e:
            print(f"Error getting exam schedules: {e}")
            return []
    
    def create_announcement(self, user_id, announcement_type, content, subject=None, deadline=None):
        """Add announcement (project, presentation, etc.)"""
        try:
            self.execute(
                """INSERT INTO announcements 
                   (user_id, announcement_type, subject, content, deadline) 
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, announcement_type, subject, content, deadline)
            )
            return self.lastrowid()
        except Exception as e:
            print(f"Error creating announcement: {e}")
            return None
    
    def get_announcements(self, user_id, start_date=None, end_date=None):
        """Get user's announcements, optionally filtered by deadline range"""
        try:
            if start_date and end_date:
                return self.fetchall(
                    "SELECT * FROM announcements WHERE user_id = ? AND deadline BETWEEN ? AND ? ORDER BY deadline",
                    (user_id, start_date, end_date)
                )
            elif start_date:
                return self.fetchall(
                    "SELECT * FROM announcements WHERE user_id = ? AND deadline >= ? ORDER BY deadline",
                    (user_id, start_date)
                )
            else:
                return self.fetchall(
                    "SELECT * FROM announcements WHERE user_id = ? ORDER BY deadline",
                    (user_id,)
                )
        except Exception as e:
            print(f"Error getting announcements: {e}")
            return []
    
    def delete_class_schedule(self, schedule_id):
        """Delete a class schedule"""
        try:
            self.execute("DELETE FROM class_schedules WHERE id = ?", (schedule_id,))
            return True
        except Exception as e:
            print(f"Error deleting class schedule: {e}")
            return False
    
    def delete_exam_schedule(self, exam_id):
        """Delete an exam schedule"""
        try:
            self.execute("DELETE FROM exam_schedules WHERE id = ?", (exam_id,))
            return True
        except Exception as e:
            print(f"Error deleting exam schedule: {e}")
            return False
    
    def delete_announcement(self, announcement_id):
        """Delete an announcement"""
        try:
            self.execute("DELETE FROM announcements WHERE id = ?", (announcement_id,))
            return True
        except Exception as e:
            print(f"Error deleting announcement: {e}")
            return False

    
    def update_flashcard_progress(self, card_id, progress_level):
        """Update flashcard progress after review"""
        try:
            self.execute(
                "UPDATE flashcards SET review_count = review_count + 1 WHERE id = ?",
                (card_id,)
            )
            return True
        except Exception as e:
            print(f"Error updating flashcard: {e}")
            return False
    
    def get_leaderboard(self, user_id, limit=10):
        """Get leaderboard of top users by score"""
        try:
            return self.fetchall(
                """SELECT id, name, score, streak 
                   FROM users 
                   ORDER BY score DESC, streak DESC 
                   LIMIT ?""",
                (limit,)
            )
        except Exception as e:
            print(f"Error getting leaderboard: {e}")
            return []

    def ensure_leaderboard_seed_data(self):
        """Ensure a set of demo users exist for leaderboard displays."""
        dummy_entries = [
            {"name": "Ananya Rao", "phone": "dummy_leader_1", "score": 820, "streak": 6},
            {"name": "Kabir Singh", "phone": "dummy_leader_2", "score": 760, "streak": 4},
            {"name": "Meera Patel", "phone": "dummy_leader_3", "score": 710, "streak": 5},
            {"name": "Rahul Verma", "phone": "dummy_leader_4", "score": 650, "streak": 3},
            {"name": "Sara Iyer", "phone": "dummy_leader_5", "score": 590, "streak": 2},
        ]

        created = 0
        for entry in dummy_entries:
            if not self.get_user_by_phone(entry["phone"]):
                self.execute(
                    "INSERT INTO users (name, phone, score, streak, preferences) VALUES (?, ?, ?, ?, ?)",
                    (
                        entry["name"],
                        entry["phone"],
                        entry["score"],
                        entry["streak"],
                        json.dumps({"seeded": True})
                    )
                )
                created += 1

        if created:
            print(f"✓ Seeded {created} leaderboard placeholder user(s)")
        return created

# Singleton instance
_db_instance = None

def get_db():
    """Get database singleton instance"""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance
