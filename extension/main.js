// (C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)
const vscode = require("vscode");

let statusBarItem = null;
let outputChannel = null;

/**
 * Activate the extension.
 * Registers command `keyboardNavigation.resetLayout` which resets sidebar/panel placement
 * according to `keyboardNavigation.orientation` setting.
 */
function activate(context) {
  const disposable = vscode.commands.registerCommand(
    "keyboardNavigation.resetLayout",
    async () => {
      const config = vscode.workspace.getConfiguration("keyboardNavigation");
      let orientation = config.get("preferences.orientation", "left");
      if (!orientation) orientation = "left";

      const workbench = vscode.workspace.getConfiguration("workbench");

      // Always set the panel to bottom first
      try {
        await vscode.commands.executeCommand(
          "workbench.action.positionPanelBottom",
        );
      } catch (e) {
        // ignore if command doesn't exist
      }

      // Behavior: 'default' should reset to VS Code default (left).
      // 'left' forces left, 'right' forces right.
      let target = "left";
      if (orientation === "right") {
        target = "right";
      } else {
        // For 'default' and any other value, default to 'left'
        target = "left";
      }

      try {
        await workbench.update(
          "sideBar.location",
          target,
          vscode.ConfigurationTarget.Global,
        );
        vscode.window.showInformationMessage(
          `keyboardNavigation.resetLayout: set sideBar.location -> ${target}; panel -> bottom`,
        );
      } catch (e) {
        vscode.window.showErrorMessage(
          `keyboardNavigation.resetLayout failed: ${e && e.message ? e.message : String(e)}`,
        );
      }
    },
  );

  context.subscriptions.push(disposable);

  // --- status bar: show extension state and open a small summary when clicked
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarItem.command = 'keyboardNavigation.showStatus';
  statusBarItem.tooltip = 'Keyboard Navigation';
  context.subscriptions.push(statusBarItem);

  // create output channel for logging/telemetry
  outputChannel = vscode.window.createOutputChannel('Keyboard Navigation');
  context.subscriptions.push(outputChannel);

  function updateStatus() {
    try {
      const cfg = vscode.workspace.getConfiguration('keyboardNavigation');
      const enabled = Boolean(cfg.get('enabled', true));
      const arrows = Boolean(cfg.get('keys.arrows', true));
      const letters = String(cfg.get('keys.letters', 'vi'));
      const vi = (letters === 'vi');
      const emacs = (letters === 'emacs');
      const kbm = (letters === 'kbm');
      const orientation = cfg.get('preferences.orientation', 'default');

      const stateText = enabled ? 'Active' : 'Inactive';
      statusBarItem.text = '$(keyboard)';
      // For the ideal/normal state, do not draw attention: use the default status-bar color
      // Only color the icon when disabled (or other non-ideal states in the future).
      let color = undefined;
      if (!enabled) {
        const highlightsEnabled = Boolean(cfg.get('highlights.enabled', false));
        if (highlightsEnabled) {
          color = String(cfg.get('highlights.color', '#FF0000'));
        } else {
          // choose color depending on theme if available
          try {
            const themeKind = vscode.window.activeColorTheme && vscode.window.activeColorTheme.kind;
            if (themeKind === vscode.ColorThemeKind.Light) {
              color = '#8B0000';
            } else {
              color = '#FF3333';
            }
          } catch (e) {
            color = '#FF0000';
          }
        }
      }
      statusBarItem.color = color;
      statusBarItem.show();
      statusBarItem.tooltip = `Keyboard Navigation — ${stateText}\norientation: ${orientation}`;
    } catch (e) {
      // fall back to a safe state
      statusBarItem.text = 'KeyNav';
      statusBarItem.show();
    }
  }

  // Register a simple status command that shows a configuration summary and quick actions
  const showStatusCmd = vscode.commands.registerCommand('keyboardNavigation.showStatus', async () => {
    const cfg = vscode.workspace.getConfiguration('keyboardNavigation');
    const enabled = Boolean(cfg.get('enabled', true));
    const arrows = Boolean(cfg.get('keys.arrows', true));
    const letters = String(cfg.get('keys.letters', 'vi'));
    const vi = (letters === 'vi');
    const emacs = (letters === 'emacs');
    const kbm = (letters === 'kbm');
    const highlights = Boolean(cfg.get('highlights.enabled', false));
    const orientation = cfg.get('preferences.orientation', 'default');

    // log a tiny telemetry line when status is opened
    try { outputChannel.appendLine(`[status] clicked — enabled=${enabled} arrows=${arrows} vi=${vi} emacs=${emacs} kbm=${kbm}`); } catch (e) {}

    const items = [
      { label: `Enabled: ${enabled}` },
      { label: `Orientation: ${orientation}` },
      { label: `Key States: arrows = ${arrows}, emacs = ${emacs}, kbm = ${kbm}, vi = ${vi}` },
      { label: `Highlights enabled: ${highlights}` },
      { label: 'Open Settings' },
      { label: enabled ? 'Disable Keyboard Navigation' : 'Enable Keyboard Navigation' },
    ];

    const pick = await vscode.window.showQuickPick(items, { placeHolder: 'Keyboard Navigation — status' });
    if (!pick) return;
    if (pick.label === 'Open Settings') {
      await vscode.commands.executeCommand('workbench.action.openSettings', 'keyboardNavigation');
      return;
    }

    if (pick.label.startsWith('Disable') || pick.label.startsWith('Enable')) {
      // determine the correct configuration target to update so we actually change
      // the effective setting (respect workspace-scoped overrides)
      let target = vscode.ConfigurationTarget.Global;
      try {
        const inspect = cfg.inspect && cfg.inspect('enabled');
        if (inspect) {
          if (inspect.workspaceValue !== undefined) target = vscode.ConfigurationTarget.Workspace;
          else if (inspect.workspaceFolderValue !== undefined) target = vscode.ConfigurationTarget.WorkspaceFolder;
          else target = vscode.ConfigurationTarget.Global;
        }
      } catch (e) {
        target = vscode.ConfigurationTarget.Global;
      }

      await cfg.update('enabled', !enabled, target);
      updateStatus();
      // show a toast indicating which scope was updated
      let scopeName = 'User';
      try {
        if (typeof vscode.ConfigurationTarget !== 'undefined') {
          if (target === vscode.ConfigurationTarget.Workspace) scopeName = 'Workspace';
          else if (target === vscode.ConfigurationTarget.WorkspaceFolder) scopeName = 'Workspace Folder';
          else scopeName = 'User';
        }
      } catch (e) {
        scopeName = 'User';
      }
      vscode.window.showInformationMessage(`keyboardNavigation: ${!enabled ? 'enabled' : 'disabled'} (${scopeName})`);
    }
  });

  context.subscriptions.push(showStatusCmd);

  // Update status when configuration changes
  const cfgListener = vscode.workspace.onDidChangeConfiguration((e) => {
    if (e.affectsConfiguration('keyboardNavigation')) {
      updateStatus();
    }
  });
  context.subscriptions.push(cfgListener);

  // initialize status
  updateStatus();

  // Apply visual highlights based on `keyboardNavigation.highlights.color` and related settings
  async function applyKeyNavVisualHighlights() {
    const rootConfig = vscode.workspace.getConfiguration();
    const altCfg = vscode.workspace.getConfiguration('keyboardNavigation');
    const color = altCfg.get('highlights.color', '#FF0000');

    try {
      // Example: set a noticeable cursor style and color
      await rootConfig.update('editor.cursorStyle', 'block', vscode.ConfigurationTarget.Global);

      const existing = rootConfig.get('workbench.colorCustomizations') || {};
      const additions = {
        'editorCursor.foreground': color
      };

      await rootConfig.update(
        'workbench.colorCustomizations',
        { ...existing, ...additions },
        vscode.ConfigurationTarget.Global,
      );

      vscode.window.showInformationMessage(`keyboardNavigation: applied visual highlights (${color})`);
    } catch (e) {
      vscode.window.showErrorMessage(
        `keyboardNavigation.applyVisualHighlights failed: ${e && e.message ? e.message : String(e)}`,
      );
    }
  }

  // Toggle the `keyboardNavigation.highlights` setting; when enabling, apply highlights; when disabling, remove our keys
  async function toggleKeyNavHighlights() {
    const altCfg = vscode.workspace.getConfiguration('keyboardNavigation');
    const rootConfig = vscode.workspace.getConfiguration();
    const current = altCfg.get('highlights.enabled', false);
    const next = !current;

    try {
      await altCfg.update('highlights.enabled', next, vscode.ConfigurationTarget.Global);
      if (next) {
        await applyKeyNavVisualHighlights();
        vscode.window.showInformationMessage('keyboardNavigation: highlights enabled');
      } else {
        // remove only the keys we add; merge with existing
        const existing = rootConfig.get('workbench.colorCustomizations') || {};
        const updated = { ...existing };
        delete updated['editorCursor.foreground'];
        await rootConfig.update('workbench.colorCustomizations', updated, vscode.ConfigurationTarget.Global);
        vscode.window.showInformationMessage('keyboardNavigation: highlights disabled (removed customizations)');
      }
    } catch (e) {
      vscode.window.showErrorMessage(
        `keyboardNavigation.toggleVisualHighlights failed: ${e && e.message ? e.message : String(e)}`,
      );
    }
  }

  const applyDisposable2 = vscode.commands.registerCommand('keyboardNavigation.applyVisualHighlights', applyKeyNavVisualHighlights);
  const toggleDisposable2 = vscode.commands.registerCommand('keyboardNavigation.toggleVisualHighlights', toggleKeyNavHighlights);
  context.subscriptions.push(applyDisposable2, toggleDisposable2);
}

function deactivate() {
  try {
    if (statusBarItem) {
      statusBarItem.dispose();
      statusBarItem = null;
    }
    if (outputChannel) {
      try { outputChannel.dispose(); } catch (e) {}
      outputChannel = null;
    }
  } catch (e) {
    // ignore
  }
}

module.exports = { activate, deactivate };
