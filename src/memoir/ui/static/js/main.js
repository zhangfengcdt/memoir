// Main orchestrator for all JavaScript modules
// This file loads after all other modules and initializes the application

// Make sure all required modules are loaded
if (!window.appConfig || !window.mockData || !window.commandHandler || !window.utils || !window.app) {
    console.error('Required modules not loaded. Please check script loading order.');
}

// Re-export commonly used functions to window for backward compatibility
window.showNotification = window.utils.showNotification;
window.formatDate = window.utils.formatDate;
window.handleCommand = window.commandHandler.handleCommand;

// Store global references for functions that need to be accessible
window.connectedStorePath = null;
window.storeData = null;
window.commandHistory = window.appConfig.commandHistory;
window.historyIndex = window.appConfig.historyIndex;
window.currentInput = window.appConfig.currentInput;

// Initialize remaining functions that weren't modularized yet
// These would be the actual implementations from the original file

// Placeholder functions - these would contain the actual implementations
window.connectToStore = async function(path, silent = false) {
    // Implementation from original file
    console.log('Connecting to store:', path);
    // ... actual implementation
};

window.createNewStore = async function(path) {
    console.log('Creating new store:', path);
    // ... actual implementation
};

window.rememberContent = async function(content) {
    console.log('Remembering content:', content);
    // ... actual implementation
};

window.forgetMemory = async function(key) {
    console.log('Forgetting memory:', key);
    // ... actual implementation
};

window.refreshStore = async function() {
    console.log('Refreshing store');
    // ... actual implementation
};

window.showDemoData = function() {
    console.log('Showing demo data');
    // ... actual implementation
};

window.showRepoInfo = function() {
    console.log('Showing repo info');
    // ... actual implementation
};

window.showIntegrationCode = function() {
    console.log('Showing integration code');
    // ... actual implementation
};

window.generateProof = async function(memoryPath) {
    console.log('Generating proof for:', memoryPath);
    // ... actual implementation
};

window.showVerifyUI = function() {
    console.log('Showing verify UI');
    // ... actual implementation
};

window.showVerifyWithInput = function(proofData) {
    console.log('Verifying proof:', proofData);
    // ... actual implementation
};

window.setView = function(viewType) {
    console.log('Setting view:', viewType);
    window.appConfig.currentView = viewType;
    // ... actual implementation
};

window.toggleTheme = function() {
    const currentTheme = window.appConfig.currentTheme;
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    window.appConfig.currentTheme = newTheme;
    localStorage.setItem('theme', newTheme);
    updateThemeToggle();
};

window.updateThemeToggle = function() {
    const themeToggle = document.querySelector('.theme-toggle');
    if (themeToggle) {
        themeToggle.innerHTML = window.appConfig.currentTheme === 'dark' ? '☀️' : '🌙';
    }
};

window.showViewContent = function(viewType) {
    document.querySelectorAll('.view-content').forEach(content => {
        content.classList.remove('active');
    });
    document.querySelectorAll('.view-nav-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    const viewContent = document.getElementById(`${viewType}View`);
    if (viewContent) {
        viewContent.classList.add('active');
    }

    const viewBtn = document.querySelector(`.view-nav-btn[data-view="${viewType}"]`);
    if (viewBtn) {
        viewBtn.classList.add('active');
    }
};

// Initialize the application when all modules are loaded
console.log('Memoir UI modules loaded successfully');
