/**
 * State Management Module
 * Following Single Responsibility - only handles application state
 * Following Observer Pattern - notifies subscribers of state changes
 */

/**
 * Simple reactive state store
 * Implements observer pattern for state change notifications
 */
export class Store {
    constructor(initialState = {}) {
        this._state = initialState;
        this._subscribers = new Map();
        this._nextSubscriberId = 0;
    }

    /**
     * Get current state (read-only)
     */
    getState() {
        return { ...this._state };
    }

    /**
     * Get specific state slice
     */
    get(key) {
        return this._state[key];
    }

    /**
     * Update state and notify subscribers
     */
    setState(updates) {
        const prevState = { ...this._state };
        this._state = { ...this._state, ...updates };

        // Notify subscribers of changed keys
        for (const key of Object.keys(updates)) {
            if (prevState[key] !== this._state[key]) {
                this._notifySubscribers(key);
            }
        }
    }

    /**
     * Subscribe to state changes
     * Returns unsubscribe function
     */
    subscribe(key, callback) {
        if (!this._subscribers.has(key)) {
            this._subscribers.set(key, new Map());
        }

        const id = this._nextSubscriberId++;
        this._subscribers.get(key).set(id, callback);

        // Return unsubscribe function
        return () => {
            this._subscribers.get(key).delete(id);
        };
    }

    /**
     * Subscribe to multiple keys
     */
    subscribeMany(keys, callback) {
        const unsubscribes = keys.map(key => this.subscribe(key, callback));
        return () => unsubscribes.forEach(unsub => unsub());
    }

    /**
     * Notify subscribers of a key change
     */
    _notifySubscribers(key) {
        const keySubscribers = this._subscribers.get(key);
        if (keySubscribers) {
            const value = this._state[key];
            keySubscribers.forEach(callback => {
                try {
                    callback(value, key);
                } catch (error) {
                    console.error('Subscriber error:', error);
                }
            });
        }
    }
}

/**
 * Application State Schema
 */
const initialState = {
    // Connection status
    isConnected: false,
    connectionError: null,

    // Tasks
    tasks: [],
    tasksLoading: false,
    tasksError: null,
    selectedTaskId: null,
    selectedTask: null,

    // Environment Tasks
    environments: [],
    environmentsLoading: false,
    selectedEnvironment: null,
    envTasks: [],
    envTasksLoading: false,

    // Queue Stats
    queueStats: {
        pending_tasks: 0,
        total_handlers: 0,
    },
    statsLoading: false,

    // UI State
    activeTab: 'tasks',
    modalOpen: false,
    toasts: [],
};

/**
 * Create and export the application store
 */
export const appStore = new Store(initialState);

/**
 * State Actions
 * Following Command Pattern - encapsulates state mutations
 */
export const actions = {
    // Connection
    setConnected: (isConnected) => {
        appStore.setState({ isConnected, connectionError: null });
    },

    setConnectionError: (error) => {
        appStore.setState({ isConnected: false, connectionError: error });
    },

    // Tasks
    setTasks: (tasks) => {
        appStore.setState({ tasks, tasksLoading: false, tasksError: null });
    },

    setTasksLoading: (loading) => {
        appStore.setState({ tasksLoading: loading });
    },

    setTasksError: (error) => {
        appStore.setState({ tasksError: error, tasksLoading: false });
    },

    addTask: (task) => {
        const tasks = [task, ...appStore.get('tasks')];
        appStore.setState({ tasks });
    },

    updateTask: (taskId, updates) => {
        const tasks = appStore.get('tasks').map(task =>
            task.task_id === taskId ? { ...task, ...updates } : task
        );
        appStore.setState({ tasks });
    },

    selectTask: (taskId, taskData = null) => {
        appStore.setState({
            selectedTaskId: taskId,
            selectedTask: taskData,
            modalOpen: taskId !== null,
        });
    },

    // Environments
    setEnvironments: (environments) => {
        appStore.setState({ environments, environmentsLoading: false });
    },

    setSelectedEnvironment: (envType) => {
        appStore.setState({ selectedEnvironment: envType });
    },

    setEnvTasks: (envTasks) => {
        appStore.setState({ envTasks, envTasksLoading: false });
    },

    addEnvTask: (task) => {
        const envTasks = [task, ...appStore.get('envTasks')];
        appStore.setState({ envTasks });
    },

    // Queue Stats
    setQueueStats: (stats) => {
        appStore.setState({ queueStats: stats, statsLoading: false });
    },

    setStatsLoading: (loading) => {
        appStore.setState({ statsLoading: loading });
    },

    // UI
    setActiveTab: (tab) => {
        appStore.setState({ activeTab: tab });
    },

    closeModal: () => {
        appStore.setState({
            modalOpen: false,
            selectedTaskId: null,
            selectedTask: null,
        });
    },

    // Toasts
    addToast: (message, type = 'info', duration = 5000) => {
        const id = Date.now();
        const toasts = [...appStore.get('toasts'), { id, message, type }];
        appStore.setState({ toasts });

        // Auto-remove toast after duration
        if (duration > 0) {
            setTimeout(() => actions.removeToast(id), duration);
        }

        return id;
    },

    removeToast: (id) => {
        const toasts = appStore.get('toasts').filter(t => t.id !== id);
        appStore.setState({ toasts });
    },
};
