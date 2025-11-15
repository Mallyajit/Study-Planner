"""
AI Planner Module - Gemini Integration for Adaptive Scheduling
Generates intelligent study plans based on user tasks, deadlines, and preferences.

FLOW: WhatsApp Bot → Planner → Gemini API → JSON Schedule → Database
"""

import os
import json
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

class AIPlanner:
    """Gemini-powered adaptive study planner"""
    
    def __init__(self):
        """Initialize Gemini API"""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in .env file")
        
        genai.configure(api_key=api_key)
        # Use supported Gemini model (gemini-2.0-flash is fast and reliable)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        print("✓ Gemini AI initialized for planning")
    
    def generate_schedule(self, user_data, tasks, preferences, free_time_slots):
        """
        Generate adaptive study schedule using Gemini AI
        
        Args:
            user_data: dict with user info (name, streak, score)
            tasks: list of task dicts (title, deadline, importance, status)
            preferences: dict with interests, study habits
            free_time_slots: list of available time windows
        
        Returns:
            dict: JSON schedule with day_plan, priority_notes, adjustments, motivation
        """
        normalized_user = self._row_to_dict(user_data)
        normalized_tasks = self._normalize_tasks(tasks)

        # Build context prompt for Gemini
        prompt = self._build_schedule_prompt(normalized_user, normalized_tasks, preferences, free_time_slots)
        
        try:
            # Call Gemini API
            response = self.model.generate_content(prompt)
            
            # Parse JSON response
            schedule = self._parse_gemini_response(response.text)
            
            # Add metadata
            schedule['generated_at'] = datetime.now().isoformat()
            schedule['user_id'] = normalized_user.get('id')
            
            return schedule
            
        except Exception as e:
            print(f"Error generating schedule: {e}")
            return self._get_fallback_schedule(normalized_tasks)
    
    def _row_to_dict(self, data: Any) -> Dict[str, Any]:
        """Convert sqlite rows or other mappings into plain dictionaries."""
        if data is None:
            return {}
        if isinstance(data, dict):
            return dict(data)
        if hasattr(data, "keys"):
            return {key: data[key] for key in data.keys()}
        return dict(data)

    def _normalize_tasks(self, tasks: Iterable[Any]) -> List[Dict[str, Any]]:
        """Normalize task records for prompt consumption, filtering out completed and overdue tasks."""
        normalized: List[Dict[str, Any]] = []
        today = datetime.now()
        
        for raw in tasks or []:
            task = self._row_to_dict(raw)
            task.setdefault('status', 'pending')
            
            # Skip completed tasks
            if task.get('status') == 'completed':
                continue
            
            task['deadline'] = self._parse_deadline(task.get('deadline'))
            
            # Skip tasks with past deadlines
            if task['deadline'] and task['deadline'].date() < today.date():
                continue
            
            normalized.append(task)
        
        return normalized

    def _parse_deadline(self, value: Any) -> Optional[datetime]:
        """Parse various deadline representations into datetime objects."""
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value)
            except (OSError, ValueError):
                return None

        value_str = str(value).strip()
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(value_str, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(value_str)
        except ValueError:
            return None

    def _format_deadline(self, value: Any) -> str:
        """Return human-readable deadline string."""
        parsed = self._parse_deadline(value)
        if parsed:
            return parsed.strftime('%Y-%m-%d %H:%M')
        return str(value) if value else 'No deadline'

    def _build_schedule_prompt(self, user_data, tasks, preferences, free_time_slots):
        """Build detailed prompt for Gemini"""
        
        # Sort tasks by deadline and importance
        pending_tasks = [t for t in tasks if t['status'] in ['pending', 'in_progress']]
        overdue_tasks = [t for t in tasks if t['status'] == 'overdue']
        
        prompt = f"""
You are an expert AI study planner. Generate a personalized, adaptive study schedule in JSON format with SPECIFIC TIME SLOTS.

TODAY'S DATE: {datetime.now().strftime("%A, %B %d, %Y")} ({datetime.now().strftime("%Y-%m-%d")})

USER PROFILE:
- Name: {user_data.get('name', 'Student')}
- Current Streak: {user_data.get('streak', 0)} days
- Score: {user_data.get('score', 0)} points
- Preferences: {preferences.get('study_style', 'balanced')}
- Gym Time: {preferences.get('gym_time', 'Not specified')}
- Gaming Time: {preferences.get('gaming_time', 'Not specified')}
- Weak Subjects: {', '.join(preferences.get('weak_subjects', [])) or 'None specified'}
- Sleep Schedule: {preferences.get('sleep_schedule', 'Not specified')}

TASKS TO SCHEDULE ({len(pending_tasks)} pending):
"""
        
        # Add overdue tasks (highest priority)
        if overdue_tasks:
            prompt += "\nOVERDUE (CRITICAL - Schedule ASAP):\n"
            for task in overdue_tasks[:5]:
                prompt += f"  - {task['title']} (Deadline: {self._format_deadline(task.get('deadline'))}, Priority: {task.get('importance', 'medium')})\n"
        
        # Add pending tasks
        if pending_tasks:
            prompt += "\nPENDING TASKS (Sort by deadline and priority):\n"
            for task in pending_tasks[:10]:
                deadline_str = self._format_deadline(task.get('deadline'))
                prompt += f"  - {task['title']} (Deadline: {deadline_str}, Priority: {task.get('importance', 'medium')})\n"
        
        # Add free time slots
        prompt += f"\nUSER'S AVAILABLE TIME & PREFERENCES:\n"
        for slot in free_time_slots[:7]:
            prompt += f"  - {slot['day']}: {slot['start_time']} to {slot['end_time']} ({slot['duration_hours']}h)\n"
        
        # Request format with detailed instructions
        prompt += """

SCHEDULING RULES (MUST FOLLOW):
1. **Priority System:**
   - Exams/Tests = Allocate 3-4 hour blocks, multiple sessions
   - Assignments (near deadline) = 2-3 hour blocks
   - Regular homework = 1-2 hour blocks
   - Practice/Review = 1 hour blocks

2. **Time Management:**
   - Create hour-by-hour schedule from 6 AM to 11 PM
   - Include ONLY study/task sessions (not gym, gaming, meals, sleep)
   - Respect user's gym time, gaming time - DO NOT schedule study during these times
   - Leave gaps for breaks, meals, personal time (don't fill every hour)
   - Typical day structure: Morning (6AM-12PM), Afternoon (12PM-6PM), Evening (6PM-11PM)

3. **Session Duration:**
   - Minimum study session: 1 hour
   - Maximum continuous study: 3 hours (then break)
   - High-priority tasks: Allocate multiple shorter sessions across days

4. **Task Assignment:**
   - Assign SPECIFIC time slots to each task (e.g., "09:00-11:00")
   - Tasks with closer deadlines get more frequent time slots
   - Spread tasks across the week, don't cram all on one day
   - For weak subjects, allocate extra time

5. **Schedule Next 7 Days Starting Today**

OUTPUT FORMAT (strict JSON):
{
  "day_plan": [
    {
      "day": "Wednesday",
      "date": "2025-11-13",
      "sessions": [
        {
          "time": "09:00-11:00",
          "task": "Physics Assignment",
          "task_id": null,
          "type": "assignment",
          "priority": "high",
          "estimated_hours": 2.0,
          "notes": "Focus on thermodynamics problems"
        },
        {
          "time": "14:00-15:30",
          "task": "Chemistry Lab Report",
          "task_id": null,
          "type": "assignment",
          "priority": "medium",
          "estimated_hours": 1.5,
          "notes": "Write experimental procedure"
        }
      ],
      "total_study_hours": 3.5
    }
  ],
  "priority_notes": "Physics assignment due tomorrow - complete by tonight. Chemistry report due Monday - spread across 3 days.",
  "motivation_message": "You're on a 5-day streak! Complete your physics assignment today to keep it going!",
  "scheduling_notes": "Gym time blocked 6-7 AM, Gaming time 8-10 PM. Study slots scheduled around these."
}

CRITICAL REQUIREMENTS:
- Every session MUST have: "time" (HH:MM-HH:MM format), "task", "type", "priority", "estimated_hours"
- Every day MUST have: "day", "date" (YYYY-MM-DD), "sessions", "total_study_hours"
- DO NOT schedule during gym/gaming/sleep times
- Allocate more hours to higher priority tasks
- Spread tasks realistically across days

Generate complete 7-day schedule starting from TODAY: """ + datetime.now().strftime("%Y-%m-%d") + """
"""
        return prompt
    
    def _parse_gemini_response(self, response_text):
        """Parse Gemini's JSON response"""
        try:
            # Extract JSON from markdown code blocks if present
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            
            schedule = json.loads(response_text)
            return schedule
        except json.JSONDecodeError as e:
            print(f"Failed to parse Gemini response: {e}")
            print(f"Response text: {response_text[:500]}")
            return self._get_fallback_schedule([])
    
    def _get_fallback_schedule(self, tasks):
        """Generate basic fallback schedule if AI fails"""
        today = datetime.now()
        
        return {
            "day_plan": [
                {
                    "day": (today + timedelta(days=i)).strftime("%A"),
                    "date": (today + timedelta(days=i)).strftime("%Y-%m-%d"),
                    "sessions": [
                        {
                            "time": "09:00-11:00",
                            "task": tasks[0]['title'] if tasks else "Study session",
                            "type": "study",
                            "priority": "high",
                            "estimated_hours": 2.0
                        },
                        {
                            "time": "14:00-16:00",
                            "task": "Review and practice",
                            "type": "study",
                            "priority": "medium",
                            "estimated_hours": 2.0
                        }
                    ],
                    "total_study_hours": 4.0
                } for i in range(7)
            ],
            "priority_notes": "Basic schedule generated. Update tasks for better planning.",
            "adjustments": "Adjust based on your actual progress.",
            "motivation_message": "Stay consistent and achieve your goals!"
        }
    
    def parse_lifestyle_message(self, message, user_data, current_tasks):
        """
        Use Gemini to parse informal lifestyle messages and extract:
        - Daily routine (gym, gaming, classes)
        - Study habits and preferences  
        - Exam dates and subjects
        - Weak/strong subjects
        - Tasks to create
        - Free time slots
        
        Args:
            message: str, informal user message
            user_data: dict, current user profile
            current_tasks: list, existing tasks
        
        Returns:
            dict with 'preferences', 'tasks', 'free_time_slots'
        """
        from datetime import datetime, timedelta
        today = datetime.now()
        
        prompt = f"""You are an intelligent study planner assistant. A student sent you this informal message about their lifestyle and study needs:

USER MESSAGE:
"{message}"

CURRENT USER PROFILE:
- Name: {user_data.get('name', 'Student')}
- Current tasks: {len(current_tasks)} tasks

TODAY'S DATE: {today.strftime('%A, %B %d, %Y')} (YYYY-MM-DD: {today.strftime('%Y-%m-%d')})
Day of week: {today.strftime('%A')}

YOUR TASK:
Carefully analyze the message and extract ALL relevant information. Be intelligent about understanding informal language, slang, and context.

IMPORTANT DATE RULES:
- "tomorrow" = {(today + timedelta(days=1)).strftime('%Y-%m-%d')}
- "next [day]" = next occurrence of that weekday (e.g., if today is Wednesday and they say "next Thursday", it's the Thursday coming up)
- "DD/MM/YYYY" format = convert to YYYY-MM-DD
- Extract BOTH date AND time for tasks (e.g., "Tomorrow 3 PM" should give deadline date AND time)
- For exams, extract the exact date mentioned

Extract and structure this information in JSON format:

{{
  "preferences": {{
    "gym_time": "time or routine mentioned for gym/workout",
    "gaming_time": "gaming schedule if mentioned",
    "weak_subjects": ["list of subjects student struggles with"],
    "strong_subjects": ["subjects they're good at"],
    "sleep_schedule": "wake up and sleep times",
    "study_style": "morning person/night owl/focused sessions/etc",
    "hobbies": ["hobbies mentioned"],
    "class_schedule": "college/school class timings",
    "daily_routine": "any routine patterns mentioned"
  }},
  "tasks": [
    {{
      "title": "task extracted from message",
      "deadline": "YYYY-MM-DD if mentioned or null",
      "deadline_time": "HH:MM in 24-hour format if mentioned (e.g., 15:00 for 3 PM) or null",
      "importance": "high/medium/low based on context",
      "description": "any additional context",
      "subject": "subject name if applicable"
    }}
  ],
  "free_time_slots": [
    {{
      "day": "Monday/Tuesday etc or 'weekdays' or 'weekends'",
      "start_time": "HH:MM",
      "end_time": "HH:MM",
      "duration_hours": hours_as_float
    }}
  ],
  "exams": [
    {{
      "subject": "exam subject",
      "date": "YYYY-MM-DD if mentioned",
      "priority": "how urgent based on date"
    }}
  ]
}}

EXTRACTION RULES:
1. DATES: Use TODAY'S DATE above to calculate relative dates accurately
   - "tomorrow" = calculate from today's date
   - "next Thursday" = find the next Thursday from today
   - "DD/MM/YYYY" format = convert to YYYY-MM-DD
2. TIMES: Convert to 24-hour format (3 PM = 15:00, 11 AM = 11:00)
3. Extract ALL subjects mentioned (both strong and weak)
4. Look for exam dates, test dates, assignment deadlines
5. Understand "teacher told me" = assignment/homework
6. "assignment for [subject] Tomorrow 3 PM" = create task with deadline and deadline_time
7. Priority: exams=high, assignments teacher mentioned=high, practice=medium
8. If they mention being weak in a subject, add it to weak_subjects array
9. Create separate entries in "tasks" for assignments and "exams" for exams/midterms
10. Be thorough - don't miss any homework, assignment, or exam mentioned

Be smart and contextual - understand the student's actual life, not just keywords.

OUTPUT ONLY VALID JSON, NO EXPLANATIONS:
"""
        
        try:
            print(f"\n📤 Sending lifestyle message to Gemini...")
            response = self.model.generate_content(prompt)
            
            # Parse JSON response
            response_text = response.text
            print(f"\n📥 Gemini Response (first 600 chars):")
            print(response_text[:600])
            print("="*60)
            
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            
            parsed = json.loads(response_text)
            print(f"✓ Extracted: {len(parsed.get('tasks', []))} tasks, {len(parsed.get('exams', []))} exams")
            print(f"  Weak subjects: {parsed.get('preferences', {}).get('weak_subjects', [])}")
            
            # Add timestamp for habit tracking
            if 'preferences' not in parsed:
                parsed['preferences'] = {}
            parsed['preferences']['last_updated'] = datetime.now().isoformat()
            parsed['preferences']['message_history'] = parsed['preferences'].get('message_history', [])
            parsed['preferences']['message_history'].append({
                'date': datetime.now().isoformat(),
                'message': message[:200]  # Store snippet for context
            })
            
            return parsed
            
        except Exception as e:
            print(f"❌ Error parsing lifestyle message: {e}")
            import traceback
            traceback.print_exc()
            
            # Fallback: Use regex to extract tasks when Gemini fails
            print("\n🔄 Using fallback parser to extract tasks...")
            return self._fallback_parse_message(message)
    
    def adjust_schedule_for_completion(self, current_schedule, completed_task, remaining_time):
        """
        Dynamically adjust schedule when user finishes early
        
        Args:
            current_schedule: dict, current day's schedule
            completed_task: dict, task that was completed
            remaining_time: float, hours remaining in current slot
        
        Returns:
            dict: adjusted schedule with suggestions
        """
        prompt = f"""
Current schedule was for task: {completed_task['title']}
User finished {remaining_time} hours early!

Suggest what to do with extra time:
1. Start next task early
2. Review completed work
3. Take earned break
4. Study something related

Return JSON:
{{
  "suggestion": "Start next task early",
  "next_activity": "Review advanced concepts",
  "reason": "You're ahead of schedule!",
  "bonus_points": 50
}}
"""
        
        try:
            response = self.model.generate_content(prompt)
            adjustment = json.loads(response.text.replace("```json", "").replace("```", "").strip())
            return adjustment
        except Exception as e:
            print(f"Error adjusting schedule: {e}")
            return {
                "suggestion": "Take a short break",
                "next_activity": "Relax for 15 minutes",
                "reason": "You finished early!",
                "bonus_points": 25
            }
    
    def generate_priority_reshuffle(self, tasks, user_progress):
        """
        Reshuffle task priorities based on user's recent progress
        
        Args:
            tasks: list of task dicts
            user_progress: dict with recent completion stats
        
        Returns:
            list: re-prioritized tasks
        """
        prompt = f"""
User's recent progress:
- Tasks completed on time: {user_progress.get('on_time', 0)}
- Tasks overdue: {user_progress.get('overdue', 0)}
- Average completion rate: {user_progress.get('completion_rate', 0)}%

Current tasks:
{json.dumps([{'title': t['title'], 'deadline': str(t['deadline']), 'importance': t['importance']} for t in tasks], indent=2)}

Re-prioritize these tasks considering:
1. Deadline urgency
2. User's completion pattern
3. Task dependencies

Return JSON array of tasks with updated priority (1=highest):
[
  {{"title": "Task X", "new_priority": 1, "reason": "Deadline approaching"}},
  ...
]
"""
        
        try:
            response = self.model.generate_content(prompt)
            prioritized = json.loads(response.text.replace("```json", "").replace("```", "").strip())
            return prioritized
        except Exception as e:
            print(f"Error reshuffling priorities: {e}")
            return []


if __name__ == "__main__":
    # Test AI Planner
    planner = AIPlanner()
    
    test_user = {
        "id": 1,
        "name": "Test Student",
        "streak": 5,
        "score": 250
    }
    
    test_tasks = [
        {
            "title": "Complete Python assignment",
            "deadline": datetime.now() + timedelta(days=2),
            "importance": "high",
            "status": "pending"
        },
        {
            "title": "Study for Math exam",
            "deadline": datetime.now() + timedelta(days=5),
            "importance": "urgent",
            "status": "pending"
        }
    ]
    
    test_preferences = {
        "interests": ["gaming", "gym"],
        "study_style": "intensive"
    }
    
    test_free_time = [
        {"day": "Monday", "start_time": "09:00", "end_time": "12:00", "duration_hours": 3},
        {"day": "Monday", "start_time": "14:00", "end_time": "18:00", "duration_hours": 4},
    ]
    
    print("\n🤖 Testing AI Schedule Generation...")
    schedule = planner.generate_schedule(test_user, test_tasks, test_preferences, test_free_time)
    print(json.dumps(schedule, indent=2))
    
    def _fallback_parse_message(self, message):
        """
        Fallback parser when Gemini API fails - uses regex to extract tasks
        """
        import re
        
        tasks = []
        message_lower = message.lower()
        
        # Common patterns to extract tasks
        # Pattern 1: "study for X exam on DATE"
        exam_pattern = r'(?:study for|prepare for|review for)\s+(?:my\s+)?([^,\.]+?)\s+(?:exam|test|midterm|final).*?(?:on|by)\s+([^,\.]+?)(?:[,\.]|$)'
        
        # Pattern 2: "finish/complete X by/due DATE"
        task_pattern = r'(?:finish|complete|work on|do|submit)\s+(?:a\s+|my\s+|the\s+)?([^,\.]+?)\s+(?:by|due|on|before)\s+([^,\.]+?)(?:[,\.]|$)'
        
        # Pattern 3: "X assignment/project due DATE"
        assignment_pattern = r'([^,\.]+?)\s+(?:assignment|project|homework|report)\s+(?:due|by|on)\s+([^,\.]+?)(?:[,\.]|$)'
        
        # Extract exam tasks
        for match in re.finditer(exam_pattern, message_lower, re.IGNORECASE):
            subject = match.group(1).strip().title()
            date_str = match.group(2).strip()
            deadline = self._parse_date_string(date_str)
            
            if deadline:
                importance = 'high' if 'high' in message_lower or 'important' in message_lower or 'urgent' in message_lower else 'high'
                tasks.append({
                    'title': f'{subject} exam preparation',
                    'deadline': deadline.strftime('%Y-%m-%d'),
                    'deadline_time': None,
                    'importance': importance,
                    'description': f'Study and prepare for {subject} exam',
                    'subject': subject
                })
                print(f"  📚 Extracted exam: {subject} on {deadline.strftime('%Y-%m-%d')}")
        
        # Extract general tasks
        for match in re.finditer(task_pattern, message_lower, re.IGNORECASE):
            task_name = match.group(1).strip().title()
            date_str = match.group(2).strip()
            deadline = self._parse_date_string(date_str)
            
            if deadline:
                importance = 'high' if 'high' in message_lower else 'medium' if 'medium' in message_lower else 'medium'
                tasks.append({
                    'title': task_name,
                    'deadline': deadline.strftime('%Y-%m-%d'),
                    'deadline_time': None,
                    'importance': importance,
                    'description': None,
                    'subject': None
                })
                print(f"  ✅ Extracted task: {task_name} by {deadline.strftime('%Y-%m-%d')}")
        
        # Extract assignment/project tasks
        for match in re.finditer(assignment_pattern, message_lower, re.IGNORECASE):
            task_name = match.group(1).strip().title()
            date_str = match.group(2).strip()
            deadline = self._parse_date_string(date_str)
            
            if deadline:
                importance = 'high' if 'high' in message_lower else 'medium' if 'medium' in message_lower else 'medium'
                tasks.append({
                    'title': f'{task_name} assignment',
                    'deadline': deadline.strftime('%Y-%m-%d'),
                    'deadline_time': None,
                    'importance': importance,
                    'description': None,
                    'subject': task_name
                })
                print(f"  📝 Extracted assignment: {task_name} due {deadline.strftime('%Y-%m-%d')}")
        
        print(f"\n✓ Fallback parser extracted {len(tasks)} tasks")
        
        return {
            "preferences": {
                "gym_time": None,
                "gaming_time": None,
                "weak_subjects": [],
                "strong_subjects": [],
                "sleep_schedule": None,
                "study_style": None,
                "hobbies": [],
                "class_schedule": None,
                "daily_routine": None
            },
            "tasks": tasks,
            "free_time_slots": [],
            "exams": []
        }
    
    def _parse_date_string(self, date_str):
        """Parse various date formats from natural language"""
        from dateutil import parser as date_parser
        
        try:
            # Replace common abbreviations
            date_str = date_str.replace('nov', 'november').replace('dec', 'december')
            date_str = date_str.replace('jan', 'january').replace('feb', 'february')
            date_str = date_str.replace('mar', 'march').replace('apr', 'april')
            date_str = date_str.replace('jun', 'june').replace('jul', 'july')
            date_str = date_str.replace('aug', 'august').replace('sep', 'september')
            date_str = date_str.replace('oct', 'october')
            
            # Use dateutil parser for flexible date parsing
            parsed_date = date_parser.parse(date_str, fuzzy=True)
            
            # If year is not specified and date is in the past, assume next year
            if parsed_date.year == datetime.now().year and parsed_date.date() < datetime.now().date():
                parsed_date = parsed_date.replace(year=parsed_date.year + 1)
            
            return parsed_date
        except:
            return None

