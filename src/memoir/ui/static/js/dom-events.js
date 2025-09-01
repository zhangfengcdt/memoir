// Event Handlers - DOM event listeners and UI interaction handlers

// Initialize all event listeners when DOM is ready
function initializeEventHandlers() {
    // Git commit node clicks
    document.querySelectorAll('.commit-node').forEach(item => {
        item.addEventListener('click', function() {
            // Remove active from all items
            document.querySelectorAll('.commit-node').forEach(i => i.classList.remove('active'));
            // Add active to clicked item
            this.classList.add('active');

            const commitId = this.dataset.commit;
            // Removed currentCommit display - was confusing for users

            // Update memory structure based on commit
            updateMemoryStructure(commitId);
        });
    });

    // Refresh button click handler
    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', async function() {
            if (!connectedStorePath) {
                showNotification('Not connected to any store', 'error');
                return;
            }

            // Add refreshing animation
            refreshBtn.classList.add('refreshing');
            refreshBtn.disabled = true;

            try {
                await refreshStore();
                showNotification('Store data refreshed', 'success');
            } catch (error) {
                console.error('Refresh error:', error);
                showNotification(`Failed to refresh: ${error.message}`, 'error');
            } finally {
                // Remove refreshing animation
                refreshBtn.classList.remove('refreshing');
                refreshBtn.disabled = false;
            }
        });
    }

    // Tree node clicks
    document.addEventListener('click', function(e) {
        if (e.target.closest('.tree-node .node-content')) {
            const node = e.target.closest('.tree-node');
            const label = node.querySelector('.node-label');
            const path = buildFullPath(node);

            if (label && label.classList.contains('has-memories')) {
                showMemoryDetails(path, node);
            }
        }
    });

    // Theme toggle
    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', function() {
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', newTheme);

            const themeIcon = themeToggle.querySelector('.theme-icon');
            if (themeIcon) {
                themeIcon.textContent = newTheme === 'dark' ? '🌙' : '☀️';
            }
            themeToggle.title = `Switch to ${newTheme === 'dark' ? 'light' : 'dark'} theme`;
        });

        // Set initial theme icon and title
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
        const themeIcon = themeToggle.querySelector('.theme-icon');
        if (themeIcon) {
            themeIcon.textContent = currentTheme === 'dark' ? '🌙' : '☀️';
        }
        themeToggle.title = `Switch to ${currentTheme === 'dark' ? 'light' : 'dark'} theme`;
    }

    // Close details
    const closeDetailsBtn = document.getElementById('closeDetails');
    if (closeDetailsBtn) {
        closeDetailsBtn.addEventListener('click', function() {
            document.getElementById('memoryDetails').classList.remove('open');
        });
    }
}

// Set up DOMContentLoaded event listener
document.addEventListener('DOMContentLoaded', initializeEventHandlers);

// Export to global scope for backward compatibility
window.initializeEventHandlers = initializeEventHandlers;
