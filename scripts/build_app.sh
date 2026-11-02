#!/bin/zsh
# Builds dist/Chess Bot.app, a double-click Mac app.
# macOS ties permissions to one exact build, so each new build must be granted again.
set -e
cd "$(dirname "$0")/.."

.venv/bin/pip install -q -r requirements.txt -r requirements-build.txt

# Python bots run inside the app, so bundle the modules they commonly import.
.venv/bin/pyinstaller --noconfirm --windowed \
  --name "Chess Bot" \
  --osx-bundle-identifier com.chessbot.app \
  --collect-submodules chess \
  --hidden-import random --hidden-import math --hidden-import statistics \
  --hidden-import itertools --hidden-import functools --hidden-import heapq \
  --hidden-import collections --hidden-import time --hidden-import json \
  run_app.py

echo "Built: dist/Chess Bot.app"
echo "If you've run an earlier build, clear its permissions before opening this one:"
echo "  tccutil reset ScreenCapture com.chessbot.app"
echo "  tccutil reset PostEvent com.chessbot.app"
echo "  tccutil reset Accessibility com.chessbot.app"
