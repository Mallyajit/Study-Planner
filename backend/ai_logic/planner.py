"""
AI Planner Module - Gemini Integration for Adaptive Scheduling
Generates intelligent study plans based on user tasks, deadlines, and preferences.

FLOW: WhatsApp Bot -> Planner -> Gemini API -> JSON Schedule -> Database
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Iterable, List, Optional

from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

load_dotenv()


class AIPlanner:
    """Gemini-powered adaptive study planner."""

    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        parser_model_name = os.getenv("GEMINI_TIMETABLE_MODEL", "gemini-2.0-flash-lite")
        self.timetable_model = genai.GenerativeModel(parser_model_name)
        print(f"[AIPlanner] Gemini model ready (planner=gemini-2.0-flash, timetable={parser_model_name})")

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def _sanitize_large_text(self, text: str, max_chars: int = 6000) -> str:
        if not text:
            return ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        compact = "\n".join(lines)
        if len(compact) > max_chars:
            return compact[:max_chars]
        return compact

    def _generate_with_retry(
        self,
        prompt: str,
        *,
        model: Optional[Any] = None,
        max_attempts: int = 3,
        base_delay: float = 1.5,
    ):
        last_error: Optional[Exception] = None
        engine = model or self.model
        for attempt in range(1, max_attempts + 1):
            try:
                return engine.generate_content(prompt)
            except (google_exceptions.ResourceExhausted, google_exceptions.ServiceUnavailable) as exc:
                last_error = exc
                if attempt >= max_attempts:
                    break
                sleep_for = base_delay * attempt
                print(f"[AIPlanner] Model busy (attempt {attempt}/{max_attempts}) - retrying in {sleep_for:.1f}s")
                time.sleep(sleep_for)
            except Exception as exc:
                last_error = exc
                break
        if last_error:
            raise last_error

    def _build_timetable_prompt(self, message_text: str) -> str:
        return f"""Parse this timetable or academic notice and extract class schedules, exams, and announcements.\n\nMESSAGE:\n{message_text}\n\nReturn STRICT JSON with keys classes, exams, announcements as described below:\n- classes: list of {{"day_of_week", "subject", "start_time", "end_time", "location", "instructor"}}.\n- exams: list of {{"subject", "exam_date", "start_time", "duration_minutes", "location", "exam_type"}}.\n- announcements: list of {{"announcement_type", "subject", "content", "deadline"}}.\n\nUse 24h times and YYYY-MM-DD dates. If data missing return empty list for that section.\n"""

    # ------------------------------------------------------------------
    # Core schedule generation
    # ------------------------------------------------------------------
    def generate_schedule(
        self,
        user_data: Dict[str, Any],
        tasks: Iterable[Any],
        preferences: Dict[str, Any],
        free_time_slots: List[Dict[str, Any]],
        class_schedules: Optional[Iterable[Any]] = None,
        exams: Optional[Iterable[Any]] = None,
        announcements: Optional[Iterable[Any]] = None,
    ) -> Dict[str, Any]:
        normalized_user = self._row_to_dict(user_data)
        normalized_tasks = self._normalize_tasks(tasks)
        normalized_classes = self._normalize_collection(class_schedules)
        normalized_exams = self._normalize_collection(exams)
        normalized_announcements = self._normalize_collection(announcements)

        prompt = self._build_schedule_prompt(
            normalized_user,
            normalized_tasks,
            preferences,
            free_time_slots,
            normalized_classes,
            normalized_exams,
            normalized_announcements,
        )

        try:
            response = self._generate_with_retry(prompt)
            schedule = self._parse_gemini_response(response.text)
            schedule = self._ensure_task_list_structure(
                schedule,
                normalized_tasks,
                normalized_classes,
                normalized_exams,
                normalized_announcements,
            )
            schedule["generated_at"] = datetime.now().isoformat()
            schedule["user_id"] = normalized_user.get("id")
            return schedule
        except Exception as exc:  # pragma: no cover - Gemini failure fallback
            print(f"[AIPlanner] Schedule generation failed: {exc}")
            return self._get_fallback_schedule(
                normalized_tasks,
                normalized_classes,
                normalized_exams,
                normalized_announcements,
            )

    def _row_to_dict(self, data: Any) -> Dict[str, Any]:
        if data is None:
            return {}
        if isinstance(data, dict):
            return dict(data)
        if hasattr(data, "keys"):
            return {key: data[key] for key in data.keys()}
        return dict(data)

    def _normalize_collection(self, records: Optional[Iterable[Any]]) -> List[Dict[str, Any]]:
        if not records:
            return []
        return [self._row_to_dict(item) for item in records]

    def _normalize_tasks(self, tasks: Iterable[Any]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        today = datetime.now().date()

        for raw in tasks or []:
            task = self._row_to_dict(raw)
            status = task.setdefault("status", "pending")
            if status == "completed":
                continue

            deadline = self._parse_deadline(task.get("deadline"))
            task["deadline"] = deadline
            if deadline and deadline.date() < today:
                continue

            normalized.append(task)

        return normalized

    def _parse_deadline(self, value: Any) -> Optional[datetime]:
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
        parsed = self._parse_deadline(value)
        if parsed:
            return parsed.strftime("%Y-%m-%d %H:%M")
        return str(value) if value else "No deadline"

    def _build_schedule_prompt(
        self,
        user_data: Dict[str, Any],
        tasks: List[Dict[str, Any]],
        preferences: Dict[str, Any],
        free_time_slots: List[Dict[str, Any]],
        class_schedules: List[Dict[str, Any]],
        exams: List[Dict[str, Any]],
        announcements: List[Dict[str, Any]],
    ) -> str:
        pending_tasks = [t for t in tasks if t.get("status") in {"pending", "in_progress"}]
        overdue_tasks = [t for t in tasks if t.get("status") == "overdue"]

        prompt = f"""
You are an expert AI study planner. Generate a prioritized TASK LIST (not a timetable) that the student can execute. 
Each task entry must include the concrete due date and time (or class day/time) so the student knows exactly when something happens.

TODAY'S DATE: {datetime.now().strftime('%A, %B %d, %Y')} ({datetime.now().strftime('%Y-%m-%d')})

USER PROFILE:
- Name: {user_data.get('name', 'Student')}
- Current Streak: {user_data.get('streak', 0)} days
- Score: {user_data.get('score', 0)} points
- Preferences: {preferences.get('study_style', 'balanced')}
- Gym Time: {preferences.get('gym_time', 'Not specified')}
- Gaming Time: {preferences.get('gaming_time', 'Not specified')}
- Weak Subjects: {', '.join(preferences.get('weak_subjects', [])) or 'None specified'}
- Sleep Schedule: {preferences.get('sleep_schedule', 'Not specified')}

TASKS TO PRIORITIZE ({len(pending_tasks)} pending):
"""
        if overdue_tasks:
            prompt += "\nOVERDUE (CRITICAL - Schedule ASAP):\n"
            for task in overdue_tasks[:5]:
                prompt += (
                    f"  - {task['title']} (Deadline: {self._format_deadline(task.get('deadline'))}, "
                    f"Priority: {task.get('importance', 'medium')})\n"
                )

        if pending_tasks:
            prompt += "\nPENDING TASKS (Sort by deadline and priority):\n"
            for task in pending_tasks[:10]:
                prompt += (
                    f"  - {task['title']} (Deadline: {self._format_deadline(task.get('deadline'))}, "
                    f"Priority: {task.get('importance', 'medium')})\n"
                )

        prompt += "\nUSER'S AVAILABLE TIME & PREFERENCES:\n"
        for slot in free_time_slots[:7]:
            prompt += (
                f"  - {slot['day']}: {slot['start_time']} to {slot['end_time']} "
                f"({slot['duration_hours']}h)\n"
            )

        prompt += "\nWEEKLY CLASS SCHEDULE (keep class days accurate):\n"
        if class_schedules:
            for cls in class_schedules[:10]:
                prompt += (
                    f"  - {cls['day_of_week']}: {cls['subject']} {cls['start_time']} - {cls['end_time']}"
                    f" at {cls.get('location', 'TBD')}\n"
                )
        else:
            prompt += "  - No classes stored yet\n"

        prompt += "\nUPCOMING EXAMS (plan prep windows + exact start times):\n"
        if exams:
            for exam in exams[:8]:
                prompt += (
                    f"  - {exam['subject']} on {exam['exam_date']} at {exam.get('start_time', 'TBD')}"
                    f" ({exam.get('exam_type', 'exam')})\n"
                )
        else:
            prompt += "  - No exams recorded\n"

        prompt += "\nANNOUNCEMENTS & PROJECTS (respect teacher instructions):\n"
        if announcements:
            for ann in announcements[:8]:
                prompt += (
                    f"  - {ann['announcement_type'].upper()}: {ann['content']} (deadline {ann.get('deadline', 'N/A')})\n"
                )
        else:
            prompt += "  - No announcements\n"

        prompt += """

TASK LIST RULES:
1. Sort tasks primarily by importance (critical/high/medium/low) and secondarily by nearest due date/time.
2. Every entry must show the exact submission or class window ("14:00 portal submit", "Monday 09:00-10:00 class").
3. Include ALL relevant work: assignments, exams, announcements, class prep, daily focus.
4. Combine related reminders (e.g., "Finish Physics Lab before 14:00 lab session"). Mention submission channel if known.
5. Highlight if any weekdays (Mon-Fri) have no classes captured so we can fill gaps later.

OUTPUT STRICT JSON:
{
  "task_list": [
    {
      "title": "Physics Lab Report",
      "category": "assignment|exam|class|announcement|practice",
      "importance": "critical|high|medium|low",
      "due_date": "YYYY-MM-DD or null",
      "due_time": "HH:MM or null",
      "class_day": "Monday/Tuesday/etc or null",
      "class_time": "HH:MM-HH:MM or null",
      "notes": "submission instructions or class context"
    }
  ],
  "priority_notes": "...",
  "scheduling_notes": "...",
  "motivation_message": "...",
  "summary": "...",
  "missing_class_days": ["list weekdays without classes"]
}

"""
        prompt += (
            "\nGenerate the prioritized task list covering the next 7 days starting today: "
            f"{datetime.now().strftime('%Y-%m-%d')}\n"
        )
        return prompt

    def _parse_gemini_response(self, response_text: str) -> Dict[str, Any]:
        text = response_text.strip()
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            text = text[start:end].strip()
        elif text.startswith("```"):
            text = text.strip('`')
        return json.loads(text)

    # ------------------------------------------------------------------
    # Task-list normalizers
    # ------------------------------------------------------------------
    def _ensure_task_list_structure(
        self,
        schedule: Optional[Dict[str, Any]],
        tasks: List[Dict[str, Any]],
        class_schedules: List[Dict[str, Any]],
        exams: List[Dict[str, Any]],
        announcements: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload = schedule or {}

        raw_entries = payload.get("task_list")
        normalized_entries: List[Dict[str, Any]] = []
        if isinstance(raw_entries, list):
            normalized_entries = [self._normalize_task_entry(entry) for entry in raw_entries]

        if not normalized_entries:
            normalized_entries = self._build_task_list_entries(
                tasks, class_schedules, exams, announcements
            )

        payload["task_list"] = self._sort_task_entries(normalized_entries)
        payload.setdefault(
            "priority_notes",
            "Tackle critical exams and near-term submissions before lower-priority work.",
        )
        payload.setdefault(
            "scheduling_notes",
            "Use free blocks to finish the next due task, then prep for upcoming classes.",
        )
        payload.setdefault(
            "motivation_message",
            "You're building momentum—show up for each session and the results will follow!",
        )
        payload.setdefault(
            "summary",
            f"{len(payload['task_list'])} actionable study steps for the next 7 days.",
        )
        payload["missing_class_days"] = self._calculate_missing_class_days(class_schedules)
        return payload

    def _build_task_list_entries(
        self,
        tasks: List[Dict[str, Any]],
        class_schedules: List[Dict[str, Any]],
        exams: List[Dict[str, Any]],
        announcements: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []

        for task in tasks or []:
            deadline = self._parse_deadline(task.get("deadline"))
            due_date = deadline.strftime("%Y-%m-%d") if deadline else None
            due_time: Optional[str] = None
            if deadline and deadline.time() != time.min:
                due_time = deadline.strftime("%H:%M")
            elif task.get("deadline_time"):
                due_time = str(task.get("deadline_time"))

            entry = {
                "title": task.get("title") or "Task",
                "category": task.get("category") or ("assignment" if due_date else "practice"),
                "importance": task.get("importance") or "medium",
                "due_date": due_date,
                "due_time": due_time,
                "class_day": None,
                "class_time": None,
                "notes": task.get("description") or task.get("subject") or "General study",
            }
            entries.append(self._normalize_task_entry(entry))

        for cls in class_schedules or []:
            class_entry = {
                "title": f"{cls.get('subject', 'Class')} session",
                "category": "class",
                "importance": "medium",
                "due_date": None,
                "due_time": None,
                "class_day": cls.get("day_of_week"),
                "class_time": self._format_time_window(
                    cls.get("start_time"), cls.get("end_time")
                ),
                "notes": cls.get("location") or "Class meeting",
            }
            entries.append(self._normalize_task_entry(class_entry))

        for exam in exams or []:
            exam_entry = {
                "title": f"{exam.get('subject', 'Exam')} preparation",
                "category": "exam",
                "importance": "critical",
                "due_date": exam.get("exam_date"),
                "due_time": exam.get("start_time"),
                "class_day": None,
                "class_time": None,
                "notes": exam.get("exam_type") or exam.get("location") or "Exam window",
            }
            entries.append(self._normalize_task_entry(exam_entry))

        for ann in announcements or []:
            ann_entry = {
                "title": ann.get("subject") or ann.get("announcement_type", "Announcement"),
                "category": "announcement",
                "importance": "high",
                "due_date": ann.get("deadline"),
                "due_time": ann.get("deadline_time"),
                "class_day": None,
                "class_time": None,
                "notes": ann.get("content") or "Teacher announcement",
            }
            entries.append(self._normalize_task_entry(ann_entry))

        if not entries:
            entries.append(
                self._normalize_task_entry(
                    {
                        "title": "General revision",
                        "category": "practice",
                        "importance": "medium",
                        "due_date": datetime.now().strftime("%Y-%m-%d"),
                        "due_time": "18:00",
                        "class_day": None,
                        "class_time": None,
                        "notes": "Fallback task while no data provided.",
                    }
                )
            )

        return entries

    def _normalize_task_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        normalized = {
            "title": str(entry.get("title") or "Task").strip(),
            "category": str(entry.get("category") or "assignment").lower(),
            "importance": str(entry.get("importance") or "medium").lower(),
            "due_date": self._format_date_value(entry.get("due_date")),
            "due_time": self._format_time_value(entry.get("due_time")),
            "class_day": self._format_weekday(entry.get("class_day")),
            "class_time": self._format_time_range_value(entry.get("class_time")),
            "notes": (entry.get("notes") or "").strip(),
        }
        return normalized

    def _format_date_value(self, value: Any) -> Optional[str]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")
        if isinstance(value, date):
            return value.strftime("%Y-%m-%d")
        parsed = self._parse_deadline(value)
        if parsed:
            return parsed.strftime("%Y-%m-%d")
        text = str(value).strip()
        if not text:
            return None
        try:
            return datetime.strptime(text, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            return text

    def _format_time_value(self, value: Any) -> Optional[str]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value.strftime("%H:%M")
        if isinstance(value, time):
            return value.strftime("%H:%M")
        text = str(value).strip()
        if not text:
            return None
        if "-" in text and len(text) > 5:
            text = text.split("-")[0].strip()
        try:
            return datetime.strptime(text, "%H:%M").strftime("%H:%M")
        except ValueError:
            return text

    def _format_time_range_value(self, value: Any) -> Optional[str]:
        if not value:
            return None
        if isinstance(value, str):
            text = value.strip()
        else:
            text = str(value)
        return text or None

    def _format_weekday(self, value: Any) -> Optional[str]:
        if not value:
            return None
        text = str(value).strip()
        if not text:
            return None
        return text.capitalize()

    def _format_time_window(self, start: Any, end: Any) -> Optional[str]:
        start_fmt = self._format_time_value(start)
        end_fmt = self._format_time_value(end)
        if start_fmt and end_fmt:
            return f"{start_fmt}-{end_fmt}"
        return start_fmt or end_fmt

    def _importance_rank(self, importance: Optional[str]) -> int:
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return order.get((importance or "medium").lower(), 2)

    def _sort_task_entries(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        def sort_key(item: Dict[str, Any]) -> tuple[Any, Any, Any]:
            return (
                self._importance_rank(item.get("importance")),
                item.get("due_date") or item.get("class_day") or "",
                item.get("due_time") or item.get("class_time") or "",
            )

        return sorted(entries, key=sort_key)

    def _calculate_missing_class_days(
        self, class_schedules: List[Dict[str, Any]]
    ) -> List[str]:
        expected = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        recorded = {
            (cls.get("day_of_week") or "").strip().capitalize()
            for cls in class_schedules or []
            if cls.get("day_of_week")
        }
        return [day for day in expected if day not in recorded]

    def _get_fallback_schedule(
        self,
        tasks: List[Dict[str, Any]],
        class_schedules: List[Dict[str, Any]],
        exams: List[Dict[str, Any]],
        announcements: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        today = datetime.now()
        fallback_entries = self._build_task_list_entries(
            tasks, class_schedules, exams, announcements
        )

        schedule = {
            "task_list": fallback_entries,
            "priority_notes": "Fallback plan created from stored tasks and deadlines.",
            "scheduling_notes": "Distribute these entries across your available study blocks.",
            "motivation_message": "Stay consistent and keep moving forward!",
            "summary": f"Fallback generated on {today.strftime('%Y-%m-%d')}.",
        }

        return self._ensure_task_list_structure(
            schedule, tasks, class_schedules, exams, announcements
        )

    # ------------------------------------------------------------------
    # Lifestyle parsing
    # ------------------------------------------------------------------
    def parse_lifestyle_message(
        self,
        message: str,
        user_data: Dict[str, Any],
        current_tasks: Iterable[Any],
    ) -> Dict[str, Any]:
        today = datetime.now()
        prompt = f"""You are a precise study planner. Analyze the student's informal message and extract all relevant structure.

USER MESSAGE:
\"{message}\"

CURRENT USER PROFILE:
- Name: {user_data.get('name', 'Student')}
- Current tasks: {len(list(current_tasks) if current_tasks else [])}

TODAY'S DATE: {today.strftime('%A, %B %d, %Y')} (YYYY-MM-DD: {today.strftime('%Y-%m-%d')})

Return STRICT JSON with:
{{
  "preferences": {{
    "gym_time": "text",
    "gaming_time": "text",
    "weak_subjects": ["..."],
    "strong_subjects": ["..."],
    "sleep_schedule": "text",
    "study_style": "text",
    "hobbies": ["..."],
    "class_schedule": "text",
    "daily_routine": "text"
  }},
  "tasks": [
    {{
      "title": "task",
      "deadline": "YYYY-MM-DD or null",
      "deadline_time": "HH:MM or null",
      "importance": "high|medium|low",
      "description": "context",
      "subject": "subject or null"
    }}
  ],
  "free_time_slots": [
    {{"day": "Monday", "start_time": "HH:MM", "end_time": "HH:MM", "duration_hours": 2.0}}
  ],
  "exams": [
    {{"subject": "...", "date": "YYYY-MM-DD", "priority": "high"}}
  ],
  "announcements": [
    {{
      "announcement_type": "project|assessment|exam_notice|presentation",
      "subject": "subject or null",
      "content": "original sentence",
      "deadline": "YYYY-MM-DD or null",
      "deadline_time": "HH:MM or null"
    }}
  ]
}}

DATE RULES:
- "tomorrow" = {(today + timedelta(days=1)).strftime('%Y-%m-%d')}.
- "next <weekday>" = next occurrence of that weekday.
- Accept DD/MM/YYYY and convert to YYYY-MM-DD.
- Capture explicit times in HH:MM 24h format.
- Exams and teacher instructions default to high importance.
- Use announcements for class tests, assessments, presentations or exam notices even if they also map to tasks.

Output valid JSON only.
"""

        try:
            response = self.model.generate_content(prompt)
            payload = self._parse_gemini_response(response.text)
            payload.setdefault("announcements", [])
            prefs = payload.setdefault("preferences", {})
            prefs["last_updated"] = datetime.now().isoformat()
            message_history = prefs.setdefault("message_history", [])
            message_history.append(
                {"date": datetime.now().isoformat(), "message": message[:200]}
            )
            return payload
        except Exception as exc:
            print(f"[AIPlanner] Lifestyle parsing failed: {exc}")
            fallback = self._fallback_parse_message(message)
            fallback.setdefault("announcements", [])
            return fallback

    # ------------------------------------------------------------------
    # Adaptive helpers
    # ------------------------------------------------------------------
    def adjust_schedule_for_completion(
        self,
        current_schedule: Dict[str, Any],
        completed_task: Dict[str, Any],
        remaining_time: float,
    ) -> Dict[str, Any]:
        prompt = f"""
A task finished {remaining_time} hours early.
Original task: {completed_task.get('title')}
Provide JSON suggestion with keys suggestion, next_activity, reason, bonus_points.
"""
        try:
            response = self.model.generate_content(prompt)
            return self._parse_gemini_response(response.text)
        except Exception:
            return {
                "suggestion": "Take a short break",
                "next_activity": "Stretch or hydrate",
                "reason": "Recover before the next block",
                "bonus_points": 15,
            }

    def generate_priority_reshuffle(
        self, tasks: List[Dict[str, Any]], user_progress: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        prompt = f"""
User progress:
- On-time tasks: {user_progress.get('on_time', 0)}
- Overdue tasks: {user_progress.get('overdue', 0)}
- Completion rate: {user_progress.get('completion_rate', 0)}%

Current tasks:
{json.dumps([{ 'title': t['title'], 'deadline': str(t.get('deadline')), 'importance': t.get('importance') } for t in tasks], indent=2)}

Return JSON list with objects: {{"title": "Task", "new_priority": 1, "reason": "..."}}
"""
        try:
            response = self.model.generate_content(prompt)
            return self._parse_gemini_response(response.text)
        except Exception as exc:
            print(f"[AIPlanner] Priority reshuffle failed: {exc}")
            return []

    # ------------------------------------------------------------------
    # Fallback NLP helpers
    # ------------------------------------------------------------------
    def _fallback_parse_message(self, message: str) -> Dict[str, Any]:
        import re

        lowered = (message or "").lower()
        tasks: List[Dict[str, Any]] = []

        exam_pattern = (
            r"([A-Za-z\s]+?)\s+(?:exam|test)\s+(?:on|by|due)\s+([^,.]+)"
        )
        for match in re.finditer(exam_pattern, lowered, re.IGNORECASE):
            subject = match.group(1).strip().title()
            deadline = self._parse_date_string(match.group(2).strip())
            if not deadline:
                continue
            tasks.append(
                {
                    "title": f"{subject} exam preparation",
                    "deadline": deadline.strftime("%Y-%m-%d"),
                    "deadline_time": None,
                    "importance": "high",
                    "description": f"Study and prepare for {subject} exam",
                    "subject": subject,
                }
            )

        task_pattern = (
            r"(?:finish|complete|work on|submit|do)\s+(?:a\s+|my\s+|the\s+)?([^,.]+?)\s+"
            r"(?:by|due|on|before)\s+([^,.]+?)(?:[,.]|$)"
        )
        for match in re.finditer(task_pattern, lowered, re.IGNORECASE):
            title = match.group(1).strip().title()
            deadline = self._parse_date_string(match.group(2).strip())
            if not deadline:
                continue
            tasks.append(
                {
                    "title": title,
                    "deadline": deadline.strftime("%Y-%m-%d"),
                    "deadline_time": None,
                    "importance": "medium",
                    "description": None,
                    "subject": None,
                }
            )

        assignment_pattern = (
            r"([^,.]+?)\s+(?:assignment|project|homework|report)\s+(?:due|by|on)\s+([^,.]+?)(?:[,.]|$)"
        )
        for match in re.finditer(assignment_pattern, lowered, re.IGNORECASE):
            subject = match.group(1).strip().title()
            deadline = self._parse_date_string(match.group(2).strip())
            if not deadline:
                continue
            tasks.append(
                {
                    "title": f"{subject} assignment",
                    "deadline": deadline.strftime("%Y-%m-%d"),
                    "deadline_time": None,
                    "importance": "medium",
                    "description": None,
                    "subject": subject,
                }
            )

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
                "daily_routine": None,
            },
            "tasks": tasks,
            "free_time_slots": [],
            "exams": [],
            "announcements": [],
        }

    def _parse_date_string(self, date_str: str) -> Optional[datetime]:
        try:
            from dateutil import parser as date_parser
        except ImportError:
            return None

        try:
            cleaned = date_str.lower()
            replacements = {
                "jan": "january",
                "feb": "february",
                "mar": "march",
                "apr": "april",
                "jun": "june",
                "jul": "july",
                "aug": "august",
                "sep": "september",
                "oct": "october",
                "nov": "november",
                "dec": "december",
            }
            for short, long in replacements.items():
                cleaned = cleaned.replace(short, long)
            parsed_date = date_parser.parse(cleaned, fuzzy=True)
            if (
                parsed_date.year == datetime.now().year
                and parsed_date.date() < datetime.now().date()
            ):
                parsed_date = parsed_date.replace(year=parsed_date.year + 1)
            return parsed_date
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Timetable parsing
    # ------------------------------------------------------------------
    def parse_timetable(self, message_text: str) -> Dict[str, Any]:
        sanitized_input = self._sanitize_large_text(message_text)
        prompt = self._build_timetable_prompt(sanitized_input)

        try:
            response = self._generate_with_retry(
                prompt,
                model=self.timetable_model,
                max_attempts=4,
                base_delay=1.0,
            )
            result = self._parse_gemini_response(response.text)
            result.setdefault("classes", [])
            result.setdefault("exams", [])
            result.setdefault("announcements", [])
            return result
        except Exception as exc:
            print(f"[AIPlanner] Timetable parse failed: {exc}")
            return self._parse_timetable_fallback(message_text)

    def _parse_timetable_fallback(self, message_text: str) -> Dict[str, Any]:
        result = {"classes": [], "exams": [], "announcements": []}
        text = self._sanitize_large_text(message_text, max_chars=8000)

        class_pattern = (
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+"
            r"(\d{1,2}):?(\d{2})?\s*-\s*(\d{1,2}):?(\d{2})?\s+([a-zA-Z\s]+?)"
            r"(?:room|hall|lab)?\s*(\d+)?"
        )
        for match in re.finditer(class_pattern, text, re.IGNORECASE):
            day, sh, sm, eh, em, subject, room = match.groups()
            result["classes"].append(
                {
                    "day_of_week": day.capitalize(),
                    "subject": subject.strip(),
                    "start_time": f"{int(sh):02d}:{sm or '00'}",
                    "end_time": f"{int(eh):02d}:{em or '00'}",
                    "location": f"Room {room}" if room else None,
                    "instructor": None,
                }
            )

        exam_pattern = r"([A-Za-z\s]+?)\s+exam\s+([A-Za-z]+\s+\d{1,2})\s+(\d{1,2})\s*(am|pm)?"
        for match in re.finditer(exam_pattern, text, re.IGNORECASE):
            subject, date_str, time_part, ampm = match.groups()
            parsed_date = self._parse_date_string(date_str)
            if not parsed_date:
                continue
            hour = int(time_part)
            if ampm and ampm.lower() == "pm" and hour < 12:
                hour += 12
            result["exams"].append(
                {
                    "subject": subject.strip(),
                    "exam_date": parsed_date.strftime("%Y-%m-%d"),
                    "start_time": f"{hour:02d}:00",
                    "duration_minutes": 120,
                    "location": None,
                    "exam_type": "exam",
                }
            )

        announcement_pattern = (
            r"(project|presentation|assignment|submission|assessment)\s+([A-Za-z\s]*?)\s+"
            r"(?:due|deadline|on)?\s*([A-Za-z]+\s+\d{1,2})"
        )
        for match in re.finditer(announcement_pattern, text, re.IGNORECASE):
            kind, subject, date_str = match.groups()
            parsed_date = self._parse_date_string(date_str)
            if not parsed_date:
                continue
            result["announcements"].append(
                {
                    "announcement_type": kind.lower(),
                    "subject": subject.strip() or None,
                    "content": match.group(0).strip(),
                    "deadline": parsed_date.strftime("%Y-%m-%d"),
                }
            )

        return result

    # ------------------------------------------------------------------
    # Daily todo generation
    # ------------------------------------------------------------------
    def generate_daily_todo_list(
        self,
        user_id: int,
        db: Any,
        target_date: Optional[str | date] = None,
    ) -> Dict[str, Any]:
        if target_date is None:
            day = datetime.now().date()
        elif isinstance(target_date, str):
            day = datetime.strptime(target_date, "%Y-%m-%d").date()
        else:
            day = target_date

        day_name = day.strftime("%A")
        classes_today = db.get_class_schedules(user_id, day_name)
        exams_soon = db.get_exam_schedules(
            user_id,
            start_date=day.strftime("%Y-%m-%d"),
            end_date=(day + timedelta(days=7)).strftime("%Y-%m-%d"),
        )
        tasks = db.get_user_tasks(user_id)
        pending_with_deadlines = [
            t
            for t in tasks
            if t.get("status") == "pending" and t.get("deadline")
        ]
        upcoming_tasks = []
        for task in pending_with_deadlines:
            deadline = self._parse_deadline(task.get("deadline"))
            if deadline and day <= deadline.date() <= day + timedelta(days=7):
                upcoming_tasks.append(task)

        announcements = db.get_announcements(
            user_id,
            start_date=day.strftime("%Y-%m-%d"),
            end_date=(day + timedelta(days=7)).strftime("%Y-%m-%d"),
        )
        free_blocks = self._calculate_free_time_blocks(day, classes_today)

        prompt = f"""Generate a focused todo plan for {day_name}, {day.strftime('%B %d, %Y')}.
Use the context below and return JSON with keys date, day_name, todos, classes_today, exams_soon, deadlines_today, free_time_blocks.

CLASSES TODAY:
"""
        if classes_today:
            for cls in classes_today:
                prompt += (
                    f"  - {cls['subject']} from {cls['start_time']} to {cls['end_time']}"
                    f" at {cls.get('location', 'TBD')}\n"
                )
        else:
            prompt += "  - None\n"

        prompt += "\nUPCOMING EXAMS (next 7 days):\n"
        if exams_soon:
            for exam in exams_soon:
                prompt += (
                    f"  - {exam['subject']} on {exam['exam_date']} "
                    f"at {exam.get('start_time', 'TBD')}\n"
                )
        else:
            prompt += "  - None\n"

        prompt += "\nPENDING DEADLINES (next 7 days):\n"
        if upcoming_tasks:
            for task in upcoming_tasks[:10]:
                deadline = self._parse_deadline(task.get("deadline"))
                deadline_str = deadline.strftime("%Y-%m-%d") if deadline else "N/A"
                prompt += (
                    f"  - {task['title']} due {deadline_str}"
                    f" (priority {task.get('importance', 'medium')})\n"
                )
        else:
            prompt += "  - None\n"

        prompt += "\nANNOUNCEMENTS/ASSESSMENTS:\n"
        if announcements:
            for ann in announcements:
                prompt += (
                    f"  - {ann['announcement_type'].upper()}: {ann['content']}"
                    f" (deadline {ann.get('deadline', 'N/A')})\n"
                )
        else:
            prompt += "  - None\n"

        prompt += "\nFREE TIME BLOCKS:\n"
        if free_blocks:
            for block in free_blocks:
                prompt += (
                    f"  - {block['start_time']} to {block['end_time']}"
                    f" ({block['duration_hours']}h, {block['period']})\n"
                )
        else:
            prompt += "  - No sizeable gaps today\n"

        prompt += """
OUTPUT STRICT JSON:
{
  "date": "YYYY-MM-DD",
  "day_name": "Monday",
  "todos": [
    {"time": "HH:MM-HH:MM", "task": "Study", "priority": "high", "reason": "Exam soon", "estimated_hours": 2.0}
  ],
  "classes_today": [...],
  "exams_soon": [...],
  "deadlines_today": [...],
  "free_time_blocks": [...]
}
"""

        try:
            response = self._generate_with_retry(prompt)
            plan = self._parse_gemini_response(response.text)
            plan.setdefault("date", day.strftime("%Y-%m-%d"))
            plan.setdefault("day_name", day_name)
            return plan
        except Exception as exc:
            print(f"[AIPlanner] Daily todo generation failed: {exc}")
            return {
                "date": day.strftime("%Y-%m-%d"),
                "day_name": day_name,
                "todos": [
                    {
                        "time": "09:00-10:00",
                        "task": "Review key concepts",
                        "priority": "medium",
                        "reason": "Fallback plan",
                        "estimated_hours": 1.0,
                    }
                ],
                "classes_today": classes_today,
                "exams_soon": exams_soon,
                "deadlines_today": upcoming_tasks,
                "free_time_blocks": free_blocks,
            }

    def _calculate_free_time_blocks(
        self,
        day: date,
        classes_today: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        def to_time(value: str) -> Optional[time]:
            try:
                return datetime.strptime(value, "%H:%M").time()
            except (TypeError, ValueError):
                return None

        ranges: List[tuple[datetime, datetime]] = []
        for cls in classes_today or []:
            start = to_time(cls.get("start_time"))
            end = to_time(cls.get("end_time"))
            if not start or not end:
                continue
            start_dt = datetime.combine(day, start)
            end_dt = datetime.combine(day, end)
            if end_dt <= start_dt:
                continue
            ranges.append((start_dt, end_dt))

        ranges.sort(key=lambda item: item[0])
        free_blocks: List[Dict[str, Any]] = []

        day_start = datetime.combine(day, time(hour=6))
        day_end = datetime.combine(day, time(hour=23))
        cursor = day_start

        for start_dt, end_dt in ranges:
            if start_dt > cursor:
                duration = (start_dt - cursor).total_seconds() / 3600
                if duration >= 0.5:
                    free_blocks.append(
                        {
                            "start_time": cursor.strftime("%H:%M"),
                            "end_time": start_dt.strftime("%H:%M"),
                            "duration_hours": round(duration, 1),
                            "period": self._period_for_time(cursor.time()),
                        }
                    )
            cursor = max(cursor, end_dt)

        if cursor < day_end:
            duration = (day_end - cursor).total_seconds() / 3600
            if duration >= 0.5:
                free_blocks.append(
                    {
                        "start_time": cursor.strftime("%H:%M"),
                        "end_time": day_end.strftime("%H:%M"),
                        "duration_hours": round(duration, 1),
                        "period": self._period_for_time(cursor.time()),
                    }
                )

        return free_blocks

    def _period_for_time(self, tm: time) -> str:
        if tm < time(12):
            return "morning"
        if tm < time(18):
            return "afternoon"
        return "evening"


