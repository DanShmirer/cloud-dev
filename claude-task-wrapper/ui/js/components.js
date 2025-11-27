/**
 * UI Components Module
 * Following Single Responsibility - each component renders one thing
 * Following Open/Closed - components can be extended without modification
 */

/**
 * Base Component class
 * Provides common rendering and DOM manipulation utilities
 */
class Component {
    constructor(container) {
        this.container = typeof container === 'string'
            ? document.querySelector(container)
            : container;
    }

    /**
     * Render content to container
     */
    render(html) {
        if (this.container) {
            this.container.innerHTML = html;
        }
    }

    /**
     * Query element within container
     */
    $(selector) {
        return this.container?.querySelector(selector);
    }

    /**
     * Query all elements within container
     */
    $$(selector) {
        return this.container?.querySelectorAll(selector) || [];
    }
}

/**
 * Task List Component
 * Renders a list of tasks with status indicators
 */
export class TaskListComponent extends Component {
    constructor(container, onTaskClick) {
        super(container);
        this.onTaskClick = onTaskClick;
    }

    render(tasks) {
        if (!tasks || tasks.length === 0) {
            super.render(`
                <div class="task-list__empty">
                    No tasks yet. Submit a task to get started.
                </div>
            `);
            return;
        }

        const html = tasks.map(task => this.renderTask(task)).join('');
        super.render(html);

        // Attach click handlers
        this.$$('.task-item').forEach(item => {
            item.addEventListener('click', () => {
                const taskId = item.dataset.taskId;
                if (this.onTaskClick) {
                    this.onTaskClick(taskId);
                }
            });
        });
    }

    renderTask(task) {
        const preview = task.prompt
            ? task.prompt.substring(0, 60) + (task.prompt.length > 60 ? '...' : '')
            : 'No prompt';

        return `
            <div class="task-item" data-task-id="${task.task_id}">
                <span class="task-item__status task-item__status--${task.status}"></span>
                <div class="task-item__content">
                    <div class="task-item__id">${task.task_id.substring(0, 8)}...</div>
                    <div class="task-item__preview">${this.escapeHtml(preview)}</div>
                </div>
                <div class="task-item__meta">
                    <span class="task-item__time">${this.formatTime(task.created_at)}</span>
                </div>
            </div>
        `;
    }

    escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    formatTime(timestamp) {
        if (!timestamp) return '';
        const date = new Date(timestamp);
        return date.toLocaleTimeString();
    }
}

/**
 * Task Detail Component
 * Renders detailed task information in modal
 */
export class TaskDetailComponent extends Component {
    render(task) {
        if (!task) {
            super.render('<div class="loading">Loading task details...</div>');
            return;
        }

        const html = `
            <div class="task-detail">
                <div class="task-detail__row">
                    <div class="task-detail__field">
                        <div class="task-detail__label">Task ID</div>
                        <div class="task-detail__value">
                            <code>${task.task_id}</code>
                        </div>
                    </div>
                    <div class="task-detail__field">
                        <div class="task-detail__label">Status</div>
                        <div class="task-detail__value">
                            <span class="task-detail__badge task-detail__badge--${task.status}">
                                ${task.status}
                            </span>
                        </div>
                    </div>
                </div>

                ${task.duration_seconds ? `
                <div class="task-detail__row">
                    <div class="task-detail__field">
                        <div class="task-detail__label">Duration</div>
                        <div class="task-detail__value">${task.duration_seconds.toFixed(2)}s</div>
                    </div>
                    <div class="task-detail__field">
                        <div class="task-detail__label">Cost</div>
                        <div class="task-detail__value">
                            ${task.cost_usd ? `$${task.cost_usd.toFixed(4)}` : 'N/A'}
                        </div>
                    </div>
                </div>
                ` : ''}

                ${task.session_id ? `
                <div class="task-detail__field">
                    <div class="task-detail__label">Session ID</div>
                    <div class="task-detail__value">
                        <code>${task.session_id}</code>
                    </div>
                </div>
                ` : ''}

                ${task.output ? `
                <div class="task-detail__field">
                    <div class="task-detail__label">Output</div>
                    <div class="task-detail__output">${this.escapeHtml(task.output)}</div>
                </div>
                ` : ''}

                ${task.error ? `
                <div class="task-detail__field">
                    <div class="task-detail__label">Error</div>
                    <div class="task-detail__output task-detail__error">
                        ${this.escapeHtml(task.error)}
                    </div>
                </div>
                ` : ''}
            </div>
        `;

        super.render(html);
    }

    escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
}

/**
 * Environment Selector Component
 * Renders available environments as selectable options
 */
export class EnvironmentSelectorComponent extends Component {
    constructor(container, onSelect) {
        super(container);
        this.onSelect = onSelect;
    }

    render(environments, selectedEnv = null) {
        if (!environments || environments.length === 0) {
            super.render(`
                <div class="loading">No environments available.</div>
            `);
            return;
        }

        const icons = {
            'crash_analysis': '🔍',
            'facts_extraction': '📝',
        };

        const html = environments.map(env => `
            <div class="env-option ${selectedEnv === env.type ? 'env-option--selected' : ''}"
                 data-env-type="${env.type}">
                <span class="env-option__icon">${icons[env.type] || '📦'}</span>
                <div class="env-option__info">
                    <div class="env-option__name">${env.name}</div>
                    <div class="env-option__description">${env.description}</div>
                </div>
            </div>
        `).join('');

        super.render(html);

        // Attach click handlers
        this.$$('.env-option').forEach(option => {
            option.addEventListener('click', () => {
                const envType = option.dataset.envType;
                if (this.onSelect) {
                    this.onSelect(envType);
                }
            });
        });
    }
}

/**
 * Stats Component
 * Renders queue statistics
 */
export class StatsComponent {
    constructor(elements) {
        this.elements = elements;
    }

    render(stats) {
        if (this.elements.pending) {
            this.elements.pending.textContent = stats.pending_tasks ?? '-';
        }
        if (this.elements.handlers) {
            this.elements.handlers.textContent = stats.total_handlers ?? '-';
        }
        if (this.elements.completed) {
            this.elements.completed.textContent = stats.completed_today ?? '-';
        }
        if (this.elements.failed) {
            this.elements.failed.textContent = stats.failed_today ?? '-';
        }
    }
}

/**
 * Toast Component
 * Manages toast notifications
 */
export class ToastComponent extends Component {
    render(toasts) {
        const html = toasts.map(toast => `
            <div class="toast toast--${toast.type}" data-toast-id="${toast.id}">
                <span class="toast__message">${this.escapeHtml(toast.message)}</span>
                <button class="toast__close" aria-label="Close">&times;</button>
            </div>
        `).join('');

        super.render(html);

        // Attach close handlers
        this.$$('.toast__close').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const toast = e.target.closest('.toast');
                const id = parseInt(toast.dataset.toastId, 10);
                this.onClose?.(id);
            });
        });
    }

    escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    setOnClose(callback) {
        this.onClose = callback;
    }
}

/**
 * Connection Status Component
 * Renders connection status indicator
 */
export class ConnectionStatusComponent extends Component {
    render(isConnected, error = null) {
        const statusClass = isConnected ? 'connected' : 'disconnected';
        const statusText = isConnected ? 'Connected' : (error || 'Disconnected');

        super.render(`
            <span class="status-indicator status-indicator--${statusClass}"></span>
            <span>${statusText}</span>
        `);
    }
}

/**
 * Tab Controller
 * Manages tab switching
 */
export class TabController {
    constructor(tabsContainer, panelsContainer, onChange) {
        this.tabs = tabsContainer.querySelectorAll('.tab');
        this.panels = panelsContainer.querySelectorAll('.tab-panel');
        this.onChange = onChange;

        this.attachHandlers();
    }

    attachHandlers() {
        this.tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const tabName = tab.dataset.tab;
                this.activate(tabName);
            });
        });
    }

    activate(tabName) {
        // Update tab buttons
        this.tabs.forEach(tab => {
            const isActive = tab.dataset.tab === tabName;
            tab.classList.toggle('tab--active', isActive);
            tab.setAttribute('aria-selected', isActive);
        });

        // Update panels
        this.panels.forEach(panel => {
            const isActive = panel.id === `panel-${tabName}`;
            panel.classList.toggle('tab-panel--active', isActive);
            panel.hidden = !isActive;
        });

        if (this.onChange) {
            this.onChange(tabName);
        }
    }
}

/**
 * Modal Controller
 * Manages modal open/close behavior
 */
export class ModalController {
    constructor(modalElement, onClose) {
        this.modal = modalElement;
        this.onClose = onClose;

        this.attachHandlers();
    }

    attachHandlers() {
        // Close on backdrop click
        const backdrop = this.modal.querySelector('.modal__backdrop');
        backdrop?.addEventListener('click', () => this.close());

        // Close buttons
        this.modal.querySelectorAll('.modal__close, .modal__close-btn').forEach(btn => {
            btn.addEventListener('click', () => this.close());
        });

        // Close on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !this.modal.hidden) {
                this.close();
            }
        });
    }

    open() {
        this.modal.hidden = false;
        document.body.style.overflow = 'hidden';
    }

    close() {
        this.modal.hidden = true;
        document.body.style.overflow = '';
        if (this.onClose) {
            this.onClose();
        }
    }

    isOpen() {
        return !this.modal.hidden;
    }
}
