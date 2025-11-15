"""
Social Module - Leaderboard & Friend Comparison
Handles multiplayer study features and social interactions.

FLOW: User Request → Social Module → Database → Rankings/Comparisons
"""

from datetime import datetime, timedelta
import json


class SocialManager:
    """Manages social features, leaderboards, and friend competitions"""
    
    def __init__(self, db):
        """
        Initialize social manager with database connection
        
        Args:
            db: Database instance
        """
        self.db = db
        print("✓ Social Manager initialized")
    
    def get_global_leaderboard(self, user_id, limit=10):
        """
        Get global leaderboard of top users
        
        Args:
            user_id: int, requesting user's ID
            limit: int, number of top users to return
        
        Returns:
            dict: leaderboard data with user's rank
        """
        # Get user's friends for leaderboard
        leaderboard = self.db.get_leaderboard(user_id, limit=limit)
        
        # Find user's rank
        user_rank = None
        for idx, entry in enumerate(leaderboard):
            if entry['id'] == user_id:
                user_rank = idx + 1
                break
        
        return {
            "leaderboard": leaderboard,
            "user_rank": user_rank,
            "total_users": len(leaderboard),
            "updated_at": datetime.now().isoformat()
        }
    
    def get_weekly_leaderboard(self, user_id, limit=10):
        """
        Get leaderboard for current week's activity
        
        Args:
            user_id: int, requesting user's ID
            limit: int, number of top users to return
        
        Returns:
            dict: weekly leaderboard data
        """
        # Get friends
        leaderboard_data = self.db.get_leaderboard(user_id, limit=100)
        
        # Calculate weekly scores for each user
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
        
        weekly_scores = []
        for user_entry in leaderboard_data:
            uid = user_entry['id']
            sessions = self.db.get_user_sessions(uid, limit=100)
            
            # Sum points from this week
            week_sessions = [
                s for s in sessions 
                if datetime.strptime(s['session_date'], '%Y-%m-%d').date() >= week_start
            ]
            
            # Calculate weekly points based on study hours (10 points per hour)
            weekly_points = sum(s['duration_hours'] * 10 for s in week_sessions)
            weekly_hours = sum(s['duration_hours'] for s in week_sessions)
            
            weekly_scores.append({
                "id": uid,
                "name": user_entry['name'],
                "weekly_points": weekly_points,
                "weekly_hours": float(weekly_hours),
                "total_score": user_entry['score'],
                "streak": user_entry['streak']
            })
        
        # Sort by weekly points
        weekly_scores.sort(key=lambda x: x['weekly_points'], reverse=True)
        
        # Find user's rank
        user_rank = None
        for idx, entry in enumerate(weekly_scores[:limit]):
            if entry['id'] == user_id:
                user_rank = idx + 1
                break
        
        return {
            "weekly_leaderboard": weekly_scores[:limit],
            "user_rank": user_rank,
            "week_start": week_start.isoformat(),
            "week_end": today.isoformat()
        }
    
    def compare_with_friend(self, user_id, friend_id):
        """
        Detailed comparison between user and specific friend
        
        Args:
            user_id: int, user's ID
            friend_id: int, friend's ID
        
        Returns:
            dict: detailed comparison data
        """
        user = self.db.get_user_by_id(user_id)
        friend = self.db.get_user_by_id(friend_id)
        
        if not user or not friend:
            return {"error": "User or friend not found"}
        
        # Get tasks
        user_tasks = self.db.get_user_tasks(user_id)
        friend_tasks = self.db.get_user_tasks(friend_id)
        
        # Get sessions (last 30 days)
        user_sessions = self.db.get_user_sessions(user_id, days=30)
        friend_sessions = self.db.get_user_sessions(friend_id, days=30)
        
        # Calculate stats
        user_stats = {
            "name": user['name'],
            "score": user['score'],
            "streak": user['streak'],
            "tasks_completed": len([t for t in user_tasks if t['status'] == 'completed']),
            "total_hours": sum(s['hours_studied'] for s in user_sessions),
            "avg_daily_hours": sum(s['hours_studied'] for s in user_sessions) / max(len(user_sessions), 1)
        }
        
        friend_stats = {
            "name": friend['name'],
            "score": friend['score'],
            "streak": friend['streak'],
            "tasks_completed": len([t for t in friend_tasks if t['status'] == 'completed']),
            "total_hours": sum(s['hours_studied'] for s in friend_sessions),
            "avg_daily_hours": sum(s['hours_studied'] for s in friend_sessions) / max(len(friend_sessions), 1)
        }
        
        # Calculate differences
        comparison = {
            "user": user_stats,
            "friend": friend_stats,
            "differences": {
                "score_diff": user_stats['score'] - friend_stats['score'],
                "streak_diff": user_stats['streak'] - friend_stats['streak'],
                "tasks_diff": user_stats['tasks_completed'] - friend_stats['tasks_completed'],
                "hours_diff": round(user_stats['total_hours'] - friend_stats['total_hours'], 2)
            },
            "winner": user['name'] if user_stats['score'] > friend_stats['score'] else friend['name']
        }
        
        return comparison
    
    def get_friend_activity_feed(self, user_id, limit=20):
        """
        Get recent activity feed from friends
        
        Args:
            user_id: int, user's ID
            limit: int, number of activities to return
        
        Returns:
            list: recent friend activities
        """
        # Get all friends
        leaderboard = self.db.get_leaderboard(user_id, limit=100)
        friend_ids = [u['id'] for u in leaderboard if u['id'] != user_id]
        
        activities = []
        
        for friend_id in friend_ids[:10]:  # Limit to 10 friends
            friend = self.db.get_user_by_id(friend_id)
            if not friend:
                continue
            
            # Get recent sessions
            sessions = self.db.get_user_sessions(friend_id, days=7)
            for session in sessions[:3]:  # Last 3 sessions per friend
                activities.append({
                    "friend_name": friend['name'],
                    "friend_id": friend_id,
                    "type": "study_session",
                    "date": session['date'].isoformat() if hasattr(session['date'], 'isoformat') else str(session['date']),
                    "details": f"Studied for {session['hours_studied']} hours, completed {session['completed_tasks']} tasks",
                    "hours": float(session['hours_studied']),
                    "timestamp": session['created_at'].isoformat() if hasattr(session['created_at'], 'isoformat') else str(session['created_at'])
                })
            
            # Get recent completed tasks
            tasks = self.db.get_user_tasks(friend_id, status='completed')
            for task in tasks[:2]:  # Last 2 completed tasks
                if task.get('completed_at'):
                    activities.append({
                        "friend_name": friend['name'],
                        "friend_id": friend_id,
                        "type": "task_completed",
                        "date": task['completed_at'].date().isoformat() if hasattr(task['completed_at'], 'date') else str(task['completed_at']),
                        "details": f"Completed: {task['title']}",
                        "task_title": task['title'],
                        "timestamp": task['completed_at'].isoformat() if hasattr(task['completed_at'], 'isoformat') else str(task['completed_at'])
                    })
        
        # Sort by timestamp and limit
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return activities[:limit]
    
    def suggest_study_buddies(self, user_id):
        """
        Suggest potential study buddies based on similar scores/interests
        
        Args:
            user_id: int, user's ID
        
        Returns:
            list: suggested users to connect with
        """
        user = self.db.get_user_by_id(user_id)
        if not user:
            return []
        
        # Get current friends
        current_friends = self.db.get_leaderboard(user_id, limit=100)
        friend_ids = {u['id'] for u in current_friends}
        
        # This is a simplified version - in production, query all users
        # For now, return empty since we're only showing friends in leaderboard
        suggestions = []
        
        return suggestions
    
    def get_friend_stats(self, user_id):
        """
        Get aggregate statistics about user's friend group
        
        Args:
            user_id: int, user's ID
        
        Returns:
            dict: friend group statistics
        """
        leaderboard = self.db.get_leaderboard(user_id, limit=100)
        friend_ids = [u['id'] for u in leaderboard if u['id'] != user_id]
        
        total_friends = len(friend_ids)
        total_score = sum(u['score'] for u in leaderboard)
        avg_score = total_score / len(leaderboard) if leaderboard else 0
        avg_streak = sum(u['streak'] for u in leaderboard) / len(leaderboard) if leaderboard else 0
        
        # Find most active friend
        most_active = max(leaderboard, key=lambda x: x['score']) if leaderboard else None
        
        return {
            "total_friends": total_friends,
            "group_total_score": total_score,
            "avg_score": round(avg_score, 2),
            "avg_streak": round(avg_streak, 2),
            "most_active_friend": {
                "name": most_active['name'],
                "score": most_active['score']
            } if most_active else None
        }


if __name__ == "__main__":
    # Test social features (requires database)
    from backend.db import get_db
    
    db = get_db()
    social = SocialManager(db)
    
    print("\n✓ Social Manager module loaded")
    print("Social features ready: leaderboards, comparisons, activity feeds")
    
    db.disconnect()
