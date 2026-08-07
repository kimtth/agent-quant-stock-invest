#!/usr/bin/env node
import blessed from 'blessed';
import contrib from 'blessed-contrib';
import chalk from 'chalk';
import { readFileSync, writeFileSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

import { AgentBridge } from './agentBridge.js';
import { DataService } from './dataService.js';
import {
  axisLabels,
  formatChange,
  formatClock,
  formatCompact,
  formatNumber,
  formatPrice,
  formatPriceCompact
} from './format.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const CONFIG_PATH = path.resolve(__dirname, '../config.json');

const PERIODS = [
  { label: '1D', days: 1 },
  { label: '7D', days: 7 },
  { label: '30D', days: 30 },
  { label: '90D', days: 90 },
  { label: '1Y', days: 365 },
  { label: '2Y', days: 730 }
];

const BACKTEST_DAYS = 730;

/** Parse a period token such as `30d`, `6mo`, `2y`, or `max` into days. */
function parseDays(token) {
  const text = String(token ?? '').toLowerCase();
  if (text === 'max' || text === 'all') return Number.MAX_SAFE_INTEGER;
  const match = /^(\d+)(d|w|mo|y)$/.exec(text);
  if (!match) return 0;
  return Number(match[1]) * { d: 1, w: 7, mo: 30, y: 365 }[match[2]];
}

const ACTION_COLORS = { BUY: 'green', SELL: 'red', HOLD: 'yellow' };
const RISK_COLORS = { LOW: 'green', MEDIUM: 'yellow', HIGH: 'red' };
const FLASH_MS = 2500;
const MAX_LOG_LINES = 200;

/** Key bindings, rendered into both the status bar and the help overlay. */
const KEYS = [
  { keys: ['up', 'k'], hint: '↑↓', label: 'nav', help: 'move the watchlist selection' },
  { keys: ['1', '2', '3', '4'], hint: '1-6', label: 'period', help: 'switch the chart period' },
  { keys: ['r'], hint: 'r', label: 'refresh', help: 'refresh market data now' },
  { keys: ['a'], hint: 'a', label: 'analyze', help: 'run the advisory workflow now' },
  { keys: ['l'], hint: 'l', label: 'log', help: 'toggle the log overlay' },
  { keys: ['/', ':'], hint: '/', label: 'command', help: 'open the command prompt' },
  { keys: ['?'], hint: '?', label: 'help', help: 'show this help' },
  { keys: ['escape', 'q'], hint: 'q', label: 'quit', help: 'close an overlay, or quit' }
];

/** Command registry: the prompt, the help overlay, and dispatch all read this. */
const COMMANDS = [
  {
    name: 'ask',
    args: '<question>',
    help: [
      'Ask about the symbols currently on screen. The question is answered',
      'from the live snapshot and its indicators (price, period change,',
      'SMAs, RSI, momentum, volatility, drawdown) only — this is not a',
      'general investing chatbot, and the workflow says so when the data',
      'cannot answer.'
    ]
  },
  {
    name: 'backtest',
    args: '[symbol] [period] [natural-language objective]',
    help: [
      'Backtest the selected symbol, or a symbol currently in the watchlist.',
      'An Agent Framework agent writes the signal strategy from the objective.',
      'The optional period sets how much daily history is loaded, e.g. 5y or',
      '6mo; it defaults to 2y. Streams progress, then shows the result.'
    ]
  },
  {
    name: 'period',
    args: '[period]',
    help: [
      'Set the on-screen chart period, which is also the window /ask and',
      'the advisory workflow see. With no argument it lists the presets.'
    ]
  },
  {
    name: 'model',
    args: '[provider] [args...]',
    help: ['Show the active chat backend, or switch to another one.']
  },
  {
    name: 'ticker',
    args: '[add|remove] <SYMBOL> [coingecko-id]',
    help: [
      'Edit the watchlist and save it to config.json. Equities use Yahoo',
      'tickers (BRK-B, 7203.T); a symbol is fetched as crypto when a',
      'CoinGecko coin id is given, e.g. /ticker add BTC bitcoin.',
      'With no argument it lists the current watchlist.'
    ]
  },
  { name: 'analyze', args: '', help: ['Run the advisory workflow now.'] },
  { name: 'refresh', args: '', help: ['Refresh market data now.'] },
  { name: 'help', args: '', help: ['Show this help.'] },
  { name: 'quit', args: '', help: ['Exit chart-cli.'] }
];

/** Clip plain text to a column width before any ANSI colouring is applied. */
function cell(text, width) {
  const value = String(text);
  return value.length > width ? value.slice(0, width) : value;
}

class ChartCliDashboard {
  constructor() {
    this.config = JSON.parse(readFileSync(CONFIG_PATH, 'utf-8'));
    this.periodIndex = Math.min(
      Math.max(this.config.chart?.defaultPeriodIndex ?? 1, 0),
      PERIODS.length - 1
    );

    this.logLines = [];
    this.assets = [];
    this.previousPrices = new Map();
    this.flashUntil = new Map();
    this.selectedIndex = 0;
    this.advisory = null;
    this.dataStatus = 'starting';
    this.nextRefreshAt = Date.now();
    this.refreshing = false;
    this.analyzing = false;
    this.asking = false;
    this.backtesting = false;
    this.commandMode = false;
    this.commandHistory = [];
    this.modelStatus = null;

    this.dataService = new DataService((level, message) => this.pushLog(level, message));
    this.agent = this.config.agent?.enabled
      ? new AgentBridge(
          {
            command: this.config.agent.command,
            args: this.config.agent.args,
            timeoutMs: this.config.agent.timeoutMs ?? 180000
          },
          (level, message) => this.pushLog(level, message)
        )
      : null;

    this.initScreen();
    this.initWidgets();
    this.bindKeys();
  }

  pushLog(level, message) {
    const stamp = formatClock();
    const color = level === 'error' ? chalk.red : level === 'warn' ? chalk.yellow : chalk.gray;
    this.logLines.push(`${chalk.gray(stamp)} ${color(`[${level}]`)} ${message}`);
    if (this.logLines.length > MAX_LOG_LINES) this.logLines.shift();
    if (this.logBox && !this.logBox.hidden) {
      this.logBox.setContent(this.logLines.slice(-40).join('\n'));
      this.logBox.setScrollPerc(100);
    }
  }

  initScreen() {
    this.screen = blessed.screen({
      smartCSR: true,
      title: 'CHART-CLI | Agent Framework Market Dashboard',
      fullUnicode: true
    });
    this.screen.key(['C-c'], () => this.shutdown());
    this.screen.key(['escape', 'q'], () => {
      if (this.commandMode) return;
      if (!this.outputBox.hidden) {
        this.hideOutput();
        return;
      }
      if (!this.logBox.hidden) {
        this.logBox.hidden = true;
        this.screen.render();
        return;
      }
      this.shutdown();
    });
  }

  initWidgets() {
    this.container = blessed.box({
      top: 0,
      left: 0,
      width: '100%',
      height: '100%-1'
    });
    this.screen.append(this.container);

    const grid = new contrib.grid({ rows: 12, cols: 12, screen: this.container });

    this.watchlist = grid.set(0, 0, 8, 4, contrib.table, {
      keys: false,
      interactive: false,
      label: ' WATCHLIST ',
      border: { type: 'line', fg: 'cyan' },
      fg: 'white',
      columnSpacing: 2,
      columnWidth: [8, 11, 9]
    });

    this.agentBox = grid.set(8, 0, 4, 4, blessed.box, {
      label: ' AGENT CALL ',
      border: { type: 'line', fg: 'magenta' },
      style: { border: { fg: 'magenta' } },
      tags: true
    });

    this.chart = grid.set(0, 4, 7, 5, contrib.line, {
      label: ' PRICE TREND ',
      border: { type: 'line', fg: 'cyan' },
      style: { line: 'green', text: 'white', baseline: 'white', border: { fg: 'cyan' } },
      showLegend: false,
      xPadding: 3,
      yPadding: 1,
      wholeNumbersOnly: false,
      minY: null
    });

    this.detailsBox = grid.set(7, 4, 5, 5, blessed.box, {
      label: ' DETAILS ',
      border: { type: 'line', fg: 'cyan' },
      style: { border: { fg: 'cyan' } },
      tags: true
    });

    this.signalsTable = grid.set(0, 9, 6, 3, contrib.table, {
      keys: false,
      interactive: false,
      label: ' SIGNALS ',
      border: { type: 'line', fg: 'magenta' },
      fg: 'white',
      columnSpacing: 2,
      columnWidth: [8, 6, 6]
    });

    this.notesBox = grid.set(6, 9, 6, 3, blessed.box, {
      label: ' NOTES ',
      border: { type: 'line', fg: 'magenta' },
      style: { border: { fg: 'magenta' } },
      tags: true,
      scrollable: true,
      alwaysScroll: true
    });

    this.logBox = blessed.box({
      parent: this.screen,
      top: 'center',
      left: 'center',
      width: '80%',
      height: '70%',
      label: ' LOG (l to close) ',
      border: { type: 'line', fg: 'yellow' },
      style: { border: { fg: 'yellow' } },
      scrollable: true,
      alwaysScroll: true,
      hidden: true,
      tags: false
    });

    this.outputBox = blessed.box({
      parent: this.screen,
      top: 'center',
      left: 'center',
      width: '76%',
      height: '72%',
      label: ' OUTPUT ',
      border: { type: 'line', fg: 'green' },
      style: { border: { fg: 'green' } },
      padding: { left: 1, right: 1 },
      scrollable: true,
      alwaysScroll: true,
      keys: true,
      mouse: true,
      hidden: true,
      tags: true
    });
    // The overlay takes focus while it is up, so it closes itself.
    this.outputBox.key(['escape', 'q', 'enter', 'space'], () => this.hideOutput());

    this.commandBar = blessed.textbox({
      parent: this.screen,
      bottom: 1,
      left: 0,
      width: '100%',
      height: 3,
      label: ' COMMAND (Enter run, Esc cancel) ',
      border: { type: 'line', fg: 'cyan' },
      style: { border: { fg: 'cyan' }, fg: 'white' },
      hidden: true
    });

    this.statusBar = blessed.box({
      parent: this.screen,
      bottom: 0,
      left: 0,
      width: '100%',
      height: 1,
      style: { fg: 'cyan', bg: 'black' },
      tags: true,
      content: ' starting...'
    });

    this.spinner = blessed.loading({
      parent: this.screen,
      top: 'center',
      left: 'center',
      height: 5,
      width: 44,
      hidden: true,
      border: { type: 'line', fg: 'cyan' },
      style: { border: { fg: 'cyan' } }
    });
  }

  bindKeys() {
    const handlers = {
      nav: null,
      period: null,
      refresh: () => this.refresh(true),
      analyze: () => this.runWorkflow(),
      log: () => this.toggleLog(),
      command: () => this.openCommand(),
      help: () => this.showOutput(' HELP ', this.buildHelp()),
      quit: null
    };

    this.screen.key(['up', 'k'], () => this.move(-1));
    this.screen.key(['down', 'j'], () => this.move(1));
    for (const [index] of PERIODS.entries()) {
      this.screen.key([String(index + 1)], () => this.switchPeriod(index));
    }
    for (const binding of KEYS) {
      const handler = handlers[binding.label];
      if (handler) this.screen.key(binding.keys, handler);
    }
  }

  toggleLog() {
    this.logBox.hidden = !this.logBox.hidden;
    if (!this.logBox.hidden) {
      this.logBox.setContent(this.logLines.slice(-40).join('\n'));
      this.logBox.setScrollPerc(100);
      this.logBox.setFront();
    }
    this.screen.render();
  }

  // --- command prompt -----------------------------------------------------

  /** Open the bottom prompt and read one command line from the user. */
  openCommand(prefill = '/') {
    if (this.commandMode) return;
    this.commandMode = true;
    this.commandBar.hidden = false;
    this.commandBar.setFront();
    this.commandBar.setValue(prefill);
    this.screen.render();

    this.commandBar.readInput((error, value) => {
      this.commandMode = false;
      this.commandBar.hidden = true;
      this.commandBar.clearValue();
      // blessed keeps the key grab on the textbox; hand control back to the screen.
      this.screen.grabKeys = false;
      this.container.focus();
      this.screen.render();
      if (error || value === null || value === undefined) return;
      const line = String(value).trim();
      if (!line || line === '/') return;
      this.commandHistory.push(line);
      void this.runCommand(line);
    });
  }

  /** Parse and execute one command line typed into the prompt. */
  async runCommand(line) {
    const body = line.startsWith('/') ? line.slice(1) : line;
    const separator = body.search(/\s/);
    const name = (separator === -1 ? body : body.slice(0, separator)).toLowerCase();
    const rest = separator === -1 ? '' : body.slice(separator + 1).trim();

    switch (name) {
      case 'help':
      case 'h':
      case '?':
        this.showOutput(' HELP ', this.buildHelp());
        return;
      case 'ask':
        await this.runAsk(rest);
        return;
      case 'backtest':
      case 'bt':
        await this.runBacktest(rest);
        return;
      case 'period':
        await this.runPeriod(rest);
        return;
      case 'model':
        await this.runModel(rest);
        return;
      case 'ticker':
      case 'tickers':
        await this.runTicker(rest);
        return;
      case 'analyze':
        await this.runWorkflow();
        return;
      case 'refresh':
        await this.refresh(true);
        return;
      case 'quit':
      case 'exit':
        this.shutdown();
        return;
      default:
        this.showOutput(
          ' COMMAND ',
          `{red-fg}Unknown command: /${name || '(empty)'}{/red-fg}\n\n${this.buildHelp()}`
        );
    }
  }

  /** Render the help overlay from the key and command tables plus live state. */
  buildHelp() {
    const width = this.outputWidth();
    const lines = [
      '{bold}{cyan-fg}chart-cli{/cyan-fg}{/bold} — terminal market dashboard driven by a',
      'Microsoft Agent Framework workflow. Market data is public and may be',
      'delayed; every panel is research output, not investment advice.',
      '',
      '{bold}{cyan-fg}KEYS{/cyan-fg}{/bold}'
    ];
    for (const binding of KEYS) {
      lines.push(`  {yellow-fg}${binding.hint.padEnd(6)}{/yellow-fg}${binding.help}`);
    }
    lines.push('', '{bold}{cyan-fg}COMMANDS{/cyan-fg}{/bold}');
    for (const command of COMMANDS) {
      lines.push(`  {yellow-fg}/${command.name} ${command.args}{/yellow-fg}`.trimEnd());
      for (const text of command.help) lines.push(`      ${text}`);
      if (command.name === 'ask') lines.push(...this.askExamples().map((t) => `      ${t}`));
      if (command.name === 'model') lines.push(...this.modelUsage().map((t) => `      ${t}`));
      lines.push('');
    }
    lines.push(`{gray-fg}${this.wrapPlain(this.advisory?.disclaimer ?? '', width)}{/gray-fg}`);
    return lines.join('\n');
  }

  /** Example questions built from the symbols actually on screen. */
  askExamples() {
    const symbols = this.assets.map((asset) => asset.symbol);
    if (symbols.length === 0) return [];
    const selected = this.selectedAsset?.symbol ?? symbols[0];
    const other = symbols.find((symbol) => symbol !== selected) ?? selected;
    return [
      'which symbol has the weakest momentum?',
      `is ${selected} overbought right now?`,
      `how does ${selected} volatility compare with ${other}?`,
      'which symbols are trading below their slow SMA?',
      'which symbol has the deepest drawdown from its recent high?',
      'rank the watchlist by risk-adjusted strength'
    ].map((question, index) => `${index === 0 ? 'e.g. ' : '     '}{gray-fg}/ask ${question}{/gray-fg}`);
  }

  /** `/model` argument hints, published by the workflow's provider catalog. */
  modelUsage() {
    const status = this.modelStatus;
    if (!status) return ['Run /model to load the provider list.'];
    const lines = (status.available ?? []).map(
      (provider) =>
        `{gray-fg}/model ${provider} ${status.usage?.[provider] ?? ''}{/gray-fg}`.trimEnd()
    );
    if (status.default_api_key_var) {
      lines.push(
        '',
        'A key-authenticated endpoint reads its key from an environment',
        `variable (default {gray-fg}${status.default_api_key_var}{/gray-fg}); never type the key here.`
      );
    }
    return lines;
  }

  /**
   * Answer a user question about the symbols currently on screen. The workflow
   * is grounded in this snapshot only; it is not a general investing chatbot.
   */
  async runAsk(question) {
    if (!question) {
      const usage = COMMANDS.find((command) => command.name === 'ask');
      this.showOutput(
        ' ASK ',
        [
          '{yellow-fg}/ask needs a question.{/yellow-fg}',
          '',
          ...usage.help,
          '',
          ...this.askExamples()
        ].join('\n')
      );
      return;
    }
    if (!this.agent) {
      this.showOutput(' ASK ', '{red-fg}The workflow is disabled in config.json.{/red-fg}');
      return;
    }
    if (this.asking) {
      this.showOutput(' ASK ', '{yellow-fg}A question is already in flight.{/yellow-fg}');
      return;
    }

    this.asking = true;
    this.showOutput(
      ' ASK ',
      `{bold}${this.wrapPlain(question, this.outputWidth())}{/bold}\n\n{magenta-fg}Asking the workflow...{/magenta-fg}`
    );
    try {
      const reply = await this.agent.ask(
        question,
        this.buildSnapshot(),
        this.selectedAsset?.symbol ?? ''
      );
      this.showOutput(' ASK ', this.formatAsk(question, reply));
    } catch (error) {
      this.showOutput(' ASK ', `{red-fg}ask failed: ${error.message}{/red-fg}`);
    } finally {
      this.asking = false;
      this.renderStatus();
      this.screen.render();
    }
  }

  formatAsk(question, reply) {
    const width = this.outputWidth();
    if (!reply) {
      return [
        `{bold}${this.wrapPlain(question, width)}{/bold}`,
        '',
        '{red-fg}No answer: the workflow is unavailable or timed out.{/red-fg}'
      ].join('\n');
    }
    const modeColor = reply.mode === 'agent' ? 'green' : 'yellow';
    const lines = [
      `{bold}${this.wrapPlain(question, width)}{/bold}`,
      `{${modeColor}-fg}${reply.mode}{/${modeColor}-fg} {gray-fg}${reply.generated_at ?? ''}{/gray-fg}`,
      `{gray-fg}${'─'.repeat(width)}{/gray-fg}`,
      this.wrapPlain(reply.answer ?? '', width)
    ];
    if (reply.highlights?.length) {
      lines.push('');
      for (const item of reply.highlights) {
        lines.push(`{cyan-fg}•{/cyan-fg} ${this.wrapPlain(item, width - 2)}`);
      }
    }
    if (reply.error) {
      lines.push('', `{red-fg}${this.formatError(reply.error, width)}{/red-fg}`);
    }
    lines.push('', `{gray-fg}${this.wrapPlain(reply.disclaimer ?? '', width)}{/gray-fg}`);
    return lines.join('\n');
  }

  /**
   * `/period [1D|7D|30D|90D|1Y|2Y]` — set the window every panel, `/ask`, and
   * the advisory workflow read. Presets keep the chart and the keys in step.
   */
  async runPeriod(rest) {
    const wanted = rest.trim().toUpperCase();
    const index = PERIODS.findIndex((period) => period.label === wanted);
    if (index === -1) {
      const list = PERIODS.map(
        (period, position) =>
          `  {yellow-fg}${period.label.padEnd(5)}{/yellow-fg}[${position + 1}] ${period.days} day(s)${period.label === this.period.label ? ' {green-fg}(active){/green-fg}' : ''}`
      );
      this.showOutput(
        ' PERIOD ',
        [
          wanted ? `{red-fg}Unknown period '${rest.trim()}'.{/red-fg}` : ' {cyan-fg}PERIODS{/cyan-fg}',
          ...list,
          '',
          ' {gray-fg}/backtest takes its own period, e.g. /backtest MSFT 5y{/gray-fg}'
        ].join('\n')
      );
      return;
    }
    this.hideOutput();
    await this.switchPeriod(index);
  }

  /** `/backtest [SYMBOL] [PERIOD] [objective]` uses the loaded price series only. */
  async runBacktest(requestText) {
    if (!this.agent) {
      this.showOutput(' BACKTEST ', '{red-fg}The workflow is disabled in config.json.{/red-fg}');
      return;
    }
    if (this.backtesting) {
      this.showOutput(' BACKTEST ', '{yellow-fg}A backtest is already in flight.{/yellow-fg}');
      return;
    }

    const words = requestText.trim().split(/\s+/).filter(Boolean);
    const namedAsset = this.assets.find((item) => item.symbol === words[0]?.toUpperCase());
    const rest = namedAsset ? words.slice(1) : words;
    const days = parseDays(rest[0]) || BACKTEST_DAYS;
    const criteria = (parseDays(rest[0]) ? rest.slice(1) : rest).join(' ').slice(0, 500);
    const asset = namedAsset ?? this.selectedAsset;
    if (!asset) {
      this.showOutput(
        ' BACKTEST ',
        '{yellow-fg}Select a symbol after market data has loaded, then try /backtest [SYMBOL] [objective].{/yellow-fg}'
      );
      return;
    }

    this.backtesting = true;
    this.renderStatus();
    this.showOutput(
      ' BACKTEST ',
      [
        `{bold}${asset.symbol}{/bold} {gray-fg}${days === Number.MAX_SAFE_INTEGER ? 'full available' : `${days} days of`} daily history{/gray-fg}`,
        criteria ? `{gray-fg}Objective: ${criteria}{/gray-fg}` : '',
        '',
        '{magenta-fg}Loading data, generating a signal strategy, then backtesting...{/magenta-fg}'
      ]
        .filter(Boolean)
        .join('\n')
    );
    try {
      const backtestAsset = await this.dataService.fetchBacktestHistory(
        asset.symbol,
        this.config.cryptoIds ?? {},
        days
      );
      const history = (backtestAsset.history ?? []).filter(
        (value) => Number.isFinite(value) && value > 0
      );
      if (backtestAsset.error || history.length < 30) {
        this.showOutput(
          ' BACKTEST ',
          `{red-fg}Could not load enough daily history for ${asset.symbol}.{/red-fg}`
        );
        return;
      }
      const summary = await this.agent.backtest(
        {
          symbol: asset.symbol,
          kind_label: backtestAsset.category,
          criteria,
          history,
          timestamps: backtestAsset.timestamps ?? []
        },
        (frame) => this.renderBacktestProgress(frame)
      );
      this.showOutput(' BACKTEST ', this.formatBacktest(summary));
    } catch (error) {
      this.showOutput(' BACKTEST ', `{red-fg}backtest failed: ${error.message}{/red-fg}`);
    } finally {
      this.backtesting = false;
      this.renderStatus();
      this.screen.render();
    }
  }

  renderBacktestProgress(frame) {
    if (this.outputBox.hidden) return;
    const metrics = frame.metrics ?? {};
    const complete = frame.total ? Math.round((frame.index / frame.total) * 100) : 0;
    this.outputBox.setContent(
      [
        `{bold}${frame.symbol ?? ''}{/bold} {magenta-fg}backtesting...{/magenta-fg}`,
        '',
        ` Progress  ${frame.index ?? 0}/${frame.total ?? 0} (${complete}%)  ${frame.time ?? ''}`,
        ` Equity    ${formatPrice(metrics.final_value)}  Return ${formatChange(metrics.total_return_pct)}`,
        ` Drawdown  ${formatChange(metrics.max_drawdown_pct)}  Trades ${metrics.trade_count ?? 0}`
      ].join('\n')
    );
    this.screen.render();
  }

  formatBacktest(summary) {
    if (!summary) {
      return '{red-fg}No result: the workflow is unavailable or timed out.{/red-fg}';
    }
    const metrics = summary.metrics ?? {};
    const plan = summary.plan ?? {};
    const width = this.outputWidth();
    const modeColor = summary.mode === 'agent' ? 'green' : 'yellow';
    const color = (metrics.total_return_pct ?? 0) >= 0 ? 'green' : 'red';
    const lines = [
      `{bold}${summary.symbol ?? 'Backtest'}{/bold} {${modeColor}-fg}${summary.mode ?? 'offline'}{/${modeColor}-fg} {gray-fg}${summary.generated_at ?? ''}{/gray-fg}`,
      `{gray-fg}${'─'.repeat(width)}{/gray-fg}`,
      ...(summary.criteria
        ? [' {cyan-fg}OBJECTIVE{/cyan-fg}', ` ${this.wrapPlain(summary.criteria, width - 1)}`, '']
        : []),
      ' {cyan-fg}STRATEGY{/cyan-fg}',
      ` ${plan.name ?? 'Generated strategy'}`,
      ` ${this.wrapPlain(plan.rationale ?? '', width - 1)}`,
      '',
      ' {cyan-fg}RESULT{/cyan-fg}',
      ` Initial ${formatPrice(metrics.initial_capital)}  Final ${formatPrice(metrics.final_value)}`,
      ` Return {${color}-fg}${formatChange(metrics.total_return_pct)}{/${color}-fg}  CAGR ${formatChange(metrics.cagr_pct)}  Sharpe ${formatNumber(metrics.sharpe)}`,
      ` Drawdown ${formatChange(metrics.max_drawdown_pct)}  Win rate ${formatNumber(metrics.win_rate_pct, 1)}%  Exposure ${formatNumber(metrics.exposure_pct, 1)}%`,
      ` Closed trades ${metrics.trade_count ?? 0}`
    ];
    if (summary.verdict) {
      lines.push('', ' {cyan-fg}VERDICT{/cyan-fg}', ` ${this.wrapPlain(summary.verdict, width - 1)}`);
    }
    if (summary.trades?.length) {
      lines.push('', ' {cyan-fg}RECENT FILLS{/cyan-fg}');
      for (const trade of summary.trades) {
        lines.push(
          ` ${trade.time ?? ''}  ${trade.side ?? ''}  ${formatPrice(trade.price)}  ${formatChange(trade.profit_pct)}`
        );
      }
    }
    if (summary.error) lines.push('', `{red-fg}${this.formatError(summary.error, width)}{/red-fg}`);
    lines.push('', `{gray-fg}${this.wrapPlain(summary.disclaimer ?? '', width)}{/gray-fg}`);
    return lines.join('\n');
  }

  /**
   * `/model` — show the active chat backend, or switch to another one.
   * An API key is never typed here: only the name of an environment variable.
   */
  async runModel(rest) {
    if (!this.agent) {
      this.showOutput(' MODEL ', '{red-fg}The workflow is disabled in config.json.{/red-fg}');
      return;
    }
    const [provider = '', model = '', endpoint = '', apiKeyVar = ''] = rest.split(/\s+/);
    const request = provider
      ? { action: 'set', provider, model, endpoint, apiKeyVar }
      : { action: 'status' };

    this.showOutput(' MODEL ', '{magenta-fg}Talking to the workflow...{/magenta-fg}');
    const status = await this.agent.model(request);
    this.modelStatus = status ?? this.modelStatus;
    this.showOutput(' MODEL ', this.formatModel(status));
    this.renderStatus();
    this.screen.render();
  }

  formatModel(status) {
    const width = this.outputWidth();
    if (!status) {
      return '{red-fg}No response: the workflow is unavailable or timed out.{/red-fg}';
    }
    const modeColor = status.mode === 'agent' ? 'green' : 'yellow';
    const lines = [
      ` {bold}provider{/bold}  ${status.provider}`,
      ` {bold}model{/bold}     ${status.model || '{gray-fg}(default){/gray-fg}'}`,
      ` {bold}endpoint{/bold}  ${status.endpoint || '{gray-fg}(default){/gray-fg}'}`,
      ` {bold}mode{/bold}      {${modeColor}-fg}${status.mode}{/${modeColor}-fg}`
    ];
    if (status.error) {
      lines.push('', ` {red-fg}${this.formatError(status.error, width - 1)}{/red-fg}`);
    }
    lines.push('', ' {cyan-fg}SWITCH{/cyan-fg}', ...this.modelUsage().map((text) => `  ${text}`));
    return lines.join('\n');
  }

  /**
   * `/ticker` — list, add, or remove watchlist symbols and persist config.json.
   * A symbol with a CoinGecko coin id is fetched as crypto, everything else
   * goes to Yahoo Finance.
   */
  async runTicker(rest) {
    const [action = '', symbolArg = '', coinArg = ''] = rest.split(/\s+/).filter(Boolean);
    if (!action) {
      this.showOutput(' TICKERS ', this.formatTickers());
      return;
    }

    const verb = action.toLowerCase();
    const isRemove = ['remove', 'rm', 'del', 'delete'].includes(verb);
    const isAdd = ['add', 'a'].includes(verb);
    if (!isAdd && !isRemove) {
      this.showOutput(
        ' TICKERS ',
        `{red-fg}Unknown action '${action}'. Use /ticker add|remove <SYMBOL>.{/red-fg}\n\n${this.formatTickers()}`
      );
      return;
    }

    const symbol = symbolArg.toUpperCase();
    // Yahoo tickers: BRK-B, 7203.T, VOD.L, ^GSPC, EURUSD=X.
    if (!/^[A-Z0-9^][A-Z0-9.^=-]{0,11}$/.test(symbol)) {
      this.showOutput(
        ' TICKERS ',
        `{red-fg}'${symbolArg || '(none)'}' is not a usable symbol.{/red-fg}\n\n${this.formatTickers()}`
      );
      return;
    }

    const tickers = this.config.tickers ?? [];
    const cryptoIds = this.config.cryptoIds ?? {};

    if (isRemove) {
      if (!tickers.includes(symbol)) {
        this.showOutput(' TICKERS ', `{yellow-fg}${symbol} is not on the watchlist.{/yellow-fg}`);
        return;
      }
      if (tickers.length === 1) {
        this.showOutput(' TICKERS ', '{red-fg}The watchlist cannot be empty.{/red-fg}');
        return;
      }
      this.config.tickers = tickers.filter((item) => item !== symbol);
      delete cryptoIds[symbol];
    } else {
      if (tickers.includes(symbol)) {
        this.showOutput(
          ' TICKERS ',
          `{yellow-fg}${symbol} is already on the watchlist.{/yellow-fg}\n\n${this.formatTickers()}`
        );
        return;
      }
      if (coinArg && !/^[a-z0-9][a-z0-9-]{0,39}$/.test(coinArg.toLowerCase())) {
        this.showOutput(' TICKERS ', `{red-fg}'${coinArg}' is not a CoinGecko coin id.{/red-fg}`);
        return;
      }
      this.config.tickers = [...tickers, symbol];
      if (coinArg) cryptoIds[symbol] = coinArg.toLowerCase();
      this.config.cryptoIds = cryptoIds;
    }

    try {
      writeFileSync(CONFIG_PATH, `${JSON.stringify(this.config, null, 2)}\n`, 'utf-8');
    } catch (error) {
      this.showOutput(' TICKERS ', `{red-fg}config.json not saved: ${error.message}{/red-fg}`);
      return;
    }
    this.pushLog('info', `${isRemove ? 'removed' : 'added'} ${symbol}`);

    this.showOutput(' TICKERS ', `{magenta-fg}Fetching ${symbol}...{/magenta-fg}`);
    await this.refresh();
    const asset = this.assets.find((item) => item.symbol === symbol);
    const note = isRemove
      ? `{green-fg}Removed ${symbol}.{/green-fg}`
      : asset?.error
        ? `{yellow-fg}Added ${symbol}, but no quote came back — check the symbol.{/yellow-fg}`
        : `{green-fg}Added ${symbol}.{/green-fg}`;
    this.showOutput(' TICKERS ', `${note}\n\n${this.formatTickers()}`);
  }

  formatTickers() {
    const cryptoIds = this.config.cryptoIds ?? {};
    const lines = [' {cyan-fg}WATCHLIST{/cyan-fg}'];
    for (const symbol of this.config.tickers ?? []) {
      const asset = this.assets.find((item) => item.symbol === symbol);
      const source = cryptoIds[symbol] ? `crypto (${cryptoIds[symbol]})` : 'yahoo';
      const state = asset?.error ? '{red-fg}no quote{/red-fg}' : `{gray-fg}${source}{/gray-fg}`;
      lines.push(`  ${symbol.padEnd(10)}${state}`);
    }
    lines.push(
      '',
      ' {cyan-fg}EDIT{/cyan-fg}',
      '  {gray-fg}/ticker add TSLA{/gray-fg}',
      '  {gray-fg}/ticker add BTC bitcoin{/gray-fg}',
      '  {gray-fg}/ticker remove QQQ{/gray-fg}',
      '',
      ' {gray-fg}Changes are saved to config.json.{/gray-fg}'
    );
    return lines.join('\n');
  }

  outputWidth() {
    return this.innerWidth(this.outputBox, 60) - 2;
  }

  /**
   * Wrap an error to at most three lines. Provider SDKs raise multi-kilobyte
   * HTTP documents; the full text stays in the log overlay ([l]).
   */
  formatError(text, width, maxLines = 3) {
    const wrapped = this.wrapPlain(text, width).split('\n');
    if (wrapped.length <= maxLines) return wrapped.join('\n');
    return [...wrapped.slice(0, maxLines - 1), `${wrapped[maxLines - 1]}… [l] for the log`].join(
      '\n'
    );
  }

  showOutput(label, content) {
    this.outputBox.setLabel(`${label}(q closes) `);
    this.outputBox.setContent(content);
    this.outputBox.hidden = false;
    this.outputBox.setFront();
    this.outputBox.setScrollPerc(0);
    this.outputBox.focus();
    this.screen.render();
  }

  hideOutput() {
    this.outputBox.hidden = true;
    this.container.focus();
    this.screen.render();
  }

  move(delta) {
    if (this.assets.length === 0) return;
    const next = this.selectedIndex + delta;
    if (next < 0 || next >= this.assets.length) return;
    this.selectedIndex = next;
    this.render();
  }

  async switchPeriod(index) {
    if (index === this.periodIndex || this.refreshing) return;
    this.periodIndex = index;
    await this.refresh(true);
  }

  get period() {
    return PERIODS[this.periodIndex];
  }

  get selectedAsset() {
    return this.assets[this.selectedIndex] ?? null;
  }

  // --- data ---------------------------------------------------------------

  async refresh(manual = false) {
    if (this.refreshing) return;
    this.refreshing = true;
    if (manual) {
      this.spinner.load(`Fetching ${this.period.label} market data...`);
      this.screen.render();
    }
    try {
      const assets = await this.dataService.fetchAll(
        this.config.tickers,
        this.config.cryptoIds ?? {},
        this.period.days
      );
      const now = Date.now();
      for (const asset of assets) {
        const previous = this.previousPrices.get(asset.symbol);
        if (Number.isFinite(previous) && previous > 0 && previous !== asset.price) {
          this.flashUntil.set(asset.symbol, now + FLASH_MS);
        }
        this.previousPrices.set(asset.symbol, asset.price);
      }
      this.assets = assets;
      if (this.selectedIndex >= assets.length) this.selectedIndex = Math.max(0, assets.length - 1);
      this.dataStatus = assets.some((asset) => asset.error)
        ? 'degraded'
        : assets.some((asset) => asset.fromCache)
          ? 'cached'
          : 'live';
    } catch (error) {
      this.dataStatus = 'error';
      this.pushLog('error', `refresh failed: ${error.message}`);
    } finally {
      this.refreshing = false;
      this.nextRefreshAt = Date.now() + this.config.updateIntervalMs;
      if (manual) this.spinner.stop();
      this.render();
    }
  }

  buildSnapshot() {
    return {
      generated_at: new Date().toISOString(),
      period_label: this.period.label,
      period_days: this.period.days,
      assets: this.assets
        .filter((asset) => !asset.error && asset.price > 0)
        .map((asset) => ({
          symbol: asset.symbol,
          kind: asset.category,
          price: asset.price,
          change_pct: asset.change,
          history: (asset.history ?? []).slice(-260)
        }))
    };
  }

  async runWorkflow() {
    if (!this.agent || this.analyzing) return;
    const snapshot = this.buildSnapshot();
    if (snapshot.assets.length === 0) return;

    this.analyzing = true;
    this.render();
    try {
      const report = await this.agent.analyze(snapshot);
      if (report) {
        this.advisory = report;
        this.pushLog('info', `workflow report received (${report.mode})`);
      }
    } catch (error) {
      this.pushLog('error', `workflow failed: ${error.message}`);
    } finally {
      this.analyzing = false;
      this.render();
    }
  }

  advisoryRow(symbol) {
    return this.advisory?.rows?.find((row) => row.symbol === symbol) ?? null;
  }

  /** Read the active chat backend so the status bar can name the provider. */
  async refreshModelStatus() {
    if (!this.agent) return;
    const status = await this.agent.model({ action: 'status' });
    if (!status) return;
    this.modelStatus = status;
    this.renderStatus();
    this.screen.render();
  }

  // --- rendering ----------------------------------------------------------

  render() {
    this.renderWatchlist();
    this.renderChart();
    this.renderDetails();
    this.renderSignals();
    this.renderAgentCall();
    this.renderNotes();
    this.renderStatus();
    this.screen.render();
  }

  renderWatchlist() {
    if (this.assets.length === 0) return;
    const now = Date.now();
    const rows = [];

    const budget = this.tableBudget(this.watchlist, 30);
    const symbolWidth = budget >= 28 ? 8 : 6;
    const changeWidth = budget >= 28 ? 9 : 7;
    const priceWidth = Math.max(7, budget - symbolWidth - changeWidth);
    const compact = priceWidth < 11;
    this.watchlist.options.columnWidth = [symbolWidth, priceWidth, changeWidth];

    const section = (title, category) => {
      const members = this.assets.filter((asset) => asset.category === category);
      if (members.length === 0) return;
      rows.push([chalk.cyan(cell(title, symbolWidth)), '', '']);
      for (const asset of members) {
        const index = this.assets.indexOf(asset);
        const selected = index === this.selectedIndex;
        const flashing = (this.flashUntil.get(asset.symbol) ?? 0) > now;
        const symbol = cell(`${selected ? '>' : ' '}${asset.symbol}`, symbolWidth);
        const price = cell(
          compact ? formatPriceCompact(asset.price) : formatPrice(asset.price),
          priceWidth
        );
        const change = cell(formatChange(asset.change), changeWidth);
        const changeColor = asset.change >= 0 ? chalk.green : chalk.red;

        if (selected) {
          rows.push([
            chalk.bgBlue.white(symbol.padEnd(symbolWidth)),
            chalk.bgBlue.white(price.padEnd(priceWidth)),
            asset.change >= 0 ? chalk.bgBlue.green(change) : chalk.bgBlue.red(change)
          ]);
        } else {
          rows.push([
            flashing ? chalk.yellow(symbol) : chalk.white(symbol),
            flashing ? chalk.bgYellow.black(price) : chalk.white(price),
            changeColor(change)
          ]);
        }
      }
    };

    section('CRYPTO', 'crypto');
    section('STOCKS', 'stock');
    section('ETFs', 'etf');

    this.watchlist.setData({ headers: ['SYMBOL', 'PRICE', 'CHANGE'], data: rows });
  }

  renderChart() {
    const asset = this.selectedAsset;
    if (!asset) return;
    const history = (asset.history ?? []).filter((value) => Number.isFinite(value));
    if (history.length === 0) return;

    const min = Math.min(...history);
    const max = Math.max(...history);
    const pad = (max - min) * 0.05 || Math.max(min * 0.01, 1);
    this.chart.options.minY = min - pad;
    this.chart.options.maxY = max + pad;

    const label = asset.category === 'crypto' ? 'CRYPTO' : asset.category.toUpperCase();
    this.chart.setLabel(` ${asset.symbol} | ${label} | ${this.period.label} `);
    this.chart.setData([
      {
        title: asset.symbol,
        x: axisLabels(asset.timestamps, history.length, this.period.days),
        y: history,
        style: { line: asset.change >= 0 ? 'green' : 'red' }
      }
    ]);
  }

  renderDetails() {
    const asset = this.selectedAsset;
    if (!asset) return;
    const row = this.advisoryRow(asset.symbol);
    const width = this.innerWidth(this.detailsBox);
    const changeColor = asset.change >= 0 ? 'green' : 'red';
    const divider = ` {gray-fg}${'─'.repeat(width)}{/gray-fg}`;
    const source = asset.fromCache
      ? '{yellow-fg}[CACHE]{/yellow-fg}'
      : '{green-fg}[LIVE]{/green-fg}';
    const isCrypto = asset.category === 'crypto';

    const quotePairs = [
      ['Price', formatPrice(asset.price)],
      [isCrypto ? 'High 24h' : 'High', formatPrice(asset.high)],
      ['Change', `{${changeColor}-fg}${formatChange(asset.change)}{/${changeColor}-fg}`],
      [isCrypto ? 'Low 24h' : 'Low', formatPrice(asset.low)],
      ['Open', formatPrice(asset.open)],
      [isCrypto ? 'ATH' : '52w High', formatPrice(asset.high52w)],
      ['Prev Close', formatPrice(asset.previousClose)],
      [isCrypto ? 'ATL' : '52w Low', formatPrice(asset.low52w)]
    ];

    const sizePairs = [
      ['Volume', formatCompact(asset.volume)],
      ['Mkt Cap', formatCompact(asset.marketCap)],
      isCrypto
        ? ['Circ Supply', formatCompact(asset.circulatingSupply)]
        : ['Avg Volume', formatCompact(asset.avgVolume)],
      isCrypto ? ['Rank', asset.rank ? `#${asset.rank}` : 'N/A'] : ['P/E', formatNumber(asset.pe)]
    ];

    const lines = [
      ` {bold}{cyan-fg}${asset.symbol}{/cyan-fg}{/bold} {gray-fg}${asset.category.toUpperCase()}{/gray-fg}`,
      divider,
      ...this.layoutPairs(quotePairs, width),
      divider,
      ...this.layoutPairs(sizePairs, width),
      divider
    ];

    if (row) {
      lines.push(
        ...this.layoutPairs(
          [
            ['RSI(14)', formatNumber(row.rsi, 1)],
            ['Trend', String(row.trend ?? 'n/a')],
            ['SMA fast', formatPrice(row.sma_fast)],
            ['SMA slow', formatPrice(row.sma_slow)],
            ['Momentum', `${formatNumber(row.momentum_pct)}%`],
            ['Volatility', `${formatNumber(row.volatility_pct)}%`]
          ],
          width
        )
      );
    } else {
      lines.push(' {gray-fg}Workflow indicators pending — press [a].{/gray-fg}');
    }

    lines.push(divider, ` ${source} ${asset.error ? '{red-fg}[ERROR]{/red-fg}' : ''}`);
    this.detailsBox.setContent(lines.join('\n'));
  }

  renderSignals() {
    const rows = this.advisory?.rows ?? [];
    const budget = this.tableBudget(this.signalsTable, 22);
    const symbolWidth = Math.max(6, budget - 9);
    this.signalsTable.options.columnWidth = [symbolWidth, 5, 4];
    if (rows.length === 0) {
      this.signalsTable.setData({
        headers: ['SYMBOL', 'CALL', 'CONF'],
        data: [[chalk.gray('pending'), chalk.gray('--'), chalk.gray('--')]]
      });
      return;
    }
    const data = rows.map((row) => {
      const color =
        row.action === 'BUY' ? chalk.green : row.action === 'SELL' ? chalk.red : chalk.yellow;
      const selected = this.selectedAsset?.symbol === row.symbol;
      const symbol = cell(row.symbol, symbolWidth);
      return [
        selected ? chalk.bgBlue.white(symbol.padEnd(symbolWidth)) : chalk.white(symbol),
        color(cell(row.action, 5)),
        chalk.white(cell(`${Math.round((row.confidence ?? 0) * 100)}%`, 4))
      ];
    });
    this.signalsTable.setData({ headers: ['SYMBOL', 'CALL', 'CONF'], data });
  }

  renderAgentCall() {
    const asset = this.selectedAsset;
    const row = asset ? this.advisoryRow(asset.symbol) : null;
    const width = this.innerWidth(this.agentBox, 26);
    if (!row) {
      this.agentBox.setContent(
        this.analyzing
          ? `\n {magenta-fg}${this.wrap('Agent Framework workflow running...', width)}{/magenta-fg}`
          : `\n {gray-fg}${this.wrap('No workflow output yet. Press [a] to run the workflow.', width)}{/gray-fg}`
      );
      return;
    }
    const color = ACTION_COLORS[row.action] ?? 'white';
    this.agentBox.setContent(
      [
        ` {bold}${row.symbol}{/bold}  {${color}-fg}{bold}${row.action}{/bold}{/${color}-fg}  ${Math.round((row.confidence ?? 0) * 100)}%`,
        ` {gray-fg}max position ${formatNumber(row.max_position_pct, 1)}%{/gray-fg}`,
        ` {gray-fg}${'─'.repeat(width)}{/gray-fg}`,
        ` ${this.wrap(row.rationale ?? '', width)}`,
        ` {yellow-fg}${this.wrap(row.risk_note ?? '', width)}{/yellow-fg}`
      ].join('\n')
    );
  }

  renderNotes() {
    const width = this.innerWidth(this.notesBox, 26);
    if (!this.advisory) {
      this.notesBox.setContent(
        `\n {gray-fg}${this.wrap('The Agent Framework workflow has not produced a report yet.', width)}{/gray-fg}`
      );
      return;
    }
    const risk = this.advisory.portfolio_risk ?? 'MEDIUM';
    const riskColor = RISK_COLORS[risk] ?? 'white';
    const modeColor = this.advisory.mode === 'agent' ? 'green' : 'yellow';
    this.notesBox.setContent(
      [
        ` {bold}${this.wrap(this.advisory.headline ?? '', width)}{/bold}`,
        ` mode {${modeColor}-fg}${this.advisory.mode}{/${modeColor}-fg} risk {${riskColor}-fg}${risk}{/${riskColor}-fg}`,
        ` {gray-fg}${'─'.repeat(width)}{/gray-fg}`,
        ' {cyan-fg}MARKET{/cyan-fg}',
        ` ${this.wrap(this.advisory.market_note ?? '', width)}`,
        '',
        ' {cyan-fg}RISK{/cyan-fg}',
        ` ${this.wrap(this.advisory.risk_summary ?? '', width)}`,
        '',
        ` {gray-fg}${this.wrap(this.advisory.disclaimer ?? '', width)}{/gray-fg}`
      ].join('\n')
    );
  }

  /** Usable content width of a bordered panel, in columns. */
  innerWidth(box, fallback = 40) {
    const width = Number.isFinite(box?.width) ? box.width : fallback;
    return Math.max(16, width - 4);
  }

  /** Columns available to `blessed-contrib` table cells, excluding column spacing. */
  tableBudget(table, fallback = 30) {
    const width = Number.isFinite(table?.width) ? table.width : fallback;
    return Math.max(14, width - 6);
  }

  /** Visible width of tagged content, ignoring blessed `{...}` markup. */
  static visibleLength(text) {
    return String(text).replace(/\{[^}]*\}/g, '').length;
  }

  /** Lay label/value pairs into one or two columns depending on panel width. */
  layoutPairs(pairs, width) {
    const columns = width >= 46 ? 2 : 1;
    const cell = Math.floor(width / columns);
    const labelWidth = Math.min(12, Math.max(6, cell - 10));
    const lines = [];
    for (let i = 0; i < pairs.length; i += columns) {
      let line = ' ';
      for (let column = 0; column < columns; column++) {
        const pair = pairs[i + column];
        if (!pair) continue;
        const [label, value] = pair;
        const text = `{bold}${label.padEnd(labelWidth)}{/bold}${value}`;
        const padding = Math.max(0, cell - ChartCliDashboard.visibleLength(text));
        line += column === columns - 1 ? text : text + ' '.repeat(padding);
      }
      lines.push(line);
    }
    return lines;
  }

  wrap(text, width) {
    const words = String(text).split(/\s+/).filter(Boolean);
    const lines = [];
    let current = '';
    for (const word of words) {
      if (current.length + word.length + 1 > width) {
        if (current) lines.push(current);
        current = word;
      } else {
        current = current ? `${current} ${word}` : word;
      }
    }
    if (current) lines.push(current);
    return lines.join('\n ');
  }

  /** Word-wrap for overlay text: keeps blank lines and adds no left padding. */
  wrapPlain(text, width) {
    const safeWidth = Math.max(20, width);
    return String(text)
      .split('\n')
      .map((paragraph) => {
        const words = paragraph.split(/\s+/).filter(Boolean);
        const lines = [];
        let current = '';
        for (const word of words) {
          if (current && current.length + word.length + 1 > safeWidth) {
            lines.push(current);
            current = word;
          } else {
            current = current ? `${current} ${word}` : word;
          }
        }
        if (current) lines.push(current);
        return lines.join('\n');
      })
      .join('\n');
  }

  renderStatus() {
    const dataTag =
      this.dataStatus === 'live'
        ? '{green-fg}LIVE{/green-fg}'
        : this.dataStatus === 'cached'
          ? '{yellow-fg}CACHED{/yellow-fg}'
          : this.dataStatus === 'degraded'
            ? '{yellow-fg}DEGRADED{/yellow-fg}'
            : '{red-fg}OFFLINE{/red-fg}';

    const agentState = this.agent?.status ?? 'disabled';
    const agentTag = this.analyzing
      ? '{magenta-fg}WORKFLOW…{/magenta-fg}'
      : this.asking
        ? '{magenta-fg}ASK…{/magenta-fg}'
        : this.backtesting
          ? '{magenta-fg}BACKTEST…{/magenta-fg}'
        : agentState === 'agent'
          ? '{green-fg}AGENT{/green-fg}'
          : agentState === 'offline'
            ? '{yellow-fg}AGENT:RULES{/yellow-fg}'
            : agentState === 'error'
              ? '{red-fg}AGENT:ERR{/red-fg}'
              : `{gray-fg}AGENT:${agentState}{/gray-fg}`;

    const provider = this.modelStatus?.provider
      ? ` | {cyan-fg}${this.modelStatus.provider}{/cyan-fg}`
      : '';
    const hints = KEYS.map(
      (binding) => `{cyan-fg}[${binding.hint}]{/cyan-fg} ${binding.label}`
    ).join(' ');
    const countdown = Math.max(0, Math.ceil((this.nextRefreshAt - Date.now()) / 1000));
    this.statusBar.setContent(
      ` ${dataTag} | ${agentTag}${provider} | ${this.selectedIndex + 1}/${this.assets.length} | ${this.period.label} | ${formatClock()} | next ${countdown}s | ${hints}`
    );
  }

  // --- lifecycle ----------------------------------------------------------

  shutdown() {
    clearInterval(this.tickTimer);
    clearInterval(this.dataTimer);
    clearInterval(this.agentTimer);
    this.agent?.stop();
    this.screen.destroy();
    process.exit(0);
  }

  async start() {
    this.spinner.load('Loading market data...');
    this.screen.render();
    this.agent?.start();

    await this.refresh();
    this.spinner.stop();
    this.render();
    void this.runWorkflow();
    void this.refreshModelStatus();

    this.tickTimer = setInterval(() => {
      this.renderWatchlist();
      this.renderStatus();
      this.screen.render();
    }, 1000);

    this.dataTimer = setInterval(() => void this.refresh(), this.config.updateIntervalMs);

    const agentInterval = this.config.agent?.analyzeIntervalMs ?? 0;
    if (this.agent && agentInterval > 0) {
      this.agentTimer = setInterval(() => void this.runWorkflow(), agentInterval);
    }
  }
}

const dashboard = new ChartCliDashboard();
dashboard.start().catch((error) => {
  console.error('chart-cli fatal error:', error);
  process.exit(1);
});
