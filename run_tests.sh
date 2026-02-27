#!/bin/bash
# Helper script to run tests with correct PYTHONPATH
export PYTHONPATH=/Users/m4mac/yui-agent/src:$PYTHONPATH
python3 -m pytest "$@"
