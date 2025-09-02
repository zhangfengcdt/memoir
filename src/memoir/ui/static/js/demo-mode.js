// Demo Mode - Demo/mock functionality and sample data interactions

// Demo places data
const demoPlacesData = {
    "san_francisco": "Lived here for 3 years working at a tech startup. Loved the foggy mornings and vibrant food scene. Favorite spots included Golden Gate Park and Mission District.",
    "paris": "Spent a wonderful week exploring museums and cafes. Visited the Louvre, walked along the Seine, and enjoyed croissants every morning.",
    "tokyo": "Amazing business trip - experienced incredible sushi, visited temples in Shibuya, and was impressed by the efficiency of the train system.",
    "new_york": "Attended a conference in Manhattan. Broadway show was fantastic, Central Park was peaceful, and the energy of the city was infectious.",
    "london": "Rainy but charming visit. Tower Bridge at sunset was breathtaking, and afternoon tea at Harrods was delightful."
};

// Initialize demo mode - main demo command functionality
function showDemoData() {
    connectedStorePath = null; // Reset connection to show original state

    // Set demo mode flag to prevent disconnected state from overriding
    window.isDemoModeActive = true;

    showNotification('Demo mode - showing original page state for exploration', 'info');

    // Clear existing data
    storeData = null;
    window.realStoreData = null; // Clear real data so graph falls back to mock data
    window.isNewEmptyStore = false; // Ensure we show demo data, not empty state

    // Update store path display to show demo mode
    updateStorePathDisplay(null, 'disconnected');

    // Reset title to just "Memoir" (not "Memoir - Git History")
    const memoirLogoText = document.querySelector('.memoir-logo-text');
    if (memoirLogoText) {
        memoirLogoText.textContent = 'Memoir';

        // Monitor for changes to the title in demo mode
        if (!window.titleMonitoringActive) {
            setupTitleMonitoring();
        }
    }

    // Restore tree view with fold functionality
    restoreOriginalTreeView();

    // Restore git demo history
    restoreOriginalGitHistory();

    // Refresh graph view with demo data
    renderGraph();

    // Update branches dropdown to original state
    updateBranchesDropdown(['main', 'experiment', 'user-profile'], 'main');

    // Save demo mode state after everything is set up
    if (typeof saveConnectionState === 'function') {
        saveConnectionState();
    }
}

// Restore original tree view with demo data
function restoreOriginalTreeView() {
    console.log('restoreOriginalTreeView: called');
    const treeView = document.getElementById('treeView');
    if (!treeView) {
        console.warn('restoreOriginalTreeView: treeView element not found');
        return;
    }

    // Use the dynamic tree builder with demo data instead of static HTML
    const demoTree = generateMockTree(1.0);
    treeView.innerHTML = buildTreeFromPaths(demoTree);
    console.log('restoreOriginalTreeView: demo tree restored');

    // Add monitoring to detect when content gets overridden
    if (!window.treeMonitoringActive) {
        setupTreeViewMonitoring();
    }
}

// Initialize places view demo mode
async function initializePlacesDemoMode() {
    await updatePlacesDisplay(demoPlacesData, true); // true = demo mode

    // Initialize map if not already done
    if (!window.placesMapInitialized) {
        // Small delay to ensure DOM is ready
        setTimeout(async () => {
            initializePlacesMap();
            // Wait a bit more for map to be fully ready, then reload demo data
            setTimeout(async () => {
                await updatePlacesDisplay(demoPlacesData, true); // true = demo mode
            }, 200);
        }, 100);
    } else if (window.placesMap) {
        // Resize map when view is shown
        setTimeout(() => {
            window.placesMap.invalidateSize();
        }, 100);
    }
}

// Initialize demo timeline data for timeline view
function initializeDemoTimelineData() {
    // Demo timeline activities for GitHub-style contribution grid
    const demoActivityData = {};
    const now = new Date();

    // Generate activity for the past year
    for (let i = 0; i < 365; i++) {
        const date = new Date(now);
        date.setDate(date.getDate() - i);
        const dateStr = date.toISOString().split('T')[0];

        // Random activity level (0-4) with some days having no activity
        const activity = Math.random() < 0.7 ? Math.floor(Math.random() * 5) : 0;
        if (activity > 0) {
            demoActivityData[dateStr] = {
                count: activity,
                memories: [`Demo memory ${i + 1}`, `Sample activity ${activity}`]
            };
        }
    }

    return demoActivityData;
}

// Restore original git history with demo data
function restoreOriginalGitHistory() {
    console.log('restoreOriginalGitHistory: called');
    const gitHistory = document.querySelector('.git-tree');
    if (!gitHistory) {
        console.warn('restoreOriginalGitHistory: git-tree element not found');
        return;
    }

    // Restore demo git history HTML
    const originalGitHTML = `
        <div class="commit-node active" data-commit="abc123">
            <div class="git-lines"><div class="commit-dot main"></div></div>
            <div class="commit-content">
                <div class="commit-info">
                    <span class="commit-message">Add user preferences and timeline entries</span>
                    <span class="commit-meta">2 hours ago by <strong>Demo User</strong></span>
                </div>
            </div>
        </div>
        <div class="commit-node" data-commit="def456">
            <div class="git-lines"><div class="commit-dot main"></div></div>
            <div class="commit-content">
                <div class="commit-info">
                    <span class="commit-message">Organize professional information</span>
                    <span class="commit-meta">1 day ago by <strong>Demo User</strong></span>
                </div>
            </div>
        </div>
        <div class="commit-node" data-commit="ghi789">
            <div class="git-lines"><div class="commit-dot main"></div></div>
            <div class="commit-content">
                <div class="commit-info">
                    <span class="commit-message">Initial memory structure</span>
                    <span class="commit-meta">3 days ago by <strong>Demo User</strong></span>
                </div>
            </div>
        </div>
    `;

    gitHistory.innerHTML = originalGitHTML;
    console.log('restoreOriginalGitHistory: demo git history restored');

    // Ensure title shows just "Memoir" in demo mode, not "Memoir - Git History"
    const memoirLogoText = document.querySelector('.memoir-logo-text');
    if (memoirLogoText && window.isDemoModeActive) {
        memoirLogoText.textContent = 'Memoir';
    }

    // Add monitoring if not already set up
    if (!window.gitMonitoringActive) {
        setupGitHistoryMonitoring();
        window.gitMonitoringActive = true;
    }
}

// Monitor git history changes
function setupGitHistoryMonitoring() {
    const gitHistory = document.querySelector('.git-tree');

    if (gitHistory) {
        const gitObserver = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'childList') {
                    console.error('🚨 GIT HISTORY CHANGED! Something overrode demo content!');
                    console.error('Current innerHTML:', gitHistory.innerHTML.substring(0, 200) + '...');
                    console.trace('Stack trace of what changed the git history:');

                    // Try to restore demo content if we're still in demo mode
                    if (window.isDemoModeActive) {
                        console.warn('🔧 Attempting to restore demo git history...');
                        setTimeout(() => {
                            restoreOriginalGitHistory();
                        }, 10);
                    }
                }
            });
        });

        gitObserver.observe(gitHistory, { childList: true, subtree: true });
        console.log('🔍 Git history monitoring activated');
    }
}

// Monitor tree view changes to detect what's overriding demo content
function setupTreeViewMonitoring() {
    const treeView = document.getElementById('treeView');

    if (treeView) {
        // Create a MutationObserver to monitor innerHTML changes
        const treeObserver = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'childList') {
                    console.error('🚨 TREE VIEW CHANGED! Something overrode demo content!');
                    console.error('Current innerHTML:', treeView.innerHTML.substring(0, 200) + '...');
                    console.trace('Stack trace of what changed the tree view:');

                    // Try to restore demo content if we're still in demo mode
                    if (window.isDemoModeActive) {
                        console.warn('🔧 Attempting to restore demo tree content...');
                        setTimeout(() => {
                            const demoTree = generateMockTree(1.0);
                            treeView.innerHTML = buildTreeFromPaths(demoTree);
                        }, 10);
                    }
                }
            });
        });

        treeObserver.observe(treeView, { childList: true, subtree: true });
        console.log('🔍 Tree view monitoring activated');
        window.treeMonitoringActive = true;
    }
}

// Monitor title changes to detect what's overriding demo mode title
function setupTitleMonitoring() {
    const memoirLogoText = document.querySelector('.memoir-logo-text');

    if (memoirLogoText) {
        // Create a MutationObserver to monitor text changes
        const titleObserver = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'characterData' || mutation.type === 'childList') {
                    const currentText = memoirLogoText.textContent;

                    // Restore demo title if we're still in demo mode and it was changed
                    if (window.isDemoModeActive && currentText !== 'Memoir') {
                        setTimeout(() => {
                            if (window.isDemoModeActive) {
                                memoirLogoText.textContent = 'Memoir';
                            }
                        }, 10);
                    }
                }
            });
        });

        titleObserver.observe(memoirLogoText, {
            characterData: true,
            childList: true,
            subtree: true
        });
        window.titleMonitoringActive = true;
    }
}

// Check if currently in demo mode
function isDemoMode() {
    return window.isDemoModeActive || connectedStorePath === null || connectedStorePath === 'demo';
}

// Export to global scope for use by other modules
window.showDemoData = showDemoData;
window.restoreOriginalTreeView = restoreOriginalTreeView;
window.restoreOriginalGitHistory = restoreOriginalGitHistory;
window.initializePlacesDemoMode = initializePlacesDemoMode;
window.initializeDemoTimelineData = initializeDemoTimelineData;
window.setupTitleMonitoring = setupTitleMonitoring;
window.isDemoMode = isDemoMode;
window.demoPlacesData = demoPlacesData;
