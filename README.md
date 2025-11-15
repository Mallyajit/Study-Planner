# 📚 StudyPlanner AI

**AI-Powered Study Scheduler with WhatsApp Integration & Smart Task Management**

---

## 🚀 Quick Start

### 1. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 2. Configure Environment
Copy `.env.example` to `.env` and add your API keys:
```env
GEMINI_API_KEY=your_gemini_api_key_here
TWILIO_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
```

### 3. Start Backend Server
```powershell
cd backend
python -m venv ..\.venv  # First time only
& ..\.venv\Scripts\Activate.ps1
python main.py
```

### 4. Open Dashboard
Open browser: `http://localhost:5000`

---

## 💬 WhatsApp Integration

### Setup for Real WhatsApp Messages

1. **Install ngrok:**
   ```powershell
   choco install ngrok
   # OR download from https://ngrok.com/download
   ```

2. **Sign up and authenticate ngrok:**
   - Go to https://dashboard.ngrok.com/signup
   - Get your auth token from https://dashboard.ngrok.com/get-started/your-authtoken
   - Run: `ngrok config add-authtoken YOUR_TOKEN`

3. **Start ngrok tunnel:**
   ```powershell
   ngrok http 5000
   ```
   Copy the `https://` URL shown (e.g., `https://abc123.ngrok-free.app`)

4. **Configure Twilio Sandbox:**
   - Go to: https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn
   - In "When a message comes in" field, paste: `https://YOUR-NGROK-URL/webhook/whatsapp`
   - Method: POST
   - Click Save

5. **Join Sandbox:**
   - Send WhatsApp message to `+1 415 523 8886`
   - Message: `join YOUR-SANDBOX-CODE` (shown in Twilio console)

6. **Send Tasks via WhatsApp:**
   ```
   I need to study for my Algorithms exam on November 25th, high priority. 
   Also have to finish a web development project by Nov 22nd, medium importance.
   ```

### Test Locally (Without Real WhatsApp)
```powershell
curl.exe -X POST "http://localhost:5000/webhook/whatsapp" `
    -H "Content-Type: application/x-www-form-urlencoded" `
    -d "From=whatsapp:+917384406508&Body=I have a Python assignment due tomorrow at 3 PM, high priority"
```

---

## 📋 Features

### ✅ Core Features
- **AI-Powered Scheduling** - Gemini generates personalized study schedules
- **Smart Task Extraction** - Natural language processing for task creation
- **WhatsApp Integration** - Add tasks and get schedules via WhatsApp
- **Time-Slot Scheduling** - Hour-by-hour timetable (09:00-11:00, etc.)
- **Priority Management** - High/Medium/Low priority tasks
- **Points & Streaks** - Gamification with scoring system
- **Leaderboard** - Compete with friends
- **Analytics Dashboard** - Track progress with charts

### 🎯 Task Management
- Add tasks manually via dashboard
- Complete tasks to earn points (High: 50, Medium: 30, Low: 20)
- Automatic deadline tracking
- Filter out completed/overdue tasks from schedule

### 📊 Analytics
- Task completion pie chart
- Weekly progress bar chart
- Daily study time line chart
- Priority distribution
- Recent activity feed

---

## 🏗️ Project Structure

```
ProjectX/
├── backend/
│   ├── main.py              # Flask API server
│   ├── db_sqlite.py         # SQLite database layer
│   ├── studyplanner.db      # SQLite database file
│   ├── ai_logic/
│   │   └── planner.py       # Gemini AI integration
│   └── whatsapp/
│       └── bot.py           # WhatsApp bot logic
├── frontend/
│   ├── index.html           # Main dashboard
│   ├── analytics.html       # Analytics page
│   ├── app.js               # Dashboard JavaScript
│   ├── analytics.js         # Analytics JavaScript
│   └── style.css            # Styling
├── .env                     # API keys (create from .env.example)
├── .env.example             # Environment template
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

---

## 🔧 API Endpoints

### Tasks
- `GET /api/tasks?user_id=1` - Get all tasks
- `POST /api/tasks` - Create new task
- `PUT /api/tasks/<id>` - Update task (complete/edit)
- `DELETE /api/tasks/<id>` - Delete task

### Schedule
- `GET /api/schedule?user_id=1` - Get schedule (cached, no AI)
- `POST /api/schedule` - Generate new schedule with AI

### User & Progress
- `GET /api/user/<id>` - Get user info
- `GET /api/progress?user_id=1` - Get score, streak, stats

### Social Features
- `GET /api/leaderboard?user_id=1&timeframe=weekly` - Get leaderboard
- `GET /api/friends/compare?user1_id=1&user2_id=3` - Compare with friend

### WhatsApp
- `POST /webhook/whatsapp` - Webhook for incoming messages

---

## 🗄️ Database Schema

### Users Table
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT UNIQUE NOT NULL,
    score INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    preferences TEXT,  -- JSON
    created_at TIMESTAMP
)
```

### Tasks Table
```sql
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    deadline DATE NOT NULL,
    importance TEXT DEFAULT 'medium',  -- high/medium/low
    status TEXT DEFAULT 'pending',     -- pending/completed
    created_at TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
```

### Friendships Table
```sql
CREATE TABLE friendships (
    user_id INTEGER,
    friend_id INTEGER,
    created_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (friend_id) REFERENCES users(id)
)
```

---

## 🎨 Styling & UI

- **Dark Theme** - Modern dark blue/purple gradient
- **Responsive Design** - Works on desktop and mobile
- **Interactive Charts** - Chart.js for analytics
- **Smooth Animations** - CSS transitions and hover effects
- **Font Awesome Icons** - For visual elements

---

## 🐛 Troubleshooting

### Backend Won't Start
- Check if port 5000 is already in use
- Verify Python virtual environment is activated
- Check `.env` file has valid API keys

### Gemini API Rate Limit (429 Error)
- App has built-in fallback parser using regex
- Wait a few minutes and try again
- Check your Gemini API quota at https://aistudio.google.com/

### WhatsApp Messages Not Working
- Verify ngrok is running and URL is correct
- Check Twilio webhook URL ends with `/webhook/whatsapp`
- Ensure you've joined the sandbox: `join YOUR-CODE`
- Check backend console for incoming POST requests

### Tasks Not Showing in Schedule
- Check if tasks are marked as "completed" (won't show)
- Check if deadline is in the past (won't show)
- Refresh dashboard manually (auto-refresh is disabled)

### Database Issues
- Database file: `backend/studyplanner.db`
- To reset: Delete the file and restart backend (recreates schema)

---

## 🔑 Environment Variables

```env
# Required
GEMINI_API_KEY=your_gemini_api_key

# Optional (for WhatsApp)
TWILIO_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# App will work without Twilio (mock mode)
```

---

## 📱 User Information

- **Default User ID:** 1
- **Phone Number:** +917384406508
- **Name:** Mallyajit

---

## 🚦 Development Status

### ✅ Completed Features
- AI-powered schedule generation
- WhatsApp integration with fallback parser
- Task CRUD operations
- Points & streak system
- Leaderboard with dummy users
- Analytics dashboard with charts
- Time-slot based scheduling
- Manual task creation with date/time picker
- Complete task button
- Past deadline filtering

### 🔄 Future Enhancements
- Schedule editing UI
- WhatsApp study reminders
- Calendar view
- Mobile app

---

## 🛠️ Technologies Used

**Backend:**
- Python 3.10+
- Flask 3.0
- SQLite
- Google Gemini AI (gemini-2.0-flash)
- Twilio WhatsApp API

**Frontend:**
- Vanilla JavaScript
- HTML5/CSS3
- Chart.js for analytics
- Font Awesome icons

**Tools:**
- ngrok (for WhatsApp webhook)
- python-dateutil (for date parsing)

---

## 📄 License

MIT License - Feel free to use and modify for your needs.

---

**Happy Studying! 📚✨**
