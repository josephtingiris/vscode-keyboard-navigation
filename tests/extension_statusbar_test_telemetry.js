#!/usr/bin/env node
//
// (C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)
//
const fs = require('fs');
const path = require('path');

// create a small mock `vscode` module under node_modules for the test harness
const mockDir = path.join(__dirname, '..', 'node_modules', 'vscode');
fs.mkdirSync(mockDir, { recursive: true });

const mockCode = `
let registeredCommands = {};
let lastOutputLines = [];

module.exports = {
  ConfigurationTarget: { Global: 1 },
  StatusBarAlignment: { Right: 1 },
  ColorThemeKind: { Light: 1, Dark: 2 },
  window: {
    activeColorTheme: { kind: 1 },
    createStatusBarItem: () => ({
      show() {}, hide() {}, dispose() {},
      text: '', color: undefined, tooltip: '', command: null
    }),
    createOutputChannel: (name) => ({
      appendLine: (l) => { lastOutputLines.push(String(l)); },
      getLines: () => lastOutputLines.slice(),
      dispose: () => {}
    }),
    showQuickPick: async () => null,
    showInformationMessage: (m) => console.log('[info]', m),
  },
  workspace: {
    _config: {
      'keyboardNavigation': {
        enabled: true,
        keys: { arrows: true, vi: true, emacs: false, kbm: false },
        highlights: { enabled: false, color: '#FF0000' },
        preferences: { orientation: 'default' }
      }
    },
    getConfiguration: function(ns) {
      const self = this;
      return {
        get: function(key, def) {
          const cfg = self._config['keyboardNavigation'];
          if (!key) return cfg || def;
          const parts = key.split('.');
          let v = cfg;
          for (const p of parts) {
            if (v && Object.prototype.hasOwnProperty.call(v, p)) v = v[p]; else { v = undefined; break; }
          }
          return v === undefined ? def : v;
        },
        update: function(key, val) {
          const cfg = self._config['keyboardNavigation'];
          const parts = key.split('.');
          if (parts.length === 1) { cfg[parts[0]] = val; return Promise.resolve(); }
          let obj = cfg;
          for (let i = 0; i < parts.length - 1; i++) {
            const p = parts[i];
            if (!(p in obj)) obj[p] = {};
            obj = obj[p];
          }
          obj[parts[parts.length - 1]] = val;
          return Promise.resolve();
        }
      };
    },
    inspect: function(key) {
      // return a minimal inspect result so code can pick a target
      const cfg = this._config['keyboardNavigation'];
      const parts = key.split('.');
      let v = cfg;
      for (const p of parts) {
        if (v && Object.prototype.hasOwnProperty.call(v, p)) v = v[p]; else { v = undefined; break; }
      }
      return {
        key,
        defaultValue: undefined,
        globalValue: v === undefined ? undefined : v,
        workspaceValue: undefined,
        workspaceFolderValue: undefined,
        userValue: undefined,
      };
    },
    onDidChangeConfiguration: function(cb) { return { dispose() {} }; }
  },
  commands: {
    registerCommand: (name, fn) => { registeredCommands[name] = fn; return { dispose() {} }; },
    _getRegistered: () => registeredCommands
  }
};
`;

const mockPath = path.join(mockDir, 'index.js');
fs.writeFileSync(mockPath, mockCode, 'utf8');

(async function run() {
  try {
    const extension = require(path.join(__dirname, '..', 'extension', 'main.js'));
    const context = { subscriptions: [], push(s) { this.subscriptions.push(s); } };
    await extension.activate(context);

    const mockVscode = require(path.join(__dirname, '..', 'node_modules', 'vscode'));
    const cmds = mockVscode.commands._getRegistered();

    if (!cmds['keyboardNavigation.showStatus']) {
      console.error('FAIL: showStatus command not registered');
      process.exit(2);
    }

    await cmds['keyboardNavigation.showStatus']();

    const lines = mockVscode.window.createOutputChannel('Keyboard Navigation').getLines();
    const found = lines.some(l => l.indexOf('[status] clicked') !== -1);

    if (found) {
      console.log('PASS: telemetry line logged on status click');
      process.exit(0);
    } else {
      console.error('FAIL: telemetry line not found. Lines:', lines);
      process.exit(3);
    }
  } catch (e) {
    console.error('ERROR running harness:', e);
    process.exit(4);
  } finally {
    try { fs.unlinkSync(mockPath); } catch (e) {}
  }
})();
