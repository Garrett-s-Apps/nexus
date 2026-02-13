"""
Prompt fragments injected into agent system prompts based on role.

Each fragment instructs agents to use Claude Code plugins (LSP, AST grep,
Context7, Greptile, Playwright) that are available in their CLI sessions.
"""

# Engineers: LSP diagnostics, ast_grep_search, Context7 for docs lookup
ENGINEER_LSP_INSTRUCTIONS = """
PLUGIN TOOLS — Use these during implementation:
- Run `lsp_diagnostics` on files you modify to catch type errors and warnings before committing.
- Use `lsp_goto_definition` and `lsp_find_references` to understand call sites before refactoring.
- Use `ast_grep_search` to find code patterns (e.g., pattern `console.log($MSG)` to find debug logs).
- Use Context7 MCP tools (`resolve-library-id` then `query-docs`) to look up library/framework documentation instead of guessing APIs.
- Run `lsp_diagnostics_directory` on the project after large changes to catch regressions.
"""

# Reviewers: LSP diagnostics, lsp_find_references, ast_grep_search, Greptile
REVIEWER_PLUGIN_INSTRUCTIONS = """
PLUGIN TOOLS — Use these during code review:
- Run `lsp_diagnostics` on changed files to verify zero errors/warnings.
- Use `lsp_find_references` to check that refactored symbols are updated everywhere.
- Use `ast_grep_search` to detect anti-patterns (e.g., bare `except:`, `type: any`, SQL string concatenation).
- Use Greptile tools (`search_greptile_comments`, `list_merge_request_comments`) to check for prior review feedback on similar code.
- Use `lsp_document_symbols` to verify consistent naming and structure in modified files.
"""

# QA: lsp_diagnostics_directory, ast_grep_search, Playwright
QA_PLUGIN_INSTRUCTIONS = """
PLUGIN TOOLS — Use these during testing:
- Run `lsp_diagnostics_directory` on the full project to catch type errors and import issues before testing.
- Use `ast_grep_search` to find untested code paths and missing error handling patterns.
- Use Playwright tools (`browser_navigate`, `browser_snapshot`, `browser_click`) for end-to-end UI testing when testing web interfaces.
- Verify test file structure with `lsp_document_symbols` to ensure test coverage aligns with source modules.
"""

# Security: ast_grep_search for OWASP patterns, lsp_find_references on auth
SECURITY_PLUGIN_INSTRUCTIONS = """
PLUGIN TOOLS — Use these during security review:
- Use `ast_grep_search` to scan for OWASP Top 10 patterns:
  - SQL injection: patterns like `f"SELECT {$COL}"`, `"SELECT " + $VAR`
  - XSS: patterns like `innerHTML = $VAR`, unsafe HTML rendering
  - Command injection: patterns like `subprocess.call($CMD, shell=True)`
  - Hardcoded secrets: patterns like `password = "$VAL"`, `api_key = "$VAL"`
- Use `lsp_find_references` on auth/session/token symbols to trace trust boundaries.
- Run `lsp_diagnostics` to catch unsafe type coercions and missing null checks.
- Cross-reference findings against SOC 2 Type II control requirements.
"""

# Map role names to their prompt fragments
_ROLE_FRAGMENTS = {
    "engineer": ENGINEER_LSP_INSTRUCTIONS,
    "reviewer": REVIEWER_PLUGIN_INSTRUCTIONS,
    "qa": QA_PLUGIN_INSTRUCTIONS,
    "security": SECURITY_PLUGIN_INSTRUCTIONS,
}


def get_prompt_fragment(role: str) -> str:
    """Return the plugin instruction fragment for a given agent role."""
    return _ROLE_FRAGMENTS.get(role, "")
