# VS Code 'when' contexts

This file consolidates VS Code version 1.109.0 'when' contexts into a line-oriented reference suitable for grepping.

### Misc / Notes

- Many keys support equality checks (e.g. editorLangId == typescript, resourceScheme == file, debugType == 'node').
- Use view.<viewId>.visible and viewItem / webviewId when targeting specific custom views or webviews.
- Keep this file greppable by searching for the bare context key (e.g. "editorFocus" or "resourceScheme").

## Workbench & Workspace contexts

workbenchState — kind of workspace opened ('empty', 'folder', 'workspace')
workspaceFolderCount — number of root folders in the workspace
openFolderWorkspaceSupport — whether open-folder workspaces are supported
enterMultiRootWorkspaceSupport — whether entering multi-root workspaces is supported
emptyWorkspaceSupport — whether empty workspaces are supported
dirtyWorkingCopies — whether any working copies have unsaved changes
remoteName — name of the remote the window is connected to (or empty)
virtualWorkspace — scheme of the current virtual workspace (or empty)
temporaryWorkspace — whether the workspace is from a temporary file system
isAgentSessionsWorkspace — whether current workspace is the agent sessions workspace
workbenchMode — current workbench mode
hasWebFileSystemAccess — support for FileSystemAccess web APIs
embedderIdentifier — identifier of the embedder (if defined)
inAutomation — whether VS Code is running under automation/smoke test
isFullscreen — whether the main window is fullscreen
isAuxiliaryWindowFocusedContext — whether an auxiliary window is focused
isWindowAlwaysOnTop — whether window is always on top
isAuxiliaryWindow — window is an auxiliary window
isFullscreen — True when window is in fullscreen (duplicated entry)

## Editor & Text contexts

editorFocus — An editor has focus (either the text or a widget)
editorTextFocus — The text in an editor has focus (cursor is blinking)
textInputFocus — Any editor has focus (regular editor, debug REPL, etc.)
inputFocus — Any text input area has focus (editors or text boxes)
editorTabMovesFocus — Whether Tab will move focus out of the editor
editorHasSelection — Text is selected in the editor
editorHasMultipleSelections — Multiple regions of text are selected (multiple cursors)
editorReadonly — The editor is read only
editorLangId — True when the editor's associated language ID matches (example: editorLangId == typescript)
isInDiffEditor — The active editor is a difference editor
isInEmbeddedEditor — Focus is inside an embedded editor
editorIsOpen — whether an editor is open
activeEditor — identifier of the active editor
activeEditorIsDirty — whether the active editor has unsaved changes
activeEditorIsNotPreview — whether the active editor is not in preview (pinned)
activeEditorIsPinned — whether the active editor is pinned
activeEditorIsReadonly — whether the active editor is read-only
activeEditorIsFirstInGroup — whether active editor is first in its group
activeEditorIsLastInGroup — whether active editor is last in its group
activeEditorAvailableEditorIds — available editor identifiers usable for the active editor
editorPartMultipleEditorGroups — whether editor part has multiple editor groups
editorPartMaximizedEditorGroup — whether editor part has a maximized group

## Editor Group & Tabs

groupEditorsCount — number of opened editors in the group
activeEditorGroupEmpty — whether the active editor group is empty
activeEditorGroupIndex — index of the active editor group
activeEditorGroupLast — whether the active editor group is the last group
activeEditorGroupLocked — whether the active editor group is locked
multipleEditorGroups — whether there are multiple editor groups open
multipleEditorsSelectedInGroup — whether multiple editors are selected in a group
twoEditorsSelectedInGroup — whether exactly two editors are selected in a group
SelectedEditorsInGroupFileOrUntitledResourceContextKey — whether all selected editors in a group have a file or untitled resource
activeEditorCanSplitInGroup — whether the active editor can be split in group
activeEditorCanToggleReadonly — whether active editor can toggle readonly/writeable
activeEditorCanRevert — whether the active editor can revert
activeCompareEditorCanSwap — whether the active compare editor can swap sides

## Global Editor UI & Views

textCompareEditorVisible — whether a text compare editor is visible
textCompareEditorActive — whether a text compare editor is active
sideBySideEditorActive — whether a side-by-side editor is active
inSearchEditor — True when focus is inside a search editor
activeWebviewPanelId — ID of the currently active webview panel
activeCustomEditorId — ID of the currently active custom editor
focusedView — identifier of the view that has keyboard focus
view.<viewId>.visible — whether a specific view (use view.{id}.visible) is visible
view — The view to display the command in (e.g. view == myViewsExplorerID)
viewItem — The contextValue from a tree item (e.g. viewItem == someContextValue)
activeAuxiliary — identifier of the active auxiliary panel
auxiliaryBarFocus — whether the auxiliary bar has keyboard focus
auxiliaryBarVisible — whether the auxiliary bar is visible
auxiliaryBarMaximized — whether the auxiliary bar is maximized

## Global UI contexts

notificationFocus — Notification has keyboard focus
notificationCenterVisible — Notification Center is visible
notificationToastsVisible — Notification toast is visible
searchViewletVisible — Search view is open
sideBarVisible — Side Bar is displayed
sideBarFocus — Side Bar has focus
panelFocus — Panel has focus
inZenMode — Window is in Zen Mode
isCenteredLayout — Editor is in centered layout mode
replaceActive — Search view Replace text box is open
isCompactTitleBar — whether title bar is in compact mode
titleBarStyle — style of the window title bar
titleBarVisible — whether the title bar is visible
statusBarFocused — whether the status bar has keyboard focus
bannerFocused — whether the banner has keyboard focus
canNavigateBack — navigation availability flag
canNavigateForward — navigation availability flag
canNavigateToLastEditLocation — navigation availability flag
isWindowAlwaysOnTop — whether window is always on top (duplicated entry)

## OS & Platform contexts

isLinux — True when the OS is Linux
isMac — True when the OS is macOS
isWindows — True when the OS is Windows
isWeb — True when accessing the editor from the Web

## Lists & Selection contexts

listFocus — A list has focus
listSupportsMultiselect — A list supports multi select
listHasSelectionOrFocus — A list has selection or focus
listDoubleSelection — A list has a selection of 2 elements
listMultiSelection — A list has a selection of multiple elements

## Mode contexts

inSnippetMode — The editor is in snippet mode
inQuickOpen — The Quick Open dropdown has focus
inDebugMode — A debug session is running (also listed under Debugger contexts)

## Resource & File contexts

resourceScheme — scheme of the resource (e.g. resourceScheme == file)
resourceFilename — filename of the resource (e.g. resourceFilename == gulpfile.js)
resourceExtname — extension name of the resource (e.g. resourceExtname == .js)
resourceDirname — folder name containing the resource (e.g. resourceDirname == /users/alice/project/src)
resourcePath — full path of the resource (e.g. resourcePath == /users/alice/project/gulpfile.js)
resourceLangId — language identifier of the resource (e.g. resourceLangId == markdown)
resource — full URI (scheme + path) of the resource
resourceSet — whether a resource is present
isFileSystemResource — whether the resource is backed by a file system provider
isFileSystemResource — True when the file is a filesystem resource handled by a provider (duplicate phrasing merged)

## Explorer contexts

explorerViewletVisible — Explorer view is visible
explorerViewletFocus — Explorer view has keyboard focus
filesExplorerFocus — File Explorer section has keyboard focus
openEditorsFocus — OPEN EDITORS section has keyboard focus
explorerResourceIsFolder — A folder is selected in the Explorer

## Editor widget contexts

findWidgetVisible — Editor Find widget is visible
suggestWidgetVisible — Suggestion widget (IntelliSense) is visible
suggestWidgetMultipleSuggestions — Multiple suggestions are displayed
renameInputVisible — Rename input text box is visible
referenceSearchVisible — Peek References window is open
inReferenceSearchEditor — The Peek References editor has focus
config.editor.stablePeek — Keep peek editors open (editor.stablePeek setting)
codeActionMenuVisible — Code Action menu is visible
parameterHintsVisible — Parameter hints are visible (editor.parameterHints.enabled)
parameterHintsMultipleSignatures — Multiple parameter hints are displayed

## Debugger contexts

debuggersAvailable — An appropriate debugger extension is available
inDebugMode — A debug session is running
debugState — Active debugger state (inactive, initializing, stopped, running)
debugType — True when debug type matches (e.g. debugType == 'node')
inDebugRepl — Focus is in the Debug Console REPL

## Integrated terminal contexts

terminalFocus — An integrated terminal has focus
terminalIsOpen — An integrated terminal is opened

## Timeline view contexts

timelineFollowActiveEditor — Timeline view is following the active editor
timelineItem — Timeline item's context value matches (e.g. timelineItem =~ /git:file:commit\\b/)

## Extension & Configuration contexts

extension — True when the extension's ID matches (e.g. extension == eamodio.gitlens)
extensionStatus — True when the extension is installed (e.g. extensionStatus == installed)
extensionHasConfiguration — True if the extension has configuration
config.editor.minimap.enabled — True when the setting editor.minimap.enabled is true
