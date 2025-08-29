// Configuration and global state
const config = {
    // Store connection state
    connectedStorePath: null,
    storeData: null,
    
    // Command history
    commandHistory: [],
    historyIndex: -1,
    currentInput: '',
    
    // Model selection
    selectedModel: 'gpt-4o-mini',
    
    // Theme
    currentTheme: 'dark',
    
    // Graph state
    currentView: 'tree',
    graphSimulation: null,
    currentCommitIndex: 0,
    
    // UI state
    lastGeneratedProof: null,
    currentBranch: 'main',
    branches: ['main'],
    
    // API endpoints
    apiBase: window.location.origin
};

// Export for other modules
window.appConfig = config;