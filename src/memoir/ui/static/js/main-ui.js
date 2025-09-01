        // Store connection state
        let connectedStorePath = null;
        let storeData = null;

        // Initialize statistics modal
        let storeStatsModal = null;

        // Command history
        let commandHistory = [];
        let historyIndex = -1;
        let currentInput = '';

        // Command handling
        async function handleCommand(command) {

            const parts = command.trim().split(' ');
            let cmd = parts[0].toLowerCase();

            // Command aliases mapping
            const aliases = {
                '/con': '/connect',
                '/conn': '/connect',
                '/rem': '/remember',
                '/forget': '/forget',
                '/del': '/forget',
                '/new': '/new',
                '/create': '/new',
                '/refresh': '/refresh',
                '/ref': '/refresh',
                '/help': '/help',
                '/h': '/help',
                '/clear': '/clear',
                '/cls': '/clear',
                '/br': '/branch',
                '/co': '/checkout',
                '/log': '/commits',
                '/tt': '/time-travel',
                '/tl': '/timeline',
                '/loc': '/location'
            };

            // Resolve alias to full command
            if (aliases[cmd]) {
                cmd = aliases[cmd];
            }




            if (cmd === '/connect') {
                const path = parts.slice(1).join(' ');
                if (!path) {
                    showNotification('Usage: /connect <path-to-memory-store>', 'error');
                    return;
                }
                await connectToStore(path);
            } else if (cmd === '/new') {
                const path = parts.slice(1).join(' ');
                if (!path) {
                    showNotification('Usage: /new <path>', 'error');
                    return;
                }
                await createNewStore(path);
            } else if (cmd === '/remember') {
                const content = parts.slice(1).join(' ');
                if (!content) {
                    showNotification('Usage: /remember <content>', 'error');
                    return;
                }
                await rememberContent(content);
            } else if (cmd === '/forget') {
                const key = parts.slice(1).join(' ');
                if (!key) {
                    showNotification('Usage: /forget <key>', 'error');
                    return;
                }
                await forgetMemory(key);
            } else if (cmd === '/refresh') {
                if (!connectedStorePath) {
                    showNotification('Not connected. Use /connect <path> first', 'error');
                    return;
                }
                await refreshStore();
            } else if (cmd === '/demo') {
                showDemoData();
            } else if (cmd === '/repo') {
                showRepoInfo();
            } else if (cmd === '/code') {
                showIntegrationCode();
            } else if (cmd === '/proof') {
                const memoryPath = parts.slice(1).join(' ').trim();
                if (!memoryPath) {
                    showNotification('Usage: /proof <memory-path>', 'error');
                } else {
                    generateProof(memoryPath);
                }
            } else if (cmd === '/verify') {
                const proofData = parts.slice(1).join(' ').trim();
                if (proofData) {
                    // User provided proof data - try to parse it
                    showVerifyWithInput(proofData);
                } else {
                    // No input - use last generated proof or show input dialog
                    showVerifyUI();
                }
            } else if (cmd === '/blame') {
                const key = parts.slice(1).join(' ').trim();
                if (!key) {
                    showNotification('Usage: /blame <key>', 'error');
                    return;
                }
                await showBlameInfo(key);
            } else if (cmd === '/time-travel') {
                const target = parts.slice(1).join(' ').trim();
                if (!target) {
                    showNotification('Usage: /time-travel <commit-hash or date>', 'error');
                    return;
                }
                await timeTravel(target);
            } else if (cmd === '/branch') {
                const subCmd = parts[1];
                const args = parts.slice(2).join(' ').trim();
                await handleBranchCommand(subCmd, args);
            } else if (cmd === '/checkout') {
                const target = parts.slice(1).join(' ').trim();
                if (!target) {
                    showNotification('Usage: /checkout <branch-name>', 'error');
                    return;
                }
                await checkoutBranch(target);
            } else if (cmd === '/merge') {
                const source = parts.slice(1).join(' ').trim();
                if (!source) {
                    showNotification('Usage: /merge <source-branch>', 'error');
                    return;
                }
                await mergeBranch(source);
            } else if (cmd === '/commits' || cmd === '/log') {
                await showCommitHistory();
            } else if (cmd === '/branches') {
                await showBranchList();
            } else if (cmd === '/timeline') {
                if (parts.length === 1) {
                    // Show timeline
                    await showTimeline();
                } else {
                    // Add timeline event: /timeline YYYY-MM-DD description
                    const args = parts.slice(1).join(' ');
                    await addTimelineEvent(args);
                }
            } else if (cmd === '/location') {
                if (parts.length === 1) {
                    // Show places popup
                    await showPlacesPopup();
                } else {
                    // Add location event: /location <place> <description>
                    const args = parts.slice(1).join(' ');
                    await addLocationEvent(args);
                }
            } else if (cmd === '/debug-timeline') {
                await debugTimeline();
            } else if (cmd === '/refresh-timeline') {
                await updateTimelineView();
                showNotification('Timeline view refreshed', 'success');
            } else if (cmd === '/inspect-dom') {
                inspectCurrentDOM();
            } else if (cmd === '/force-timeline') {
                await forceTimelineView();
            } else if (cmd === '/check-styles') {
                checkTimelineStyles();
            } else if (cmd === '/restore-layout') {
                restoreNormalLayout();
            } else if (cmd === '/summarize') {
                if (parts.length > 1 && parts[1].toLowerCase() === 'keys') {
                    // Handle /summarize keys <pattern>
                    const keyPattern = parts.length > 2 ? parts[2] : '';
                    if (!keyPattern) {
                        showNotification('Usage: /summarize keys <pattern> (e.g., /summarize keys profile.personal.*)', 'error');
                        return;
                    }
                    // Store pattern globally for API to access
                    window.keyPattern = keyPattern;
                    await summarizeMemoryStore('keys');
                } else {
                    // Handle regular /summarize [type]
                    const summaryType = parts.length > 1 ? parts[1].toLowerCase() : 'all';
                    await summarizeMemoryStore(summaryType);
                }
            } else if (cmd === '/recall' || cmd === '/search') {
                let query, person;
                const args = parts.slice(1).join(' ');

                // Check if person parameter is specified: /recall (person) query
                const personMatch = args.match(/^\(([^)]+)\)\s*(.*)$/);
                if (personMatch) {
                    person = personMatch[1].trim();
                    query = personMatch[2].trim();
                } else {
                    query = args;
                }

                if (!query) {
                    showNotification('Usage: /recall <query> or /recall (person) <query>\nExamples:\n/recall user preferences about colors\n/recall (john) career goals', 'error');
                } else {
                    await recallMemories(query, person);
                }
            } else if (cmd === '/diff' || cmd === '/d') {
                const arg1 = parts[1];
                const arg2 = parts[2];

                if (arg1 === 'mock') {
                    // Mode 1: /diff mock - show mocked UI
                    await showDiffModal(arg2, parts[3], true);  // true for mock mode
                } else if (arg1 && arg2) {
                    // Mode 3: /diff commit1 commit2 - show diff between two commits
                    await showDiffModal(arg1, arg2, false);
                } else {
                    // Mode 2: /diff without parameters - show current vs last commit
                    await showDiffModal(null, null, false);
                }
            } else if (cmd === '/debug-store') {
                // Quick debug command to check store contents
                if (!connectedStorePath) {
                    showNotification('Not connected to any store', 'error');
                    return;
                }





                // Make a direct API call to list all memories
                try {
                    const response = await fetch(`/api/store?path=${encodeURIComponent(connectedStorePath)}`);
                    const result = await response.json();


                    showNotification(`Debug: ${connectedStorePath} - Check console for details`, 'info');
                } catch (error) {
                    console.error('Store debug error:', error);
                    showNotification('Store debug failed - check console', 'error');
                }

            // Developer & Debugging Commands
            } else if (cmd === '/inspect') {
                const path = parts.slice(1).join(' ');
                if (!path) {
                    showNotification('Usage: /inspect <path>\nExample: /inspect profile.professional.skills', 'error');
                } else {
                    await handleInspectCommand(path);
                }
            } else if (cmd === '/benchmark') {
                await handleBenchmarkCommand();
            } else if (cmd === '/export') {
                const format = parts.length > 1 ? parts[1].toLowerCase() : 'json';
                await handleExportCommand(format);
            } else if (cmd === '/compare-stores') {
                if (parts.length < 3) {
                    showNotification('Usage: /compare-stores <path1> <path2>\nExample: /compare-stores /tmp/store1 /tmp/store2', 'error');
                } else {
                    const [, path1, path2] = parts;
                    await handleCompareStoresCommand(path1, path2);
                }
            } else if (cmd === '/replay') {
                const sessionId = parts.slice(1).join(' ');
                if (!sessionId) {
                    showNotification('Usage: /replay <session>\nExample: /replay session-123', 'error');
                } else {
                    await handleReplayCommand(sessionId);
                }
            } else if (cmd === '/import') {
                const filePath = parts.slice(1).join(' ');
                if (!filePath) {
                    showNotification('Usage: /import <file_path>\nExample: /import /path/to/conversation.json\nSupported formats: JSON, TXT', 'error');
                } else {
                    showNotification(`Importing conversations from "${filePath}" coming soon. This will ingest and process conversation history into the memory store.`, 'info');
                }
            } else if (cmd === '/eval') {
                const input = parts.slice(1).join(' ');
                if (!input) {
                    showNotification('Usage: /eval <question_or_file>\nExample: /eval "What is the user\'s favorite color?"\nExample: /eval /path/to/questions.txt', 'error');
                } else {
                    showNotification(`Evaluating recall for "${input}" coming soon. This will test memory recall hit rate and answer quality.`, 'info');
                }
            } else if (cmd === '/organize') {
                const path = parts.slice(1).join(' ');
                if (!path) {
                    showNotification('Usage: /organize <path>\nExample: /organize profile.career', 'error');
                } else {
                    showNotification(`Organizing memories under "${path}" coming soon. This will restructure and optimize the taxonomy for better organization.`, 'info');
                }
            } else if (cmd === '/template') {
                const templateType = parts.slice(1).join(' ');
                if (!templateType) {
                    showNotification('Usage: /template <type>\nAvailable types: langchain, langgraph, basic, advanced', 'error');
                } else {
                    await handleTemplateCommand(templateType);
                }
            } else if (cmd === '/help') {
                showHelpModal();
            } else {
                // Check if input starts with "/" (indicating it's an unknown command)
                if (command.trim().startsWith('/')) {
                    // Check if it's a placeholder command
                    const placeholderCmd = availableCommands.find(c => c.cmd === cmd && c.placeholder);
                    if (placeholderCmd) {
                        showNotification(`${placeholderCmd.cmd} - ${placeholderCmd.desc}`, 'info', 4000);
                    } else {
                        showNotification(`Unknown command: ${cmd}`, 'error');
                    }
                } else {
                    // Input doesn't start with "/" - treat it as a natural language query
                    // Default to recall functionality

                    let query, person;
                    const input = command.trim();

                    // Check if person parameter is specified: (person) query
                    const personMatch = input.match(/^\(([^)]+)\)\s*(.*)$/);
                    if (personMatch) {
                        person = personMatch[1].trim();
                        query = personMatch[2].trim();
                    } else {
                        query = input;
                    }

                    if (query) {
                        await recallMemories(query, person);
                    } else {
                        showNotification('Please enter a question or search query', 'error');
                    }
                }
            }
        }

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
            updateBranchesDropdown(['main', 'feature/context-memory', 'feature/ui-improvements', 'experimental/ml-optimization'], 'main');

            // Restore original git history
            restoreOriginalGitHistory();

            // Update graph view to original state
            updateGraphView();
        }

        function restoreOriginalGitHistory() {
            const gitHistory = document.querySelector('.git-tree');
            if (!gitHistory) return;

            // Update panel header to show "Git History" mode
            updateTimelinePanelHeader('Git History');

            // Restore the complete original git history HTML
            const originalGitHTML = `
                <!-- Week 1 - Recent commits -->
                <div class="commit-node active" data-commit="f9a8b12">
                    <div class="git-lines"><div class="commit-dot tag"></div><div class="git-tag">v2.3.1</div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">f9a8b12</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">fix: Resolve memory leak in taxonomy caching</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">AS</div><span>Alice Smith</span></div><div class="commit-time">2h ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="d75e832">
                    <div class="git-lines"><div class="commit-dot main"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">d75e832</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">feat: Add intelligent memory classification</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">JD</div><span>John Doe</span></div><div class="commit-time">4h ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="e2c4f89">
                    <div class="git-lines"><div class="commit-dot merge"></div><div class="git-line merge-curve feature"></div><div class="git-line branch-vertical merge-down"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">e2c4f89</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">Merge branch 'feature/batch-processing'</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">JD</div><span>John Doe</span></div><div class="commit-time">8h ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="b3a7c91">
                    <div class="git-lines"><div class="commit-dot branch"></div><div class="git-line branch-vertical branch-commit"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">b3a7c91</div><div class="branch-tag">feature/batch-processing</div></div>
                        <div class="commit-message">perf: Implement batch memory operations</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">AS</div><span>Alice Smith</span></div><div class="commit-time">12h ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="c3f7921">
                    <div class="git-lines"><div class="commit-dot main"></div><div class="git-line branch-curve feature"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">c3f7921</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">refactor: Optimize search engine performance</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">MB</div><span>Mike Brown</span></div><div class="commit-time">1d ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="a9e5d21">
                    <div class="git-lines"><div class="commit-dot main"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">a9e5d21</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">feat: Add memory confidence scoring</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">JD</div><span>John Doe</span></div><div class="commit-time">1d ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="b92f381">
                    <div class="git-lines"><div class="commit-dot tag"></div><div class="git-tag">v2.3.0</div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">b92f381</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">feat: Modern glassmorphism UI design</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">AS</div><span>Alice Smith</span></div><div class="commit-time">2d ago</div></div>
                    </div>
                </div>

                <!-- Week 2 - Previous week -->
                <div class="commit-node" data-commit="7f2a8b3">
                    <div class="git-lines"><div class="commit-dot merge"></div><div class="git-line merge-curve feature"></div><div class="git-line branch-vertical merge-down"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">7f2a8b3</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">Merge branch 'feature/async-processing'</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">MB</div><span>Mike Brown</span></div><div class="commit-time">3d ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="6e1b4c7">
                    <div class="git-lines"><div class="commit-dot branch"></div><div class="git-line branch-vertical branch-commit"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">6e1b4c7</div><div class="branch-tag">feature/async-processing</div></div>
                        <div class="commit-message">feat: Add async memory operations</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">AS</div><span>Alice Smith</span></div><div class="commit-time">4d ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="a4f7f14">
                    <div class="git-lines"><div class="commit-dot main"></div><div class="git-line branch-curve feature"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">a4f7f14</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">refactor: Improve memory store performance</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">JD</div><span>John Doe</span></div><div class="commit-time">4d ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="3d9c2e8">
                    <div class="git-lines"><div class="commit-dot main"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">3d9c2e8</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">docs: Update API documentation</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">MB</div><span>Mike Brown</span></div><div class="commit-time">5d ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="8e1c492">
                    <div class="git-lines"><div class="commit-dot tag"></div><div class="git-tag">v2.2.0</div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">8e1c492</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">feat: Git-like versioning for AI memory</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">JD</div><span>John Doe</span></div><div class="commit-time">6d ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="5a8f3b1">
                    <div class="git-lines"><div class="commit-dot main"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">5a8f3b1</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">fix: Handle edge cases in memory retrieval</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">AS</div><span>Alice Smith</span></div><div class="commit-time">1w ago</div></div>
                    </div>
                </div>

                <!-- Week 3-4 - Older commits -->
                <div class="commit-node" data-commit="2b7e4a9">
                    <div class="git-lines"><div class="commit-dot merge"></div><div class="git-line merge-curve hotfix"></div><div class="git-line branch-vertical merge-down"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">2b7e4a9</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">Merge branch 'feature/search-improvements'</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">MB</div><span>Mike Brown</span></div><div class="commit-time">1w ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="9c4d1f8">
                    <div class="git-lines"><div class="commit-dot branch"></div><div class="git-line branch-vertical branch-commit"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">9c4d1f8</div><div class="branch-tag">feature/search-improvements</div></div>
                        <div class="commit-message">feat: Enhanced semantic search capabilities</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">JD</div><span>John Doe</span></div><div class="commit-time">1w ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="f3e8a72">
                    <div class="git-lines"><div class="commit-dot main"></div><div class="git-line branch-curve release"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">f3e8a72</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">test: Add comprehensive unit tests</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">AS</div><span>Alice Smith</span></div><div class="commit-time">1w ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="35be3ae">
                    <div class="git-lines"><div class="commit-dot tag"></div><div class="git-tag">v2.1.0</div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">35be3ae</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">feat: Add comprehensive API documentation</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">MB</div><span>Mike Brown</span></div><div class="commit-time">2w ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="1a5c9d4">
                    <div class="git-lines"><div class="commit-dot main"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">1a5c9d4</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">refactor: Clean up legacy code paths</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">JD</div><span>John Doe</span></div><div class="commit-time">2w ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="8b2f6e3">
                    <div class="git-lines"><div class="commit-dot main"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">8b2f6e3</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">feat: Implement memory compression</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">AS</div><span>Alice Smith</span></div><div class="commit-time">2w ago</div></div>
                    </div>
                </div>

                <!-- Month 2 - Earlier development -->
                <div class="commit-node" data-commit="4d7a3c1">
                    <div class="git-lines"><div class="commit-dot merge"></div><div class="git-line merge-curve release"></div><div class="git-line branch-vertical merge-down"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">4d7a3c1</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">Merge branch 'feature/taxonomy-system'</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">MB</div><span>Mike Brown</span></div><div class="commit-time">3w ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="6f8e2b9">
                    <div class="git-lines"><div class="commit-dot branch"></div><div class="git-line branch-vertical branch-commit"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">6f8e2b9</div><div class="branch-tag">feature/taxonomy-system</div></div>
                        <div class="commit-message">feat: Dynamic taxonomy expansion</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">JD</div><span>John Doe</span></div><div class="commit-time">3w ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="9e4b7a2">
                    <div class="git-lines"><div class="commit-dot main"></div><div class="git-line branch-curve develop"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">9e4b7a2</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">feat: Core taxonomy implementation</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">AS</div><span>Alice Smith</span></div><div class="commit-time">3w ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="2c1e5f7">
                    <div class="git-lines"><div class="commit-dot tag"></div><div class="git-tag">v2.0.0</div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">2c1e5f7</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">feat: Major architecture overhaul</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">MB</div><span>Mike Brown</span></div><div class="commit-time">1mo ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="7a3d8c4">
                    <div class="git-lines"><div class="commit-dot main"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">7a3d8c4</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">refactor: Modularize classifier system</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">JD</div><span>John Doe</span></div><div class="commit-time">1mo ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="5b9f2e1">
                    <div class="git-lines"><div class="commit-dot main"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">5b9f2e1</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">feat: Add memory indexing system</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">AS</div><span>Alice Smith</span></div><div class="commit-time">1mo ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="8c4a6f3">
                    <div class="git-lines"><div class="commit-dot tag"></div><div class="git-tag">v1.5.0</div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">8c4a6f3</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">feat: Implement prolly tree storage</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">MB</div><span>Mike Brown</span></div><div class="commit-time">1mo ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="3f7b1a8">
                    <div class="git-lines"><div class="commit-dot main"></div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">3f7b1a8</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">docs: Add getting started guide</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">JD</div><span>John Doe</span></div><div class="commit-time">1mo ago</div></div>
                    </div>
                </div>

                <div class="commit-node" data-commit="00c5625">
                    <div class="git-lines"><div class="commit-dot tag"></div><div class="git-tag">v1.0.0</div></div>
                    <div class="commit-info">
                        <div class="commit-header"><div class="commit-hash">00c5625</div><div class="branch-tag">main</div></div>
                        <div class="commit-message">feat: Initial release - Core memory system</div>
                        <div class="commit-meta"><div class="commit-author"><div class="author-avatar">JD</div><span>John Doe</span></div><div class="commit-time">2mo ago</div></div>
                    </div>
                </div>
            `;

            gitHistory.innerHTML = originalGitHTML;
        }

        function updateBranchesDropdown(branches, currentBranch) {
            const branchSelector = document.getElementById('branchSelector');
            if (!branchSelector) return;

            // Clear existing options
            branchSelector.innerHTML = '';

            // Add branch options
            branches.forEach(branch => {
                const option = document.createElement('option');
                option.value = branch;
                option.textContent = branch;
                if (branch === currentBranch) {
                    option.selected = true;
                }
                branchSelector.appendChild(option);
            });
        }

        function restoreOriginalTreeView() {
            const treeView = document.getElementById('treeView');
            if (!treeView) return;

            // Use the dynamic tree builder with demo data instead of static HTML
            const demoTree = generateMockTree(1.0);
            treeView.innerHTML = buildTreeFromPaths(demoTree);
            return;
        }

        function showRepoInfo() {


            if (!connectedStorePath) {
                showNotification('No repository connected. Use /connect <path> or /demo first.', 'error');
                return;
            }

            if (!storeData) {
                showNotification('No data available. Try /refresh to reload.', 'error');
                return;
            }

            // Calculate repository statistics
            const totalMemories = storeData.total_memories || storeData.memories?.length || 0;
            const totalBranches = storeData.branches?.length || 0;
            const totalCommits = storeData.commits?.length || 0;
            const currentBranch = storeData.current_branch || 'unknown';

            // Count unique paths and namespaces
            const uniquePaths = new Set();
            const uniqueNamespaces = new Set();

            if (storeData.memories) {
                storeData.memories.forEach(memory => {
                    if (memory.path) uniquePaths.add(memory.path);
                    if (memory.namespace) uniqueNamespaces.add(memory.namespace);
                });
            }

            // Count tree levels
            let maxDepth = 0;
            if (storeData.tree) {
                Object.keys(storeData.tree).forEach(path => {
                    const depth = path.split('.').length;
                    if (depth > maxDepth) maxDepth = depth;
                });
            }

            // Format the repository info
            const repoInfo = `📊 Repository Information

🗂️  Store Path: ${connectedStorePath}
🌟 Current Branch: ${currentBranch}
🌿 Total Branches: ${totalBranches}
📝 Total Commits: ${totalCommits}
🧠 Total Memories: ${totalMemories}
🏷️  Unique Paths: ${uniquePaths.size}
👤 Namespaces: ${uniqueNamespaces.size}
📊 Max Tree Depth: ${maxDepth}

Branches: ${storeData.branches ? storeData.branches.join(', ') : 'none'}

Recent Commits:
${storeData.commits ? storeData.commits.slice(0, 5).map(c => `• ${c.hash}: ${c.message}`).join('\n') : 'No commits available'}`;

            // Show the info in a notification with longer display time
            showNotification(repoInfo, 'info', 10000); // 10 second display
        }

        function showIntegrationCode() {


            // Use the actual connected path or provide helpful default
            const storePath = connectedStorePath && connectedStorePath !== 'demo'
                ? connectedStorePath
                : '"/tmp/memoir_ui_store"  # Use your actual store path';

            const integrationCode = `

# Create components
taxonomy = SemanticTaxonomy()
llm = ChatOpenAI(model="gpt-4", temperature=0.1)
classifier = IntelligentClassifier(
    taxonomy=taxonomy,
    llm=llm
)

# Initialize store with versioning
prolly_store = ProllyTreeStore(
    path="${storePath}",
    enable_versioning=True,
    auto_commit=True
)

# Create memory manager
memory_manager = ProllyTreeMemoryStoreManager(
    prolly_store=prolly_store,
    classifier=classifier,
    enable_versioning=True,
    auto_commit=True
)

# LangGraph Integration
langgraph_store = LangGraphMemoryStore(
    memory_manager=memory_manager,
    namespace=("conversation_123",)
)

# Use with LangGraph agents
config = {"configurable": {"store": langgraph_store}}`;

            // Show code in a modal-like notification
            showCodeModal(integrationCode);
        }

        async function generateProof(memoryPath) {
            if (!connectedStorePath) {
                showNotification('Please connect to a store first with /connect <path>', 'error');
                return;
            }

            showNotification(`Generating proof for: ${memoryPath}...`, 'info');

            try {
                const response = await fetch(`/api/proof?path=${encodeURIComponent(connectedStorePath)}&key=${encodeURIComponent(memoryPath)}&namespace=default`);
                const result = await response.json();

                if (result.success) {
                    // Store the last proof for easy verification
                    window.lastProof = result;

                    // Show proof in modal
                    const proofDisplay = `
🔐 Cryptographic Proof Generated
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Memory Path: ${result.key}
Namespace: ${result.namespace}
Proof Size: ${result.proof_size} bytes

Proof (Base64):
${result.proof}

Current Value:
${JSON.stringify(result.value, null, 2)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

To verify this proof:
• Quick verify (uses cached data): /verify
• Manual verify (copy this command):
  /verify ${result.proof} ${result.key}

• Share as JSON:
  ${JSON.stringify({proof: result.proof, key: result.key, namespace: result.namespace})}

💡 Tip: The manual verify command above is ready to copy-paste!
                    `;
                    showCodeModal(proofDisplay);
                    showNotification('Proof generated successfully! ✓', 'success');
                } else {
                    showNotification(`Error: ${result.error}`, 'error');
                }
            } catch (error) {
                showNotification(`Failed to generate proof: ${error.message}`, 'error');
            }
        }

        function showVerifyUI() {
            if (!window.lastProof) {
                // Show instructions for manual verification
                const helpText = `
📝 Proof Verification Options
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

No cached proof found. You can:

1. Generate a proof first:
   /proof <memory-path>

2. Verify a proof manually:
   /verify <proof-base64> <memory-key>

3. Paste a proof JSON:
   /verify {"proof":"...", "key":"...", "namespace":"..."}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The verify command uses the last generated proof by default,
or you can provide proof data manually for verification.
                `;
                showCodeModal(helpText);
                return;
            }

            // Use cached proof from last generation
            showNotification(`Verifying last generated proof for: ${window.lastProof.key}`, 'info');
            verifyProof(window.lastProof.proof, window.lastProof.key, window.lastProof.namespace);
        }

        function showVerifyWithInput(proofData) {
            try {
                // Try to parse as JSON first
                if (proofData.startsWith('{')) {
                    const parsed = JSON.parse(proofData);
                    if (parsed.proof && parsed.key) {
                        verifyProof(parsed.proof, parsed.key, parsed.namespace || 'default');
                        return;
                    }
                }

                // Otherwise treat as space-separated: proof key [namespace]
                const parts = proofData.split(' ');
                if (parts.length >= 2) {
                    const [proof, key, namespace = 'default'] = parts;
                    verifyProof(proof, key, namespace);
                } else {
                    showNotification('Invalid format. Use: /verify <proof> <key> [namespace]', 'error');
                }
            } catch (error) {
                showNotification(`Failed to parse proof data: ${error.message}`, 'error');
            }
        }

        async function verifyProof(proofB64, memoryKey, namespace = 'default') {
            if (!connectedStorePath) {
                showNotification('Please connect to a store first with /connect <path>', 'error');
                return;
            }

            showNotification('Verifying proof...', 'info');

            try {
                const response = await fetch(`/api/verify?path=${encodeURIComponent(connectedStorePath)}&proof=${encodeURIComponent(proofB64)}&key=${encodeURIComponent(memoryKey)}&namespace=${namespace}`);
                const result = await response.json();

                if (result.success) {
                    const verifyDisplay = `
🔍 Proof Verification Result
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Memory Path: ${result.key}
Namespace: ${result.namespace}

Verification: ${result.valid ? '✅ VALID' : '❌ INVALID'}
${result.message}

Current Value:
${JSON.stringify(result.current_value, null, 2)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

${result.valid ?
'This proof cryptographically verifies that the memory exists\nand has not been tampered with.' :
'This proof could not be verified. The memory may have been\nmodified or the proof may be corrupted.'}
                    `;
                    showCodeModal(verifyDisplay);

                    if (result.valid) {
                        showNotification('Proof verified successfully! ✅', 'success');
                    } else {
                        showNotification('Proof verification failed! ❌', 'error');
                    }
                } else {
                    showNotification(`Error: ${result.error}`, 'error');
                }
            } catch (error) {
                showNotification(`Failed to verify proof: ${error.message}`, 'error');
            }
        }

        function showCodeModal(code) {
            // Create a modal overlay
            const modal = document.createElement('div');
            modal.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.8);
                z-index: 10001;
                display: flex;
                align-items: center;
                justify-content: center;
                backdrop-filter: blur(4px);
            `;

            const modalContent = document.createElement('div');
            modalContent.style.cssText = `
                background: #0d1117;
                color: #f1f5f9;
                border-radius: 12px;
                padding: 24px;
                max-width: 900px;
                max-height: 80vh;
                overflow-y: auto;
                font-family: 'JetBrains Mono', monospace;
                font-size: 14px;
                line-height: 1.6;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
                border: 1px solid rgba(48, 54, 61, 0.5);
            `;

            const closeButton = document.createElement('button');
            closeButton.innerHTML = '✕';
            closeButton.style.cssText = `
                position: absolute;
                top: 16px;
                right: 20px;
                background: transparent;
                border: none;
                color: #94a3b8;
                font-size: 18px;
                cursor: pointer;
                padding: 4px;
                border-radius: 4px;
                transition: all 0.2s;
            `;

            closeButton.addEventListener('mouseenter', () => {
                closeButton.style.background = 'rgba(239, 68, 68, 0.1)';
                closeButton.style.color = '#ef4444';
            });

            closeButton.addEventListener('mouseleave', () => {
                closeButton.style.background = 'transparent';
                closeButton.style.color = '#94a3b8';
            });

            const copyButton = document.createElement('button');
            copyButton.innerHTML = '📋';
            copyButton.title = 'Copy code to clipboard';
            copyButton.style.cssText = `
                position: absolute;
                top: 16px;
                right: 60px;
                background: transparent;
                border: none;
                color: #94a3b8;
                font-size: 16px;
                cursor: pointer;
                padding: 4px 8px;
                border-radius: 4px;
                transition: all 0.2s;
            `;

            copyButton.addEventListener('mouseenter', () => {
                copyButton.style.background = 'rgba(34, 197, 94, 0.1)';
                copyButton.style.color = '#22c55e';
            });

            copyButton.addEventListener('mouseleave', () => {
                copyButton.style.background = 'transparent';
                copyButton.style.color = '#94a3b8';
            });

            copyButton.addEventListener('click', async () => {
                try {
                    await navigator.clipboard.writeText(code);
                    copyButton.innerHTML = '✅';
                    copyButton.style.color = '#22c55e';
                    setTimeout(() => {
                        copyButton.innerHTML = '📋';
                        copyButton.style.color = '#94a3b8';
                    }, 2000);
                    showNotification('Code copied to clipboard!', 'success');
                } catch (err) {
                    console.error('Failed to copy code:', err);
                    showNotification('Failed to copy code', 'error');
                }
            });

            modalContent.style.position = 'relative';
            modalContent.appendChild(closeButton);
            modalContent.appendChild(copyButton);

            // Create a pre/code element for syntax highlighting
            const preElement = document.createElement('pre');
            const codeElement = document.createElement('code');
            codeElement.className = 'language-python';
            codeElement.textContent = code;

            // Apply syntax highlighting
            hljs.highlightElement(codeElement);

            preElement.appendChild(codeElement);
            preElement.style.cssText = `
                margin: 0;
                padding: 0;
                background: transparent;
                overflow-x: auto;
                margin-right: 20px;
            `;

            modalContent.appendChild(preElement);

            modal.appendChild(modalContent);
            document.body.appendChild(modal);

            // Close handlers
            const closeModal = () => modal.remove();
            closeButton.addEventListener('click', closeModal);
            modal.addEventListener('click', (e) => {
                if (e.target === modal) closeModal();
            });

            // ESC key handler
            const handleKeydown = (e) => {
                if (e.key === 'Escape') {
                    closeModal();
                    document.removeEventListener('keydown', handleKeydown);
                }
            };
            document.addEventListener('keydown', handleKeydown);
        }

        function updateStorePathDisplay(path = null, status = 'disconnected') {
            const storePathText = document.getElementById('storePathText');
            const connectionBtn = document.getElementById('connectionStatusBtn');
            const refreshBtn = document.getElementById('refreshBtn');

            if (!storePathText) return;

            // Update path text
            if (path) {
                storePathText.textContent = path;
                storePathText.title = path; // Add tooltip for long paths
            } else {
                storePathText.textContent = 'Not connected - demo mode';
                storePathText.title = 'No store connected - viewing demo data';
            }

            // Update text color based on connection status
            storePathText.className = `store-path-text ${status}`;

            // Show/hide connection status button based on status
            if (connectionBtn) {
                if (status === 'connected') {
                    connectionBtn.classList.add('show');
                } else {
                    connectionBtn.classList.remove('show');
                }
            }

            // Show/hide refresh button based on connection status (if it exists)
            if (refreshBtn) {
                if (status === 'connected') {
                    refreshBtn.classList.add('show');
                } else {
                    refreshBtn.classList.remove('show');
                }
            }
        }

        async function connectToStore(path, silent = false) {

            updateStorePathDisplay(path, 'connecting');
            if (!silent) {
                showNotification(`Connecting to ${path}...`, 'info');
            }

            try {
                // First try the API endpoint
                let response;
                let data = null;

                // Try API endpoint (works when served via HTTP server)
                try {
                    const apiUrl = `/api/store?path=${encodeURIComponent(path)}`;

                    response = await fetch(apiUrl);


                    if (response.ok) {
                        data = await response.json();

                        connectedStorePath = path;
                        storeData = data;

                        // Clear the new empty store flag when connecting to existing data
                        window.isNewEmptyStore = false;

                        updateStorePathDisplay(path, 'connected');
                        if (!silent) {
                            showNotification(`Successfully connected to ${path}`, 'success');
                        }
                        await updateUIWithRealData(data);
                        // Update branch display and git history for connected store
                        await updateBranchDisplay();
                        return;
                    } else {
                        console.error('API returned error:', response.status, response.statusText);
                    }
                } catch (e) {
                    console.error('API fetch error:', e);

                }

                // Try to read the metadata file directly (for file:// protocol)
                try {
                    response = await fetch(`file://${path}/ui_metadata.json`);
                    if (response.ok) {
                        data = await response.json();
                        connectedStorePath = path;
                        storeData = data;
                        updateStorePathDisplay(path, 'connected');
                        if (!silent) {
                            showNotification(`Connected to ${path} (file mode)`, 'success');
                        }
                        await updateUIWithRealData(data);
                        // Update branch display and git history for connected store
                        await updateBranchDisplay();
                        return;
                    }
                } catch (e) {

                }

                // If both methods fail, show an error instead of falling back
                updateStorePathDisplay(null, 'disconnected');
                if (!silent) {
                    showNotification(`Failed to connect to ${path}. Path may not exist or store may be empty. Try:\n1. Check if path exists\n2. Run initialization script\n3. Use HTTP server (python server.py)`, 'error');
                }
                return;
            } catch (error) {
                console.error('Connection error:', error);
                updateStorePathDisplay(null, 'disconnected');
                if (!silent) {
                    showNotification(`Connection failed: ${error.message}`, 'error');
                }
            }
        }

        function clearUIViews() {


            // Clear global data
            storeData = null;
            connectedStorePath = null;

            // Clear tree view
            const treeView = document.getElementById('treeView');
            if (treeView) {
                treeView.innerHTML = `
                    <div class="tree-node">
                        <div class="node-content">
                            <span class="node-icon">📁</span>
                            <span class="node-label">Empty memory store</span>
                        </div>
                        <div class="node-children">
                            <div class="tree-node">
                                <div class="node-content">
                                    <span class="node-icon">💭</span>
                                    <span class="node-label">Use /remember to add your first memory</span>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            }

            // Clear graph view (D3.js)
            d3.select('#graphSvg').selectAll('*').remove();

            // Also clear any cached graph data
            window.realStoreData = null;

            // Set flag to indicate this is a new empty store
            window.isNewEmptyStore = true;

            // Clear branches dropdown
            const branchSelector = document.querySelector('#branchSelector');
            if (branchSelector) {
                branchSelector.innerHTML = '<option value="main">main</option>';
            }

            // Clear git timeline
            const gitHistory = document.querySelector('.git-tree');
            if (gitHistory) {
                gitHistory.innerHTML = `
                    <div class="commit-node">
                        <div class="git-lines">
                            <div class="commit-dot main"></div>
                        </div>
                        <div class="commit-content">
                            <div class="commit-message">Initial commit</div>
                            <div class="commit-meta">New memory store created</div>
                        </div>
                    </div>
                `;
            }

            // Clear status
            const statusEl = document.getElementById('connectionStatus');
            if (statusEl) {
                statusEl.innerHTML = `<span style="margin-right: 5px;">📁</span> New empty store`;
            }
        }

        async function createNewStore(path) {
            // Provide helpful suggestions if path looks problematic
            if (path === '/temp' || path === '/tmp') {
                path = '/tmp/memoir_store_' + Date.now();
                showNotification(`Using writable path: ${path}`, 'info');
            } else if (path.startsWith('/temp/')) {
                path = path.replace('/temp/', '/tmp/');
                showNotification(`Corrected path to: ${path}`, 'info');
            }



            // Clear UI immediately to show it's a new store
            clearUIViews();
            showNotification(`Creating new memory store at ${path}...`, 'info');

            try {
                const response = await fetch('/api/new', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ path })
                });

                const result = await response.json();

                if (response.ok && result.success) {
                    showNotification(`✓ Memory store created at ${path}`, 'success');
                    // Set the connected path but don't load data (since it's empty)
                    connectedStorePath = path;

                    // Ensure flag is set for new empty store
                    window.isNewEmptyStore = true;

                    // Update store path display
                    updateStorePathDisplay(path, 'connected');

                    // Update status to show we're connected to the new store
                    const statusEl = document.getElementById('connectionStatus');
                    if (statusEl) {
                        statusEl.innerHTML = `<span style="margin-right: 5px;">📁</span> Connected: ${path}`;
                    }
                } else {
                    const errorMsg = result.message || `HTTP error! status: ${response.status}`;
                    updateStorePathDisplay(null, 'disconnected');
                    showNotification(`Failed to create store: ${errorMsg}`, 'error');

                    // Suggest alternative paths
                    if (errorMsg.includes('Permission denied') || errorMsg.includes('Read-only')) {
                        const suggestedPath = `/tmp/memoir_store_${Date.now()}`;
                        showNotification(`💡 Try a writable path like: ${suggestedPath}`, 'info', 5000);
                    }
                }
            } catch (error) {
                console.error('Create store error:', error);
                updateStorePathDisplay(null, 'disconnected');
                showNotification(`Failed to create store: ${error.message}`, 'error');
            }
        }

        async function rememberContent(content) {
            if (!connectedStorePath) {
                showNotification('Not connected. Use /connect or /new first', 'error');
                return;
            }

            // Show progress modal
            const progressModal = showProgressModal('Storing Memory', 'Preparing to store memory...');
            const startTime = Date.now();
            progressModal.startTime = startTime;

            try {
                // Start progress tracking with messages for the four steps
                const progressMessages = [
                    'Step 1/4: Initializing store...',
                    'Step 2/4: Classifying content...',
                    'Step 3/4: Storing memory...',
                    'Step 4/4: Processing timeline...'
                ];

                let progressStep = 0;
                const progressInterval = setInterval(() => {
                    const elapsedMs = Date.now() - startTime;
                    const elapsedSec = (elapsedMs / 1000).toFixed(1);

                    // Cycle through progress steps
                    const currentMessage = progressMessages[progressStep % progressMessages.length];
                    const messageWithTime = `${currentMessage} (${elapsedSec}s)`;

                    // Update progress bar (simulate progress)
                    const percentage = Math.min(95, (progressStep + 1) * 20 + (elapsedMs / 100) % 20);
                    updateProgressModal(progressModal, messageWithTime, percentage);

                    // Move to next step periodically
                    if (elapsedMs > (progressStep + 1) * 500) {
                        progressStep++;
                    }
                }, 100);

                const response = await fetch('/api/remember', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        path: connectedStorePath,
                        content: content,
                        namespace: 'default'
                    })
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const result = await response.json();

                // Clear progress tracking and close modal
                clearInterval(progressInterval);
                closeProgressModal(progressModal);

                if (result.success) {
                    // Show results in modal popup
                    showRememberResultsModal(result);

                    let message = `✓ Memory stored at: ${result.key}`;
                    if (result.confidence) {
                        message += ` (confidence: ${(result.confidence * 100).toFixed(0)}%)`;
                    }
                    showNotification(message, 'success');

                    // Refresh the view to show the new memory
                    await refreshStore();
                } else {
                    showNotification(`Not stored: ${result.message}`, 'warning');
                }
            } catch (error) {
                // Clear progress tracking on error
                if (progressInterval) clearInterval(progressInterval);
                closeProgressModal(progressModal);

                console.error('Remember error:', error);
                showNotification(`Failed to store memory: ${error.message}`, 'error');
            }
        }

        async function forgetMemory(key) {
            if (!connectedStorePath) {
                showNotification('Not connected. Use /connect first', 'error');
                return;
            }


            showNotification(`Deleting memory: ${key}...`, 'info');

            try {
                const response = await fetch('/api/forget', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        path: connectedStorePath,
                        key: key,
                        namespace: 'default'
                    })
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const result = await response.json();

                if (result.success) {
                    showNotification(`✓ Memory deleted: ${result.key}`, 'success');

                    // Refresh the view to reflect the deletion
                    await refreshStore();
                } else {
                    showNotification(`Failed to delete: ${result.message}`, 'error');
                }
            } catch (error) {
                console.error('Forget error:', error);
                showNotification(`Failed to delete memory: ${error.message}`, 'error');
            }
        }

        async function refreshStore() {
            if (!connectedStorePath) {
                showNotification('Not connected to any store', 'error');
                return;
            }



            // Reconnect to the store to get fresh data (silent mode to avoid duplicate notifications)
            await connectToStore(connectedStorePath, true);

            // Update branch display and git history
            await updateBranchDisplay();

            // The connectToStore function already calls updateUIWithRealData
            // which refreshes the tree view, so all views are now updated
        }

        async function refreshVisualizationData() {
            if (!connectedStorePath) {

                return;
            }



            try {
                // Refresh the main store data (tree and graph views)
                await refreshStore();


            } catch (error) {
                console.error('Failed to refresh visualization data:', error);
                showNotification('Failed to refresh data views', 'error');
            }
        }

        async function showTimeline() {


            if (!connectedStorePath) {
                showNotification('Not connected to any store. Use /connect <path> first', 'error');
                return;
            }


            try {
                const response = await fetch(`/api/timeline?path=${encodeURIComponent(connectedStorePath)}`);
                const result = await response.json();



                if (result.success) {
                    // Display timeline in a modal or notification
                    const timelineHtml = formatTimelineData(result.timeline_data, result.summary);
                    showTimelineModal(timelineHtml);
                } else {
                    showNotification('Failed to retrieve timeline data', 'error');

                }
            } catch (error) {
                console.error('Timeline error:', error);
                showNotification(`Failed to retrieve timeline: ${error.message}`, 'error');
            }
        }

        async function refreshStoreData() {
            if (!connectedStorePath) {
                return false;
            }

            try {
                const apiUrl = `/api/store?path=${encodeURIComponent(connectedStorePath)}`;
                const response = await fetch(apiUrl);

                if (response.ok) {
                    const data = await response.json();

                    // Update the global realStoreData
                    window.realStoreData = data;

                    // Also update the tree view with fresh data
                    updateTreeViewWithRealData(data);

                    return true;
                } else {
                    return false;
                }
            } catch (error) {
                return false;
            }
        }

        async function loadTimelineData() {
            if (!connectedStorePath) {
                return { success: false, timeline_data: {} };
            }

            // Refresh store data to ensure we have the latest timeline/location entries
            await refreshStoreData();

            try {
                const response = await fetch(`/api/timeline?path=${encodeURIComponent(connectedStorePath)}`);
                const result = await response.json();
                return result;
            } catch (error) {
                console.error('Error loading timeline data:', error);
                return { success: false, timeline_data: {} };
            }
        }

        async function addTimelineEvent(args) {


            if (!connectedStorePath) {
                showNotification('Not connected to any store. Use /connect <path> first', 'error');
                return;
            }

            // Check if input matches old format (YYYY-MM-DD at start) or use natural language
            const datePattern = /^\d{4}-\d{2}-\d{2}\s/;
            let requestBody = { path: connectedStorePath };

            if (datePattern.test(args.trim())) {
                // Old format: YYYY-MM-DD description
                const parts = args.trim().split(' ');
                if (parts.length < 2) {
                    showNotification('Usage: /timeline YYYY-MM-DD description', 'error');
                    return;
                }

                const dateInput = parts[0];
                const description = parts.slice(1).join(' ');

                // Convert YYYY-MM-DD to YYYYMMDD format
                let dateStr;
                if (dateInput.includes('-')) {
                    dateStr = dateInput.replace(/-/g, '');
                } else {
                    dateStr = dateInput;
                }

                // Validate date format
                if (dateStr.length !== 8 || !/^\d{8}$/.test(dateStr)) {
                    showNotification('Invalid date format. Use YYYY-MM-DD (e.g., 2025-01-07)', 'error');
                    return;
                }

                requestBody.date = dateStr;
                requestBody.description = description;

            } else {
                // Natural language format: let the server parse it with LLM
                requestBody.content = args.trim();

                showNotification('Parsing timeline event with AI...', 'info');
            }


            try {
                const response = await fetch('/api/timeline', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(requestBody)
                });

                const result = await response.json();


                if (result.success) {
                    const eventDate = result.date || requestBody.date || 'date';
                    const eventDesc = result.description || requestBody.description || 'event';
                    showNotification(`✓ Timeline event added for ${eventDate}: ${eventDesc}`, 'success');
                    // Refresh the timeline view to show the new event
                    await updateTimelineView();
                    // Also refresh the store to update other views
                    await refreshVisualizationData();
                } else {
                    showNotification(`Failed to add timeline event: ${result.message || 'Unknown error'}`, 'error');
                }
            } catch (error) {
                console.error('Timeline add error:', error);
                showNotification(`Failed to add timeline event: ${error.message}`, 'error');
            }
        }

        function formatTimelineData(timelineData, summary) {
            if (!timelineData || Object.keys(timelineData).length === 0) {
                return '<div class="timeline-empty">No timeline events found.</div>';
            }

            let html = '<div class="timeline-container">';

            // Add summary if available
            if (summary && summary !== 'No timeline events available.') {
                html += '<div class="timeline-summary">';
                html += '<h3>Timeline Summary</h3>';
                html += `<pre>${summary}</pre>`;
                html += '</div>';
            }

            // Add structured timeline data
            html += '<div class="timeline-events">';
            html += '<h3>Timeline Events</h3>';

            // Sort dates in reverse chronological order
            const sortedDates = Object.keys(timelineData).sort().reverse();

            for (const dateStr of sortedDates) {
                const events = timelineData[dateStr];
                const formattedDate = formatDisplayDate(dateStr);

                html += `<div class="timeline-entry">`;
                html += `<div class="timeline-date">${formattedDate}</div>`;
                html += `<div class="timeline-content">${events}</div>`;
                html += `</div>`;
            }

            html += '</div>';
            html += '</div>';

            return html;
        }

        function formatDisplayDate(dateStr) {
            // Convert YYYYMMDD to readable format
            if (dateStr.length === 8) {
                const year = dateStr.substring(0, 4);
                const month = dateStr.substring(4, 6);
                const day = dateStr.substring(6, 8);
                const date = new Date(year, month - 1, day);
                return date.toLocaleDateString('en-US', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                    weekday: 'long'
                });
            }
            return dateStr;
        }

        function showTimelineModal(content) {
            // Create modal
            const modal = document.createElement('div');
            modal.className = 'timeline-modal';
            modal.innerHTML = `
                <div class="timeline-modal-backdrop"></div>
                <div class="timeline-modal-content">
                    <div class="timeline-modal-header">
                        <h2>Timeline View</h2>
                        <button class="timeline-modal-close">&times;</button>
                    </div>
                    <div class="timeline-modal-body">
                        ${content}
                    </div>
                </div>
            `;

            // Add event listeners
            modal.querySelector('.timeline-modal-close').addEventListener('click', () => {
                document.body.removeChild(modal);
            });
            modal.querySelector('.timeline-modal-backdrop').addEventListener('click', () => {
                document.body.removeChild(modal);
            });

            // Add modal to page
            document.body.appendChild(modal);
        }

        async function showPlacesPopup() {
            if (!connectedStorePath) {
                showNotification('Not connected to any store. Use /connect <path> first', 'error');
                return;
            }



            try {
                const response = await fetch(`/api/location?path=${encodeURIComponent(connectedStorePath)}`);
                const result = await response.json();



                if (result.success) {

                    // Display places in a modal popup
                    const placesHtml = formatPlacesData(result.location_data, result.summary);

                    showPlacesModal(placesHtml);
                } else {
                    showNotification('Failed to retrieve places data', 'error');

                }
            } catch (error) {
                console.error('Places error:', error);
                showNotification(`Failed to retrieve places: ${error.message}`, 'error');
            }
        }

        function showPlacesModal(content) {
            // Create modal
            const modal = document.createElement('div');
            modal.className = 'places-modal';
            modal.innerHTML = `
                <div class="places-modal-backdrop"></div>
                <div class="places-modal-content">
                    <div class="places-modal-header">
                        <h2>📍 Your Places</h2>
                        <button class="places-modal-close">&times;</button>
                    </div>
                    <div class="places-modal-body">
                        ${content}
                    </div>
                </div>
            `;

            // Add event listeners
            modal.querySelector('.places-modal-close').addEventListener('click', () => {
                document.body.removeChild(modal);
            });
            modal.querySelector('.places-modal-backdrop').addEventListener('click', () => {
                document.body.removeChild(modal);
            });

            // Add modal to page
            document.body.appendChild(modal);
        }

        function formatPlacesData(placesData, summary) {
            if (!placesData || Object.keys(placesData).length === 0) {
                return `
                    <div style="text-align: center; color: #888; padding: 40px 20px;">
                        <div style="font-size: 48px; margin-bottom: 16px; opacity: 0.3;">🏜️</div>
                        <div style="font-size: 16px; margin-bottom: 8px;">No places found</div>
                        <div style="font-size: 14px; opacity: 0.7;">Add places with /location &lt;place&gt; &lt;description&gt;</div>
                    </div>
                `;
            }

            // Convert places data to array and sort by event count
            const sortedPlaces = Object.entries(placesData)
                .map(([place, data]) => {
                    // Handle different data structures
                    let content;

                    if (typeof data === 'string') {
                        content = data;
                    } else if (data && typeof data === 'object' && data.content) {
                        content = data.content;
                    } else {
                        content = String(data || '');
                    }

                    const events = content.split(' | ').filter(e => e.trim());
                    return {
                        name: place,
                        displayName: (data && typeof data === 'object' && data.name) ? data.name : place.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
                        events: events,
                        eventCount: events.length,
                        content: content
                    };
                })
                .sort((a, b) => b.eventCount - a.eventCount);

            let html = `
                <div style="margin-bottom: 20px; padding: 16px; background: rgba(255,255,255,0.05); border-radius: 8px;">
                    <div style="font-size: 14px; font-weight: 600; margin-bottom: 8px; color: var(--text-primary);">
                        📊 Places Summary
                    </div>
                    <div style="font-size: 13px; color: var(--text-secondary);">
                        ${sortedPlaces.length} place${sortedPlaces.length !== 1 ? 's' : ''} • ${sortedPlaces.reduce((sum, p) => sum + p.eventCount, 0)} total memories
                    </div>
                </div>
                <div class="places-list-popup">
            `;

            // Generate places list HTML
            sortedPlaces.forEach(place => {
                const formattedEvents = place.events.map(event => `• ${event.trim()}`).join('<br>');
                html += `
                    <div class="place-item-popup">
                        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
                            <div style="width: 8px; height: 8px; border-radius: 50%; background: var(--accent-primary);"></div>
                            <div>
                                <div style="font-size: 14px; font-weight: 500; color: var(--text-primary);">
                                    ${place.displayName}
                                </div>
                                <div style="font-size: 12px; color: var(--text-secondary);">
                                    ${place.eventCount} ${place.eventCount === 1 ? 'memory' : 'memories'}
                                </div>
                            </div>
                        </div>
                        <div style="font-size: 13px; color: var(--text-secondary); line-height: 1.4; margin-left: 20px; padding: 8px 12px; background: rgba(255,255,255,0.05); border-radius: 6px;">
                            ${formattedEvents}
                        </div>
                    </div>
                `;
            });

            html += `</div>`;

            return html;
        }

        function renderTimelineGrid(timelineData) {

            const gitTreeElement = document.getElementById('gitTree');
            if (!gitTreeElement) {
                console.error('gitTree element not found!');
                return;
            }



            // Update panel header to show "Timeline" mode
            updateTimelinePanelHeader('Timeline');

            // Force clear existing content and reset to proper container styles
            gitTreeElement.innerHTML = '';
            gitTreeElement.style.display = 'block';
            gitTreeElement.style.visibility = 'visible';
            gitTreeElement.style.opacity = '1';
            gitTreeElement.style.position = 'relative';
            gitTreeElement.style.width = '100%';
            gitTreeElement.style.height = '100%';
            gitTreeElement.style.overflow = 'auto';

            // Create timeline grid container
            const timelineContainer = document.createElement('div');
            timelineContainer.className = 'timeline-grid-container';


            if (!timelineData || Object.keys(timelineData).length === 0) {
                // Show empty state with high visibility
                timelineContainer.innerHTML = `
                    <div class="timeline-empty-state" style="background: #1a1a2e; padding: 40px; border-radius: 12px; text-align: center; margin: 20px;">
                        <div class="timeline-empty-icon" style="font-size: 48px; margin-bottom: 16px;">📅</div>
                        <div class="timeline-empty-title" style="font-size: 18px; font-weight: 600; color: #fff; margin-bottom: 8px;">No Timeline Events</div>
                        <div class="timeline-empty-subtitle" style="font-size: 14px; color: #888;">Add events with /timeline YYYY-MM-DD description</div>
                    </div>
                `;
                gitTreeElement.appendChild(timelineContainer);
                return;
            }

            // Group events by month for better organization
            const eventsByMonth = groupEventsByMonth(timelineData);

            // Create timeline grid
            for (const [monthKey, events] of Object.entries(eventsByMonth)) {
                const monthContainer = document.createElement('div');
                monthContainer.className = 'timeline-month';

                // Month header with inline styling
                const monthHeader = document.createElement('div');
                monthHeader.className = 'timeline-month-header';
                monthHeader.textContent = formatMonthHeader(monthKey);
                monthHeader.style.fontSize = '18px';
                monthHeader.style.fontWeight = '600';
                monthHeader.style.color = '#fff';
                monthHeader.style.marginBottom = '16px';
                monthHeader.style.paddingBottom = '8px';
                monthHeader.style.borderBottom = '2px solid #9333ea';
                monthContainer.appendChild(monthHeader);

                // Month grid with inline styling
                const monthGrid = document.createElement('div');
                monthGrid.className = 'timeline-month-grid';
                monthGrid.style.display = 'grid';
                monthGrid.style.gridTemplateColumns = 'repeat(7, 1fr)';
                monthGrid.style.gap = '4px';
                monthGrid.style.maxWidth = '280px';
                monthGrid.style.marginBottom = '32px';

                // Create calendar grid for the month
                const daysInMonth = getDaysInMonth(monthKey);
                for (let day = 1; day <= daysInMonth; day++) {
                    const dayStr = monthKey + String(day).padStart(2, '0');
                    const dayElement = document.createElement('div');
                    dayElement.className = 'timeline-day';
                    dayElement.dataset.date = dayStr;

                    // Base styling for all days
                    dayElement.style.position = 'relative';
                    dayElement.style.aspectRatio = '1';
                    dayElement.style.display = 'flex';
                    dayElement.style.alignItems = 'center';
                    dayElement.style.justifyContent = 'center';
                    dayElement.style.background = '#2d3748';
                    dayElement.style.border = '1px solid #4a5568';
                    dayElement.style.borderRadius = '8px';
                    dayElement.style.cursor = 'pointer';
                    dayElement.style.transition = 'all 0.2s ease';
                    dayElement.style.color = '#e2e8f0';

                    const dayNumber = document.createElement('div');
                    dayNumber.className = 'timeline-day-number';
                    dayNumber.textContent = day;
                    dayNumber.style.fontSize = '12px';
                    dayNumber.style.fontWeight = '500';
                    dayElement.appendChild(dayNumber);

                    if (events[dayStr]) {
                        dayElement.classList.add('has-event');
                        dayElement.title = `${formatDisplayDate(dayStr)}: ${events[dayStr]}`;

                        // Add inline styling to ensure visibility
                        dayElement.style.background = '#9333ea';
                        dayElement.style.color = 'white';
                        dayElement.style.fontWeight = '600';
                        dayElement.style.border = '2px solid #7c3aed';
                        dayElement.style.boxShadow = '0 2px 8px rgba(147, 51, 234, 0.3)';

                        // Add event indicator
                        const eventDot = document.createElement('div');
                        eventDot.className = 'timeline-event-dot';
                        eventDot.style.position = 'absolute';
                        eventDot.style.top = '2px';
                        eventDot.style.right = '2px';
                        eventDot.style.width = '6px';
                        eventDot.style.height = '6px';
                        eventDot.style.background = 'rgba(255, 255, 255, 0.8)';
                        eventDot.style.borderRadius = '50%';
                        dayElement.appendChild(eventDot);

                        // Add click handler
                        dayElement.addEventListener('click', () => showEventDetail(dayStr, events[dayStr]));
                    }

                    monthGrid.appendChild(dayElement);
                }

                monthContainer.appendChild(monthGrid);
                timelineContainer.appendChild(monthContainer);
            }

            gitTreeElement.appendChild(timelineContainer);



            // Mark this element as showing timeline to prevent overwrites
            gitTreeElement.setAttribute('data-showing', 'timeline');
        }

        function groupEventsByMonth(timelineData) {
            const eventsByMonth = {};

            for (const [dateStr, content] of Object.entries(timelineData)) {
                if (dateStr.length === 8) {
                    const monthKey = dateStr.substring(0, 6); // YYYYMM
                    if (!eventsByMonth[monthKey]) {
                        eventsByMonth[monthKey] = {};
                    }
                    eventsByMonth[monthKey][dateStr] = content;
                }
            }

            // Sort months in reverse chronological order
            const sortedMonths = Object.keys(eventsByMonth).sort().reverse();
            const sortedEventsByMonth = {};
            for (const month of sortedMonths) {
                sortedEventsByMonth[month] = eventsByMonth[month];
            }

            return sortedEventsByMonth;
        }

        function formatMonthHeader(monthKey) {
            if (monthKey.length === 6) {
                const year = monthKey.substring(0, 4);
                const month = monthKey.substring(4, 6);
                const date = new Date(year, month - 1, 1);
                return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long' });
            }
            return monthKey;
        }

        function getDaysInMonth(monthKey) {
            if (monthKey.length === 6) {
                const year = parseInt(monthKey.substring(0, 4));
                const month = parseInt(monthKey.substring(4, 6));
                return new Date(year, month, 0).getDate();
            }
            return 31; // fallback
        }

        function showEventDetail(dateStr, content) {
            const formattedDate = formatDisplayDate(dateStr);

            // Update the Memory Activity panel instead of showing a modal
            const timelineDetailsContent = document.getElementById('timelineDetailsContent');
            if (timelineDetailsContent) {
                timelineDetailsContent.innerHTML = `
                    <div style="margin-bottom: 16px;">
                        <h3 style="color: var(--text-primary); font-size: 18px; font-weight: 600; margin: 0 0 12px 0;">
                            📅 ${formattedDate}
                        </h3>
                    </div>
                    <div style="background: var(--bg-glass-light); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; padding: 16px;">
                        <p style="color: var(--text-secondary); line-height: 1.6; margin: 0; font-size: 14px;">
                            ${content}
                        </p>
                    </div>
                    <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid rgba(255, 255, 255, 0.1);">
                        <small style="color: var(--text-muted); font-size: 12px;">
                            Timeline event from ${dateStr}
                        </small>
                    </div>
                `;

                // Update the timeline details header
                const timelineDetailsHeader = document.querySelector('.timeline-details-header');
                if (timelineDetailsHeader) {
                    timelineDetailsHeader.textContent = 'Timeline Event Details';
                }
            }
        }

        function updateTimelinePanelHeader(mode) {
            // Find the timeline header element (currently just shows "Memoir")
            const memoirLogoText = document.querySelector('.memoir-logo-text');
            if (memoirLogoText) {
                // Update to show current mode
                memoirLogoText.textContent = `Memoir - ${mode}`;
            }
        }

        function inspectCurrentDOM() {
            const gitTreeElement = document.querySelector('.git-tree');
            if (gitTreeElement) {






                // Show classes on direct children
                Array.from(gitTreeElement.children).forEach((child, i) => {

                });

                showNotification(`DOM Inspection complete - check console`, 'info');
            } else {

                showNotification('gitTree element not found!', 'error');
            }
        }

        async function forceTimelineView() {
            if (!connectedStorePath) {
                showNotification('Not connected to any store', 'error');
                return;
            }



            // Force clear any existing content
            const gitTreeElement = document.querySelector('.git-tree');
            if (gitTreeElement) {

                gitTreeElement.innerHTML = '';

                // Force reload timeline data
                const timelineResult = await loadTimelineData();

                if (timelineResult.success) {
                    renderTimelineGrid(timelineResult.timeline_data);

                    // Double-check it was added
                    setTimeout(() => {
                        const timelineContainer = gitTreeElement.querySelector('.timeline-grid-container');
                        if (timelineContainer) {
                        }
                    }, 100);

                    showNotification('Timeline view forced', 'success');
                } else {
                    showNotification('Failed to load timeline data', 'error');
                }
            } else {
                showNotification('gitTree element not found', 'error');
            }
        }

        function checkTimelineStyles() {


            const gitTreeElement = document.querySelector('.git-tree');
            if (gitTreeElement) {
                const computedStyle = window.getComputedStyle(gitTreeElement);
                console.log('gitTree element styles:', {
                    display: computedStyle.display,
                    visibility: computedStyle.visibility,
                    opacity: computedStyle.opacity,
                    height: computedStyle.height,
                    width: computedStyle.width,
                    position: computedStyle.position
                });

                const timelineContainer = gitTreeElement.querySelector('.timeline-grid-container');
                if (timelineContainer) {
                    const containerStyle = window.getComputedStyle(timelineContainer);
                    console.log('Timeline container styles:', {
                        display: containerStyle.display,
                        visibility: containerStyle.visibility,
                        opacity: containerStyle.opacity,
                        height: containerStyle.height,
                        width: containerStyle.width,
                        position: containerStyle.position
                    });

                    const timelineMonths = timelineContainer.querySelectorAll('.timeline-month');

                    timelineMonths.forEach((month, i) => {
                        const monthStyle = window.getComputedStyle(month);
                        console.log(`Month ${i} styles:`, {
                            display: monthStyle.display,
                            visibility: monthStyle.visibility,
                            opacity: monthStyle.opacity
                        });

                        const days = month.querySelectorAll('.timeline-day.has-event');


                        days.forEach((day, j) => {
                            const dayStyle = window.getComputedStyle(day);
                            console.log(`Event day ${j} (${day.dataset.date}):`, {
                                display: dayStyle.display,
                                backgroundColor: dayStyle.backgroundColor,
                                color: dayStyle.color,
                                visibility: dayStyle.visibility
                            });
                        });
                    });
                } else {

                }
            } else {

            }

            showNotification('CSS styles check complete - see console', 'info');
        }

        function restoreNormalLayout() {


            // Clear timeline and restore git history
            restoreOriginalGitHistory();

            // Reset any modified styles
            const gitTreeElement = document.querySelector('.git-tree');
            if (gitTreeElement) {
                gitTreeElement.style.position = '';
                gitTreeElement.style.width = '';
                gitTreeElement.style.height = '';
                gitTreeElement.style.overflow = '';
                gitTreeElement.removeAttribute('data-showing');
            }

            showNotification('Layout restored to normal git history view', 'success');
        }

        async function debugTimeline() {
            if (!connectedStorePath) {
                showNotification('Not connected to any store. Use /connect <path> first', 'error');
                return;
            }

            try {
                // Use the dedicated debug-timeline API to get raw timeline data
                const response = await fetch(`/api/debug-timeline?path=${encodeURIComponent(connectedStorePath)}`);
                const result = await response.json();


                if (result.success) {


                    // Show detailed timeline memory structures
                    if (result.timeline_memories && result.timeline_memories.length > 0) {
                        result.timeline_memories.forEach((tm, index) => {
                            console.log(`DEBUG: Timeline Memory ${index + 1}:`, {
                                path: tm.path,
                                data: tm.data
                            });

                        });
                    }

                    showNotification(
                        `Debug Results:\n` +
                        `${result.timeline_memories_count} timeline memories found\n` +
                        `${result.all_memories_count} total memories\n` +
                        `Check console for detailed structures`,
                        'info',
                        8000
                    );
                } else {
                    showNotification('Failed to retrieve store data for debugging', 'error');

                }
            } catch (error) {
                console.error('Debug timeline error:', error);
                showNotification(`Failed to debug timeline: ${error.message}`, 'error');
            }
        }

        // ==================== PLACES VIEW FUNCTIONS ====================

        async function showPlacesView() {
            // Switch to Places view tab
            document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
            document.querySelector('.view-btn[data-view="places"]').classList.add('active');

            // Show places view
            document.getElementById('treeView').style.display = 'none';
            document.getElementById('graphView').style.display = 'none';
            document.getElementById('timelineView').style.display = 'none';
            document.getElementById('placesView').style.display = 'block';

            await initializePlacesView();
            showNotification('Switched to Places view', 'success');
        }

        async function initializePlacesDemoMode() {
            // Demo places data
            const demoPlacesData = {
                "san_francisco": "Lived here for 3 years working at a tech startup. Loved the foggy mornings and vibrant food scene. Favorite spots included Golden Gate Park and Mission District.",
                "paris": "Spent a wonderful week exploring museums and cafes. Visited the Louvre, walked along the Seine, and enjoyed croissants every morning.",
                "tokyo": "Amazing business trip - experienced incredible sushi, visited temples in Shibuya, and was impressed by the efficiency of the train system.",
                "new_york": "Attended a conference in Manhattan. Broadway show was fantastic, Central Park was peaceful, and the energy of the city was infectious.",
                "london": "Rainy but charming visit. Tower Bridge at sunset was breathtaking, and afternoon tea at Harrods was delightful."
            };

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

        async function initializePlacesView() {
            if (!connectedStorePath) {
                // Demo mode - show sample places data
                await initializePlacesDemoMode();
                return;
            }

            try {
                await loadPlacesData();

                // Initialize map if not already done
                if (!window.placesMapInitialized) {

                    // Small delay to ensure DOM is ready
                    setTimeout(async () => {
                        initializePlacesMap();
                        // Wait a bit more for map to be fully ready, then reload places data
                        setTimeout(async () => {

                            await loadPlacesData();
                        }, 200);
                    }, 100);
                } else if (window.placesMap) {

                    // Resize map when view is shown
                    setTimeout(() => {
                        window.placesMap.invalidateSize();
                    }, 100);
                }
            } catch (error) {
                console.error('Failed to initialize Places view:', error);
                showNotification('Failed to load places data', 'error');
            }
        }

        async function loadPlacesData() {
            if (!connectedStorePath) {
                console.error('No store path connected for places data');
                return { success: false, places_data: {} };
            }

            // Refresh store data to ensure we have the latest timeline/location entries
            await refreshStoreData();

            try {
                const response = await fetch(`/api/location?path=${encodeURIComponent(connectedStorePath)}`);
                const result = await response.json();

                if (result.success) {
                    await updatePlacesDisplay(result.location_data);
                } else {
                    console.error('Failed to load places data:', result.error);
                    document.getElementById('placesListContent').innerHTML = `
                        <div style="text-align: center; color: #ef4444; padding: 20px;">
                            <div style="font-size: 16px; margin-bottom: 8px;">⚠️ Error Loading Places</div>
                            <div style="font-size: 14px; opacity: 0.8;">${result.error || 'Unknown error'}</div>
                            <div style="font-size: 14px; opacity: 0.7; margin-top: 8px;">Add places with /location place description</div>
                        </div>
                    `;
                }

                return result;
            } catch (error) {
                console.error('Error loading places data:', error);
                document.getElementById('placesListContent').innerHTML = `
                    <div style="text-align: center; color: #ef4444; padding: 20px;">
                        <div style="font-size: 16px; margin-bottom: 8px;">⚠️ Connection Error</div>
                        <div style="font-size: 14px; opacity: 0.8;">Failed to fetch places data</div>
                        <div style="font-size: 14px; opacity: 0.7; margin-top: 8px;">Check your connection and try again</div>
                    </div>
                `;
                return { success: false, places_data: {} };
            }
        }

        async function updatePlacesDisplay(placesData, isDemo = false) {
            const placesListContent = document.getElementById('placesListContent');

            if (!placesData || Object.keys(placesData).length === 0) {
                placesListContent.innerHTML = `
                    <div style="text-align: center; color: #888; padding: 40px 20px;">
                        <div style="font-size: 48px; margin-bottom: 16px; opacity: 0.3;">🏜️</div>
                        <div style="font-size: 16px; margin-bottom: 8px;">No places found</div>
                        <div style="font-size: 14px; opacity: 0.7;">Add places with /location place description</div>
                    </div>
                `;
                return;
            }

            // Add demo banner if in demo mode
            let demoBanner = '';
            if (isDemo) {
                demoBanner = `
                    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px 20px; margin-bottom: 16px; border-radius: 8px; text-align: center; font-size: 14px;">
                        📍 <strong>Demo Mode</strong> - Sample location data shown. Connect to a memory store to see your real places.
                    </div>
                `;
            }

            // Convert places data to array and sort by event count
            const sortedPlaces = Object.entries(placesData)
                .map(([place, data]) => {
                    // Handle different data structures
                    let content;

                    if (typeof data === 'string') {
                        content = data;
                    } else if (data && typeof data === 'object' && data.content) {
                        content = data.content;
                    } else {
                        content = String(data || '');
                    }

                    const events = content.split(' | ').filter(e => e.trim());
                    return {
                        name: place,
                        displayName: (data && typeof data === 'object' && data.name) ? data.name : place.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
                        events: events,
                        eventCount: events.length,
                        content: content
                    };
                })
                .sort((a, b) => b.eventCount - a.eventCount);

            // Generate places list HTML
            const placesHTML = sortedPlaces.map(place => `
                <div class="place-item" onclick="selectPlace('${place.name}', '${place.displayName}', '${place.content.replace(/'/g, "\\'")}')">
                    <div class="place-marker"></div>
                    <div class="place-info">
                        <div class="place-name">${place.displayName}</div>
                        <div class="place-count">${place.eventCount} ${place.eventCount === 1 ? 'memory' : 'memories'}</div>
                    </div>
                </div>
            `).join('');

            placesListContent.innerHTML = demoBanner + placesHTML;

            // Update map with places data
            await updatePlacesMap(sortedPlaces);
        }

        async function selectPlace(placeName, displayName, content) {
            // Remove selection from other places
            document.querySelectorAll('.place-item').forEach(item => item.classList.remove('selected'));

            // Select clicked place
            event.target.closest('.place-item').classList.add('selected');

            // Show place details
            const detailsContainer = document.getElementById('placesLocationDetails');
            const placeNameElement = document.getElementById('selectedPlaceName');
            const placeContentElement = document.getElementById('selectedPlaceContent');

            placeNameElement.textContent = displayName;

            // Format content with events separated
            const events = content.split(' | ').filter(e => e.trim());
            const formattedContent = events.map(event => `• ${event.trim()}`).join('<br>');
            placeContentElement.innerHTML = formattedContent;

            detailsContainer.style.display = 'block';

            // Center map on selected location
            if (window.placesMap) {
                try {
                    const coords = await geocodeLocation(placeName);
                    if (coords) {
                        window.placesMap.setView([coords.lat, coords.lon], 12);

                        // Find and open the marker popup
                        window.placesMarkers.eachLayer((layer) => {
                            if (layer instanceof L.Marker) {
                                const markerLatLng = layer.getLatLng();
                                if (Math.abs(markerLatLng.lat - coords.lat) < 0.001 &&
                                    Math.abs(markerLatLng.lng - coords.lon) < 0.001) {
                                    layer.openPopup();
                                }
                            }
                        });
                    }
                } catch (error) {
                    console.warn('Failed to center map on selected location:', error);
                }
            }
        }

        async function addLocationEvent(args) {
            if (!connectedStorePath) {
                showNotification('Please connect to a memory store first', 'error');
                return;
            }

            // Check if input looks like structured format (starts with a single word that could be a location)
            // Otherwise use natural language processing
            let requestBody = { path: connectedStorePath };

            const parts = args.trim().split(/\s+/);

            // Simple heuristic: if first word looks like a place name and there's more text, treat as structured
            // Otherwise send the whole thing for natural language processing
            const firstWord = parts[0];
            const hasMultipleParts = parts.length >= 2;
            const looksLikeStructured = hasMultipleParts && /^[A-Z][a-zA-Z]+$/.test(firstWord);

            if (looksLikeStructured) {
                // Structured format: <location> <description>
                requestBody.location = parts[0];
                requestBody.description = parts.slice(1).join(' ');

            } else {
                // Natural language format: let the server parse it with AI
                requestBody.content = args.trim();

                showNotification('Parsing location event with AI...', 'info');
            }

            try {
                const response = await fetch('/api/location', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(requestBody),
                });

                const result = await response.json();

                if (result.success) {
                    const locationName = result.location || requestBody.location || 'location';
                    showNotification(`Location event added: ${locationName}`, 'success');

                    // Refresh places view if it's currently active
                    if (document.getElementById('placesView').style.display === 'block') {
                        await loadPlacesData();
                    }

                    // Refresh tree and graph views to show new data
                    await refreshVisualizationData();
                } else {
                    showNotification(`Failed to add location event: ${result.error}`, 'error');
                    console.error('Location event error:', result.error);
                }
            } catch (error) {
                console.error('Location event submission error:', error);
                showNotification(`Error adding location event: ${error.message}`, 'error');
            }
        }

        async function summarizeMemoryStore(summaryType = 'all') {
            if (!connectedStorePath) {
                showNotification('Please connect to a memory store first', 'error');
                return;
            }

            // Check if we're in demo mode
            if (connectedStorePath === null || window.isNewEmptyStore === true) {
                showNotification('Summarization is not available in demo mode. Please connect to a real memory store using /connect <path>', 'error', 5000);
                return;
            }

            // Validate summary type
            const validTypes = ['all', 'taxonomy', 'timeline', 'places', 'keys'];
            if (!validTypes.includes(summaryType)) {
                showNotification(`Invalid summary type: ${summaryType}. Use: ${validTypes.join(', ')}`, 'error');
                return;
            }

            // Show progress modal
            const progressModal = showProgressModal('Generating Summary', 'Analyzing memory store data...');

            // Create AbortController for cancellation
            const abortController = new AbortController();
            progressModal.abortController = abortController;

            try {
                // Update progress
                updateProgressModal(progressModal, 'Sending request to server...', 20);

                // Build API URL with pattern if needed for keys type
                let apiUrl = `/api/summarize?path=${encodeURIComponent(connectedStorePath)}&type=${encodeURIComponent(summaryType)}`;
                if (summaryType === 'keys' && window.keyPattern) {
                    apiUrl += `&pattern=${encodeURIComponent(window.keyPattern)}`;
                }

                const response = await fetch(apiUrl, {
                    signal: abortController.signal
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                // Update progress
                updateProgressModal(progressModal, 'Processing memory data with AI...', 60);

                const result = await response.json();

                // Update progress
                updateProgressModal(progressModal, 'Generating summary display...', 90);

                if (result.success) {
                    // Create a comprehensive summary display
                    let summaryContent = `<div class="summary-content">`;
                    summaryContent += `<h3>Memory Store Summary (${summaryType})</h3>`;

                    // Add metadata section
                    if (result.metadata) {
                        summaryContent += `<div class="summary-metadata">`;
                        summaryContent += `<div class="metadata-grid">`;
                        summaryContent += `<div class="metadata-item">`;
                        summaryContent += `<span class="metadata-label">📁 Store Path:</span>`;
                        summaryContent += `<span class="metadata-value">${result.metadata.store_path}</span>`;
                        summaryContent += `</div>`;
                        summaryContent += `<div class="metadata-item">`;
                        summaryContent += `<span class="metadata-label">🌿 Branch:</span>`;
                        summaryContent += `<span class="metadata-value">${result.metadata.current_branch} (${result.metadata.current_commit})</span>`;
                        summaryContent += `</div>`;
                        summaryContent += `<div class="metadata-item">`;
                        summaryContent += `<span class="metadata-label">⏱️ Generation Time:</span>`;
                        summaryContent += `<span class="metadata-value">${result.metadata.total_time_seconds}s</span>`;
                        summaryContent += `</div>`;
                        summaryContent += `<div class="metadata-item">`;
                        summaryContent += `<span class="metadata-label">🕒 Generated At:</span>`;
                        summaryContent += `<span class="metadata-value">${result.metadata.generated_at}</span>`;
                        summaryContent += `</div>`;

                        // Add timing breakdown if available
                        if (result.metadata.timing_breakdown && Object.keys(result.metadata.timing_breakdown).length > 1) {
                            summaryContent += `<div class="metadata-item full-width">`;
                            summaryContent += `<span class="metadata-label">📊 Timing Breakdown:</span>`;
                            summaryContent += `<span class="metadata-value">`;
                            const timings = Object.entries(result.metadata.timing_breakdown)
                                .map(([key, value]) => `${key}: ${value}s`)
                                .join(', ');
                            summaryContent += timings;
                            summaryContent += `</span>`;
                            summaryContent += `</div>`;
                        }

                        summaryContent += `</div>`;
                        summaryContent += `</div>`;
                    }

                    const summaries = result.summaries;

                    if (summaries.overall) {
                        summaryContent += `<div class="summary-section">`;
                        summaryContent += `<h4>📋 Executive Summary</h4>`;
                        summaryContent += `<p>${summaries.overall.replace(/\n/g, '<br>')}</p>`;
                        summaryContent += `</div>`;
                    }

                    if (summaries.taxonomy) {
                        summaryContent += `<div class="summary-section">`;
                        summaryContent += `<h4>🗂️ Data Organization & Taxonomy</h4>`;
                        summaryContent += `<p>${summaries.taxonomy.replace(/\n/g, '<br>')}</p>`;
                        summaryContent += `</div>`;
                    }

                    if (summaries.timeline) {
                        summaryContent += `<div class="summary-section">`;
                        summaryContent += `<h4>⏰ Timeline & Events</h4>`;
                        summaryContent += `<p>${summaries.timeline.replace(/\n/g, '<br>')}</p>`;
                        summaryContent += `</div>`;
                    }

                    if (summaries.places) {
                        summaryContent += `<div class="summary-section">`;
                        summaryContent += `<h4>📍 Places & Locations</h4>`;
                        summaryContent += `<p>${summaries.places.replace(/\n/g, '<br>')}</p>`;
                        summaryContent += `</div>`;
                    }

                    if (summaries.keys) {
                        summaryContent += `<div class="summary-section">`;
                        summaryContent += `<h4>🔑 Keys Summary</h4>`;
                        summaryContent += `<p>${summaries.keys.replace(/\n/g, '<br>')}</p>`;
                        summaryContent += `</div>`;

                        // Add matching keys list if available
                        if (result.matching_keys && result.matching_keys.length > 0) {
                            summaryContent += `<div class="summary-section">`;
                            summaryContent += `<h4>🗂️ Matching Keys (${result.matching_keys.length})</h4>`;
                            summaryContent += `<div style="max-height: 200px; overflow-y: auto; font-family: monospace; font-size: 0.9em; background: var(--bg-glass); padding: 12px; border-radius: 8px;">`;
                            result.matching_keys.forEach(key => {
                                summaryContent += `<div style="padding: 2px 0; border-bottom: 1px solid var(--border-light);">${key}</div>`;
                            });
                            summaryContent += `</div>`;
                            summaryContent += `</div>`;
                        }
                    }

                    summaryContent += `</div>`;

                    // Create and show a modal popup for the summary
                    const modal = document.createElement('div');
                    modal.className = 'summary-modal';

                    // Generate dynamic title based on summary type
                    let modalTitle = 'Memory Store Summary';
                    if (summaryType === 'keys' && window.keyPattern) {
                        modalTitle = `Keys Summary: ${window.keyPattern}`;
                    }

                    modal.innerHTML = `
                        <div class="summary-modal-content">
                            <div class="summary-modal-header">
                                <h2>${modalTitle}</h2>
                                <button class="summary-modal-close">&times;</button>
                            </div>
                            <div class="summary-modal-body">
                                ${summaryContent}
                            </div>
                            <div class="summary-modal-footer">
                                <button class="summary-button secondary" onclick="copySummaryToClipboard()">📋 Copy to Clipboard</button>
                                <button class="summary-button primary" onclick="closeSummaryModal()">Close</button>
                            </div>
                        </div>
                    `;

                    // Add CSS for the modal
                    if (!document.getElementById('summary-modal-styles')) {
                        const styles = document.createElement('style');
                        styles.id = 'summary-modal-styles';
                        styles.textContent = `
                            .summary-modal {
                                position: fixed;
                                top: 0;
                                left: 0;
                                width: 100%;
                                height: 100%;
                                background: rgba(0, 0, 0, 0.8);
                                backdrop-filter: blur(10px);
                                z-index: 10000;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                animation: fadeIn 0.3s ease-out;
                            }

                            .summary-modal-content {
                                background: var(--bg-primary);
                                border: 1px solid var(--border-light);
                                border-radius: 20px;
                                max-width: 80%;
                                max-height: 80%;
                                overflow: hidden;
                                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                                animation: slideIn 0.3s ease-out;
                            }

                            .summary-modal-header {
                                padding: 20px 30px;
                                border-bottom: 1px solid var(--border-light);
                                display: flex;
                                justify-content: space-between;
                                align-items: center;
                                background: var(--bg-glass);
                            }

                            .summary-modal-header h2 {
                                margin: 0;
                                color: var(--text-primary);
                                font-size: 1.5em;
                            }

                            .summary-modal-close {
                                background: none;
                                border: none;
                                font-size: 1.5em;
                                color: var(--text-muted);
                                cursor: pointer;
                                padding: 5px;
                                border-radius: 50%;
                                transition: all 0.2s ease;
                            }

                            .summary-modal-close:hover {
                                color: var(--text-primary);
                                background: var(--bg-glass-light);
                            }

                            .summary-modal-body {
                                padding: 30px;
                                max-height: 60vh;
                                overflow-y: auto;
                            }

                            .summary-content h3 {
                                color: var(--accent-primary);
                                margin-bottom: 20px;
                                font-size: 1.3em;
                            }

                            .summary-section {
                                margin-bottom: 25px;
                                padding: 15px;
                                background: var(--bg-glass);
                                border-radius: 12px;
                                border: 1px solid var(--border-light);
                            }

                            .summary-section h4 {
                                color: var(--text-primary);
                                margin-bottom: 10px;
                                font-size: 1.1em;
                            }

                            .summary-section p {
                                color: var(--text-secondary);
                                line-height: 1.6;
                                margin: 0;
                            }

                            .summary-metadata {
                                margin-bottom: 25px;
                                padding: 15px;
                                background: rgba(168, 85, 247, 0.1);
                                border-radius: 12px;
                                border: 1px solid rgba(168, 85, 247, 0.2);
                            }

                            .metadata-grid {
                                display: grid;
                                grid-template-columns: 1fr 1fr;
                                gap: 12px;
                            }

                            .metadata-item {
                                display: flex;
                                flex-direction: column;
                                gap: 4px;
                            }

                            .metadata-item.full-width {
                                grid-column: 1 / -1;
                            }

                            .metadata-label {
                                font-size: 12px;
                                font-weight: 600;
                                color: var(--accent-primary);
                                text-transform: uppercase;
                                letter-spacing: 0.5px;
                            }

                            .metadata-value {
                                font-size: 13px;
                                color: var(--text-primary);
                                font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
                                word-break: break-all;
                            }

                            .summary-modal-footer {
                                padding: 20px 30px;
                                border-top: 1px solid var(--border-light);
                                display: flex;
                                gap: 15px;
                                justify-content: flex-end;
                                background: var(--bg-glass);
                            }

                            .summary-button {
                                padding: 10px 20px;
                                border: none;
                                border-radius: 8px;
                                font-size: 14px;
                                cursor: pointer;
                                transition: all 0.2s ease;
                                font-weight: 500;
                            }

                            .summary-button.primary {
                                background: var(--accent-primary);
                                color: white;
                            }

                            .summary-button.primary:hover {
                                background: var(--accent-secondary);
                                transform: translateY(-1px);
                            }

                            .summary-button.secondary {
                                background: var(--bg-glass);
                                color: var(--text-primary);
                                border: 1px solid var(--border-light);
                            }

                            .summary-button.secondary:hover {
                                background: var(--bg-glass-light);
                                transform: translateY(-1px);
                            }

                            @keyframes fadeIn {
                                from { opacity: 0; }
                                to { opacity: 1; }
                            }

                            @keyframes slideIn {
                                from { transform: scale(0.9) translateY(-20px); opacity: 0; }
                                to { transform: scale(1) translateY(0); opacity: 1; }
                            }
                        `;
                        document.head.appendChild(styles);
                    }

                    // Store summary for clipboard copying
                    window.currentSummary = result;

                    // Add modal to DOM
                    document.body.appendChild(modal);

                    // Add event listeners
                    modal.querySelector('.summary-modal-close').onclick = () => document.body.removeChild(modal);
                    modal.onclick = (e) => {
                        if (e.target === modal) document.body.removeChild(modal);
                    };

                    // Global functions for modal buttons
                    window.closeSummaryModal = () => {
                        const modal = document.querySelector('.summary-modal');
                        if (modal) document.body.removeChild(modal);
                    };

                    window.copySummaryToClipboard = () => {
                        if (window.currentSummary) {
                            let textSummary = `Memory Store Summary (${window.currentSummary.summary_type})\n\n`;

                            // Add metadata information
                            if (window.currentSummary.metadata) {
                                const meta = window.currentSummary.metadata;
                                textSummary += `METADATA:\n`;
                                textSummary += `Store Path: ${meta.store_path}\n`;
                                textSummary += `Branch: ${meta.current_branch} (${meta.current_commit})\n`;
                                textSummary += `Generation Time: ${meta.total_time_seconds}s\n`;
                                textSummary += `Generated At: ${meta.generated_at}\n`;

                                if (meta.timing_breakdown && Object.keys(meta.timing_breakdown).length > 1) {
                                    const timings = Object.entries(meta.timing_breakdown)
                                        .map(([key, value]) => `${key}: ${value}s`)
                                        .join(', ');
                                    textSummary += `Timing Breakdown: ${timings}\n`;
                                }
                                textSummary += '\n';
                            }

                            Object.entries(window.currentSummary.summaries).forEach(([key, value]) => {
                                const sectionTitles = {
                                    overall: 'Executive Summary',
                                    taxonomy: 'Data Organization & Taxonomy',
                                    timeline: 'Timeline & Events',
                                    places: 'Places & Locations'
                                };
                                textSummary += `${sectionTitles[key] || key}:\n${value}\n\n`;
                            });

                            navigator.clipboard.writeText(textSummary).then(() => {
                                showNotification('Summary copied to clipboard!', 'success');
                            }).catch(() => {
                                showNotification('Failed to copy to clipboard', 'error');
                            });
                        }
                    };

                    // Complete progress and close modal
                    updateProgressModal(progressModal, 'Summary completed!', 100);
                    setTimeout(() => closeProgressModal(progressModal), 500);
                    showNotification('Summary generated successfully!', 'success');

                } else {
                    closeProgressModal(progressModal);
                    showNotification(`Summary generation failed: ${result.error || 'Unknown error'}`, 'error');
                }

            } catch (error) {
                closeProgressModal(progressModal);

                if (error.name === 'AbortError') {
                    showNotification('Summary generation cancelled', 'info');
                } else {
                    console.error('Summary generation error:', error);
                    showNotification(`Error generating summary: ${error.message}`, 'error');
                }
            }
        }

        async function summarizeNodePath(fullPath) {
            // Close the node details popup
            const existingPopup = document.querySelector('.node-details-popup');
            if (existingPopup) {
                document.body.removeChild(existingPopup);
            }

            // Set the pattern and trigger keys summary
            // Use exact key to get the single key's content, or add proper wildcard for children
            window.keyPattern = fullPath;  // Use exact key (the backend will handle it)
            await summarizeMemoryStore('keys');
        }

        async function recallMemories(query, person = null) {
            if (!connectedStorePath) {
                showNotification('Please connect to a memory store first', 'error');
                return;
            }

            // Check if we're in demo mode
            if (connectedStorePath === null || window.isNewEmptyStore === true) {
                showNotification('Recall is not available in demo mode. Please connect to a real memory store using /connect <path>', 'error', 5000);
                return;
            }

            // Track timing
            const startTime = Date.now();

            // Show progress modal
            const searchDescription = person ?
                `Searching for: "${query}" (filtered by ${person})` :
                `Searching for: "${query}"`;
            const progressModal = showProgressModal('Recalling Memories', searchDescription);
            progressModal.startTime = startTime;

            // Create AbortController for cancellation
            const abortController = new AbortController();
            progressModal.abortController = abortController;

            try {
                // Start with initial progress
                updateProgressModalWithTime(progressModal, 'Initializing search...', 5);

                // The actual search happens in the API call, so we simulate progress during the fetch
                let apiUrl = `/api/recall?path=${encodeURIComponent(connectedStorePath)}&query=${encodeURIComponent(query)}`;
                if (person) {
                    apiUrl += `&person=${encodeURIComponent(person)}`;
                }
                const fetchPromise = fetch(apiUrl, {
                    signal: abortController.signal
                });

                // Start continuous progress updates with elapsed time
                let progressStep = 0;
                const progressMessages = [
                    'Initializing search...',
                    'Step 1/4: Discovering memory paths...',
                    'Step 2/4: AI selecting relevant paths...',
                    'Step 3/4: AI analyzing content...',
                    'Step 4/4: Retrieving memories...'
                ];

                const progressInterval = setInterval(() => {
                    if (!abortController.signal.aborted) {
                        const elapsedMs = Date.now() - startTime;
                        const elapsedSec = (elapsedMs / 1000).toFixed(1);

                        // Determine step and progress based on elapsed time
                        let step = 0;
                        let percent = 5;

                        if (elapsedSec < 0.5) {
                            step = 0; percent = 5;
                        } else if (elapsedSec < 1.0) {
                            step = 1; percent = 15;
                        } else if (elapsedSec < 2.0) {
                            step = 2; percent = 35;
                        } else if (elapsedSec < 3.0) {
                            step = 3; percent = 65;
                        } else {
                            step = 4; percent = 85;
                        }

                        // Only update if step changed or every 100ms for time display
                        if (step !== progressStep || elapsedMs % 100 < 50) {
                            progressStep = step;
                            const message = progressMessages[step] || progressMessages[4];
                            updateProgressModalWithTime(progressModal, message, percent);
                        }
                    }
                }, 100); // Update every 100ms

                // Clear interval when request completes
                const cleanupProgress = () => {
                    if (progressInterval) {
                        clearInterval(progressInterval);
                    }
                };

                // Wait for the API response
                const response = await fetchPromise;
                cleanupProgress(); // Stop the progress updates

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                updateProgressModalWithTime(progressModal, 'Processing results...', 95);

                const result = await response.json();

                if (result.success) {
                    // Create recall results display
                    let recallContent = `<div class="recall-content">`;
                    recallContent += `<h3>Memory Recall Results</h3>`;
                    recallContent += `<div class="recall-query">Query: "${query}"${person ? ` (filtered by ${person})` : ''}</div>`;

                    // Display search metadata
                    if (result.metadata) {
                        recallContent += `
                            <div class="recall-metadata">
                                <div class="metadata-grid">
                                    <div class="metadata-item">
                                        <span class="metadata-label">Results Found</span>
                                        <span class="metadata-value">${result.metadata.results_count || 0}</span>
                                    </div>
                                    <div class="metadata-item">
                                        <span class="metadata-label">Total Time</span>
                                        <span class="metadata-value">${result.metadata.total_time_seconds || 0}s</span>
                                    </div>
                                    <div class="metadata-item full-width">
                                        <span class="metadata-label">Store Path</span>
                                        <span class="metadata-value">${result.metadata.store_path || connectedStorePath}</span>
                                    </div>
                                </div>
                        `;

                        // Display four-step timing breakdown if available
                        if (result.metadata.four_step_timings) {
                            recallContent += `
                                <div class="timing-breakdown">
                                    <div class="timing-header">⏱️ Recall Process Breakdown</div>
                                    <div class="timing-grid">
                            `;

                            const timing = result.metadata.four_step_timings;
                            const stepLabels = {
                                'step1_path_discovery': 'Step 1: Path Discovery',
                                'step2_path_selection': 'Step 2: Semantic Path Selection',
                                'step3_content_refinement': 'Step 3: Content Refinement',
                                'step4_memory_retrieval': 'Step 4: Memory Retrieval'
                            };

                            // Calculate total for percentages
                            const totalStepTime = Object.values(timing).reduce((sum, val) => sum + val, 0);

                            const stepKeys = ['step1_path_discovery', 'step2_path_selection', 'step3_content_refinement', 'step4_memory_retrieval'];
                            stepKeys.forEach((key, index) => {
                                const value = timing[key] || 0;
                                const label = stepLabels[key] || key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                                const percentage = totalStepTime > 0 ?
                                    Math.round((value / totalStepTime) * 100) : 0;

                                // Check if this step involves LLM (steps 2 and 3 = path selection and content refinement)
                                const hasPrompt = (index === 1 || index === 2) && result.metadata.llm_prompts;
                                let promptButton = '';
                                if (hasPrompt) {
                                    const promptKey = index === 1 ? 'path_selection' : 'content_refinement';
                                    const prompt = result.metadata.llm_prompts[promptKey];
                                    if (prompt) {
                                        promptButton = `<button class="prompt-btn recall-prompt-btn" data-prompt="${encodeURIComponent(prompt)}" style="
                                            margin-left: 10px;
                                            padding: 4px 8px;
                                            font-size: 11px;
                                            background: var(--accent-secondary);
                                            color: white;
                                            border: none;
                                            border-radius: 3px;
                                            cursor: pointer;
                                            opacity: 0.8;
                                            transition: opacity 0.2s;
                                        ">View Prompt</button>`;
                                    }
                                }

                                recallContent += `
                                    <div class="timing-item">
                                        <div class="timing-label">
                                            ${label}
                                            ${promptButton}
                                        </div>
                                        <div class="timing-value">
                                            <span class="timing-duration">${value}s</span>
                                            <span class="timing-percentage">(${percentage}%)</span>
                                        </div>
                                        <div class="timing-bar">
                                            <div class="timing-fill" style="width: ${percentage}%"></div>
                                        </div>
                                    </div>
                                `;
                            });

                            recallContent += `
                                    </div>
                                </div>
                            `;
                        }

                        recallContent += `</div>`;
                    }

                    // Display search results
                    if (result.results && result.results.length > 0) {
                        recallContent += `<div class="recall-results">`;
                        result.results.forEach((item, index) => {
                            const fullPath = `${item.namespace || 'default'}:${item.path}`;
                            const itemId = `recall-item-${index}`;
                            recallContent += `
                                <div class="recall-item" id="${itemId}">
                                    <div class="recall-item-header">
                                        <div class="recall-path-section">
                                            <div class="recall-path-main">
                                                <span class="recall-path-label">Path:</span>
                                                <span class="recall-path">${item.path}</span>
                                                <button class="copy-btn" onclick="copyToClipboard('${item.path.replace(/'/g, "\\'")}', this)" title="Copy path">📋</button>
                                            </div>
                                            <div class="recall-path-full">
                                                <span class="recall-path-label">Full Key:</span>
                                                <span class="recall-fullpath">${fullPath}</span>
                                                <button class="copy-btn" onclick="copyToClipboard('${fullPath.replace(/'/g, "\\'")}', this)" title="Copy full key">📋</button>
                                            </div>
                                            <div class="recall-namespace">
                                                <span class="recall-path-label">Namespace:</span>
                                                <span class="recall-namespace-value">${item.namespace || 'default'}</span>
                                                <button class="copy-btn" onclick="copyToClipboard('${(item.namespace || 'default').replace(/'/g, "\\'")}', this)" title="Copy namespace">📋</button>
                                            </div>
                                        </div>
                                        <span class="recall-score">${(item.relevance_score * 100).toFixed(0)}% match</span>
                                    </div>
                                    <div class="recall-item-content">
                                        <div class="recall-content-header">
                                            <span class="recall-content-label">Content:</span>
                                            <button class="copy-btn" onclick="copyToClipboard(\`${escapeHtml(item.content).replace(/`/g, '\\`').replace(/\\/g, '\\\\')}\`, this)" title="Copy content">📋</button>
                                        </div>
                                        <div class="recall-content-text">${escapeHtml(item.content)}</div>
                                    </div>
                                </div>
                            `;
                        });
                        recallContent += `</div>`;
                    } else {


                        recallContent += `<div class="recall-no-results">No relevant memories found for your query.</div>`;
                    }

                    recallContent += `</div>`;

                    // Complete progress and close modal
                    updateProgressModalWithTime(progressModal, 'Recall completed!', 100);
                    setTimeout(() => closeProgressModal(progressModal), 500);

                    // Store the recall data globally for the Answer button
                    window.lastRecallData = {
                        query: query,
                        person: person,
                        results: result.results || [],
                        metadata: result.metadata || {}
                    };

                    // Create and show results modal
                    const modal = document.createElement('div');
                    modal.className = 'recall-modal';
                    modal.innerHTML = `
                        <div class="recall-modal-content">
                            <div class="recall-modal-header">
                                <h2>🔍 Memory Recall</h2>
                                <button class="recall-modal-close">&times;</button>
                            </div>
                            <div class="recall-modal-body">
                                ${recallContent}
                            </div>
                            <div class="recall-modal-footer">
                                <button class="recall-button secondary" onclick="closeRecallModal()">Close</button>
                                <button class="recall-button primary" onclick="copyRecallToClipboard()">Copy Results</button>
                                <button class="recall-button primary" onclick="answerWithMemories()">
                                    💡 Answer
                                </button>
                            </div>
                        </div>
                    `;

                    // Add CSS for recall modal (reuse summary modal styles)
                    if (!document.getElementById('recall-modal-styles')) {
                        const styles = document.createElement('style');
                        styles.id = 'recall-modal-styles';
                        styles.textContent = `
                            .recall-modal {
                                position: fixed;
                                top: 0;
                                left: 0;
                                width: 100%;
                                height: 100%;
                                background: rgba(0, 0, 0, 0.8);
                                backdrop-filter: blur(10px);
                                z-index: 10000;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                animation: fadeIn 0.3s ease-out;
                            }

                            .recall-modal-content {
                                background: var(--bg-primary);
                                border: 1px solid var(--border-light);
                                border-radius: 16px;
                                max-width: 900px;
                                width: 90%;
                                max-height: 80vh;
                                display: flex;
                                flex-direction: column;
                                animation: slideIn 0.3s ease-out;
                                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
                            }

                            .recall-modal-header {
                                padding: 20px 30px;
                                border-bottom: 1px solid var(--border-light);
                                display: flex;
                                justify-content: space-between;
                                align-items: center;
                                background: var(--bg-glass);
                                border-radius: 16px 16px 0 0;
                            }

                            .recall-modal-header h2 {
                                margin: 0;
                                color: var(--text-primary);
                                font-size: 24px;
                            }

                            .recall-modal-close {
                                background: none;
                                border: none;
                                color: var(--text-secondary);
                                font-size: 28px;
                                cursor: pointer;
                                padding: 0;
                                width: 32px;
                                height: 32px;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                border-radius: 6px;
                                transition: all 0.2s ease;
                            }

                            .recall-modal-close:hover {
                                background: rgba(255, 255, 255, 0.1);
                                color: var(--text-primary);
                            }

                            .recall-modal-body {
                                padding: 30px;
                                overflow-y: auto;
                                flex: 1;
                            }

                            .recall-content h3 {
                                margin-top: 0;
                                margin-bottom: 20px;
                                color: var(--accent-primary);
                            }

                            .recall-query {
                                padding: 15px;
                                background: rgba(34, 211, 238, 0.1);
                                border-radius: 8px;
                                border: 1px solid rgba(34, 211, 238, 0.3);
                                margin-bottom: 20px;
                                font-size: 14px;
                                color: var(--text-primary);
                            }

                            .recall-metadata {
                                margin-bottom: 25px;
                                padding: 15px;
                                background: rgba(168, 85, 247, 0.1);
                                border-radius: 12px;
                                border: 1px solid rgba(168, 85, 247, 0.2);
                            }

                            .timing-breakdown {
                                margin-top: 20px;
                                padding: 15px;
                                background: rgba(34, 211, 238, 0.1);
                                border-radius: 12px;
                                border: 1px solid rgba(34, 211, 238, 0.2);
                            }

                            .timing-header {
                                font-size: 14px;
                                font-weight: 600;
                                color: var(--text-primary);
                                margin-bottom: 12px;
                                display: flex;
                                align-items: center;
                                gap: 6px;
                            }

                            .timing-grid {
                                display: flex;
                                flex-direction: column;
                                gap: 8px;
                            }

                            .timing-item {
                                display: flex;
                                flex-direction: column;
                                gap: 4px;
                            }

                            .timing-label {
                                font-size: 12px;
                                color: var(--text-secondary);
                                font-weight: 500;
                            }

                            .timing-value {
                                display: flex;
                                justify-content: space-between;
                                align-items: center;
                            }

                            .timing-duration {
                                font-size: 13px;
                                font-weight: 600;
                                color: var(--text-primary);
                                font-family: 'SF Mono', Monaco, monospace;
                            }

                            .timing-percentage {
                                font-size: 11px;
                                color: var(--text-secondary);
                                font-family: 'SF Mono', Monaco, monospace;
                            }

                            .timing-bar {
                                height: 4px;
                                background: rgba(255, 255, 255, 0.1);
                                border-radius: 2px;
                                overflow: hidden;
                                margin-top: 2px;
                            }

                            .timing-fill {
                                height: 100%;
                                background: linear-gradient(90deg, #22d3ee, #06b6d4);
                                border-radius: 2px;
                                transition: width 0.3s ease;
                            }

                            .recall-results {
                                display: flex;
                                flex-direction: column;
                                gap: 15px;
                            }

                            .recall-item {
                                padding: 15px;
                                background: var(--bg-glass);
                                border-radius: 10px;
                                border: 1px solid var(--border-light);
                                transition: all 0.2s ease;
                            }

                            .recall-item:hover {
                                border-color: var(--accent-primary);
                                box-shadow: 0 4px 12px rgba(34, 211, 238, 0.1);
                            }

                            .recall-item-header {
                                display: flex;
                                justify-content: space-between;
                                align-items: center;
                                margin-bottom: 10px;
                            }

                            .recall-path {
                                font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
                                font-size: 13px;
                                color: var(--accent-primary);
                                font-weight: 600;
                            }

                            .recall-score {
                                font-size: 12px;
                                color: var(--text-secondary);
                                background: rgba(34, 211, 238, 0.1);
                                padding: 4px 8px;
                                border-radius: 4px;
                            }

                            .recall-item-content {
                                font-size: 14px;
                                color: var(--text-primary);
                                line-height: 1.6;
                                margin-bottom: 10px;
                            }

                            .recall-item-metadata {
                                font-size: 12px;
                                color: var(--text-secondary);
                                display: flex;
                                gap: 8px;
                            }

                            .recall-meta-label {
                                font-weight: 600;
                            }

                            .recall-no-results {
                                padding: 40px;
                                text-align: center;
                                color: var(--text-secondary);
                                font-size: 16px;
                            }

                            .recall-modal-footer {
                                padding: 20px 30px;
                                border-top: 1px solid var(--border-light);
                                display: flex;
                                gap: 15px;
                                justify-content: flex-end;
                                background: var(--bg-glass);
                            }

                            .recall-button {
                                padding: 10px 20px;
                                border: none;
                                border-radius: 8px;
                                font-size: 14px;
                                cursor: pointer;
                                transition: all 0.2s ease;
                                font-weight: 500;
                            }

                            .recall-button.primary {
                                background: var(--accent-primary);
                                color: white;
                            }

                            .recall-button.primary:hover {
                                background: var(--accent-secondary);
                                transform: translateY(-1px);
                            }

                            .recall-button.secondary {
                                background: var(--bg-glass);
                                color: var(--text-primary);
                                border: 1px solid var(--border-light);
                            }

                            .recall-button.secondary:hover {
                                background: var(--bg-glass-light);
                                transform: translateY(-1px);
                            }

                            /* Enhanced path and copy functionality styles */
                            .recall-path-section {
                                display: flex;
                                flex-direction: column;
                                gap: 8px;
                                flex: 1;
                            }

                            .recall-path-main, .recall-path-full, .recall-namespace {
                                display: flex;
                                align-items: center;
                                gap: 8px;
                            }

                            .recall-path-label {
                                font-size: 11px;
                                font-weight: 600;
                                color: var(--text-secondary);
                                min-width: 70px;
                                text-transform: uppercase;
                                letter-spacing: 0.5px;
                            }

                            .recall-fullpath {
                                font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
                                font-size: 12px;
                                color: var(--accent-secondary);
                                font-weight: 500;
                            }

                            .recall-namespace-value {
                                font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
                                font-size: 12px;
                                color: var(--text-primary);
                                font-weight: 500;
                            }

                            .copy-btn {
                                background: var(--bg-glass);
                                border: 1px solid var(--border-light);
                                border-radius: 4px;
                                padding: 2px 6px;
                                font-size: 12px;
                                cursor: pointer;
                                transition: all 0.2s ease;
                                color: var(--text-secondary);
                                opacity: 0.7;
                            }

                            .copy-btn:hover {
                                background: var(--accent-primary);
                                color: white;
                                opacity: 1;
                                transform: translateY(-1px);
                            }

                            .recall-content-header {
                                display: flex;
                                justify-content: space-between;
                                align-items: center;
                                margin-bottom: 8px;
                            }

                            .recall-content-label {
                                font-size: 11px;
                                font-weight: 600;
                                color: var(--text-secondary);
                                text-transform: uppercase;
                                letter-spacing: 0.5px;
                            }

                            .recall-content-text {
                                font-size: 14px;
                                color: var(--text-primary);
                                line-height: 1.6;
                                padding: 10px;
                                background: rgba(0, 0, 0, 0.1);
                                border-radius: 6px;
                                border-left: 3px solid var(--accent-primary);
                            }
                        `;
                        document.head.appendChild(styles);
                    }

                    // Store results for clipboard copying
                    window.currentRecallResults = result;

                    // Add modal to DOM
                    document.body.appendChild(modal);

                    // Add event listeners
                    modal.querySelector('.recall-modal-close').onclick = () => document.body.removeChild(modal);
                    modal.onclick = (e) => {
                        if (e.target === modal) document.body.removeChild(modal);
                    };

                    // Add prompt button functionality
                    const recallPromptBtns = modal.querySelectorAll('.recall-prompt-btn');
                    recallPromptBtns.forEach(btn => {
                        btn.addEventListener('click', () => {
                            const encodedPrompt = btn.getAttribute('data-prompt');
                            const prompt = decodeURIComponent(encodedPrompt);
                            showPromptModal(prompt);
                        });
                    });

                    // Global functions for modal buttons
                    window.closeRecallModal = () => {
                        const modal = document.querySelector('.recall-modal');
                        if (modal) document.body.removeChild(modal);
                    };

                    window.answerWithMemories = async () => {
                        if (!window.lastRecallData) {
                            showNotification('No recall data available', 'error');
                            return;
                        }

                        const { query, person, results } = window.lastRecallData;

                        // Close the recall modal first
                        closeRecallModal();

                        // Show progress modal
                        const progressModal = showProgressModal('Generating Answer', 'Using memories to answer your question...');

                        try {
                            // Prepare the memories text
                            const memoriesText = results.map(item =>
                                `Path: ${item.path}\nContent: ${item.content}`
                            ).join('\n\n');

                            // Call the API to get the answer
                            const response = await fetch('/api/answer', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                },
                                body: JSON.stringify({
                                    path: connectedStorePath,
                                    query: query,
                                    memories: memoriesText,
                                    person: person
                                })
                            });

                            if (!response.ok) {
                                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                            }

                            const result = await response.json();

                            // Close progress modal
                            closeProgressModal(progressModal);

                            if (result.success) {
                                // Show answer modal with prompt and response
                                showAnswerModal(query, result.prompt, result.answer, memoriesText);
                            } else {
                                showNotification(`Failed to generate answer: ${result.error}`, 'error');
                            }
                        } catch (error) {
                            closeProgressModal(progressModal);
                            console.error('Answer generation error:', error);
                            showNotification(`Error generating answer: ${error.message}`, 'error');
                        }
                    };

                    window.copyRecallToClipboard = () => {
                        if (window.currentRecallResults) {
                            let textResults = `Memory Recall Results\n`;
                            textResults += `Query: "${query}"\n\n`;

                            if (window.currentRecallResults.metadata) {
                                textResults += `Results Found: ${window.currentRecallResults.metadata.results_count || 0}\n`;
                                textResults += `Search Time: ${window.currentRecallResults.metadata.search_time || 'N/A'}\n\n`;
                            }

                            if (window.currentRecallResults.results && window.currentRecallResults.results.length > 0) {
                                window.currentRecallResults.results.forEach((item, index) => {
                                    textResults += `--- Result ${index + 1} ---\n`;
                                    textResults += `Path: ${item.path}\n`;
                                    textResults += `Relevance: ${(item.relevance_score * 100).toFixed(0)}%\n`;
                                    textResults += `Content: ${item.content}\n`;
                                    if (item.namespace) {
                                        textResults += `Namespace: ${item.namespace}\n`;
                                    }
                                    textResults += `\n`;
                                });
                            } else {
                                textResults += 'No relevant memories found.\n';
                            }

                            navigator.clipboard.writeText(textResults).then(() => {
                                showNotification('Recall results copied to clipboard', 'success');
                            }).catch(err => {
                                console.error('Failed to copy:', err);
                                showNotification('Failed to copy results', 'error');
                            });
                        }
                    };

                } else {
                    throw new Error(result.error || 'Unknown error occurred');
                }
            } catch (error) {
                console.error('Recall error:', error);
                cleanupProgress(); // Stop the progress updates
                closeProgressModal(progressModal);

                if (error.name === 'AbortError') {
                    showNotification('Recall search cancelled', 'info');
                } else {
                    showNotification(`Error recalling memories: ${error.message}`, 'error', 5000);
                }
            }
        }

        function showProgressModal(title, message) {
            // Create progress modal
            const modal = document.createElement('div');
            modal.className = 'progress-modal';
            modal.innerHTML = `
                <div class="progress-modal-content">
                    <div class="progress-modal-header">
                        <h3>${title}</h3>
                    </div>
                    <div class="progress-modal-body">
                        <div class="progress-message">${message}</div>
                        <div class="progress-container">
                            <div class="progress-bar">
                                <div class="progress-fill" style="width: 0%"></div>
                            </div>
                            <div class="progress-percentage">0%</div>
                        </div>
                        <div class="progress-actions">
                            <button class="progress-cancel-btn">Cancel</button>
                        </div>
                    </div>
                </div>
            `;

            // Add CSS for progress modal
            if (!document.getElementById('progress-modal-styles')) {
                const styles = document.createElement('style');
                styles.id = 'progress-modal-styles';
                styles.textContent = `
                    .progress-modal {
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        background: rgba(0, 0, 0, 0.7);
                        backdrop-filter: blur(8px);
                        z-index: 10001;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        animation: fadeIn 0.3s ease-out;
                    }

                    .progress-modal-content {
                        background: var(--bg-primary);
                        border: 1px solid var(--border-light);
                        border-radius: 16px;
                        width: 400px;
                        max-width: 90%;
                        overflow: hidden;
                        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                        animation: slideIn 0.3s ease-out;
                    }

                    .progress-modal-header {
                        padding: 20px 24px 16px;
                        background: var(--bg-glass);
                        border-bottom: 1px solid var(--border-light);
                    }

                    .progress-modal-header h3 {
                        margin: 0;
                        color: var(--text-primary);
                        font-size: 1.2em;
                        font-weight: 600;
                    }

                    .progress-modal-body {
                        padding: 24px;
                    }

                    .progress-message {
                        color: var(--text-secondary);
                        margin-bottom: 20px;
                        font-size: 14px;
                    }

                    .progress-container {
                        margin-bottom: 20px;
                    }

                    .progress-bar {
                        width: 100%;
                        height: 8px;
                        background: var(--bg-glass);
                        border-radius: 4px;
                        overflow: hidden;
                        margin-bottom: 8px;
                        border: 1px solid var(--border-light);
                    }

                    .progress-fill {
                        height: 100%;
                        background: linear-gradient(90deg, var(--accent-primary), var(--accent-secondary));
                        transition: width 0.3s ease;
                        border-radius: 4px;
                    }

                    .progress-percentage {
                        text-align: center;
                        color: var(--text-muted);
                        font-size: 12px;
                        font-weight: 500;
                    }

                    .progress-actions {
                        display: flex;
                        justify-content: center;
                    }

                    .progress-cancel-btn {
                        padding: 8px 16px;
                        background: var(--bg-glass);
                        border: 1px solid var(--border-light);
                        border-radius: 8px;
                        color: var(--text-primary);
                        cursor: pointer;
                        font-size: 14px;
                        transition: all 0.2s ease;
                    }

                    .progress-cancel-btn:hover {
                        background: var(--bg-glass-light);
                        transform: translateY(-1px);
                    }
                `;
                document.head.appendChild(styles);
            }

            // Add to DOM
            document.body.appendChild(modal);

            // Add cancel functionality
            const cancelBtn = modal.querySelector('.progress-cancel-btn');
            cancelBtn.onclick = () => {
                if (modal.abortController) {
                    modal.abortController.abort();
                }
                closeProgressModal(modal);
            };

            return modal;
        }

        function updateProgressModal(modal, message, percentage) {
            const messageEl = modal.querySelector('.progress-message');
            const fillEl = modal.querySelector('.progress-fill');
            const percentEl = modal.querySelector('.progress-percentage');

            if (messageEl) messageEl.textContent = message;
            if (fillEl) fillEl.style.width = `${percentage}%`;
            if (percentEl) percentEl.textContent = `${percentage}%`;
        }

        function updateProgressModalWithTime(modal, message, percentage) {
            const elapsedMs = Date.now() - (modal.startTime || Date.now());
            const elapsedSec = (elapsedMs / 1000).toFixed(1);
            const messageWithTime = `${message} (${elapsedSec}s)`;

            updateProgressModal(modal, messageWithTime, percentage);
        }

        function closeProgressModal(modal) {
            if (modal && modal.parentNode) {
                document.body.removeChild(modal);
            }
        }

        function showRememberResultsModal(result) {
            // Create modal overlay
            const modal = document.createElement('div');
            modal.className = 'remember-results-modal';
            modal.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0, 0, 0, 0.7);
                z-index: 1000;
                display: flex;
                justify-content: center;
                align-items: center;
            `;

            // Format timing breakdown
            const timings = result.five_step_timings || {};
            const timingBars = Object.entries(timings).map(([step, time], index) => {
                const stepNames = [
                    'Store Initialization',
                    'Classification & Path Generation',
                    'Memory Storage',
                    'Timeline Processing',
                    'Location Processing'
                ];
                const percentage = time > 0 ? Math.max(10, Math.min(100, (time / Math.max(0.1, Object.values(timings).reduce((a, b) => Math.max(a, b), 0.1)) * 100))) : 0;

                // Check if this step involves LLM (step 2 = classification)
                const hasPrompt = index === 1 && result.classification_prompt;
                const promptButton = hasPrompt ? `<button class="prompt-btn" data-prompt="${encodeURIComponent(result.classification_prompt)}" style="
                    margin-left: 10px;
                    padding: 4px 8px;
                    font-size: 11px;
                    background: var(--accent-secondary);
                    color: white;
                    border: none;
                    border-radius: 3px;
                    cursor: pointer;
                    opacity: 0.8;
                    transition: opacity 0.2s;
                ">View Prompt</button>` : '';

                return `
                    <div class="timing-step">
                        <div class="step-name">
                            ${stepNames[index] || step}
                            ${promptButton}
                        </div>
                        <div class="progress-bar-container">
                            <div class="progress-bar-fill" style="width: ${percentage}%"></div>
                        </div>
                        <div class="step-time">${time.toFixed(3)}s</div>
                    </div>
                `;
            }).join('');

            // Format timeline events if present
            let timelineSection = '';
            if (result.timeline_events && result.timeline_events.length > 0) {
                timelineSection = `
                    <div class="timeline-events-section">
                        <h4>🕒 Timeline Events Detected:</h4>
                        <ul class="timeline-events-list">
                            ${result.timeline_events.map(event => `
                                <li>${event.description || event.event || JSON.stringify(event)}</li>
                            `).join('')}
                        </ul>
                    </div>
                `;
            }

            modal.innerHTML = `
                <div class="modal-content" style="
                    background: var(--bg-primary);
                    color: var(--text-primary);
                    padding: 30px;
                    border-radius: 12px;
                    max-width: 800px;
                    width: 90%;
                    max-height: 80vh;
                    overflow-y: auto;
                    box-shadow: 0 20px 60px var(--shadow);
                    border: 1px solid var(--border-light);
                ">
                    <div class="modal-header" style="
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-bottom: 20px;
                        padding-bottom: 15px;
                        border-bottom: 2px solid var(--border-light);
                    ">
                        <h2 style="margin: 0; color: var(--success); font-size: 24px;">
                            ✅ Memory Stored Successfully
                        </h2>
                        <button class="close-btn" style="
                            background: none;
                            border: none;
                            font-size: 24px;
                            cursor: pointer;
                            color: var(--text-secondary);
                            padding: 5px;
                        ">&times;</button>
                    </div>

                    <div class="remember-results-content">
                        <!-- Memory Details -->
                        <div class="memory-details" style="margin-bottom: 25px;">
                            <h3 style="color: var(--success); margin-bottom: 15px;">📝 Memory Details</h3>
                            <div class="detail-row" style="margin-bottom: 10px;">
                                <strong>Path:</strong> <code style="background: var(--bg-secondary); color: var(--text-primary); padding: 2px 6px; border-radius: 3px; border: 1px solid var(--border-light);">${result.key}</code>
                                <button class="copy-btn" data-copy="${result.key}" style="margin-left: 10px; padding: 4px 8px; font-size: 12px; background: var(--accent-primary); color: white; border: none; border-radius: 3px; cursor: pointer;">Copy</button>
                            </div>
                            <div class="detail-row" style="margin-bottom: 10px;">
                                <strong>Full Key:</strong> <code style="background: var(--bg-secondary); color: var(--text-primary); padding: 2px 6px; border-radius: 3px; border: 1px solid var(--border-light);">${result.full_key}</code>
                                <button class="copy-btn" data-copy="${result.full_key}" style="margin-left: 10px; padding: 4px 8px; font-size: 12px; background: var(--accent-primary); color: white; border: none; border-radius: 3px; cursor: pointer;">Copy</button>
                            </div>
                            <div class="detail-row" style="margin-bottom: 10px;">
                                <strong>Confidence:</strong> <span style="color: ${result.confidence > 0.8 ? 'var(--success)' : result.confidence > 0.5 ? 'var(--warning)' : 'var(--error)'};">${(result.confidence * 100).toFixed(0)}%</span>
                            </div>
                            <div class="detail-row" style="margin-bottom: 10px;">
                                <strong>Namespace:</strong> ${result.namespace}
                            </div>
                            ${result.commit_hash ? `
                                <div class="detail-row" style="margin-bottom: 10px;">
                                    <strong>Commit:</strong> ${result.commit_hash}
                                </div>
                            ` : ''}
                            ${result.commit_date ? `
                                <div class="detail-row" style="margin-bottom: 10px;">
                                    <strong>Date:</strong> ${new Date(result.commit_date).toLocaleString()}
                                </div>
                            ` : ''}
                        </div>

                        <!-- Stored Content -->
                        <div class="stored-content" style="margin-bottom: 25px;">
                            <h3 style="color: var(--success); margin-bottom: 15px;">💾 Stored Content</h3>
                            <div class="content-box" style="
                                background: var(--bg-secondary);
                                color: var(--text-primary);
                                border: 1px solid var(--border-light);
                                border-radius: 8px;
                                padding: 15px;
                                max-height: 200px;
                                overflow-y: auto;
                                font-family: 'JetBrains Mono', monospace;
                                white-space: pre-wrap;
                                word-wrap: break-word;
                            ">${result.content}</div>
                            <button class="copy-btn" data-copy="${result.content}" style="margin-top: 10px; padding: 6px 12px; background: var(--success); color: white; border: none; border-radius: 3px; cursor: pointer;">Copy Content</button>
                        </div>

                        <!-- Classification Reasoning -->
                        <div class="classification-reasoning" style="margin-bottom: 25px;">
                            <h3 style="color: var(--success); margin-bottom: 15px;">🧠 Classification Reasoning</h3>
                            <div style="
                                background: var(--bg-glass);
                                border-left: 4px solid var(--accent-primary);
                                padding: 15px;
                                border-radius: 0 8px 8px 0;
                                font-style: italic;
                                color: var(--text-primary);
                                border: 1px solid var(--border-light);
                                border-left: 4px solid var(--accent-primary);
                            ">${result.reasoning}</div>
                        </div>

                        <!-- Performance Timing -->
                        <div class="performance-timing" style="margin-bottom: 25px;">
                            <h3 style="color: var(--success); margin-bottom: 15px;">⚡ Performance Breakdown</h3>
                            <div class="timing-breakdown" style="
                                background: var(--bg-secondary);
                                border: 1px solid var(--border-light);
                                border-radius: 8px;
                                padding: 20px;
                            ">
                                ${timingBars}
                                <div class="total-time" style="
                                    margin-top: 15px;
                                    padding-top: 15px;
                                    border-top: 2px solid var(--border-light);
                                    font-weight: bold;
                                    color: var(--success);
                                ">
                                    Total Time: ${(result.step_timings.total_remember || 0).toFixed(3)}s
                                </div>
                            </div>
                        </div>

                        ${timelineSection}
                    </div>
                </div>
            `;

            // Add click handlers
            const closeBtn = modal.querySelector('.close-btn');
            closeBtn.addEventListener('click', () => {
                document.body.removeChild(modal);
            });

            // Close on backdrop click
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    document.body.removeChild(modal);
                }
            });

            // Add copy functionality
            const copyBtns = modal.querySelectorAll('.copy-btn');
            copyBtns.forEach(btn => {
                btn.addEventListener('click', () => {
                    const textToCopy = btn.getAttribute('data-copy');
                    navigator.clipboard.writeText(textToCopy).then(() => {
                        btn.textContent = 'Copied!';
                        btn.style.background = 'var(--success)';
                        setTimeout(() => {
                            btn.textContent = btn.getAttribute('data-copy') === result.content ? 'Copy Content' : 'Copy';
                            btn.style.background = btn.getAttribute('data-copy') === result.content ? 'var(--success)' : 'var(--accent-primary)';
                        }, 2000);
                    }).catch(() => {
                        btn.textContent = 'Copy failed';
                        setTimeout(() => {
                            btn.textContent = btn.getAttribute('data-copy') === result.content ? 'Copy Content' : 'Copy';
                        }, 2000);
                    });
                });
            });

            // Add prompt button functionality
            const promptBtns = modal.querySelectorAll('.prompt-btn');
            promptBtns.forEach(btn => {
                btn.addEventListener('click', () => {
                    const encodedPrompt = btn.getAttribute('data-prompt');
                    const prompt = decodeURIComponent(encodedPrompt);
                    showPromptModal(prompt);
                });
            });

            // Add styles for timing breakdown
            const style = document.createElement('style');
            style.textContent = `
                .timing-step {
                    display: flex;
                    align-items: center;
                    margin-bottom: 10px;
                    gap: 15px;
                }
                .step-name {
                    min-width: 200px;
                    font-weight: 500;
                }
                .progress-bar-container {
                    flex: 1;
                    background: var(--bg-tertiary);
                    height: 20px;
                    border-radius: 10px;
                    overflow: hidden;
                    border: 1px solid var(--border-light);
                }
                .progress-bar-fill {
                    height: 100%;
                    background: linear-gradient(45deg, var(--accent-primary), var(--accent-secondary));
                    border-radius: 10px;
                    transition: width 0.3s ease;
                }
                .step-time {
                    min-width: 60px;
                    text-align: right;
                    font-weight: bold;
                    color: var(--accent-primary);
                }
                .timeline-events-list {
                    margin: 0;
                    padding-left: 20px;
                }
                .timeline-events-list li {
                    margin-bottom: 5px;
                }
            `;
            document.head.appendChild(style);

            document.body.appendChild(modal);
        }

        function showPromptModal(prompt) {
            // Create modal overlay
            const modal = document.createElement('div');
            modal.className = 'prompt-modal';
            modal.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0, 0, 0, 0.7);
                z-index: 10001;
                display: flex;
                justify-content: center;
                align-items: center;
            `;

            modal.innerHTML = `
                <div class="modal-content" style="
                    background: var(--bg-primary);
                    color: var(--text-primary);
                    padding: 30px;
                    border-radius: 12px;
                    max-width: 800px;
                    width: 90%;
                    max-height: 80vh;
                    overflow-y: auto;
                    box-shadow: 0 20px 60px var(--shadow);
                    border: 1px solid var(--border-light);
                ">
                    <div class="modal-header" style="
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-bottom: 20px;
                        padding-bottom: 15px;
                        border-bottom: 2px solid var(--border-light);
                    ">
                        <h2 style="margin: 0; color: var(--accent-primary); font-size: 24px;">
                            🤖 LLM Prompt Inspection
                        </h2>
                        <button class="close-btn" style="
                            background: none;
                            border: none;
                            font-size: 24px;
                            cursor: pointer;
                            color: var(--text-secondary);
                            padding: 5px;
                        ">&times;</button>
                    </div>
                    <div class="prompt-content">
                        <div style="margin-bottom: 15px;">
                            <button class="copy-prompt-btn" style="
                                padding: 8px 16px;
                                background: var(--success);
                                color: white;
                                border: none;
                                border-radius: 3px;
                                cursor: pointer;
                                margin-right: 10px;
                            ">Copy Prompt</button>
                            <span style="color: var(--text-secondary); font-size: 14px;">
                                This is the exact prompt sent to the LLM for classification
                            </span>
                        </div>
                        <div class="prompt-box" style="
                            background: var(--bg-secondary);
                            color: var(--text-primary);
                            border: 1px solid var(--border-light);
                            border-radius: 8px;
                            padding: 20px;
                            max-height: 500px;
                            overflow-y: auto;
                            font-family: 'JetBrains Mono', Monaco, 'Courier New', monospace;
                            white-space: pre-wrap;
                            word-wrap: break-word;
                            line-height: 1.4;
                            font-size: 13px;
                        ">${prompt}</div>
                    </div>
                </div>
            `;

            // Add event handlers
            const closeBtn = modal.querySelector('.close-btn');
            closeBtn.addEventListener('click', () => {
                document.body.removeChild(modal);
            });

            // Close on backdrop click
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    document.body.removeChild(modal);
                }
            });

            // Copy button functionality
            const copyBtn = modal.querySelector('.copy-prompt-btn');
            copyBtn.addEventListener('click', () => {
                navigator.clipboard.writeText(prompt).then(() => {
                    copyBtn.textContent = 'Copied!';
                    copyBtn.style.background = 'var(--accent-primary)';
                    setTimeout(() => {
                        copyBtn.textContent = 'Copy Prompt';
                        copyBtn.style.background = 'var(--success)';
                    }, 2000);
                }).catch(() => {
                    copyBtn.textContent = 'Copy failed';
                    setTimeout(() => {
                        copyBtn.textContent = 'Copy Prompt';
                    }, 2000);
                });
            });

            document.body.appendChild(modal);
        }

        function showAnswerModal(query, prompt, answer, memories) {
            // Create modal overlay
            const modal = document.createElement('div');
            modal.className = 'answer-modal';
            modal.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0, 0, 0, 0.8);
                backdrop-filter: blur(10px);
                z-index: 10001;
                display: flex;
                justify-content: center;
                align-items: center;
                animation: fadeIn 0.3s ease-out;
            `;

            modal.innerHTML = `
                <div class="modal-content" style="
                    background: var(--bg-primary);
                    color: var(--text-primary);
                    padding: 30px;
                    border-radius: 12px;
                    max-width: 900px;
                    width: 90%;
                    max-height: 85vh;
                    overflow-y: auto;
                    box-shadow: 0 20px 60px var(--shadow);
                    border: 1px solid var(--border-light);
                ">
                    <div class="modal-header" style="
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-bottom: 20px;
                        padding-bottom: 15px;
                        border-bottom: 2px solid var(--border-light);
                    ">
                        <h2 style="margin: 0; color: var(--accent-primary); font-size: 24px;">
                            💡 Memory-Based Answer
                        </h2>
                        <button class="close-btn" style="
                            background: none;
                            border: none;
                            font-size: 24px;
                            cursor: pointer;
                            color: var(--text-secondary);
                            padding: 5px;
                        ">&times;</button>
                    </div>

                    <div class="answer-content">
                        <!-- Original Question -->
                        <div style="margin-bottom: 25px;">
                            <h3 style="color: var(--accent-secondary); margin-bottom: 10px; font-size: 16px;">
                                📝 Question:
                            </h3>
                            <div style="
                                background: var(--bg-secondary);
                                padding: 15px;
                                border-radius: 8px;
                                border-left: 3px solid var(--accent-secondary);
                                font-size: 14px;
                            ">${escapeHtml(query)}</div>
                        </div>

                        <!-- Answer -->
                        <div style="margin-bottom: 25px;">
                            <h3 style="color: var(--success); margin-bottom: 10px; font-size: 16px;">
                                ✨ Answer:
                            </h3>
                            <div style="
                                background: var(--bg-secondary);
                                padding: 15px;
                                border-radius: 8px;
                                border-left: 3px solid var(--success);
                                font-size: 14px;
                                line-height: 1.6;
                                white-space: pre-wrap;
                            ">${escapeHtml(answer)}</div>
                        </div>

                        <!-- Collapsible Prompt Section -->
                        <details style="margin-bottom: 25px;">
                            <summary style="
                                cursor: pointer;
                                color: var(--accent-primary);
                                font-size: 16px;
                                font-weight: bold;
                                padding: 10px;
                                background: var(--bg-secondary);
                                border-radius: 8px;
                                user-select: none;
                            ">
                                🤖 View LLM Prompt
                            </summary>
                            <div style="
                                margin-top: 10px;
                                background: var(--bg-secondary);
                                padding: 15px;
                                border-radius: 8px;
                                font-family: 'JetBrains Mono', Monaco, 'Courier New', monospace;
                                font-size: 12px;
                                white-space: pre-wrap;
                                word-wrap: break-word;
                                max-height: 300px;
                                overflow-y: auto;
                                border: 1px solid var(--border-light);
                            ">${escapeHtml(prompt)}</div>
                        </details>

                        <!-- Collapsible Memories Section -->
                        <details style="margin-bottom: 20px;">
                            <summary style="
                                cursor: pointer;
                                color: var(--accent-primary);
                                font-size: 16px;
                                font-weight: bold;
                                padding: 10px;
                                background: var(--bg-secondary);
                                border-radius: 8px;
                                user-select: none;
                            ">
                                🧠 View Retrieved Memories
                            </summary>
                            <div style="
                                margin-top: 10px;
                                background: var(--bg-secondary);
                                padding: 15px;
                                border-radius: 8px;
                                font-family: 'JetBrains Mono', Monaco, 'Courier New', monospace;
                                font-size: 12px;
                                white-space: pre-wrap;
                                word-wrap: break-word;
                                max-height: 300px;
                                overflow-y: auto;
                                border: 1px solid var(--border-light);
                            ">${escapeHtml(memories)}</div>
                        </details>
                    </div>

                    <div class="modal-footer" style="
                        display: flex;
                        justify-content: flex-end;
                        gap: 10px;
                        margin-top: 20px;
                        padding-top: 15px;
                        border-top: 1px solid var(--border-light);
                    ">
                        <button class="close-modal-btn" style="
                            padding: 10px 20px;
                            background: var(--bg-tertiary);
                            color: var(--text-primary);
                            border: 1px solid var(--border-light);
                            border-radius: 6px;
                            cursor: pointer;
                            font-size: 14px;
                            transition: all 0.2s;
                        ">Close</button>
                        <button class="copy-answer-btn" style="
                            padding: 10px 20px;
                            background: var(--accent-primary);
                            color: white;
                            border: none;
                            border-radius: 6px;
                            cursor: pointer;
                            font-size: 14px;
                            transition: all 0.2s;
                        ">Copy Answer</button>
                    </div>
                </div>
            `;

            // Add event handlers
            const closeBtn = modal.querySelector('.close-btn');
            const closeModalBtn = modal.querySelector('.close-modal-btn');
            const copyBtn = modal.querySelector('.copy-answer-btn');

            const closeModal = () => {
                modal.style.animation = 'fadeOut 0.3s ease-out';
                setTimeout(() => document.body.removeChild(modal), 300);
            };

            closeBtn.addEventListener('click', closeModal);
            closeModalBtn.addEventListener('click', closeModal);

            // Close on backdrop click
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    closeModal();
                }
            });

            // Copy button functionality
            copyBtn.addEventListener('click', () => {
                const fullText = `Question: ${query}\n\nAnswer: ${answer}`;
                navigator.clipboard.writeText(fullText).then(() => {
                    copyBtn.textContent = 'Copied!';
                    copyBtn.style.background = 'var(--success)';
                    setTimeout(() => {
                        copyBtn.textContent = 'Copy Answer';
                        copyBtn.style.background = 'var(--accent-primary)';
                    }, 2000);
                }).catch(() => {
                    copyBtn.textContent = 'Copy failed';
                    setTimeout(() => {
                        copyBtn.textContent = 'Copy Answer';
                    }, 2000);
                });
            });

            // Add fadeIn animation
            if (!document.getElementById('answer-modal-animation')) {
                const style = document.createElement('style');
                style.id = 'answer-modal-animation';
                style.textContent = `
                    @keyframes fadeIn {
                        from { opacity: 0; }
                        to { opacity: 1; }
                    }
                    @keyframes fadeOut {
                        from { opacity: 1; }
                        to { opacity: 0; }
                    }
                `;
                document.head.appendChild(style);
            }

            document.body.appendChild(modal);
        }

        function showNodeDetailsPopup(nodeData, event) {
            // Close any existing node popup
            const existingPopup = document.querySelector('.node-details-popup');
            if (existingPopup) {
                document.body.removeChild(existingPopup);
            }

            // Find node data from current store
            let nodeInfo = null;
            let nodeContent = '';
            let nodeNamespace = 'default';
            let fullPath = nodeData.id;

            // Try to find the node in the current data
            if (window.realStoreData && window.realStoreData.memories) {
                // Look through memories to find this path
                for (const memory of window.realStoreData.memories) {
                    if (memory.path === nodeData.id) {
                        nodeInfo = memory;
                        nodeContent = memory.content || '';
                        nodeNamespace = memory.namespace || 'default';
                        fullPath = `${nodeNamespace}:${memory.path}`;
                        break;
                    }
                }
            }

            // If not found in memories, check if it's demo data
            if (!nodeInfo && window.demoData && window.demoData.memories) {
                for (const memory of window.demoData.memories) {
                    if (memory.path === nodeData.id) {
                        nodeInfo = memory;
                        nodeContent = memory.content || '';
                        nodeNamespace = memory.namespace || 'demo';
                        fullPath = `${nodeNamespace}:${memory.path}`;
                        break;
                    }
                }
            }

            // Create popup
            const popup = document.createElement('div');
            popup.className = 'node-details-popup';

            popup.innerHTML = `
                <div class="node-popup-content">
                    <div class="node-popup-header">
                        <h3>📍 Memory Details</h3>
                        <button class="node-popup-close">&times;</button>
                    </div>
                    <div class="node-popup-body">
                        <div class="node-path-section">
                            <div class="node-path-full">
                                <span class="node-path-label">FULL KEY:</span>
                                <span class="node-fullpath-value">${fullPath}</span>
                                <button class="copy-btn" onclick="copyToClipboard('${fullPath.replace(/'/g, "\\'")}', this)" title="Copy full key">Copy</button>
                            </div>
                            <div class="node-namespace">
                                <span class="node-path-label">NAMESPACE:</span>
                                <span class="node-namespace-value">${nodeNamespace}</span>
                                <button class="copy-btn" onclick="copyToClipboard('${nodeNamespace.replace(/'/g, "\\'")}', this)" title="Copy namespace">Copy</button>
                            </div>
                        </div>
                        <div class="node-content-section">
                            <div class="node-content-header">
                                <span class="node-content-label">CONTENT:</span>
                                ${nodeContent ? `<button class="copy-btn" onclick="copyToClipboard(\`${nodeContent.replace(/`/g, '\\`').replace(/\\/g, '\\\\')}\`, this)" title="Copy content">Copy</button>` : ''}
                            </div>
                            ${nodeContent ? `
                                <div class="node-content-text">${escapeHtml(nodeContent)}</div>
                            ` : `
                                <div class="node-no-content">
                                    <span class="no-content-text">No content stored for this path</span>
                                </div>
                            `}
                        </div>
                        <div class="node-meta-section">
                            <div class="node-meta-item">
                                <span class="node-meta-label">TYPE:</span>
                                <span class="node-meta-value">${nodeData.group === 1 ? 'Root' : nodeData.group === 2 ? 'Branch' : 'Leaf'}</span>
                            </div>
                            <div class="node-meta-item">
                                <span class="node-meta-label">CONNECTIONS:</span>
                                <span class="node-meta-value">${nodeData.connections || 0}</span>
                            </div>
                        </div>
                        <div class="node-actions-section">
                            <button class="node-summarize-btn" onclick="summarizeNodePath('${fullPath.replace(/'/g, "\\'")}')">
                                📋 Summarize Keys
                            </button>
                        </div>
                    </div>
                </div>
            `;

            // Add styles for node popup
            if (!document.getElementById('node-popup-styles')) {
                const styles = document.createElement('style');
                styles.id = 'node-popup-styles';
                styles.textContent = `
                    .node-details-popup {
                        position: fixed;
                        top: 0;
                        left: 0;
                        right: 0;
                        bottom: 0;
                        background: rgba(0, 0, 0, 0.8);
                        backdrop-filter: blur(8px);
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        z-index: 10000;
                        animation: fadeIn 0.2s ease;
                    }

                    .node-popup-content {
                        background: var(--bg-primary);
                        border-radius: 16px;
                        border: 1px solid var(--border-light);
                        max-width: 600px;
                        width: 90%;
                        max-height: 80vh;
                        overflow-y: auto;
                        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
                    }

                    .node-popup-header {
                        padding: 20px 25px;
                        border-bottom: 1px solid var(--border-light);
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        background: var(--bg-glass);
                    }

                    .node-popup-header h3 {
                        margin: 0;
                        color: var(--accent-primary);
                        font-size: 18px;
                        font-weight: 600;
                    }

                    .node-popup-close {
                        background: none;
                        border: none;
                        font-size: 24px;
                        color: var(--text-secondary);
                        cursor: pointer;
                        padding: 0;
                        width: 32px;
                        height: 32px;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        transition: all 0.2s ease;
                    }

                    .node-popup-close:hover {
                        background: var(--bg-glass);
                        color: var(--accent-primary);
                    }

                    .node-popup-body {
                        padding: 25px;
                    }

                    .node-path-section, .node-content-section, .node-meta-section {
                        margin-bottom: 20px;
                    }

                    .node-path-main, .node-path-full, .node-namespace, .node-meta-item {
                        display: flex;
                        align-items: center;
                        gap: 12px;
                        margin-bottom: 12px;
                    }

                    .node-path-label, .node-content-label, .node-meta-label {
                        font-size: 11px;
                        font-weight: 700;
                        color: var(--text-secondary);
                        min-width: 80px;
                        text-transform: uppercase;
                        letter-spacing: 1px;
                    }

                    .node-path-value, .node-fullpath-value {
                        font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
                        font-size: 13px;
                        color: var(--accent-primary);
                        font-weight: 600;
                        flex: 1;
                    }

                    .node-namespace-value, .node-meta-value {
                        font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
                        font-size: 13px;
                        color: var(--text-primary);
                        font-weight: 500;
                        flex: 1;
                    }

                    .node-content-header {
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-bottom: 12px;
                    }

                    .node-content-text {
                        font-size: 14px;
                        color: var(--text-primary);
                        line-height: 1.6;
                        padding: 15px;
                        background: rgba(0, 0, 0, 0.2);
                        border-radius: 8px;
                        border-left: 4px solid var(--accent-primary);
                        font-family: system-ui, -apple-system, sans-serif;
                    }

                    .node-no-content {
                        padding: 20px;
                        text-align: center;
                        background: rgba(0, 0, 0, 0.1);
                        border-radius: 8px;
                        border: 1px dashed var(--border-light);
                    }

                    .no-content-text {
                        color: var(--text-secondary);
                        font-style: italic;
                    }

                    .node-meta-section {
                        padding-top: 15px;
                        border-top: 1px solid var(--border-light);
                    }

                    /* Copy button styles for node popup */
                    .copy-btn {
                        background: #22d3ee;
                        border: 1px solid #0891b2;
                        border-radius: 6px;
                        padding: 4px 8px;
                        font-size: 11px;
                        font-weight: 600;
                        cursor: pointer;
                        transition: all 0.2s ease;
                        color: white;
                        min-width: 45px;
                        height: 26px;
                        display: inline-flex;
                        align-items: center;
                        justify-content: center;
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                    }

                    .copy-btn:hover {
                        background: #0891b2;
                        transform: translateY(-1px);
                        box-shadow: 0 4px 8px rgba(34, 211, 238, 0.4);
                    }

                    /* Node actions section */
                    .node-actions-section {
                        margin-top: 20px;
                        padding-top: 15px;
                        border-top: 1px solid var(--border-light);
                        display: flex;
                        justify-content: center;
                    }

                    .node-summarize-btn {
                        background: var(--accent-primary);
                        color: white;
                        border: none;
                        border-radius: 8px;
                        padding: 10px 20px;
                        font-size: 14px;
                        font-weight: 600;
                        cursor: pointer;
                        transition: all 0.2s ease;
                        display: flex;
                        align-items: center;
                        gap: 8px;
                        text-transform: none;
                    }

                    .node-summarize-btn:hover {
                        background: var(--accent-secondary);
                        transform: translateY(-1px);
                        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
                    }

                    .node-summarize-btn:active {
                        transform: translateY(0);
                    }
                `;
                document.head.appendChild(styles);
            }

            // Position popup and add to DOM
            document.body.appendChild(popup);

            // Add event listeners
            popup.querySelector('.node-popup-close').onclick = () => {
                document.body.removeChild(popup);
            };

            // Close on background click
            popup.onclick = (e) => {
                if (e.target === popup) {
                    document.body.removeChild(popup);
                }
            };

            // Close on escape key
            const escapeHandler = (e) => {
                if (e.key === 'Escape') {
                    if (document.body.contains(popup)) {
                        document.body.removeChild(popup);
                    }
                    document.removeEventListener('keydown', escapeHandler);
                }
            };
            document.addEventListener('keydown', escapeHandler);
        }

        async function showDiffModal(commit1, commit2, isMock = false) {
            if (!connectedStorePath) {
                showNotification('Please connect to a memory store first', 'error');
                return;
            }

            // Show progress modal
            const progressModal = showProgressModal('Generating Diff',
                isMock ? 'Generating mock diff data...' : 'Analyzing memory store changes...');

            try {
                // Build API URL
                let apiUrl = `/api/diff?path=${encodeURIComponent(connectedStorePath)}`;
                if (commit1) apiUrl += `&commit1=${encodeURIComponent(commit1)}`;
                if (commit2) apiUrl += `&commit2=${encodeURIComponent(commit2)}`;
                if (isMock) apiUrl += `&mode=mock`;

                updateProgressModal(progressModal,
                    isMock ? 'Creating demonstration data...' : 'Comparing commits and analyzing changes...', 50);

                const response = await fetch(apiUrl);
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                const result = await response.json();
                updateProgressModal(progressModal, 'Formatting diff results...', 90);

                // Complete progress and close modal
                updateProgressModal(progressModal, 'Diff completed!', 100);
                setTimeout(() => closeProgressModal(progressModal), 500);

                if (result.success) {
                    // Create diff results display
                    let diffContent = `<div class="diff-content">`;
                    diffContent += `<h3>Memory Store Diff</h3>`;

                    // Only show mock notice if it's mock data
                    if (result.is_mock) {
                        diffContent += `<div class="diff-mock-notice">⚠️ <strong>Mock Data</strong> - This is simulated diff data for demonstration purposes</div>`;
                    }

                    // Use header from result or build one
                    if (result.header) {
                        diffContent += `<div class="diff-header">${result.header}</div>`;
                    } else if (commit1 && commit2) {
                        diffContent += `<div class="diff-header">Comparing ${commit1} → ${commit2}</div>`;
                    } else {
                        diffContent += `<div class="diff-header">Recent changes</div>`;
                    }

                    // Display diff stats
                    if (result.stats) {
                        diffContent += `
                            <div class="diff-stats">
                                <div class="diff-stat added">+${result.stats.added || 0} additions</div>
                                <div class="diff-stat modified">~${result.stats.modified || 0} modifications</div>
                                <div class="diff-stat deleted">-${result.stats.deleted || 0} deletions</div>
                            </div>
                        `;
                    }

                    // Display diff results
                    if (result.changes && result.changes.length > 0) {
                        diffContent += `<div class="diff-results">`;
                        result.changes.forEach((change, index) => {
                            const changeType = change.type || 'modified';
                            const changeIcon = changeType === 'added' ? '➕' :
                                             changeType === 'deleted' ? '➖' : '📝';

                            diffContent += `
                                <div class="diff-item ${changeType}">
                                    <div class="diff-item-header">
                                        <span class="diff-icon">${changeIcon}</span>
                                        <span class="diff-path">${change.path}</span>
                                        <span class="diff-type">${changeType}</span>
                                        <button class="copy-btn" onclick="copyToClipboard('${change.path.replace(/'/g, "\\'")}', this)" title="Copy path">Copy</button>
                                    </div>
                                    ${change.old_content || change.new_content ? `
                                        <div class="diff-content-section">
                                            ${change.old_content ? `
                                                <div class="diff-old">
                                                    <div class="diff-content-label">Before:</div>
                                                    <div class="diff-content-text">${escapeHtml(change.old_content)}</div>
                                                </div>
                                            ` : ''}
                                            ${change.new_content ? `
                                                <div class="diff-new">
                                                    <div class="diff-content-label">After:</div>
                                                    <div class="diff-content-text">${escapeHtml(change.new_content)}</div>
                                                </div>
                                            ` : ''}
                                        </div>
                                    ` : ''}
                                </div>
                            `;
                        });
                        diffContent += `</div>`;
                    } else {
                        diffContent += `<div class="diff-no-results">No changes found</div>`;
                    }

                    diffContent += `</div>`;

                    // Create and show results modal
                    const modal = document.createElement('div');
                    modal.className = 'diff-modal';
                    modal.innerHTML = `
                        <div class="diff-modal-content">
                            <div class="diff-modal-header">
                                <h2>🔍 Memory Store Diff</h2>
                                <button class="diff-modal-close">&times;</button>
                            </div>
                            <div class="diff-modal-body">
                                ${diffContent}
                            </div>
                            <div class="diff-modal-footer">
                                <button class="diff-button secondary" onclick="document.body.removeChild(this.closest('.diff-modal'))">Close</button>
                            </div>
                        </div>
                    `;

                    // Add CSS for diff modal (reuse similar styles to recall modal)
                    if (!document.getElementById('diff-modal-styles')) {
                        const styles = document.createElement('style');
                        styles.id = 'diff-modal-styles';
                        styles.textContent = `
                            .diff-modal {
                                position: fixed;
                                top: 0;
                                left: 0;
                                right: 0;
                                bottom: 0;
                                background: rgba(0, 0, 0, 0.8);
                                backdrop-filter: blur(8px);
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                z-index: 10000;
                                animation: fadeIn 0.3s ease;
                            }

                            .diff-modal-content {
                                background: var(--bg-primary);
                                border-radius: 16px;
                                border: 1px solid var(--border-light);
                                max-width: 900px;
                                width: 95%;
                                max-height: 85vh;
                                display: flex;
                                flex-direction: column;
                                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
                            }

                            .diff-modal-header {
                                padding: 20px 30px;
                                border-bottom: 1px solid var(--border-light);
                                display: flex;
                                justify-content: space-between;
                                align-items: center;
                                background: var(--bg-glass);
                                border-radius: 16px 16px 0 0;
                            }

                            .diff-modal-header h2 {
                                margin: 0;
                                color: var(--accent-primary);
                                font-size: 20px;
                                font-weight: 600;
                            }

                            .diff-modal-close {
                                background: none;
                                border: none;
                                font-size: 24px;
                                color: var(--text-secondary);
                                cursor: pointer;
                                padding: 4px;
                                border-radius: 4px;
                                transition: all 0.2s ease;
                            }

                            .diff-modal-close:hover {
                                background: var(--bg-glass);
                                color: var(--accent-primary);
                            }

                            .diff-modal-body {
                                padding: 30px;
                                overflow-y: auto;
                                flex: 1;
                            }

                            .diff-mock-notice {
                                font-size: 14px;
                                color: #f59e0b;
                                background: rgba(251, 191, 36, 0.1);
                                border: 1px solid rgba(251, 191, 36, 0.3);
                                padding: 12px 15px;
                                border-radius: 8px;
                                margin-bottom: 20px;
                                text-align: center;
                                font-weight: 500;
                            }

                            .diff-header {
                                font-size: 16px;
                                color: var(--text-primary);
                                margin-bottom: 20px;
                                font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
                                background: rgba(99, 102, 241, 0.1);
                                padding: 10px 15px;
                                border-radius: 8px;
                                border: 1px solid rgba(99, 102, 241, 0.3);
                            }

                            .diff-stats {
                                display: flex;
                                gap: 20px;
                                margin-bottom: 25px;
                                padding: 15px;
                                background: var(--bg-glass);
                                border-radius: 10px;
                                border: 1px solid var(--border-light);
                            }

                            .diff-stat {
                                font-size: 14px;
                                font-weight: 600;
                                padding: 8px 12px;
                                border-radius: 6px;
                                font-family: 'SF Mono', Monaco, monospace;
                            }

                            .diff-stat.added { background: rgba(34, 197, 94, 0.2); color: #22c55e; }
                            .diff-stat.modified { background: rgba(251, 191, 36, 0.2); color: #fbbf24; }
                            .diff-stat.deleted { background: rgba(239, 68, 68, 0.2); color: #ef4444; }

                            .diff-results {
                                display: flex;
                                flex-direction: column;
                                gap: 15px;
                            }

                            .diff-item {
                                border-radius: 10px;
                                border: 1px solid var(--border-light);
                                background: var(--bg-glass);
                                overflow: hidden;
                            }

                            .diff-item.added { border-left: 4px solid #22c55e; }
                            .diff-item.modified { border-left: 4px solid #fbbf24; }
                            .diff-item.deleted { border-left: 4px solid #ef4444; }

                            .diff-item-header {
                                padding: 15px 20px;
                                display: flex;
                                align-items: center;
                                gap: 12px;
                                background: rgba(0, 0, 0, 0.1);
                            }

                            .diff-icon {
                                font-size: 16px;
                            }

                            .diff-path {
                                font-family: 'SF Mono', Monaco, monospace;
                                font-size: 13px;
                                color: var(--accent-primary);
                                font-weight: 600;
                                flex: 1;
                            }

                            .diff-type {
                                font-size: 12px;
                                text-transform: uppercase;
                                font-weight: 600;
                                letter-spacing: 0.5px;
                                padding: 4px 8px;
                                border-radius: 4px;
                                background: var(--bg-glass);
                                color: var(--text-secondary);
                            }

                            .diff-content-section {
                                padding: 20px;
                                display: flex;
                                flex-direction: column;
                                gap: 15px;
                            }

                            .diff-old, .diff-new {
                                border-radius: 8px;
                                overflow: hidden;
                            }

                            .diff-content-label {
                                font-size: 11px;
                                font-weight: 600;
                                color: var(--text-secondary);
                                text-transform: uppercase;
                                letter-spacing: 0.5px;
                                margin-bottom: 8px;
                            }

                            .diff-content-text {
                                font-size: 14px;
                                line-height: 1.6;
                                padding: 15px;
                                border-radius: 6px;
                                font-family: system-ui, -apple-system, sans-serif;
                            }

                            .diff-old .diff-content-text {
                                background: rgba(239, 68, 68, 0.1);
                                border: 1px solid rgba(239, 68, 68, 0.3);
                                color: var(--text-primary);
                            }

                            .diff-new .diff-content-text {
                                background: rgba(34, 197, 94, 0.1);
                                border: 1px solid rgba(34, 197, 94, 0.3);
                                color: var(--text-primary);
                            }

                            .diff-no-results {
                                padding: 40px;
                                text-align: center;
                                color: var(--text-secondary);
                                font-size: 16px;
                            }

                            .diff-modal-footer {
                                padding: 20px 30px;
                                border-top: 1px solid var(--border-light);
                                display: flex;
                                gap: 15px;
                                justify-content: flex-end;
                                background: var(--bg-glass);
                            }

                            .diff-button {
                                padding: 10px 20px;
                                border: none;
                                border-radius: 8px;
                                font-size: 14px;
                                cursor: pointer;
                                transition: all 0.2s ease;
                                font-weight: 500;
                            }

                            .diff-button.secondary {
                                background: var(--bg-glass);
                                color: var(--text-primary);
                                border: 1px solid var(--border-light);
                            }

                            .diff-button.secondary:hover {
                                background: var(--bg-glass-light);
                                transform: translateY(-1px);
                            }
                        `;
                        document.head.appendChild(styles);
                    }

                    // Add modal to DOM
                    document.body.appendChild(modal);

                    // Add event listeners
                    modal.querySelector('.diff-modal-close').onclick = () => document.body.removeChild(modal);
                    modal.onclick = (e) => {
                        if (e.target === modal) {
                            document.body.removeChild(modal);
                        }
                    };
                } else {
                    throw new Error(result.error || 'Failed to generate diff');
                }

            } catch (error) {
                closeProgressModal(progressModal);
                console.error('Diff error:', error);
                showNotification(`Failed to generate diff: ${error.message}`, 'error');
            }
        }

        function updateMapTheme(theme) {
            if (!window.placesMap || !window.mapTileLayer) return;

            // Remove current tile layer
            window.placesMap.removeLayer(window.mapTileLayer);

            // Add new tile layer based on theme
            if (theme === 'dark') {
                // Dark mode tiles (CartoDB Dark Matter)
                window.mapTileLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
                    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>',
                    subdomains: 'abcd',
                    maxZoom: 19,
                }).addTo(window.placesMap);
            } else {
                // Light mode tiles (CartoDB Positron)
                window.mapTileLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
                    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>',
                    subdomains: 'abcd',
                    maxZoom: 19,
                }).addTo(window.placesMap);
            }
        }

        function initializePlacesMap() {
            const mapElement = document.getElementById('placesMapElement');
            const placeholder = document.getElementById('placesMapPlaceholder');

            if (!mapElement) {
                console.error('Places map element not found');
                return;
            }

            try {
                // Hide placeholder and show map
                placeholder.style.display = 'none';
                mapElement.style.display = 'block';

                // Show map controls
                const mapControls = document.getElementById('mapControls');
                if (mapControls) {
                    mapControls.style.display = 'flex';
                }

                // Initialize Leaflet map
                window.placesMap = L.map('placesMapElement').setView([40.7128, -74.0060], 2); // Default to world view

                // Store default view for home button
                window.mapDefaultView = {
                    center: [40.7128, -74.0060],
                    zoom: 2
                };

                // Get current theme
                const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';

                // Add appropriate tile layer based on theme
                if (currentTheme === 'dark') {
                    // Dark mode tiles (CartoDB Dark Matter)
                    window.mapTileLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
                        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>',
                        subdomains: 'abcd',
                        maxZoom: 19,
                    }).addTo(window.placesMap);
                } else {
                    // Light mode tiles (CartoDB Positron)
                    window.mapTileLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
                        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>',
                        subdomains: 'abcd',
                        maxZoom: 19,
                    }).addTo(window.placesMap);
                }

                // Initialize marker layer group
                window.placesMarkers = L.layerGroup().addTo(window.placesMap);


                window.placesMapInitialized = true;

                // Add event handlers for map control buttons
                const mapHomeBtn = document.getElementById('mapHomeBtn');
                const mapRefreshBtn = document.getElementById('mapRefreshBtn');

                if (mapHomeBtn) {
                    mapHomeBtn.addEventListener('click', () => {
                        if (window.placesMap && window.mapDefaultView) {
                            window.placesMap.setView(window.mapDefaultView.center, window.mapDefaultView.zoom);
                            showNotification('Map reset to default view', 'success', 2000);
                        }
                    });
                }

                if (mapRefreshBtn) {
                    mapRefreshBtn.addEventListener('click', async () => {
                        if (connectedStorePath) {
                            await loadPlacesData();
                            showNotification('Places data refreshed', 'success', 2000);
                        } else {
                            // Demo mode
                            await initializePlacesDemoMode();
                            showNotification('Demo places refreshed', 'success', 2000);
                        }
                    });
                }

            } catch (error) {
                console.error('Error initializing places map:', error);
                // Show error in placeholder
                placeholder.innerHTML = `
                    <div class="places-map-icon">⚠️</div>
                    <div class="places-map-text">
                        <strong>Map Initialization Error</strong><br>
                        Unable to load the interactive map
                    </div>
                `;
            }
        }

        async function updatePlacesMap(places) {


            if (!window.placesMap || !window.placesMarkers) {

                return;
            }



            // Clear existing markers
            window.placesMarkers.clearLayers();

            // Add markers for each place
            const bounds = [];

            for (const place of places) {
                try {
                    const coords = await geocodeLocation(place.name);
                    if (coords) {
                        // Create marker with custom popup
                        const marker = L.marker([coords.lat, coords.lon])
                            .bindPopup(`
                                <div style="min-width: 200px;">
                                    <h4 style="margin: 0 0 8px 0; color: #333;">${place.displayName}</h4>
                                    <p style="margin: 0; color: #666; font-size: 12px;">${place.eventCount} ${place.eventCount === 1 ? 'memory' : 'memories'}</p>
                                    <div style="margin-top: 8px; font-size: 13px; line-height: 1.4; color: #555;">
                                        ${place.events.map(event => `• ${event.trim()}`).join('<br>')}
                                    </div>
                                </div>
                            `);

                        window.placesMarkers.addLayer(marker);
                        bounds.push([coords.lat, coords.lon]);


                    }
                } catch (error) {
                    console.warn(`Failed to geocode location: ${place.name}`, error);
                }
            }

            // Fit map to show all markers
            if (bounds.length > 0) {
                if (bounds.length === 1) {
                    // Single marker - center on it
                    window.placesMap.setView(bounds[0], 10);
                } else {
                    // Multiple markers - fit bounds
                    window.placesMap.fitBounds(bounds, { padding: [20, 20] });
                }
            }
        }

        async function geocodeLocation(locationName) {
            // Use Nominatim (OpenStreetMap) geocoding service
            const encodedLocation = encodeURIComponent(locationName);
            const url = `https://nominatim.openstreetmap.org/search?q=${encodedLocation}&format=json&limit=1&addressdetails=1`;



            try {
                const response = await fetch(url, {
                    headers: {
                        'User-Agent': 'Memoir-Places-Viewer/1.0'
                    }
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const data = await response.json();


                if (data && data.length > 0) {
                    const result = data[0];
                    const coords = {
                        lat: parseFloat(result.lat),
                        lon: parseFloat(result.lon),
                        display_name: result.display_name
                    };

                    return coords;
                }

                console.warn(`No geocoding results found for "${locationName}"`);
                return null;
            } catch (error) {
                console.error(`Geocoding failed for "${locationName}":`, error);
                return null;
            }
        }

        async function updateUIWithRealData(data) {


            // Update branches
            const branchSelector = document.querySelector('#branchSelector');


            if (branchSelector && data.branches) {

                branchSelector.innerHTML = '';
                data.branches.forEach(branch => {
                    const option = document.createElement('option');
                    option.value = branch;

                    // Shorten long branch names for display - show beginning instead of ending
                    let displayName = branch;
                    if (branch.length > 25) {
                        // Truncate long names but keep the beginning part
                        displayName = branch.slice(0, 22) + '...';
                    }

                    option.textContent = displayName;
                    option.title = branch; // Show full name on hover

                    if (branch === data.current_branch) {
                        option.selected = true;
                    }
                    branchSelector.appendChild(option);
                });
            }

            // Update commit timeline with real data
            if (data.commits) {
                const gitHistory = document.querySelector('.git-tree');
                if (gitHistory) {
                    // Clear existing commits except the time headers
                    const commitNodes = gitHistory.querySelectorAll('.commit-node');
                    commitNodes.forEach(node => node.remove());

                    // Add real commits from all branches
                    let insertAfter = gitHistory.querySelector('.time-header') || gitHistory.firstChild;

                    // Handle different commit data formats
                    const allCommits = [];
                    if (Array.isArray(data.commits)) {
                        // Format: [{hash: "abc", message: "..."}, ...]
                        data.commits.forEach(commit => {
                            allCommits.push({
                                hash: commit.hash,
                                message: commit.message,
                                branch: data.current_branch || 'main'
                            });
                        });
                    } else if (data.commits && typeof data.commits === 'object') {
                        // Format: {main: ["hash1", "hash2"], feature: ["hash3"]}
                        for (const [branch, commits] of Object.entries(data.commits)) {
                            if (Array.isArray(commits)) {
                                commits.forEach(hash => {
                                    allCommits.push({ hash, branch, message: 'Memory store update' });
                                });
                            } else if (typeof commits === 'string') {
                                allCommits.push({ hash: commits, branch, message: 'Memory store update' });
                            }
                        }
                    }

                    // Add ALL commits (no limit)
                    allCommits.forEach((commit, index) => {
                        const commitNode = document.createElement('div');
                        commitNode.className = 'commit-node';
                        commitNode.dataset.commit = commit.hash;

                        const branchClass = commit.branch === 'main' ? 'main' : 'branch';
                        const branchTag = commit.branch.replace('feature/', '').replace('experimental/', '');

                        commitNode.innerHTML = `
                            <div class="git-lines">
                                <div class="commit-dot ${branchClass}"></div>
                            </div>
                            <div class="commit-info">
                                <div class="commit-header">
                                    <div class="commit-hash">${commit.hash.substring(0, 7)}</div>
                                    <div class="branch-tag">${branchTag}</div>
                                </div>
                                <div class="commit-message">${commit.message || 'Memory store update'}</div>
                                <div class="commit-meta">
                                    <div class="commit-author">
                                        <div class="author-avatar">M</div>
                                        <span>Memoir</span>
                                    </div>
                                    <div class="commit-time">recent</div>
                                </div>
                            </div>
                        `;

                        // Insert after the last element
                        if (insertAfter.nextSibling) {
                            gitHistory.insertBefore(commitNode, insertAfter.nextSibling);
                        } else {
                            gitHistory.appendChild(commitNode);
                        }
                        insertAfter = commitNode;

                        // Re-attach click handlers
                        commitNode.addEventListener('click', function() {
                            document.querySelectorAll('.commit-node').forEach(i => i.classList.remove('active'));
                            this.classList.add('active');
                            const commitId = this.dataset.commit;
                            // Removed currentCommit display - was confusing for users
                            updateMemoryStructure(commitId);
                        });
                    });
                }
            }

            // Update commits if available
            if (data.commits && data.commits.main) {
                // Removed currentCommit display - was confusing for users
                // const currentCommit = document.getElementById('currentCommit');
                // if (currentCommit && data.commits.main.length > 0) {
                //     currentCommit.textContent = data.commits.main[0];
                // }
            }

            // Update status
            const statusEl = document.querySelector('.connection-status');
            if (!statusEl) {
                // Create status element
                const headerControls = document.querySelector('.header-controls');
                if (headerControls) {
                    const status = document.createElement('div');
                    status.className = 'connection-status';
                    status.style.cssText = 'color: #10b981; font-size: 12px; margin-left: 10px; display: inline-flex; align-items: center;';
                    status.innerHTML = `<span style="margin-right: 5px;">📁</span> Connected: ${connectedStorePath}`;
                    headerControls.appendChild(status);
                }
            } else {
                statusEl.innerHTML = `<span style="margin-right: 5px;">📁</span> Connected: ${connectedStorePath}`;
            }

            // Update tree view with real memory data
            console.log('Checking if we should update tree view:', {
                hasMemories: !!(data.memories && data.memories.length > 0),
                hasTree: !!(data.tree && Object.keys(data.tree).length > 0),
                memoriesCount: data.memories ? data.memories.length : 0,
                treeKeysCount: data.tree ? Object.keys(data.tree).length : 0,
                dataKeys: Object.keys(data)
            });

            // Always update the tree view when connected (even with empty data)
            updateTreeViewWithRealData(data);

            // Also update the global variable for graph rendering
            window.realStoreData = data;

            // Clear the new empty store flag since we now have real data
            if (data && (data.memories && data.memories.length > 0) || (data.tree && Object.keys(data.tree).length > 0)) {
                window.isNewEmptyStore = false;
            }

            // Update graph view if it's currently visible
            const graphView = document.getElementById('graphView');
            const isGraphVisible = graphView && graphView.style.display !== 'none';
            if (isGraphVisible) {

                renderGraph();
            }

            // Load and display timeline data
            await updateTimelineView();

            // Show success in console

        }

        async function updateTimelineView() {


            // Only refresh if Timeline view is currently active
            const timelineView = document.getElementById('timelineView');
            if (timelineView && timelineView.style.display !== 'none') {


                // Re-initialize the timeline view to show updated data
                if (connectedStorePath) {
                    await renderGitHubStyleTimelineGrid();
                } else {
                    await initializeTimelineView();
                }


            } else {

            }
        }

        function showNotification(message, type = 'info', duration = 3000) {
            // Calculate position to stack notifications vertically
            const existingNotifications = document.querySelectorAll('.notification');
            let topPosition = 100;

            existingNotifications.forEach(notif => {
                const rect = notif.getBoundingClientRect();
                topPosition = Math.max(topPosition, rect.bottom + 10);
            });

            // Create notification element
            const notification = document.createElement('div');
            notification.className = 'notification';
            notification.style.cssText = `
                position: fixed;
                top: ${topPosition}px;
                right: 20px;
                padding: 12px 20px;
                background: ${type === 'error' ? '#ef4444' : type === 'success' ? '#10b981' : '#3b82f6'};
                color: white;
                border-radius: 8px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                z-index: 10000;
                animation: slideIn 0.3s ease;
                white-space: pre-line;
                font-family: 'JetBrains Mono', monospace;
                font-size: 12px;
                max-width: 400px;
                line-height: 1.4;
                transition: all 0.3s ease;
            `;
            notification.textContent = message;

            document.body.appendChild(notification);

            // Remove after specified duration
            setTimeout(() => {
                notification.style.animation = 'slideOut 0.3s ease';
                setTimeout(() => {
                    notification.remove();
                    // Reposition remaining notifications
                    repositionNotifications();
                }, 300);
            }, duration);
        }

        function repositionNotifications() {
            const notifications = document.querySelectorAll('.notification');
            let topPosition = 100;

            notifications.forEach(notif => {
                notif.style.top = `${topPosition}px`;
                const rect = notif.getBoundingClientRect();
                topPosition = rect.bottom + 10;
            });
        }

        // Add CSS animation
        if (!document.querySelector('#notification-styles')) {
            const style = document.createElement('style');
            style.id = 'notification-styles';
            style.textContent = `
                @keyframes slideIn {
                    from { transform: translateX(100%); opacity: 0; }
                    to { transform: translateX(0); opacity: 1; }
                }
                @keyframes slideOut {
                    from { transform: translateX(0); opacity: 1; }
                    to { transform: translateX(100%); opacity: 0; }
                }
            `;
            document.head.appendChild(style);
        }


        function updateTreeViewWithRealData(data) {


            const treeView = document.getElementById('treeView');
            if (!treeView) return;

            // If we have a tree structure, use it
            if (data.tree && Object.keys(data.tree).length > 0) {

                treeView.innerHTML = buildTreeFromPaths(data.tree);
            } else if (data.memories && data.memories.length > 0) {

                // Build tree from memory paths
                const pathCount = {};
                data.memories.forEach(memory => {
                    if (memory.path) {
                        const parts = memory.path.split('.');
                        let currentPath = '';
                        parts.forEach(part => {
                            currentPath = currentPath ? currentPath + '.' + part : part;
                            pathCount[currentPath] = (pathCount[currentPath] || 0) + 1;
                        });
                    }
                });
                treeView.innerHTML = buildTreeFromPaths(pathCount);
            } else {
                // Show connection info and sample structure for demo

                treeView.innerHTML = `
                    <div class="tree-node">
                        <div class="node-content">
                            <span class="node-icon">📁</span>
                            <span class="node-label">Connected: ${data.store_path || 'memory store'}</span>
                        </div>
                        <div class="node-children">
                            <div class="tree-node">
                                <div class="node-content">
                                    <span class="node-icon">📁</span>
                                    <span class="node-label">Branches: ${data.branches ? data.branches.length : 0}</span>
                                </div>
                            </div>
                            <div class="tree-node">
                                <div class="node-content">
                                    <span class="node-icon">📁</span>
                                    <span class="node-label">Total memories: ${data.total_memories || 0}</span>
                                </div>
                            </div>
                            <div class="tree-node">
                                <div class="node-content">
                                    <span class="node-icon">📁</span>
                                    <span class="node-label">Memory tree will populate with data</span>
                                </div>
                                <div class="node-children">
                                    <div class="tree-node">
                                        <div class="node-content">
                                            <span class="node-icon">📁</span>
                                            <span class="node-label">Add memories to see hierarchical structure</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            }
        }

        function buildTreeFromPaths(pathCount) {
            const tree = {};

            // Create organized structure with memento and taxonomy folders
            const organizedPaths = {
                'memento': { children: {}, count: 0 },
                'taxonomy': { children: {}, count: 0 }
            };

            // Categorize paths
            Object.keys(pathCount).forEach(path => {
                const parts = path.split('.');
                const rootCategory = parts[0];

                // Determine if this is memento (timeline/location) or taxonomy data
                let targetFolder, pathInFolder;
                if (rootCategory === 'timeline' || rootCategory === 'location') {
                    targetFolder = 'memento';
                    pathInFolder = path; // Keep full path under memento
                } else {
                    targetFolder = 'taxonomy';
                    pathInFolder = path; // Keep full path under taxonomy
                }

                // Build nested structure within the appropriate folder
                const pathParts = pathInFolder.split('.');
                let current = organizedPaths[targetFolder];

                pathParts.forEach((part, index) => {
                    if (!current.children[part]) {
                        current.children[part] = { children: {}, count: 0 };
                    }
                    if (index === pathParts.length - 1) {
                        current.children[part].count = pathCount[path];
                        // Also increment the parent folder count
                        organizedPaths[targetFolder].count += pathCount[path];
                    }
                    current = current.children[part];
                });
            });

            // Add folders in specific order: taxonomy first, then memento
            const folderOrder = ['taxonomy', 'memento'];
            folderOrder.forEach(folderName => {
                if (organizedPaths[folderName] && Object.keys(organizedPaths[folderName].children).length > 0) {
                    tree[folderName] = organizedPaths[folderName];
                }
            });

            // Convert to HTML
            function renderNode(name, node, level = 0) {
                const hasMemories = node.count > 0;
                const hasChildren = Object.keys(node.children).length > 0;
                const isLeafNode = hasMemories && !hasChildren;
                const icon = getIconForPath(name, level, isLeafNode);
                const foldIcon = hasChildren ? '▼' : '';

                let html = `
                    <div class="tree-node ${hasChildren ? 'has-children' : ''}">
                        <div class="node-content">
                            ${hasChildren ? `<span class="fold-indicator" onclick="toggleFold(event)">${foldIcon}</span>` : '<span class="fold-spacer"></span>'}
                            <span class="node-icon">${icon}</span>
                            <span class="node-label ${hasMemories ? 'has-memories' : ''}">${name}</span>
                            ${hasMemories ? `<span class="memory-count">${node.count}</span>` : ''}
                        </div>
                `;

                if (hasChildren) {
                    html += '<div class="node-children">';
                    Object.entries(node.children).forEach(([childName, childNode]) => {
                        html += renderNode(childName, childNode, level + 1);
                    });
                    html += '</div>';
                }

                html += '</div>';
                return html;
            }

            let result = '';
            Object.entries(tree).forEach(([name, node]) => {
                result += renderNode(name, node);
            });

            return result || '<div class="tree-node"><div class="node-content"><span class="node-icon">📁</span><span class="node-label">No memory paths found</span></div></div>';
        }

        function toggleFold(event) {
            event.stopPropagation(); // Prevent triggering node click events

            const foldIndicator = event.target;
            const treeNode = foldIndicator.closest('.tree-node');
            const nodeChildren = treeNode.querySelector('.node-children');

            if (!nodeChildren) return; // No children to fold/unfold

            const isCurrentlyFolded = treeNode.classList.contains('folded');

            if (isCurrentlyFolded) {
                // Unfold
                treeNode.classList.remove('folded');
                foldIndicator.textContent = '▼';
                nodeChildren.style.maxHeight = nodeChildren.scrollHeight + 'px';
                // Reset to auto after animation completes
                setTimeout(() => {
                    if (!treeNode.classList.contains('folded')) {
                        nodeChildren.style.maxHeight = 'none';
                    }
                }, 300);
            } else {
                // Fold
                nodeChildren.style.maxHeight = nodeChildren.scrollHeight + 'px';
                // Force reflow
                nodeChildren.offsetHeight;
                treeNode.classList.add('folded');
                foldIndicator.textContent = '▶';
                nodeChildren.style.maxHeight = '0';
            }
        }

        function getIconForPath(name, level, isLeafNode = false) {
            // Use folder icon for directories, document icon for items with memories
            return isLeafNode ? '📄' : '📁';
        }

        function buildGraphDataFromRealData(data) {
            const nodes = [];
            const links = [];
            const nodeMap = new Map();

            // Process memories or tree data
            let pathCount = {};
            if (data.tree && Object.keys(data.tree).length > 0) {
                pathCount = data.tree;
            } else if (data.memories && data.memories.length > 0) {
                data.memories.forEach(memory => {
                    if (memory.path) {
                        const parts = memory.path.split('.');
                        let currentPath = '';
                        parts.forEach(part => {
                            currentPath = currentPath ? currentPath + '.' + part : part;
                            pathCount[currentPath] = (pathCount[currentPath] || 0) + 1;
                        });
                    }
                });
            }

            // Create nodes from paths - limit to 3 levels deep for cleaner visualization
            Object.keys(pathCount).forEach(path => {
                const parts = path.split('.');
                const name = parts[parts.length - 1];
                const level = parts.length - 1;

                // Only include paths up to 3 levels deep (0, 1, 2)
                if (level <= 2 && !nodeMap.has(path)) {
                    // Check if this is a leaf node (has direct count in pathCount and level > 0)
                    const isLeafNode = pathCount.hasOwnProperty(path) && level > 0;
                    const group = level === 0 ? 1 : (level === 1 ? 2 : 3); // Set group based on level for compatibility

                    nodes.push({
                        id: path,
                        name: name,
                        level: level,
                        group: group,
                        count: pathCount[path] || 0,
                        isLeaf: isLeafNode,
                        x: 0, // Will be positioned later
                        y: 0, // Will be positioned later
                        fx: null,
                        fy: null
                    });
                    nodeMap.set(path, nodes.length - 1);
                }

                // Create link to parent (only if both parent and child are within depth limit)
                if (parts.length > 1 && level <= 2) {
                    const parentPath = parts.slice(0, -1).join('.');
                    const parentLevel = parts.length - 2;

                    if (parentLevel <= 2 && pathCount[parentPath] !== undefined) {
                        links.push({
                            source: parentPath,
                            target: path,
                            strength: 0.5
                        });
                    }
                }
            });

            // Position nodes in organized radial layout
            positionNodesRadially(nodes);

            return { nodes, links };
        }

        function positionNodesRadially(nodes) {
            // Group nodes by level
            const nodesByLevel = { 0: [], 1: [], 2: [] };
            nodes.forEach(node => {
                if (nodesByLevel[node.level]) {
                    nodesByLevel[node.level].push(node);
                }
            });

            const centerX = 400; // Center of the visualization
            const centerY = 300;

            // Position Level 0 nodes (root) in the center
            if (nodesByLevel[0].length > 0) {
                if (nodesByLevel[0].length === 1) {
                    // Single root node in the center
                    nodesByLevel[0][0].x = centerX;
                    nodesByLevel[0][0].y = centerY;
                } else {
                    // Multiple root nodes in a small circle around center
                    const radius = 60;
                    nodesByLevel[0].forEach((node, i) => {
                        const angle = (i * 2 * Math.PI) / nodesByLevel[0].length;
                        node.x = centerX + radius * Math.cos(angle);
                        node.y = centerY + radius * Math.sin(angle);
                    });
                }
            }

            // Position Level 1 nodes (categories) in a circle around level 0
            if (nodesByLevel[1].length > 0) {
                const radius = 150;
                nodesByLevel[1].forEach((node, i) => {
                    const angle = (i * 2 * Math.PI) / nodesByLevel[1].length - Math.PI / 2; // Start from top
                    node.x = centerX + radius * Math.cos(angle);
                    node.y = centerY + radius * Math.sin(angle);
                });
            }

            // Position Level 2 nodes (specific) in outer circle, grouped by their parent
            if (nodesByLevel[2].length > 0) {
                const radius = 250;

                // Group level 2 nodes by their parent (level 1)
                const nodesByParent = {};
                nodesByLevel[2].forEach(node => {
                    const parentPath = node.id.split('.').slice(0, -1).join('.');
                    if (!nodesByParent[parentPath]) {
                        nodesByParent[parentPath] = [];
                    }
                    nodesByParent[parentPath].push(node);
                });

                // Position each group around their parent
                Object.entries(nodesByParent).forEach(([parentPath, childNodes]) => {
                    const parent = nodesByLevel[1].find(n => n.id === parentPath);
                    if (parent) {
                        // Calculate angle from center to parent
                        const parentAngle = Math.atan2(parent.y - centerY, parent.x - centerX);

                        // Position children in an arc around the parent's direction
                        childNodes.forEach((child, i) => {
                            const angleOffset = (i - (childNodes.length - 1) / 2) * (Math.PI / 6); // 30 degree spacing
                            const childAngle = parentAngle + angleOffset;
                            child.x = centerX + radius * Math.cos(childAngle);
                            child.y = centerY + radius * Math.sin(childAngle);
                        });
                    } else {
                        // Fallback: distribute evenly around outer circle
                        childNodes.forEach((child, i) => {
                            const angle = (i * 2 * Math.PI) / nodesByLevel[2].length;
                            child.x = centerX + radius * Math.cos(angle);
                            child.y = centerY + radius * Math.sin(angle);
                        });
                    }
                });
            }
        }

        function buildGraphDataFromMockData() {
            // Build comprehensive graph data from the same mock tree structure used by tree view
            const mockTree = generateMockTree(1.0); // Use full density to match tree view
            const nodes = [];
            const links = [];
            const nodeMap = new Map();

            // Helper function to get node name from path
            function getNodeName(path) {
                return path.split('.').pop();
            }

            // Helper function to get parent path
            function getParentPath(path) {
                const parts = path.split('.');
                return parts.length > 1 ? parts.slice(0, -1).join('.') : null;
            }

            // Build nodes from all paths in mock tree
            const allPaths = Object.keys(mockTree);
            const processedPaths = new Set();

            // Add root node
            nodes.push({
                id: 'profile',
                name: 'profile',
                level: 0,
                group: 1, // Root node group
                count: Object.values(mockTree).reduce((sum, count) => sum + count, 0),
                isLeaf: false, // Root is never a leaf
                x: 400,
                y: 300,
                fx: null,
                fy: null
            });
            nodeMap.set('profile', true);

            // Process all intermediate paths
            for (const fullPath of allPaths) {
                const pathParts = fullPath.split('.');

                // Create intermediate nodes for each level
                for (let i = 1; i < pathParts.length; i++) {
                    const partialPath = pathParts.slice(0, i + 1).join('.');

                    if (!processedPaths.has(partialPath)) {
                        processedPaths.add(partialPath);

                        // Calculate count for this node (sum of all child paths)
                        const nodeCount = Object.entries(mockTree)
                            .filter(([path]) => path.startsWith(partialPath))
                            .reduce((sum, [, count]) => sum + count, 0);

                        const level = i;
                        const name = getNodeName(partialPath);

                        // Position calculation for better layout
                        const centerX = 400;
                        const centerY = 300;
                        const radius = 100 + (level * 80);
                        const angle = (processedPaths.size * (2 * Math.PI / 16)) + (level * 0.5);

                        // Check if this is a leaf node (has direct memory count in mockTree)
                        const isLeafNode = mockTree.hasOwnProperty(partialPath);
                        const group = level === 0 ? 1 : (level === 1 ? 2 : 3); // Set group based on level for compatibility

                        nodes.push({
                            id: partialPath,
                            name: name,
                            level: level,
                            group: group,
                            count: nodeCount,
                            isLeaf: isLeafNode,
                            x: centerX + Math.cos(angle) * radius,
                            y: centerY + Math.sin(angle) * radius,
                            fx: null,
                            fy: null
                        });
                        nodeMap.set(partialPath, true);

                        // Create link to parent
                        const parentPath = getParentPath(partialPath);
                        if (parentPath && nodeMap.has(parentPath)) {
                            links.push({
                                source: parentPath,
                                target: partialPath,
                                strength: 0.5
                            });
                        }
                    }
                }
            }

            return { nodes, links };
        }

        function updateMemoryStructure(commitId) {
            // Update memory counts based on commit (for mock data)
            const data = commits[commitId];
            if (data && data.tree) {
                Object.entries(data.tree).forEach(([path, count]) => {
                    const pathParts = path.split('.');
                    const nodeName = pathParts[pathParts.length - 1];

                    document.querySelectorAll('.tree-node').forEach(node => {
                        const label = node.querySelector('.node-label');
                        if (label && label.textContent === nodeName) {
                            const countSpan = node.querySelector('.memory-count');
                            if (countSpan) {
                                countSpan.textContent = count;
                                if (count > 0) {
                                    label.classList.add('has-memories');
                                } else {
                                    label.classList.remove('has-memories');
                                }
                            }
                        }
                    });
                });
            }
        }

        function escapeHtml(text) {
            if (typeof text !== 'string') {
                text = String(text);
            }
            return text
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        }

        function formatTimeAgo(timestamp) {
            const now = Date.now();
            const diff = now - timestamp;
            const seconds = Math.floor(diff / 1000);
            const minutes = Math.floor(seconds / 60);
            const hours = Math.floor(minutes / 60);
            const days = Math.floor(hours / 24);
            const weeks = Math.floor(days / 7);
            const months = Math.floor(days / 30);

            if (seconds < 60) return `${seconds}s ago`;
            if (minutes < 60) return `${minutes}m ago`;
            if (hours < 24) return `${hours}h ago`;
            if (days < 7) return `${days}d ago`;
            if (weeks < 4) return `${weeks}w ago`;
            return `${months}mo ago`;
        }

        function buildFullPath(node) {
            const pathParts = [];
            let currentNode = node;

            // Traverse up the tree to build the full path
            while (currentNode && currentNode.classList.contains('tree-node')) {
                const label = currentNode.querySelector('.node-label');
                if (label) {
                    pathParts.unshift(label.textContent);
                }
                currentNode = currentNode.parentElement?.closest('.tree-node');
            }

            // Remove the folder prefixes (memento/taxonomy) from the path
            // since the actual memory paths don't include these organizational folders
            const fullPath = pathParts.join('.');
            if (fullPath.startsWith('memento.') || fullPath.startsWith('taxonomy.')) {
                return pathParts.slice(1).join('.');
            }

            return fullPath;
        }

        function showMemoryDetails(path) {
            // Create node data for the popup
            const nodeData = {
                id: path,
                group: 3, // leaf node
                connections: 0
            };

            // Only call our enhanced popup function - skip the old UI
            showNodeDetailsPopup(nodeData, null);
            return; // Exit early to prevent old popup from showing

            // Old function disabled - only our new popup is shown
            const detailsPanel = document.getElementById('memoryDetails');
            const detailsPath = document.getElementById('detailsPath');
            const memoriesList = document.getElementById('memoriesList');

            // Set the path title with tooltip for long paths
            detailsPath.textContent = path;
            detailsPath.title = path; // Add tooltip to show full path on hover


            // Filter memories that match this path
            const matchingMemories = [];
            if (window.realStoreData && window.realStoreData.memories) {


                // Log first few memory paths for debugging
                const memoryPaths = window.realStoreData.memories.map(m => m.path).slice(0, 10);


                for (const memory of window.realStoreData.memories) {
                    if (memory.path && memory.path.startsWith(path)) {
                        matchingMemories.push(memory);

                    }
                }
            }



            // Populate with real memory data
            if (matchingMemories.length > 0) {
                memoriesList.innerHTML = matchingMemories.map(memory => {
                    const timeAgo = memory.value && memory.value.timestamp ?
                        formatTimeAgo(memory.value.timestamp * 1000) : 'Unknown time';
                    const confidence = memory.value && memory.value.confidence ?
                        memory.value.confidence.toFixed(2) : '1.0';
                    // Handle different data structures for different memory types
                    let content = 'No content';


                    if (memory.content) {
                        content = memory.content;
                    } else if (memory.value?.content) {
                        // Standard memory format
                        if (typeof memory.value.content === 'string') {
                            content = memory.value.content;
                        } else if (memory.value.content.raw_text) {
                            // Timeline/location format with raw_text
                            content = memory.value.content.raw_text;
                        } else if (memory.value.content.content) {
                            // Nested content structure
                            content = memory.value.content.content;
                        } else {
                        }
                    } else if (memory.value?.memories && Array.isArray(memory.value.memories) && memory.value.memories.length > 0) {
                        // AggregatedMemory format - content is in the memories array
                        const firstMemory = memory.value.memories[0];

                        if (firstMemory.content) {
                            // Extract content from the first memory entry
                            if (typeof firstMemory.content === 'string') {
                                content = firstMemory.content;
                            } else if (firstMemory.content.raw_text) {
                                content = firstMemory.content.raw_text;
                            } else if (firstMemory.content.content) {
                                content = firstMemory.content.content;
                            } else {
                                // Try JSON stringify as fallback
                                content = JSON.stringify(firstMemory.content, null, 2);
                            }
                        } else {
                        }
                    } else if (memory.value?.raw_text) {
                        // Direct raw_text field
                        content = memory.value.raw_text;
                    } else if (typeof memory.value === 'string') {
                        content = memory.value;
                    } else {
                    }

                    // Extract additional metadata for timeline/location entries
                    let summary = '';
                    let memoryType = '';
                    let structuredData = null;

                    // Check if we have memories array (AggregatedMemory format)
                    if (memory.value?.memories && Array.isArray(memory.value.memories) && memory.value.memories.length > 0) {
                        const firstMemory = memory.value.memories[0];
                        if (firstMemory.content) {
                            if (firstMemory.content.summary) {
                                summary = firstMemory.content.summary;
                            }
                            if (firstMemory.content.memory_type) {
                                memoryType = firstMemory.content.memory_type;
                            }
                            if (firstMemory.content.structured_data) {
                                structuredData = firstMemory.content.structured_data;
                            }
                        }
                    } else if (memory.value?.content) {
                        if (memory.value.content.summary) {
                            summary = memory.value.content.summary;
                        }
                        if (memory.value.content.memory_type) {
                            memoryType = memory.value.content.memory_type;
                        }
                        if (memory.value.content.structured_data) {
                            structuredData = memory.value.content.structured_data;
                        }
                    } else if (memory.value) {
                        if (memory.value.summary) {
                            summary = memory.value.summary;
                        }
                        if (memory.value.memory_type) {
                            memoryType = memory.value.memory_type;
                        }
                        if (memory.value.structured_data) {
                            structuredData = memory.value.structured_data;
                        }
                    }

                    // Build additional info display
                    let additionalInfo = '';
                    if (summary && summary !== content) {
                        additionalInfo += `<div class="memory-summary"><strong>Summary:</strong> ${summary}</div>`;
                    }
                    if (memoryType) {
                        additionalInfo += `<div class="memory-type"><strong>Type:</strong> ${memoryType}</div>`;
                    }
                    if (structuredData) {
                        if (structuredData.timeline_date) {
                            additionalInfo += `<div class="timeline-date"><strong>Date:</strong> ${structuredData.timeline_date}</div>`;
                        }
                        if (structuredData.location_name) {
                            additionalInfo += `<div class="location-name"><strong>Location:</strong> ${structuredData.location_name}</div>`;
                        }
                    }

                    return `
                        <div class="memory-item">
                            <div class="memory-content">${content}</div>
                            ${additionalInfo}
                            <div class="memory-meta">
                                <span class="confidence-score">${confidence}</span>
                                <span>${timeAgo}</span>
                            </div>
                        </div>
                    `;
                }).join('');
            } else {
                memoriesList.innerHTML = `
                    <div class="memory-item">
                        <div class="memory-content">No memories found for this path</div>
                        <div class="memory-meta">
                            <span>Try storing some memories first</span>
                        </div>
                    </div>
                `;
            }

            // Show the details panel
            detailsPanel.classList.add('open');
        }

        function renderGraph() {
            // Use real data if available, otherwise fall back to mock data (unless it's a new empty store)
            let graphData;
            if (window.realStoreData && (window.realStoreData.memories || window.realStoreData.tree)) {
                graphData = buildGraphDataFromRealData(window.realStoreData);
            } else if (window.isNewEmptyStore) {
                // For new empty stores, show truly empty graph
                graphData = { nodes: [], links: [] };
            } else {
                // Only show mock data when not connected to any store (demo mode)
                graphData = buildGraphDataFromMockData();
            }

            // Optimized D3.js force-directed graph with pre-calculated positions
            const svg = d3.select('#graphSvg');
            svg.selectAll('*').remove();

            const width = svg.node().getBoundingClientRect().width;
            const height = svg.node().getBoundingClientRect().height;

            // Create container group for zoom/pan functionality
            const container = svg.append('g').attr('class', 'zoom-container');

            // Add zoom behavior
            const zoom = d3.zoom()
                .scaleExtent([0.1, 4])
                .on('zoom', function(event) {
                    container.attr('transform', event.transform);
                });

            svg.call(zoom);

            // Connect zoom controls to D3 zoom behavior
            d3.select('#zoomIn').on('click', () => {
                svg.transition().duration(300).call(
                    zoom.scaleBy, 1.5
                );
            });

            d3.select('#zoomOut').on('click', () => {
                svg.transition().duration(300).call(
                    zoom.scaleBy, 1 / 1.5
                );
            });

            d3.select('#zoomReset').on('click', () => {
                svg.transition().duration(500).call(
                    zoom.transform,
                    d3.zoomIdentity
                );
            });

            // Use the graph data from real or mock data
            const nodes = graphData.nodes;
            const links = graphData.links;

            // Pre-calculated positions for comprehensive radial layout (fallback if no positions)
            const centerX = width / 2;
            const centerY = height / 2;
            const radius1 = 120; // Main categories
            const radius2 = 220; // Leaf nodes

            // Ensure nodes have positions
            nodes.forEach((node, i) => {
                if (!node.x || !node.y) {
                    const angle = (i * 360) / nodes.length;
                    const radius = node.level === 0 ? 0 : (node.level === 1 ? radius1 : radius2);
                    node.x = centerX + radius * Math.cos((angle - 90) * Math.PI / 180);
                    node.y = centerY + radius * Math.sin((angle - 90) * Math.PI / 180);
                }
            });

            // Keep original static layout for reference
            const staticNodes = [
                // Center node
                {id: 'profile', group: 1, x: centerX, y: centerY, fixed: true},

                // Second ring - main categories (6 categories at 60° intervals)
                {id: 'personal', group: 2, x: centerX + radius1 * Math.cos(-90 * Math.PI/180), y: centerY + radius1 * Math.sin(-90 * Math.PI/180), fixed: true},
                {id: 'professional', group: 2, x: centerX + radius1 * Math.cos(-30 * Math.PI/180), y: centerY + radius1 * Math.sin(-30 * Math.PI/180), fixed: true},
                {id: 'preferences', group: 2, x: centerX + radius1 * Math.cos(30 * Math.PI/180), y: centerY + radius1 * Math.sin(30 * Math.PI/180), fixed: true},
                {id: 'interests', group: 2, x: centerX + radius1 * Math.cos(90 * Math.PI/180), y: centerY + radius1 * Math.sin(90 * Math.PI/180), fixed: true},
                {id: 'technology', group: 2, x: centerX + radius1 * Math.cos(150 * Math.PI/180), y: centerY + radius1 * Math.sin(150 * Math.PI/180), fixed: true},

                // Third ring - All 23 leaf nodes evenly distributed around circle
                // Personal subcategories (positions 0-4)
                {id: 'identity', group: 3, x: centerX + radius2 * Math.cos(0 * Math.PI/180), y: centerY + radius2 * Math.sin(0 * Math.PI/180), fixed: true},
                {id: 'location', group: 3, x: centerX + radius2 * Math.cos(15 * Math.PI/180), y: centerY + radius2 * Math.sin(15 * Math.PI/180), fixed: true},
                {id: 'relationships', group: 3, x: centerX + radius2 * Math.cos(30 * Math.PI/180), y: centerY + radius2 * Math.sin(30 * Math.PI/180), fixed: true},
                {id: 'health', group: 3, x: centerX + radius2 * Math.cos(45 * Math.PI/180), y: centerY + radius2 * Math.sin(45 * Math.PI/180), fixed: true},
                {id: 'goals', group: 3, x: centerX + radius2 * Math.cos(60 * Math.PI/180), y: centerY + radius2 * Math.sin(60 * Math.PI/180), fixed: true},

                // Professional subcategories (positions 5-9)
                {id: 'skills', group: 3, x: centerX + radius2 * Math.cos(75 * Math.PI/180), y: centerY + radius2 * Math.sin(75 * Math.PI/180), fixed: true},
                {id: 'experience', group: 3, x: centerX + radius2 * Math.cos(90 * Math.PI/180), y: centerY + radius2 * Math.sin(90 * Math.PI/180), fixed: true},
                {id: 'companies', group: 3, x: centerX + radius2 * Math.cos(105 * Math.PI/180), y: centerY + radius2 * Math.sin(105 * Math.PI/180), fixed: true},
                {id: 'education', group: 3, x: centerX + radius2 * Math.cos(120 * Math.PI/180), y: centerY + radius2 * Math.sin(120 * Math.PI/180), fixed: true},
                {id: 'achievements', group: 3, x: centerX + radius2 * Math.cos(135 * Math.PI/180), y: centerY + radius2 * Math.sin(135 * Math.PI/180), fixed: true},

                // Preferences subcategories (positions 10-13)
                {id: 'interface', group: 3, x: centerX + radius2 * Math.cos(150 * Math.PI/180), y: centerY + radius2 * Math.sin(150 * Math.PI/180), fixed: true},
                {id: 'notifications', group: 3, x: centerX + radius2 * Math.cos(165 * Math.PI/180), y: centerY + radius2 * Math.sin(165 * Math.PI/180), fixed: true},
                {id: 'privacy', group: 3, x: centerX + radius2 * Math.cos(180 * Math.PI/180), y: centerY + radius2 * Math.sin(180 * Math.PI/180), fixed: true},
                {id: 'workflow', group: 3, x: centerX + radius2 * Math.cos(195 * Math.PI/180), y: centerY + radius2 * Math.sin(195 * Math.PI/180), fixed: true},

                // Interests subcategories (positions 14-18)
                {id: 'music', group: 3, x: centerX + radius2 * Math.cos(210 * Math.PI/180), y: centerY + radius2 * Math.sin(210 * Math.PI/180), fixed: true},
                {id: 'books', group: 3, x: centerX + radius2 * Math.cos(225 * Math.PI/180), y: centerY + radius2 * Math.sin(225 * Math.PI/180), fixed: true},
                {id: 'movies', group: 3, x: centerX + radius2 * Math.cos(240 * Math.PI/180), y: centerY + radius2 * Math.sin(240 * Math.PI/180), fixed: true},
                {id: 'sports', group: 3, x: centerX + radius2 * Math.cos(255 * Math.PI/180), y: centerY + radius2 * Math.sin(255 * Math.PI/180), fixed: true},
                {id: 'hobbies', group: 3, x: centerX + radius2 * Math.cos(270 * Math.PI/180), y: centerY + radius2 * Math.sin(270 * Math.PI/180), fixed: true},

                // Technology subcategories (positions 19-21)
                {id: 'devices', group: 3, x: centerX + radius2 * Math.cos(285 * Math.PI/180), y: centerY + radius2 * Math.sin(285 * Math.PI/180), fixed: true},
                {id: 'tools', group: 3, x: centerX + radius2 * Math.cos(300 * Math.PI/180), y: centerY + radius2 * Math.sin(300 * Math.PI/180), fixed: true},
                {id: 'platforms', group: 3, x: centerX + radius2 * Math.cos(315 * Math.PI/180), y: centerY + radius2 * Math.sin(315 * Math.PI/180), fixed: true}
            ];

            // Links are now provided by graphData.links (defined above)

            // Create a minimal simulation since we're using fixed positioning
            const simulation = d3.forceSimulation(nodes)
                .force('link', d3.forceLink(links).id(d => d.id).distance(d => {
                    // Link distances based on hierarchy levels
                    const sourceLevel = d.source.level || 0;
                    const targetLevel = d.target.level || 1;
                    if (sourceLevel === 0 && targetLevel === 1) return 120; // Root to categories
                    if (sourceLevel === 1 && targetLevel === 2) return 80;  // Categories to specifics
                    return 100; // Default
                }).strength(0.3)) // Stronger links to maintain structure
                .force('collision', d3.forceCollide().radius(d => {
                    // Collision radius based on level
                    if (d.level === 0) return 35;      // Largest collision for root
                    if (d.level === 1) return 25;      // Medium for categories
                    return 18;                          // Smallest for specifics
                }))
                .alpha(0.3)  // Moderate energy to allow some adjustment
                .alphaDecay(0.05)  // Slower decay to settle into position
                .alphaMin(0.01);   // Stop when mostly stable

            // Create links with immediate positioning
            const linkGroup = container.append('g').attr('class', 'links');
            const link = linkGroup.selectAll('line')
                .data(links)
                .enter().append('line')
                .attr('class', 'graph-link')
                .attr('stroke-width', 2)
                .attr('x1', d => {
                    const source = nodes.find(n => n.id === d.source);
                    return source ? source.x : 0;
                })
                .attr('y1', d => {
                    const source = nodes.find(n => n.id === d.source);
                    return source ? source.y : 0;
                })
                .attr('x2', d => {
                    const target = nodes.find(n => n.id === d.target);
                    return target ? target.x : 0;
                })
                .attr('y2', d => {
                    const target = nodes.find(n => n.id === d.target);
                    return target ? target.y : 0;
                });

            // Create nodes with immediate positioning and modern styling
            const nodeGroup = container.append('g').attr('class', 'nodes');
            const node = nodeGroup.selectAll('circle')
                .data(nodes)
                .enter().append('circle')
                .attr('class', 'graph-node')
                .attr('r', d => {
                    // Size based on level: Level 0 (root) = largest, Level 2 = smallest
                    if (d.level === 0) return 28;      // Root nodes (profile, projects, etc.)
                    if (d.level === 1) return 18;      // Category nodes (personal, professional, etc.)
                    return 12;                          // Specific nodes (name, skills, etc.)
                })
                .attr('fill', d => {
                    // Color based on level
                    if (d.level === 0) return 'url(#centerGradient)';      // Blue gradient for root
                    if (d.level === 1) return 'url(#midGradient)';         // Purple gradient for categories
                    return 'url(#leafGradient)';                           // Pink gradient for specifics
                })
                .attr('stroke', d => {
                    // Border color based on level
                    if (d.level === 0) return '#1e40af';      // Deep blue for root
                    if (d.level === 1) return '#7c3aed';      // Purple for categories
                    return '#e11d48';                          // Red for specifics
                })
                .attr('stroke-width', d => {
                    // Border thickness based on level
                    if (d.level === 0) return 4;              // Thickest for root
                    if (d.level === 1) return 3;              // Medium for categories
                    return 2;                                  // Thinnest for specifics
                })
                .attr('cx', d => d.x)
                .attr('cy', d => d.y)
                .style('filter', d => {
                    // Shadow effect based on level
                    if (d.level === 0) return 'drop-shadow(0 6px 16px rgba(30, 64, 175, 0.4))';     // Strong blue shadow for root
                    if (d.level === 1) return 'drop-shadow(0 4px 12px rgba(124, 58, 237, 0.3))';    // Purple shadow for categories
                    return 'drop-shadow(0 2px 8px rgba(225, 29, 72, 0.3))';                         // Red shadow for specifics
                })
                .call(d3.drag()
                    .on('start', dragstarted)
                    .on('drag', dragged)
                    .on('end', dragended));

            // Add gradient definitions for modern styling
            const defs = svg.append('defs');

            const centerGradient = defs.append('linearGradient')
                .attr('id', 'centerGradient')
                .attr('gradientUnits', 'userSpaceOnUse')
                .attr('x1', '0%').attr('y1', '0%')
                .attr('x2', '100%').attr('y2', '100%');
            centerGradient.append('stop').attr('offset', '0%').attr('stop-color', '#22d3ee');
            centerGradient.append('stop').attr('offset', '100%').attr('stop-color', '#0891b2');

            const midGradient = defs.append('linearGradient')
                .attr('id', 'midGradient')
                .attr('gradientUnits', 'userSpaceOnUse')
                .attr('x1', '0%').attr('y1', '0%')
                .attr('x2', '100%').attr('y2', '100%');
            midGradient.append('stop').attr('offset', '0%').attr('stop-color', '#a78bfa');
            midGradient.append('stop').attr('offset', '100%').attr('stop-color', '#7c3aed');

            const leafGradient = defs.append('linearGradient')
                .attr('id', 'leafGradient')
                .attr('gradientUnits', 'userSpaceOnUse')
                .attr('x1', '0%').attr('y1', '0%')
                .attr('x2', '100%').attr('y2', '100%');
            leafGradient.append('stop').attr('offset', '0%').attr('stop-color', '#fb7185');
            leafGradient.append('stop').attr('offset', '100%').attr('stop-color', '#e11d48');

            // Create text labels with immediate positioning
            const textGroup = container.append('g').attr('class', 'labels');
            const text = textGroup.selectAll('text')
                .data(nodes)
                .enter().append('text')
                .attr('class', 'node-text')
                .attr('x', d => d.x)
                .attr('y', d => d.y + 6) // Slightly lower for better centering
                .attr('font-weight', d => d.group === 1 ? '700' : d.group === 2 ? '600' : '500')
                .attr('font-size', d => d.group === 1 ? '14px' : d.group === 2 ? '11px' : '9px') // Smaller text for more nodes
                .attr('text-shadow', d => d.group === 1 ? '0 2px 4px rgba(0,0,0,0.5)' : '0 1px 2px rgba(0,0,0,0.3)')
                .text(d => d.id);

            // Optimized tick function with reduced DOM updates
            let tickCount = 0;
            simulation.on('tick', () => {
                tickCount++;

                // Only update DOM every few ticks for better performance
                if (tickCount % 2 === 0) {
                    link.attr('x1', d => d.source.x)
                        .attr('y1', d => d.source.y)
                        .attr('x2', d => d.target.x)
                        .attr('y2', d => d.target.y);

                    node.attr('cx', d => d.x)
                        .attr('cy', d => d.y);

                    text.attr('x', d => d.x)
                        .attr('y', d => d.y + 6);
                }
            });

            // Stop simulation after short time for instant feel
            setTimeout(() => {
                simulation.stop();
            }, 500);

            function dragstarted(event, d) {
                if (!event.active) simulation.alphaTarget(0.1).restart();
                d.fx = d.x;
                d.fy = d.y;
            }

            function dragged(event, d) {
                d.fx = event.x;
                d.fy = event.y;
            }

            function dragended(event, d) {
                if (!event.active) simulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
            }

            // Add click interactions for nodes
            node.on('click', function(event, d) {
                // Show detailed node information popup
                showNodeDetailsPopup(d, event);

                // Highlight connected nodes
                const connectedNodes = new Set([d.id]);
                links.forEach(link => {
                    if (link.source === d.id || link.source.id === d.id) {
                        connectedNodes.add(typeof link.target === 'string' ? link.target : link.target.id);
                    }
                    if (link.target === d.id || link.target.id === d.id) {
                        connectedNodes.add(typeof link.source === 'string' ? link.source : link.source.id);
                    }
                });

                // Apply highlighting
                node.style('opacity', n => connectedNodes.has(n.id) ? 1 : 0.3);
                link.style('opacity', l => {
                    const sourceId = typeof l.source === 'string' ? l.source : l.source.id;
                    const targetId = typeof l.target === 'string' ? l.target : l.target.id;
                    return connectedNodes.has(sourceId) && connectedNodes.has(targetId) ? 1 : 0.1;
                });
                text.style('opacity', n => connectedNodes.has(n.id) ? 1 : 0.3);

                // Reset after delay
                setTimeout(() => {
                    node.style('opacity', 1);
                    link.style('opacity', 1);
                    text.style('opacity', 1);
                }, 2000);

                // Memory details are now shown in the popup above
            });
        }

        // Available commands with descriptions
        const availableCommands = [
            { cmd: '/connect', args: '<path>', desc: 'Connect to memory store at path', aliases: '/con, /conn' },
            { cmd: '/new', args: '<path>', desc: 'Create new memory store at path (e.g., /tmp/my_store)', aliases: '/create' },
            { cmd: '/import', args: '<file_path>', desc: 'Import conversations from JSON or TXT files', placeholder: true },
            { cmd: '/remember', args: '<content>', desc: 'Store and classify new memory', aliases: '/rem' },
            { cmd: '/forget', args: '<key>', desc: 'Delete memory by key', aliases: '/del' },
            { cmd: '/refresh', args: '', desc: 'Refresh current connection', aliases: '/ref' },
            { cmd: '/demo', args: '', desc: 'Show original demo data' },
            { cmd: '/repo', args: '', desc: 'Show repository information' },
            { cmd: '/code', args: '', desc: 'Show Python integration code' },
            { cmd: '/proof', args: '<memory-path>', desc: 'Generate cryptographic proof for a memory' },
            { cmd: '/verify', args: '[proof] [key]', desc: 'Verify last proof or provide proof data' },
            { cmd: '/time-travel', args: '<commit>', desc: 'Travel to a specific commit and create a branch', aliases: '/tt' },
            { cmd: '/branch', args: '<create|delete|list>', desc: 'Manage branches', aliases: '/br' },
            { cmd: '/checkout', args: '<branch>', desc: 'Switch to a different branch', aliases: '/co' },
            { cmd: '/merge', args: '<branch>', desc: 'Merge a branch into current branch' },
            { cmd: '/commits', args: '', desc: 'Show recent commit history', aliases: '/log' },
            { cmd: '/branches', args: '', desc: 'List all branches' },
            { cmd: '/blame', args: '<key>', desc: 'Show Git-like blame history for memory key' },
            { cmd: '/help', args: '', desc: 'Show all available commands', aliases: '/h' },
            { cmd: '/summarize', args: '[type]', desc: 'Generate summary of memories (all, taxonomy, timeline, places, keys <pattern>)', aliases: '/sum' },
            { cmd: '/recall', args: '<query>', desc: 'Search and recall relevant memories using AI', aliases: '/search' },
            { cmd: '/timeline', args: '[YYYY-MM-DD description]', desc: 'Show timeline or add timeline event', aliases: '/tl' },
            { cmd: '/location', args: '[place description]', desc: 'Show places or add location event', aliases: '/loc' },

            // Developer & Debugging Commands (Coming Soon)
            { cmd: '/eval', args: '<question_or_file>', desc: 'Evaluate recall hit rate and answer quality', placeholder: true },
            { cmd: '/organize', args: '<path>', desc: 'Reorganize and optimize memory taxonomy for a subset of keys', placeholder: true },
            { cmd: '/inspect', args: '<path>', desc: 'Deep dive into a specific memory path with full history', placeholder: true },
            { cmd: '/diff', args: '[commit1] [commit2]', desc: 'Compare memory store between commits or show recent changes', aliases: '/d' },
            { cmd: '/benchmark', args: '', desc: 'Performance benchmarks for search, retrieval, classification', placeholder: true },
            { cmd: '/export', args: '<format>', desc: 'Export memories to JSON/CSV for external analysis', placeholder: true },
            { cmd: '/compare-stores', args: '<path1> <path2>', desc: 'Compare two memory stores', placeholder: true },
            { cmd: '/replay', args: '<session>', desc: 'Replay agent interactions with memory', placeholder: true },
            { cmd: '/template', args: '<type>', desc: 'Generate prompt templates for common integration patterns', placeholder: true }
        ];

        let selectedCommandIndex = -1;

        // Memory Input Bar Functionality
        function initializeMemoryInput() {
            const input = document.getElementById('memoryInput');
            const queryBtn = document.getElementById('queryBtn');
            const modelBtn = document.getElementById('modelBtn');
            const modelNameDisplay = document.getElementById('modelNameDisplay');
            const suggestions = document.getElementById('inputSuggestions');
            const modelDropdown = document.getElementById('modelDropdown');

            // Load command history from localStorage
            loadHistoryFromStorage();

            // Create command suggestions element
            createCommandSuggestionsElement();

            // Hide command suggestions when clicking outside input area
            document.addEventListener('click', (e) => {
                const input = document.getElementById('memoryInput');
                const commandSuggestions = document.getElementById('commandSuggestions');

                if (input && commandSuggestions &&
                    !input.contains(e.target) &&
                    !commandSuggestions.contains(e.target)) {
                    hideCommandSuggestions();
                }
            });

            // Hide command suggestions when mouse leaves the input container
            const inputContainer = input.parentElement;
            inputContainer.addEventListener('mouseleave', () => {
                // Always hide when mouse leaves, regardless of focus
                setTimeout(() => {
                    hideCommandSuggestions();
                }, 100);
            });


            // Handle input focus and blur
            input.addEventListener('focus', () => {
                if (!input.value.startsWith('/')) {
                    suggestions.style.display = 'block';
                }
            });

            input.addEventListener('blur', (e) => {
                // Delay hiding to allow clicking on suggestions
                setTimeout(() => {
                    suggestions.style.display = 'none';
                    hideCommandSuggestions();
                }, 200);
            });

            // Handle Enter key
            input.addEventListener('keydown', async (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();

                    // Check if user selected a command suggestion with arrow keys
                    const suggestions = document.getElementById('commandSuggestions');
                    if (suggestions && suggestions.style.display === 'block' && selectedCommandIndex >= 0) {
                        const items = suggestions.querySelectorAll('.command-suggestion');
                        const selectedCmd = availableCommands[parseInt(items[selectedCommandIndex].dataset.index)];

                        // Handle placeholder commands differently
                        if (selectedCmd.placeholder) {
                            showNotification(`${selectedCmd.cmd} - ${selectedCmd.desc}`, 'info', 3000);
                            hideCommandSuggestions();
                            input.value = '';
                        } else {
                            selectCommand(selectedCmd.cmd, selectedCmd.args);
                        }
                        return;
                    }

                    const value = input.value.trim();
                    if (value) {
                        // Add to history before processing
                        addToHistory(value);

                        // Clear input immediately
                        input.value = '';
                        resetHistoryIndex(); // Reset history navigation

                        // Check if it's a command
                        // Always call handleCommand - it now handles both commands and natural language

                        hideCommandSuggestions();
                        await handleCommand(value);
                    }
                } else if (e.key === 'Escape') {
                    hideCommandSuggestions();
                } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                    const suggestions = document.getElementById('commandSuggestions');
                    if (suggestions && suggestions.style.display === 'block') {
                        // Navigate command suggestions
                        e.preventDefault();
                        navigateCommandSuggestions(e.key === 'ArrowDown' ? 1 : -1);
                    } else {
                        // Navigate command history
                        e.preventDefault();
                        navigateHistory(e.key === 'ArrowUp' ? 'up' : 'down');
                    }
                }
            });

            // Handle input changes for command suggestions
            input.addEventListener('input', (e) => {
                // Reset history navigation when user types
                resetHistoryIndex();

                const value = e.target.value;
                if (value.startsWith('/')) {
                    showCommandSuggestions(value);
                    // Hide original suggestions when showing commands
                    suggestions.style.display = 'none';
                } else {
                    hideCommandSuggestions();
                    // Show original suggestions if input is focused and not a command
                    if (document.activeElement === input) {
                        suggestions.style.display = 'block';
                    }
                }
            });


            // Query button functionality
            queryBtn.addEventListener('click', () => {
                const value = input.value.trim();
                if (value) {
                    handleQuery(value);
                }
            });

            // Model button functionality
            modelBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const isVisible = modelDropdown.style.display === 'block';
                modelDropdown.style.display = isVisible ? 'none' : 'block';

                if (!isVisible) {
                    // Hide other dropdowns/suggestions
                    suggestions.style.display = 'none';
                    hideCommandSuggestions();
                }
            });

            // Model selection
            const modelOptions = document.querySelectorAll('.model-option');
            modelOptions.forEach(option => {
                option.addEventListener('click', () => {
                    // Check if model is available
                    const isAvailable = option.dataset.available === 'true';

                    if (!isAvailable) {
                        // Show notification for disabled models
                        const modelName = option.querySelector('.model-name').textContent;
                        showNotification(`${modelName} is coming soon! Currently only GPT-4o Mini is supported.`, 'info', 4000);
                        return;
                    }

                    // Remove selected class from all available options
                    modelOptions.forEach(opt => {
                        if (opt.dataset.available === 'true') {
                            opt.classList.remove('selected');
                        }
                    });

                    // Add selected class to clicked option
                    option.classList.add('selected');

                    // Get selected model
                    const selectedModel = option.dataset.model;
                    const modelName = option.querySelector('.model-name').textContent;

                    // Update button text and title
                    modelNameDisplay.textContent = modelName;
                    modelBtn.title = `LLM Model: ${modelName}`;

                    // Hide dropdown
                    modelDropdown.style.display = 'none';

                    // Store selected model (could be used by backend)
                    localStorage.setItem('selectedLLMModel', selectedModel);

                    // Show notification
                    showNotification(`LLM Model changed to: ${modelName}`, 'success', 3000);
                });
            });

            // Hide model dropdown when clicking outside
            document.addEventListener('click', (e) => {
                if (!modelDropdown.contains(e.target) && e.target !== modelBtn) {
                    modelDropdown.style.display = 'none';
                }
            });

            // Suggestion clicks
            const suggestionItems = document.querySelectorAll('.suggestion-item');
            suggestionItems.forEach(item => {
                item.addEventListener('click', () => {
                    const text = item.textContent;
                    if (text.includes('Search') || text.includes('Query')) {
                        const query = text.match(/"([^"]+)"/)?.[1] || text.split(' ').slice(-2).join(' ');
                        input.value = query;
                        handleQuery(query);
                    }
                });
            });

            // Initialize selected model from localStorage
            const savedModel = localStorage.getItem('selectedLLMModel');
            if (savedModel) {
                const savedOption = document.querySelector(`[data-model="${savedModel}"]`);
                if (savedOption && savedOption.dataset.available === 'true') {
                    // Remove selected class from all available options
                    modelOptions.forEach(opt => {
                        if (opt.dataset.available === 'true') {
                            opt.classList.remove('selected');
                        }
                    });

                    // Add selected class to saved option
                    savedOption.classList.add('selected');

                    // Update button text and title
                    const modelName = savedOption.querySelector('.model-name').textContent;
                    modelNameDisplay.textContent = modelName;
                    modelBtn.title = `LLM Model: ${modelName}`;
                }
            } else {
                // Default to GPT-4o Mini if no saved selection
                const defaultModel = document.querySelector('[data-model="gpt-4o-mini"]');
                if (defaultModel) {
                    const modelName = defaultModel.querySelector('.model-name').textContent;
                    modelNameDisplay.textContent = modelName;
                    modelBtn.title = `LLM Model: ${modelName}`;
                }
            }
        }

        // Command History Functions
        function addToHistory(command) {
            if (command.trim() && command !== commandHistory[commandHistory.length - 1]) {
                commandHistory.push(command);
                // Limit history to 50 entries
                if (commandHistory.length > 50) {
                    commandHistory.shift();
                }
                // Save to localStorage
                localStorage.setItem('memoryInputHistory', JSON.stringify(commandHistory));
            }
            resetHistoryIndex();
        }

        function resetHistoryIndex() {
            historyIndex = -1;
            currentInput = '';
        }

        function navigateHistory(direction) {
            const input = document.getElementById('memoryInput');

            if (commandHistory.length === 0) return;

            // Store current input when starting navigation
            if (historyIndex === -1) {
                currentInput = input.value;
            }

            if (direction === 'up') {
                if (historyIndex < commandHistory.length - 1) {
                    historyIndex++;
                    const historyItem = commandHistory[commandHistory.length - 1 - historyIndex];
                    input.value = historyItem;
                }
            } else if (direction === 'down') {
                if (historyIndex > 0) {
                    historyIndex--;
                    const historyItem = commandHistory[commandHistory.length - 1 - historyIndex];
                    input.value = historyItem;
                } else if (historyIndex === 0) {
                    historyIndex = -1;
                    input.value = currentInput;
                }
            }
        }

        function loadHistoryFromStorage() {
            try {
                const saved = localStorage.getItem('memoryInputHistory');
                if (saved) {
                    commandHistory = JSON.parse(saved);
                }
            } catch (e) {
                console.warn('Failed to load command history from storage:', e);
                commandHistory = [];
            }
        }

        function createCommandSuggestionsElement() {
            const input = document.getElementById('memoryInput');
            const inputContainer = input.parentElement;

            const commandSuggestions = document.createElement('div');
            commandSuggestions.id = 'commandSuggestions';
            commandSuggestions.style.cssText = `
                position: absolute;
                bottom: 100%;
                left: 0;
                right: 0;
                background: rgba(15, 23, 42, 0.95);
                backdrop-filter: blur(12px);
                border: 1px solid rgba(71, 85, 105, 0.3);
                border-bottom: none;
                border-radius: 12px 12px 0 0;
                box-shadow: 0 -8px 32px rgba(0, 0, 0, 0.3);
                z-index: 1001;
                display: none;
                max-height: 300px;
                pointer-events: none;
                overflow-y: auto;
            `;

            inputContainer.appendChild(commandSuggestions);
        }

        function showCommandSuggestions(input) {
            const suggestions = document.getElementById('commandSuggestions');
            if (!suggestions) return;

            const query = input.toLowerCase();
            const matchingCommands = availableCommands.filter(cmd =>
                cmd.cmd.startsWith(query) || query === '/'
            );

            if (matchingCommands.length === 0) {
                hideCommandSuggestions();
                return;
            }

            suggestions.innerHTML = matchingCommands.map((cmd, index) => {
                const isPlaceholder = cmd.placeholder;
                const commandColor = isPlaceholder ? '#6b7280' : '#22d3ee';
                const descColor = isPlaceholder ? '#6b7280' : '#94a3b8';
                const hoverBg = isPlaceholder ? 'rgba(107, 114, 128, 0.1)' : 'rgba(99, 102, 241, 0.1)';
                const cursor = isPlaceholder ? 'not-allowed' : 'pointer';
                const clickHandler = isPlaceholder ? `showNotification('${cmd.cmd} - ${cmd.desc}', 'info', 3000)` : `selectCommand('${cmd.cmd}', '${cmd.args}')`;

                return `
                <div class="command-suggestion" data-index="${index}" style="
                    padding: 12px 16px;
                    cursor: ${cursor};
                    border-bottom: 1px solid rgba(71, 85, 105, 0.2);
                    transition: all 0.2s ease;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    ${isPlaceholder ? 'opacity: 0.7;' : ''}
                " onmouseover="this.style.background='${hoverBg}'"
                   onmouseout="this.style.background='transparent'"
                   onclick="${clickHandler}">
                    <div>
                        <div style="color: ${commandColor}; font-family: 'JetBrains Mono', monospace; font-weight: 600;">
                            ${cmd.cmd}${cmd.args ? ' ' + cmd.args : ''}
                            ${isPlaceholder ? ' <span style="color: #f59e0b; font-size: 10px;">⚡ SOON</span>' : ''}
                        </div>
                        <div style="color: ${descColor}; font-size: 12px; margin-top: 2px;">
                            ${cmd.desc}
                        </div>
                    </div>
                </div>
            `}).join('');

            suggestions.style.display = 'block';
            suggestions.style.pointerEvents = 'auto';
            selectedCommandIndex = -1;
        }

        function hideCommandSuggestions() {
            const commandSuggestions = document.getElementById('commandSuggestions');
            if (commandSuggestions) {
                commandSuggestions.style.display = 'none';
                commandSuggestions.style.pointerEvents = 'none';
                selectedCommandIndex = -1;
            }

            // Restore original suggestions if input is focused and not a command
            const input = document.getElementById('memoryInput');
            const originalSuggestions = document.getElementById('inputSuggestions');
            if (input && originalSuggestions && document.activeElement === input && !input.value.startsWith('/')) {
                originalSuggestions.style.display = 'block';
            }
        }

        function navigateCommandSuggestions(direction) {
            const suggestions = document.getElementById('commandSuggestions');
            const items = suggestions.querySelectorAll('.command-suggestion');

            // Remove previous selection
            if (selectedCommandIndex >= 0) {
                items[selectedCommandIndex].style.background = 'transparent';
            }

            // Update selection
            selectedCommandIndex += direction;
            if (selectedCommandIndex < 0) selectedCommandIndex = items.length - 1;
            if (selectedCommandIndex >= items.length) selectedCommandIndex = 0;

            // Highlight new selection
            items[selectedCommandIndex].style.background = 'rgba(99, 102, 241, 0.2)';
            items[selectedCommandIndex].scrollIntoView({ block: 'nearest' });

            // Update input with selected command
            const input = document.getElementById('memoryInput');
            const selectedCmd = availableCommands[parseInt(items[selectedCommandIndex].dataset.index)];
            input.value = selectedCmd.cmd + (selectedCmd.args ? ' ' : '');

            // Position cursor at end
            setTimeout(() => input.setSelectionRange(input.value.length, input.value.length), 0);
        }

        function selectCommand(cmd, args) {
            const input = document.getElementById('memoryInput');
            input.value = cmd + (args ? ' ' : '');
            input.focus();

            // Position cursor at end or after space for args
            setTimeout(() => {
                const cursorPos = args ? input.value.length : input.value.length;
                input.setSelectionRange(cursorPos, cursorPos);
            }, 0);

            hideCommandSuggestions();
        }

        function handleQuery(query) {


            // Show visual feedback
            const input = document.getElementById('memoryInput');
            const queryBtn = document.getElementById('queryBtn');

            queryBtn.style.background = 'rgba(34, 211, 238, 0.3)';
            queryBtn.style.color = '#22d3ee';

            // Simulate search results (in real implementation, this would call the backend)
            setTimeout(() => {
                // Reset button style
                queryBtn.style.background = '';
                queryBtn.style.color = '';

                // Show mock results
                showQueryResults(query);
                input.value = '';
            }, 800);
        }


        function showQueryResults(query) {
            // Mock search results display
            const detailsPanel = document.getElementById('memoryDetails');
            const detailsPath = document.getElementById('detailsPath');
            const memoriesList = document.getElementById('memoriesList');

            detailsPath.textContent = `Search Results: "${query}"`;
            memoriesList.innerHTML = `
                <div class="memory-item">
                    <div class="memory-content">Found: Python programming skills - expert level</div>
                    <div class="memory-meta">
                        <span class="confidence-score">0.95</span>
                        <span>profile.professional.skills.python</span>
                    </div>
                </div>
                <div class="memory-item">
                    <div class="memory-content">Found: JavaScript development experience - 3+ years</div>
                    <div class="memory-meta">
                        <span class="confidence-score">0.88</span>
                        <span>profile.professional.experience.javascript</span>
                    </div>
                </div>
            `;

            detailsPanel.classList.add('open');
        }

        async function showBlameInfo(memoryKey) {
            if (!connectedStorePath) {
                showNotification('Please connect to a store first with /connect <path>', 'error');
                return;
            }

            showNotification(`Getting blame information for: ${memoryKey}...`, 'info');

            try {
                const response = await fetch(`/api/blame?path=${encodeURIComponent(connectedStorePath)}&key=${encodeURIComponent(memoryKey)}&namespace=default`);
                const result = await response.json();

                if (result.error) {
                    // Handle non-existent key with clear message
                    if (result.status === 'not_found') {
                        showNotification(`❌ Key Not Found: "${memoryKey}"\n\nThe memory key does not exist in the store.\nPlease check the key name and try again.`, 'error', 5000);
                    } else {
                        showNotification(`Error: ${result.error}`, 'error');
                    }
                    return;
                }

                // Format blame information for display
                let blameDisplay = `🕰️ Git Blame for Memory Key: ${result.key}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Full Key: ${result.full_key}
Status: ${result.status}
Total Commits: ${result.total_commits}

`;

                if (result.current_value) {
                    blameDisplay += `Current Value:
${JSON.stringify(result.current_value, null, 2)}

`;
                }

                blameDisplay += `Commit History:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`;

                if (result.blame_info && result.blame_info.length > 0) {
                    result.blame_info.forEach((commit, index) => {
                        const date = new Date(commit.date).toLocaleDateString();
                        blameDisplay += `
${index + 1}. ${commit.commit_hash} (${date})
   Author: ${commit.author} <${commit.email}>
   Message: ${commit.message}`;

                        if (commit.files && commit.files.length > 0) {
                            blameDisplay += `
   Files: ${commit.files.join(', ')}`;
                        }

                        if (commit.note) {
                            blameDisplay += `
   Note: ${commit.note}`;
                        }

                        blameDisplay += '\\n';
                    });
                } else {
                    blameDisplay += `
No commit history found for this key.
`;
                }

                // Show blame info in a modal-like notification
                showCodeModal(blameDisplay);

            } catch (error) {
                showNotification(`Failed to get blame info: ${error.message}`, 'error');
            }
        }

        // Time-travel functionality
        async function timeTravel(target) {
            if (!connectedStorePath) {
                showNotification('Please connect to a store first with /connect <path>', 'error');
                return;
            }

            // Parse target - could be commit hash or relative time
            let commitHash = target;

            // Check if target looks like a date/time description
            if (target.includes('ago') || target.includes('yesterday') || target.includes('hours') || target.includes('minutes')) {
                // For now, show placeholder - could integrate with git log --since
                showNotification('Date-based time travel coming soon. Please use commit hash for now.', 'info');
                return;
            }

            // Auto-generate branch name with timestamp for uniqueness
            const timestamp = Date.now();
            const branchName = `time-travel-${commitHash.slice(0, 8)}-${timestamp}`;

            try {
                // Create and checkout new branch at target commit
                const response = await fetch('/api/checkout', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        path: connectedStorePath,
                        target: commitHash,
                        create_branch: branchName
                    })
                });

                if (!response.ok) {
                    const error = await response.text();
                    throw new Error(error);
                }

                const result = await response.json();
                showNotification(`✨ Time-travel successful!\n${result.message}\n\nYou can now explore and modify memories at this point in time.\nChanges will be saved to branch: ${branchName}`, 'success', 8000);

                // Refresh the store to show the state at that commit
                await refreshStore();

                // Update branch display
                await updateBranchDisplay();

            } catch (error) {
                showNotification(`Time-travel failed: ${error.message}`, 'error');
            }
        }

        async function handleBranchCommand(subCmd, args) {
            if (!connectedStorePath) {
                showNotification('Please connect to a store first with /connect <path>', 'error');
                return;
            }

            switch(subCmd) {
                case 'create':
                case 'new':
                    if (!args) {
                        showNotification('Usage: /branch create <branch-name>', 'error');
                        return;
                    }
                    await createBranch(args);
                    break;

                case 'delete':
                case 'rm':
                    if (!args) {
                        showNotification('Usage: /branch delete <branch-name>', 'error');
                        return;
                    }
                    await deleteBranch(args);
                    break;

                case 'list':
                case 'ls':
                    await showBranchList();
                    break;

                default:
                    showNotification('Usage: /branch <create|delete|list> [args]', 'error');
            }
        }

        async function createBranch(branchName) {
            try {
                const response = await fetch('/api/create-branch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        path: connectedStorePath,
                        branch: branchName
                    })
                });

                if (!response.ok) {
                    const error = await response.text();
                    throw new Error(error);
                }

                const result = await response.json();
                showNotification(`✅ ${result.message}`, 'success');
                await updateBranchDisplay();

            } catch (error) {
                showNotification(`Failed to create branch: ${error.message}`, 'error');
            }
        }

        async function deleteBranch(branchName) {
            const confirm = window.confirm(`Are you sure you want to delete branch '${branchName}'?`);
            if (!confirm) return;

            try {
                const response = await fetch('/api/delete-branch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        path: connectedStorePath,
                        branch: branchName,
                        force: false
                    })
                });

                if (!response.ok) {
                    const error = await response.text();
                    if (error.includes('not fully merged')) {
                        const forceDelete = window.confirm(`Branch '${branchName}' is not fully merged. Force delete?`);
                        if (forceDelete) {
                            const forceResponse = await fetch('/api/delete-branch', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    path: connectedStorePath,
                                    branch: branchName,
                                    force: true
                                })
                            });
                            if (!forceResponse.ok) {
                                throw new Error(await forceResponse.text());
                            }
                            const forceResult = await forceResponse.json();
                            showNotification(`✅ ${forceResult.message}`, 'success');
                        }
                    } else {
                        throw new Error(error);
                    }
                } else {
                    const result = await response.json();
                    showNotification(`✅ ${result.message}`, 'success');
                }

                await updateBranchDisplay();

            } catch (error) {
                showNotification(`Failed to delete branch: ${error.message}`, 'error');
            }
        }

        async function checkoutBranch(branchName) {
            try {
                const response = await fetch('/api/checkout', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        path: connectedStorePath,
                        target: branchName
                    })
                });

                if (!response.ok) {
                    const error = await response.text();
                    throw new Error(error);
                }

                const result = await response.json();
                showNotification(`✅ ${result.message}`, 'success');

                // Refresh store to show new branch state
                await refreshStore();
                await updateBranchDisplay();

            } catch (error) {
                showNotification(`Failed to checkout branch: ${error.message}`, 'error');
            }
        }

        async function mergeBranch(sourceBranch) {
            const currentBranch = await getCurrentBranch();
            const confirm = window.confirm(`Merge '${sourceBranch}' into '${currentBranch}'?`);
            if (!confirm) return;

            try {
                const response = await fetch('/api/merge-branch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        path: connectedStorePath,
                        source: sourceBranch
                    })
                });

                if (!response.ok) {
                    const error = await response.text();
                    if (error.includes('conflict')) {
                        showNotification(`❌ Merge conflict detected!\n\nPlease resolve conflicts manually using git.`, 'error', 8000);
                    } else {
                        throw new Error(error);
                    }
                } else {
                    const result = await response.json();
                    showNotification(`✅ ${result.message}`, 'success', 5000);

                    // Refresh to show merged state
                    await refreshStore();
                }

            } catch (error) {
                showNotification(`Failed to merge: ${error.message}`, 'error');
            }
        }

        async function showBranchList() {
            if (!connectedStorePath) {
                showNotification('Please connect to a store first with /connect <path>', 'error');
                return;
            }

            try {
                const response = await fetch(`/api/branches?path=${encodeURIComponent(connectedStorePath)}`);
                if (!response.ok) throw new Error(await response.text());

                const data = await response.json();
                const branchList = data.branches.map(b =>
                    b === data.current ? `* ${b} (current)` : `  ${b}`
                ).join('\n');

                showNotification(`📌 Branches:\n${branchList}`, 'info', 8000);

            } catch (error) {
                showNotification(`Failed to get branches: ${error.message}`, 'error');
            }
        }

        async function showCommitHistory() {
            if (!connectedStorePath) {
                showNotification('Please connect to a store first with /connect <path>', 'error');
                return;
            }

            try {
                const response = await fetch(`/api/commits?path=${encodeURIComponent(connectedStorePath)}&limit=10`);
                if (!response.ok) throw new Error(await response.text());

                const data = await response.json();

                if (data.commits.length === 0) {
                    showNotification('No commits found', 'info');
                    return;
                }

                const commitList = data.commits.map(c => {
                    const date = new Date(c.timestamp * 1000);
                    const timeAgo = getTimeAgo(date);
                    return `${c.short_hash} - ${c.message} (${timeAgo})`;
                }).join('\n');

                showCodeModal(`📜 Recent Commits (${data.branch}):\n\n${commitList}`);

            } catch (error) {
                showNotification(`Failed to get commits: ${error.message}`, 'error');
            }
        }

        async function getCurrentBranch() {
            if (!connectedStorePath) return null;

            try {
                const response = await fetch(`/api/current-branch?path=${encodeURIComponent(connectedStorePath)}`);
                if (!response.ok) throw new Error(await response.text());

                const data = await response.json();
                return data.branch;

            } catch (error) {
                console.error('Failed to get current branch:', error);
                return null;
            }
        }

        async function updateBranchDisplay() {
            if (!connectedStorePath) return;

            try {
                // Get current branch info
                const branchResponse = await fetch(`/api/current-branch?path=${encodeURIComponent(connectedStorePath)}`);
                if (branchResponse.ok) {
                    const branchData = await branchResponse.json();

                    // Update the branch display in the UI
                    const storePathElement = document.querySelector('.store-path');
                    if (storePathElement) {
                        const branchBadge = storePathElement.querySelector('.branch-badge') ||
                                          document.createElement('span');
                        branchBadge.className = 'branch-badge';
                        branchBadge.style.cssText = 'margin-left: 10px; padding: 2px 8px; background: #4a5568; border-radius: 4px; font-size: 12px;';
                        branchBadge.textContent = `📌 ${branchData.branch}`;

                        if (!storePathElement.querySelector('.branch-badge')) {
                            storePathElement.appendChild(branchBadge);
                        }
                    }

                    // Hide/show remove button based on current branch
                    const removeBtn = document.getElementById('removeBranchBtn');
                    if (removeBtn) {
                        if (branchData.branch === 'main') {
                            removeBtn.classList.add('hidden');
                        } else {
                            removeBtn.classList.remove('hidden');
                        }
                    }
                }

                // Get branches for dropdown
                const branchesResponse = await fetch(`/api/branches?path=${encodeURIComponent(connectedStorePath)}`);
                if (branchesResponse.ok) {
                    const branchesData = await branchesResponse.json();
                    updateBranchesDropdown(branchesData.branches, branchesData.current);
                }

                // Update git history for current branch
                await updateGitHistory();

            } catch (error) {
                console.error('Failed to update branch display:', error);
            }
        }

        async function updateGitHistory() {
            if (!connectedStorePath) return;

            // Don't update git history if we're showing timeline view
            const gitTreeElement = document.querySelector('.git-tree');
            if (gitTreeElement) {
                if (gitTreeElement.querySelector('.timeline-grid-container') || gitTreeElement.getAttribute('data-showing') === 'timeline') {

                    return;
                }
            }

            // Removed automatic timeline view switching - let user control which view to see

            try {
                const response = await fetch(`/api/commits?path=${encodeURIComponent(connectedStorePath)}&limit=15`);
                if (!response.ok) return; // Don't show error, just keep existing history

                const data = await response.json();
                if (!gitTreeElement || data.commits.length === 0) return;

                // Generate git history HTML from real commits
                let historyHTML = '';
                data.commits.forEach((commit, index) => {
                    const isActive = index === 0; // First commit is active
                    const timeAgo = getTimeAgo(new Date(commit.timestamp * 1000));
                    const authorInitials = commit.author.split(' ').map(n => n[0]).join('').toUpperCase();

                    historyHTML += `
                        <div class="commit-node ${isActive ? 'active' : ''}" data-commit="${commit.hash}">
                            <div class="git-lines"><div class="commit-dot main"></div></div>
                            <div class="commit-info">
                                <button class="commit-menu-btn" data-commit="${commit.hash}">⋯</button>
                                <div class="commit-header">
                                    <div class="commit-hash">${commit.short_hash}</div>
                                    <div class="branch-tag">${data.branch}</div>
                                </div>
                                <div class="commit-message">${commit.message}</div>
                                <div class="commit-meta">
                                    <div class="commit-author">
                                        <div class="author-avatar">${authorInitials}</div>
                                        <span>${commit.author}</span>
                                    </div>
                                    <div class="commit-time">${timeAgo}</div>
                                </div>
                            </div>
                        </div>
                    `;
                });

                gitTreeElement.innerHTML = historyHTML;

                // Add menu button handlers
                initializeCommitMenus();

            } catch (error) {
                console.error('Failed to update git history:', error);
                // Keep existing history on error
            }
        }

        function getTimeAgo(date) {
            const seconds = Math.floor((new Date() - date) / 1000);
            const intervals = {
                year: 31536000,
                month: 2592000,
                week: 604800,
                day: 86400,
                hour: 3600,
                minute: 60
            };

            for (const [unit, secondsInUnit] of Object.entries(intervals)) {
                const interval = Math.floor(seconds / secondsInUnit);
                if (interval >= 1) {
                    return `${interval} ${unit}${interval === 1 ? '' : 's'} ago`;
                }
            }
            return 'just now';
        }

        // Initialize commit context menus
        function initializeCommitMenus() {
            const gitTreeElement = document.querySelector('.git-tree');
            if (!gitTreeElement) return;

            // Remove any existing menus
            document.querySelectorAll('.commit-context-menu').forEach(menu => menu.remove());

            // Add click handlers to menu buttons
            gitTreeElement.querySelectorAll('.commit-menu-btn').forEach(button => {
                button.addEventListener('click', (e) => {
                    e.stopPropagation(); // Prevent any parent click handlers
                    const commitHash = button.dataset.commit;
                    showCommitContextMenu(e, commitHash);
                });
            });

            // Close menus when clicking outside
            document.addEventListener('click', (e) => {
                if (!e.target.closest('.commit-context-menu') && !e.target.closest('.commit-menu-btn')) {
                    hideAllCommitMenus();
                }
            });
        }

        function showCommitContextMenu(event, commitHash) {
            // Hide any existing menus first
            hideAllCommitMenus();

            // Create menu element
            const menu = document.createElement('div');
            menu.className = 'commit-context-menu show';

            // Get commit info for display
            const shortHash = commitHash.slice(0, 8);

            menu.innerHTML = `
                <div class="commit-menu-item time-travel" data-action="time-travel" data-commit="${commitHash}">
                    <span class="menu-icon">🕐</span>
                    Time-travel to ${shortHash}
                </div>
                <div class="commit-menu-item" data-action="view-diff" data-commit="${commitHash}">
                    <span class="menu-icon">🔍</span>
                    View changes
                </div>
                <div class="commit-menu-item" data-action="copy-hash" data-commit="${commitHash}">
                    <span class="menu-icon">📋</span>
                    Copy commit hash
                </div>
                <div class="commit-menu-item" data-action="view-details" data-commit="${commitHash}">
                    <span class="menu-icon">👁</span>
                    View commit details
                </div>
            `;

            // Position menu near the button
            const rect = event.target.getBoundingClientRect();
            menu.style.position = 'fixed';
            menu.style.left = `${rect.right - 160}px`; // Align right edge with button
            menu.style.top = `${rect.bottom + 4}px`;

            // Add menu to document
            document.body.appendChild(menu);

            // Add click handlers to menu items
            menu.querySelectorAll('.commit-menu-item').forEach(item => {
                item.addEventListener('click', async (e) => {
                    const action = e.currentTarget.dataset.action;
                    const commit = e.currentTarget.dataset.commit;

                    hideAllCommitMenus();

                    switch(action) {
                        case 'time-travel':
                            await timeTravel(commit);
                            break;
                        case 'view-diff':
                            await showCommitDiff(commit);
                            break;
                        case 'copy-hash':
                            await copyToClipboard(commit);
                            showNotification(`Copied commit hash: ${commit.slice(0, 8)}`, 'success', 3000);
                            break;
                        case 'view-details':
                            await showCommitDetails(commit);
                            break;
                    }
                });
            });

            // Adjust position if menu goes off screen
            const menuRect = menu.getBoundingClientRect();
            if (menuRect.right > window.innerWidth) {
                menu.style.left = `${rect.left - menuRect.width}px`;
            }
            if (menuRect.bottom > window.innerHeight) {
                menu.style.top = `${rect.top - menuRect.height - 4}px`;
            }
        }

        function hideAllCommitMenus() {
            document.querySelectorAll('.commit-context-menu').forEach(menu => {
                menu.remove();
            });
        }

        async function copyToClipboard(text) {
            try {
                await navigator.clipboard.writeText(text);
            } catch (err) {
                // Fallback for older browsers
                const textArea = document.createElement('textarea');
                textArea.value = text;
                document.body.appendChild(textArea);
                textArea.select();
                document.execCommand('copy');
                document.body.removeChild(textArea);
            }
        }

        async function showCommitDiff(commitHash) {
            if (!connectedStorePath) {
                showNotification('Please connect to a memory store first', 'error');
                return;
            }

            try {
                // Get commit list to find the previous commit
                const response = await fetch(`/api/commits?path=${encodeURIComponent(connectedStorePath)}&limit=100`);
                if (!response.ok) throw new Error('Failed to get commit list');

                const data = await response.json();
                const commits = data.commits;

                // Find the current commit and its previous commit
                const currentIndex = commits.findIndex(c => c.hash === commitHash);
                if (currentIndex === -1) {
                    showNotification('Commit not found', 'error');
                    return;
                }

                const currentCommit = commits[currentIndex];
                const shortHash = commitHash.slice(0, 8);

                if (currentIndex === commits.length - 1) {
                    // This is the first commit (oldest), show it as initial commit
                    showNotification(`Showing initial commit diff for ${shortHash}`, 'info');
                    await showDiffModal(null, commitHash, false);
                } else {
                    // Compare with previous commit
                    const previousCommit = commits[currentIndex + 1];
                    const prevShortHash = previousCommit.hash.slice(0, 8);

                    showNotification(`Showing diff: ${prevShortHash} → ${shortHash}`, 'info');
                    await showDiffModal(previousCommit.hash, commitHash, false);
                }

            } catch (error) {
                console.error('Failed to show commit diff:', error);
                showNotification(`Error showing diff: ${error.message}`, 'error');
            }
        }

        async function showCommitDetails(commitHash) {
            if (!connectedStorePath) return;

            try {
                // Get detailed commit info
                const response = await fetch(`/api/commits?path=${encodeURIComponent(connectedStorePath)}&limit=100`);
                if (!response.ok) throw new Error('Failed to get commit details');

                const data = await response.json();
                const commit = data.commits.find(c => c.hash === commitHash);

                if (!commit) {
                    showNotification('Commit details not found', 'error');
                    return;
                }

                const date = new Date(commit.timestamp * 1000);
                const timeAgo = getTimeAgo(date);

                const details = `📋 Commit Details

Hash: ${commit.hash}
Short: ${commit.short_hash}
Author: ${commit.author} <${commit.email}>
Date: ${date.toLocaleString()}
Time: ${timeAgo}
Branch: ${data.branch}

Message: ${commit.message}`;

                showCodeModal(details);

            } catch (error) {
                showNotification(`Failed to get commit details: ${error.message}`, 'error');
            }
        }

        // Initialize branch selector functionality
        function initializeBranchSelector() {
            const branchSelector = document.getElementById('branchSelector');
            if (!branchSelector) return;

            branchSelector.addEventListener('change', async (e) => {
                const selectedBranch = e.target.value;

                // Update remove button visibility immediately based on selection
                const removeBtn = document.getElementById('removeBranchBtn');
                if (removeBtn) {
                    if (selectedBranch === 'main') {
                        removeBtn.classList.add('hidden');
                    } else {
                        removeBtn.classList.remove('hidden');
                    }
                }

                if (!connectedStorePath) {
                    // Reset to previous selection if no store connected
                    showNotification('Please connect to a store first with /connect <path>', 'error');
                    return;
                }

                // Don't switch if already on the selected branch
                const currentBranch = await getCurrentBranch();
                if (currentBranch === selectedBranch) {
                    return;
                }

                try {
                    showNotification(`Switching to branch: ${selectedBranch}...`, 'info');

                    // Use checkoutBranch function we already have
                    await checkoutBranch(selectedBranch);

                } catch (error) {
                    console.error('Failed to switch branch via dropdown:', error);
                    showNotification(`Failed to switch to branch: ${error.message}`, 'error');

                    // Reset dropdown to current branch on error
                    const actualCurrentBranch = await getCurrentBranch();
                    if (actualCurrentBranch && branchSelector) {
                        branchSelector.value = actualCurrentBranch;
                    }
                }
            });
        }

        // Initialize branch control buttons
        function initializeBranchButtons() {
            const addBtn = document.getElementById('addBranchBtn');
            const removeBtn = document.getElementById('removeBranchBtn');
            const branchSelector = document.getElementById('branchSelector');

            if (addBtn) {
                addBtn.addEventListener('click', handleCreateBranch);
            }

            if (removeBtn) {
                removeBtn.addEventListener('click', handleRemoveBranch);

                // Set initial visibility based on current branch selection
                if (branchSelector && branchSelector.value === 'main') {
                    removeBtn.classList.add('hidden');
                }
            }
        }

        async function handleCreateBranch() {
            if (!connectedStorePath) {
                showNotification('Please connect to a store first with /connect <path>', 'error');
                return;
            }

            const currentBranch = await getCurrentBranch();
            const newBranchName = prompt(`Create new branch from '${currentBranch}':`, `feature/new-feature`);

            if (!newBranchName) {
                return; // User cancelled
            }

            if (newBranchName.trim() === '') {
                showNotification('Branch name cannot be empty', 'error');
                return;
            }

            // Validate branch name (basic validation)
            if (!/^[a-zA-Z0-9_/-]+$/.test(newBranchName)) {
                showNotification('Branch name can only contain letters, numbers, underscores, hyphens, and forward slashes', 'error');
                return;
            }

            try {
                showNotification(`Creating branch '${newBranchName}'...`, 'info');

                const response = await fetch('/api/create-branch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        path: connectedStorePath,
                        branch: newBranchName,
                        from: currentBranch
                    })
                });

                if (!response.ok) {
                    const error = await response.text();
                    throw new Error(error);
                }

                const result = await response.json();

                // Automatically checkout the new branch
                await checkoutBranch(newBranchName);

                showNotification(`✅ Created and switched to branch '${newBranchName}'`, 'success');

            } catch (error) {
                console.error('Failed to create branch:', error);
                showNotification(`Failed to create branch: ${error.message}`, 'error');
            }
        }

        async function handleRemoveBranch() {
            if (!connectedStorePath) {
                showNotification('Please connect to a store first with /connect <path>', 'error');
                return;
            }

            const currentBranch = await getCurrentBranch();

            // Don't allow removing main branch
            if (currentBranch === 'main') {
                showNotification('Cannot delete the main branch', 'error');
                return;
            }

            const confirmDelete = confirm(`Are you sure you want to delete branch '${currentBranch}'?\n\nThis will switch to 'main' branch and delete '${currentBranch}'.`);
            if (!confirmDelete) {
                return;
            }

            try {
                showNotification(`Switching to main and deleting '${currentBranch}'...`, 'info');

                // First checkout main branch
                await checkoutBranch('main');

                // Then delete the branch
                const response = await fetch('/api/delete-branch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        path: connectedStorePath,
                        branch: currentBranch,
                        force: false
                    })
                });

                if (!response.ok) {
                    const error = await response.text();
                    if (error.includes('not fully merged')) {
                        const forceDelete = confirm(`Branch '${currentBranch}' is not fully merged. Force delete anyway?`);
                        if (forceDelete) {
                            const forceResponse = await fetch('/api/delete-branch', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    path: connectedStorePath,
                                    branch: currentBranch,
                                    force: true
                                })
                            });
                            if (!forceResponse.ok) {
                                throw new Error(await forceResponse.text());
                            }
                            showNotification(`✅ Force deleted branch '${currentBranch}' and switched to main`, 'success');

                            // Refresh branch dropdown to remove deleted branch
                            await updateBranchDisplay();
                        } else {
                            showNotification('Branch deletion cancelled', 'info');
                        }
                    } else {
                        throw new Error(error);
                    }
                } else {
                    showNotification(`✅ Deleted branch '${currentBranch}' and switched to main`, 'success');

                    // Refresh branch dropdown to remove deleted branch
                    await updateBranchDisplay();
                }

            } catch (error) {
                console.error('Failed to remove branch:', error);
                showNotification(`Failed to remove branch: ${error.message}`, 'error');
            }
        }



        // Update contributions count display
        function updateContributionsCount(activityData) {
            const countElement = document.getElementById('contributionsCount');
            if (countElement) {
                let totalCount = 0;
                for (const date in activityData) {
                    totalCount += activityData[date].count;
                }
                countElement.textContent = totalCount;
            }
        }

        async function renderGitHubStyleTimelineGrid(selectedYear = null) {
            const activityGrid = document.getElementById('activityGrid');
            const activityMonths = document.getElementById('activityMonths');
            const yearsList = document.getElementById('timelineYearsList');
            const demoBanner = document.getElementById('timelineDemoBanner');

            if (!activityGrid || !activityMonths) return;

            // Hide demo banner when showing real data
            if (demoBanner) {
                demoBanner.style.display = 'none';
            }

            // Set up year selector if not already done
            const currentYear = new Date().getFullYear();
            const targetYear = selectedYear || currentYear;
            const yearButton = document.getElementById('timelineYearButton');
            const yearPanel = document.getElementById('timelineYearPanel');
            const selectedYearSpan = document.getElementById('selectedYear');
            if (yearsList && yearButton && yearPanel && selectedYearSpan) {
                // Set current year in button
                selectedYearSpan.textContent = targetYear;

                // Clear existing items and add current and past years
                yearsList.innerHTML = '';
                for (let year = currentYear; year >= currentYear - 8; year--) {
                    const yearItem = document.createElement('div');
                    yearItem.className = 'timeline-year-item';
                    yearItem.textContent = year;
                    yearItem.dataset.year = year;

                    if (year === targetYear) {
                        yearItem.classList.add('active');
                    }

                    // Add year click listener
                    yearItem.addEventListener('click', function() {
                        // Remove active from all years
                        document.querySelectorAll('.timeline-year-item').forEach(item => {
                            item.classList.remove('active');
                        });
                        // Add active to clicked year
                        this.classList.add('active');
                        // Update button text
                        selectedYearSpan.textContent = this.dataset.year;
                        // Hide panel
                        yearPanel.classList.remove('show');
                        yearButton.classList.remove('open');
                        // Regenerate timeline for selected year
                        const selectedYear = parseInt(this.dataset.year);
                        renderGitHubStyleTimelineGrid(selectedYear);
                    });

                    yearsList.appendChild(yearItem);
                }
            }

            // Simple solution: just set the onclick directly
            if (yearButton && yearPanel) {
                yearButton.onclick = function(e) {
                    e.stopPropagation();
                    yearPanel.classList.toggle('show');
                    yearButton.classList.toggle('open');
                };
            }

            try {
                // Load real timeline data
                const timelineResult = await loadTimelineData();

                let realTimelineData = {};
                if (timelineResult.success && timelineResult.timeline_data) {
                    // Convert timeline data from YYYYMMDD format to YYYY-MM-DD format
                    const timelineData = timelineResult.timeline_data;
                    for (const [dateKey, content] of Object.entries(timelineData)) {
                        // Convert YYYYMMDD to YYYY-MM-DD
                        if (dateKey.length === 8) {
                            const formattedDate = `${dateKey.substring(0,4)}-${dateKey.substring(4,6)}-${dateKey.substring(6,8)}`;
                            realTimelineData[formattedDate] = {
                                level: 4, // High activity level for timeline events
                                count: 1,
                                content: content,
                                originalKey: dateKey
                            };
                        }
                    }
                }

                // Generate GitHub-style grid - expand range to include all timeline events
                const weeks = 65;
                const daysPerWeek = 7;

                // Calculate start date based on selected year, but expand to include all events
                let startDate;
                if (targetYear === currentYear) {
                    // For current year, show last 53 weeks from today but extend to include future events
                    const today = new Date();
                    startDate = new Date(today);
                    startDate.setDate(today.getDate() - (weeks * daysPerWeek));

                    // Find the latest timeline event to ensure we include it
                    const eventDates = Object.keys(realTimelineData).map(dateStr => new Date(dateStr));
                    if (eventDates.length > 0) {
                        const maxEventDate = new Date(Math.max(...eventDates));
                        const endDate = new Date(today);
                        endDate.setDate(today.getDate() + (weeks * daysPerWeek));

                        // If the latest event is beyond our normal range, we still show it
                    }
                } else {
                    // For past years, show the full year (start from Jan 1 minus some weeks to align grid)
                    startDate = new Date(targetYear, 0, 1); // Jan 1 of target year
                    const dayOfWeek = startDate.getDay(); // 0 = Sunday
                    startDate.setDate(startDate.getDate() - dayOfWeek); // Go back to the Sunday of that week
                }

                // Generate month labels
                const monthLabels = [];
                let currentMonth = null;
                let monthWeekCount = 0;

                // Filter timeline data by selected year if not current year
                let filteredTimelineData = realTimelineData;
                if (targetYear !== currentYear) {
                    filteredTimelineData = {};
                    for (const [dateStr, event] of Object.entries(realTimelineData)) {
                        const eventYear = new Date(dateStr).getFullYear();
                        if (eventYear === targetYear) {
                            filteredTimelineData[dateStr] = event;
                        }
                    }
                }

                // Create activity data mapping
                const activityData = {};

                // Calculate date range being checked - extend to include all timeline events
                let endDate = new Date(startDate);
                endDate.setDate(startDate.getDate() + (weeks * daysPerWeek) - 1);

                // Extend range to include all timeline events for the selected year
                const eventDates = Object.keys(filteredTimelineData).map(dateStr => new Date(dateStr));
                if (eventDates.length > 0) {
                    const maxEventDate = new Date(Math.max(...eventDates));
                    if (maxEventDate > endDate) {
                        endDate = maxEventDate;
                    }
                }

                // Calculate total days needed
                const totalDays = Math.ceil((endDate - startDate) / (1000 * 60 * 60 * 24)) + 1;

                for (let i = 0; i < totalDays; i++) {
                    const currentDate = new Date(startDate);
                    currentDate.setDate(startDate.getDate() + i);
                    const dateStr = currentDate.toISOString().split('T')[0];

                    // Check if we have timeline data for this date
                    if (filteredTimelineData[dateStr]) {
                        // filteredTimelineData already has the correct structure
                        activityData[dateStr] = filteredTimelineData[dateStr];
                    }
                }

                // Debug: show which timeline events are outside the range and add them anyway
                for (const [date, event] of Object.entries(filteredTimelineData)) {
                    if (!activityData[date]) {
                        activityData[date] = event;
                    }
                }

                // Generate month labels
                for (let week = 0; week < weeks; week++) {
                    const weekStartDate = new Date(startDate);
                    weekStartDate.setDate(startDate.getDate() + (week * 7));
                    const monthName = weekStartDate.toLocaleDateString('en-US', { month: 'short' });

                    if (currentMonth !== monthName) {
                        currentMonth = monthName;
                        monthWeekCount = 0;

                        // Only show month label if it has enough weeks to be visible
                        if (week === 0 || monthWeekCount === 0) {
                            monthLabels[week] = monthName;
                        }
                    }
                    monthWeekCount++;
                }

                // Clear and populate month labels
                activityMonths.innerHTML = '';
                monthLabels.forEach((month, weekIndex) => {
                    const monthDiv = document.createElement('div');
                    monthDiv.className = 'activity-month';
                    monthDiv.textContent = month || '';
                    monthDiv.style.gridColumnStart = weekIndex + 1;
                    activityMonths.appendChild(monthDiv);
                });

                // Calculate weeks needed for the extended range
                const totalWeeks = Math.ceil(totalDays / 7);

                // Generate grid
                activityGrid.innerHTML = '';
                activityGrid.style.display = 'grid';
                activityGrid.style.gridTemplateColumns = `repeat(${totalWeeks}, 1fr)`;
                activityGrid.style.gridTemplateRows = 'repeat(7, 1fr)';
                activityGrid.style.gap = '3px';

                for (let week = 0; week < totalWeeks; week++) {
                    for (let day = 0; day < daysPerWeek; day++) {
                        const currentDate = new Date(startDate);
                        currentDate.setDate(startDate.getDate() + (week * 7) + day);
                        const dateStr = currentDate.toISOString().split('T')[0];

                        // Skip dates beyond our calculated end date
                        if (currentDate > endDate) continue;

                        const dayElement = document.createElement('div');
                        dayElement.className = 'activity-day';
                        dayElement.style.gridColumn = week + 1;
                        dayElement.style.gridRow = day + 1;

                        const activity = activityData[dateStr];
                        if (activity) {
                            dayElement.classList.add(`level-${activity.level}`);
                            dayElement.title = `${formatDisplayDate(activity.originalKey)}: ${activity.content}`;

                            // Add click handler for timeline events
                            dayElement.addEventListener('click', () => {
                                showEventDetail(activity.originalKey, activity.content);
                            });

                            dayElement.style.cursor = 'pointer';
                        } else {
                            dayElement.classList.add('empty');
                            dayElement.title = formatDisplayDate(dateStr.replace(/-/g, ''));
                        }

                        activityGrid.appendChild(dayElement);
                    }
                }

                // Update contributions count
                const totalEvents = Object.keys(realTimelineData).length;
                const countElement = document.getElementById('contributionsCount');
                if (countElement) {
                    countElement.textContent = totalEvents;
                }

                // Initialize the Memory Activities panel
                const timelineDetailsContent = document.getElementById('timelineDetailsContent');
                if (timelineDetailsContent) {
                    if (totalEvents > 0) {
                        timelineDetailsContent.innerHTML = `
                            <div style="text-align: center; padding: 40px 20px; color: var(--text-secondary);">
                                <div style="font-size: 36px; margin-bottom: 16px;">👆</div>
                                <div style="font-size: 16px; font-weight: 600; margin-bottom: 8px; color: var(--text-primary);">Click on a Purple Square</div>
                                <div style="font-size: 14px; opacity: 0.7;">Select a day with timeline events to see details here</div>
                            </div>
                        `;
                    } else {
                        timelineDetailsContent.innerHTML = `
                            <div style="text-align: center; padding: 40px 20px; color: var(--text-secondary);">
                                <div style="font-size: 48px; margin-bottom: 16px;">📅</div>
                                <div style="font-size: 16px; font-weight: 600; margin-bottom: 8px; color: var(--text-primary);">No Timeline Events</div>
                                <div style="font-size: 14px; opacity: 0.7;">Add events with /timeline YYYY-MM-DD description</div>
                            </div>
                        `;
                    }
                }


            } catch (error) {
                console.error('Error rendering GitHub-style timeline grid:', error);
                activityGrid.innerHTML = `
                    <div style="text-align: center; padding: 60px 20px; color: var(--text-secondary);">
                        <div style="font-size: 48px; margin-bottom: 16px;">⚠️</div>
                        <div style="font-size: 18px; font-weight: 600; margin-bottom: 8px; color: var(--text-primary);">Error Loading Timeline</div>
                        <div style="font-size: 14px; opacity: 0.7;">${error.message}</div>
                    </div>
                `;
            }
        }

        async function renderRealTimelineInView() {
            const activityGrid = document.getElementById('activityGrid');
            if (!activityGrid) return;


            try {
                // Load timeline data
                const timelineResult = await loadTimelineData();

                if (timelineResult.success && timelineResult.timeline_data) {
                    // Clear the activity grid and add our timeline calendar
                    activityGrid.innerHTML = '';
                    activityGrid.style.display = 'block';
                    activityGrid.style.overflowY = 'auto';
                    activityGrid.style.maxHeight = '600px';

                    const timelineData = timelineResult.timeline_data;

                    if (Object.keys(timelineData).length === 0) {
                        // Show empty state
                        activityGrid.innerHTML = `
                            <div style="text-align: center; padding: 40px 20px; color: var(--text-secondary);">
                                <div style="font-size: 48px; margin-bottom: 16px;">📅</div>
                                <div style="font-size: 18px; font-weight: 600; margin-bottom: 8px; color: var(--text-primary);">No Timeline Events</div>
                                <div style="font-size: 14px; opacity: 0.7;">Add events with /timeline YYYY-MM-DD description</div>
                            </div>
                        `;
                    } else {
                        // Group events by month
                        const eventsByMonth = groupEventsByMonth(timelineData);

                        // Create calendar for each month
                        for (const [monthKey, events] of Object.entries(eventsByMonth)) {
                            const monthContainer = document.createElement('div');
                            monthContainer.style.marginBottom = '30px';

                            // Month header
                            const monthHeader = document.createElement('div');
                            monthHeader.textContent = formatMonthHeader(monthKey);
                            monthHeader.style.fontSize = '20px';
                            monthHeader.style.fontWeight = '600';
                            monthHeader.style.marginBottom = '16px';
                            monthHeader.style.color = 'var(--text-primary)';
                            monthHeader.style.borderBottom = '2px solid #9333ea';
                            monthHeader.style.paddingBottom = '8px';
                            monthContainer.appendChild(monthHeader);

                            // Month grid
                            const monthGrid = document.createElement('div');
                            monthGrid.style.display = 'grid';
                            monthGrid.style.gridTemplateColumns = 'repeat(7, 1fr)';
                            monthGrid.style.gap = '8px';
                            monthGrid.style.maxWidth = '400px';

                            // Add weekday headers
                            const weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
                            weekdays.forEach(day => {
                                const dayHeader = document.createElement('div');
                                dayHeader.textContent = day;
                                dayHeader.style.textAlign = 'center';
                                dayHeader.style.fontWeight = '600';
                                dayHeader.style.padding = '8px';
                                dayHeader.style.color = '#9ca3af';
                                dayHeader.style.fontSize = '12px';
                                monthGrid.appendChild(dayHeader);
                            });

                            // Get first day of month and days in month
                            const year = parseInt(monthKey.substring(0, 4));
                            const month = parseInt(monthKey.substring(4, 6)) - 1;
                            const firstDay = new Date(year, month, 1).getDay();
                            const daysInMonth = new Date(year, month + 1, 0).getDate();

                            // Add empty cells for days before month starts
                            for (let i = 0; i < firstDay; i++) {
                                const emptyCell = document.createElement('div');
                                monthGrid.appendChild(emptyCell);
                            }

                            // Add days of the month
                            for (let day = 1; day <= daysInMonth; day++) {
                                const dayStr = monthKey + String(day).padStart(2, '0');
                                const dayElement = document.createElement('div');
                                dayElement.textContent = day;
                                dayElement.style.padding = '12px 8px';
                                dayElement.style.textAlign = 'center';
                                dayElement.style.borderRadius = '8px';
                                dayElement.style.cursor = 'pointer';
                                dayElement.style.transition = 'all 0.2s ease';
                                dayElement.style.fontSize = '14px';
                                dayElement.style.fontWeight = '500';

                                if (events[dayStr]) {
                                    // Event day
                                    dayElement.style.background = '#9333ea';
                                    dayElement.style.color = 'white';
                                    dayElement.style.fontWeight = '600';
                                    dayElement.style.boxShadow = '0 2px 8px rgba(147, 51, 234, 0.3)';
                                    dayElement.title = `${formatDisplayDate(dayStr)}: ${events[dayStr]}`;

                                    // Add click handler
                                    dayElement.addEventListener('click', () => showEventDetail(dayStr, events[dayStr]));

                                    // Hover effect
                                    dayElement.addEventListener('mouseenter', () => {
                                        dayElement.style.transform = 'scale(1.1)';
                                        dayElement.style.boxShadow = '0 4px 12px rgba(147, 51, 234, 0.4)';
                                    });
                                    dayElement.addEventListener('mouseleave', () => {
                                        dayElement.style.transform = 'scale(1)';
                                        dayElement.style.boxShadow = '0 2px 8px rgba(147, 51, 234, 0.3)';
                                    });
                                } else {
                                    // Regular day
                                    dayElement.style.background = '#374151';
                                    dayElement.style.color = '#9ca3af';
                                    dayElement.style.border = '1px solid #4b5563';
                                }

                                monthGrid.appendChild(dayElement);
                            }

                            monthContainer.appendChild(monthGrid);
                            activityGrid.appendChild(monthContainer);
                        }
                    }

                    // Initialize the Memory Activities panel with instructions
                    const timelineDetailsContent = document.getElementById('timelineDetailsContent');
                    if (timelineDetailsContent) {
                        timelineDetailsContent.innerHTML = `
                            <div style="text-align: center; padding: 40px 20px; color: var(--text-secondary);">
                                <div style="font-size: 36px; margin-bottom: 16px;">👆</div>
                                <div style="font-size: 16px; font-weight: 600; margin-bottom: 8px; color: var(--text-primary);">Click on a Purple Date</div>
                                <div style="font-size: 14px; opacity: 0.7;">Select a day with timeline events to see details here</div>
                            </div>
                        `;
                    }

                } else {
                    // Show error or empty state
                    activityGrid.innerHTML = `
                        <div style="text-align: center; padding: 60px 20px; color: #fff;">
                            <div style="font-size: 48px; margin-bottom: 16px;">❌</div>
                            <div style="font-size: 18px; font-weight: 600; margin-bottom: 8px;">Failed to Load Timeline</div>
                            <div style="font-size: 14px; opacity: 0.7;">Could not retrieve timeline data</div>
                        </div>
                    `;
                }
            } catch (error) {
                console.error('Error rendering timeline in view:', error);
                activityGrid.innerHTML = `
                    <div style="text-align: center; padding: 60px 20px; color: #fff;">
                        <div style="font-size: 48px; margin-bottom: 16px;">⚠️</div>
                        <div style="font-size: 18px; font-weight: 600; margin-bottom: 8px;">Error Loading Timeline</div>
                        <div style="font-size: 14px; opacity: 0.7;">${error.message}</div>
                    </div>
                `;
            }
        }

        // Initialize timeline view with mock data
        async function initializeTimelineView() {
            const activityGrid = document.getElementById('activityGrid');
            const activityMonths = document.getElementById('activityMonths');
            const yearsList = document.getElementById('timelineYearsList');
            const demoBanner = document.getElementById('timelineDemoBanner');

            // Clear existing content to show real timeline data
            if (activityGrid) {
                activityGrid.innerHTML = '';
            }

            // If connected to a store, show real timeline data in GitHub-style grid
            if (connectedStorePath) {
                // Hide demo banner when connected
                if (demoBanner) {
                    demoBanner.style.display = 'none';
                }
                await renderGitHubStyleTimelineGrid();
                return;
            }

            // Show demo banner when in demo mode
            if (demoBanner) {
                demoBanner.style.display = 'block';
            }

            // Set up year selector with current and past years
            const currentYear = new Date().getFullYear();
            const yearButton = document.getElementById('timelineYearButton');
            const yearPanel = document.getElementById('timelineYearPanel');
            const selectedYearSpan = document.getElementById('selectedYear');

            if (yearsList && yearButton && yearPanel && selectedYearSpan) {
                // Set current year in button
                selectedYearSpan.textContent = currentYear;

                // Clear existing items and add current and past years
                yearsList.innerHTML = '';
                for (let year = currentYear; year >= currentYear - 8; year--) {
                    const yearItem = document.createElement('div');
                    yearItem.className = 'timeline-year-item';
                    yearItem.textContent = year;
                    yearItem.dataset.year = year;

                    if (year === currentYear) {
                        yearItem.classList.add('active');
                    }

                    // Add year click listener
                    yearItem.addEventListener('click', function() {
                        // Remove active from all years
                        document.querySelectorAll('.timeline-year-item').forEach(item => {
                            item.classList.remove('active');
                        });
                        // Add active to clicked year
                        this.classList.add('active');
                        // Update button text
                        selectedYearSpan.textContent = this.dataset.year;
                        // Hide panel
                        yearPanel.classList.remove('show');
                        yearButton.classList.remove('open');
                        // Regenerate timeline - check if we're connected to a store
                        const selectedYear = parseInt(this.dataset.year);
                        try {
                            if (connectedStorePath) {
                                renderGitHubStyleTimelineGrid(selectedYear);
                            } else {
                                regenerateTimelineForYear(selectedYear);
                            }
                        } catch (error) {
                            console.error('Error regenerating timeline for year', selectedYear, ':', error);
                        }
                    });

                    yearsList.appendChild(yearItem);
                }

                // Add button click listener to toggle panel
                yearButton.addEventListener('click', function(e) {
                    e.stopPropagation();
                    yearPanel.classList.toggle('show');
                    yearButton.classList.toggle('open');
                });

                // Close panel when clicking outside
                document.addEventListener('click', function(e) {
                    if (!yearPanel.contains(e.target) && !yearButton.contains(e.target)) {
                        yearPanel.classList.remove('show');
                        yearButton.classList.remove('open');
                    }
                });
            }

            // Generate mock timeline data (65 weeks - about 15 months)
            const weeks = 65;
            const daysPerWeek = 7;
            const today = new Date();
            const startDate = new Date(today);
            startDate.setDate(today.getDate() - (weeks * daysPerWeek));

            // Generate month labels
            const monthLabels = [];
            let currentMonth = null;
            let monthWeekCount = 0;

            // Mock activity data - simulate memory creation patterns
            const mockActivityData = {};

            // Generate some realistic patterns
            for (let i = 0; i < weeks * daysPerWeek; i++) {
                const currentDate = new Date(startDate);
                currentDate.setDate(startDate.getDate() + i);
                const dateStr = currentDate.toISOString().split('T')[0];

                // Simulate different activity levels based on day patterns
                const dayOfWeek = currentDate.getDay();
                const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
                const isRecent = i > (weeks * daysPerWeek) - 30; // Last 30 days more active

                let activityLevel = 0;
                const rand = Math.random();

                if (isRecent && !isWeekend && rand > 0.3) {
                    // More activity in recent weekdays
                    if (rand > 0.8) activityLevel = 4;
                    else if (rand > 0.6) activityLevel = 3;
                    else if (rand > 0.4) activityLevel = 2;
                    else activityLevel = 1;
                } else if (!isWeekend && rand > 0.5) {
                    // Some weekday activity
                    if (rand > 0.9) activityLevel = 3;
                    else if (rand > 0.7) activityLevel = 2;
                    else activityLevel = 1;
                } else if (isWeekend && rand > 0.8) {
                    // Rare weekend activity
                    activityLevel = 1;
                }

                if (activityLevel > 0) {
                    mockActivityData[dateStr] = {
                        level: activityLevel,
                        count: activityLevel * (Math.floor(Math.random() * 3) + 1),
                        memories: generateMockMemories(activityLevel, currentDate)
                    };
                }
            }

            // Generate month labels
            for (let week = 0; week < weeks; week++) {
                const firstDayOfWeek = new Date(startDate);
                firstDayOfWeek.setDate(startDate.getDate() + (week * daysPerWeek));
                const monthName = firstDayOfWeek.toLocaleDateString('en', { month: 'short' });

                if (currentMonth !== monthName) {
                    monthLabels.push({
                        month: monthName,
                        startWeek: week,
                        weekSpan: 1
                    });
                    currentMonth = monthName;
                    monthWeekCount = 1;
                } else if (monthLabels.length > 0) {
                    monthLabels[monthLabels.length - 1].weekSpan++;
                }
            }

            // Create month labels
            monthLabels.forEach(monthInfo => {
                const monthDiv = document.createElement('div');
                monthDiv.className = 'activity-month';
                monthDiv.textContent = monthInfo.month;
                monthDiv.style.width = `${monthInfo.weekSpan * 15}px`; // 12px day + 3px gap
                activityMonths.appendChild(monthDiv);
            });

            // Create the grid
            for (let week = 0; week < weeks; week++) {
                const weekDiv = document.createElement('div');
                weekDiv.className = 'activity-week';

                for (let day = 0; day < daysPerWeek; day++) {
                    const currentDate = new Date(startDate);
                    currentDate.setDate(startDate.getDate() + (week * daysPerWeek) + day);
                    const dateStr = currentDate.toISOString().split('T')[0];

                    const dayDiv = document.createElement('div');
                    dayDiv.className = 'activity-day';
                    dayDiv.dataset.date = dateStr;

                    if (mockActivityData[dateStr]) {
                        const level = mockActivityData[dateStr].level;
                        dayDiv.classList.add(`level-${level}`);
                        dayDiv.title = `${currentDate.toLocaleDateString()}: ${mockActivityData[dateStr].count} memories`;
                    } else {
                        dayDiv.classList.add('empty');
                        dayDiv.title = `${currentDate.toLocaleDateString()}: No memories`;
                    }

                    // Add click handler
                    dayDiv.addEventListener('click', () => {
                        showTimelineDetails(dateStr, mockActivityData[dateStr] || null);
                    });

                    weekDiv.appendChild(dayDiv);
                }

                activityGrid.appendChild(weekDiv);
            }
        }

        function generateMockMemories(level, date) {
            const mockMemories = [
                "Learned about React hooks",
                "Had coffee with Sarah",
                "Finished reading AI paper",
                "Started new project",
                "Meeting with team",
                "Discovered new restaurant",
                "Went to the gym",
                "Coded late into the night",
                "Watched a great documentary",
                "Fixed a challenging bug",
                "Visited the art museum",
                "Had dinner with family",
                "Completed online course",
                "Walked in the park",
                "Read an interesting article"
            ];

            const count = level * (Math.floor(Math.random() * 2) + 1);
            const memories = [];

            for (let i = 0; i < count; i++) {
                const memory = mockMemories[Math.floor(Math.random() * mockMemories.length)];
                const time = new Date(date);
                time.setHours(Math.floor(Math.random() * 24), Math.floor(Math.random() * 60));

                memories.push({
                    content: memory,
                    time: time.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
                });
            }

            return memories;
        }

        function showTimelineDetails(dateStr, activityData) {
            const timelineDetails = document.getElementById('timelineDetails');
            const detailsHeader = document.querySelector('.timeline-details-header');
            const detailsContent = document.getElementById('timelineDetailsContent');

            if (!activityData) {
                detailsHeader.textContent = `${new Date(dateStr).toLocaleDateString()} - No memories`;
                detailsContent.innerHTML = '<p style="color: var(--text-secondary); font-style: italic;">No memories recorded on this day</p>';
            } else {
                detailsHeader.textContent = `${new Date(dateStr).toLocaleDateString()} - ${activityData.count} memories`;

                let html = '';
                activityData.memories.forEach(memory => {
                    html += `
                        <div class="timeline-memory-item">
                            <div class="timeline-memory-time">${memory.time}</div>
                            <div class="timeline-memory-content">${memory.content}</div>
                        </div>
                    `;
                });

                detailsContent.innerHTML = html;
            }

            // Timeline details are always visible in the new layout
        }

        // Regenerate timeline for a specific year
        function regenerateTimelineForYear(year) {
            const activityGrid = document.getElementById('activityGrid');
            const activityMonths = document.getElementById('activityMonths');

            if (!activityGrid || !activityMonths) return;

            // Clear existing content
            activityGrid.innerHTML = '';
            activityMonths.innerHTML = '';

            // Generate timeline for the selected year (65 weeks - about 15 months)
            const weeks = 65;
            const daysPerWeek = 7;
            const endDate = new Date(year, 11, 31); // December 31 of selected year
            const startDate = new Date(endDate);
            startDate.setDate(endDate.getDate() - (weeks * daysPerWeek));

            // Generate mock activity data for selected year
            const mockActivityData = {};

            // Generate some realistic patterns (same logic as before)
            for (let i = 0; i < weeks * daysPerWeek; i++) {
                const currentDate = new Date(startDate);
                currentDate.setDate(startDate.getDate() + i);
                const dateStr = currentDate.toISOString().split('T')[0];

                // Skip future dates
                if (currentDate > new Date()) continue;

                // Generate activity patterns (simplified version)
                const dayOfWeek = currentDate.getDay();
                const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
                const isRecentWeek = Math.abs(new Date() - currentDate) < (7 * 24 * 60 * 60 * 1000 * 4);

                let activityLevel = 0;
                const rand = Math.random();

                if (!isWeekend) {
                    if (isRecentWeek && rand > 0.3) activityLevel = Math.min(4, Math.floor(rand * 5) + 1);
                    else if (rand > 0.6) activityLevel = Math.min(3, Math.floor(rand * 4) + 1);
                } else if (rand > 0.8) {
                    activityLevel = 1;
                }

                if (activityLevel > 0) {
                    mockActivityData[dateStr] = {
                        level: activityLevel,
                        count: activityLevel * (Math.floor(Math.random() * 3) + 1),
                        memories: generateMockMemories(activityLevel, currentDate)
                    };
                }
            }

            // Generate month labels for selected year
            const monthLabels = [];
            let currentMonth = null;

            for (let week = 0; week < weeks; week++) {
                const firstDayOfWeek = new Date(startDate);
                firstDayOfWeek.setDate(startDate.getDate() + (week * daysPerWeek));
                const monthName = firstDayOfWeek.toLocaleDateString('en', { month: 'short' });

                if (currentMonth !== monthName) {
                    monthLabels.push({
                        month: monthName,
                        startWeek: week,
                        weekSpan: 1
                    });
                    currentMonth = monthName;
                } else if (monthLabels.length > 0) {
                    monthLabels[monthLabels.length - 1].weekSpan++;
                }
            }

            // Create month labels
            monthLabels.forEach(monthInfo => {
                const monthDiv = document.createElement('div');
                monthDiv.className = 'activity-month';
                monthDiv.textContent = monthInfo.month;
                monthDiv.style.width = `${monthInfo.weekSpan * 15}px`;
                activityMonths.appendChild(monthDiv);
            });

            // Create the grid
            for (let week = 0; week < weeks; week++) {
                const weekDiv = document.createElement('div');
                weekDiv.className = 'activity-week';

                for (let day = 0; day < daysPerWeek; day++) {
                    const currentDate = new Date(startDate);
                    currentDate.setDate(startDate.getDate() + (week * daysPerWeek) + day);
                    const dateStr = currentDate.toISOString().split('T')[0];

                    const dayDiv = document.createElement('div');
                    dayDiv.className = 'activity-day';
                    dayDiv.dataset.date = dateStr;

                    if (mockActivityData[dateStr]) {
                        dayDiv.classList.add(`level-${mockActivityData[dateStr].level}`);
                        dayDiv.title = `${currentDate.toLocaleDateString()}: ${mockActivityData[dateStr].count} memories`;

                        dayDiv.addEventListener('click', function() {
                            showTimelineDetails(dateStr, mockActivityData[dateStr]);
                        });
                    } else {
                        dayDiv.classList.add('empty');
                        dayDiv.title = `${currentDate.toLocaleDateString()}: No memories`;

                        dayDiv.addEventListener('click', function() {
                            showTimelineDetails(dateStr, null);
                        });
                    }

                    weekDiv.appendChild(dayDiv);
                }

                activityGrid.appendChild(weekDiv);
            }
        }

        // Initialize statistics modal functionality
        function initializeStatsModal() {
            // Create modal instance
            storeStatsModal = new StoreStatsModal();

            // Add click handler to connection status button
            const connectionBtn = document.getElementById('connectionStatusBtn');
            if (connectionBtn) {
                connectionBtn.addEventListener('click', () => {
                    if (connectedStorePath) {
                        storeStatsModal.show(connectedStorePath);
                    } else {
                        showNotification('No memory store connected', 'warning');
                    }
                });

                // Make the button look clickable when connected
                connectionBtn.style.cursor = 'pointer';
            }
        }

        // Initialize the page
        function initializePage() {
            // Initialize demo mode tree with fold functionality
            restoreOriginalTreeView();

            // Initialize the memory input functionality
            initializeMemoryInput();

            // Initialize branch selector functionality
            initializeBranchSelector();

            // Initialize branch control buttons
            initializeBranchButtons();

            // Initialize view switching
            initializeViewSwitching();

            // Initialize statistics modal
            initializeStatsModal();
        }

        // Help Modal Function
        function showHelpModal() {
            const helpContent = generateHelpContent();

            const modal = document.createElement('div');
            modal.className = 'help-modal';
            modal.innerHTML = `
                <div class="help-modal-content">
                    <div class="help-modal-header">
                        <h2>🛠️ Git for AI Memory - Command Reference</h2>
                        <button class="help-modal-close">&times;</button>
                    </div>
                    <div class="help-modal-body">
                        ${helpContent}
                    </div>
                    <div class="help-modal-footer">
                        <div class="help-footer-info">
                            <span class="help-version">Memoir v0.1.0 • Git for AI Memory</span>
                        </div>
                        <button class="help-button primary" onclick="closeHelpModal()">Close</button>
                    </div>
                </div>
            `;

            // Add help modal CSS if not exists
            if (!document.getElementById('help-modal-styles')) {
                const styles = document.createElement('style');
                styles.id = 'help-modal-styles';
                styles.textContent = `
                    .help-modal {
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        background: rgba(0, 0, 0, 0.8);
                        backdrop-filter: blur(10px);
                        z-index: 10002;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        animation: fadeIn 0.3s ease-out;
                    }

                    .help-modal-content {
                        background: var(--bg-primary);
                        border: 1px solid var(--border-light);
                        border-radius: 20px;
                        max-width: 90%;
                        max-height: 85%;
                        width: 900px;
                        overflow: hidden;
                        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
                        animation: slideIn 0.3s ease-out;
                        display: flex;
                        flex-direction: column;
                    }

                    .help-modal-header {
                        padding: 24px 30px 20px;
                        border-bottom: 1px solid var(--border-light);
                        background: var(--bg-glass);
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        flex-shrink: 0;
                    }

                    .help-modal-header h2 {
                        margin: 0;
                        color: var(--text-primary);
                        font-size: 1.4em;
                        font-weight: 600;
                        display: flex;
                        align-items: center;
                        gap: 12px;
                    }

                    .help-modal-close {
                        background: none;
                        border: none;
                        color: var(--text-secondary);
                        font-size: 24px;
                        cursor: pointer;
                        padding: 8px;
                        border-radius: 8px;
                        transition: all 0.2s ease;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        width: 40px;
                        height: 40px;
                    }

                    .help-modal-close:hover {
                        background: var(--bg-glass-light);
                        color: var(--text-primary);
                        transform: scale(1.1);
                    }

                    .help-modal-body {
                        padding: 30px;
                        overflow-y: auto;
                        flex-grow: 1;
                        max-height: calc(85vh - 180px);
                    }

                    .help-modal-footer {
                        padding: 20px 30px;
                        border-top: 1px solid var(--border-light);
                        background: var(--bg-glass);
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        flex-shrink: 0;
                    }

                    .help-footer-info {
                        display: flex;
                        align-items: center;
                        gap: 16px;
                    }

                    .help-version {
                        color: var(--text-muted);
                        font-size: 13px;
                        font-weight: 500;
                    }

                    .help-button {
                        padding: 10px 24px;
                        border: none;
                        border-radius: 10px;
                        font-weight: 600;
                        cursor: pointer;
                        font-size: 14px;
                        transition: all 0.2s ease;
                        display: flex;
                        align-items: center;
                        gap: 8px;
                    }

                    .help-button.primary {
                        background: var(--accent-primary);
                        color: white;
                    }

                    .help-button.primary:hover {
                        background: var(--accent-secondary);
                        transform: translateY(-1px);
                        box-shadow: 0 4px 12px rgba(168, 85, 247, 0.3);
                    }

                    .help-section {
                        margin-bottom: 32px;
                    }

                    .help-section h3 {
                        color: var(--text-primary);
                        font-size: 1.2em;
                        font-weight: 600;
                        margin-bottom: 16px;
                        padding-bottom: 8px;
                        border-bottom: 2px solid var(--accent-primary);
                        display: flex;
                        align-items: center;
                        gap: 10px;
                    }

                    .help-command-grid {
                        display: grid;
                        grid-template-columns: 1fr 1fr;
                        gap: 16px;
                        margin-bottom: 20px;
                    }

                    .help-command-item {
                        background: var(--bg-glass);
                        border: 1px solid var(--border-light);
                        border-radius: 12px;
                        padding: 16px;
                        transition: all 0.2s ease;
                    }

                    .help-command-item:hover {
                        background: var(--bg-glass-light);
                        transform: translateY(-2px);
                        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                    }

                    .help-command-syntax {
                        font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
                        font-size: 14px;
                        font-weight: 600;
                        color: var(--accent-primary);
                        margin-bottom: 6px;
                    }

                    .help-command-desc {
                        font-size: 13px;
                        color: var(--text-secondary);
                        line-height: 1.4;
                        margin-bottom: 8px;
                    }

                    .help-command-aliases {
                        font-size: 11px;
                        color: var(--text-muted);
                        font-style: italic;
                    }

                    .help-coming-soon-badge {
                        background: linear-gradient(135deg, #fbbf24, #f59e0b);
                        color: #ffffff;
                        font-size: 10px;
                        font-weight: 700;
                        padding: 3px 8px;
                        border-radius: 12px;
                        margin-left: 8px;
                        box-shadow: 0 2px 4px rgba(251, 191, 36, 0.3);
                        animation: pulse 2s infinite;
                    }

                    .help-command-placeholder {
                        opacity: 0.75;
                        border: 1px dashed var(--border-light);
                    }

                    .help-command-placeholder:hover {
                        opacity: 0.9;
                        border-style: solid;
                    }

                    .help-placeholder-indicator {
                        background: linear-gradient(135deg, #fbbf24, #f59e0b);
                        color: #ffffff;
                        font-size: 9px;
                        font-weight: 700;
                        padding: 2px 6px;
                        border-radius: 8px;
                        margin-left: 8px;
                        box-shadow: 0 1px 3px rgba(251, 191, 36, 0.4);
                        animation: glow 1.5s ease-in-out infinite alternate;
                    }

                    .help-placeholder-note {
                        background: linear-gradient(135deg, rgba(251, 191, 36, 0.1), rgba(245, 158, 11, 0.1));
                        border: 1px solid rgba(251, 191, 36, 0.3);
                        border-radius: 12px;
                        padding: 16px;
                        margin-top: 20px;
                    }

                    .help-placeholder-note p {
                        color: var(--text-secondary);
                        margin: 0;
                        font-size: 13px;
                        line-height: 1.5;
                    }

                    .help-api-docs {
                        background: linear-gradient(135deg, rgba(59, 130, 246, 0.1), rgba(147, 51, 234, 0.1));
                        border: 1px solid rgba(59, 130, 246, 0.3);
                        border-radius: 12px;
                        padding: 16px;
                        margin-bottom: 20px;
                    }

                    .help-api-docs h4 {
                        color: var(--accent-secondary);
                        margin-bottom: 10px;
                        display: flex;
                        align-items: center;
                        gap: 8px;
                    }

                    .help-api-link {
                        color: var(--accent-secondary);
                        text-decoration: none;
                        font-weight: 600;
                        border-bottom: 1px solid transparent;
                        transition: all 0.2s ease;
                    }

                    .help-api-link:hover {
                        border-bottom-color: var(--accent-secondary);
                        transform: translateY(-1px);
                    }

                    @keyframes pulse {
                        0%, 100% { opacity: 1; }
                        50% { opacity: 0.8; }
                    }

                    @keyframes glow {
                        from { box-shadow: 0 1px 3px rgba(251, 191, 36, 0.4); }
                        to { box-shadow: 0 2px 8px rgba(251, 191, 36, 0.6); }
                    }

                    .help-info-box {
                        background: var(--bg-glass);
                        border: 1px solid var(--border-light);
                        border-radius: 12px;
                        padding: 20px;
                        margin-bottom: 24px;
                    }

                    .help-info-box h4 {
                        color: var(--accent-primary);
                        font-size: 1.1em;
                        font-weight: 600;
                        margin-bottom: 12px;
                        display: flex;
                        align-items: center;
                        gap: 8px;
                    }

                    .help-info-box p {
                        color: var(--text-secondary);
                        font-size: 14px;
                        line-height: 1.5;
                        margin-bottom: 8px;
                    }

                    @media (max-width: 768px) {
                        .help-command-grid {
                            grid-template-columns: 1fr;
                        }

                        .help-modal-content {
                            max-width: 95%;
                            width: auto;
                        }
                    }
                `;
                document.head.appendChild(styles);
            }

            document.body.appendChild(modal);

            // Add event listeners
            const closeBtn = modal.querySelector('.help-modal-close');
            closeBtn.onclick = () => closeHelpModal();

            // Close on background click
            modal.onclick = (e) => {
                if (e.target === modal) {
                    closeHelpModal();
                }
            };

            // Store reference for cleanup
            window.currentHelpModal = modal;
        }

        function generateHelpContent() {
            const coreCommands = availableCommands.filter(c => ['connect', 'new', 'import', 'remember', 'forget', 'refresh'].some(cmd => c.cmd.includes(cmd)));
            const gitCommands = availableCommands.filter(c => ['branch', 'checkout', 'merge', 'time-travel', 'commits', 'blame'].some(cmd => c.cmd.includes(cmd)));
            const viewCommands = availableCommands.filter(c => ['timeline', 'location', 'summarize', 'recall', 'proof', 'verify'].some(cmd => c.cmd.includes(cmd)));
            const devCommands = availableCommands.filter(c => ['eval', 'organize', 'inspect', 'diff', 'benchmark', 'export', 'compare-stores', 'replay', 'template'].some(cmd => c.cmd.includes(cmd)));

            return `
                <div class="help-api-docs">
                    <h4>📚 API Documentation</h4>
                    <p>For comprehensive API documentation, integration guides, and developer resources, visit: <a href="https://memoir-memoir.readthedocs-hosted.com/en/latest/" target="_blank" rel="noopener noreferrer" class="help-api-link">memoir-memoir.readthedocs-hosted.com</a></p>
                </div>

                <div class="help-info-box">
                    <h4>💡 Getting Started</h4>
                    <p>Memoir brings Git-like version control to AI memory systems. Connect to a memory store to start exploring your data with cryptographic integrity and full history tracking.</p>
                    <p><strong>Quick Start:</strong> Use <code>/connect /path/to/store</code> or <code>/new /tmp/my_store</code> to begin.</p>
                    <p><strong>🔍 Smart Search:</strong> Just type natural questions without commands! Example: <code>user preferences about colors</code> will automatically search your memories.</p>
                </div>

                <div class="help-section">
                    <h3>🔗 Core Operations</h3>
                    <div class="help-command-grid">
                        ${coreCommands.map(cmd => `
                            <div class="help-command-item ${cmd.placeholder ? 'help-command-placeholder' : ''}">
                                <div class="help-command-syntax">
                                    ${cmd.cmd}${cmd.args ? ' ' + cmd.args : ''}
                                    ${cmd.placeholder ? '<span class="help-placeholder-indicator">Soon</span>' : ''}
                                </div>
                                <div class="help-command-desc">${cmd.desc}</div>
                                ${cmd.aliases ? `<div class="help-command-aliases">Aliases: ${cmd.aliases}</div>` : ''}
                            </div>
                        `).join('')}
                    </div>
                </div>

                <div class="help-section">
                    <h3>🌿 Git-like Version Control</h3>
                    <div class="help-command-grid">
                        ${gitCommands.map(cmd => `
                            <div class="help-command-item ${cmd.placeholder ? 'help-command-placeholder' : ''}">
                                <div class="help-command-syntax">
                                    ${cmd.cmd}${cmd.args ? ' ' + cmd.args : ''}
                                    ${cmd.placeholder ? '<span class="help-placeholder-indicator">Soon</span>' : ''}
                                </div>
                                <div class="help-command-desc">${cmd.desc}</div>
                                ${cmd.aliases ? `<div class="help-command-aliases">Aliases: ${cmd.aliases}</div>` : ''}
                            </div>
                        `).join('')}
                    </div>
                </div>

                <div class="help-section">
                    <h3>📊 Data Views & Analysis</h3>
                    <div class="help-command-grid">
                        ${viewCommands.map(cmd => `
                            <div class="help-command-item ${cmd.placeholder ? 'help-command-placeholder' : ''}">
                                <div class="help-command-syntax">
                                    ${cmd.cmd}${cmd.args ? ' ' + cmd.args : ''}
                                    ${cmd.placeholder ? '<span class="help-placeholder-indicator">Soon</span>' : ''}
                                </div>
                                <div class="help-command-desc">${cmd.desc}</div>
                                ${cmd.aliases ? `<div class="help-command-aliases">Aliases: ${cmd.aliases}</div>` : ''}
                            </div>
                        `).join('')}
                    </div>
                </div>

                <div class="help-section">
                    <h3>🛠️ Developer & Debugging Tools <span class="help-coming-soon-badge">Supported Soon</span></h3>
                    <div class="help-command-grid">
                        ${devCommands.map(cmd => `
                            <div class="help-command-item ${cmd.placeholder ? 'help-command-placeholder' : ''}">
                                <div class="help-command-syntax">
                                    ${cmd.cmd}${cmd.args ? ' ' + cmd.args : ''}
                                    ${cmd.placeholder ? '<span class="help-placeholder-indicator">Soon</span>' : ''}
                                </div>
                                <div class="help-command-desc">${cmd.desc}</div>
                                ${cmd.aliases ? `<div class="help-command-aliases">Aliases: ${cmd.aliases}</div>` : ''}
                            </div>
                        `).join('')}
                    </div>
                    <div class="help-placeholder-note">
                        <p><strong>🚀 Coming Soon:</strong> Advanced developer tools are in active development. These commands will provide powerful debugging and analysis capabilities for AI agent development.</p>
                    </div>
                </div>

                <div class="help-info-box">
                    <h4>⚡ Pro Tips</h4>
                    <p>• Use aliases for faster typing: <code>/con</code> instead of <code>/connect</code>, <code>/rem</code> for <code>/remember</code></p>
                    <p>• Commands support tab completion and history - use ↑/↓ arrow keys to browse previous commands</p>
                    <p>• All memory operations are cryptographically secured with SHA-256 hashing</p>
                    <p>• Use <code>/demo</code> to explore sample data, <code>/repo</code> for GitHub repository information</p>
                </div>
            `;
        }

        function closeHelpModal() {
            if (window.currentHelpModal && window.currentHelpModal.parentNode) {
                document.body.removeChild(window.currentHelpModal);
                window.currentHelpModal = null;
            }
        }

        // Run initialization when page loads
        initializePage();
