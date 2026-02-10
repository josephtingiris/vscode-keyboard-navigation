const vscode = require("vscode");

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
      let orientation = config.get("orientation", "left");
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
    const current = altCfg.get('highlights', false);
    const next = !current;

    try {
      await altCfg.update('highlights', next, vscode.ConfigurationTarget.Global);
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

function deactivate() {}

module.exports = { activate, deactivate };
