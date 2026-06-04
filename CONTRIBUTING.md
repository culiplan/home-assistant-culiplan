# Contributing to Culiplan for Home Assistant

This is a private repo — contributions are by invite only. The guidelines below
are for the core team.

## Development environment

```bash
# 1. Clone and enter the repo
git clone https://github.com/culiplan/home-assistant-culiplan.git
cd home-assistant-culiplan

# 2. Create a virtual environment (Python 3.12+)
python -m venv .venv && source .venv/bin/activate

# 3. Install dev dependencies (pick one)
pip install uv && uv pip install -r requirements_test.txt
# or: pip install pytest pytest-homeassistant-custom-component mypy
```

## Running tests

```bash
# Unit tests
pytest tests/ -v

# Type checking (must stay at 0 errors)
mypy --strict custom_components/culiplan

# Single file
pytest tests/test_coordinator.py -v
```

`pytest-homeassistant-custom-component` provides the `hass` fixture and all
HA stubs. No live HA instance needed.

## Branching model

Trunk-based development on `main`. No long-lived feature branches. All
commits go to `main` directly. Releases are tagged (`v0.2.0`, `v0.3.0`, …)
from `main` HEAD once CI is green.

## Code style

- Python: follow HA Core conventions (PEP 8, `from __future__ import annotations`).
- All new modules must pass `mypy --strict`.
- Log via `_LOGGER = logging.getLogger(__name__)`, never `print()`.
- Tests go in `tests/` with the `pytest_homeassistant_custom_component` fixture.
