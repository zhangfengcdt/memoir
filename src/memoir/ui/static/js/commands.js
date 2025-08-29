// Command handling module

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
    '/loc': '/location',
    '/rec': '/recall',
    '/diff': '/diff'
};

async function handleCommand(command) {
    console.log('Handling command:', command);
    const parts = command.trim().split(' ');
    let cmd = parts[0].toLowerCase();

    // Resolve alias to full command
    if (aliases[cmd]) {
        cmd = aliases[cmd];
    }

    console.log('Command parts:', parts);
    console.log('Resolved command:', cmd);

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
        if (!window.appConfig.connectedStorePath) {
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
            showVerifyWithInput(proofData);
        } else {
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
            showNotification('Usage: /merge <branch-name>', 'error');
            return;
        }
        await mergeBranch(source);
    } else if (cmd === '/commits' || cmd === '/log') {
        await showCommitLog();
    } else if (cmd === '/status') {
        await showRepoStatus();
    } else if (cmd === '/diff') {
        const args = parts.slice(1).join(' ').trim();
        await showDiff(args);
    } else if (cmd === '/recall') {
        const query = parts.slice(1).join(' ').trim();
        if (!query) {
            showNotification('Usage: /recall <query>', 'error');
            return;
        }
        await handleRecallCommand(query);
    } else if (cmd === '/timeline') {
        const subCmd = parts[1];
        const args = parts.slice(2).join(' ').trim();
        await handleTimelineCommand(subCmd, args);
    } else if (cmd === '/location' || cmd === '/place') {
        const subCmd = parts[1];
        const args = parts.slice(2).join(' ').trim();
        await handleLocationCommand(subCmd, args);
    } else if (cmd === '/summary') {
        const summaryType = parts[1] || 'all';
        await summarizeMemoryStore(summaryType);
    } else if (cmd === '/help') {
        showHelp();
    } else if (cmd === '/clear') {
        clearOutput();
    } else {
        showNotification(`Unknown command: ${cmd}. Type /help for available commands.`, 'error');
    }
}

// Export functions
window.commandHandler = {
    handleCommand,
    aliases
};