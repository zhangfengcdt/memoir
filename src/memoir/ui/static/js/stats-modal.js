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
                    <button class="stats-tab" data-tab="codebase" id="statsTabCodebase" style="display: none;">Codebase</button>
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
            // Load stats and raw store data in parallel — the Codebase tab
            // needs the full key/value payload which /api/statistics doesn't
            // return.
            const [statsRes, storeRes] = await Promise.all([
                fetch(`/api/statistics?path=${encodeURIComponent(storePath)}`),
                fetch(`/api/store?path=${encodeURIComponent(storePath)}`),
            ]);
            const statsData = await statsRes.json();
            const storeData = storeRes.ok ? await storeRes.json() : null;

            if (statsData.success) {
                this.statistics = statsData.statistics;
                this.codebaseData = this.collectCodebaseData(storeData);
                this.updateCodebaseTabVisibility();
                this.updateLastUpdated();
                this.renderContent();
            } else {
                this.showError(statsData.error || 'Failed to load statistics');
            }
        } catch (error) {
            console.error('Error loading statistics:', error);
            this.showError('Failed to load statistics: ' + error.message);
        } finally {
            this.isLoading = false;
        }
    }

    // Scan /api/store memories for any namespace matching `codebase*`
    // (covers `codebase:onboard`, `codebase:tests`, plain `codebase`, etc.)
    // and group them the way SessionStart does: per-namespace, then per
    // top-level root (goal.*, structure.*, test.*, _meta.*, …).
    collectCodebaseData(storeData) {
        if (!storeData || !storeData.memories) return null;
        const groups = new Map();  // namespace -> { meta: {...}, roots: { root: [{key, content}] } }
        for (const m of storeData.memories) {
            const ns = m.namespace || '';
            if (!(ns === 'codebase' || ns.startsWith('codebase:') || ns.startsWith('codebase.'))) continue;
            if (!groups.has(ns)) groups.set(ns, { meta: {}, roots: {} });
            const g = groups.get(ns);
            const key = m.path || m.key || '';
            const content = (m.value && typeof m.value === 'object' && 'content' in m.value)
                ? (m.value.content || '')
                : (m.content || '');
            if (key.startsWith('_meta.')) {
                g.meta[key] = content;
            } else {
                const root = key.split('.', 1)[0] || '(other)';
                if (!g.roots[root]) g.roots[root] = [];
                g.roots[root].push({ key, content });
            }
        }
        if (groups.size === 0) return null;
        // Sort each root's keys alphabetically for a stable display.
        for (const g of groups.values()) {
            for (const root of Object.keys(g.roots)) {
                g.roots[root].sort((a, b) => a.key.localeCompare(b.key));
            }
        }
        return groups;
    }

    updateCodebaseTabVisibility() {
        const btn = document.getElementById('statsTabCodebase');
        if (!btn) return;
        if (this.codebaseData && this.codebaseData.size > 0) {
            btn.style.display = '';
        } else {
            btn.style.display = 'none';
            // If the user was on the codebase tab and the namespace went
            // away (unusual but possible after a /forget), fall back.
            if (this.currentTab === 'codebase') this.currentTab = 'overview';
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
            case 'codebase':
                this.renderCodebase();
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

    // Render the Codebase tab: show each `codebase:*` namespace exactly
    // the way SessionStart groups it (header meta + top-level roots), but
    // expand every key to its full stored value so the user can audit
    // what's being injected at session start.
    renderCodebase() {
        const content = document.getElementById('statsContent');
        if (!content) return;

        if (!this.codebaseData || this.codebaseData.size === 0) {
            content.innerHTML = `<div class="stats-error"><p>No <code>codebase:*</code> namespaces in this store.</p></div>`;
            return;
        }

        // SessionStart's preferred root order, with anything else appended
        // alphabetically at the end — matches render_codebase_onboard_compact
        // in plugins/claude-code/hooks/common.sh.
        const preferredRoots = ['goal', 'structure', 'test', 'debug', 'deploy', 'rules', 'lessons', 'references', 'document'];

        const namespaces = Array.from(this.codebaseData.entries()).sort(([a], [b]) => a.localeCompare(b));
        const blocks = namespaces.map(([ns, g]) => this.renderCodebaseNamespace(ns, g, preferredRoots)).join('');
        content.innerHTML = `<div class="stats-codebase">${blocks}</div>`;
    }

    renderCodebaseNamespace(namespace, group, preferredRoots) {
        const esc = (s) => this.escapeHtml(s);
        const meta = group.meta || {};
        const commit = (meta['_meta.last_onboard.commit'] || '').slice(0, 7) || '?';
        const dateIso = meta['_meta.last_onboard.date'] || '';
        const mode = meta['_meta.last_onboard.mode'] || '?';
        const ageStr = dateIso ? this.formatRelativeAge(dateIso) : '?';
        const stale = dateIso ? this.isOnboardStale(dateIso) : false;

        // Ordered list of roots: preferred first, then the rest alphabetically.
        const seen = new Set();
        const ordered = preferredRoots.filter(r => r in group.roots);
        ordered.forEach(r => seen.add(r));
        Object.keys(group.roots).sort().forEach(r => { if (!seen.has(r)) ordered.push(r); });

        const sections = ordered.map(root => {
            const rows = group.roots[root].map(({ key, content }) => `
                <div class="cb-row">
                    <div class="cb-key">${esc(key)}</div>
                    <div class="cb-value">${esc(content)}</div>
                </div>
            `).join('');
            return `
                <div class="cb-section">
                    <div class="cb-section-header">${esc(root)} <span class="cb-section-count">(${group.roots[root].length})</span></div>
                    <div class="cb-rows">${rows}</div>
                </div>
            `;
        }).join('');

        const metaKeys = Object.keys(meta).sort();
        const metaRows = metaKeys.length > 0
            ? metaKeys.map(k => `
                <div class="cb-row cb-meta-row">
                    <div class="cb-key">${esc(k)}</div>
                    <div class="cb-value">${esc(meta[k])}</div>
                </div>
            `).join('')
            : '';
        const metaSection = metaRows ? `
            <div class="cb-section cb-meta-section">
                <div class="cb-section-header">_meta <span class="cb-section-count">(${metaKeys.length})</span></div>
                <div class="cb-rows">${metaRows}</div>
            </div>
        ` : '';

        const staleBadge = stale ? `<span class="cb-badge cb-badge-stale">stale</span>` : '';
        const noContent = ordered.length === 0 && metaKeys.length === 0
            ? `<div class="stats-error"><p>Namespace <code>${esc(namespace)}</code> is empty.</p></div>`
            : '';

        return `
            <div class="cb-namespace">
                <div class="cb-namespace-header">
                    <div class="cb-namespace-title">
                        <span class="cb-ns-icon">📘</span>
                        <span class="cb-ns-name">${esc(namespace)}</span>
                        ${staleBadge}
                    </div>
                    <div class="cb-namespace-meta">
                        <span>last_onboard: <strong>${esc(ageStr)}</strong> @ <code>${esc(commit)}</code></span>
                        <span>mode: <code>${esc(mode)}</code></span>
                    </div>
                </div>
                ${noContent}
                ${sections}
                ${metaSection}
            </div>
        `;
    }

    escapeHtml(text) {
        if (text === null || text === undefined) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    formatRelativeAge(isoStr) {
        try {
            const dt = new Date(isoStr);
            const delta = Date.now() - dt.getTime();
            const days = Math.floor(delta / (24 * 3600 * 1000));
            if (days >= 1) return `${days}d ago`;
            const hours = Math.floor(delta / (3600 * 1000));
            if (hours >= 1) return `${hours}h ago`;
            return '<1h ago';
        } catch (e) { return '?'; }
    }

    isOnboardStale(isoStr) {
        try {
            const dt = new Date(isoStr);
            const days = (Date.now() - dt.getTime()) / (24 * 3600 * 1000);
            return days > 30;
        } catch (e) { return false; }
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
