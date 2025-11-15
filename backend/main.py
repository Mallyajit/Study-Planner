"""
Main Flask Application - API Layer
REST API endpoints for UI integration (fully decoupled).

FLOW SUMMARY:
1. WhatsApp Message → Bot → Parse → AI/DB → Response
2. User Action → API Endpoint → Backend Logic → JSON Response
3. Scheduler → Periodic Checks → Send Reminders → Update DB

Start with: python main.py
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import json
from typing import Any, Iterable, List, Optional

# Import backend modules
try:
    from db_sqlite import get_db  # Use SQLite for easy setup
    print("Using SQLite database (no MySQL setup required)")
except ImportError:
    from db import get_db  # Fallback to MySQL
    print("Using MySQL database")

from ai_logic.planner import AIPlanner
from ai_logic.progress import ProgressTracker
from ai_logic.social import SocialManager
from whatsapp.bot import WhatsAppBot
from scheduler import ReminderScheduler

load_dotenv()

# Initialize Flask app
app = Flask(__name__, static_folder='../frontend')
CORS(app)  # Enable CORS for any UI frontend

# Initialize backend components
print("\n" + "="*60)
print("🚀 STUDYPLANNER AI BACKEND - INITIALIZING")
print("="*60)

db = get_db()
ai_planner = AIPlanner()
progress_tracker = ProgressTracker(db)
social_manager = SocialManager(db)
whatsapp_bot = WhatsAppBot(db, ai_planner)
scheduler = ReminderScheduler(db, whatsapp_bot, progress_tracker)


def _row_to_dict(row: Any) -> dict:
    """Ensure database rows behave like plain dictionaries."""
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    try:
        return {key: row[key] for key in row.keys()}
    except AttributeError:
        return dict(row)


def _parse_datetime(value: Any) -> Optional[datetime]:
    """Convert various datetime string formats into datetime objects."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value)
        except (OSError, ValueError):
            return None

    candidates = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]

    for fmt in candidates:
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _prepare_tasks_for_planner(task_rows: Iterable[Any]) -> List[dict]:
    """Normalize task rows and parse deadlines for AI planner."""
    formatted: List[dict] = []
    for row in task_rows or []:
        task = _row_to_dict(row)
        task['deadline'] = _parse_datetime(task.get('deadline'))
        formatted.append(task)
    return formatted


def _generate_simple_schedule(user: dict, tasks: List[dict]) -> dict:
    """Generate basic schedule from tasks without calling Gemini AI."""
    today = datetime.now()
    
    # Filter out completed tasks and tasks past deadline
    active_tasks = []
    for t in tasks:
        if t.get('status') == 'completed':
            continue
        deadline = t.get('deadline')
        # Only include tasks with future deadlines or no deadline
        if deadline:
            if deadline.date() >= today.date():
                active_tasks.append(t)
        else:
            # Tasks without deadline are always active
            active_tasks.append(t)
    
    schedule = {
        "day_plan": [],
        "priority_notes": "Schedule generated from your tasks",
        "motivation_message": f"You have {len(active_tasks)} active tasks to complete!",
        "generated_at": today.isoformat()
    }
    
    # Sort tasks by deadline (earliest first)
    sorted_tasks = sorted(
        active_tasks,
        key=lambda x: x.get('deadline') if x.get('deadline') else datetime.max
    )
    
    # Generate 7 days of schedule
    for day_offset in range(7):
        current_date = today + timedelta(days=day_offset)
        day_name = current_date.strftime("%A")
        date_str = current_date.strftime("%Y-%m-%d")
        
        sessions = []
        total_hours = 0
        
        # Add tasks due on this date or within next 7 days
        for task in sorted_tasks:
            if len(sessions) >= 3:  # Max 3 sessions per day
                break
                
            deadline = task.get('deadline')
            # Schedule task if it's due within the next 7 days from current_date
            if deadline and deadline.date() >= current_date.date() and deadline.date() <= (current_date + timedelta(days=7)).date():
                start_hour = 9 + len(sessions) * 2
                if start_hour >= 17:
                    break
                
                sessions.append({
                    "time": f"{start_hour:02d}:00-{start_hour+2:02d}:00",
                    "task": task.get('title', 'Study session'),
                    "type": "study",
                    "priority": task.get('importance', 'medium'),
                    "estimated_hours": 2.0,
                    "task_id": task.get('id'),
                    "deadline": deadline.strftime("%Y-%m-%d") if deadline else None
                })
                total_hours += 2.0
        
        # If no specific tasks for today and it's not too far in future, add general study session
        if not sessions and day_offset < 3:
            if sorted_tasks:  # If there are any tasks at all
                sessions.append({
                    "time": "09:00-11:00",
                    "task": f"Work on: {sorted_tasks[0].get('title', 'Study')}",
                    "type": "study",
                    "priority": sorted_tasks[0].get('importance', 'medium'),
                    "estimated_hours": 2.0,
                    "task_id": sorted_tasks[0].get('id')
                })
                total_hours = 2.0
        
        # Only add days with sessions
        if sessions:
            schedule["day_plan"].append({
                "day": day_name,
                "date": date_str,
                "sessions": sessions,
                "total_study_hours": total_hours
            })
    
    return schedule

print("\n✓ All backend modules loaded successfully!")
print("="*60 + "\n")


# ==================== API ROUTES ====================

# Serve frontend
@app.route('/')
def index():
    """Serve the main frontend page"""
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    """Serve static files (CSS, JS, etc.)"""
    return send_from_directory(app.static_folder, path)

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "service": "StudyPlanner AI Backend",
        "status": "running",
        "version": "1.0.0",
        "endpoints": {
            "schedule": "/api/schedule",
            "progress": "/api/progress",
            "leaderboard": "/api/leaderboard",
            "flashcards": "/api/flashcards",
            "tasks": "/api/tasks",
            "whatsapp": "/webhook/whatsapp"
        }
    })


@app.route('/api/schedule', methods=['GET', 'POST'])
def schedule():
    """
    GET: Retrieve cached schedule (no AI generation)
    POST: Generate new schedule with Gemini AI
    """
    if request.method == 'GET':
        user_id = request.args.get('user_id', type=int)
        
        if not user_id:
            return jsonify({"error": "user_id required"}), 400
        
        try:
            # Get user data
            user_row = db.get_user(user_id)
            if not user_row:
                return jsonify({"error": "User not found"}), 404

            user = _row_to_dict(user_row)
            tasks = _prepare_tasks_for_planner(db.get_user_tasks(user_id))
            
            # Return simple schedule without calling Gemini
            # This prevents continuous API calls from dashboard refresh
            schedule_data = _generate_simple_schedule(user, tasks)
            
            return jsonify({
                "success": True,
                "schedule": schedule_data
            })
        
        except Exception as e:
            print(f"❌ Error in GET /api/schedule: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    
    elif request.method == 'POST':
        data = request.json
        user_id = data.get('user_id')
        free_time_slots = data.get('free_time', [])
        
        if not user_id:
            return jsonify({"error": "user_id required"}), 400
        
        try:
            user_row = db.get_user(user_id)
            if not user_row:
                return jsonify({"error": "User not found"}), 404

            user = _row_to_dict(user_row)
            preference_raw = user.get('preferences')
            preferences = json.loads(preference_raw) if preference_raw else {}

            tasks = _prepare_tasks_for_planner(db.get_user_tasks(user_id))

            schedule_data = ai_planner.generate_schedule(user, tasks, preferences, free_time_slots)
            
            return jsonify({
                "success": True,
                "schedule": schedule_data
            })
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@app.route('/api/progress', methods=['GET'])
def progress():
    """Get user's progress, scores, and streaks"""
    user_id = request.args.get('user_id', type=int)
    
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    
    try:
        progress_data = progress_tracker.get_user_progress_summary(user_id)
        
        if not progress_data:
            return jsonify({"error": "User not found"}), 404
        
        return jsonify({
            "success": True,
            "progress": progress_data
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/leaderboard', methods=['GET'])
def leaderboard():
    """Get leaderboard rankings"""
    user_id = request.args.get('user_id', type=int)
    timeframe = request.args.get('timeframe', 'all')  # 'all' or 'weekly'
    limit = request.args.get('limit', 10, type=int)
    
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    
    try:
        if timeframe == 'weekly':
            leaderboard_data = social_manager.get_weekly_leaderboard(user_id, limit)
        else:
            leaderboard_data = social_manager.get_global_leaderboard(user_id, limit)
        
        return jsonify({
            "success": True,
            "leaderboard": leaderboard_data
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/flashcards', methods=['GET', 'POST'])
def flashcards():
    """
    GET: Retrieve flashcards for review
    POST: Create new flashcard
    """
    if request.method == 'GET':
        user_id = request.args.get('user_id', type=int)
        limit = request.args.get('limit', 10, type=int)
        
        if not user_id:
            return jsonify({"error": "user_id required"}), 400
        
        try:
            cards = db.get_user_flashcards(user_id, limit)
            return jsonify({
                "success": True,
                "flashcards": cards
            })
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    elif request.method == 'POST':
        data = request.json
        user_id = data.get('user_id')
        question = data.get('question')
        answer = data.get('answer')
        
        if not all([user_id, question, answer]):
            return jsonify({"error": "user_id, question, and answer required"}), 400
        
        try:
            card_id = db.create_flashcard(user_id, question, answer)
            return jsonify({
                "success": True,
                "flashcard_id": card_id
            })
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@app.route('/api/flashcards/<int:card_id>/review', methods=['POST'])
def review_flashcard(card_id):
    """Update flashcard progress after review"""
    data = request.json
    progress_level = data.get('progress_level', 0)
    
    try:
        success = db.update_flashcard_progress(card_id, progress_level)
        return jsonify({
            "success": success,
            "message": "Flashcard updated"
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/tasks', methods=['GET', 'POST', 'PUT'])
def tasks():
    """
    GET: Retrieve user tasks
    POST: Create new task
    PUT: Update task status
    """
    if request.method == 'GET':
        user_id = request.args.get('user_id', type=int)
        status = request.args.get('status')  # optional filter
        
        if not user_id:
            return jsonify({"error": "user_id required"}), 400
        
        try:
            task_list = db.get_user_tasks(user_id, status)
            return jsonify({
                "success": True,
                "tasks": task_list
            })
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    elif request.method == 'POST':
        data = request.json
        user_id = data.get('user_id')
        title = data.get('title')
        deadline = data.get('deadline')
        importance = data.get('importance', 'medium')
        description = data.get('description')
        
        if not all([user_id, title]):
            return jsonify({"error": "user_id and title required"}), 400
        
        try:
            # Parse deadline if provided
            deadline_dt = None
            if deadline:
                from utils.helpers import parse_date
                deadline_dt = parse_date(deadline)
            
            task_id = db.create_task(user_id, title, deadline_dt, importance, description=description)
            return jsonify({
                "success": True,
                "task_id": task_id
            })
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    elif request.method == 'PUT':
        data = request.json
        task_id = data.get('task_id')
        status = data.get('status')
        
        if not all([task_id, status]):
            return jsonify({"error": "task_id and status required"}), 400
        
        try:
            # Get task details before updating
            task = db.fetchone("SELECT * FROM tasks WHERE id = ?", (task_id,))
            if not task:
                return jsonify({"error": "Task not found"}), 404
            
            user_id = task['user_id']
            
            # Update task status
            success = db.update_task_status(task_id, status)
            
            # Award points and update streak if completed
            points_awarded = 0
            if status == 'completed':
                # Calculate points based on priority
                priority = task.get('importance', 'medium')
                if priority == 'high':
                    points_awarded = 50
                elif priority == 'medium':
                    points_awarded = 30
                else:
                    points_awarded = 20
                
                # Get current user data
                user = db.get_user(user_id)
                if user:
                    current_score = user.get('score', 0) or 0
                    current_streak = user.get('streak', 0) or 0
                    
                    # Update score
                    new_score = current_score + points_awarded
                    
                    # Update streak (increment by 1)
                    new_streak = current_streak + 1
                    
                    # Update user in database
                    db.cursor.execute(
                        "UPDATE users SET score = ?, streak = ? WHERE id = ?",
                        (new_score, new_streak, user_id)
                    )
                    db.conn.commit()
                    
                    print(f"✓ User {user_id} completed task: +{points_awarded} points, streak now {new_streak}")
            
            return jsonify({
                "success": success,
                "message": f"Task marked as {status}",
                "points_awarded": points_awarded,
                "completed": status == 'completed'
            })
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@app.route('/api/user/register', methods=['POST'])
def register_user():
    """Register a new user"""
    data = request.json
    name = data.get('name')
    phone = data.get('phone')
    preferences = data.get('preferences', {})
    
    if not all([name, phone]):
        return jsonify({"error": "name and phone required"}), 400
    
    try:
        # Check if user exists
        existing = db.get_user_by_phone(phone)
        if existing:
            return jsonify({"error": "User already exists", "user_id": existing['id']}), 409
        
        user_id = db.create_user(name, phone, preferences)
        return jsonify({
            "success": True,
            "user_id": user_id,
            "message": "User registered successfully"
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/user/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """Get user details"""
    try:
        user = db.get_user(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        return jsonify({
            "success": True,
            "user": user
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """
    Webhook endpoint for incoming WhatsApp messages (Twilio)
    Handles both Twilio and mock modes
    """
    try:
        # Parse Twilio webhook data
        from_number = request.form.get('From', '')
        message_body = request.form.get('Body', '')
        
        if not from_number or not message_body:
            return jsonify({"error": "Invalid webhook data"}), 400
        
        # Process message
        response_text = whatsapp_bot.handle_incoming_message(from_number, message_body)
        
        # If in mock mode, just return JSON (no Twilio TwiML needed)
        if whatsapp_bot.mock_mode:
            return jsonify({
                "success": True,
                "message": response_text,
                "mode": "mock"
            })
        
        # If Twilio available, send TwiML response
        try:
            from twilio.twiml.messaging_response import MessagingResponse
            resp = MessagingResponse()
            resp.message(response_text)
            return str(resp)
        except ImportError:
            # Fallback if Twilio import fails
            return jsonify({
                "success": True,
                "message": response_text,
                "mode": "mock_fallback"
            })
    
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/friends/compare', methods=['GET'])
def compare_friends():
    """Compare user with a specific friend"""
    # Support both parameter naming conventions
    user1_id = request.args.get('user1_id', request.args.get('user_id', type=int), type=int)
    user2_id = request.args.get('user2_id', request.args.get('friend_id', type=int), type=int)
    
    if not all([user1_id, user2_id]):
        return jsonify({"error": "user1_id and user2_id (or user_id and friend_id) required"}), 400
    
    try:
        comparison = social_manager.compare_with_friend(user1_id, user2_id)
        return jsonify({
            "success": True,
            "comparison": comparison
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/api/activity-feed', methods=['GET'])
def activity_feed():
    """Get friend activity feed"""
    user_id = request.args.get('user_id', type=int)
    limit = request.args.get('limit', 20, type=int)
    
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    
    try:
        activities = social_manager.get_friend_activity_feed(user_id, limit)
        return jsonify({
            "success": True,
            "activities": activities
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== MAIN ====================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 STARTING FLASK API SERVER")
    print("="*60)
    print("📡 API endpoints available at: http://localhost:5000")
    print("📚 Documentation: http://localhost:5000/")
    print("\nModule Communication Flow:")
    print("  1. WhatsApp → Bot → AI Planner → Database")
    print("  2. Scheduler → Check DB → Send Reminders")
    print("  3. API Request → Backend Logic → JSON Response")
    print("="*60 + "\n")
    
    # Start background scheduler
    scheduler.start()
    
    # Run Flask app
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("DEBUG", "False").lower() == "true"
    
    try:
        app.run(host='0.0.0.0', port=port, debug=debug)
    finally:
        # Cleanup on shutdown
        scheduler.stop()
        if hasattr(db, 'disconnect'):
            db.disconnect()
        elif hasattr(db, 'close'):
            db.close()
        print("\n✓ Server stopped gracefully")
