# VS Code Keyboard Navigation

The VS Code Keyboard Navigation extension provides an opinionated modal keyboard grammar that focuses on speedrunning the Workbench UI.
It is designed to build upon and complement vi/vim/neovim muscle memory by including alt+hjkl alongside alt+arrow key navigation throughout
the VS Code WorkBench UI components (editor groups, side bars, panel, and terminals).

Why use it
- Keeps your hands on the keyboard — fast and fluid spatial navigation throughout workbench components.
- Optional (but useful!) visual highlights for when your fingers are moving faster than your eyes (or an observer is trying to keep up).
- Configurable orientation and optional wrap behaviors (primary sidebar on the left side of the screen by default).
- Respects in-element movement (lists, trees, and editor splits) when available.

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
- `keyNav.enabled` (boolean): enable/disable the extension (default: `true`).

Support & development
- Report issues, feature requests, or contribute on the GitHub repository root.

License
- Distributed under the terms in the [LICENSE](LICENSE) file.