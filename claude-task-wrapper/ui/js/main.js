/**
 * Main Application Entry Point
 * Following Single Responsibility - orchestrates application initialization
 * Following Dependency Injection - components receive their dependencies
 */

import { taskApi, environmentApi, queueApi, ApiError } from './api.js';
import { appStore, actions } from './state.js';
import {
    TaskListComponent,
    TaskDetailComponent,
    EnvironmentSelectorComponent,
    StatsComponent,
    ToastComponent,
    ConnectionStatusComponent,
    TabController,
    ModalController,
} from './components.js';

/**
 * Application Controller
 * Coordinates between API, State, and Components
 */
class App {
    constructor() {
        this.components = {};
        this.controllers = {};
        this.pollInterval = null;
    }

    /**
     * Initialize the application
     */
    async init() {
        this.initComponents();
        this.initControllers();
        this.bindEvents();
        this.subscribeToState();

        // Initial data load
        await this.checkConnection();
        await this.loadInitialData();

        // Start polling for updates
        this.startPolling();
    }

    /**
     * Initialize UI components
     */
    initComponents() {
        // Task components
        this.components.taskList = new TaskListComponent(
            '#taskList',
            (taskId) => this.showTaskDetail(taskId)
        );

        this.components.taskDetail = new TaskDetailComponent('#taskDetailContent');

        // Environment components
        this.components.envSelector = new EnvironmentSelectorComponent(
            '#envSelector',
            (envType) => this.selectEnvironment(envType)
        );

        this.components.envTaskList = new TaskListComponent(
            '#envTaskList',
            (taskId) => this.showEnvTaskDetail(taskId)
        );

        // Stats component
        this.components.stats = new StatsComponent({
            pending: document.getElementById('statPending'),
            handlers: document.getElementById('statHandlers'),
            completed: document.getElementById('statCompleted'),
            failed: document.getElementById('statFailed'),
        });

        // Toast component
        this.components.toast = new ToastComponent('#toastContainer');
        this.components.toast.setOnClose((id) => actions.removeToast(id));

        // Connection status
        this.components.connectionStatus = new ConnectionStatusComponent('#connectionStatus');
    }

    /**
     * Initialize controllers
     */
    initControllers() {
        // Tab controller
        this.controllers.tabs = new TabController(
            document.querySelector('.tabs'),
            document.querySelector('.tab-panels'),
            (tab) => {
                actions.setActiveTab(tab);
                this.onTabChange(tab);
            }
        );

        // Modal controller
        this.controllers.modal = new ModalController(
            document.getElementById('taskDetailModal'),
            () => actions.closeModal()
        );
    }

    /**
     * Bind form and button events
     */
    bindEvents() {
        // Task form submission
        document.getElementById('taskForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.submitTask();
        });

        // Crash analysis form
        document.getElementById('crashForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.submitCrashAnalysis();
        });

        // Facts extraction form
        document.getElementById('factsForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.submitFactsExtraction();
        });

        // Refresh buttons
        document.getElementById('refreshTasks')?.addEventListener('click', () => {
            this.loadTasks();
        });

        document.getElementById('refreshEnvTasks')?.addEventListener('click', () => {
            this.loadEnvTasks();
        });

        document.getElementById('refreshStats')?.addEventListener('click', () => {
            this.loadStats();
        });

        // Task status filter
        document.getElementById('taskStatusFilter')?.addEventListener('change', (e) => {
            this.loadTasks(e.target.value || null);
        });

        // Clear queue button
        document.getElementById('clearQueue')?.addEventListener('click', () => {
            this.clearQueue();
        });

        // Continue session button
        document.getElementById('continueSessionBtn')?.addEventListener('click', () => {
            this.continueSession();
        });
    }

    /**
     * Subscribe to state changes
     */
    subscribeToState() {
        // Connection status
        appStore.subscribe('isConnected', (isConnected) => {
            const error = appStore.get('connectionError');
            this.components.connectionStatus.render(isConnected, error);
        });

        // Tasks
        appStore.subscribe('tasks', (tasks) => {
            this.components.taskList.render(tasks);
        });

        // Selected task
        appStore.subscribe('selectedTask', (task) => {
            this.components.taskDetail.render(task);

            // Show/hide continue session button
            const continueBtn = document.getElementById('continueSessionBtn');
            if (continueBtn) {
                continueBtn.hidden = !task?.session_id || task?.status !== 'completed';
            }
        });

        // Modal state
        appStore.subscribe('modalOpen', (isOpen) => {
            if (isOpen) {
                this.controllers.modal.open();
            } else {
                this.controllers.modal.close();
            }
        });

        // Environments
        appStore.subscribe('environments', (envs) => {
            const selected = appStore.get('selectedEnvironment');
            this.components.envSelector.render(envs, selected);
        });

        appStore.subscribe('selectedEnvironment', (envType) => {
            const envs = appStore.get('environments');
            this.components.envSelector.render(envs, envType);
            this.showEnvironmentForm(envType);
        });

        // Environment tasks
        appStore.subscribe('envTasks', (tasks) => {
            this.components.envTaskList.render(tasks);
        });

        // Queue stats
        appStore.subscribe('queueStats', (stats) => {
            this.components.stats.render(stats);
        });

        // Toasts
        appStore.subscribe('toasts', (toasts) => {
            this.components.toast.render(toasts);
        });
    }

    /**
     * Check API connection
     */
    async checkConnection() {
        try {
            await queueApi.healthCheck();
            actions.setConnected(true);
        } catch (error) {
            actions.setConnectionError(error.message);
        }
    }

    /**
     * Load initial data
     */
    async loadInitialData() {
        await Promise.all([
            this.loadTasks(),
            this.loadEnvironments(),
            this.loadStats(),
        ]);
    }

    /**
     * Load tasks from API
     */
    async loadTasks(status = null) {
        actions.setTasksLoading(true);
        try {
            const tasks = await taskApi.listTasks(status);
            actions.setTasks(tasks);
        } catch (error) {
            actions.setTasksError(error.message);
            this.showError('Failed to load tasks');
        }
    }

    /**
     * Load environments from API
     */
    async loadEnvironments() {
        try {
            const envs = await environmentApi.listEnvironments();
            actions.setEnvironments(envs);
        } catch (error) {
            console.error('Failed to load environments:', error);
        }
    }

    /**
     * Load environment tasks
     */
    async loadEnvTasks() {
        const envType = appStore.get('selectedEnvironment');
        if (!envType) return;

        try {
            const tasks = await environmentApi.listEnvironmentTasks(envType);
            actions.setEnvTasks(tasks);
        } catch (error) {
            console.error('Failed to load environment tasks:', error);
        }
    }

    /**
     * Load queue stats
     */
    async loadStats() {
        actions.setStatsLoading(true);
        try {
            const stats = await queueApi.getStats();
            actions.setQueueStats(stats);
        } catch (error) {
            console.error('Failed to load stats:', error);
        }
    }

    /**
     * Submit a new task
     */
    async submitTask() {
        const form = document.getElementById('taskForm');
        const formData = {
            prompt: document.getElementById('taskPrompt').value,
            taskType: document.getElementById('taskType').value,
            model: document.getElementById('taskModel').value,
            priority: parseInt(document.getElementById('taskPriority').value, 10),
            timeout: parseInt(document.getElementById('taskTimeout').value, 10),
            allowedTools: document.getElementById('taskTools').value.split(',').map(t => t.trim()),
            workingDir: document.getElementById('taskWorkDir').value,
            callbackUrl: document.getElementById('taskCallback').value || null,
        };

        try {
            const result = await taskApi.submitTask(formData);
            this.showSuccess(`Task ${result.task_id.substring(0, 8)}... submitted`);
            form.reset();

            // Refresh task list
            await this.loadTasks();
        } catch (error) {
            this.showError(`Failed to submit task: ${error.message}`);
        }
    }

    /**
     * Submit crash analysis
     */
    async submitCrashAnalysis() {
        const formData = {
            repoUrl: document.getElementById('crashRepo').value,
            backtrace: document.getElementById('crashBacktrace').value,
            commitHash: document.getElementById('crashCommit').value || null,
            branch: document.getElementById('crashBranch').value || null,
            logs: document.getElementById('crashLogs').value || null,
            additionalContext: document.getElementById('crashContext').value || null,
        };

        try {
            const result = await environmentApi.submitCrashAnalysis(formData);
            this.showSuccess(`Crash analysis task ${result.task_id.substring(0, 8)}... submitted`);
            document.getElementById('crashForm').reset();

            // Refresh environment tasks
            await this.loadEnvTasks();
        } catch (error) {
            this.showError(`Failed to submit crash analysis: ${error.message}`);
        }
    }

    /**
     * Submit facts extraction
     */
    async submitFactsExtraction() {
        const messagesText = document.getElementById('factsMessages').value;
        let messages;

        // Parse JSON messages
        try {
            messages = JSON.parse(messagesText);
            if (!Array.isArray(messages)) {
                throw new Error('Messages must be an array');
            }
        } catch (parseError) {
            this.showError(`Invalid JSON format: ${parseError.message}`);
            return;
        }

        // Parse focus areas
        const focusAreasText = document.getElementById('factsFocusAreas').value;
        const focusAreas = focusAreasText
            ? focusAreasText.split(',').map(s => s.trim()).filter(s => s)
            : null;

        const formData = {
            messages: messages,
            contextName: document.getElementById('factsContextName').value || 'conversation',
            extractionFocus: document.getElementById('factsFocus').value || 'general',
            focusAreas: focusAreas,
            additionalInstructions: document.getElementById('factsInstructions').value || null,
            priority: parseInt(document.getElementById('factsPriority').value, 10),
            callbackUrl: document.getElementById('factsCallback').value || null,
        };

        try {
            const result = await environmentApi.submitFactsExtraction(formData);
            this.showSuccess(`Facts extraction task ${result.task_id.substring(0, 8)}... submitted`);
            document.getElementById('factsForm').reset();

            // Refresh environment tasks
            await this.loadEnvTasks();
        } catch (error) {
            this.showError(`Failed to submit facts extraction: ${error.message}`);
        }
    }

    /**
     * Show task detail modal
     */
    async showTaskDetail(taskId) {
        actions.selectTask(taskId, null);

        try {
            const task = await taskApi.getTask(taskId);
            actions.selectTask(taskId, task);
        } catch (error) {
            this.showError(`Failed to load task details: ${error.message}`);
        }
    }

    /**
     * Show environment task detail
     */
    async showEnvTaskDetail(taskId) {
        const envType = appStore.get('selectedEnvironment');
        if (!envType) return;

        try {
            const task = await environmentApi.getEnvironmentTask(envType, taskId);
            // For now, show in console - could extend to use modal
            console.log('Environment task:', task);
            this.showInfo(`Task status: ${task.status}`);
        } catch (error) {
            this.showError(`Failed to load task details: ${error.message}`);
        }
    }

    /**
     * Continue a session
     */
    async continueSession() {
        const task = appStore.get('selectedTask');
        if (!task?.session_id) return;

        const prompt = window.prompt('Enter continuation prompt:');
        if (!prompt) return;

        try {
            const result = await taskApi.continueSession(task.task_id, prompt);
            this.showSuccess(`Continuation task ${result.task_id.substring(0, 8)}... submitted`);
            actions.closeModal();
            await this.loadTasks();
        } catch (error) {
            this.showError(`Failed to continue session: ${error.message}`);
        }
    }

    /**
     * Select environment type
     */
    selectEnvironment(envType) {
        actions.setSelectedEnvironment(envType);
        this.loadEnvTasks();
    }

    /**
     * Show environment-specific form
     */
    showEnvironmentForm(envType) {
        // Hide all environment forms first
        document.getElementById('crashAnalysisForm').hidden = true;
        document.getElementById('factsExtractionForm').hidden = true;

        // Show the relevant form
        if (envType === 'crash_analysis') {
            document.getElementById('crashAnalysisForm').hidden = false;
        } else if (envType === 'facts_extraction') {
            document.getElementById('factsExtractionForm').hidden = false;
        }
    }

    /**
     * Handle tab change
     */
    onTabChange(tab) {
        if (tab === 'queue') {
            this.loadStats();
        } else if (tab === 'environments') {
            this.loadEnvironments();
        }
    }

    /**
     * Clear the queue
     */
    async clearQueue() {
        if (!confirm('Are you sure you want to clear all pending tasks?')) {
            return;
        }

        try {
            const result = await queueApi.clearQueue();
            this.showSuccess(`Cleared ${result.cleared} tasks from queue`);
            await this.loadStats();
            await this.loadTasks();
        } catch (error) {
            this.showError(`Failed to clear queue: ${error.message}`);
        }
    }

    /**
     * Start polling for updates
     */
    startPolling() {
        // Poll every 10 seconds
        this.pollInterval = setInterval(async () => {
            const activeTab = appStore.get('activeTab');

            if (activeTab === 'tasks') {
                await this.loadTasks();
            } else if (activeTab === 'queue') {
                await this.loadStats();
            }

            // Always check connection
            await this.checkConnection();
        }, 10000);
    }

    /**
     * Stop polling
     */
    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    /**
     * Toast helpers
     */
    showSuccess(message) {
        actions.addToast(message, 'success');
    }

    showError(message) {
        actions.addToast(message, 'error');
    }

    showWarning(message) {
        actions.addToast(message, 'warning');
    }

    showInfo(message) {
        actions.addToast(message, 'info');
    }
}

// Initialize application when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    const app = new App();
    app.init().catch(console.error);

    // Expose for debugging
    window.__app = app;
    window.__store = appStore;
});
