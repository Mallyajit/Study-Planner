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
from datetime import date, datetime, timedelta, time
import json
from typing import Any, Iterable, List, Optional, Tuple

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
from whatsapp.media_handler import MediaHandler
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
db.ensure_leaderboard_seed_data()
ai_planner = AIPlanner()
progress_tracker = ProgressTracker(db)
social_manager = SocialManager(db)
whatsapp_bot = WhatsAppBot(db, ai_planner)
scheduler = ReminderScheduler(db, whatsapp_bot, progress_tracker)

# Initialize media handler for WhatsApp files
twilio_account_sid = os.getenv('TWILIO_ACCOUNT_SID')
twilio_auth_token = os.getenv('TWILIO_AUTH_TOKEN')
if twilio_account_sid and twilio_auth_token:
    media_handler = MediaHandler(twilio_account_sid, twilio_auth_token)
    print("✓ Media handler initialized for WhatsApp images/PDFs")
else:
    media_handler = None
    print("⚠ Media handler not initialized (Twilio credentials missing)")


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


def _parse_time_of_day(value: Any) -> Optional[datetime.time]:
    """Parse HH:MM(:SS) strings into time objects."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.time()

    time_str = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(time_str, fmt).time()
        except ValueError:
            continue
    return None


def _exam_timing_bounds(exam: dict) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Return start/end datetimes for a given exam entry."""
    exam_date = _parse_datetime(exam.get('exam_date'))
    if not exam_date:
        return None, None

    start_time_obj = _parse_time_of_day(exam.get('start_time'))
    if start_time_obj:
        start_dt = datetime.combine(exam_date.date(), start_time_obj)
    else:
        start_dt = datetime.combine(exam_date.date(), time(23, 59))

    duration = exam.get('duration_minutes')
    try:
        duration = int(duration)
    except (TypeError, ValueError):
        duration = 0

    if duration <= 0:
        duration = 90 if exam.get('start_time') else 30

    end_dt = start_dt + timedelta(minutes=duration)
    return start_dt, end_dt


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


def _format_due_time(deadline: Optional[datetime], explicit_time: Optional[str] = None) -> Optional[str]:
    """Return HH:MM text when we have a time component available."""
    if deadline:
        if deadline.hour == 0 and deadline.minute == 0 and deadline.second == 0:
            # Time component not provided, fall back to explicit string if any
            return explicit_time
        return deadline.strftime("%H:%M")
    return explicit_time


def _build_dashboard_task_list(user_id: int, reference_date: date) -> dict:
    """Create a next-day-focused task list while buffering upcoming work."""

    focus_day = reference_date + timedelta(days=1)
    buffer_end = focus_day + timedelta(days=2)
    focus_str = focus_day.strftime('%Y-%m-%d')
    buffer_end_str = buffer_end.strftime('%Y-%m-%d')

    importance_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    def sort_entries(entries: List[dict]) -> List[dict]:
        return sorted(
            entries,
            key=lambda item: (
                importance_rank.get((item.get('importance') or 'medium').lower(), 2),
                item.get('due_date') or '9999-12-31',
                item.get('due_time') or '23:59',
            ),
        )

    def build_entry(title: str, category: str, due_date: Optional[str], due_time: Optional[str],
                    importance: str, notes: Optional[str], meta: Optional[dict] = None) -> dict:
        entry = {
            "title": title,
            "category": category,
            "due_date": due_date,
            "due_time": due_time,
            "importance": (importance or 'medium').lower(),
            "notes": notes or "",
        }
        if meta:
            entry.update(meta)
        return entry

    def allocate_entry(target_date: Optional[str], entry: dict, focus_entries: List[dict], buffer_entries: List[dict]):
        if target_date == focus_str:
            focus_entries.append(entry)
        else:
            buffer_entries.append(entry)

    focus_entries: List[dict] = []
    buffer_entries: List[dict] = []

    # Collect tasks with deadlines
    for task in db.get_user_tasks(user_id):
        deadline = _parse_datetime(task.get('deadline'))
        if not deadline:
            continue
        if focus_day <= deadline.date() <= buffer_end:
            due_date = deadline.strftime('%Y-%m-%d')
            entry = build_entry(
                task.get('title', 'Task'),
                'assignment',
                due_date,
                _format_due_time(deadline),
                task.get('importance', 'medium'),
                task.get('description')
            )
            allocate_entry(due_date, entry, focus_entries, buffer_entries)

    # Announcements (project/presentation deadlines)
    announcements = db.get_announcements(
        user_id,
        start_date=focus_str,
        end_date=buffer_end_str,
    )
    for ann in announcements:
        deadline = _parse_datetime(ann.get('deadline'))
        if not deadline:
            continue
        due_date = deadline.strftime('%Y-%m-%d')
        entry = build_entry(
            ann.get('subject') or ann.get('announcement_type', 'Announcement'),
            'announcement',
            due_date,
            _format_due_time(deadline),
            'high',
            ann.get('content'),
        )
        allocate_entry(due_date, entry, focus_entries, buffer_entries)

    # Exams are surfaced exclusively via the exam schedule section

    return {
        "focus_date": focus_str,
        "items": sort_entries(focus_entries),
        "buffered_items": sort_entries(buffer_entries),
        "buffer_window": {
            "start": focus_str,
            "end": buffer_end_str,
        },
        "total_items": len(focus_entries),
        "buffer_count": len(buffer_entries),
    }


def _build_exam_schedule_overview(user_id: int, reference_date: date, horizon_days: int = 45) -> List[dict]:
    """Return upcoming exams/assessments for the requested horizon."""

    horizon_end = reference_date + timedelta(days=horizon_days)
    start_str = reference_date.strftime('%Y-%m-%d')
    end_str = horizon_end.strftime('%Y-%m-%d')

    upcoming = db.get_exam_schedules(user_id, start_date=start_str, end_date=end_str)
    overview: List[dict] = []
    now = datetime.now()

    for exam in upcoming:
        start_dt, end_dt = _exam_timing_bounds(exam)
        if not start_dt or not end_dt or end_dt <= now:
            continue

        days_left = (start_dt.date() - reference_date).days
        minutes_until = max(0, int((start_dt - now).total_seconds() // 60))

        overview.append({
            **exam,
            "days_left": days_left,
            "is_due_soon": days_left <= 3,
            "minutes_until": minutes_until,
        })

    return overview

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
                    db.execute(
                        "UPDATE users SET score = ?, streak = ? WHERE id = ?",
                        (new_score, new_streak, user_id)
                    )
                    
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
    Handles text messages and media (images/PDFs)
    """
    try:
        # Parse Twilio webhook data
        from_number = request.form.get('From', '')
        message_body = request.form.get('Body', '')
        
        if not from_number:
            return jsonify({"error": "Invalid webhook data: missing From"}), 400
        
        # Handle media files (images/PDFs)
        media_files = []
        num_media = int(request.form.get('NumMedia', 0))
        
        if num_media > 0 and media_handler:
            print(f"📎 Received {num_media} media file(s) from {from_number}")
            
            for i in range(num_media):
                media_url = request.form.get(f'MediaUrl{i}')
                media_content_type = request.form.get(f'MediaContentType{i}')
                
                if media_url and media_handler.is_supported_media(media_content_type):
                    try:
                        file_info = media_handler.download_media(media_url, media_content_type)
                        media_files.append(file_info)
                        print(f"✓ Downloaded: {file_info['filename']} ({file_info['size']} bytes)")
                    except Exception as e:
                        print(f"✗ Failed to download media {i}: {e}")
                else:
                    print(f"⚠ Unsupported media type: {media_content_type}")
        
        # Process message with media files
        response_text = whatsapp_bot.handle_incoming_message(from_number, message_body, media_files)
        
        # If in mock mode, just return JSON (no Twilio TwiML needed)
        if whatsapp_bot.mock_mode:
            return jsonify({
                "success": True,
                "message": response_text,
                "media_count": len(media_files),
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
                "media_count": len(media_files),
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
        if not comparison or comparison.get('error'):
            return jsonify({"error": comparison.get('error', 'No comparison data')}), 404

        payload = {
            "user1": comparison.get('user') or comparison.get('user1'),
            "user2": comparison.get('friend') or comparison.get('user2'),
            "differences": comparison.get('differences', {}),
            "winner": comparison.get('winner')
        }

        return jsonify({
            "success": True,
            "comparison": payload
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


# ==================== CONTEXT-AWARE SCHEDULING ENDPOINTS ====================

@app.route('/api/todos', methods=['GET'])
def get_daily_todos():
    """Get intelligent daily todo list for a specific date (default: tomorrow)"""
    user_id = request.args.get('user_id', type=int)
    date_str = request.args.get('date')  # Format: YYYY-MM-DD
    
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    
    try:
        # Generate daily todo list using AI
        result = ai_planner.generate_daily_todo_list(user_id, db, target_date=date_str)
        
        return jsonify({
            "success": True,
            "todos": result
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/parse-timetable', methods=['POST'])
def parse_timetable():
    """Parse forwarded timetable text and store schedules in database"""
    data = request.get_json()
    user_id = data.get('user_id')
    message_text = data.get('message')
    
    if not user_id or not message_text:
        return jsonify({"error": "user_id and message required"}), 400
    
    try:
        # Parse timetable using AI
        parsed = ai_planner.parse_timetable(message_text)
        
        # Store parsed data in database
        stored = {
            "classes": [],
            "exams": [],
            "announcements": []
        }
        
        # Store class schedules
        for cls in parsed.get('classes', []):
            schedule_id = db.create_class_schedule(
                user_id=user_id,
                day_of_week=cls['day_of_week'],
                subject=cls['subject'],
                start_time=cls['start_time'],
                end_time=cls['end_time'],
                location=cls.get('location'),
                instructor=cls.get('instructor')
            )
            if schedule_id:
                stored['classes'].append({**cls, 'id': schedule_id})
        
        # Store exam schedules
        for exam in parsed.get('exams', []):
            exam_id = db.create_exam_schedule(
                user_id=user_id,
                subject=exam['subject'],
                exam_date=exam['exam_date'],
                start_time=exam['start_time'],
                duration_minutes=exam.get('duration_minutes'),
                location=exam.get('location'),
                exam_type=exam.get('exam_type')
            )
            if exam_id:
                stored['exams'].append({**exam, 'id': exam_id})
        
        # Store announcements
        for ann in parsed.get('announcements', []):
            ann_id = db.create_announcement(
                user_id=user_id,
                announcement_type=ann['announcement_type'],
                content=ann['content'],
                subject=ann.get('subject'),
                deadline=ann.get('deadline')
            )
            if ann_id:
                stored['announcements'].append({**ann, 'id': ann_id})
        
        return jsonify({
            "success": True,
            "message": f"Stored {len(stored['classes'])} classes, {len(stored['exams'])} exams, {len(stored['announcements'])} announcements",
            "parsed": parsed,
            "stored": stored
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/schedule/daily', methods=['GET'])
def get_daily_schedule():
    """Get complete schedule for a specific day (classes + exams + announcements + AI study sessions)"""
    user_id = request.args.get('user_id', type=int)
    date_str = request.args.get('date')  # Format: YYYY-MM-DD
    
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    
    try:
        # Parse date or use today
        if date_str:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            target_date = datetime.now().date()
        
        day_name = target_date.strftime('%A')
        next_day = target_date + timedelta(days=1)

        # Get classes for today and tomorrow
        classes_today = [_row_to_dict(c) for c in db.get_class_schedules(user_id, day_name)]
        classes_next_day = [_row_to_dict(c) for c in db.get_class_schedules(user_id, next_day.strftime('%A'))]

        # Determine which classes should be surfaced in the dashboard
        focus_classes = list(classes_today)
        focus_day_name = day_name
        focus_date_obj = target_date
        focus_reason = "requested_date"
        focus_is_today = target_date == datetime.now().date()

        if not date_str:
            now_dt = datetime.now()
            now_time = now_dt.time()

            def _class_is_relevant_today(class_entry: dict) -> bool:
                start_time = _parse_time_of_day(class_entry.get('start_time'))
                end_time = _parse_time_of_day(class_entry.get('end_time'))
                if end_time:
                    return end_time >= now_time
                if start_time:
                    return start_time >= now_time
                return True

            remaining_today = [cls for cls in classes_today if _class_is_relevant_today(cls)]

            if remaining_today:
                focus_classes = remaining_today
                focus_day_name = day_name
                focus_date_obj = target_date
                focus_is_today = True
                focus_reason = "today_remaining"
            elif classes_next_day:
                focus_classes = list(classes_next_day)
                focus_day_name = next_day.strftime('%A')
                focus_date_obj = next_day
                focus_is_today = False
                focus_reason = "next_day_preview"
            else:
                focus_classes = []
                focus_is_today = False
                focus_reason = "no_classes"
        else:
            focus_classes = list(classes_today)
            focus_is_today = target_date == datetime.now().date()
            focus_reason = "requested_date"

        # Exams and announcements for the specific day
        exams_today_all = [_row_to_dict(e) for e in db.get_exam_schedules(
            user_id,
            start_date=target_date.strftime('%Y-%m-%d'),
            end_date=target_date.strftime('%Y-%m-%d')
        )]
        exams_today = []
        for exam in exams_today_all:
            start_dt, end_dt = _exam_timing_bounds(exam)
            if not start_dt or not end_dt:
                continue
            if end_dt <= datetime.now():
                continue
            exams_today.append(exam)

        announcements_today = [_row_to_dict(a) for a in db.get_announcements(
            user_id,
            start_date=target_date.strftime('%Y-%m-%d'),
            end_date=target_date.strftime('%Y-%m-%d')
        )]

        task_list_payload = _build_dashboard_task_list(user_id, target_date)
        exams_overview = _build_exam_schedule_overview(user_id, target_date)
        
        # Get AI-generated study schedule for this specific day
        study_sessions = []
        try:
            user = _row_to_dict(db.get_user(user_id))
            tasks = _prepare_tasks_for_planner(db.get_user_tasks(user_id))
            
            if tasks:  # Only generate if there are tasks
                # Generate simple schedule without calling Gemini repeatedly
                schedule_data = _generate_simple_schedule(user, tasks)
                
                # Find sessions for this specific day
                target_date_str = target_date.strftime('%Y-%m-%d')
                for day_plan in schedule_data.get('day_plan', []):
                    if day_plan.get('date') == target_date_str:
                        study_sessions = day_plan.get('sessions', [])
                        break
        except Exception as e:
            print(f"⚠️ Error getting study sessions: {e}")
            # Continue without study sessions if there's an error
        
        return jsonify({
            "success": True,
            "date": target_date.strftime('%Y-%m-%d'),
            "day_name": day_name,
            "classes": classes_today,
            "classes_today": classes_today,
            "classes_next_day": classes_next_day,
            "classes_focus": {
                "day_name": focus_day_name,
                "date": focus_date_obj.strftime('%Y-%m-%d') if focus_date_obj else None,
                "is_today": focus_is_today,
                "items": focus_classes,
                "reason": focus_reason,
            },
            "task_list": task_list_payload,
            "exams": exams_today,
            "exams_schedule": exams_overview,
            "announcements": announcements_today,
            "study_sessions": study_sessions
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/free-time', methods=['GET'])
def get_free_time():
    """Get available free time blocks for a specific day"""
    user_id = request.args.get('user_id', type=int)
    date_str = request.args.get('date')  # Format: YYYY-MM-DD
    
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    
    try:
        # Parse date or use tomorrow
        if date_str:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            target_date = (datetime.now() + timedelta(days=1)).date()
        
        day_name = target_date.strftime('%A')
        
        # Get classes for that day
        classes = db.get_class_schedules(user_id, day_name)
        
        # Calculate free time blocks
        free_blocks = ai_planner._calculate_free_time_blocks(target_date, classes)
        
        return jsonify({
            "success": True,
            "date": target_date.strftime('%Y-%m-%d'),
            "day_name": day_name,
            "free_time_blocks": free_blocks
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/flashcards', methods=['GET', 'POST'])
def flashcards():
    """
    GET: Retrieve user flashcards
    POST: Create flashcards from notes (text or image)
    """
    if request.method == 'GET':
        user_id = request.args.get('user_id', type=int)
        
        if not user_id:
            return jsonify({"error": "user_id required"}), 400
        
        try:
            flashcards_list = db.get_user_flashcards(user_id, limit=100)
            batches = db.get_flashcard_batches(user_id, limit=25)
            modules = []
            skipped_modules = 0
            for batch in batches:
                batch_dict = _row_to_dict(batch)
                card_count = (
                    batch_dict.get('flashcards_generated')
                    or batch_dict.get('flashcard_count')
                    or 0
                )
                batch_dict['available_flashcards'] = card_count

                if card_count <= 0:
                    skipped_modules += 1
                    continue

                latest_attempt = db.get_latest_quiz_attempt(batch_dict.get('id'), user_id)
                if latest_attempt:
                    batch_dict['latest_attempt'] = latest_attempt
                modules.append(batch_dict)
            weekly_points = db.get_user_weekly_points(user_id)
            return jsonify({
                "success": True,
                "flashcards": flashcards_list,
                "modules": modules,
                "weekly_points": weekly_points,
                "total_flashcards": len(flashcards_list),
                "skipped_empty_modules": skipped_modules
            })
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    elif request.method == 'POST':
        data = request.json
        user_id = data.get('user_id')
        notes_text = data.get('notes_text')
        image_path = data.get('image_path')
        topic = data.get('topic')
        module_name = data.get('module_name') or topic or 'General Study'
        count = data.get('count', 10)
        
        if not user_id:
            return jsonify({"error": "user_id required"}), 400
        
        if not notes_text and not image_path:
            return jsonify({"error": "notes_text or image_path required"}), 400
        
        try:
            from ai_logic.flashcard_generator import FlashcardGenerator
            
            generator = FlashcardGenerator()
            
            # Generate flashcards from image or text
            if image_path:
                flashcards = generator.generate_flashcards_from_image(image_path, topic, count)
            else:
                flashcards = generator.generate_flashcards(notes_text, topic, count)

            note_id = None
            if notes_text:
                note_id = db.create_study_note(
                    user_id=user_id,
                    title=f"{module_name} upload",
                    content=notes_text,
                    source_type='text',
                    source_path=image_path,
                    module_name=module_name,
                    topic=topic
                )

            batch_id = db.create_flashcard_batch(
                user_id=user_id,
                module_name=module_name,
                topic=topic,
                note_id=note_id,
                source_path=image_path
            )

            # Save flashcards to database
            flashcard_ids = []
            for card in flashcards:
                card_id = db.create_flashcard(
                    user_id,
                    card['question'],
                    card['answer'],
                    topic=topic,
                    module_name=module_name,
                    note_id=note_id,
                    batch_id=batch_id,
                    source_path=image_path
                )
                flashcard_ids.append(card_id)

            quiz_questions = []
            if flashcards:
                quiz_questions = generator.generate_quiz(flashcards, count=min(5, len(flashcards)))
                for question in quiz_questions:
                    options = question.get('options') or []
                    db.save_quiz_question(
                        user_id,
                        batch_id,
                        question.get('question', 'Quiz question'),
                        options,
                        question.get('correct_index', 0),
                        question.get('explanation')
                    )

            db.update_flashcard_batch_counts(batch_id, flashcard_count=len(flashcards), quiz_count=len(quiz_questions))
            
            return jsonify({
                "success": True,
                "flashcards_created": len(flashcard_ids),
                "flashcard_ids": flashcard_ids,
                "flashcards": flashcards,
                "batch_id": batch_id,
                "quiz_questions": quiz_questions
            })
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500


@app.route('/api/study-session', methods=['POST', 'PUT'])
def study_session():
    """
    POST: Start a new study session
    PUT: End study session
    """
    if request.method == 'POST':
        data = request.json
        user_id = data.get('user_id')
        topic = data.get('topic')
        notes_image_path = data.get('notes_image_path')
        
        if not all([user_id, topic]):
            return jsonify({"error": "user_id and topic required"}), 400
        
        try:
            # Check if there's already an active session
            active_session = db.get_active_study_session(user_id)
            if active_session:
                return jsonify({
                    "error": "You already have an active study session",
                    "active_session": _row_to_dict(active_session)
                }), 400
            
            session_id = db.create_study_session(user_id, topic, notes_image_path=notes_image_path)
            
            return jsonify({
                "success": True,
                "session_id": session_id,
                "message": f"Study session started for {topic}"
            })
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    elif request.method == 'PUT':
        data = request.json
        user_id = data.get('user_id')
        session_id = data.get('session_id')
        
        if not user_id:
            return jsonify({"error": "user_id required"}), 400
        
        try:
            # Get active session if session_id not provided
            if not session_id:
                session = db.get_active_study_session(user_id)
                if not session:
                    return jsonify({"error": "No active study session found"}), 404
                session_id = session['id']
            
            # End the session
            success = db.end_study_session(session_id)
            
            if success:
                return jsonify({
                    "success": True,
                    "message": "Study session ended",
                    "session_id": session_id
                })
            else:
                return jsonify({"error": "Failed to end session"}), 500
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@app.route('/api/quiz', methods=['POST'])
def generate_quiz():
    """Generate a quiz from flashcards"""
    data = request.json
    user_id = data.get('user_id')
    count = data.get('count', 5)
    topic = data.get('topic')
    batch_id = data.get('batch_id')
    
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    
    try:
        generator = None

        def require_generator():
            nonlocal generator
            if generator is not None:
                return generator
            from ai_logic.flashcard_generator import FlashcardGenerator
            generator = FlashcardGenerator()
            return generator

        if batch_id:
            stored_questions = db.get_quiz_questions_for_batch(batch_id)
            if not stored_questions:
                flashcards = db.get_user_flashcards(user_id, limit=50, batch_id=batch_id)
                if not flashcards:
                    return jsonify({"error": "No flashcards found for this module"}), 404
                generator_instance = require_generator()
                generated = generator_instance.generate_quiz(flashcards, min(count, len(flashcards)))
                for question in generated:
                    db.save_quiz_question(
                        user_id,
                        batch_id,
                        question.get('question', 'Quiz question'),
                        question.get('options') or [],
                        question.get('correct_index', 0),
                        question.get('explanation')
                    )
                db.update_flashcard_batch_counts(batch_id, quiz_count=len(generated))
                stored_questions = db.get_quiz_questions_for_batch(batch_id)
            quiz_payload = []
            for row in stored_questions:
                row_dict = _row_to_dict(row)
                options = json.loads(row_dict.get('options_json') or '[]')
                quiz_payload.append({
                    "id": row_dict.get('id'),
                    "question": row_dict.get('question'),
                    "options": options,
                    "correct_index": row_dict.get('correct_index'),
                    "explanation": row_dict.get('explanation')
                })
        else:
            flashcards = db.get_user_flashcards(user_id, limit=50)
            if not flashcards:
                return jsonify({"error": "No flashcards available for quiz"}), 404
            generator_instance = require_generator()
            quiz_payload = generator_instance.generate_quiz(flashcards, count)
        
        return jsonify({
            "success": True,
            "quiz": quiz_payload,
            "total_questions": len(quiz_payload),
            "batch_id": batch_id
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        if isinstance(e, ValueError) and 'GEMINI_API_KEY' in str(e):
            return jsonify({"error": "Flashcard generator is not configured. Please set GEMINI_API_KEY to create new quizzes."}), 503
        return jsonify({"error": str(e)}), 500


@app.route('/api/quiz/attempt', methods=['POST'])
def submit_quiz_attempt():
    """Record quiz answers and award weekly points"""
    data = request.json or {}
    user_id = data.get('user_id')
    batch_id = data.get('batch_id')
    answers = data.get('answers', [])
    duration_ms = data.get('duration_ms')

    if not user_id or not batch_id:
        return jsonify({"error": "user_id and batch_id required"}), 400

    questions = db.get_quiz_questions_for_batch(batch_id)
    if not questions:
        return jsonify({"error": "No quiz found for this module"}), 404

    question_lookup = {q['id']: q for q in questions}
    correct = 0
    evaluated = []
    for answer in answers:
        q_id = answer.get('question_id')
        selected = answer.get('selected_index')
        question = question_lookup.get(q_id)
        if not question:
            continue
        is_correct = selected == question.get('correct_index')
        if is_correct:
            correct += 1
        evaluated.append({
            "question_id": q_id,
            "selected_index": selected,
            "correct": is_correct
        })

    total_questions = len(questions)
    accuracy = (correct / total_questions) if total_questions else 0

    if accuracy >= 0.9:
        base_points = 120
    elif accuracy >= 0.75:
        base_points = 90
    elif accuracy >= 0.6:
        base_points = 60
    else:
        base_points = 30 if total_questions else 0

    week_start = (datetime.now().date() - timedelta(days=datetime.now().weekday()))
    latest_attempt = db.get_latest_quiz_attempt(batch_id, user_id)
    weekly_awarded = True
    if latest_attempt:
        last_completed = _parse_datetime(latest_attempt.get('completed_at'))
        if last_completed and last_completed.date() >= week_start:
            weekly_awarded = False

    awarded_points = base_points if weekly_awarded else 0
    if awarded_points > 0:
        db.update_user_score(user_id, awarded_points)

    attempt_id = db.record_quiz_attempt(
        user_id,
        batch_id,
        correct,
        total_questions,
        awarded_points,
        evaluated,
        duration_ms=duration_ms
    )

    return jsonify({
        "success": True,
        "attempt_id": attempt_id,
        "correct": correct,
        "total": total_questions,
        "accuracy": round(accuracy, 2),
        "points_awarded": awarded_points,
        "weekly_points": db.get_user_weekly_points(user_id),
        "weekly_limited": not weekly_awarded,
        "duration_ms": duration_ms
    })


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

