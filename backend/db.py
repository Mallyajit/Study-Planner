"""
Database Module - MySQL Connection & Schema Management
Handles all database operations for the Study Planner AI backend.
"""

import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv
import json

load_dotenv()

class Database:
    """MySQL Database Handler with connection pooling"""
    
    def __init__(self):
        """Initialize database connection from environment variables"""
        self.host = os.getenv("MYSQL_HOST", "localhost")
        self.user = os.getenv("MYSQL_USER", "root")
        self.password = os.getenv("MYSQL_PASSWORD", "")
        self.database = os.getenv("MYSQL_DB", "study_planner_db")
        self.connection = None
        self.cursor = None
    
    def connect(self):
        """Establish connection to MySQL database"""
        try:
            self.connection = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                autocommit=False
            )
            self.cursor = self.connection.cursor(dictionary=True)
            print(f"✓ Connected to MySQL database: {self.database}")
            return True
        except Error as e:
            print(f"✗ Database connection failed: {e}")
            return False
    
    def disconnect(self):
        """Close database connection"""
        if self.cursor:
            self.cursor.close()
        if self.connection and self.connection.is_connected():
            self.connection.close()
            print("✓ Database connection closed")
    
    def create_database(self):
        """Create database if it doesn't exist"""
        try:
            temp_conn = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password
            )
            temp_cursor = temp_conn.cursor()
            temp_cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.database}")
            print(f"✓ Database '{self.database}' created/verified")
            temp_cursor.close()
            temp_conn.close()
        except Error as e:
            print(f"✗ Error creating database: {e}")
    
    def init_schema(self):
        """Initialize all database tables"""
        
        schema_queries = [
            # Users table
            """
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                phone VARCHAR(20) UNIQUE NOT NULL,
                preferences_json TEXT,
                streak INT DEFAULT 0,
                score INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_phone (phone),
                INDEX idx_score (score)
            )
            """,
            
            # Tasks table
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                title VARCHAR(255) NOT NULL,
                deadline DATETIME,
                status ENUM('pending', 'in_progress', 'completed', 'overdue') DEFAULT 'pending',
                importance ENUM('low', 'medium', 'high', 'urgent') DEFAULT 'medium',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_status (user_id, status),
                INDEX idx_deadline (deadline)
            )
            """,
            
            # Study sessions table
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                date DATE NOT NULL,
                completed_tasks INT DEFAULT 0,
                hours_studied DECIMAL(5,2) DEFAULT 0.00,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_date (user_id, date)
            )
            """,
            
            # Friends/Social table
            """
            CREATE TABLE IF NOT EXISTS friends (
                user_id INT NOT NULL,
                friend_id INT NOT NULL,
                status ENUM('pending', 'accepted', 'blocked') DEFAULT 'accepted',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, friend_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (friend_id) REFERENCES users(id) ON DELETE CASCADE,
                CHECK (user_id != friend_id)
            )
            """,
            
            # Flashcards table
            """
            CREATE TABLE IF NOT EXISTS flashcards (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                progress_level INT DEFAULT 0,
                last_reviewed TIMESTAMP NULL,
                review_count INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_progress (user_id, progress_level)
            )
            """,
            
            # Notes table
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                filepath VARCHAR(500) NOT NULL,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user (user_id)
            )
            """
        ]
        
        try:
            for query in schema_queries:
                self.cursor.execute(query)
            self.connection.commit()
            print("✓ Database schema initialized successfully")
            return True
        except Error as e:
            print(f"✗ Error initializing schema: {e}")
            self.connection.rollback()
            return False
    
    # ==================== USER OPERATIONS ====================
    
    def create_user(self, name, phone, preferences=None):
        """Create a new user"""
        try:
            query = """
            INSERT INTO users (name, phone, preferences_json)
            VALUES (%s, %s, %s)
            """
            prefs_json = json.dumps(preferences) if preferences else None
            self.cursor.execute(query, (name, phone, prefs_json))
            self.connection.commit()
            return self.cursor.lastrowid
        except Error as e:
            print(f"Error creating user: {e}")
            self.connection.rollback()
            return None
    
    def get_user_by_phone(self, phone):
        """Get user by phone number"""
        try:
            query = "SELECT * FROM users WHERE phone = %s"
            self.cursor.execute(query, (phone,))
            return self.cursor.fetchone()
        except Error as e:
            print(f"Error fetching user: {e}")
            return None
    
    def get_user_by_id(self, user_id):
        """Get user by ID"""
        try:
            query = "SELECT * FROM users WHERE id = %s"
            self.cursor.execute(query, (user_id,))
            return self.cursor.fetchone()
        except Error as e:
            print(f"Error fetching user: {e}")
            return None
    
    def update_user_score(self, user_id, points):
        """Add points to user's score"""
        try:
            query = "UPDATE users SET score = score + %s WHERE id = %s"
            self.cursor.execute(query, (points, user_id))
            self.connection.commit()
            return True
        except Error as e:
            print(f"Error updating score: {e}")
            self.connection.rollback()
            return False
    
    def update_user_streak(self, user_id, streak):
        """Update user's streak"""
        try:
            query = "UPDATE users SET streak = %s WHERE id = %s"
            self.cursor.execute(query, (streak, user_id))
            self.connection.commit()
            return True
        except Error as e:
            print(f"Error updating streak: {e}")
            self.connection.rollback()
            return False
    
    # ==================== TASK OPERATIONS ====================
    
    def create_task(self, user_id, title, deadline=None, importance='medium', description=None, status='pending'):
        """Create a new task"""
        try:
            query = """
            INSERT INTO tasks (user_id, title, description, deadline, importance, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            self.cursor.execute(query, (user_id, title, description, deadline, importance, status))
            self.connection.commit()
            return self.cursor.lastrowid
        except Error as e:
            print(f"Error creating task: {e}")
            self.connection.rollback()
            return None
    
    def get_user_tasks(self, user_id, status=None):
        """Get all tasks for a user, optionally filtered by status"""
        try:
            if status:
                query = "SELECT * FROM tasks WHERE user_id = %s AND status = %s ORDER BY deadline"
                self.cursor.execute(query, (user_id, status))
            else:
                query = "SELECT * FROM tasks WHERE user_id = %s ORDER BY deadline"
                self.cursor.execute(query, (user_id,))
            return self.cursor.fetchall()
        except Error as e:
            print(f"Error fetching tasks: {e}")
            return []
    
    def update_task_status(self, task_id, status):
        """Update task status"""
        try:
            query = "UPDATE tasks SET status = %s"
            if status == 'completed':
                query += ", completed_at = NOW()"
            query += " WHERE id = %s"
            self.cursor.execute(query, (status, task_id))
            self.connection.commit()
            return True
        except Error as e:
            print(f"Error updating task: {e}")
            self.connection.rollback()
            return False
    
    # ==================== SESSION OPERATIONS ====================
    
    def create_session(self, user_id, date, completed_tasks=0, hours_studied=0, notes=None):
        """Log a study session"""
        try:
            query = """
            INSERT INTO sessions (user_id, date, completed_tasks, hours_studied, notes)
            VALUES (%s, %s, %s, %s, %s)
            """
            self.cursor.execute(query, (user_id, date, completed_tasks, hours_studied, notes))
            self.connection.commit()
            return self.cursor.lastrowid
        except Error as e:
            print(f"Error creating session: {e}")
            self.connection.rollback()
            return None
    
    def get_user_sessions(self, user_id, days=30):
        """Get user's recent sessions"""
        try:
            query = """
            SELECT * FROM sessions 
            WHERE user_id = %s AND date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            ORDER BY date DESC
            """
            self.cursor.execute(query, (user_id, days))
            return self.cursor.fetchall()
        except Error as e:
            print(f"Error fetching sessions: {e}")
            return []
    
    # ==================== FLASHCARD OPERATIONS ====================
    
    def create_flashcard(self, user_id, question, answer):
        """Create a new flashcard"""
        try:
            query = """
            INSERT INTO flashcards (user_id, question, answer)
            VALUES (%s, %s, %s)
            """
            self.cursor.execute(query, (user_id, question, answer))
            self.connection.commit()
            return self.cursor.lastrowid
        except Error as e:
            print(f"Error creating flashcard: {e}")
            self.connection.rollback()
            return None
    
    def get_user_flashcards(self, user_id, limit=10):
        """Get flashcards for review (prioritize low progress)"""
        try:
            query = """
            SELECT * FROM flashcards 
            WHERE user_id = %s 
            ORDER BY progress_level ASC, last_reviewed ASC
            LIMIT %s
            """
            self.cursor.execute(query, (user_id, limit))
            return self.cursor.fetchall()
        except Error as e:
            print(f"Error fetching flashcards: {e}")
            return []
    
    def update_flashcard_progress(self, flashcard_id, progress_level):
        """Update flashcard progress after review"""
        try:
            query = """
            UPDATE flashcards 
            SET progress_level = %s, last_reviewed = NOW(), review_count = review_count + 1
            WHERE id = %s
            """
            self.cursor.execute(query, (progress_level, flashcard_id))
            self.connection.commit()
            return True
        except Error as e:
            print(f"Error updating flashcard: {e}")
            self.connection.rollback()
            return False
    
    # ==================== SOCIAL/FRIENDS OPERATIONS ====================
    
    def add_friend(self, user_id, friend_id):
        """Add a friend connection"""
        try:
            query = "INSERT INTO friends (user_id, friend_id) VALUES (%s, %s)"
            self.cursor.execute(query, (user_id, friend_id))
            # Add reciprocal relationship
            self.cursor.execute(query, (friend_id, user_id))
            self.connection.commit()
            return True
        except Error as e:
            print(f"Error adding friend: {e}")
            self.connection.rollback()
            return False
    
    def get_leaderboard(self, user_id, limit=10):
        """Get leaderboard (user's friends + self)"""
        try:
            query = """
            SELECT u.id, u.name, u.score, u.streak
            FROM users u
            WHERE u.id = %s 
            OR u.id IN (
                SELECT friend_id FROM friends WHERE user_id = %s AND status = 'accepted'
            )
            ORDER BY u.score DESC, u.streak DESC
            LIMIT %s
            """
            self.cursor.execute(query, (user_id, user_id, limit))
            return self.cursor.fetchall()
        except Error as e:
            print(f"Error fetching leaderboard: {e}")
            return []
    
    # ==================== NOTES OPERATIONS ====================
    
    def save_note(self, user_id, filepath, tags=None):
        """Save note metadata"""
        try:
            query = "INSERT INTO notes (user_id, filepath, tags) VALUES (%s, %s, %s)"
            tags_str = json.dumps(tags) if tags else None
            self.cursor.execute(query, (user_id, filepath, tags_str))
            self.connection.commit()
            return self.cursor.lastrowid
        except Error as e:
            print(f"Error saving note: {e}")
            self.connection.rollback()
            return None
    
    def get_user_notes(self, user_id):
        """Get all notes for a user"""
        try:
            query = "SELECT * FROM notes WHERE user_id = %s ORDER BY created_at DESC"
            self.cursor.execute(query, (user_id,))
            return self.cursor.fetchall()
        except Error as e:
            print(f"Error fetching notes: {e}")
            return []


# Singleton instance
_db_instance = None

def get_db():
    """Get or create database singleton instance"""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
        _db_instance.create_database()
        _db_instance.connect()
        _db_instance.init_schema()
    return _db_instance


if __name__ == "__main__":
    # Test database setup
    db = get_db()
    print("\n✓ Database module initialized successfully!")
    print("All tables created and ready to use.")
    db.disconnect()
