// Main application initialization and event handlers

// Initialize the application when DOM is ready
document.addEventListener('DOMContentLoaded', async function() {
    console.log('Memoir UI Initialized');

    // Initialize theme
    initializeTheme();

    // Initialize event listeners
    initializeEventListeners();

    // Initialize view
    setView('tree');

    // Show initial demo data
    showDemoData();

    // Initialize input handling
    initializeInputHandling();
});

function initializeTheme() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    window.appConfig.currentTheme = savedTheme;
    updateThemeToggle();
}

function initializeEventListeners() {
    // Theme toggle
    const themeToggle = document.querySelector('.theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }

    // View buttons
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const view = e.target.dataset.view;
            setView(view);
        });
    });

    // View navigation buttons
    document.querySelectorAll('.view-nav-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const viewType = e.target.dataset.view;
            showViewContent(viewType);
        });
    });

    // Branch selector
    const branchSelector = document.getElementById('branchSelector');
    if (branchSelector) {
        branchSelector.addEventListener('change', (e) => {
            const selectedBranch = e.target.value;
            switchBranch(selectedBranch);
        });
    }

    // Branch buttons
    const addBranchBtn = document.getElementById('addBranchBtn');
    if (addBranchBtn) {
        addBranchBtn.addEventListener('click', createNewBranch);
    }

    const removeBranchBtn = document.getElementById('removeBranchBtn');
    if (removeBranchBtn) {
        removeBranchBtn.addEventListener('click', deleteCurrentBranch);
    }

    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', refreshStore);
    }
}

function initializeInputHandling() {
    const memoryInput = document.getElementById('memoryInput');
    const modelBtn = document.querySelector('.model-btn');
    const queryBtn = document.querySelector('.query-btn');

    if (memoryInput) {
        memoryInput.addEventListener('keydown', handleInputKeyDown);
        memoryInput.addEventListener('keyup', handleInputKeyUp);
    }

    if (modelBtn) {
        modelBtn.addEventListener('click', toggleModelDropdown);
    }

    if (queryBtn) {
        queryBtn.addEventListener('click', () => {
            const input = memoryInput.value.trim();
            if (input) {
                handleQueryInput(input);
            }
        });
    }

    // Model selection
    document.querySelectorAll('.model-option').forEach(option => {
        option.addEventListener('click', (e) => {
            const modelName = e.currentTarget.dataset.model;
            selectModel(modelName);
        });
    });
}

async function handleInputKeyDown(e) {
    const input = e.target;

    // Handle Enter key
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const value = input.value.trim();

        if (!value) return;

        // Add to history
        window.appConfig.commandHistory.push(value);
        window.appConfig.historyIndex = window.appConfig.commandHistory.length;

        // Check if it's a command
        if (value.startsWith('/')) {
            await window.commandHandler.handleCommand(value);
            input.value = '';
        } else {
            // Regular memory input
            await rememberContent(value);
            input.value = '';
        }
    }

    // Handle Up arrow for history
    else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (window.appConfig.historyIndex > 0) {
            if (window.appConfig.historyIndex === window.appConfig.commandHistory.length) {
                window.appConfig.currentInput = input.value;
            }
            window.appConfig.historyIndex--;
            input.value = window.appConfig.commandHistory[window.appConfig.historyIndex];
        }
    }

    // Handle Down arrow for history
    else if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (window.appConfig.historyIndex < window.appConfig.commandHistory.length - 1) {
            window.appConfig.historyIndex++;
            input.value = window.appConfig.commandHistory[window.appConfig.historyIndex];
        } else if (window.appConfig.historyIndex === window.appConfig.commandHistory.length - 1) {
            window.appConfig.historyIndex = window.appConfig.commandHistory.length;
            input.value = window.appConfig.currentInput;
        }
    }
}

function handleInputKeyUp(e) {
    const input = e.target;
    const value = input.value;

    // Show command suggestions
    if (value.startsWith('/')) {
        showCommandSuggestions(value);
    } else {
        hideCommandSuggestions();
    }
}

function showCommandSuggestions(input) {
    // Implementation for showing command suggestions
    // This would create a dropdown with matching commands
}

function hideCommandSuggestions() {
    // Implementation for hiding command suggestions
}

// Export main functions
window.app = {
    initializeTheme,
    initializeEventListeners,
    initializeInputHandling,
    handleInputKeyDown,
    handleInputKeyUp
};
