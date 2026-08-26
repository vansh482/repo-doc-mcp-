# Changelog

All notable changes to Repo Doc Generator are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-08-22

### Added
- Smart base branch detection — auto-detects mainline/develop/development, checks git tracking config, falls back to remote branches
- Custom instructions text field in sidebar — per-run formatting hints passed to the LLM
- Base branch selector in sidebar — visible "Compare against:" input, synced with settings
- Token usage tracking — all 3 LLM providers report input/output tokens, logged per-run
- Wire up docLength setting — concise/standard/detailed now controls output length
- Page-level restrictions — new Confluence pages locked to creator only
- Error recovery — if Confluence publish fails, docs saved locally to .repodoc/
- Non-code artifact coverage — prompts explicitly cover licenses, configs, CI/CD, package metadata
- Diff truncation at file boundaries — prioritizes source code files, lists skipped files
- Structured output channel logging — step numbers, branch info, token usage, timing
- CI/CD pipeline — GitHub Actions for PR checks and tag-based marketplace releases

### Changed
- Page titles simplified to `branchName — Technical/Summary` (removed repo name prefix)
- LLM provider interface returns `LLMResponse { content, usage }` instead of plain string

### Fixed
- Diff truncation no longer cuts mid-file (was sending half-files to LLM)

## [0.1.0] - 2026-08-18

### Added
- Initial release
- TypeScript VS Code extension with sidebar UI
- Git diff extraction (three-dot strategy)
- Repository scanning (languages, structure, key files)
- LLM integration (Anthropic Claude, OpenAI GPT-4o, AWS Bedrock)
- Confluence publishing (create + update pages)
- Branch-to-page tracking (update existing, don't duplicate)
- Progress indicator with step-based updates, elapsed time, and cancel button
- Setup wizard webview for first-time configuration
- SecretStorage for API keys (OS keychain)
- Personal space security constraint
- Extension icon and marketplace publishing
- MIT License
