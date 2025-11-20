from backend.db_sqlite import Database

# Check BOTH database locations
print('\n==================== ROOT DATABASE ====================')
db_root = Database('studyplanner.db')

print('\n=== ALL TASKS FOR USER 1 (ROOT) ===')
tasks = db_root.get_user_tasks(1)
for t in tasks:
    print(f'ID: {t["id"]}, Title: {t["title"]}, Deadline: {t["deadline"]}, Status: {t["status"]}')
print(f'\nTotal: {len(tasks)} tasks')

print('\n=== ALL EXAMS FOR USER 1 (ROOT) ===')
exams = db_root.get_exam_schedules(1)
for e in exams:
    print(f'ID: {e["id"]}, Subject: {e["subject"]}, Date: {e["exam_date"]}, Time: {e["start_time"]}')
print(f'\nTotal: {len(exams)} exams')

print('\n\n==================== BACKEND DATABASE ====================')
db_backend = Database('backend/studyplanner.db')

print('\n=== ALL TASKS FOR USER 1 (BACKEND) ===')
tasks = db_backend.get_user_tasks(1)
for t in tasks:
    print(f'ID: {t["id"]}, Title: {t["title"]}, Deadline: {t["deadline"]}, Status: {t["status"]}')
print(f'\nTotal: {len(tasks)} tasks')

print('\n=== ALL EXAMS FOR USER 1 (BACKEND) ===')
exams = db_backend.get_exam_schedules(1)
for e in exams:
    print(f'ID: {e["id"]}, Subject: {e["subject"]}, Date: {e["exam_date"]}, Time: {e["start_time"]}')
print(f'\nTotal: {len(exams)} exams')
