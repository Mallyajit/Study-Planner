"""
Simple SQLite Database Layer
Lightweight alternative to MySQL for local development
"""

import sqlite3
import json
from datetime import datetime
import os

class Database:
    def __init__(self, db_path='studyplanner.db'):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
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
            
            self.conn.commit()
            print("✓ Database schema initialized successfully")
            
        except Exception as e:
            print(f"✗ Error initializing schema: {e}")
            raise
    
    def execute(self, query, params=None):
        """Execute a query and return cursor"""
        try:
            cursor = self.conn.cursor()  # Create fresh cursor for each query
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            self.conn.commit()
            
            # Update class cursor with last insert ID
            self.cursor = cursor
            
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
        return self.cursor.lastrowid
    
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
                new_score = user.get('score', 0) + points
                self.execute("UPDATE users SET score = ? WHERE id = ?", (new_score, user_id))
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
    
    def get_user_sessions(self, user_id, limit=50):
        """Get user study sessions"""
        try:
            return self.fetchall(
                "SELECT * FROM sessions WHERE user_id = ? ORDER BY session_date DESC LIMIT ?",
                (user_id, limit)
            )
        except Exception as e:
            print(f"Error getting sessions: {e}")
            return []
    
    # ==================== FLASHCARD OPERATIONS ====================
    
    def create_flashcard(self, user_id, question, answer):
        """Create flashcard"""
        try:
            self.execute(
                "INSERT INTO flashcards (user_id, question, answer) VALUES (?, ?, ?)",
                (user_id, question, answer)
            )
            return self.lastrowid()
        except Exception as e:
            print(f"Error creating flashcard: {e}")
            return None
    
    def get_user_flashcards(self, user_id, limit=50):
        """Get user flashcards"""
        try:
            return self.fetchall(
                "SELECT * FROM flashcards WHERE user_id = ? ORDER BY next_review ASC LIMIT ?",
                (user_id, limit)
            )
        except Exception as e:
            print(f"Error getting flashcards: {e}")
            return []
    
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

# Singleton instance
_db_instance = None

def get_db():
    """Get database singleton instance"""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance
