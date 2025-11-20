import sys
sys.path.append('backend')

from db_sqlite import Database

db = Database()

# Get recent tasks
tasks = db.get_user_tasks(1)
print('=== RECENT TASKS (Last 5) ===')
for t in tasks[-5:]:
    print(f"- {t['title']}")
    print(f"  Deadline: {t['deadline']}, Importance: {t['importance']}")

# Get exam schedules
exams = db.get_exam_schedules(1)
print('\n=== RECENT EXAMS (Last 3) ===')
for e in exams[-3:]:
    print(f"- {e['subject']} Exam")
    print(f"  Date: {e['exam_date']}, Time: {e['start_time']}")
