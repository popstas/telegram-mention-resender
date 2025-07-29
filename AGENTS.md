## Rules on new features:
- Add tests for new features.
- Update README.md after features changes.
- If config type was changed, change config.ts generateConfig function.

## Rules before commit
- Always run `pre-commit --all-files` before commit.
- Update AGENTS.md when project structure changes.

# Repository Overview

This project forwards Telegram messages that match specific rules to a target chat. The application is implemented in **src/main.py** and uses [Telethon](https://github.com/LonamiWebs/Telethon). Configuration is stored in YAML under `data/config.yml` (see `config-example.yml` for reference).

```
├── src/        # application code
├── tests/      # pytest suite
├── README.md   # setup instructions
├── pyproject.toml / requirements.txt  # dependencies
└── Dockerfile
```

## Development hints

- Create a virtual environment, install dependencies and copy the example config:
  ```bash
  pip install -r requirements.txt
  cp config-example.yml data/config.yml
  ```
- Run the bot:
  ```bash
  python -m src.main
  ```
- Tests are written with **pytest** and **pytest-asyncio**. Run them with:
  ```bash
  pytest
  ```
- Pre-commit hooks apply **black** and **isort**. Install them once:
  ```bash
  pre-commit install
  ```

You can inspect `.github/workflows/test.yml` for the CI workflow. The default branch runs the same `pytest` command and reports coverage to Coveralls.

