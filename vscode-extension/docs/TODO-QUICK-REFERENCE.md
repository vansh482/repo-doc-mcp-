# TODO Quick Reference — Sorted by Effort (Descending)

75 total items. Dependency chains noted with →.

---

## Large (3-7 days)

- [ ] IntelliJ plugin (2-7 days)
- [ ] Google Docs publisher (3-5 days) → needs DocPublisher interface
- [ ] SharePoint/OneNote publisher (3-5 days) → needs DocPublisher interface
- [ ] OAuth for Confluence (2-3 days) → needs AuthenticationProvider adoption
- [ ] Team knowledge base (3-5 days)
- [ ] Custom model fine-tuning (3-5 days)

## Medium (1-2 days)

- [ ] Notion publisher (1-2 days) → needs DocPublisher interface
- [ ] MCP Server (1-2 days) → needs Extract shared core
- [x] Smart base branch detection (1 day)
- [ ] CLI tool (1 day) → needs Extract shared core
- [ ] Unit tests (1-2 days)
- [ ] Integration tests (1-2 days) → needs Unit tests
- [ ] Streaming LLM output (1-2 days)
- [ ] Onboarding walkthrough (1 day)
- [ ] CI/CD pipeline (1 day)
- [ ] Real-time file watching (1-2 days)
- [ ] Scheduled generation (1 day)
- [ ] Doc comparison (1-2 days) → needs History panel
- [ ] Diagram generation (1-2 days)
- [ ] Analytics dashboard (1-2 days) → needs Token tracking
- [ ] Sentry integration (1 day)
- [ ] Telemetry / Application Insights (1 day)

## Half Day (4-6 hours)

- [ ] Extract shared core package (half day)
- [ ] VS Code AuthenticationProvider adoption (half day) → needs DocPublisher interface
- [ ] Multi-publisher simultaneous output (half day) → needs DocPublisher + 2+ publishers
- [ ] GitHub Action (half day) → needs CLI tool
- [ ] GitLab CI integration (half day) → needs CLI tool
- [ ] GitHub Wiki publisher (0.5-1 day) → needs DocPublisher interface
- [ ] Slack integration (0.5-1 day) → needs DocPublisher interface
- [ ] History panel (half day)
- [ ] Token refresh/rotation (half day)
- [ ] Credential validation on save (half day)
- [ ] Bundle with esbuild (half day)
- [ ] Strict TypeScript (half day)

## Quick (1-4 hours)

- [x] Fix page title naming (30 min)
- [x] Wire up `docLength` setting (1-2 hrs)
- [x] Output channel logging (1-2 hrs)
- [x] Custom instructions text field (2-3 hrs)
- [x] Cover non-code artifacts in docs (2-3 hrs)
- [x] Error recovery — save locally on publish fail (2-3 hrs)
- [x] Diff too large handling (2-3 hrs)
- [ ] DocPublisher interface + factory (2-3 hrs)
- [ ] ContentTransformer pipeline (3-4 hrs)
- [ ] Markdown file publisher (2-3 hrs) → needs DocPublisher interface
- [ ] Prompt versioning (2-3 hrs)
- [ ] Selective file exclusion (2-3 hrs)
- [ ] Draft mode (2-3 hrs)
- [ ] Commit-level docs (2-3 hrs)
- [ ] Auto-detect Confluence space (2-3 hrs)
- [ ] Generation metadata in sidebar (2-3 hrs) → needs Token tracking
- [ ] Quick pick for common actions (1-2 hrs)
- [x] Page-level restrictions (2-3 hrs)
- [x] Token usage tracking (2-3 hrs)
- [ ] Simple webhook on error (1-2 hrs)
- [ ] In-extension error report button (1-2 hrs)
- [ ] Usage analytics (2-3 hrs) → needs Token tracking
- [ ] Changelog (1 hr)
- [ ] Screenshots for marketplace (1-2 hrs)
- [ ] Custom endpoint / OpenAI-compatible (2-3 hrs)
- [ ] Ollama local LLM (2-3 hrs)
- [ ] Azure OpenAI (2-3 hrs)
- [ ] Google Vertex AI (2-3 hrs)
- [x] Smart base branch detection error message fix (30 min)

## Not Estimated (future/vague)

- [ ] PR description generation
- [ ] Diff changelog mode
- [ ] Doc preview before publish
- [ ] Branch comparison picker
- [ ] Custom prompt templates
- [ ] Usage-based pricing
- [ ] Team/org licenses
- [ ] Priority LLM routing

---

## Dependency Chains

```
Extract shared core ──► CLI tool ──► GitHub Action
                    └──► MCP Server    └──► GitLab CI

DocPublisher interface ──► ContentTransformer ──► AuthenticationProvider adoption
         │                                              │
         ├──► Markdown publisher                        ├──► Multi-publisher output
         ├──► GitHub Wiki publisher                     ├──► OAuth for Confluence
         ├──► Slack integration                         ├──► Notion publisher
         ├──► Notion publisher                          ├──► Google Docs publisher
         └──► Google/SharePoint publishers              └──► SharePoint publisher

Token usage tracking ──► Generation metadata in sidebar
                     └──► Usage-based pricing
                     └──► Analytics dashboard

Unit tests ──► Integration tests ──► CI/CD pipeline
```
