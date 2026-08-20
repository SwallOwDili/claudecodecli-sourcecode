# Claude Code 2.1.235 release notes

Source: upstream `anthropics/claude-code` `CHANGELOG.md`, captured on 2026-08-20.

- Added an optional `spellcheck` setting that underlines misspelled words in the prompt input as you type, using an installed `aspell`, `hunspell`, or `ispell`.
- Fixed whole-prompt-cache invalidation when a language server disconnected or reconnected mid-session.
- Fixed nested Markdown list item alignment at depth 3+ and added hanging indentation for wrapped list items in the terminal UI.
- Fixed prompt input highlights shifting by one or more characters in some multi-line prompts.
- Fixed Shift+Tab in the permission prompt comment field approving the edit and granting session-wide edit permission instead of closing the field.
- Fixed the Agent tool advertising a general-purpose default in sessions where that agent is unavailable; omitted `subagent_type` now reports the available agents.
- Fixed notebook cell delete/replace approval dialogs omitting the existing cell when it could not be read; the dialog now explains why.
- Fixed slash commands run while Claude is responding showing HTML entities instead of actual characters.
- Fixed the prompt footer not showing the `Update installed` restart notice after a background auto-update.
- Fixed the expanded task list (`ctrl+t`) always starting collapsed after resuming or relaunching a session with open tasks.
- Reduced memory and CPU use while cloud sessions such as `/ultrareview` and `/autofix-pr` run in the background by avoiding full event-stream rescans and re-renders on every update.
- Improved permission dialogs so display text and `don't ask again` options match the scope of the actual grant; the persistent option is withheld when content cannot be fully displayed.
- Improved embedded `grep` on native macOS/Linux builds: pathological patterns fail fast, and `-m N` with `-A`/`-C` prints correct context.
- Improved the context-limit error when auto-compact is disabled and linked the user to `/config` to re-enable it.
- Vim mode now preserves NORMAL mode and cursor position when toggling detailed transcript (`ctrl+o`) or closing a panel.
- Dialogs now process fast arrow-key plus Enter sequences against the newly navigated option instead of the stale highlight.
- `SendMessage` now rejects messages that exceed cross-session delivery limits instead of silently dropping them.
- Remote Control alias `claude rc` now applies the same enterprise-gateway availability check as interactive startup.
- VS Code: fixed focus jumping between Claude tabs when restoring or reloading a window containing several Claude panels.
