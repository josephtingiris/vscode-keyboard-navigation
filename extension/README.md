# VS Code Keyboard Navigation

The VS Code Keyboard Navigation extension provides an opinionated modal keyboard grammar that focuses on speedrunning the Workbench UI.
It is designed to build upon and complement vi/vim/neovim muscle memory by including alt+hjkl alongside alt+arrow key navigation throughout
the VS Code WorkBench UI components (editor groups, side bars, panel, and terminals).

Why use it
- Keeps your hands on the keyboard.
- Fluid spatial navigation throughout workbench components.
- Navigate faster and more accurately, without the need to remember a million shortcuts.
- Optional (but useful!) visual highlights for when your fingers are moving faster than your eyes (or when an observer is trying to keep up).
- Configurable key groups; enable/disable various well-know key groups such as `arrows` and/or `vi`.  Disable groups that get in your way, or learn them one at a time.
- Easy. Easy. Easier. Easiest. Intuitive. Smooth.

Highlights
- intuitive and predictable use of the arrow keys
- complements vi/vim/neovim keyboard grammar
- extensive testing with the vscode-neovim extension
- smooth keyboard navigation across editors, side bars, panel, and terminals
- configurable orientation, visual cues, and highlight color
- lightweight status bar indicator with clever indicators

Install
- From the VS Code Marketplace (recommended) or build/install from source in `extension/`.

Basic usage
- Press `alt+left/alt+right/alt+up/alt+down` (or `alt+h/j/k/l`) and other variants (i.e. `alt+shif+j`) to move focus between
	the visible workbench surfaces.

Configuration (selected)
- `keyboardNavigation.enabled` (boolean): enable/disable the extension (default: `true`).

Support & development
- Report issues, feature requests, or contribute on the GitHub repository root.

License
- Distributed under the terms in the [LICENSE](LICENSE) file.