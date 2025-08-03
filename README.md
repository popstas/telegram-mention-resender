# telegram-mention-resender

[![Coverage Status](https://coveralls.io/repos/github/popstas/telegram-mention-resender/badge.svg?branch=main)](https://coveralls.io/github/popstas/telegram-mention-resender?branch=main)

This project listens to mentions in specified Telegram chats and forwards
matching messages to a target chat.

# Features

- Listen folders, chats, channels
- Multiple instances for different chats, words and targets
- Each instance has target chat
- Forwarded messages include a link to the original message
- Prompt-triggered forwards include a short reason and quote from the message
- Reactions (👍/👎) forward messages to true/false positive chats once per message

## Setup

1. Install Python 3.10+ and create a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `config-example.yml` to `data/config.yml` and adjust the values:

- `api_id` – your Telegram API ID.
- `api_hash` – your Telegram API hash.
- `session` – path to your session file (default is `data/session`).
- `log_level` – logging level (default is `info`).
- `langfuse_public_key` – (optional) public key to enable Langfuse tracing.
- `langfuse_secret_key` – (optional) secret key for Langfuse.
- `langfuse_base_url` – (optional) custom Langfuse API URL.
- `ignore_usernames` – list of usernames to ignore when processing messages.
- `ignore_user_ids` – list of user IDs to ignore when processing messages.
- `instances` – list of monitoring instances. Each instance may contain
  `folders`, `chat_ids`, `entities`, `words`, `negative_words`, `ignore_words`, `target_chat`,
  `target_entity`, `folder_mute`, `false_positive_entity`, `true_positive_entity` and
  `no_forward_message`.

## Running

```bash
python -m src.main
```

The application will listen to new messages in all configured instances and
forward those containing any of the specified words to their target chats.

Statistics about processed messages are stored in `data/stats.json`. If you
have a file in the old format (without the `stats` section), it will be
automatically converted on startup using the new `Stats` structure.

## Generate evaluation datasets

Build evaluation tasks from collected true and false positive messages:

```bash
python -m src.generate_evals --suffix run1
```

Datasets and configuration files will be written to `data/evals/` with the
provided suffix.

## Run evaluations

After generating datasets, run them with [DeepEval](https://github.com/confident-ai/deepeval):

```bash
python -m src.run_deepeval --instance "Inst" --prompt "Prompt" --suffix run1
```

Use `--config` to provide a custom path to `config.yml` if needed.
The command exits with status code `1` if accuracy is below 80%.

To evaluate using OpenAI's Evals API:

```bash
python -m src.run_openai_evals --instance "Inst" --prompt "Prompt" --suffix run1
```

The runner respects any `model` or `temperature` options defined in the prompt
configuration and forces JSON responses that match the `EvaluateResult` schema.

### Langfuse tracing

Set `langfuse_public_key` and `langfuse_secret_key` in the config to enable
tracing with [Langfuse](https://langfuse.com). Optionally specify
`langfuse_base_url` if using a self-hosted instance.
The bot uses the Langfuse OpenAI integration, so all OpenAI calls are
automatically traced. Each request is tagged with the instance name and chat
name to make debugging easier.

#### Langfuse prompts

Prompts used for LLM evaluation can be stored in Langfuse. Set
`langfuse_name`, `langfuse_label`, `langfuse_version`, or `langfuse_type`
under a prompt entry in the config to fetch the text from Langfuse at startup.
When the local text differs from Langfuse, a new version is automatically
created and `langfuse_version` updated. The optional `config` field is forwarded
to Langfuse when creating versions. See `config-example.yml` for an example.
The compiled prompt is linked to Langfuse generations via `update_current_generation`.

## Development

It is built using [Telethon](https://github.com/LonamiWebs/Telethon).

Install pre-commit hooks:

```bash
pre-commit install
```

This will automatically run `black` and `isort` before each commit.
