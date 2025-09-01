// View Manager - Handles switching between different UI views (tree, graph, timeline, places)

// Initialize view switching
function initializeViewSwitching() {
    // View toggle - using the correct .view-btn class from HTML
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.addEventListener('click', async function() {
            document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            const view = this.dataset.view;

            // Hide all views first
            document.getElementById('treeView').style.display = 'none';
            const graphView = document.getElementById('graphView');
            if (graphView) {
                graphView.style.display = 'none';
                graphView.style.pointerEvents = 'none';
            }
            document.getElementById('timelineView').style.display = 'none';
            document.getElementById('placesView').style.display = 'none';

            // Show selected view
            if (view === 'tree') {
                document.getElementById('treeView').style.display = 'block';
            } else if (view === 'graph') {
                if (graphView) {
                    graphView.style.display = 'block';
                    graphView.style.pointerEvents = 'auto';
                    renderGraph();
                }
            } else if (view === 'timeline') {
                document.getElementById('timelineView').style.display = 'block';
                await initializeTimelineView();
            } else if (view === 'places') {
                document.getElementById('placesView').style.display = 'block';
                await initializePlacesView();
            }
        });
    });
}

// Export to global scope for backward compatibility
window.initializeViewSwitching = initializeViewSwitching;
