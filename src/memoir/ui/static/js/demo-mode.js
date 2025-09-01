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
    showNotification('Demo mode - showing original page state for exploration', 'info');

    // Clear existing data
    storeData = null;
    window.realStoreData = null; // Clear real data so graph falls back to mock data
    window.isNewEmptyStore = false; // Ensure we show demo data, not empty state

    // Update store path display to show demo mode
    updateStorePathDisplay(null, 'disconnected');

    // Restore tree view with fold functionality
    restoreOriginalTreeView();

    // Refresh graph view with demo data
    renderGraph();

    // Update branches dropdown to original state
    updateBranchesDropdown(['main', 'experiment', 'user-profile'], 'main');

    // Update graph view to original state
    updateGraphView();
}

// Restore original tree view with demo data
function restoreOriginalTreeView() {
    const treeView = document.getElementById('treeView');
    if (!treeView) return;

    // Use the dynamic tree builder with demo data instead of static HTML
    const demoTree = generateMockTree(1.0);
    treeView.innerHTML = buildTreeFromPaths(demoTree);
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

// Check if currently in demo mode
function isDemoMode() {
    return connectedStorePath === null || connectedStorePath === 'demo';
}

// Export to global scope for use by other modules
window.showDemoData = showDemoData;
window.restoreOriginalTreeView = restoreOriginalTreeView;
window.initializePlacesDemoMode = initializePlacesDemoMode;
window.initializeDemoTimelineData = initializeDemoTimelineData;
window.isDemoMode = isDemoMode;
window.demoPlacesData = demoPlacesData;