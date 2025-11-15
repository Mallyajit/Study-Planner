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
    
    def handle_incoming_message(self, from_number, message_body):
        """
        Process incoming WhatsApp message and generate response
        
        Args:
            from_number: str, sender's phone number
            message_body: str, message content
        
        Returns:
            str: response message to send back
        """
        # Clean phone number
        from_number = from_number.replace("whatsapp:", "").strip()
        message_body = message_body.strip().lower()
        
        print(f"\n📩 Incoming message from {from_number}: {message_body}")
        
        # Get or create user
        user = self.db.get_user_by_phone(from_number)
        if not user:
            # New user - register them
            response = self._handle_new_user(from_number, message_body)
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
        
        # Check for lifestyle/exam updates first (longer messages with specific keywords)
        lifestyle_keywords = ["gym", "gaming", "exam", "assignment", "project", "teacher", "weak", 
                            "strong", "hobby", "morning", "evening", "wake", "sleep", "class", 
                            "college", "tuition", "prepare", "study for", "due", "deadline"]
        
        # Prioritize lifestyle updates (informal task descriptions)
        if (any(keyword in message_lower for keyword in lifestyle_keywords) and len(message.split()) > 10):
            return self._handle_lifestyle_update(user_id, message)
        
        # Explicit command patterns
        if "add task" in message_lower or "new task" in message_lower:
            return self._handle_add_task(user_id, message)
        
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
                return self._handle_lifestyle_update(user_id, message)
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
            
            for day in schedule['day_plan'][:3]:  # Show first 3 days
                response += f"**{day['day']}** ({day['date']})\n"
                for session in day['sessions'][:2]:  # Show first 2 sessions
                    response += f"  {session['time']} - {session['task']}\n"
                response += f"  Total: {day['total_study_hours']}h\n\n"
            
            response += f"💡 {schedule['priority_notes']}\n\n"
            response += f"🎯 {schedule['motivation_message']}"
            
            return response
        
        except Exception as e:
            print(f"Error generating schedule: {e}")
            return "❌ Couldn't generate schedule. Please try again later."
    
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
            response += f"📋 Added {tasks_created} new tasks based on what you told me.\n\n"
            
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
            
            # Show abbreviated schedule
            response += f"📅 **Your New Schedule:**\n\n"
            for day in schedule['day_plan'][:2]:  # Show first 2 days
                response += f"**{day['day']}** ({day['date']})\n"
                for session in day['sessions'][:3]:  # Show first 3 sessions
                    emoji = "📚" if session.get('type') == 'study' else "💪" if 'gym' in session['task'].lower() else "🎮" if 'gaming' in session['task'].lower() else "⏸️"
                    response += f"  {emoji} {session['time']} - {session['task']}\n"
                response += "\n"
            
            response += f"💡 **Priority:** {schedule.get('priority_notes', 'Focus on your tasks!')}\n\n"
            response += f"🔥 **Motivation:** {schedule.get('motivation_message', 'You got this!')}\n\n"
            response += f"Type 'show schedule' anytime to see your full plan!"
            
            return response
            
        except Exception as e:
            print(f"❌ Error in lifestyle update: {e}")
            import traceback
            traceback.print_exc()
            return f"✅ I heard you! I'll create a schedule based on:\n• Your gym routine\n• Gaming time\n• Study focus areas\n• Exam dates\n\nGenerating your personalized plan now... Type 'schedule' in a moment to see it!"
    
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
            'exams': []
        }


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
