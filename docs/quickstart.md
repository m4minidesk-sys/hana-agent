# Quick Start Guide

## Installation

```bash
# Create virtual environment
python3.13 -m venv .venv
source .venv/bin/activate

# Install yui
pip install -e .

# Setup configuration
mkdir -p ~/.yui/workspace
cp config.yaml.example ~/.yui/config.yaml
cp workspace/*.md ~/.yui/workspace/
```

## Configuration

Edit `~/.yui/config.yaml` to customize:

```yaml
model:
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
  region: us-east-1
  max_tokens: 4096

tools:
  shell:
    allowlist: [ls, cat, grep, find, python3]
    blocklist: ["rm -rf /", sudo]
    timeout_seconds: 30
  
  file:
    workspace_root: ~/.yui/workspace
```

## AWS Credentials

Ensure AWS credentials are configured:

```bash
# Option 1: AWS CLI
aws configure

# Option 2: Environment variables
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-east-1

# Option 3: ~/.aws/credentials
[default]
aws_access_key_id = your_key
aws_secret_access_key = your_secret
```

## Running

```bash
# Activate venv
source .venv/bin/activate

# Run REPL
python -m yui

# Or use the entry point (if installed)
yui
```

## Usage

```
You: List files in the current directory
Yui: [executes ls command and shows results]

You: Read the README.md file
Yui: [reads and displays file content]

You: ^D
Goodbye!
```

## Keyboard Shortcuts

- **Up/Down arrows**: Navigate command history
- **Ctrl+D**: Exit
- **Ctrl+C**: Cancel current input (continue REPL)

## Troubleshooting

### "No module named 'yui'"
```bash
# Reinstall in editable mode
pip install -e .
```

### "AWS credentials not configured"
```bash
# Configure AWS CLI
aws configure
```

### "Command blocked by security policy"
The command contains a blocked pattern. Check `tools.shell.blocklist` in config.yaml.

### "Command not in allowlist"
The command is not in the allowlist. Add it to `tools.shell.allowlist` in config.yaml.
