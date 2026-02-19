# Changelog

All notable changes to this repository will be documented in this file.

This project adheres to "Keep a Changelog" conventions. Entries are grouped by date (YYYY-mm-dd) with sections: Added, Changed, Deprecated, Removed, Fixed, Security. Each bullet references commits or files for traceability.
## 2026-02-18

### Added
- Add `--when-prefix` and `--when-regex` options to `bin/keybindings-sort.py` (commit a241ce9).
- Add comments-handling support to keybindings tooling (commit 4933bb1).

### Changed
- Set default `KEYBINDINGS_SORT_ARGUMENTS` and default keybindings for `keybindings-sort.py` (commits 7d9ee02, 29adeb3).
- Prepare 0.0.2 release candidate and tag RC artifacts (commits f973c27, 4f8aaec).

### Fixed
- Fix root chords parsing/handling (commit c1da95d).

## 2026-02-17

### Changed
- Update release candidate metadata and checkpoint references (commits 1ea2d71, 9ed6dc6).
- Adjust SCM/make root handling and housekeeping changes (commits 264a0c8, 1c61ff5).

## 2026-02-16

### Changed
- Checkpoint and wrapping fixes in references and corpus (commits 16bd339, 457fa70).

## 2026-02-15

### Added
- Add focal-invariant example for keybinding sorting (commit 185742e).

### Changed
- Add and revise argument parsing, usage, RNG handling, and formatting for CLI tools (commits a58a750, 3241d71).
- Consolidate when-token lists and prioritize negation flag before base key (commits 8f99e7e, 1b02f50).

## 2026-02-14

### Added
- Add experimental when-grouping/focal-invariant support and token-order tuning for `keybindings-sort.py` (commits ef05394, 970ab28).

### Changed
- Several checkpoints and refinements to reference data and grouping rules used by sorting and canonicalization logic (multiple checkpoint commits on 2026-02-14).

## 2026-02-13

### Changed
- Add project and workspace configuration guidance; apply formatting and repository ignore rules (commits fd3b6a9, 0619d6c, d4260b6).
- Add multiple hand-crafted reference updates to `references/` used for when-token tests (commits 866a780, aca5322).

## 2026-02-12

### Changed
- Remove sleep and fix race conditions in test/dev helpers; checkpoint reference updates (commits 352a624, ebd475f, 3404625).

## 2026-02-11

### Added
- Add reference datasets and generated corpus improvements used for sorting and testing (`references/`, `bin/keybindings-corpus.py`) (commits 6a261ac, c33bff9, db9c3e9).
- Add initial visual overview and examples (commits 6d7a6b4, c3ca052).

### Changed
- Numerous test/reference additions for EXTRA_WHENS and focus/visibility variants to improve sort correctness (commits f493914, 3615f66, d2bb7a06).

## 2026-02-10

### Added
- Add primary CLI tools: `bin/keybindings-sort.py`, `bin/keybindings-merge.py`, `bin/keybindings-remove.py`, and supporting scripts for JSONC handling (commits 28f248a, 1dfb5ed, 514a366, 56beb96).
- Add `bin/keybindings-corpus.py` for deterministic generation of JSONC keybinding objects (commit c5263d1).

### Changed
- Add README/DEVELOPMENT.md updates and tooling helpers (commits ce74c7b, b1dd13f0).

## 2026-02-09 and earlier

### Added
- Initial project scaffolding, license, extension metadata, and early reference material (multiple commits, see c9ecbfb, fdd356c, 20944c5).