import { execFile, spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { access, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { homedir } from 'node:os';
import { promisify } from 'node:util';
import { type Config, type Plugin, tool } from '@opencode-ai/plugin';

const execFileAsync = promisify(execFile);

export const SECRET_PATTERN = /(api[_-]?key|token|secret|password|passwd|private[_-]?key|-----BEGIN [A-Z ]*PRIVATE KEY-----)/i;
const MEMOIR_PACKAGE = 'memoir-ai';

type CommandOutput = {
  parts: unknown[];
};

type OpenCodeConfig = Config & {
  command?: Config['command'];
};

type MemoirRememberArgs = {
  content: string;
  path?: string | string[];
  namespace?: string;
  replace?: boolean;
};

type MemoirRecallArgs = {
  query?: string;
  namespace?: string;
  namespaces?: string[];
  includeMetrics?: boolean;
};

type MemoirGetArgs = {
  keys: string[];
  namespace?: string;
};

/** Derive `~/.memoir/<slug>` from cwd. Override via `store` plugin option or `MEMOIR_STORE` env var. */
export function deriveStorePath(cwd: string = process.cwd()): string {
  if (pluginStoreOverride) return pluginStoreOverride;
  const configured = process.env.MEMOIR_STORE;
  if (configured) return configured;
  const slug = cwd.replace(/[/.]/g, '-');
  return join(homedir(), '.memoir', slug);
}

/** Set by plugin options (`store` key). */
export let pluginStoreOverride: string | undefined;

async function ensureStore(store: string): Promise<void> {
  try {
    await access(join(store, '.git'));
  } catch {
    const result = await runMemoir(['new', store, '--taxonomy-builtin']);
    if (result.startsWith('Memoir command failed')) {
      throw new Error(result);
    }
  }
}

async function runMemoir(args: string[], options: { cwd?: string } = {}): Promise<string> {
  try {
    const { stdout } = await execFileAsync('memoir', args, {
      cwd: options.cwd ?? process.cwd(),
      env: process.env,
      maxBuffer: 1024 * 1024,
    });
    return stdout.trim();
  } catch (memoirError) {
    // Fallbacks match the Claude Code plugin: uvx, then uv tool run.
    try {
      const { stdout } = await execFileAsync('uvx', ['--from', MEMOIR_PACKAGE, 'memoir', ...args], {
        cwd: options.cwd ?? process.cwd(),
        env: process.env,
        maxBuffer: 1024 * 1024,
      });
      return stdout.trim();
    } catch {
      try {
        const { stdout } = await execFileAsync('uv', ['tool', 'run', '--from', MEMOIR_PACKAGE, 'memoir', ...args], {
          cwd: options.cwd ?? process.cwd(),
          env: process.env,
          maxBuffer: 1024 * 1024,
        });
        return stdout.trim();
      } catch {
        const err = memoirError as Error & { stdout?: string; stderr?: string; code?: number };
        const detail = (err.stderr || err.stdout || err.message).trim();
        return `Memoir command failed${err.code ? ` (${err.code})` : ''}: ${detail}`;
      }
    }
  }
}

async function statusJson(store: string): Promise<string> {
  await ensureStore(store);
  const raw = await runMemoir(['--json', '-s', store, 'status'], { cwd: store });
  try {
    const data = JSON.parse(raw);
    const branch = (await runCommand('git', ['branch', '--show-current'], { cwd: process.cwd() })).trim();
    data.opencode = { store, project_git_root: process.cwd(), project_git_branch: branch };
    return JSON.stringify(data, null, 2);
  } catch {
    return raw;
  }
}

async function runCommand(cmd: string, args: string[], options: { cwd?: string } = {}): Promise<string> {
  const { stdout } = await execFileAsync(cmd, args, {
    cwd: options.cwd ?? process.cwd(),
    env: process.env,
    maxBuffer: 1024 * 1024,
  });
  return stdout.trim();
}

type SpawnSpec = { command: string; args: string[]; label: string };

function memoirSpawnSpecs(args: string[]): SpawnSpec[] {
  return [
    { command: 'memoir', args, label: 'memoir' },
    { command: 'uvx', args: ['--from', MEMOIR_PACKAGE, 'memoir', ...args], label: 'uvx' },
    { command: 'uv', args: ['tool', 'run', '--from', MEMOIR_PACKAGE, 'memoir', ...args], label: 'uv tool run' },
  ];
}

async function launchUi(store: string): Promise<string> {
  await ensureStore(store);
  const pidDir = join(homedir(), '.memoir', 'ui-servers');
  await mkdir(pidDir, { recursive: true });
  const hash = createHash('sha256').update(store).digest('hex').slice(0, 8);
  const pidfile = join(pidDir, `${hash}.json`);

  try {
    const existing = JSON.parse(await readFile(pidfile, 'utf8'));
    if (existing?.pid && existing?.url && process.kill(Number(existing.pid), 0)) {
      return JSON.stringify({ ...existing, reused: true }, null, 2);
    }
  } catch {
    await rm(pidfile, { force: true }).catch(() => undefined);
  }

  let lastError = '';
  for (const spec of memoirSpawnSpecs(['ui', store])) {
    const child = spawn(spec.command, spec.args, {
      detached: true,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: process.env,
    });

    let output = '';
    child.stdout?.on('data', chunk => { output += String(chunk); });
    child.stderr?.on('data', chunk => { output += String(chunk); });

    const spawnFailed = new Promise<string | null>(resolve => {
      child.once('error', error => resolve(String(error.message || error)));
      child.once('spawn', () => resolve(null));
    });
    const error = await spawnFailed;
    if (error) {
      lastError = `${spec.label}: ${error}`;
      continue;
    }

    child.unref();

    const urlPattern = /https?:\/\/(?:localhost|127\.0\.0\.1):\d+\S*/;
    const deadline = Date.now() + 5000;
    while (Date.now() < deadline) {
      const match = output.match(urlPattern);
      if (match) {
        const url = match[0];
        const data = { pid: child.pid, url, store, command: spec.label, started: new Date().toISOString(), reused: false };
        await writeFile(pidfile, JSON.stringify(data, null, 2));
        return JSON.stringify(data, null, 2);
      }
      await new Promise(resolve => setTimeout(resolve, 100));
    }

    return `Memoir UI started with ${spec.label} (pid ${child.pid ?? 'unknown'}), but URL was not detected yet.\n${output.trim()}`.trim();
  }

  return `Memoir UI failed to start: ${lastError || 'no launcher succeeded'}`;
}

export function coercePaths(path: string | string[] | undefined): string[] {
  if (!path) return [];
  return Array.isArray(path) ? path.filter(Boolean) : [path];
}

function pushText(output: CommandOutput, text: string): void {
  output.parts.length = 0;
  output.parts.push({ type: 'text', text });
}

/** Format JSON string with 2-space indentation. Passes non-JSON through unchanged. */
export function tryPrettyJson(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

// === Recall Gate Logic ===
// Mirrors the Claude Code plugin's UserPromptSubmit hook exactly.
// Every user message is checked; the gate decides whether to inject a
// recall instruction into the next LLM call.

/**
 * Sessions waiting for a recall instruction (one-shot, consumed by
 * experimental.chat.system.transform on the next LLM call).
 */
const pendingRecall = new Set<string>();

/** Short acknowledgements that never trigger recall. */
const ACK_PATTERN = /^(ok|thanks|thank you|sounds good|got it|👍|🙏|perfect|great|cool|nice|awesome|understood|makes sense|agree|right|sure|yes|no|done|nvm|never mind|lgtm|looks good|proceed|continue|good|fine)\b/i;

/** Explicit memoir commands always trigger recall regardless of length. */
const EXPLICIT_RECALL_PATTERN = /\b(memoir:recall|memoir:remember|memoir-recall|memoir-remember)\b|(\/recall|\/remember)\b/i;

/** Positive-list patterns — identical to the Claude Code UserPromptSubmit gate. */
const RECALL_TRIGGER_PATTERNS = [
  // Action verbs and domain nouns
  /\b(add|build|implement|refactor|redesign|design|create|write|set( |-)up|wire( |-)up|integrate|migrate|rewrite|extract|extend|plumb|hook( |-)up|ship|scaffold|optimize|fix|debug|review|architect|model|schema|API|service|feature|module|system|pipeline|workflow|make|move|replace|convert|swap|remove|clean( |-)up|transform|investigate|explore|figure( |-)out|plan|decide|choose|pick|compare|walk( |-)?me( |-)?through|take( |-)?a( |-)?stab|help( |-)?me|harness|hook|prompt|test)\b/i,
  // Question starts (how/why/what/where/when/should/can/could/would/is it/are we/do I/does it)
  /^(how|why|what|where|when|should|can|could|would|is it|are we|do I|does it)\b.*\?/im,
  // Code blocks (triple backticks)
  /```/,
  // Code definitions
  /\b(def|function|class|import|export)\s+/,
  // Memoir/recall keywords
  /\b(memoir|recall|remember|memory)\b/i,
  // File extensions
  /\b\w+\.(py|js|ts|tsx|scala|java|go|rs|rb|md|json|yaml|yml|toml|sh|bash|css|html|kt|swift|c|cpp|h|hpp)\b/i,
  // File paths (slash-containing tokens)
  /\w+\/\w+/,
];

export function isAcknowledgement(text: string): boolean {
  const trimmed = text.trim().toLowerCase();
  const words = trimmed.split(/\s+/);
  return words.length <= 5 && ACK_PATTERN.test(trimmed);
}

/**
 * Decide whether a user message should trigger a recall instruction.
 * Identical gate logic to the Claude Code UserPromptSubmit hook:
 *
 *  1. Empty text → skip
 *  2. Explicit `/recall` / `memoir:recall` commands → always fire
 *  3. < 10 chars → skip (empty or noise)
 *  4. Acknowledgements (ok/thanks/…) → skip
 *  5. < 40 chars without explicit command → skip (too short for intent)
 *  6. ≥ 40 chars + any trigger pattern → fire
 */
export function shouldTriggerRecall(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed) return false;
  // Explicit memoir commands fire regardless of length
  if (EXPLICIT_RECALL_PATTERN.test(trimmed)) return true;
  if (trimmed.length < 10) return false;
  if (isAcknowledgement(trimmed)) return false;
  // Gate: ≥ 40 chars + any trigger
  if (trimmed.length >= 40 && RECALL_TRIGGER_PATTERNS.some(p => p.test(trimmed))) return true;
  return false;
}



// === Capture (Code Changes & Metrics) ===
// Mirrors the Claude Code Stop hook: metrics accumulation + code change audit.
// Since OpenCode has no transcript or built-in LLM access, we use
// tool.execute.after to observe edits and tool calls in real time.

const EDIT_TOOLS = new Set(['Edit', 'Write', 'MultiEdit', 'NotebookEdit', 'apply_patch']);

interface EditRecord {
  tool: string;
  filePath: string;
  snippet: string;
  timestamp: number;
}

interface ToolMetrics {
  calls: number;
  errors: number;
}

/** Edits accumulated during the current assistant turn. */
const pendingEdits: EditRecord[] = [];

/** Per-tool call and error counters for the session. */
const toolMetrics = new Map<string, ToolMetrics>();

/**
 * Flush pending edits as a code change entry, then save metrics.
 * Called at each new user message (end of assistant turn) and at dispose.
 */
async function flushCapture(): Promise<void> {
  const edits = pendingEdits.splice(0);
  const hasMetrics = toolMetrics.size > 0;
  if (edits.length === 0 && !hasMetrics) return;

  try {
    const store = deriveStorePath();
    if (!store) return;
    await ensureStore(store);

    // Code change audit entry (cf. Claude Code metrics.code.<branch>)
    if (edits.length > 0) {
      const files = [...new Set(edits.map(e => e.filePath))];
      const summary = `Changed ${edits.length} block(s) across ${files.length} file(s): ${files.join(', ')}`;
      await runMemoir(['-s', store, 'remember', '--replace', summary, '-p', 'metrics.code.changes'], { cwd: store });
    }

    // Metrics accumulator entry (cf. Claude Code metrics.turn.<branch>)
    if (hasMetrics) {
      const entries = [...toolMetrics.entries()].map(
        ([tool, m]) => `${tool}:${m.calls}:${m.errors}`
      );
      await runMemoir(['-s', store, 'remember', '--replace', entries.join(' | '), '-p', 'metrics.turn'], { cwd: store });
    }
  } catch {
    // Silent fail — capture is best-effort
  }
}

function registerCommands(config: OpenCodeConfig): void {
  config.command = config.command ?? {};

  config.command['memoir:status'] = {
    description: 'Show Memoir status for the current OpenCode project',
    template: 'Show Memoir status for this OpenCode project.',
  };

  config.command['memoir:ui'] = {
    description: 'Launch or reopen the Memoir web UI for this project store',
    template: 'Launch or reopen the Memoir UI for this project.',
  };

  config.command['memoir:remember'] = {
    description: 'Save a durable fact, preference, rule, or decision to Memoir',
    template: `Use Memoir to save this durable memory now.\n\nUSER REQUEST:\n$ARGUMENTS\n\nExtract the memory content, choose a semantic path if none is supplied, then call the memoir_remember tool. Never save secrets.`,
  };

  config.command['memoir:recall'] = {
    description: 'Recall relevant facts from Memoir before answering',
    template: `Recall relevant Memoir memories for this request.\n\nUSER REQUEST:\n$ARGUMENTS\n\nUse memoir_recall first. It checks default plus onboard namespaces unless a namespace is specified. Then call memoir_get with the matching namespace for exact values before answering.`,
  };

  config.command['memoir:onboard'] = {
    description: 'Populate or refresh Memoir onboarding for this project',
    template: `Populate or refresh Memoir onboarding for the CURRENT OpenCode project only.\n\nUSER REQUEST:\n$ARGUMENTS\n\nWorkflow:\n- Stay inside the current project/worktree. Do not inspect parent directories.\n- First obtain a project file tree to understand structure.\n- Start studying from project documentation.\n- Continue only based on what the tree and documentation show.\n\nMemory rules:\n- Record only verified facts from files/docs/code or explicit user statements.\n- Do not write inferred user thoughts, intentions, preferences, or opinions.\n- Do not use preferences.* paths unless the user explicitly stated a preference.\n- If a fact is your interpretation, do not save it; report it as uncertain instead.\n\nThen call memoir_remember with replace=true for durable onboarding facts. Use namespace codebase:onboard in git repositories and project:onboard outside git. Do not install or invoke separate skills/scripts.`,
  };
}

const memoirStatus = tool({
  description: 'Show Memoir status for the current OpenCode project store.',
  args: {},
  execute: async () => statusJson(deriveStorePath()),
});

const memoirRemember = tool({
  description: 'Explicitly save a durable memory to Memoir at one or more semantic taxonomy paths.',
  args: {
    content: tool.schema.string().describe('Memory content to save. Do not include secrets.'),
    path: tool.schema.string().optional().describe('Semantic taxonomy path, e.g. preferences.coding.style.'),
    namespace: tool.schema.string().optional().describe('Memoir namespace. Defaults to default.'),
    replace: tool.schema.boolean().optional().describe('Replace existing value at the path.'),
  },
  execute: async (args: MemoirRememberArgs) => {
    const content = args.content?.trim();
    if (!content) return 'Memoir memory was not saved: content is empty.';
    if (SECRET_PATTERN.test(content)) {
      return 'Memoir memory was not saved: the content looks like a secret or credential. Save a redacted rule instead.';
    }
    const paths = coercePaths(args.path);
    if (paths.length === 0) {
      return 'Memoir memory was not saved: provide a semantic path, e.g. preferences.coding.style.';
    }

    const store = deriveStorePath();
    try {
      await ensureStore(store);
    } catch (error) {
      return String((error as Error).message || error);
    }

    const cliArgs = ['--json', '-s', store, 'remember', content];
    for (const p of paths) cliArgs.push('-p', p);
    cliArgs.push('-n', args.namespace ?? 'default');
    if (args.replace) cliArgs.push('--replace');
    return tryPrettyJson(await runMemoir(cliArgs, { cwd: store }));
  },
});

export const DEFAULT_RECALL_NAMESPACES = ['default', 'project:onboard', 'codebase:onboard'];

const memoirRecall = tool({
  description: 'List Memoir memory keys across relevant namespaces for relevance picking. Never calls legacy memoir recall.',
  args: {
    query: tool.schema.string().optional().describe('User query or topic to recall for.'),
    namespace: tool.schema.string().optional().describe('Single Memoir namespace to inspect. If omitted, checks default + onboard namespaces.'),
    namespaces: tool.schema.array(tool.schema.string()).optional().describe('Namespaces to inspect. Defaults to default, project:onboard, codebase:onboard.'),
    includeMetrics: tool.schema.boolean().optional().describe('Include metrics.* memories in the listing.'),
  },
  execute: async (args: MemoirRecallArgs) => {
    const store = deriveStorePath();
    try {
      await ensureStore(store);
    } catch (error) {
      return String((error as Error).message || error);
    }

    const namespaces = args.namespace
      ? [args.namespace]
      : (args.namespaces && args.namespaces.length > 0 ? args.namespaces : DEFAULT_RECALL_NAMESPACES);
    const sections: string[] = [];
    for (const namespace of namespaces) {
      const output = tryPrettyJson(await runMemoir(['--json', '-s', store, 'summarize', '--depth', '3', '-n', namespace], { cwd: store }));
      sections.push(`## namespace: ${namespace}\n${output}`);
    }
    const note = args.includeMetrics
      ? 'Metrics were included by request.'
      : 'Ignore metrics.* and taxonomy:v1:* entries unless explicitly needed. If default is empty or only metrics, inspect project:onboard/codebase:onboard before concluding there is no memory.';
    const query = args.query ? `Query: ${args.query}\n` : '';
    return `${query}${note}\nPick at most 5-7 relevant exact keys across namespaces, then call memoir_get with the matching namespace if values are needed.\n${sections.join('\n\n')}`;
  },
});

const memoirGet = tool({
  description: 'Fetch exact Memoir memory keys after selecting them from memoir_recall output.',
  args: {
    keys: tool.schema.array(tool.schema.string()).describe('Exact memory keys to fetch.'),
    namespace: tool.schema.string().optional().describe('Memoir namespace. Defaults to default.'),
  },
  execute: async (args: MemoirGetArgs) => {
    const keys = args.keys?.map((key) => key.trim()).filter(Boolean) ?? [];
    if (keys.length === 0) return 'No Memoir keys were provided.';

    const store = deriveStorePath();
    try {
      await ensureStore(store);
    } catch (error) {
      return String((error as Error).message || error);
    }

    return tryPrettyJson(await runMemoir(['--json', '-s', store, 'get', ...keys, '-n', args.namespace ?? 'default'], { cwd: store }));
  },
});

const MemoirOpenCode: Plugin = async (_input, rawOptions) => {
  const opts = (rawOptions ?? {}) as { store?: string };
  if (opts.store) pluginStoreOverride = opts.store;

  return ({
  name: 'memoir',
  tool: {
    memoir_status: memoirStatus,
    memoir_remember: memoirRemember,
    memoir_recall: memoirRecall,
    memoir_get: memoirGet,
  },
  config: async (opencodeConfig: OpenCodeConfig) => {
    registerCommands(opencodeConfig);
  },
  'command.execute.before': async (input: { command?: string }, output: CommandOutput) => {
    try {
      if (input.command === 'memoir:status') {
        pushText(output, await statusJson(deriveStorePath()));
      }
      if (input.command === 'memoir:ui') {
        pushText(output, await launchUi(deriveStorePath()));
      }
    } catch (error) {
      pushText(output, `Memoir command failed: ${String((error as Error).message || error)}`);
    }
  },

  /**
   * Inject MEMOIR_STORE into every shell command's environment so any memoir
   * invocation automatically targets the right store without manual -s flags.
   */
  'shell.env': async (input, output) => {
    try {
      output.env.MEMOIR_STORE = deriveStorePath(input.cwd);
    } catch {
      // Silent fail — shell.env is best-effort
    }
  },

  /**
   * Observe every tool execution for metrics and code-change tracking.
   * Mirrors the observation phase of Claude Code's Stop hook.
   * Never modifies the tool output.
   */
  'tool.execute.after': async (input, output) => {
    try {
      // Accumulate per-tool metrics (cf. collect-metrics.sh)
      const m = toolMetrics.get(input.tool) ?? { calls: 0, errors: 0 };
      m.calls++;
      // Detect errors: some tools signal failure via output metadata
      if (output.metadata?.error || output.output?.startsWith('Error:')) {
        m.errors++;
      }
      toolMetrics.set(input.tool, m);

      // Track file edits (cf. collect-edits.sh)
      if (EDIT_TOOLS.has(input.tool)) {
        const filePath =
          typeof input.args?.filePath === 'string' ? input.args.filePath
          : typeof input.args?.path === 'string' ? input.args.path
          : '';
        if (filePath) {
          pendingEdits.push({ tool: input.tool, filePath, snippet: '', timestamp: Date.now() });
        }
      }
    } catch {
      // Silent fail
    }
  },

  /**
   * Fires on every incoming user message.
   *
   * 1. Flush pending edits from the previous assistant turn
   *    (cf. Stop hook code change audit, run after each turn).
   * 2. Run the recall gate (cf. UserPromptSubmit).
   */
  'chat.message': async (input, output) => {
    try {
      // Flush code changes from the previous turn first
      await flushCapture();

      // Then run the recall gate
      const text = output.parts
        .filter((p): p is typeof p & { type: 'text'; text: string } => p.type === 'text')
        .map(p => p.text)
        .join(' ');
      if (shouldTriggerRecall(text)) {
        pendingRecall.add(input.sessionID);
      }
    } catch {
      // Silent fail — chat.message is best-effort
    }
  },

  /**
   * Fires before every LLM call. If a recall is pending for this session,
   * injects a brief instruction telling the model to use memoir tools.
   *
   * The flag is consumed once (one-shot) so the instruction only appears
   * for the next LLM call, not persistently.
   */
  'experimental.chat.system.transform': async (input, output) => {
    try {
      if (input.sessionID && pendingRecall.has(input.sessionID)) {
        pendingRecall.delete(input.sessionID);
        output.system.push(
          '\n[memoir] The user may have relevant context in Memoir. Run memoir_recall to list available memories across default and onboard namespaces, then memoir_get with the matching namespace to fetch exact values.'
        );
      }
    } catch {
      // Silent fail — system.transform is best-effort
    }
  },

  /**
   * Fires when the plugin is shut down. Flushes any remaining code changes
   * and metrics (cf. SessionEnd heartbeat cleanup + final metrics flush).
   */
  dispose: async () => {
    await flushCapture();
  },
});
};

export default MemoirOpenCode;
