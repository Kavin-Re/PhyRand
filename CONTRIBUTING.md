# Contributing to PhyRand

Thanks for your interest. PhyRand: Zener-noise entropy source, not validated (STM32F401RE firmware), FastAPI key authority and file vault.

## Getting started

Firmware: open `firmware/` in STM32CubeIDE, build and flash the Nucleo-F401RE. Host side:

```
pip install -e ".[server]"            # or: pip install -r requirements.txt
pip install -r requirements-dev.txt   # test and lint tools
phyrand analyze data/random_whitened.bin
```

## Testing

No hardware is needed for the automated tests (they use a fake serial source):

```
python -m unittest discover -s tests -t .
node --test tests/js/fernet.test.mjs     # web client Fernet vectors
ruff check . && black --check .
```

CI (`.github/workflows/ci.yml`) runs lint, the unit tests on Python 3.10 to 3.12, the package install and CLI smoke test, and the Node tests. Firmware changes cannot be tested in CI and need a board.

## Pull requests

- Open an issue first for larger changes.
- Keep PRs focused and fill in the pull request template.
- Follow `.editorconfig` and match the style of surrounding code.
- Firmware changes must say which board they were tested on.

## Conduct

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
