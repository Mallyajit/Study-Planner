// Configuration
const API_BASE_URL = 'http://localhost:5000';
const USER_ID = 1; // Default user - will be the WhatsApp user
const USER_PHONE = '+917384406508';

// State
let currentUser = null;
let friends = [];

// Initialize app
document.addEventListener('DOMContentLoaded', async() => {
    console.log('StudyPlanner AI - Initializing...');
    await initializeUser();
    await loadAllData();
    updateLastUpdateTime();

    // Removed auto-refresh - only refresh on user action or WhatsApp message
    // setInterval(() => {
    //     loadAllData();
    //     updateLastUpdateTime();
    // }, 30000);
});

// Initialize or get user
async function initializeUser() {
    try {
        // Try to get existing user
        const response = await fetch(`${API_BASE_URL}/api/user/${USER_ID}`);

        if (response.ok) {
            currentUser = await response.json();
            console.log('User loaded:', currentUser);
        } else {
            // Register new user
            const registerResponse = await fetch(`${API_BASE_URL}/api/user/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: 'Mallyajit',
                    phone: USER_PHONE,
                    preferences: {
                        interests: ['coding', 'gaming', 'gym'],
                        study_hours_per_day: 6
                    }
                })
            });

            if (registerResponse.ok) {
                const result = await registerResponse.json();
                currentUser = { user_id: result.user_id, name: 'Mallyajit', phone: USER_PHONE };
                console.log('User registered:', currentUser);
            }
        }

        // Update UI
        if (currentUser) {
            document.getElementById('userName').textContent = currentUser.name || 'User';
        }
    } catch (error) {
        console.error('Error initializing user:', error);
        document.getElementById('userName').textContent = 'Error loading user';
    }
}

// Load all data
async function loadAllData() {
    await Promise.all([
        loadProgress(),
        loadTasks(),
        loadSchedule(),
        loadLeaderboard(),
        loadFriends()
    ]);
}

// Load progress stats
async function loadProgress() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/progress?user_id=${USER_ID}`);
        if (!response.ok) throw new Error('Failed to load progress');

        const data = await response.json();
        const progress = data.progress;

        // Update stats cards
        document.getElementById('totalScore').textContent = progress.score || 0;
        document.getElementById('currentStreak').textContent = `${progress.streak || 0} days`;
        document.getElementById('tasksCompleted').textContent =
            `${progress.tasks.completed || 0}/${progress.tasks.total || 0}`;

        // Get rank from leaderboard (will be updated when leaderboard loads)

    } catch (error) {
        console.error('Error loading progress:', error);
    }
}

// Load tasks
async function loadTasks() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/tasks?user_id=${USER_ID}`);
        if (!response.ok) throw new Error('Failed to load tasks');

        const data = await response.json();
        const tasks = data.tasks || [];

        const tasksList = document.getElementById('tasksList');

        if (tasks.length === 0) {
            tasksList.innerHTML = `
                <p class="info-text">No tasks yet. Add one via WhatsApp or <button onclick="showAddTaskModal()" class="btn-link">click here</button>.</p>
            `;
            return;
        }

        // Separate tasks by status
        const pending = tasks.filter(t => t.status === 'pending');
        const completed = tasks.filter(t => t.status === 'completed');

        let html = '';

        // Pending tasks
        if (pending.length > 0) {
            html += '<h4 style="color: var(--warning); margin-bottom: 10px;">Pending Tasks</h4>';
            html += pending.map(task => `
                <div class="task-item ${task.importance || 'medium'}-priority">
                    <div class="task-info">
                        <div class="task-title">${task.title}</div>
                        <div class="task-deadline">
                            <i class="fas fa-clock"></i> 
                            ${task.deadline ? new Date(task.deadline).toLocaleString() : 'No deadline'}
                        </div>
                    </div>
                    <button onclick="completeTask(${task.id})" class="btn-complete">
                        <i class="fas fa-check"></i> Complete
                    </button>
                </div>
            `).join('');
        }

        // Completed tasks
        if (completed.length > 0) {
            html += '<h4 style="color: var(--success); margin-top: 20px; margin-bottom: 10px;">Completed Tasks</h4>';
            html += completed.map(task => `
                <div class="task-item completed-task">
                    <div class="task-info">
                        <div class="task-title"><s>${task.title}</s></div>
                        <div class="task-deadline">
                            <i class="fas fa-check-circle"></i> Completed
                        </div>
                    </div>
                </div>
            `).join('');
        }

        // Add task button
        html += `
            <button onclick="showAddTaskModal()" class="btn-add-task">
                <i class="fas fa-plus"></i> Add New Task
            </button>
        `;

        tasksList.innerHTML = html;

    } catch (error) {
        console.error('Error loading tasks:', error);
        document.getElementById('tasksList').innerHTML = '<p class="error-text">Error loading tasks.</p>';
    }
}

// Complete a task
async function completeTask(taskId) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/tasks`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                task_id: taskId,
                status: 'completed'
            })
        });

        if (!response.ok) throw new Error('Failed to complete task');

        const data = await response.json();

        // Show success message with points
        if (data.points_awarded > 0) {
            showNotification(`Task completed! +${data.points_awarded} points! 🎉`, 'success');
        }

        // Reload data
        await loadAllData();

    } catch (error) {
        console.error('Error completing task:', error);
        showNotification('Failed to complete task', 'error');
    }
}

// Show add task modal
function showAddTaskModal() {
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content">
            <h3><i class="fas fa-plus-circle"></i> Add New Task</h3>
            <form id="addTaskForm" onsubmit="handleAddTask(event)">
                <div class="form-group">
                    <label>Task Title *</label>
                    <input type="text" name="title" required placeholder="e.g., Complete Physics Assignment">
                </div>
                <div class="form-group">
                    <label>Deadline Date *</label>
                    <input type="date" name="deadline_date" required>
                </div>
                <div class="form-group">
                    <label>Deadline Time</label>
                    <input type="time" name="deadline_time" placeholder="15:00">
                </div>
                <div class="form-group">
                    <label>Priority</label>
                    <select name="importance">
                        <option value="low">Low</option>
                        <option value="medium" selected>Medium</option>
                        <option value="high">High</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Description (optional)</label>
                    <textarea name="description" rows="3" placeholder="Additional details..."></textarea>
                </div>
                <div class="form-actions">
                    <button type="button" onclick="closeModal()" class="btn-secondary">Cancel</button>
                    <button type="submit" class="btn-primary">Add Task</button>
                </div>
            </form>
        </div>
    `;
    document.body.appendChild(modal);
    setTimeout(() => modal.classList.add('show'), 10);
}

// Handle add task form submission
async function handleAddTask(event) {
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);

    // Combine date and time
    const date = formData.get('deadline_date');
    const time = formData.get('deadline_time');
    const deadline = time ? `${date} ${time}:00` : date;

    try {
        const response = await fetch(`${API_BASE_URL}/api/tasks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: USER_ID,
                title: formData.get('title'),
                deadline: deadline,
                importance: formData.get('importance'),
                description: formData.get('description')
            })
        });

        if (!response.ok) throw new Error('Failed to add task');

        showNotification('Task added successfully! 📝', 'success');
        closeModal();
        await loadAllData();

    } catch (error) {
        console.error('Error adding task:', error);
        showNotification('Failed to add task', 'error');
    }
}

// Close modal
function closeModal() {
    const modal = document.querySelector('.modal');
    if (modal) {
        modal.classList.remove('show');
        setTimeout(() => modal.remove(), 300);
    }
}

// Show notification
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);
    setTimeout(() => notification.classList.add('show'), 10);
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Load schedule
async function loadSchedule() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/schedule?user_id=${USER_ID}`);
        if (!response.ok) throw new Error('Failed to load schedule');

        const data = await response.json();
        const schedule = data.schedule;

        const scheduleContent = document.getElementById('scheduleContent');

        if (!schedule || !schedule.day_plan || schedule.day_plan.length === 0) {
            scheduleContent.innerHTML = `
                <p class="info-text">
                    No schedule yet. Generate one via WhatsApp:<br>
                    <code>schedule</code>
                </p>
            `;
            return;
        }

        // Show motivation message if available
        let html = '';
        if (schedule.motivation_message) {
            html += `
                <div style="background: var(--primary-dark); padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                    <i class="fas fa-lightbulb" style="color: var(--warning); margin-right: 8px;"></i>
                    ${schedule.motivation_message}
                </div>
            `;
        }

        // Show day plans
        html += schedule.day_plan.map(day => `
            <div class="schedule-day">
                <div class="schedule-day-header">
                    <div class="schedule-day-title">
                        <i class="fas fa-calendar-day"></i> ${day.day || 'Unknown'} - ${day.date || ''}
                    </div>
                    <div class="schedule-day-hours">
                        <i class="fas fa-clock"></i> ${day.total_study_hours || day.total_hours || 0}h
                    </div>
                </div>
                <div class="schedule-sessions">
                    ${day.sessions && day.sessions.length > 0 ? day.sessions.map(session => `
                        <div class="schedule-session">
                            <div class="session-time">${session.time || 'TBD'}</div>
                            <div class="session-task">${session.task || 'Study session'}</div>
                        </div>
                    `).join('') : '<p class="info-text">No sessions scheduled</p>'}
                </div>
            </div>
        `).join('');
        
        scheduleContent.innerHTML = html;
        
    } catch (error) {
        console.error('Error loading schedule:', error);
        document.getElementById('scheduleContent').innerHTML = 
            '<p class="info-text">Error loading schedule. Request a new one via WhatsApp.</p>';
    }
}

// Load leaderboard
async function loadLeaderboard() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/leaderboard?user_id=${USER_ID}&timeframe=weekly`);
        if (!response.ok) throw new Error('Failed to load leaderboard');
        
        const data = await response.json();
        // Fix: leaderboard data is nested - get weekly_leaderboard array
        const leaderboardData = data.leaderboard?.weekly_leaderboard || data.leaderboard || [];
        
        const leaderboardList = document.getElementById('leaderboardList');
        
        if (leaderboardData.length === 0) {
            leaderboardList.innerHTML = '<p class="info-text">No leaderboard data yet.</p>';
            return;
        }
        
        // Update user's rank from API response
        const userRank = data.leaderboard?.user_rank || 
                        leaderboardData.findIndex(u => u.id === USER_ID || u.user_id === USER_ID) + 1;
        if (userRank > 0) {
            document.getElementById('globalRank').textContent = `#${userRank}`;
        }
        
        leaderboardList.innerHTML = leaderboardData.slice(0, 10).map((user, index) => {
            const userId = user.id || user.user_id;
            const isCurrentUser = userId === USER_ID;
            const score = user.total_score || user.score || 0;
            const streak = user.streak || 0;
            const tasksCompleted = user.tasks_completed || 0;
            
            return `
                <div class="leaderboard-item ${isCurrentUser ? 'current-user' : ''}">
                    <div class="leaderboard-rank">#${index + 1}</div>
                    <div class="leaderboard-info">
                        <div class="leaderboard-name">
                            ${user.name}${isCurrentUser ? ' (You)' : ''}
                        </div>
                        <div class="leaderboard-stats">
                            🔥 ${streak} days | ⭐ ${score} pts
                        </div>
                    </div>
                    <div class="leaderboard-score">${score}</div>
                </div>
            `;
        }).join('');
        
    } catch (error) {
        console.error('Error loading leaderboard:', error);
        document.getElementById('leaderboardList').innerHTML = 
            '<p class="info-text">Error loading leaderboard.</p>';
    }
}

// Load friends for comparison
async function loadFriends() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/leaderboard?user_id=${USER_ID}&timeframe=all`);
        if (!response.ok) throw new Error('Failed to load friends');
        
        const data = await response.json();
        // Fix: get the actual leaderboard array from nested structure
        const allUsers = data.leaderboard?.weekly_leaderboard || data.leaderboard || [];
        friends = allUsers.filter(u => (u.id || u.user_id) !== USER_ID);
        
        const friendSelect = document.getElementById('friendSelect');
        if (friends.length === 0) {
            friendSelect.innerHTML = '<option value="">No friends yet</option>';
            return;
        }
        
        friendSelect.innerHTML = '<option value="">Select a friend...</option>' +
            friends.map(f => 
                `<option value="${f.id || f.user_id}">${f.name}</option>`
            ).join('');
        
    } catch (error) {
        console.error('Error loading friends:', error);
    }
}

// Compare with friend
async function compareFriend() {
    const friendSelect = document.getElementById('friendSelect');
    const friendId = friendSelect.value;
    
    if (!friendId) {
        document.getElementById('friendComparison').innerHTML = 
            '<p class="info-text">Select a friend to compare stats</p>';
        return;
    }
    
    try {
        const response = await fetch(
            `${API_BASE_URL}/api/friends/compare?user1_id=${USER_ID}&user2_id=${friendId}`
        );
        if (!response.ok) throw new Error('Failed to compare');
        
        const data = await response.json();
        const comparison = data.comparison;
        
        const html = `
            <div class="comparison-stats">
                <div class="comparison-item">
                    <div class="comparison-label">Score</div>
                    <div class="comparison-values">
                        <span class="comparison-you ${comparison.user1.score > comparison.user2.score ? 'comparison-winner' : ''}">
                            ${comparison.user1.score}
                        </span>
                        <span class="comparison-vs">vs</span>
                        <span class="comparison-friend ${comparison.user2.score > comparison.user1.score ? 'comparison-winner' : ''}">
                            ${comparison.user2.score}
                        </span>
                    </div>
                </div>
                
                <div class="comparison-item">
                    <div class="comparison-label">Streak</div>
                    <div class="comparison-values">
                        <span class="comparison-you ${comparison.user1.streak > comparison.user2.streak ? 'comparison-winner' : ''}">
                            ${comparison.user1.streak}
                        </span>
                        <span class="comparison-vs">vs</span>
                        <span class="comparison-friend ${comparison.user2.streak > comparison.user1.streak ? 'comparison-winner' : ''}">
                            ${comparison.user2.streak}
                        </span>
                    </div>
                </div>
                
                <div class="comparison-item">
                    <div class="comparison-label">Tasks Completed</div>
                    <div class="comparison-values">
                        <span class="comparison-you ${comparison.user1.tasks_completed > comparison.user2.tasks_completed ? 'comparison-winner' : ''}">
                            ${comparison.user1.tasks_completed}
                        </span>
                        <span class="comparison-vs">vs</span>
                        <span class="comparison-friend ${comparison.user2.tasks_completed > comparison.user2.tasks_completed ? 'comparison-winner' : ''}">
                            ${comparison.user2.tasks_completed}
                        </span>
                    </div>
                </div>
                
                <div class="comparison-item">
                    <div class="comparison-label">Study Hours</div>
                    <div class="comparison-values">
                        <span class="comparison-you ${comparison.user1.study_hours > comparison.user2.study_hours ? 'comparison-winner' : ''}">
                            ${comparison.user1.study_hours.toFixed(1)}h
                        </span>
                        <span class="comparison-vs">vs</span>
                        <span class="comparison-friend ${comparison.user2.study_hours > comparison.user1.study_hours ? 'comparison-winner' : ''}">
                            ${comparison.user2.study_hours.toFixed(1)}h
                        </span>
                    </div>
                </div>
            </div>
        `;
        
        document.getElementById('friendComparison').innerHTML = html;
        
    } catch (error) {
        console.error('Error comparing friend:', error);
        document.getElementById('friendComparison').innerHTML = 
            '<p class="info-text">Error loading comparison.</p>';
    }
}

// Utility functions
function formatDate(date) {
    const d = new Date(date);
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

function updateLastUpdateTime() {
    const now = new Date();
    document.getElementById('lastUpdate').textContent = 
        now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

// Expose functions globally for HTML onclick handlers
window.loadTasks = loadTasks;
window.loadSchedule = loadSchedule;
window.loadLeaderboard = loadLeaderboard;
window.compareFriend = compareFriend;