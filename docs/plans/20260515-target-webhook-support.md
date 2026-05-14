# Add target_webhook support for forwarding matched messages

## Overview

Add a per-instance `target_webhook` configuration option that, when set, causes matched messages to be POSTed to an HTTP endpoint in addition to Telegram forwarding. Two payload formats are supported: a plain-text line and a JSON object. The first consumer is the instance named "Сотрудники привет", but the field is generic and any instance may use it.

## Context

- Impacted module: `src/config.py` (Instance dataclass and config loader), `src/app.py` (message handler that currently forwards to `target_chat` / `target_entity`), and the example config `config-example.yml`.
- Test coverage lives under `tests/` using pytest + pytest-asyncio; new functionality must be unit-tested without making real HTTP calls.
- A standalone manual helper script (port 8002) will live under `scripts/` for hands-on verification.
- Source: adopted from `data/webhooks-plan.md` (free-form brain dump).
- Per repository rules (CLAUDE.md): new features require tests, README updates, and `generateConfig` updates if config schema changes.

## Development Approach

- Testing approach: regular (write code, then add tests)
- Complete each task fully before moving to the next
- Update this plan when scope changes during implementation

## Testing Strategy

- Unit tests required for every code-changing Task
- Mock the HTTP client so tests do not make real network calls
- Run project tests after each Task before proceeding

## Technical Details

- New optional field on `Instance` in `src/config.py`:
  - `target_webhook: TargetWebhook | None = None`
  - Sub-shape: `url: str` (required), `format: Literal["text", "json"]` (default `"text"`)
- Update `config.py` `generateConfig` (or equivalent example-builder) so the generated example mirrors the schema.
- Wire delivery into the existing forward path in `src/app.py` (the block that currently appends to `destinations`). The webhook call should run alongside `target_chat` / `target_entity` delivery, not replace it.
- Payload formats:
  - `text`: a single line, e.g. `From: @user, Name: John Doe, Message: Hello, how are you?`
  - `json`: an object with at minimum `from_username`, `from_name`, `message_text`, plus useful metadata like `chat_id`, `message_id`, `message_url`, `timestamp`.
- HTTP client: use whichever async HTTP library is already a dependency (`aiohttp` or `httpx`). Use a short timeout (e.g., 10s) and log non-2xx responses without crashing the handler.
- Failures sending to the webhook must not block Telegram forwarding or raise out of the handler.

## Implementation Steps

### Task 1: Extend config schema for target_webhook

- [x] add `TargetWebhook` dataclass with `url: str` and `format: str = "text"` to `src/config.py`
- [x] add `target_webhook: TargetWebhook | None = None` field to the `Instance` dataclass
- [x] parse `target_webhook` in the config loader, including format validation (`text` or `json` only)
- [x] update `generateConfig` (or example-config builder) so `target_webhook` is reflected in the generated example
- [x] add `target_webhook` example under the `default` instance in `config-example.yml`
- [x] write tests for new functionality (config loading, defaults, invalid format rejection)
- [x] run project tests - must pass before next task

### Task 2: Implement webhook delivery in the message handler

- [x] add a `send_webhook(instance, message, context)` helper (text and json branches) — place near the forward block in `src/app.py` or in a new `src/webhook.py` if it grows
- [x] format `text` payload as a single line: `From: @user, Name: <full_name>, Message: <text>`
- [x] format `json` payload with `from_username`, `from_name`, `message_text`, `chat_id`, `message_id`, `message_url`, `timestamp`
- [x] call the helper from the forward branch in `src/app.py` when `inst.target_webhook` is set; do not skip existing `target_chat` / `target_entity` delivery
- [x] wrap the POST in try/except so a webhook failure logs but never raises out of the handler
- [x] use a short request timeout (10s) and log non-2xx responses
- [x] write tests for new functionality (text payload formatting, json payload formatting, network error is swallowed and logged)
- [x] run project tests - must pass before next task

### Task 3: Standalone test webhook server

- [x] add `scripts/test_webhook_server.py` — a tiny stdlib `http.server` (or `aiohttp.web`) listener on port 8002
- [x] log each incoming request's method, headers, and decoded body to stdout
- [x] respond with `200 OK` and a short JSON ack
- [x] document how to run it in the README (manual testing section)
- [x] write tests for new functionality (smoke test: launch server in a thread, POST text and json, assert it returns 200 and prints the body)
- [x] run project tests - must pass before next task

### Task 4: Documentation

- [ ] document `target_webhook` config (fields, formats, example) in `README.md`
- [ ] include a short example showing both `text` and `json` formats
- [ ] note that webhook delivery runs in addition to Telegram forwarding, and that failures are logged and swallowed
- [ ] mention `scripts/test_webhook_server.py` for local verification
- [ ] update `AGENTS.md` if any module layout changed (per project rule)
- [ ] run project tests - must pass before next task

### Task 5: Verify acceptance criteria

- [ ] verify all requirements from Overview are implemented (per-instance `target_webhook`, text and json formats, named instance keeps working)
- [ ] run full project test suite (`pytest`)
- [ ] run project linter — `pre-commit run --all-files` — all issues must be fixed

## Post-Completion

*Items requiring manual intervention - no checkboxes, informational only*

- Set `target_webhook` under the "Сотрудники привет" instance in `data/config.yml` (not in version control)
- Start `scripts/test_webhook_server.py` locally on port 8002 and trigger a matching Telegram message to confirm end-to-end delivery
