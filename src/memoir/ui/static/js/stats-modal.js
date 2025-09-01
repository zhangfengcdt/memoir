/**
 * Statistics Modal Module
 * Handles the display and interaction of memory store statistics
 */

class StoreStatsModal {
    constructor() {
        this.modal = null;
        this.currentTab = 'overview';
        this.statistics = null;
        this.charts = {};
        this.isLoading = false;
        
        this.initModal();
        this.bindEvents();
    }
    
    initModal() {
        // Check if modal already exists
        const existing = document.getElementById('storeStatsModal');
        if (existing) {
            this.modal = existing;
            return;
        }
        
        // Create modal HTML structure
        this.modal = this.createModalHTML();
        document.body.appendChild(this.modal);
    }
    
    createModalHTML() {
        const modal = document.createElement('div');
        modal.id = 'storeStatsModal';
        modal.className = 'stats-modal';
        
        modal.innerHTML = `
            <div class="stats-modal-content">
                <div class="stats-header">
                    <h2>📊 Memory Store Statistics</h2>
                    <div class="stats-path" id="statsStorePath"></div>
                    <button class="stats-close" id="statsCloseBtn">&times;</button>
                </div>
                
                <div class="stats-tabs">
                    <button class="stats-tab active" data-tab="overview">Overview</button>
                    <button class="stats-tab" data-tab="structure">Tree Structure</button>
                    <button class="stats-tab" data-tab="versioning">Version Control</button>
                    <button class="stats-tab" data-tab="performance">Performance</button>
                    <button class="stats-tab" data-tab="taxonomy">Classification</button>
                    <button class="stats-tab" data-tab="content">Content Analysis</button>
                </div>
                
                <div class="stats-content" id="statsContent">
                    <!-- Tab content dynamically loaded -->
                </div>
                
                <div class="stats-footer">
                    <div class="stats-refresh">
                        <button id="refreshStatsBtn">🔄 Refresh</button>
                        <span class="last-updated" id="statsLastUpdated">Never</span>
                    </div>
                    <div class="stats-actions">
                        <button id="exportStatsBtn">📤 Export JSON</button>
                    </div>
                </div>
            </div>
        `;
        
        return modal;
    }
    
    bindEvents() {
        // Close button
        document.addEventListener('click', (e) => {
            if (e.target.id === 'statsCloseBtn' || e.target.classList.contains('stats-modal')) {
                this.hide();
            }
        });
        
        // Tab switching
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('stats-tab')) {
                this.switchTab(e.target.dataset.tab);
            }
        });
        
        // Refresh button
        document.addEventListener('click', (e) => {
            if (e.target.id === 'refreshStatsBtn') {
                this.refresh();
            }
        });
        
        // Export button
        document.addEventListener('click', (e) => {
            if (e.target.id === 'exportStatsBtn') {
                this.exportStatistics();
            }
        });
        
        // ESC key to close
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.modal.classList.contains('show')) {
                this.hide();
            }
        });
    }
    
    async show(storePath) {
        if (!storePath) {
            console.error('No store path provided');
            return;
        }
        
        // Update store path display
        const pathElement = document.getElementById('statsStorePath');
        if (pathElement) {
            pathElement.textContent = `🔗 ${storePath}`;
        }
        
        // Show modal
        this.modal.classList.add('show');
        
        // Load statistics
        await this.loadStatistics(storePath);
    }
    
    hide() {
        this.modal.classList.remove('show');
    }
    
    async loadStatistics(storePath) {
        if (this.isLoading) return;
        
        this.isLoading = true;
        this.showLoading();
        
        try {
            const response = await fetch(`/api/statistics?path=${encodeURIComponent(storePath)}`);
            const data = await response.json();
            
            if (data.success) {
                this.statistics = data.statistics;
                this.updateLastUpdated();
                this.renderContent();
            } else {
                this.showError(data.error || 'Failed to load statistics');
            }
        } catch (error) {
            console.error('Error loading statistics:', error);
            this.showError('Failed to load statistics: ' + error.message);
        } finally {
            this.isLoading = false;
        }
    }
    
    async refresh() {
        const pathElement = document.getElementById('statsStorePath');
        if (pathElement) {
            const path = pathElement.textContent.replace('🔗 ', '');
            await this.loadStatistics(path);
        }
    }
    
    showLoading() {
        const content = document.getElementById('statsContent');
        if (content) {
            content.innerHTML = `
                <div class="stats-loading">
                    <div class="loading-spinner"></div>
                    <p>Loading statistics...</p>
                </div>
            `;
        }
    }
    
    showError(message) {
        const content = document.getElementById('statsContent');
        if (content) {
            content.innerHTML = `
                <div class="stats-error">
                    <p>❌ ${message}</p>
                </div>
            `;
        }
    }
    
    switchTab(tab) {
        // Update active tab
        document.querySelectorAll('.stats-tab').forEach(t => {
            t.classList.toggle('active', t.dataset.tab === tab);
        });
        
        this.currentTab = tab;
        this.renderContent();
    }
    
    renderContent() {
        if (!this.statistics) return;
        
        switch (this.currentTab) {
            case 'overview':
                this.renderOverview();
                break;
            case 'structure':
                this.renderTreeStructure();
                break;
            case 'versioning':
                this.renderVersioning();
                break;
            case 'performance':
                this.renderPerformance();
                break;
            case 'taxonomy':
                this.renderTaxonomy();
                break;
            case 'content':
                this.renderContentAnalysis();
                break;
        }
    }
    
    renderOverview() {
        const content = document.getElementById('statsContent');
        const stats = this.statistics;
        
        content.innerHTML = `
            <div class="stats-overview">
                <div class="stats-grid">
                    ${this.createStatCard('🗄️', stats.storage?.total_keys || 0, 'Total Keys', `${stats.storage?.total_namespaces || 0} namespaces`)}
                    ${this.createStatCard('🌳', stats.tree_structure?.total_levels || 0, 'Tree Levels', 'Max depth')}
                    ${this.createStatCard('🌿', stats.versioning?.total_branches || 0, 'Branches', stats.versioning?.current_branch || 'main')}
                    ${this.createStatCard('📝', stats.versioning?.total_commits || 0, 'Commits', `${stats.versioning?.commits_this_week || 0} this week`)}
                    ${this.createStatCard('⚡', `${stats.performance?.timing_averages?.avg_search_ms?.toFixed(1) || '0.0'}ms`, 'Avg Search', `${Math.round((stats.performance?.memory_usage?.cache_hit_ratio || 0) * 100)}% cache hit`)}
                    ${this.createStatCard('💾', `${(stats.storage?.store_size_mb || 0).toFixed(1)}MB`, 'Store Size', `${stats.storage?.average_key_length || 0} avg key length`)}
                </div>
                
                <div class="stats-summary">
                    <h3>Quick Summary</h3>
                    <div class="summary-items">
                        <div class="summary-item">
                            <span class="summary-label">Store Type:</span>
                            <span class="summary-value">${stats.metadata?.store_type || 'Unknown'}</span>
                        </div>
                        <div class="summary-item">
                            <span class="summary-label">Store Age:</span>
                            <span class="summary-value">${stats.metadata?.store_age_days || 0} days</span>
                        </div>
                        <div class="summary-item">
                            <span class="summary-label">Git Initialized:</span>
                            <span class="summary-value">${stats.metadata?.git_initialized ? '✅ Yes' : '❌ No'}</span>
                        </div>
                        <div class="summary-item">
                            <span class="summary-label">Uncommitted Changes:</span>
                            <span class="summary-value">${stats.versioning?.uncommitted_changes || 0}</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    renderTreeStructure() {
        const content = document.getElementById('statsContent');
        const stats = this.statistics.tree_structure || {};
        
        content.innerHTML = `
            <div class="stats-tree-structure">
                <div class="tree-metrics">
                    <div class="level-breakdown">
                        <h3>Nodes per Level</h3>
                        <div class="level-bars">
                            ${this.renderLevelBars(stats.nodes_per_level || {})}
                        </div>
                    </div>
                    
                    <div class="tree-analysis">
                        <h3>Tree Analysis</h3>
                        <div class="analysis-item">
                            <span class="analysis-label">Total Nodes:</span>
                            <span class="analysis-value">${stats.total_nodes || 0}</span>
                        </div>
                        <div class="analysis-item">
                            <span class="analysis-label">Deepest Path:</span>
                            <span class="analysis-value" title="${stats.deepest_path || 'N/A'}">${this.truncatePath(stats.deepest_path || 'N/A')}</span>
                        </div>
                        <div class="analysis-item">
                            <span class="analysis-label">Widest Branch:</span>
                            <span class="analysis-value">${stats.widest_branch || 'N/A'}</span>
                        </div>
                    </div>
                </div>
                
                <div class="category-distribution">
                    <h3>Category Distribution</h3>
                    <div class="category-bars">
                        ${this.renderCategoryBars(stats.categories || {})}
                    </div>
                </div>
            </div>
        `;
    }
    
    renderVersioning() {
        const content = document.getElementById('statsContent');
        const stats = this.statistics.versioning || {};
        
        content.innerHTML = `
            <div class="stats-versioning">
                <div class="branch-info">
                    <h3>Current State</h3>
                    <div class="current-branch">
                        <span class="branch-icon">🌿</span>
                        <span class="branch-name">${stats.current_branch || 'unknown'}</span>
                        <span class="commit-hash">(${stats.current_commit || 'unknown'})</span>
                    </div>
                    
                    <div class="uncommitted-changes">
                        <span class="changes-count">${stats.uncommitted_changes || 0}</span>
                        <span class="changes-label">uncommitted changes</span>
                    </div>
                    
                    <div class="last-commit">
                        <div class="commit-date">Last commit: ${stats.last_commit_date || 'Unknown'}</div>
                        <div class="commit-message">"${stats.last_commit_message || 'No message'}"</div>
                    </div>
                </div>
                
                <div class="branch-list">
                    <h3>All Branches (${stats.total_branches || 0})</h3>
                    <div class="branch-items">
                        ${(stats.branches || []).map(branch => `
                            <div class="branch-item ${branch === stats.current_branch ? 'active' : ''}">
                                <span class="branch-name">${branch}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
                
                <div class="commit-stats">
                    <h3>Commit Statistics</h3>
                    <div class="commit-info">
                        <div class="commit-stat">
                            <span class="stat-label">Total Commits:</span>
                            <span class="stat-value">${stats.total_commits || 0}</span>
                        </div>
                        <div class="commit-stat">
                            <span class="stat-label">Commits This Week:</span>
                            <span class="stat-value">${stats.commits_this_week || 0}</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    renderPerformance() {
        const content = document.getElementById('statsContent');
        const stats = this.statistics.performance || {};
        
        content.innerHTML = `
            <div class="stats-performance">
                <div class="performance-grid">
                    <div class="perf-section">
                        <h3>Operations Count</h3>
                        <div class="perf-items">
                            <div class="perf-item">
                                <span class="perf-label">Reads:</span>
                                <span class="perf-value">${stats.operations?.reads || 0}</span>
                            </div>
                            <div class="perf-item">
                                <span class="perf-label">Writes:</span>
                                <span class="perf-value">${stats.operations?.writes || 0}</span>
                            </div>
                            <div class="perf-item">
                                <span class="perf-label">Searches:</span>
                                <span class="perf-value">${stats.operations?.searches || 0}</span>
                            </div>
                            <div class="perf-item">
                                <span class="perf-label">Classifications:</span>
                                <span class="perf-value">${stats.operations?.classifications || 0}</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="perf-section">
                        <h3>Average Timing</h3>
                        <div class="perf-items">
                            <div class="perf-item">
                                <span class="perf-label">Avg Read:</span>
                                <span class="perf-value">${stats.timing_averages?.avg_read_ms || 0}ms</span>
                            </div>
                            <div class="perf-item">
                                <span class="perf-label">Avg Write:</span>
                                <span class="perf-value">${stats.timing_averages?.avg_write_ms || 0}ms</span>
                            </div>
                            <div class="perf-item">
                                <span class="perf-label">Avg Search:</span>
                                <span class="perf-value">${stats.timing_averages?.avg_search_ms || 0}ms</span>
                            </div>
                            <div class="perf-item">
                                <span class="perf-label">Avg Classification:</span>
                                <span class="perf-value">${stats.timing_averages?.avg_classification_ms || 0}ms</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="perf-section">
                        <h3>Memory Usage</h3>
                        <div class="perf-items">
                            <div class="perf-item">
                                <span class="perf-label">Cache Hit Ratio:</span>
                                <span class="perf-value">${Math.round((stats.memory_usage?.cache_hit_ratio || 0) * 100)}%</span>
                            </div>
                            <div class="perf-item">
                                <span class="perf-label">Cache Size:</span>
                                <span class="perf-value">${stats.memory_usage?.cache_size_mb || 0}MB</span>
                            </div>
                            <div class="perf-item">
                                <span class="perf-label">Active Connections:</span>
                                <span class="perf-value">${stats.memory_usage?.active_connections || 0}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    renderTaxonomy() {
        const content = document.getElementById('statsContent');
        const stats = this.statistics.taxonomy || {};
        
        content.innerHTML = `
            <div class="stats-taxonomy">
                <div class="taxonomy-overview">
                    <h3>Classification Overview</h3>
                    <div class="taxonomy-stats">
                        <div class="tax-stat">
                            <span class="tax-label">Total Paths:</span>
                            <span class="tax-value">${stats.total_paths || 0}</span>
                        </div>
                        <div class="tax-stat">
                            <span class="tax-label">Categories:</span>
                            <span class="tax-value">${stats.categories || 0}</span>
                        </div>
                        <div class="tax-stat">
                            <span class="tax-label">Classification Accuracy:</span>
                            <span class="tax-value">${Math.round((stats.classification_accuracy || 0) * 100)}%</span>
                        </div>
                    </div>
                </div>
                
                <div class="category-breakdown">
                    <h3>Paths by Category</h3>
                    <div class="category-list">
                        ${this.renderCategoryList(stats.paths_by_category || {})}
                    </div>
                </div>
                
                <div class="confidence-thresholds">
                    <h3>Confidence Thresholds</h3>
                    <div class="threshold-items">
                        <div class="threshold-item">
                            <span class="threshold-label">High:</span>
                            <span class="threshold-value">${stats.confidence_thresholds?.high || 0}</span>
                        </div>
                        <div class="threshold-item">
                            <span class="threshold-label">Medium:</span>
                            <span class="threshold-value">${stats.confidence_thresholds?.medium || 0}</span>
                        </div>
                        <div class="threshold-item">
                            <span class="threshold-label">Low:</span>
                            <span class="threshold-value">${stats.confidence_thresholds?.low || 0}</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    renderContentAnalysis() {
        const content = document.getElementById('statsContent');
        const stats = this.statistics.content || {};
        
        content.innerHTML = `
            <div class="stats-content-analysis">
                <div class="content-overview">
                    <h3>Content Statistics</h3>
                    <div class="content-stats">
                        <div class="content-stat">
                            <span class="content-label">Memories Sampled:</span>
                            <span class="content-value">${stats.total_memories_sampled || 0}</span>
                        </div>
                        <div class="content-stat">
                            <span class="content-label">Avg Content Length:</span>
                            <span class="content-value">${stats.average_content_length || 0} chars</span>
                        </div>
                        <div class="content-stat">
                            <span class="content-label">Total Characters:</span>
                            <span class="content-value">${stats.total_characters || 0}</span>
                        </div>
                    </div>
                </div>
                
                <div class="memory-types">
                    <h3>Memory Types</h3>
                    <div class="type-list">
                        ${this.renderMemoryTypes(stats.memory_types || {})}
                    </div>
                </div>
            </div>
        `;
    }
    
    // Helper methods
    createStatCard(icon, value, label, trend) {
        return `
            <div class="stat-card">
                <div class="stat-icon">${icon}</div>
                <div class="stat-value">${value}</div>
                <div class="stat-label">${label}</div>
                <div class="stat-trend">${trend}</div>
            </div>
        `;
    }
    
    renderLevelBars(levels) {
        const maxCount = Math.max(...Object.values(levels), 1);
        return Object.entries(levels).map(([level, count]) => `
            <div class="level-bar">
                <span class="level-label">${level.replace('_', ' ')}</span>
                <div class="bar-container">
                    <div class="bar-fill" style="width: ${(count / maxCount) * 100}%"></div>
                    <span class="bar-value">${count}</span>
                </div>
            </div>
        `).join('');
    }
    
    renderCategoryBars(categories) {
        const maxCount = Math.max(...Object.values(categories), 1);
        return Object.entries(categories).sort((a, b) => b[1] - a[1]).map(([category, count]) => `
            <div class="category-bar">
                <span class="category-label">${category}</span>
                <div class="bar-container">
                    <div class="bar-fill" style="width: ${(count / maxCount) * 100}%"></div>
                    <span class="bar-value">${count}</span>
                </div>
            </div>
        `).join('');
    }
    
    renderCategoryList(categories) {
        return Object.entries(categories).sort((a, b) => b[1] - a[1]).map(([category, count]) => `
            <div class="category-item">
                <span class="category-name">${category}</span>
                <span class="category-count">${count}</span>
            </div>
        `).join('');
    }
    
    renderMemoryTypes(types) {
        return Object.entries(types).sort((a, b) => b[1] - a[1]).map(([type, count]) => `
            <div class="memory-type-item">
                <span class="type-name">${type.replace(/_/g, ' ')}</span>
                <span class="type-count">${count}</span>
            </div>
        `).join('');
    }
    
    truncatePath(path, maxLength = 50) {
        if (path.length <= maxLength) return path;
        const start = path.substring(0, 20);
        const end = path.substring(path.length - 27);
        return `${start}...${end}`;
    }
    
    updateLastUpdated() {
        const element = document.getElementById('statsLastUpdated');
        if (element) {
            const now = new Date();
            element.textContent = `Updated: ${now.toLocaleTimeString()}`;
        }
    }
    
    async exportStatistics() {
        if (!this.statistics) {
            console.error('No statistics to export');
            return;
        }
        
        const dataStr = JSON.stringify(this.statistics, null, 2);
        const dataBlob = new Blob([dataStr], {type: 'application/json'});
        
        const link = document.createElement('a');
        link.href = URL.createObjectURL(dataBlob);
        link.download = `memoir-stats-${new Date().toISOString().split('T')[0]}.json`;
        link.click();
        
        // Clean up
        URL.revokeObjectURL(link.href);
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = StoreStatsModal;
}