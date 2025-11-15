"""
Script to populate dummy data for friends and leaderboard
"""
from db_sqlite import get_db
import json

db = get_db()

# Add dummy users/friends
dummy_users = [
    ("Rahul Kumar", "+919876543210", 850, 12),
    ("Priya Sharma", "+919876543211", 920, 15),
    ("Arjun Patel", "+919876543212", 780, 9),
    ("Sneha Gupta", "+919876543213", 1050, 18),
    ("Vikram Singh", "+919876543214", 690, 7),
    ("Ananya Roy", "+919876543215", 1150, 21),
    ("Karan Mehta", "+919876543216", 820, 11),
]

print("Adding dummy users for leaderboard...")
for name, phone, score, streak in dummy_users:
    try:
        db.cursor.execute('''
            INSERT INTO users (name, phone, score, streak, preferences)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, phone, score, streak, json.dumps({"study_style": "focused"})))
        print(f"  ✓ Added {name} (Score: {score}, Streak: {streak})")
    except Exception as e:
        print(f"  ⚠️  {name} might already exist: {e}")

db.conn.commit()

# Add friendships for user_id=1 (your user)
print("\nAdding friends for user...")
friend_ids = [2, 3, 4, 5, 6, 7, 8]  # IDs of the dummy users

for friend_id in friend_ids:
    try:
        db.cursor.execute('''
            INSERT INTO friends (user_id, friend_id, status)
            VALUES (?, ?, 'accepted')
        ''', (1, friend_id))
        print(f"  ✓ Added friend ID {friend_id}")
    except Exception as e:
        print(f"  ⚠️  Friendship might already exist: {e}")

db.conn.commit()
print("\n✅ Dummy data added successfully!")
