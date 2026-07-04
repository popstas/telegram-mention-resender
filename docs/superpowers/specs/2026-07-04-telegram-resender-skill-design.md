# Design: `telegram-resender` config-management skill

**Date:** 2026-07-04
**Status:** Approved (design)

## Purpose

An agent skill that manages this project's `data/config.yml` — specifically the
`instances` list — through a step-by-step interview. It:

1. Adds a new monitoring instance via `AskUserQuestion`, asking essentials first
   and offering advanced options.
2. Edits or removes existing instances.
3. Explains what any instance config option means or does.

The skill is instructions for the agent (Claude), not a runtime feature of the
bot. The agent reads/edits `data/config.yml` with its own file tools and
validates using the project's own config loader.

## Type & location

- **Type:** technique (interactive wizard) + reference (per-option docs).
- **Repo-tracked source of truth:** `skills/telegram-resender/`.
- **Discovery:** Claude Code auto-discovers skills only under `.claude/skills/`,
  not a bare repo-root `skills/`. A committed symlink bridges them. `.claude/`
  is **not** gitignored in this repo, so the symlink commits without any
  gitignore change.

```
skills/telegram-resender/
  SKILL.md              # wizard flow + validation + quick-reference table
  instance-options.md   # full per-option reference (heavy reference, kept out of SKILL.md)
.claude/skills/telegram-resender -> ../../skills/telegram-resender   # committed discovery symlink
```

## Frontmatter

- `name: telegram-resender`
- `description` (triggering conditions only, per SDO — no workflow summary):
  > Use when adding, editing, or removing a monitoring instance in the
  > telegram-resender `data/config.yml`, or when the user asks what an instance
  > config option means or does.

## SKILL.md flow

1. **Locate & read** `data/config.yml` (honor the `CONFIG_PATH` env override,
   matching `src/config.py`). List existing instance names for the user.
2. **Branch:** add / edit / remove / explain-an-option.
3. **Add-instance wizard** (`AskUserQuestion`, essentials first):
   - **Round A — identity + sources:** `name`; sources via `entities`
     (t.me links) and/or `folders`.
   - **Round B — matching:** `words` (trigger terms), `negative_words`,
     `ignore_words`; explain the AND/OR semantics.
   - **Round C — target:** at least one of `target_chat` / `target_entity` /
     `target_webhook`.
   - **Then one question:** "Configure advanced options?" — if yes, grouped
     rounds for:
     - forwarding behavior: `once_per_chat` (+`reset_hour`), `debounce_ms`
       (+`cancel_on_owner_reply`)
     - message preface: `no_forward_message` / `message_template` /
       `forward_message` flags (`show_trigger`, `show_source`, `prefix`,
       `suffix`)
     - AI `prompts` (`name`, `prompt`, `threshold`, optional Langfuse keys)
     - folder automation: `folder_mute`, `folder_add_topic`
     - misc: `ignore_usernames_override`, `false_positive_entity`,
       `true_positive_entity`, `chat_ids`
4. **Edit-instance flow:** pick instance → pick field(s) → new value →
   surgical Edit.
5. **Remove-instance flow:** pick instance → confirm → delete its YAML block.
6. **Write back** via the Edit tool (not a YAML round-trip) to preserve
   comments and ordering. A new instance is appended in the block style of
   `config-example.yml`. This avoids adding a `ruamel.yaml` dependency.
7. **Validate** with the project's own loader, no bot restart:
   ```
   python -c "import asyncio; from src.config import load_config, load_instances; asyncio.run(load_instances(load_config()))"
   ```
   Reports nothing on success; raises on validation error. On failure, fix or
   revert. Tell the user to restart the bot themselves.

## instance-options.md

One entry per instance option, mirroring `src/config.py`:

- key, type, default, required?
- validation rules (e.g. `reset_hour` 0–23; `debounce_ms` ≥ 0 int;
  `target_webhook.format` ∈ {text, json}; `message_template` placeholders
  `{trigger} {source} {username} {name} {chat}`; `forward_message.*` types;
  `cancel_on_owner_reply` bool)
- what it does
- an example value
- the wizard question to ask for it

This satisfies the "describe each config option" requirement and is the source
the "explain-an-option" branch reads from.

## Validation & apply decisions (locked)

- Edit in place, preserve comments.
- Validate by loading via `load_instances`; do **not** restart the bot.
- Wizard: essentials, then offer advanced.

## Build method

Built TDD-style per the `writing-skills` skill, adapted for a
technique/reference skill:

1. **RED (baseline):** dispatch a subagent to add and edit an instance
   *without* the skill; record what it gets wrong (invalid values, missed
   validation, unknown/omitted options).
2. **GREEN:** write `SKILL.md` + `instance-options.md` addressing those gaps;
   verify a subagent can add an instance, edit one, and correctly explain an
   option using the skill.
3. **REFACTOR:** close gaps found in testing; re-verify.

Then create the committed symlink and validate discovery.

## Out of scope

- Managing top-level config keys (`api_id`, `openai_*`, `langfuse_*`, `proxy_url`)
  beyond what an instance needs. The skill focuses on `instances`.
- Restarting or deploying the bot.
- Runtime changes to the bot itself (project repo is read-only per README;
  this skill only edits `data/config.yml` and adds skill files).
