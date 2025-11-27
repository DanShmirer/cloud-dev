/**
 * API Client Module
 * Following Single Responsibility - only handles API communication
 * Following Interface Segregation - separate methods for each endpoint
 */

/**
 * Base API client with fetch wrapper
 */
class ApiClient {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl;
    }

    /**
     * Make HTTP request with error handling
     */
    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const defaultHeaders = {
            'Content-Type': 'application/json',
        };

        const config = {
            ...options,
            headers: {
                ...defaultHeaders,
                ...options.headers,
            },
        };

        try {
            const response = await fetch(url, config);
            const data = await response.json();

            if (!response.ok) {
                throw new ApiError(
                    data.detail || 'Request failed',
                    response.status,
                    data
                );
            }

            return data;
        } catch (error) {
            if (error instanceof ApiError) {
                throw error;
            }
            throw new ApiError(error.message, 0, null);
        }
    }

    get(endpoint) {
        return this.request(endpoint, { method: 'GET' });
    }

    post(endpoint, data) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    }

    delete(endpoint) {
        return this.request(endpoint, { method: 'DELETE' });
    }
}

/**
 * Custom API Error class
 */
class ApiError extends Error {
    constructor(message, status, data) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.data = data;
    }
}

/**
 * Task API Service
 * Handles all task-related API calls
 */
export class TaskApi {
    constructor(client) {
        this.client = client;
    }

    /**
     * Submit a new task
     */
    async submitTask(taskData) {
        return this.client.post('/tasks', {
            prompt: taskData.prompt,
            task_type: taskData.taskType,
            config: {
                model: taskData.model,
                allowed_tools: taskData.allowedTools,
                working_dir: taskData.workingDir,
                timeout_seconds: taskData.timeout,
                max_turns: taskData.maxTurns || 50,
                verbose: false,
            },
            priority: taskData.priority,
            callback_url: taskData.callbackUrl || null,
        });
    }

    /**
     * Get task status and result
     */
    async getTask(taskId) {
        return this.client.get(`/tasks/${taskId}`);
    }

    /**
     * List tasks with optional status filter
     */
    async listTasks(status = null, limit = 50) {
        let endpoint = `/tasks?limit=${limit}`;
        if (status) {
            endpoint += `&status=${status}`;
        }
        return this.client.get(endpoint);
    }

    /**
     * Cancel a pending task
     */
    async cancelTask(taskId) {
        return this.client.delete(`/tasks/${taskId}`);
    }

    /**
     * Continue a session with new prompt
     */
    async continueSession(previousTaskId, prompt, config = {}) {
        return this.client.post(`/sessions/${previousTaskId}/continue`, {
            prompt,
            task_type: 'session',
            config: {
                model: config.model || 'sonnet',
                allowed_tools: config.allowedTools || ['Read', 'Glob', 'Grep'],
                working_dir: config.workingDir || '/workspace',
                timeout_seconds: config.timeout || 300,
                max_turns: 50,
                verbose: false,
            },
            priority: config.priority || 5,
        });
    }
}

/**
 * Environment Task API Service
 * Handles environment-specific task API calls
 */
export class EnvironmentApi {
    constructor(client) {
        this.client = client;
    }

    /**
     * List available environments
     */
    async listEnvironments() {
        return this.client.get('/environments');
    }

    /**
     * Get environment details
     */
    async getEnvironment(envType) {
        return this.client.get(`/environments/${envType}`);
    }

    /**
     * Submit crash analysis task
     */
    async submitCrashAnalysis(data) {
        return this.client.post('/environments/crash_analysis/tasks', {
            repo_url: data.repoUrl,
            backtrace: data.backtrace,
            commit_hash: data.commitHash || null,
            branch: data.branch || null,
            logs: data.logs || null,
            additional_context: data.additionalContext || null,
            priority: data.priority || 5,
            callback_url: data.callbackUrl || null,
        });
    }

    /**
     * Submit facts extraction task
     */
    async submitFactsExtraction(data) {
        return this.client.post('/environments/facts_extraction/tasks', {
            messages: data.messages,
            context_name: data.contextName || 'conversation',
            extraction_focus: data.extractionFocus || 'general',
            focus_areas: data.focusAreas || null,
            additional_instructions: data.additionalInstructions || null,
            priority: data.priority || 5,
            callback_url: data.callbackUrl || null,
        });
    }

    /**
     * Get environment task status
     */
    async getEnvironmentTask(envType, taskId) {
        return this.client.get(`/environments/${envType}/tasks/${taskId}`);
    }

    /**
     * List environment tasks
     */
    async listEnvironmentTasks(envType, status = null, limit = 50) {
        let endpoint = `/environments/${envType}/tasks?limit=${limit}`;
        if (status) {
            endpoint += `&status=${status}`;
        }
        return this.client.get(endpoint);
    }
}

/**
 * Queue API Service
 * Handles queue management API calls
 */
export class QueueApi {
    constructor(client) {
        this.client = client;
    }

    /**
     * Get queue statistics
     */
    async getStats() {
        return this.client.get('/queue/stats');
    }

    /**
     * Clear all pending tasks from queue
     */
    async clearQueue() {
        return this.client.post('/queue/clear', {});
    }

    /**
     * Health check
     */
    async healthCheck() {
        return this.client.get('/health');
    }
}

/**
 * Create and export API instances
 */
const client = new ApiClient('');

export const taskApi = new TaskApi(client);
export const environmentApi = new EnvironmentApi(client);
export const queueApi = new QueueApi(client);
export { ApiError };
