"""Shared pytest fixtures — put the repo root on sys.path so `core`,
`backends`, and `aisubs_whisper` import as the plugin does from VLC."""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Tests are dev-only; never let a foreign PYTHONPATH (e.g. a desktop-agent
# terminal export) shadow packages inside the venv under test.
os.environ.pop("PYTHONPATH", None)