#!/bin/bash
# Helper script to run tests with correct PYTHONPATH
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}/src:$PYTHONPATH"
python3 -m pytest "$@"
