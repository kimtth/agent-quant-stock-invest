import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '..');

export const REPORT_PREFIX = '@@REPORT@@ ';

/**
 * Long-lived bridge to the Microsoft Agent Framework workflow.
 *
 * A single Python process is kept alive in `--serve` mode: market snapshots are
 * written to its stdin as NDJSON and advisory reports are read back from stdout,
 * so the Foundry client and workflow graph are built only once.
 */
export class AgentBridge {
  /**
   * @param {{command: string, args: string[], timeoutMs: number}} options
   * @param {(level: string, message: string) => void} [logger]
   */
  constructor(options, logger = () => {}) {
    this.options = options;
    this.log = logger;
    this.child = null;
    this.stdoutBuffer = '';
    /** @type {Map<string, {resolve: (value: any) => void, timer: NodeJS.Timeout, onReport?: (report: any) => void}>} */
    this.pending = new Map();
    this.status = 'idle';
    this.lastError = '';
  }

  start() {
    if (this.child) return;
    try {
      this.child = spawn(this.options.command, this.options.args, {
        cwd: ROOT_DIR,
        windowsHide: true,
        stdio: ['pipe', 'pipe', 'pipe']
      });
    } catch (error) {
      this.failAll(`spawn failed: ${error.message}`);
      return;
    }

    this.status = 'starting';
    this.child.stdout.setEncoding('utf-8');
    this.child.stdout.on('data', (chunk) => this.onStdout(chunk));
    this.child.stderr.setEncoding('utf-8');
    this.child.stderr.on('data', (chunk) => {
      for (const line of String(chunk).split(/\r?\n/)) {
        if (line.trim()) this.log('agent', line.trim());
      }
    });
    this.child.on('error', (error) => this.failAll(`process error: ${error.message}`));
    this.child.on('exit', (code) => {
      this.child = null;
      this.failAll(`workflow process exited (code ${code})`);
    });
  }

  onStdout(chunk) {
    this.stdoutBuffer += chunk;
    let newlineIndex = this.stdoutBuffer.indexOf('\n');
    while (newlineIndex !== -1) {
      const line = this.stdoutBuffer.slice(0, newlineIndex).trim();
      this.stdoutBuffer = this.stdoutBuffer.slice(newlineIndex + 1);
      if (line) this.onLine(line);
      newlineIndex = this.stdoutBuffer.indexOf('\n');
    }
  }

  onLine(line) {
    if (!line.startsWith(REPORT_PREFIX)) {
      this.log('agent', line);
      return;
    }
    let report;
    try {
      report = JSON.parse(line.slice(REPORT_PREFIX.length));
    } catch (error) {
      this.log('error', `unparsable agent report: ${error.message}`);
      return;
    }
    const kind = report.kind ?? 'advisory';
    if (kind === 'frame') {
      this.pending.get('backtest')?.onReport?.(report);
      return;
    }
    if (kind === 'summary') {
      this.resolvePending('backtest', report);
      return;
    }
    if (kind === 'advisory') {
      this.status = report.mode === 'agent' ? 'agent' : 'offline';
      this.lastError = report.error ?? '';
    }
    this.resolvePending(kind, report);
  }

  resolvePending(kind, report) {
    const entry = this.pending.get(kind);
    if (!entry) return;
    clearTimeout(entry.timer);
    this.pending.delete(kind);
    entry.resolve(report);
  }

  failAll(message) {
    this.status = 'error';
    this.lastError = message;
    this.log('error', message);
    for (const entry of this.pending.values()) {
      clearTimeout(entry.timer);
      entry.resolve(null);
    }
    this.pending.clear();
  }

  /**
   * Send one request through the workflow server and await its reply.
   * Resolves to `null` when the workflow is unavailable, busy, or times out.
   *
   * @param {'advisory'|'ask'|'model'|'backtest'} kind
   * @param {object} payload
   * @param {{responseKind?: string, onReport?: (report: any) => void}} [options]
   */
  async request(kind, payload, { responseKind = kind, onReport } = {}) {
    if (!this.child) this.start();
    if (!this.child) return null;
    if (this.pending.has(responseKind)) return null;

    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        this.pending.delete(responseKind);
        this.lastError = `${kind} request timed out`;
        this.log('error', this.lastError);
        resolve(null);
      }, this.options.timeoutMs);

      this.pending.set(responseKind, { resolve, timer, onReport });
      try {
        this.child.stdin.write(`${JSON.stringify({ kind, payload })}\n`);
      } catch (error) {
        clearTimeout(timer);
        this.pending.delete(responseKind);
        this.failAll(`stdin write failed: ${error.message}`);
        resolve(null);
      }
    });
  }

  /** Send a market snapshot through the workflow and await one advisory report. */
  async analyze(snapshot) {
    this.status = 'running';
    return this.request('advisory', snapshot);
  }

  /** Ask one grounded question about the current watchlist. */
  async ask(question, snapshot, focusSymbol) {
    return this.request('ask', {
      question,
      snapshot,
      focus_symbol: focusSymbol ?? ''
    });
  }

  /** Run one streamed single-symbol backtest and resolve with its final summary. */
  async backtest(payload, onFrame = () => {}) {
    return this.request('backtest', payload, { responseKind: 'backtest', onReport: onFrame });
  }

  /**
   * Inspect or switch the chat backend. `apiKeyVar` is an environment variable
   * name — a literal key is never sent, so secrets stay out of the UI and logs.
   */
  async model({ action = 'status', provider = '', model = '', endpoint = '', apiKeyVar = '' } = {}) {
    return this.request('model', {
      action,
      provider,
      model,
      endpoint,
      api_key_var: apiKeyVar
    });
  }

  stop() {
    if (!this.child) return;
    const child = this.child;
    this.child = null;
    try {
      child.stdin.end();
    } catch {
      // Process already gone.
    }
    child.kill();
  }
}
