"""
Utility Helper Functions
Common utilities used across the backend.
"""

import os
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path


def parse_date(date_string):
    """
    Parse various date formats into datetime object
    
    Args:
        date_string: str, date in various formats
    
    Returns:
        datetime or None
    """
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_string, fmt)
        except ValueError:
            continue
    
    return None


def format_duration(hours):
    """
    Format hours into human-readable duration
    
    Args:
        hours: float, duration in hours
    
    Returns:
        str, formatted duration
    """
    if hours < 1:
        minutes = int(hours * 60)
        return f"{minutes} minutes"
    elif hours < 24:
        return f"{hours:.1f} hours"
    else:
        days = int(hours / 24)
        remaining_hours = hours % 24
        return f"{days} days, {remaining_hours:.1f} hours"


def calculate_time_until(target_datetime):
    """
    Calculate time remaining until target datetime
    
    Args:
        target_datetime: datetime object
    
    Returns:
        dict with days, hours, minutes remaining
    """
    now = datetime.now()
    diff = target_datetime - now
    
    if diff.total_seconds() < 0:
        return {"overdue": True, "days": 0, "hours": 0, "minutes": 0}
    
    days = diff.days
    hours = diff.seconds // 3600
    minutes = (diff.seconds % 3600) // 60
    
    return {
        "overdue": False,
        "days": days,
        "hours": hours,
        "minutes": minutes,
        "total_hours": diff.total_seconds() / 3600
    }


def sanitize_filename(filename):
    """
    Sanitize filename for safe storage
    
    Args:
        filename: str, original filename
    
    Returns:
        str, sanitized filename
    """
    # Remove invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    return filename.strip()


def save_note_file(user_id, content, filename=None):
    """
    Save user note to local filesystem
    
    Args:
        user_id: int, user ID
        content: str or bytes, file content
        filename: str, optional filename
    
    Returns:
        str, filepath where note was saved
    """
    # Create user directory
    notes_dir = Path("data/notes") / str(user_id)
    notes_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename if not provided
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"note_{timestamp}.txt"
    
    filename = sanitize_filename(filename)
    filepath = notes_dir / filename
    
    # Save file
    if isinstance(content, bytes):
        with open(filepath, 'wb') as f:
            f.write(content)
    else:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    
    return str(filepath)


def load_note_file(filepath):
    """
    Load note content from filesystem
    
    Args:
        filepath: str, path to note file
    
    Returns:
        str, file content
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error loading note: {e}")
        return None


def generate_user_hash(phone):
    """
    Generate unique hash for user identifier
    
    Args:
        phone: str, phone number
    
    Returns:
        str, hashed identifier
    """
    return hashlib.sha256(phone.encode()).hexdigest()[:16]


def validate_phone_number(phone):
    """
    Validate phone number format
    
    Args:
        phone: str, phone number
    
    Returns:
        bool, True if valid
    """
    # Remove common separators
    cleaned = phone.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
    
    # Check if it's all digits and reasonable length
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    
    return cleaned.isdigit() and 10 <= len(cleaned) <= 15


def format_task_list(tasks, max_items=10):
    """
    Format task list for display
    
    Args:
        tasks: list of task dicts
        max_items: int, maximum items to show
    
    Returns:
        str, formatted task list
    """
    if not tasks:
        return "No tasks found."
    
    output = []
    for idx, task in enumerate(tasks[:max_items], 1):
        status_emoji = {
            'pending': '⏳',
            'in_progress': '🔄',
            'completed': '✅',
            'overdue': '⚠️'
        }
        
        emoji = status_emoji.get(task['status'], '📝')
        title = task['title']
        
        if task.get('deadline'):
            time_info = calculate_time_until(task['deadline'])
            if time_info['overdue']:
                deadline_str = "OVERDUE"
            else:
                deadline_str = f"{time_info['days']}d {time_info['hours']}h left"
        else:
            deadline_str = "No deadline"
        
        output.append(f"{emoji} {title} ({deadline_str})")
    
    if len(tasks) > max_items:
        output.append(f"\n... and {len(tasks) - max_items} more")
    
    return "\n".join(output)


def calculate_completion_rate(tasks):
    """
    Calculate task completion rate
    
    Args:
        tasks: list of task dicts
    
    Returns:
        float, completion rate (0-100)
    """
    if not tasks:
        return 0.0
    
    completed = len([t for t in tasks if t['status'] == 'completed'])
    return (completed / len(tasks)) * 100


def get_motivational_message(streak, score):
    """
    Generate motivational message based on user stats
    
    Args:
        streak: int, current streak
        score: int, current score
    
    Returns:
        str, motivational message
    """
    messages = {
        (0, 100): "🌱 Every expert was once a beginner. Start your journey today!",
        (1, 3): "🔥 Great start! Keep the momentum going!",
        (4, 7): "⭐ One week! You're building a solid habit!",
        (8, 14): "🚀 Two weeks strong! You're unstoppable!",
        (15, 30): "💎 Half a month! This is discipline!",
        (31, 100): "👑 You're a true champion! Keep conquering!",
    }
    
    for (min_streak, max_streak), message in messages.items():
        if min_streak <= streak <= max_streak:
            return message
    
    if score >= 1000:
        return "🏆 1000+ points! You're in the elite league!"
    elif score >= 500:
        return "⚡ 500+ points! Your dedication is inspiring!"
    elif score >= 100:
        return "🎯 100+ points! You're making great progress!"
    
    return "💪 Keep pushing! Every step counts!"


def export_user_data(user, tasks, sessions):
    """
    Export user data to JSON format
    
    Args:
        user: dict, user data
        tasks: list, user tasks
        sessions: list, study sessions
    
    Returns:
        str, JSON formatted data
    """
    export_data = {
        "user": {
            "name": user['name'],
            "phone": user['phone'],
            "score": user['score'],
            "streak": user['streak']
        },
        "tasks": [
            {
                "title": t['title'],
                "deadline": str(t['deadline']) if t['deadline'] else None,
                "status": t['status'],
                "importance": t['importance']
            } for t in tasks
        ],
        "sessions": [
            {
                "date": str(s['date']),
                "hours_studied": float(s['hours_studied']),
                "completed_tasks": s['completed_tasks']
            } for s in sessions
        ],
        "export_date": datetime.now().isoformat()
    }
    
    return json.dumps(export_data, indent=2)


if __name__ == "__main__":
    # Test utilities
    print("✓ Utilities module loaded")
    
    # Test date parsing
    test_date = parse_date("2025-11-20")
    print(f"Parsed date: {test_date}")
    
    # Test time calculation
    future = datetime.now() + timedelta(days=3, hours=5)
    time_left = calculate_time_until(future)
    print(f"Time until: {time_left}")
    
    # Test motivational message
    msg = get_motivational_message(5, 250)
    print(f"Motivation: {msg}")
