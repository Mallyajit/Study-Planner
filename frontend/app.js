// Configuration
const API_BASE_URL = 'http://localhost:5000';
const USER_ID = 1; // Default user - will be the WhatsApp user
const USER_PHONE = '+917384406508';

// State
let currentUser = null;
let friends = [];
let flashcardModules = [];
let activeQuiz = null;

// Helpers
function normalizeLeaderboardEntries(payload) {
    if (!payload) {
        return [];
    }

    if (Array.isArray(payload)) {
        return payload;
    }

    if (payload.leaderboard && Array.isArray(payload.leaderboard)) {
        return payload.leaderboard;
    }

    if (payload.weekly_leaderboard && Array.isArray(payload.weekly_leaderboard)) {
        return payload.weekly_leaderboard;
    }

    if (payload.entries && Array.isArray(payload.entries)) {
        return payload.entries;
    }

    return [];
}

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
        loadFlashcards(),
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
        const completedToShow = completed.slice(0, 5);
        const hiddenCompletedCount = Math.max(0, completed.length - completedToShow.length);

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
            html += completedToShow.map(task => `
                <div class="task-item completed-task">
                    <div class="task-info">
                        <div class="task-title"><s>${task.title}</s></div>
                        <div class="task-deadline">
                            <i class="fas fa-check-circle"></i> Completed
                        </div>
                    </div>
                </div>
            `).join('');
            if (hiddenCompletedCount > 0) {
                html += `<p class="subtle-note">Showing 5 of ${completed.length} completed tasks</p>`;
            }
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

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to complete task');
        }

        const data = await response.json();

        // Show success message with points
        if (data.points_awarded > 0) {
            showNotification(`Task completed! +${data.points_awarded} points! 🎉`, 'success');
        } else {
            showNotification('Task completed successfully!', 'success');
        }

        // Reload data
        await loadAllData();

    } catch (error) {
        console.error('Error completing task:', error);
        showNotification('Failed to complete task: ' + error.message, 'error');
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

// Load flashcards
async function loadFlashcards() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/flashcards?user_id=${USER_ID}`);
        if (!response.ok) throw new Error('Failed to load flashcards');

        const data = await response.json();
        const flashcards = data.flashcards || [];
        flashcardModules = data.modules || [];
        const weeklyPoints = data.weekly_points || 0;

        const flashcardsContent = document.getElementById('flashcardsContent');

        const summaryHtml = `
            <div class="flashcard-summary">
                <div class="summary-card">
                    <span>Weekly flashcard XP</span>
                    <strong>${weeklyPoints}</strong>
                </div>
                <div class="summary-card">
                    <span>Total cards saved</span>
                    <strong>${flashcards.length}</strong>
                </div>
            </div>
        `;

        const modulesHtml = flashcardModules.length > 0 ?
            `<div class="modules-grid">${flashcardModules.map(renderModuleCard).join('')}</div>` :
            `
                <p class="info-text">
                    Forward a PDF or clear photo of your notes on WhatsApp and I’ll auto-build flashcards plus a quiz for you.
                </p>
            `;

        const previewHtml = renderFlashcardPreview(flashcards);

        flashcardsContent.innerHTML = summaryHtml + modulesHtml + previewHtml;

    } catch (error) {
        console.error('Error loading flashcards:', error);
        document.getElementById('flashcardsContent').innerHTML =
            '<p class="error-text">Error loading flashcards.</p>';
    }
}

function renderModuleCard(module) {
    const moduleName = module.module_name || 'General Study';
    const topic = module.topic || moduleName;
    let cards = module.available_flashcards;
    if (cards === undefined || cards === null) {
        cards = module.flashcards_generated;
    }
    if (cards === undefined || cards === null) {
        cards = module.flashcard_count;
    }
    if (cards === undefined || cards === null) {
        cards = 0;
    }

    let quizCount = module.quiz_generated;
    if (quizCount === undefined || quizCount === null) {
        quizCount = module.quiz_count;
    }
    if (quizCount === undefined || quizCount === null) {
        quizCount = 0;
    }
    const created = module.created_at ? new Date(module.created_at).toLocaleDateString() : '';
    const latestAttempt = module.latest_attempt;
    const accuracy = latestAttempt && latestAttempt.total_questions ?
        Math.round((latestAttempt.correct_count / latestAttempt.total_questions) * 100) :
        null;
    const attemptCopy = latestAttempt ?
        `Last quiz: ${accuracy}%` :
        'No quiz attempts this week';

    const quizDisabled = cards <= 0;
    const quizButtonClass = quizDisabled ? 'btn-disabled' : 'btn-primary';
    const quizButtonAttrs = quizDisabled ?
        'disabled aria-disabled="true"' :
        `onclick="startModuleQuiz(${module.id})"`;

    return `
        <div class="module-card ${quizDisabled ? 'module-card--disabled' : ''}">
            <div class="module-card__header">
                <div>
                    <p class="module-label">${escapeHtml(moduleName)}</p>
                    <h4>${escapeHtml(topic)}</h4>
                </div>
                <span class="module-date">${created}</span>
            </div>
            <div class="module-metrics">
                <span><i class="fas fa-layer-group"></i> ${cards} cards</span>
                <span><i class="fas fa-question-circle"></i> ${quizCount} quiz</span>
            </div>
            <p class="module-attempt">${attemptCopy}</p>
            <button class="${quizButtonClass} full-width" ${quizButtonAttrs}>
                <i class="fas fa-play-circle"></i> ${quizDisabled ? 'Upload Notes First' : 'Study & Quiz'}
            </button>
        </div>
    `;
}

function renderFlashcardPreview(flashcards) {
    if (!flashcards || flashcards.length === 0) {
        return '';
    }

    const previewCards = flashcards.slice(0, 4);
    return `
        <div class="flashcards-preview-title">
            <h4>Recent flashcards</h4>
            <p>Tap to flip between question and answer.</p>
        </div>
        <div class="flashcard-preview-grid">
            ${previewCards.map((card, index) => `
                <div class="flashcard-preview" onclick="toggleFlashcardAnswer(this)">
                    <div class="flashcard-front">
                        <div class="flashcard-number">#${index + 1}</div>
                        <div class="flashcard-text">${escapeHtml(card.question)}</div>
                        <div class="flashcard-hint">Tap to reveal answer</div>
                    </div>
                    <div class="flashcard-back">
                        <div class="flashcard-text">${escapeHtml(card.answer)}</div>
                        <div class="flashcard-hint">Tap to view question</div>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

function toggleFlashcardAnswer(element) {
    element.classList.toggle('flipped');
}

function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value).replace(/[&<>"']/g, char => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    })[char] || char);
}

async function startModuleQuiz(batchId) {
    if (!batchId) {
        showNotification('Module is missing an identifier.', 'error');
        return;
    }

    activeQuiz = { batchId, questions: [], startedAt: Date.now(), durationMs: null };
    showQuizModal('<p class="info-text">Loading quiz questions...</p>');

    try {
        const response = await fetch(`${API_BASE_URL}/api/quiz`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: USER_ID, batch_id: batchId })
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to load quiz');
        }

        if (!data.quiz || data.quiz.length === 0) {
            showQuizModal('<p class="info-text">No quiz available for this module yet. Try generating new notes.</p>');
            return;
        }

        activeQuiz.batchId = data.batch_id || batchId;
        activeQuiz.questions = data.quiz;
        renderQuizQuestionsModal();
    } catch (error) {
        console.error('Error loading quiz:', error);
        showQuizModal(`<p class="error-text">${escapeHtml(error.message)}</p>`);
    }
}

function renderQuizQuestionsModal() {
    if (!activeQuiz || !activeQuiz.questions) {
        showQuizModal('<p class="info-text">Quiz is not ready yet.</p>');
        return;
    }

    try {
        const questionsHtml = activeQuiz.questions.map((question, index) => {
            const questionId = question.id || question.question_id;
            if (!questionId) {
                throw new Error('Quiz question missing identifier');
            }
            const options = question.options || [];
            return `
                <div class="quiz-question">
                    <h4>Q${index + 1}. ${escapeHtml(question.question)}</h4>
                    ${options.map((option, optionIndex) => `
                        <label class="quiz-option">
                            <input type="radio" name="question-${questionId}" value="${optionIndex}">
                            <span>${escapeHtml(option)}</span>
                        </label>
                    `).join('')}
                </div>
            `;
        }).join('');

        const formHtml = `
            <form id="quizForm">
                ${questionsHtml}
                <div class="quiz-actions">
                    <button type="button" class="btn-secondary" onclick="closeQuizModal()">Cancel</button>
                    <button type="submit" class="btn-primary">Submit Quiz</button>
                </div>
                <p class="quiz-hint">Finish this quiz once a week to keep earning XP.</p>
            </form>
        `;

        showQuizModal(formHtml);
        const form = document.getElementById('quizForm');
        if (form) {
            form.addEventListener('submit', submitQuizAttempt);
        }
    } catch (error) {
        console.error('Error rendering quiz modal:', error);
        showQuizModal('<p class="error-text">Quiz data is incomplete. Please re-upload your notes.</p>');
    }
}

function showQuizModal(contentHtml, title = 'Module Quiz') {
    let modal = document.getElementById('quizModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'quizModal';
        modal.className = 'quiz-modal';
        modal.innerHTML = `
            <div class="quiz-modal-overlay" onclick="closeQuizModal()"></div>
            <div class="quiz-modal-content">
                <div class="quiz-modal-header">
                    <h3><i class="fas fa-question-circle"></i> <span class="quiz-modal-title"></span></h3>
                    <button class="modal-close" aria-label="Close" onclick="closeQuizModal()">&times;</button>
                </div>
                <div class="quiz-modal-body"></div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    modal.querySelector('.quiz-modal-title').textContent = title;
    modal.querySelector('.quiz-modal-body').innerHTML = contentHtml;
    modal.classList.add('show');
}

async function submitQuizAttempt(event) {
    event.preventDefault();
    if (!activeQuiz || !activeQuiz.questions || activeQuiz.questions.length === 0) {
        return;
    }

    const form = event.target;
    let answers;
    try {
        answers = activeQuiz.questions.map((question, index) => {
            const questionId = question.id || question.question_id;
            if (!questionId) {
                throw new Error('Quiz question missing identifier');
            }
            const selected = form.querySelector(`input[name="question-${questionId}"]:checked`);
            return {
                question_id: questionId,
                selected_index: selected ? Number(selected.value) : null
            };
        });
    } catch (error) {
        console.error('Quiz submission aborted:', error);
        showQuizModal('<p class="error-text">Quiz data is incomplete. Please try regenerating your notes.</p>');
        return;
    }

    if (answers.some(answer => answer.selected_index === null)) {
        showNotification('Answer every question before submitting.', 'warning');
        return;
    }

    try {
        const durationMs = activeQuiz.startedAt ? Date.now() - activeQuiz.startedAt : null;
        if (durationMs !== null) {
            activeQuiz.durationMs = durationMs;
        }
        const response = await fetch(`${API_BASE_URL}/api/quiz/attempt`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: USER_ID,
                batch_id: activeQuiz.batchId,
                answers,
                duration_ms: durationMs
            })
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to submit quiz');
        }

        renderQuizResults(data);
        await loadFlashcards();
    } catch (error) {
        console.error('Error submitting quiz:', error);
        showNotification('Failed to submit quiz: ' + error.message, 'error');
        showQuizModal(`<p class="error-text">${escapeHtml(error.message)}</p>`);
    }
}

function renderQuizResults(result) {
    const accuracyPercent = result.total ? Math.round((result.correct / result.total) * 100) : 0;
    const weeklyCopy = result.weekly_limited
        ? 'Weekly XP already claimed for this module'
        : (result.points_awarded > 0
            ? `+${result.points_awarded} XP added to your weekly total!`
            : 'No XP awarded this round');
    const elapsedMs = result.duration_seconds ? result.duration_seconds * 1000 : activeQuiz?.durationMs;
    const elapsedSeconds = elapsedMs ? Math.round(elapsedMs / 1000) : null;
    const elapsedCopy = elapsedSeconds !== null ? `${elapsedSeconds}s` : '—';

    const resultsHtml = `
        <div class="quiz-results">
            <h4>Quiz Submitted</h4>
            <div class="quiz-result-stats">
                <span>Correct<strong>${result.correct}/${result.total}</strong></span>
                <span>Accuracy<strong>${accuracyPercent}%</strong></span>
            </div>
            <p class="quiz-duration">Time taken: <strong>${elapsedCopy}</strong></p>
            <p class="quiz-points">${weeklyCopy}</p>
            <div class="quiz-actions">
                <button class="btn-secondary" onclick="closeQuizModal()">Close</button>
            </div>
        </div>
    `;

    showQuizModal(resultsHtml, 'Great work!');
}

function closeQuizModal() {
    const modal = document.getElementById('quizModal');
    if (modal) {
        modal.classList.remove('show');
    }
    activeQuiz = null;
}

// Load schedule
async function loadSchedule() {
    const scheduleContent = document.getElementById('scheduleContent');

    try {
        const response = await fetch(`${API_BASE_URL}/api/schedule/daily?user_id=${USER_ID}`);
        if (!response.ok) throw new Error('Failed to load schedule');

        const data = await response.json();
        const {
            classes_focus = null,
                classes_today = [],
                classes_next_day = [],
                task_list = {},
                exams_schedule = [],
                study_sessions = [],
                day_name,
                date
        } = data;

        const sections = [
            renderClassesSection(classes_focus, classes_today, classes_next_day, day_name, date),
            renderTaskListSection(task_list, study_sessions),
            renderExamSection(exams_schedule)
        ].filter(Boolean);

        if (sections.length === 0) {
            scheduleContent.innerHTML = `
                <p class="info-text">
                    📅 No classes or major tasks tracked yet.<br>
                    💬 Share your timetable or deadlines on WhatsApp to populate this space.
                </p>
            `;
            return;
        }

        scheduleContent.innerHTML = sections.join('');

    } catch (error) {
        console.error('Error loading schedule:', error);
        scheduleContent.innerHTML = '<p class="info-text">Error loading schedule. Please try refreshing.</p>';
    }
}

function renderClassesSection(focusData, classesToday = [], classesNextDay = [], fallbackDayName, fallbackDateStr) {
    const focusItems = focusData?.items || [];
    const hasAnyClasses = focusItems.length > 0 || classesToday.length > 0 || classesNextDay.length > 0;

    if (!hasAnyClasses) {
        return `
            <div class="schedule-block">
                <div class="schedule-block-header">
                    <h3><i class="fas fa-chalkboard-teacher"></i> Classes</h3>
                </div>
                <p class="info-text">No timetable stored yet. Forward your class schedule via WhatsApp.</p>
            </div>
        `;
    }

    const blockDate = focusData?.date || fallbackDateStr;
    const focusDayName = focusData?.day_name || fallbackDayName || 'Today';
    const focusTag = focusData ? (focusData.is_today ? 'Today' : 'Up Next') : (fallbackDayName || 'Today');
    const headerDate = blockDate ? formatDate(blockDate) : '';

    let html = `
        <div class="schedule-block">
            <div class="schedule-block-header">
                <h3><i class="fas fa-chalkboard-teacher"></i> Classes</h3>
                <span class="schedule-block-date">${headerDate}</span>
            </div>
    `;

    if (focusItems.length > 0) {
        if (focusData && focusData.reason === 'next_day_preview') {
            html += '<p class="subtle-note">All of today\'s classes are done. Here\'s the next timetable.</p>';
        }

        html += `<h4 class="schedule-subtitle">${focusTag} • ${focusDayName}</h4>`;
        html += focusItems.map(renderClassCard).join('');
    } else {
        const todayLabel = fallbackDayName || 'Today';
        if (classesToday.length > 0) {
            html += `<h4 class="schedule-subtitle">${todayLabel}</h4>`;
            html += classesToday.map(renderClassCard).join('');
        }
        if (classesNextDay.length > 0) {
            html += `<h4 class="schedule-subtitle">Tomorrow</h4>`;
            html += classesNextDay.map(renderClassCard).join('');
        }
    }

    if (focusData?.is_today && classesNextDay.length > 0) {
        html += '<h4 class="schedule-subtitle">Tomorrow</h4>';
        html += classesNextDay.map(renderClassCard).join('');
    }

    html += '</div>';
    return html;
}

function renderClassCard(cls) {
    return `
        <div class="schedule-class">
            <div class="class-time">${cls.start_time} - ${cls.end_time}</div>
            <div class="class-details">
                <div class="class-subject">${cls.subject}</div>
                <div class="class-location"><i class="fas fa-map-marker-alt"></i> ${cls.location || 'TBD'}</div>
                ${cls.instructor ? `<div class="class-instructor"><i class="fas fa-user"></i> ${cls.instructor}</div>` : ''}
            </div>
        </div>
    `;
}

function renderTaskListSection(taskList = {}, studySessions = []) {
    const items = taskList.items || [];
    const bufferCount = taskList.buffer_count || 0;
    const focusLabel = taskList.focus_date ? formatDate(taskList.focus_date) : 'Next Day';

    let html = `
        <div class="schedule-block">
            <div class="schedule-block-header">
                <h3><i class="fas fa-list-check"></i> Task List</h3>
                <span class="schedule-block-date">Focus: ${focusLabel}</span>
            </div>
    `;

    if (items.length === 0) {
        html += '<p class="info-text">No critical deadlines for tomorrow. Keep logging your assignments!</p>';
    } else {
        html += items.map(renderTaskPill).join('');
    }

    if (bufferCount > 0) {
        html += `<p class="subtle-note">Stored ${bufferCount} additional tasks for upcoming days. They will show up closer to the due date.</p>`;
    }

    if (studySessions && studySessions.length > 0) {
        const focusSession = studySessions[0];
        html += `
            <div class="ai-study-note">
                <i class="fas fa-robot"></i>
                AI Focus: ${focusSession.task} at ${focusSession.time} (${focusSession.priority} priority)
            </div>
        `;
    }

    html += '</div>';
    return html;
}

function renderTaskPill(item) {
    const categoryIcons = {
        assignment: 'fa-book',
        exam: 'fa-clipboard-check',
        announcement: 'fa-bullhorn',
        practice: 'fa-pen'
    };
    const icon = categoryIcons[item.category] || 'fa-check-circle';
    const priorityClass = `priority-${item.importance || 'medium'}`;

    return `
        <div class="task-pill ${priorityClass}">
            <div class="task-pill-header">
                <span><i class="fas ${icon}"></i> ${item.title}</span>
                ${item.due_time ? `<span class="task-pill-time">${item.due_time}</span>` : ''}
            </div>
            <div class="task-pill-meta">
                ${item.due_date ? `<span><i class="fas fa-calendar"></i> ${formatDate(item.due_date)}</span>` : ''}
                ${item.notes ? `<span><i class="fas fa-info-circle"></i> ${item.notes}</span>` : ''}
            </div>
        </div>
    `;
}

function renderExamSection(exams = []) {
    let html = `
        <div class="schedule-block">
            <div class="schedule-block-header">
                <h3><i class="fas fa-clipboard-list"></i> Exams • Top Priority</h3>
            </div>
    `;

    if (exams.length === 0) {
        html += '<p class="info-text">No assessments recorded. Share exam notices via WhatsApp to track them here.</p>';
    } else {
        html += exams.slice(0, 5).map(renderExamCard).join('');
    }

    html += '</div>';
    return html;
}

function renderExamCard(exam) {
    let countdown = '';
    if (typeof exam.days_left === 'number') {
        countdown = exam.days_left <= 0 ? 'Today' : `${exam.days_left}d left`;
    }
    const priorityLabel = exam.is_due_soon ? '<span class="exam-priority">High Priority</span>' : '';
    return `
        <div class="schedule-exam ${exam.is_due_soon ? 'urgent' : ''}">
            <div class="exam-subject">${exam.subject || 'Exam'} ${exam.exam_type ? `(${exam.exam_type})` : ''}</div>
            <div class="exam-info">
                <span><i class="fas fa-calendar"></i> ${exam.exam_date ? formatDate(exam.exam_date) : 'TBD'}</span>
                ${exam.start_time ? `<span><i class="fas fa-clock"></i> ${exam.start_time}</span>` : ''}
                ${exam.location ? `<span><i class="fas fa-map-marker-alt"></i> ${exam.location}</span>` : ''}
            </div>
            <div class="exam-highlights">
                ${priorityLabel}
                ${countdown ? `<span class="exam-countdown">${countdown}</span>` : ''}
            </div>
        </div>
    `;
}

// Load leaderboard
async function loadLeaderboard() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/leaderboard?user_id=${USER_ID}&timeframe=weekly`);
        if (!response.ok) throw new Error('Failed to load leaderboard');
        
        const data = await response.json();
        const leaderboardPayload = data.leaderboard ? data.leaderboard : [];
        const leaderboardData = normalizeLeaderboardEntries(leaderboardPayload);
        
        const leaderboardList = document.getElementById('leaderboardList');
        
        if (leaderboardData.length === 0) {
            leaderboardList.innerHTML = '<p class="info-text">No leaderboard data yet.</p>';
            return;
        }
        
        let userRank = 0;
        if (leaderboardPayload && typeof leaderboardPayload.user_rank === 'number' && leaderboardPayload.user_rank > 0) {
            userRank = leaderboardPayload.user_rank;
        } else {
            const foundIndex = leaderboardData.findIndex(u => (u.id === USER_ID) || (u.user_id === USER_ID));
            if (foundIndex !== -1) {
                userRank = foundIndex + 1;
            }
        }

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
        const leaderboardPayload = data.leaderboard ? data.leaderboard : [];
        const allUsers = normalizeLeaderboardEntries(leaderboardPayload);
        friends = allUsers.filter(user => {
            const userId = user.id || user.user_id;
            return userId !== USER_ID;
        });
        
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
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to compare');
        }

        const comparison = data.comparison || {};
        const userStats = comparison.user1 || comparison.user || {};
        const friendStats = comparison.user2 || comparison.friend || {};
        
        const html = `
            <div class="comparison-stats">
                <div class="comparison-item">
                    <div class="comparison-label">Score</div>
                    <div class="comparison-values">
                        <span class="comparison-you ${userStats.score > friendStats.score ? 'comparison-winner' : ''}">
                            ${userStats.score ?? 0}
                        </span>
                        <span class="comparison-vs">vs</span>
                        <span class="comparison-friend ${friendStats.score > userStats.score ? 'comparison-winner' : ''}">
                            ${friendStats.score ?? 0}
                        </span>
                    </div>
                </div>
                
                <div class="comparison-item">
                    <div class="comparison-label">Streak</div>
                    <div class="comparison-values">
                        <span class="comparison-you ${userStats.streak > friendStats.streak ? 'comparison-winner' : ''}">
                            ${userStats.streak ?? 0}
                        </span>
                        <span class="comparison-vs">vs</span>
                        <span class="comparison-friend ${friendStats.streak > userStats.streak ? 'comparison-winner' : ''}">
                            ${friendStats.streak ?? 0}
                        </span>
                    </div>
                </div>
                
                <div class="comparison-item">
                    <div class="comparison-label">Tasks Completed</div>
                    <div class="comparison-values">
                        <span class="comparison-you ${userStats.tasks_completed > friendStats.tasks_completed ? 'comparison-winner' : ''}">
                            ${userStats.tasks_completed ?? 0}
                        </span>
                        <span class="comparison-vs">vs</span>
                        <span class="comparison-friend ${friendStats.tasks_completed > userStats.tasks_completed ? 'comparison-winner' : ''}">
                            ${friendStats.tasks_completed ?? 0}
                        </span>
                    </div>
                </div>
                
                <div class="comparison-item">
                    <div class="comparison-label">Study Hours</div>
                    <div class="comparison-values">
                        <span class="comparison-you ${userStats.study_hours > friendStats.study_hours ? 'comparison-winner' : ''}">
                            ${(userStats.study_hours || 0).toFixed(1)}h
                        </span>
                        <span class="comparison-vs">vs</span>
                        <span class="comparison-friend ${friendStats.study_hours > userStats.study_hours ? 'comparison-winner' : ''}">
                            ${(friendStats.study_hours || 0).toFixed(1)}h
                        </span>
                    </div>
                </div>
            </div>
        `;
        
        document.getElementById('friendComparison').innerHTML = html;
        
    } catch (error) {
        console.error('Error comparing friend:', error);
        document.getElementById('friendComparison').innerHTML = 
            `<p class="info-text">${escapeHtml(error.message || 'Error loading comparison.')}</p>`;
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