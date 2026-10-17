# Mandatory Project Rules

These rules MUST be followed in every session.

1. **Claude is only an orchestrator.** Every implementation (writing/modifying code, files, configuration) MUST be done through a subagent (Agent tool). More than 1 subagent may run in parallel as long as their tasks do not conflict (they do not touch the same files).
2. **Subagent model selection:**
   - `sonnet` (Sonnet 5.5) — regular/normal tasks.
   - `opus` (Opus 5.5) — very complex tasks.
   - `haiku` (Haiku 5.5) — writing README documentation.
3. **Taking initiative without confirmation is forbidden.** Do not take any action, make any change, or add anything beyond what was requested without explicit approval from the user first.
4. **Code and documentation MUST be written in English.** All code (variable/function names, comments, commit messages) and all documentation (README, docs, docstrings) MUST be written in English.

## Project Context

- This is an AI service called by a backend (internal service, not user-facing).
- Purpose: product discovery and recommendation. Uses AI to search across marketplaces, business websites, etc.; collects product images, checks/compares prices, and evaluates reviews to judge whether a seller/product is trusted.
- Architecture: parallel agents and multi-agent.
- Pipeline mapping:
  - discovery/search -> `app/services/discovery.py`, `app/services/browser.py`
  - dedup -> `app/services/dedup.py`
  - trust check -> `app/services/trust.py`
  - recommendation -> `app/services/recommender.py`
  - orchestration -> `app/services/pipeline.py`
  - LLM providers in `app/provider/` (custom, ollama, amd); config in `app/config/settings.py`
- LLM provider note: AMD Token Factory (OpenAI-compatible, base URL `https://developer.amd.com.cn/radeon/api/v1`). One API key is shared by the whole team: 30 RPM and 8 concurrent requests per key, so parallel agents must share a global rate/concurrency limit and back off on 429 (honor `Retry-After`).
