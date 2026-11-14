#!/bin/zsh
# Native offline Mac application. Internet only needed to install packages once.
set -e
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  if command -v uv >/dev/null 2>&1; then
    echo 'Creating Python 3.12 virtual environment with uv...'
    uv venv --python 3.12 .venv
  elif command -v python3.12 >/dev/null 2>&1; then
    echo 'Creating Python 3.12 virtual environment...'
    python3.12 -m venv .venv || {
      echo 'Python ensurepip failed. Install uv with: brew install uv'
      read '?Press Return to close...'
      exit 1
    }
  else
    echo 'Install Python 3.12 and uv: brew install python@3.12 uv'
    read '?Press Return to close...'
    exit 1
  fi
fi
if ! .venv/bin/python -c 'import PySide6, pypdfium2, PIL' >/dev/null 2>&1; then
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python .venv/bin/python -r requirements.txt
  else
    .venv/bin/python -m pip install -r requirements.txt
  fi
fi
exec .venv/bin/python main.py
