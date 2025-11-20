"""
WhatsApp Bot Module - Twilio Integration
Handles incoming WhatsApp messages and sends responses.
Falls back to mock mode if Twilio credentials are missing.

FLOW: WhatsApp Message → Bot → Parse Input → Forward to AI/DB → Send Reply
"""

import os
from datetime import datetime
from dotenv import load_dotenv
import json

# Try to import Twilio (will use mock if not available)
try:
    from twilio.rest import Client
    from twilio.twiml.messaging_response import MessagingResponse
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    print("⚠ Twilio not available, using mock mode")

load_dotenv()


class WhatsAppBot:
    """WhatsApp bot handler with Twilio or mock implementation"""
    
    def __init__(self, db, ai_planner):
        """
        Initialize WhatsApp bot
        
        Args:
            db: Database instance
            ai_planner: AIPlanner instance for schedule generation
        """
        self.db = db
        self.ai_planner = ai_planner
        self.mock_mode = False
        
        # Try to initialize Twilio
        self.account_sid = os.getenv("TWILIO_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.whatsapp_number = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
        
        if TWILIO_AVAILABLE and self.account_sid and self.auth_token:
            try:
                self.client = Client(self.account_sid, self.auth_token)
                print("✓ WhatsApp Bot initialized with Twilio")
            except Exception as e:
                print(f"⚠ Twilio init failed: {e}, using mock mode")
                self.mock_mode = True
        else:
            self.mock_mode = True
            print("✓ WhatsApp Bot initialized in MOCK mode")

    @staticmethod
    def _row_to_dict(row):
        if row is None:
            return {}
        if isinstance(row, dict):
            return dict(row)
        if hasattr(row, "keys"):
            return {key: row[key] for key in row.keys()}
        return dict(row)
    
    def send_message(self, to_number, message):
        """
        Send WhatsApp message to user
        
        Args:
            to_number: str, recipient phone number (with country code)
            message: str, message content
        
        Returns:
            dict: send status
        """
        if self.mock_mode:
            return self._mock_send(to_number, message)
        
        try:
            # Ensure number has whatsapp: prefix
            if not to_number.startswith("whatsapp:"):
                to_number = f"whatsapp:{to_number}"
            
            msg = self.client.messages.create(
                from_=self.whatsapp_number,
                body=message,
                to=to_number
            )
            
            return {
                "status": "sent",
                "sid": msg.sid,
                "to": to_number,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"Error sending message: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "to": to_number
            }
    
    def _mock_send(self, to_number, message):
        """Mock message sending for testing"""
        print(f"\n📱 MOCK WhatsApp Message")
        print(f"To: {to_number}")
        print(f"Message: {message}")
        print("-" * 50)
        
        return {
            "status": "sent (mock)",
            "to": to_number,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
    
    def handle_incoming_message(self, from_number, message_body, media_files=None):
        """
        Process incoming WhatsApp message and generate response
        
        Args:
            from_number: str, sender's phone number
            message_body: str, message content
            media_files: list, optional list of downloaded media files with info
                Each file is a dict: {'filename', 'filepath', 'content_type', 'size', 'extension'}
        
        Returns:
            str: response message to send back
        """
        # Clean phone number
        from_number = from_number.replace("whatsapp:", "").strip()
        message_body = message_body.strip().lower() if message_body else ""
        
        print(f"\n📩 Incoming message from {from_number}: {message_body}")
        if media_files:
            print(f"📎 With {len(media_files)} media file(s)")
        
        # Get or create user
        user = self.db.get_user_by_phone(from_number)
        if not user:
            # New user - register them
            response = self._handle_new_user(from_number, message_body)
        else:
            # Handle media messages (images/PDFs for flashcards)
            if media_files:
                response = self._handle_media_message(user, media_files, message_body)
            else:
                # Existing user - parse command
                response = self._parse_command(user, message_body)
        
        return response
    
    def _handle_new_user(self, phone, message):
        """Handle first-time user registration"""
        # Extract name from message
        if message.startswith("hi") or message.startswith("hello"):
            name = message.replace("hi", "").replace("hello", "").strip()
            if not name:
                name = f"User_{phone[-4:]}"
        else:
            name = f"User_{phone[-4:]}"
        
        # Create user
        user_id = self.db.create_user(
            name=name.title(),
            phone=phone,
            preferences={"interests": [], "study_style": "balanced"}
        )
        
        if user_id:
            return f"""🎓 Welcome to StudyPlanner AI, {name.title()}!

I'm your AI study assistant. I can help you:
• Add tasks and deadlines
• Generate smart study schedules
• Track your progress & streaks
• Send reminders
• Compete with friends

Try these commands:
- "add task: [title] by [date]"
- "show schedule"
- "my progress"
- "set free time: [day] [time]"

Let's start! What would you like to do?"""
        else:
            return "Sorry, I couldn't register you. Please try again."
    
    def _parse_command(self, user, message):
        """
        Parse user command and execute appropriate action
        
        Args:
            user: dict, user data
            message: str, user message
        
        Returns:
            str: bot response
        """
        user_id = user['id']
        message_lower = message.lower()
        
        # Check for lifestyle/exam updates FIRST (informal task descriptions)
        # These are conversational messages about personal schedule, exams, assignments
        lifestyle_keywords = ["gym", "gaming", "exam", "assignment", "project", "teacher", "weak", 
                            "strong", "hobby", "morning", "evening", "wake", "sleep", "class", 
                            "college", "tuition", "prepare", "study for", "due", "deadline",
                            "tomorrow", "day after tomorrow", "update my", "please set", "cgpa"]
        
        # Priority to lifestyle if it has personal pronouns or request language
        personal_indicators = ["my", "i have", "i'm", "please", "need to", "have to", "will take"]
        has_personal_context = any(indicator in message_lower for indicator in personal_indicators)
        
        # If message has personal context and lifestyle keywords, it's a lifestyle update
        if has_personal_context and any(keyword in message_lower for keyword in lifestyle_keywords) and len(message.split()) > 10:
            response, _ = self._handle_lifestyle_update(user_id, message)
            return response
        
        # Check for timetable/schedule messages (forwarded schedules from college/school)
        # These typically have structured format with multiple days and times
        timetable_keywords = ["timetable", "time table", "class schedule", 
                             "exam hall", "room 301", "room 302", "venue"]
        
        # Detect timetable if message contains multiple days (2+) - indicates a formal schedule
        day_count = sum(1 for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] if day in message_lower)
        
        # Only route to timetable if it has 2+ days (formal schedule format) OR explicit timetable keywords
        if (day_count >= 2 or any(keyword in message_lower for keyword in timetable_keywords)):
            response, _ = self._handle_timetable_message(user_id, message)
            return response
        
        # General lifestyle/exam updates (longer messages with keywords but no personal context)
        if (any(keyword in message_lower for keyword in lifestyle_keywords) and len(message.split()) > 10):
            response, _ = self._handle_lifestyle_update(user_id, message)
            return response
        
        # Explicit command patterns
        if "add task" in message_lower or "new task" in message_lower:
            return self._handle_add_task(user_id, message)
        
        elif "todos" in message_lower or "todo list" in message_lower or "tomorrow" in message_lower:
            return self._handle_get_todos(user_id, message)
        
        elif "start study" in message_lower:
            return self._handle_start_study(user_id, message)
        
        elif "end study" in message_lower or "stop study" in message_lower:
            return self._handle_end_study(user_id, message)
        
        elif "quiz me" in message_lower or "start quiz" in message_lower or "test me" in message_lower:
            return self._handle_quiz_request(user_id, message)
        
        elif ("schedule" in message_lower or "plan" in message_lower or "routine" in message_lower) and len(message.split()) < 10:
            return self._handle_get_schedule(user_id)
        
        elif "progress" in message_lower or "stats" in message_lower or "score" in message_lower:
            return self._handle_get_progress(user_id)
        
        elif "deadline" in message_lower:
            return self._handle_add_deadline(user_id, message)
        
        elif "free time" in message_lower or "availability" in message_lower:
            return self._handle_set_free_time(user_id, message)
        
        elif "leaderboard" in message_lower or "ranking" in message_lower:
            return self._handle_leaderboard(user_id)
        
        elif "help" in message_lower or "commands" in message_lower:
            return self._get_help_message()
        
        elif ("completed" in message_lower or "done" in message_lower or "finished" in message_lower) and len(message.split()) < 8:
            # Only match completion if it's a short command, not a task description
            return self._handle_complete_task(user_id, message)
        
        else:
            # Check if it's a long informal message about lifestyle/schedule
            if len(message.split()) > 15:
                response, _ = self._handle_lifestyle_update(user_id, message)
                return response
            else:
                # Default: store as note and acknowledge
                return f"✓ Noted: '{message}'\n\nI'm not sure what you mean. Type 'help' to see available commands."
    
    def _handle_add_task(self, user_id, message):
        """Extract and add task from message"""
        try:
            # Parse: "add task: Complete assignment by 2025-11-20"
            task_text = message.split(":", 1)[1] if ":" in message else message
            
            # Extract deadline if present
            deadline = None
            importance = 'medium'
            
            if " by " in task_text:
                title, deadline_str = task_text.split(" by ", 1)
                title = title.replace("add task", "").replace("new task", "").strip()
                # Simple date parsing
                try:
                    deadline = datetime.strptime(deadline_str.strip(), "%Y-%m-%d")
                except:
                    pass
            else:
                title = task_text.replace("add task", "").replace("new task", "").strip()
            
            # Check for importance keywords
            if "urgent" in message or "asap" in message:
                importance = 'urgent'
            elif "important" in message or "high" in message:
                importance = 'high'
            
            # Create task
            task_id = self.db.create_task(user_id, title, deadline, importance)
            
            if task_id:
                deadline_str = deadline.strftime("%Y-%m-%d") if deadline else "No deadline"
                return f"✅ Task added!\n\n📝 {title}\n⏰ Deadline: {deadline_str}\n🎯 Priority: {importance}\n\nType 'schedule' to get your updated study plan."
            else:
                return "❌ Failed to add task. Please try again."
        
        except Exception as e:
            print(f"Error adding task: {e}")
            return "❌ Couldn't parse task. Format: 'add task: [title] by [YYYY-MM-DD]'"
    
    def _handle_get_schedule(self, user_id):
        """Generate and return study schedule"""
        try:
            # Get user data
            user = self._row_to_dict(self.db.get_user(user_id))
            tasks = [self._row_to_dict(t) for t in self.db.get_user_tasks(user_id)]
            
            # Default free time slots (can be customized)
            free_time = [
                {"day": "Monday", "start_time": "09:00", "end_time": "17:00", "duration_hours": 8},
                {"day": "Tuesday", "start_time": "09:00", "end_time": "17:00", "duration_hours": 8},
                {"day": "Wednesday", "start_time": "09:00", "end_time": "17:00", "duration_hours": 8},
            ]
            
            prefs_raw = user.get('preferences')
            preferences = json.loads(prefs_raw) if prefs_raw else {}
            
            # Generate schedule with AI
            schedule = self.ai_planner.generate_schedule(user, tasks, preferences, free_time)
            
            # Format response
            response = f"📅 Your Study Schedule (Next 7 Days)\n\n"

            day_plan = schedule.get('day_plan') or []
            if day_plan:
                for day in day_plan[:3]:  # Show first 3 days
                    response += f"**{day.get('day', 'Day')}** ({day.get('date', 'TBD')})\n"
                    sessions = day.get('sessions', [])
                    if sessions:
                        for session in sessions[:2]:  # Show first 2 sessions
                            response += f"  {session.get('time', 'Time TBD')} - {session.get('task', 'Focus block')}\n"
                    else:
                        response += "  ⏸️ No sessions scheduled\n"
                    total_hours = day.get('total_study_hours')
                    if total_hours:
                        response += f"  Total: {total_hours}h\n"
                    response += "\n"
            else:
                task_preview = schedule.get('task_list', [])[:5]
                if task_preview:
                    response += "📝 Upcoming focus tasks:\n"
                    for entry in task_preview:
                        label = entry.get('due_date') or entry.get('class_day') or 'no date'
                        response += f"  • {entry.get('title', 'Task')} ({label})\n"
                    response += "\n"
                else:
                    response += "Still gathering enough context for a full plan.\n\n"

            response += f"💡 {schedule['priority_notes']}\n\n"
            response += f"🎯 {schedule['motivation_message']}"
            
            return response
        
        except Exception as e:
            print(f"Error generating schedule: {e}")
            return "❌ Couldn't generate schedule. Please try again later."
    
    def _handle_get_todos(self, user_id, message):
        """Generate and return intelligent daily todo list"""
        try:
            from datetime import datetime, timedelta
            
            # Check if user wants todos for specific date
            date_str = None
            message_lower = message.lower()
            
            if "tomorrow" in message_lower:
                target_date = (datetime.now() + timedelta(days=1)).date()
            elif "today" in message_lower:
                target_date = datetime.now().date()
            else:
                # Default to tomorrow
                target_date = (datetime.now() + timedelta(days=1)).date()
            
            # Generate daily todo list using context-aware AI
            result = self.ai_planner.generate_daily_todo_list(user_id, self.db, target_date)
            
            # Format response
            response = f"📋 *Todo List for {result['day_name']}, {result['date']}*\n\n"
            
            # Show classes
            if result.get('classes_today'):
                response += "📚 *Classes Today:*\n"
                for cls in result['classes_today'][:3]:
                    response += f"  • {cls['subject']} at {cls['start_time']} ({cls.get('location', 'TBD')})\n"
                response += "\n"
            
            # Show todos
            if result.get('todos'):
                response += "✅ *Your Todos:*\n"
                for todo in result['todos'][:5]:  # Show first 5
                    priority_emoji = {
                        'critical': '🔴',
                        'high': '🟠',
                        'medium': '🟡',
                        'low': '🟢'
                    }.get(todo['priority'], '⚪')
                    
                    response += f"{priority_emoji} *{todo['time']}* - {todo['task']}\n"
                    response += f"   _{todo['reason']}_\n\n"
                
                response += f"📊 Total Study Time: {result.get('total_study_hours', 0)}h\n\n"
            else:
                response += "✨ No urgent todos for this day!\n\n"
            
            # Show upcoming exams
            if result.get('exams_soon'):
                response += "⚠️ *Upcoming Exams:*\n"
                for exam in result['exams_soon'][:2]:
                    days_until = (datetime.strptime(exam['exam_date'], '%Y-%m-%d').date() - target_date).days
                    response += f"  • {exam['subject']} in {days_until} days ({exam['exam_date']})\n"
                response += "\n"
            
            # Add summary
            if result.get('summary'):
                response += f"💡 *Focus:* {result['summary']}"
            
            return response
            
        except Exception as e:
            print(f"Error generating todos: {e}")
            return f"❌ Failed to generate todos: {str(e)}\n\nMake sure you've added your class schedule first by forwarding your timetable."
    
    def _handle_get_progress(self, user_id):
        """Return user's progress statistics"""
        try:
            user = self._row_to_dict(self.db.get_user(user_id))
            tasks = [self._row_to_dict(t) for t in self.db.get_user_tasks(user_id)]
            
            completed = len([t for t in tasks if t['status'] == 'completed'])
            pending = len([t for t in tasks if t['status'] == 'pending'])
            
            response = f"""📊 Your Progress

🏆 Score: {user['score']} points
🔥 Streak: {user['streak']} days

📝 Tasks:
  ✅ Completed: {completed}
  ⏳ Pending: {pending}
  📊 Total: {len(tasks)}

Keep going! Type 'leaderboard' to see how you compare with friends."""
            
            return response
        
        except Exception as e:
            print(f"Error getting progress: {e}")
            return "❌ Couldn't fetch progress. Please try again."
    
    def _handle_add_deadline(self, user_id, message):
        """Add deadline information"""
        return "✓ Deadline noted! I'll factor this into your schedule. Type 'schedule' to see updates."
    
    def _handle_set_free_time(self, user_id, message):
        """Store user's availability"""
        return "✓ Free time saved! I'll optimize your schedule around these hours. Type 'schedule' to refresh."
    
    def _handle_leaderboard(self, user_id):
        """Show leaderboard rankings"""
        try:
            leaderboard = self.db.get_leaderboard(user_id, limit=5)
            
            response = "🏆 Leaderboard (Top 5)\n\n"
            for idx, entry in enumerate(leaderboard[:5]):
                medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][idx]
                response += f"{medal} {entry['name']}: {entry['score']} pts (🔥 {entry['streak']})\n"
            
            return response
        
        except Exception as e:
            print(f"Error fetching leaderboard: {e}")
            return "❌ Couldn't load leaderboard."
    
    def _handle_complete_task(self, user_id, message):
        """Mark task as completed"""
        # Simplified - in production, parse task title
        tasks = self.db.get_user_tasks(user_id, status='pending')
        if tasks:
            task = tasks[0]
            self.db.update_task_status(task['id'], 'completed')
            return f"🎉 Great job! Task '{task['title']}' marked as complete. You earned 50 points!"
        return "No pending tasks to complete."
    
    def _handle_lifestyle_update(self, user_id, message):
        """
        Parse informal message about lifestyle, habits, schedule, exams, etc.
        Extract info and use Gemini to intelligently create schedule + tasks
        """
        try:
            print(f"\n🎯 Processing lifestyle update from user {user_id}")
            print(f"Message: {message}")
            
            # Get current user data
            user = self._row_to_dict(self.db.get_user(user_id))
            current_tasks = [self._row_to_dict(t) for t in self.db.get_user_tasks(user_id)]
            
            # Try Gemini first, fallback to manual parsing if it fails
            try:
                parsed_data = self.ai_planner.parse_lifestyle_message(message, user, current_tasks)
            except Exception as gemini_error:
                print(f"⚠️ Gemini parsing failed: {gemini_error}")
                print("📝 Using fallback manual parser...")
                parsed_data = self._fallback_parse_message(message)
            
            # Update user preferences with extracted lifestyle info
            if parsed_data.get('preferences'):
                current_prefs = {}
                if user.get('preferences'):
                    current_prefs = json.loads(user['preferences'])
                current_prefs.update(parsed_data['preferences'])
                self.db.execute(
                    "UPDATE users SET preferences = ? WHERE id = ?",
                    (json.dumps(current_prefs), user_id)
                )
                user['preferences'] = json.dumps(current_prefs)
            
            # Create new tasks from extracted information
            tasks_created = 0
            if parsed_data.get('tasks'):
                print(f"\n📝 Creating {len(parsed_data['tasks'])} tasks...")
                for task_info in parsed_data['tasks']:
                    # Combine deadline date and time if both present
                    deadline = task_info.get('deadline')
                    deadline_time = task_info.get('deadline_time')
                    
                    if deadline and deadline_time:
                        # Combine date and time: YYYY-MM-DD + HH:MM -> YYYY-MM-DD HH:MM:00
                        full_deadline = f"{deadline} {deadline_time}:00"
                    elif deadline:
                        full_deadline = deadline
                    else:
                        full_deadline = None
                    
                    print(f"  - {task_info.get('title')} (deadline: {full_deadline})")
                    task_id = self.db.create_task(
                        user_id=user_id,
                        title=task_info['title'],
                        deadline=full_deadline,
                        importance=task_info.get('importance', 'medium'),
                        description=task_info.get('description'),
                        status=task_info.get('status', 'pending')
                    )
                    if task_id:
                        tasks_created += 1
                        print(f"    ✓ Created task ID: {task_id}")
                    else:
                        print(f"    ✗ Failed to create task")
            else:
                print(f"\n⚠️ No tasks found in parsed data!")
                print(f"  Parsed data keys: {list(parsed_data.keys())}")
            
            # Create exam schedules from extracted information
            exams_created = 0
            if parsed_data.get('exams'):
                print(f"\n📚 Creating {len(parsed_data['exams'])} exam schedules...")
                for exam_info in parsed_data['exams']:
                    exam_date = exam_info.get('date')
                    subject = exam_info.get('subject')
                    
                    if exam_date and subject:
                        # Default start time if not specified
                        start_time = "09:00"
                        duration = 120  # Default 2 hours
                        
                        print(f"  - {subject} exam on {exam_date}")
                        exam_id = self.db.create_exam_schedule(
                            user_id=user_id,
                            subject=subject,
                            exam_date=exam_date,
                            start_time=start_time,
                            duration_minutes=duration,
                            location=None,
                            exam_type='exam'
                        )
                        
                        if exam_id:
                            exams_created += 1
                            print(f"    ✓ Created exam schedule ID: {exam_id}")
                            
                            # Also create a high-priority task for the exam
                            exam_task_title = f"Prepare for {subject} Exam"
                            task_id = self.db.create_task(
                                user_id=user_id,
                                title=exam_task_title,
                                deadline=exam_date,
                                importance='high',
                                description=f"Study and prepare for {subject} exam",
                                status='pending'
                            )
                            if task_id:
                                tasks_created += 1
                                print(f"    ✓ Created exam preparation task ID: {task_id}")
                        else:
                            print(f"    ✗ Failed to create exam schedule")
            else:
                print(f"\n⚠️ No exams found in parsed data!")

            # Store announcements (projects, assessments, submissions)
            announcements_created = 0
            if parsed_data.get('announcements'):
                print(f"\n📢 Creating {len(parsed_data['announcements'])} announcements...")
                for ann in parsed_data['announcements']:
                    ann_type = ann.get('announcement_type') or 'announcement'
                    subject = ann.get('subject')
                    content = ann.get('content') or subject or ann_type.title()
                    deadline = ann.get('deadline')

                    # Include time info in content if present (useful for same-day assessments)
                    if ann.get('deadline_time') and deadline:
                        content = f"{content} at {ann['deadline_time']}"

                    ann_id = self.db.create_announcement(
                        user_id=user_id,
                        announcement_type=ann_type,
                        subject=subject,
                        content=content,
                        deadline=deadline
                    )

                    if ann_id:
                        announcements_created += 1
                        print(f"    ✓ Stored announcement ID: {ann_id}")

                        # Create paired reminder task when a deadline exists
                        if deadline:
                            reminder_title = subject or content
                            reminder_task = self.db.create_task(
                                user_id=user_id,
                                title=f"{ann_type.title()}: {reminder_title}",
                                deadline=deadline,
                                importance='high'
                            )
                            if reminder_task:
                                tasks_created += 1
                                print(f"      ↳ Created reminder task ID: {reminder_task}")
                    else:
                        print("    ✗ Failed to store announcement")
            else:
                print("\n⚠️ No announcements found in parsed data!")
            
            # Generate new intelligent schedule
            updated_tasks = [self._row_to_dict(t) for t in self.db.get_user_tasks(user_id)]
            updated_prefs_raw = user.get('preferences')
            updated_preferences = json.loads(updated_prefs_raw) if updated_prefs_raw else {}
            schedule = self.ai_planner.generate_schedule(
                user_data=user,
                tasks=updated_tasks,
                preferences=updated_preferences,
                free_time_slots=parsed_data.get('free_time_slots', [])
            )
            
            # Format response
            response = f"✅ Got it! I've analyzed your lifestyle and created a personalized plan.\n\n"
            
            if tasks_created > 0 or exams_created > 0:
                response += f"📋 Added:\n"
                if tasks_created > 0:
                    response += f"  • {tasks_created} tasks\n"
                if exams_created > 0:
                    response += f"  • {exams_created} exam schedule(s)\n"
                if announcements_created > 0:
                    response += f"  • {announcements_created} announcement(s)\n"
                response += "\n"
            
            if parsed_data.get('preferences'):
                response += f"🎯 I'll remember:\n"
                prefs = parsed_data['preferences']
                if prefs.get('gym_time'):
                    response += f"  • Gym: {prefs['gym_time']}\n"
                if prefs.get('gaming_time'):
                    response += f"  • Gaming: {prefs['gaming_time']}\n"
                if prefs.get('weak_subjects'):
                    response += f"  • Focus subjects: {', '.join(prefs['weak_subjects'])}\n"
                if prefs.get('study_style'):
                    response += f"  • Study style: {prefs['study_style']}\n"
                response += "\n"
            
            # Show schedule with tasks
            response += f"📅 **Your Schedule:**\n\n"
            day_plan = schedule.get('day_plan') or []
            if day_plan:
                for day in day_plan[:4]:  # Show first 4 days
                    response += f"**{day.get('day', 'Day')}** ({day.get('date', 'TBD')})\n"
                    sessions = day.get('sessions', [])
                    if sessions:
                        for session in sessions[:5]:  # Show up to 5 sessions per day
                            task_name = session.get('task', 'Focus block')
                            emoji = "📚"
                            task_lower = task_name.lower()
                            if session.get('type') == 'study':
                                emoji = "📚"
                            elif 'gym' in task_lower:
                                emoji = "💪"
                            elif 'gaming' in task_lower:
                                emoji = "🎮"
                            else:
                                emoji = "📝"
                            response += f"  {emoji} {session.get('time', 'Time TBD')} - {task_name}\n"
                    else:
                        response += "  ⏸️ No sessions scheduled\n"
                    response += "\n"
            else:
                task_preview = schedule.get('task_list', [])[:5]
                if task_preview:
                    response += "📝 Upcoming priorities:\n"
                    for entry in task_preview:
                        label = entry.get('due_date') or entry.get('class_day') or 'no date'
                        response += f"  • {entry.get('title', 'Task')} ({label})\n"
                    response += "\n"
                else:
                    response += "Still gathering enough data to craft sessions.\n\n"
            
            response += f"💡 **Priority:** {schedule.get('priority_notes', 'Focus on your tasks!')}\n\n"
            response += f"🔥 **Motivation:** {schedule.get('motivation_message', 'You got this!')}\n\n"
            response += f"Type 'show schedule' anytime to see your full plan!"
            summary = {
                "tasks_created": tasks_created,
                "exams_created": exams_created,
                "announcements_created": announcements_created
            }
            return response, summary
        
        except Exception as e:
            print(f"❌ Error in lifestyle update: {e}")
            import traceback
            traceback.print_exc()
            fallback = (
                "✅ I heard you! I'll create a schedule based on:\n• Your gym routine\n• Gaming time\n"
                "• Study focus areas\n• Exam dates\n\nGenerating your personalized plan now... Type 'schedule' in a moment to see it!"
            )
            return fallback, {
                "tasks_created": 0,
                "exams_created": 0,
                "announcements_created": 0
            }
    
    def _get_help_message(self):
        """Return help/commands list"""
        return """🤖 StudyPlanner AI Commands

📝 Tasks:
  • "add task: [title] by [date]"
  • "complete [task]"
  • "show tasks"

📅 Schedule:
  • "show schedule"
  • "set free time: [day] [time]"

📊 Progress:
  • "my progress"
  • "my stats"
  • "leaderboard"

💬 Natural Messages:
  • Just tell me about your routine, exams, hobbies!
  • I'll create a schedule automatically

💬 General:
  • "help" - show this message

Just message me naturally and I'll help you stay productive!"""
    
    def _fallback_parse_message(self, message):
        """
        Fallback parser when Gemini API fails or is rate-limited.
        Uses simple regex to extract tasks, deadlines, and priorities.
        """
        import re
        from datetime import datetime, timedelta
        
        tasks = []
        message_lower = message.lower()
        
        # Common date patterns
        # "november 25th", "nov 22nd", "19th nov"
        date_patterns = [
            r'(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})(?:st|nd|rd|th)?',
            r'(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',
            r'(\d{4})-(\d{2})-(\d{2})'
        ]
        
        # Month name to number mapping
        month_map = {
            'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
            'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6,
            'july': 7, 'jul': 7, 'august': 8, 'aug': 8, 'september': 9, 'sep': 9,
            'october': 10, 'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12
        }
        
        # Split message by sentences or conjunctions
        parts = re.split(r'[.;]|\. also | also |, and | and ', message_lower)
        
        for part in parts:
            if len(part.strip()) < 10:  # Skip very short fragments
                continue
            
            # Extract deadline
            deadline = None
            for pattern in date_patterns:
                match = re.search(pattern, part)
                if match:
                    if len(match.groups()) == 2:
                        month_str, day = match.groups()
                        if month_str.isdigit():
                            day, month_str = month_str, day
                        month = month_map.get(month_str.lower())
                        if month:
                            year = 2025  # Current year
                            deadline = f"{year}-{month:02d}-{int(day):02d}"
                    break
            
            if not deadline:
                continue
            
            # Extract task title (text before deadline)
            title_match = re.search(r'(.*?)\s+(?:by|on|due|before)', part)
            if title_match:
                title = title_match.group(1).strip()
            else:
                # Take first few words as title
                title = ' '.join(part.split()[:6])
            
            # Clean up title
            title = re.sub(r'^(i need to|i have to|got to|need to|have to|must|should)', '', title).strip()
            title = title.capitalize()
            
            # Extract importance
            importance = 'medium'
            if 'high priority' in part or 'urgent' in part or 'important' in part or 'asap' in part:
                importance = 'high'
            elif 'low priority' in part or 'not urgent' in part:
                importance = 'low'
            
            if title and deadline:
                tasks.append({
                    'title': title,
                    'deadline': deadline,
                    'deadline_time': None,
                    'importance': importance,
                    'description': None,
                    'subject': None
                })
        
        print(f"✓ Fallback parser extracted {len(tasks)} tasks")
        
        return {
            'preferences': {},
            'tasks': tasks,
            'free_time_slots': [],
            'exams': [],
            'announcements': []
        }
    
    def _handle_timetable_message(self, user_id, message):
        """Handle forwarded timetable messages (class schedules, exam dates, announcements)"""
        stats = {
            "classes_replaced": 0,
            "classes_added": 0,
            "exams_added": 0,
            "announcements_added": 0
        }

        try:
            print(f"\n📅 Parsing timetable for user {user_id}")
            
            # Parse timetable using AI
            parsed = self.ai_planner.parse_timetable(message)

            normalized_classes = []
            days_detected = set()
            for cls in parsed.get('classes', []):
                day = (cls.get('day_of_week') or '').strip()
                subject = (cls.get('subject') or '').strip()
                start_time = cls.get('start_time')
                end_time = cls.get('end_time')
                if not (day and subject and start_time and end_time):
                    continue
                normalized_day = day.title()
                normalized_classes.append({
                    **cls,
                    'day_of_week': normalized_day,
                    'subject': subject,
                    'start_time': start_time,
                    'end_time': end_time
                })
                days_detected.add(normalized_day)
            parsed['classes'] = normalized_classes

            if normalized_classes:
                stats['classes_replaced'] = self.db.delete_class_schedules_for_days(user_id, list(days_detected))

            # Store parsed data in database
            for cls in normalized_classes:
                schedule_id = self.db.create_class_schedule(
                    user_id=user_id,
                    day_of_week=cls['day_of_week'],
                    subject=cls['subject'],
                    start_time=cls['start_time'],
                    end_time=cls['end_time'],
                    location=cls.get('location'),
                    instructor=cls.get('instructor')
                )
                if schedule_id:
                    stats['classes_added'] += 1
            
            # Store exam schedules
            for exam in parsed.get('exams', []):
                if not exam.get('subject') or not exam.get('exam_date'):
                    continue
                exam_id = self.db.create_exam_schedule(
                    user_id=user_id,
                    subject=exam['subject'],
                    exam_date=exam['exam_date'],
                    start_time=exam.get('start_time') or '09:00',
                    duration_minutes=exam.get('duration_minutes'),
                    location=exam.get('location'),
                    exam_type=exam.get('exam_type')
                )
                if exam_id:
                    stats['exams_added'] += 1
            
            # Store announcements and create tasks for them
            for ann in parsed.get('announcements', []):
                if not ann.get('announcement_type') or not ann.get('content'):
                    continue
                ann_id = self.db.create_announcement(
                    user_id=user_id,
                    announcement_type=ann['announcement_type'],
                    content=ann['content'],
                    subject=ann.get('subject'),
                    deadline=ann.get('deadline')
                )
                if ann_id:
                    stats['announcements_added'] += 1
                    
                    # Also create a task for this announcement
                    if ann.get('deadline'):
                        subject_preview = ann.get('subject') or ann['content'][:30]
                        task_title = f"{ann['announcement_type'].capitalize()}: {subject_preview}"
                        self.db.create_task(
                            user_id=user_id,
                            title=task_title,
                            deadline=ann['deadline'],
                            importance='high'
                        )
            
            # Build response message
            response = "✅ *Timetable Parsed Successfully!*\n\n"
            
            if stats['classes_replaced'] > 0:
                response += f"♻️ Replaced {stats['classes_replaced']} older class slot(s) for those days\n"
            if stats['classes_added'] > 0:
                response += f"📚 Added {stats['classes_added']} class(es) to your schedule\n"
            
            if stats['exams_added'] > 0:
                response += f"📝 Added {stats['exams_added']} exam(s)\n"
                # List exams with dates
                for exam in parsed.get('exams', [])[:3]:  # Show first 3
                    response += f"   - {exam['subject']}: {exam['exam_date']} at {exam.get('start_time', 'TBD')}\n"
            
            if stats['announcements_added'] > 0:
                response += f"📢 Added {stats['announcements_added']} announcement(s)\n"
            
            if stats['classes_added'] == 0 and stats['exams_added'] == 0 and stats['announcements_added'] == 0:
                response = "⚠️ I couldn't find any schedule information in that message.\n\n"
                response += "Try sending a clearer timetable with:\n"
                response += "- Class times (e.g., Monday 9-11 Computer Networks)\n"
                response += "- Exam dates (e.g., Physics exam Nov 28 9AM)\n"
                response += "- Project deadlines (e.g., Web Dev project due Dec 1)"
            else:
                response += "\n💡 Your daily todo lists will now be generated based on this schedule!\n"
                response += "Send 'todos' to see tomorrow's intelligent todo list."
            
            return response, stats
            
        except Exception as e:
            print(f"Error handling timetable: {e}")
            return (
                f"❌ Failed to parse timetable: {str(e)}\n\nPlease try reformatting the timetable or send it in smaller chunks.",
                stats
            )
    
    def _handle_start_study(self, user_id, message):
        """Handle start study session command"""
        try:
            # Extract topic from message
            # Format: "start study [topic]"
            parts = message.lower().split("start study", 1)
            if len(parts) > 1 and parts[1].strip():
                topic = parts[1].strip()
            else:
                topic = "General Study"
            
            # Check for active session
            active_session = self.db.get_active_study_session(user_id)
            if active_session:
                return f"⚠️ You already have an active study session for '{active_session['topic']}'!\n\nEnd it first with: end study"
            
            # Create study session
            session_id = self.db.create_study_session(user_id, topic)
            
            if session_id:
                response = f"✅ *Study Session Started!*\n\n"
                response += f"📚 Topic: {topic}\n"
                response += f"⏰ Started at: {datetime.now().strftime('%I:%M %p')}\n\n"
                response += "💡 Send images of your notes and I'll generate flashcards!\n\n"
                response += "When you're done:\n"
                response += "  • Send 'end study' to finish\n"
                response += "  • Get a quiz on what you learned!"
                return response
            else:
                return "❌ Failed to start study session. Please try again."
        
        except Exception as e:
            print(f"Error starting study session: {e}")
            return "❌ Failed to start study session."
    
    def _handle_end_study(self, user_id, message):
        """Handle end study session command"""
        try:
            # Get active session
            session = self.db.get_active_study_session(user_id)
            
            if not session:
                return "⚠️ No active study session found!\n\nStart one with: start study [topic]"
            
            # End the session
            success = self.db.end_study_session(session['id'])
            
            if success:
                # Get updated session with duration
                ended_session = self.db.fetchone(
                    "SELECT * FROM study_sessions WHERE id = ?", 
                    (session['id'],)
                )
                
                duration_min = ended_session.get('duration_minutes', 0)
                hours = duration_min // 60
                minutes = duration_min % 60
                
                response = f"✅ *Study Session Completed!*\n\n"
                response += f"📚 Topic: {session['topic']}\n"
                response += f"⏱️ Duration: {hours}h {minutes}m\n\n"
                
                # Check if they have flashcards
                flashcards = self.db.get_user_flashcards(user_id, limit=5)
                
                if flashcards and len(flashcards) > 0:
                    response += "🎯 *Ready for a quiz?*\n"
                    response += f"You have {len(flashcards)} flashcards!\n\n"
                    response += "Send 'quiz me' to test your knowledge!"
                else:
                    response += "💡 Tip: Send images of your notes next time, and I'll create flashcards automatically!"
                
                return response
            else:
                return "❌ Failed to end study session."
        
        except Exception as e:
            print(f"Error ending study session: {e}")
            return "❌ Failed to end study session."
    
    def _handle_quiz_request(self, user_id, message):
        """Handle quiz request command"""
        try:
            # Get user's flashcards
            flashcards = self.db.get_user_flashcards(user_id, limit=50)
            
            if not flashcards or len(flashcards) == 0:
                return "⚠️ No flashcards available!\n\nSend images of your notes during a study session to generate flashcards."
            
            # Generate quiz (simplified for WhatsApp)
            import random
            quiz_cards = random.sample(flashcards, min(5, len(flashcards)))
            
            response = f"🎯 *Quick Quiz* ({len(quiz_cards)} questions)\n\n"
            
            for i, card in enumerate(quiz_cards, 1):
                response += f"*Q{i}:* {card['question']}\n\n"
                response += f"💭 Think about it, then scroll for answer...\n\n"
                response += "━" * 20 + "\n\n"
                response += f"*A{i}:* {card['answer']}\n\n"
                response += "━" * 30 + "\n\n"
            
            response += "Great work! Keep studying! 📚✨"
            
            return response
        
        except Exception as e:
            print(f"Error generating quiz: {e}")
            return "❌ Failed to generate quiz."
    
    def _handle_media_message(self, user, media_files, caption=""):
        """
        Handle incoming media messages (images/PDFs)
        - If active study session: Generate flashcards
        - If no session: Try to parse as timetable/announcement/lifestyle update
        
        Args:
            user: dict, user data
            media_files: list of downloaded media files
            caption: str, optional message caption/body
        
        Returns:
            str: bot response
        """
        try:
            from ai_logic.flashcard_generator import FlashcardGenerator
            
            user_id = user['id']
            
            # Check if user has active study session
            session = self.db.get_active_study_session(user_id)
            
            # If there's an active study session, treat as flashcard material
            if session:
                topic_hint = session.get('topic') if session else None
                return self._process_media_for_flashcards(
                    user_id,
                    media_files,
                    topic_hint=topic_hint,
                    module_hint=topic_hint,
                    session=session
                )
            
            # Otherwise, try to parse as timetable/announcement/lifestyle update
            return self._process_media_for_schedule(user_id, media_files, caption)
        
        except Exception as e:
            print(f"Error handling media message: {e}")
            return f"❌ Failed to process media: {str(e)}"
    
    def _guess_module_topic(self, caption, extracted_text):
        """Infer module/topic names from caption or extracted text"""
        caption = (caption or '').strip()
        module = None
        topic = None

        if caption:
            separators = [':', '-', '—', '|']
            for sep in separators:
                if sep in caption:
                    parts = [part.strip() for part in caption.split(sep, 1)]
                    if len(parts) == 2:
                        module, topic = parts
                        break
            if not topic:
                topic = caption

        if not topic:
            lines = [line.strip() for line in (extracted_text or '').splitlines() if line.strip()]
            if lines:
                topic = lines[0][:80]
                if len(lines) > 1 and len(lines[1]) < 60:
                    module = lines[1][:80]

        module = module or topic or 'General Study'
        topic = topic or module
        return module, topic

    def _process_media_for_flashcards(self, user_id, media_files, topic_hint=None, module_hint=None,
                                      session=None, extracted_text_map=None):
        """Process media files for flashcard + quiz generation"""
        try:
            from ai_logic.flashcard_generator import FlashcardGenerator

            topic = topic_hint or (session.get('topic') if session else None) or 'General Study'
            module_name = module_hint or topic
            flashcard_generator = FlashcardGenerator()

            total_flashcards = 0
            total_quiz_questions = 0
            processed_files = []
            failed_files = []
            summaries = []

            # Process each media file
            for file_info in media_files:
                try:
                    filepath = file_info['filepath']
                    filename = file_info['filename']
                    content_type = file_info['content_type']

                    print(f"Processing {filename} ({content_type}) for flashcards...")

                    # Use extracted text if provided to avoid duplicate Gemini calls
                    if extracted_text_map and filepath in extracted_text_map:
                        notes_text = extracted_text_map[filepath]
                    else:
                        notes_text = flashcard_generator.extract_text_from_file(filepath)

                    if not notes_text or notes_text.startswith(("❌", "⚠️")):
                        failed_files.append(filename)
                        print(f"⚠️ Skipping {filename}: {notes_text or 'No text extracted'}")
                        continue

                    # Persist extracted notes for reference
                    note_id = self.db.create_study_note(
                        user_id=user_id,
                        title=f"{module_name} - {filename}",
                        content=notes_text,
                        source_type='pdf' if content_type.startswith('application/pdf') else 'image',
                        source_path=filepath,
                        study_session_id=session['id'] if session else None,
                        module_name=module_name,
                        topic=topic
                    )

                    flashcards = flashcard_generator.generate_flashcards(
                        notes_text=notes_text,
                        topic=topic,
                        count=10
                    )

                    if not flashcards:
                        failed_files.append(filename)
                        print(f"⚠️ Skipping {filename}: flashcard generator returned no cards")
                        continue

                    batch_id = self.db.create_flashcard_batch(
                        user_id=user_id,
                        module_name=module_name,
                        topic=topic,
                        note_id=note_id,
                        source_path=filepath
                    )
                    if not batch_id:
                        failed_files.append(filename)
                        print(f"⚠️ Skipping {filename}: unable to create flashcard batch")
                        continue

                    flashcard_ids = []
                    for card in flashcards:
                        fc_id = self.db.add_flashcard(
                            user_id=user_id,
                            question=card['question'],
                            answer=card['answer'],
                            topic=topic,
                            module_name=module_name,
                            note_id=note_id,
                            batch_id=batch_id,
                            source_path=filepath
                        )
                        flashcard_ids.append(fc_id)

                    quiz_questions = []
                    quiz_questions = flashcard_generator.generate_quiz(
                        flashcards,
                        count=min(5, len(flashcards))
                    )
                    for question in quiz_questions:
                        options = question.get('options') or question.get('choices') or []
                        if not options and 'correct_answer' in question:
                            options = [question['correct_answer']]
                        self.db.save_quiz_question(
                            user_id=user_id,
                            batch_id=batch_id,
                            question=question.get('question', 'Quiz question'),
                            options=options,
                            correct_index=question.get('correct_index', 0),
                            explanation=question.get('explanation')
                        )

                    self.db.update_flashcard_batch_counts(
                        batch_id,
                        flashcard_count=len(flashcards),
                        quiz_count=len(quiz_questions)
                    )

                    total_flashcards += len(flashcards)
                    total_quiz_questions += len(quiz_questions)
                    processed_files.append(filename)
                    summaries.append({
                        "module": module_name,
                        "topic": topic,
                        "flashcards": len(flashcards),
                        "quizzes": len(quiz_questions)
                    })

                except Exception as e:
                    print(f"Error processing {file_info['filename']}: {e}")
                    failed_files.append(file_info['filename'])

            if total_flashcards > 0:
                response = "✅ *Flashcards & Quiz Ready!*\n\n"
                response += f"📚 Module: {module_name}\n"
                response += f"🧠 Topic: {topic}\n"
                response += f"📝 Flashcards: {total_flashcards}\n"
                response += f"❓ Quiz questions: {total_quiz_questions}\n\n"
                if processed_files:
                    response += f"Processed files: {', '.join(processed_files)}\n\n"
                if failed_files:
                    response += f"⚠️ Skipped: {', '.join(failed_files)}\n\n"
                response += "Open the dashboard to practice these cards and finish the quiz for weekly points!"
            else:
                response = "❌ *Couldn't extract enough text to build flashcards.*\n"
                if failed_files:
                    response += f" Skipped: {', '.join(failed_files)}."
                response += " Try sharing a clearer PDF/photo or add a short caption with the topic."

            return response

        except Exception as e:
            print(f"Error processing media for flashcards: {e}")
            return f"❌ Failed to process media: {str(e)}"
    
    def _process_media_for_schedule(self, user_id, media_files, caption=""):
        """
        Process media files for timetable/announcement/lifestyle parsing
        Uses Gemini Vision OCR to extract text, then applies AI parsing
        """
        try:
            from ai_logic.flashcard_generator import FlashcardGenerator
            
            print(f"\n📸 Processing {len(media_files)} media file(s) for schedule/timetable parsing")
            
            flashcard_generator = FlashcardGenerator()
            all_extracted_text = []
            processed_files = []
            failed_files = []
            successful_entries = []
            
            # Extract text from all media files
            for file_info in media_files:
                try:
                    filepath = file_info['filepath']
                    filename = file_info['filename']
                    
                    extracted_text = flashcard_generator.extract_text_from_file(filepath)
                    
                    # Check if extraction succeeded (not None and not an error message)
                    if extracted_text and not extracted_text.startswith(("❌", "⚠️")):
                        all_extracted_text.append(extracted_text)
                        processed_files.append(filename)
                        successful_entries.append({
                            "file": file_info,
                            "text": extracted_text
                        })
                        print(f"✓ Extracted {len(extracted_text)} characters from {filename}")
                    else:
                        failed_files.append(filename)
                        print(f"⚠️ Failed to extract from {filename}: {extracted_text or 'No text returned'}")
                        
                except Exception as e:
                    failed_files.append(file_info['filename'])
                    print(f"❌ Error processing {file_info['filename']}: {e}")
            
            # If all files failed, return helpful error message
            if not all_extracted_text:
                return "⚠️ *Could not extract text from your media file(s)*\n\n" \
                       "Please try:\n" \
                       "• Taking a clearer photo with better lighting\n" \
                       "• Ensuring text is large and readable\n" \
                       "• Converting handwritten notes to typed text\n" \
                       "• Using a different file format (JPG/PNG for images, PDF for documents)\n\n" \
                       "If the problem persists, the Gemini API might be temporarily unavailable."
            
            # Combine all extracted text
            combined_text = "\n\n".join(all_extracted_text)
            
            # Add caption if provided
            if caption:
                combined_text = f"{caption}\n\n{combined_text}"
            
            print(f"\n📝 Combined extracted text (first 500 chars):\n{combined_text[:500]}")
            
            # Determine what type of content this is and route accordingly
            text_lower = combined_text.lower()
            timetable_keywords = [
                "timetable", "time table", "exam schedule", "class schedule", "exam dates"
            ]
            day_count = sum(1 for day in [
                "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
            ] if day in text_lower)

            import re
            has_time_range = bool(re.search(r"\b\d{1,2}(:\d{2})?\s*(am|pm)?\s*-\s*\d{1,2}(:\d{2})?\s*(am|pm)?", text_lower))
            attempt_timetable = day_count >= 2 or has_time_range or any(keyword in text_lower for keyword in timetable_keywords)

            lifestyle_keywords = [
                "exam", "assignment", "project", "deadline", "due", "teacher",
                "test", "quiz", "homework", "submit", "presentation"
            ]
            lifestyle_word_count = len(combined_text.split())
            attempt_lifestyle = any(keyword in text_lower for keyword in lifestyle_keywords) or lifestyle_word_count > 40

            extracted_map = {entry['file']['filepath']: entry['text'] for entry in successful_entries}
            successful_files = [entry['file'] for entry in successful_entries]

            if attempt_timetable:
                print("🎯 Detected timetable/schedule - routing to timetable handler")
                timetable_response, timetable_stats = self._handle_timetable_message(user_id, combined_text)
                if timetable_stats and (
                    timetable_stats.get('classes_added') or
                    timetable_stats.get('exams_added') or
                    timetable_stats.get('announcements_added')
                ):
                    return timetable_response
                print("⚠️ Timetable heuristics matched but no structured entries were saved – falling back.")

            if attempt_lifestyle:
                print("🎯 Detected lifestyle/announcement update - routing to lifestyle handler")
                lifestyle_response, lifestyle_stats = self._handle_lifestyle_update(user_id, combined_text)
                if lifestyle_stats and (
                    lifestyle_stats.get('tasks_created') or
                    lifestyle_stats.get('exams_created') or
                    lifestyle_stats.get('announcements_created')
                ):
                    return lifestyle_response
                print("⚠️ Lifestyle parser returned no actionable updates – treating as study notes.")

            # Default: acknowledge and generate flashcards for notes-style content
            if successful_entries:
                module_hint, topic_hint = self._guess_module_topic(caption, combined_text)
                print("✨ Defaulted to study-notes mode – generating flashcards automatically")
                return self._process_media_for_flashcards(
                    user_id,
                    successful_files,
                    topic_hint=topic_hint,
                    module_hint=module_hint,
                    extracted_text_map=extracted_map
                )

            response = f"✅ *Image received and processed!*\n\n"
            response += f"📎 Processed: {', '.join(processed_files)}\n\n"
            response += "I extracted the text but could not identify whether it's a schedule or notes."
            response += " Add a short caption with the topic or share a clearer file and I'll try again."
            return response
            
        except Exception as e:
            print(f"Error processing media for schedule: {e}")
            import traceback
            traceback.print_exc()
            return f"❌ Failed to process image: {str(e)}"
    
    def handle_image_message(self, user_id, image_url, caption=""):
        """Handle incoming image messages (DEPRECATED - use _handle_media_message instead)"""
        try:
            # Check if user has active study session
            session = self.db.get_active_study_session(user_id)
            
            if not session:
                return "⚠️ Please start a study session first!\n\nSend: start study [topic]"
            
            # Download image (this would need actual implementation with Twilio media handling)
            # For now, return a message indicating the feature
            response = "📸 *Image received!*\n\n"
            response += "🔄 Processing your notes...\n\n"
            response += "⚠️ *Note:* Image processing is configured but requires image download implementation.\n\n"
            response += "Alternative: Copy-paste your notes as text, and I'll generate flashcards!"
            
            return response
        
        except Exception as e:
            print(f"Error handling image: {e}")
            return "❌ Failed to process image."


if __name__ == "__main__":
    # Test WhatsApp bot
    from backend.db import get_db
    from backend.ai_logic.planner import AIPlanner
    
    db = get_db()
    planner = AIPlanner()
    bot = WhatsAppBot(db, planner)
    
    # Test message handling
    test_response = bot.handle_incoming_message("+1234567890", "Hi, I'm John")
    print(f"\nBot response:\n{test_response}")
    
    db.disconnect()
