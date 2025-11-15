// Configuration
const API_BASE_URL = 'http://localhost:5000';
const USER_ID = 1;

// Initialize analytics
document.addEventListener('DOMContentLoaded', async() => {
    console.log('Loading analytics...');
    await loadAnalytics();
});

// Load all analytics data
async function loadAnalytics() {
    try {
        // Load tasks data
        const tasksResponse = await fetch(`${API_BASE_URL}/api/tasks?user_id=${USER_ID}`);
        const tasksData = await tasksResponse.json();
        const tasks = tasksData.tasks || [];

        // Load progress data
        const progressResponse = await fetch(`${API_BASE_URL}/api/progress?user_id=${USER_ID}`);
        const progressData = await progressResponse.json();
        const progress = progressData.progress || {};

        // Update summary stats
        updateSummaryStats(tasks, progress);

        // Create charts
        createTaskCompletionChart(tasks);
        createWeeklyProgressChart(tasks);
        createDailyStudyChart(tasks);
        createPriorityChart(tasks);

        // Load recent activity
        loadRecentActivity(tasks);

    } catch (error) {
        console.error('Error loading analytics:', error);
    }
}

// Update summary statistics
function updateSummaryStats(tasks, progress) {
    const completed = tasks.filter(t => t.status === 'completed').length;
    const total = tasks.length;
    const completionRate = total > 0 ? Math.round((completed / total) * 100) : 0;

    document.getElementById('totalPointsEarned').textContent = progress.score || 0;
    document.getElementById('studyDaysMonth').textContent = progress.streak || 0;
    document.getElementById('completionRate').textContent = `${completionRate}%`;
    document.getElementById('totalStudyHours').textContent = `${(total * 2).toFixed(1)}h`; // Estimate
}

// Task Completion Pie Chart
function createTaskCompletionChart(tasks) {
    const completed = tasks.filter(t => t.status === 'completed').length;
    const pending = tasks.filter(t => t.status === 'pending').length;

    const ctx = document.getElementById('taskCompletionChart').getContext('2d');
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Completed', 'Pending'],
            datasets: [{
                data: [completed, pending],
                backgroundColor: ['#10b981', '#f59e0b'],
                borderWidth: 2,
                borderColor: '#1e293b'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#f8fafc', font: { size: 14 } }
                }
            }
        }
    });
}

// Weekly Progress Bar Chart
function createWeeklyProgressChart(tasks) {
    const today = new Date();
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const weekData = new Array(7).fill(0);

    tasks.filter(t => t.status === 'completed').forEach(task => {
        const completedDate = new Date(task.completed_at || task.created_at);
        const dayOfWeek = completedDate.getDay();
        weekData[dayOfWeek]++;
    });

    const ctx = document.getElementById('weeklyProgressChart').getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: days,
            datasets: [{
                label: 'Tasks Completed',
                data: weekData,
                backgroundColor: '#6366f1',
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { color: '#cbd5e1', stepSize: 1 },
                    grid: { color: '#334155' }
                },
                x: {
                    ticks: { color: '#cbd5e1' },
                    grid: { display: false }
                }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}

// Daily Study Time Line Chart
function createDailyStudyChart(tasks) {
    const last7Days = [];
    const studyHours = [];

    for (let i = 6; i >= 0; i--) {
        const date = new Date();
        date.setDate(date.getDate() - i);
        last7Days.push(date.toLocaleDateString('en', { month: 'short', day: 'numeric' }));

        // Simulate study hours (2 hours per completed task that day)
        const tasksOnDay = tasks.filter(t => {
            const taskDate = new Date(t.completed_at || t.created_at);
            return taskDate.toDateString() === date.toDateString() && t.status === 'completed';
        }).length;
        studyHours.push(tasksOnDay * 2);
    }

    const ctx = document.getElementById('dailyStudyChart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: last7Days,
            datasets: [{
                label: 'Study Hours',
                data: studyHours,
                borderColor: '#8b5cf6',
                backgroundColor: 'rgba(139, 92, 246, 0.1)',
                tension: 0.4,
                fill: true,
                pointRadius: 5,
                pointBackgroundColor: '#8b5cf6'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { color: '#cbd5e1' },
                    grid: { color: '#334155' }
                },
                x: {
                    ticks: { color: '#cbd5e1' },
                    grid: { display: false }
                }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}

// Priority Distribution Chart
function createPriorityChart(tasks) {
    const high = tasks.filter(t => t.importance === 'high').length;
    const medium = tasks.filter(t => t.importance === 'medium').length;
    const low = tasks.filter(t => t.importance === 'low').length;

    const ctx = document.getElementById('priorityChart').getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['High Priority', 'Medium Priority', 'Low Priority'],
            datasets: [{
                data: [high, medium, low],
                backgroundColor: ['#ef4444', '#f59e0b', '#3b82f6'],
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            scales: {
                x: {
                    beginAtZero: true,
                    ticks: { color: '#cbd5e1', stepSize: 1 },
                    grid: { color: '#334155' }
                },
                y: {
                    ticks: { color: '#cbd5e1' },
                    grid: { display: false }
                }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}

// Load recent activity
function loadRecentActivity(tasks) {
    const recentTasks = tasks
        .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
        .slice(0, 10);

    const activityHtml = recentTasks.map(task => {
        const date = new Date(task.created_at);
        const isCompleted = task.status === 'completed';
        return `
            <div class="activity-item">
                <div class="activity-icon ${isCompleted ? 'activity-completed' : 'activity-pending'}">
                    <i class="fas fa-${isCompleted ? 'check-circle' : 'clock'}"></i>
                </div>
                <div class="activity-details">
                    <div class="activity-title">${task.title}</div>
                    <div class="activity-time">${date.toLocaleDateString()} ${date.toLocaleTimeString()}</div>
                </div>
                <div class="activity-badge ${task.importance}">${task.importance}</div>
            </div>
        `;
    }).join('');

    document.getElementById('recentActivity').innerHTML = activityHtml || '<p class="info-text">No recent activity</p>';
}