# AGENTS.md - AI Coding Agent Guide for LNbits Extensions

This file is an extension of the general AGENTS.md guidelines, tailored specifically for AI coding agents working on LNbits extensions. It emphasizes the unique architecture of LNbits, the importance of following existing patterns, and the need for careful verification in security-sensitive areas. The goal is to ensure that AI agents contribute effectively while maintaining the integrity and security of the LNbits ecosystem.

## LNbits Extension Architecture

- Extensions don't modify core functionality.
- Extensions have their own repository, database tables, API routes, and frontend code.

## Extension Commands and Verification

Read `Makefile` at extension root before running project commands.

Use Makefile targets instead of hand-written commands when available:

- `make prettier` for code formatting.
- `make ruff` for Python linting.
- `make black` for Python formatting.
- `make pyright` for Python type checking.
- `make test` for running tests (only when explicitly requested by the user).

## Frontend Template Rules

LNbits extension templates use custom Vue delimiters such as `${ ... }`. Avoid putting JavaScript string literals or ternaries directly inside text interpolation, because Prettier can split quoted strings across lines and cause browser runtime errors like `SyntaxError: string literal contains an unescaped line break`.

- Prefer `v-text`, `:label`, or computed properties for dynamic text/messages/buttons.
- Avoid inline `${ condition ? 'long label' : 'other label' }` inside `.vue` text nodes.
- After running Prettier, scan `.vue` files for multiline quoted strings inside `${ ... }` expressions when touching template text.

## Extension Dependencies

Extensions are not allowed to add dependencies.
