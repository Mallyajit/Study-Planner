"""
Progress Module - Gamification & Scoring Logic
Handles streaks, points, achievements, and user progress tracking.

FLOW: User Action → Progress Update → Database → Leaderboard Refresh
"""

from datetime import datetime, timedelta
import json


class ProgressTracker:
    """Gamification engine for tracking scores, streaks, and achievements"""
    
    # Points configuration
    POINTS = {
        'task_completed_on_time': 50,
        'task_completed_early': 100,
        'task_completed_late': 20,
        'study_session_1h': 10,
        'study_session_2h': 25,
        'study_session_3h': 50,
        'flashcard_review': 5,
        'daily_streak': 30,
        'weekly_goal_met': 200,
        'perfect_week': 500,
    }
    
    # Achievement thresholds
    ACHIEVEMENTS = {
        'first_task': {'threshold': 1, 'reward': 25, 'title': 'Getting Started'},
        'streak_7': {'threshold': 7, 'reward': 100, 'title': 'Week Warrior'},
        'streak_30': {'threshold': 30, 'reward': 500, 'title': 'Month Master'},
        'tasks_50': {'threshold': 50, 'reward': 250, 'title': 'Task Slayer'},
        'score_1000': {'threshold': 1000, 'reward': 0, 'title': 'Point Collector'},
    }
    
    def __init__(self, db):
        """
        Initialize progress tracker with database connection
        
        Args:
            db: Database instance for queries
        """
        self.db = db
        print("✓ Progress Tracker initialized")
    
    def calculate_task_points(self, task, completion_time):
        """
        Calculate points earned for completing a task
        
        Args:
            task: dict with task details (deadline, importance)
            completion_time: datetime when task was completed
        
        Returns:
            int: points earned
        """
        base_points = self.POINTS['task_completed_on_time']
        
        # Check if completed early, on time, or late
        if task.get('deadline'):
            deadline = task['deadline']
            time_diff = (deadline - completion_time).total_seconds() / 3600  # hours
            
            if time_diff > 24:  # More than 1 day early
                base_points = self.POINTS['task_completed_early']
            elif time_diff < 0:  # Late
                base_points = self.POINTS['task_completed_late']
        
        # Bonus for importance
        importance_multiplier = {
            'low': 1.0,
            'medium': 1.5,
            'high': 2.0,
            'urgent': 2.5
        }
        
        importance = task.get('importance', 'medium')
        final_points = int(base_points * importance_multiplier.get(importance, 1.0))
        
        return final_points
    
    def calculate_session_points(self, hours_studied):
        """
        Calculate points for study session based on duration
        
        Args:
            hours_studied: float, hours spent studying
        
        Returns:
            int: points earned
        """
        if hours_studied >= 3:
            return self.POINTS['study_session_3h']
        elif hours_studied >= 2:
            return self.POINTS['study_session_2h']
        elif hours_studied >= 1:
            return self.POINTS['study_session_1h']
        else:
            return int(hours_studied * 10)  # 10 points per hour
    
    def update_streak(self, user_id):
        """
        Update user's daily streak
        
        Args:
            user_id: int, user ID
        
        Returns:
            dict: streak info with points earned
        """
        user = self.db.get_user_by_id(user_id)
        if not user:
            return {"streak": 0, "points": 0, "status": "user_not_found"}
        
        # Get today's sessions
        today = datetime.now().date()
        sessions = self.db.get_user_sessions(user_id, days=2)
        
        # Check if user studied today
        studied_today = any(
            s['date'] == today for s in sessions
        )
        
        # Check if user studied yesterday
        yesterday = today - timedelta(days=1)
        studied_yesterday = any(
            s['date'] == yesterday for s in sessions
        )
        
        current_streak = user['streak']
        new_streak = current_streak
        points_earned = 0
        
        if studied_today:
            if studied_yesterday or current_streak == 0:
                # Continue streak
                new_streak = current_streak + 1
                points_earned = self.POINTS['daily_streak']
            else:
                # Streak already counted for today
                new_streak = current_streak
        else:
            if not studied_yesterday and current_streak > 0:
                # Streak broken
                new_streak = 0
                points_earned = 0
        
        # Update database
        if new_streak != current_streak:
            self.db.update_user_streak(user_id, new_streak)
            if points_earned > 0:
                self.db.update_user_score(user_id, points_earned)
        
        return {
            "streak": new_streak,
            "points": points_earned,
            "status": "streak_continued" if new_streak > current_streak else "no_change"
        }
    
    def check_achievements(self, user_id):
        """
        Check and award new achievements for user
        
        Args:
            user_id: int, user ID
        
        Returns:
            list: newly unlocked achievements
        """
        user = self.db.get_user_by_id(user_id)
        if not user:
            return []
        
        tasks = self.db.get_user_tasks(user_id, status='completed')
        
        unlocked = []
        
        # Check task completion achievements
        completed_count = len(tasks)
        if completed_count == 1 and user['score'] < self.ACHIEVEMENTS['first_task']['reward']:
            unlocked.append(self.ACHIEVEMENTS['first_task'])
        elif completed_count >= 50:
            unlocked.append(self.ACHIEVEMENTS['tasks_50'])
        
        # Check streak achievements
        current_streak = user['streak']
        if current_streak >= 30:
            unlocked.append(self.ACHIEVEMENTS['streak_30'])
        elif current_streak >= 7:
            unlocked.append(self.ACHIEVEMENTS['streak_7'])
        
        # Check score achievements
        if user['score'] >= 1000:
            unlocked.append(self.ACHIEVEMENTS['score_1000'])
        
        # Award achievement points
        total_reward = sum(a['reward'] for a in unlocked if a['reward'] > 0)
        if total_reward > 0:
            self.db.update_user_score(user_id, total_reward)
        
        return unlocked
    
    def get_user_progress_summary(self, user_id):
        """
        Get comprehensive progress summary for user
        
        Args:
            user_id: int, user ID
        
        Returns:
            dict: complete progress data
        """
        user = self.db.get_user(user_id)
        if not user:
            return None
        
        tasks = self.db.get_user_tasks(user_id)
        sessions = self.db.get_user_sessions(user_id, limit=100)
        
        # Calculate statistics
        total_tasks = len(tasks) if tasks else 0
        completed_tasks = len([t for t in tasks if t['status'] == 'completed']) if tasks else 0
        pending_tasks = len([t for t in tasks if t['status'] == 'pending']) if tasks else 0
        overdue_tasks = len([t for t in tasks if t.get('status') == 'overdue']) if tasks else 0
        
        total_hours = sum(float(s.get('duration_hours', 0)) for s in sessions) if sessions else 0
        total_sessions = len(sessions) if sessions else 0
        
        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        return {
            "user_id": user_id,
            "name": user.get('name', 'User'),
            "score": user.get('score', 0),
            "streak": user.get('streak', 0),
            "tasks": {
                "total": total_tasks,
                "completed": completed_tasks,
                "pending": pending_tasks,
                "overdue": overdue_tasks,
                "completion_rate": round(completion_rate, 2)
            },
            "study_stats": {
                "total_hours": float(total_hours),
                "total_sessions": total_sessions,
                "avg_session_length": round(total_hours / total_sessions, 2) if total_sessions > 0 else 0
            },
            "recent_sessions": sessions[:7]  # Last 7 sessions
        }
    
    def compare_with_friends(self, user_id, friend_ids):
        """
        Compare user's progress with friends
        
        Args:
            user_id: int, user ID
            friend_ids: list of friend IDs
        
        Returns:
            dict: comparison data
        """
        user_progress = self.get_user_progress_summary(user_id)
        friends_progress = []
        
        for friend_id in friend_ids:
            friend_progress = self.get_user_progress_summary(friend_id)
            if friend_progress:
                friends_progress.append(friend_progress)
        
        # Calculate rankings
        all_users = [user_progress] + friends_progress
        all_users.sort(key=lambda x: x['score'], reverse=True)
        
        user_rank = next(i+1 for i, u in enumerate(all_users) if u['user_id'] == user_id)
        
        return {
            "user": user_progress,
            "rank": user_rank,
            "total_friends": len(friend_ids),
            "friends": friends_progress,
            "leaderboard": all_users
        }


if __name__ == "__main__":
    # Test progress tracking (requires database)
    from backend.db import get_db
    
    db = get_db()
    tracker = ProgressTracker(db)
    
    print("\n✓ Progress Tracker module loaded")
    print("Points configuration:", json.dumps(tracker.POINTS, indent=2))
    print("Achievements:", json.dumps(tracker.ACHIEVEMENTS, indent=2))
    
    db.disconnect()
