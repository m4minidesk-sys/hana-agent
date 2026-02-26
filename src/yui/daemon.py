"""macOS launchd daemon management."""

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_plist(config: dict) -> str:
    """Generate launchd plist XML for Yui daemon (AC-23).
    
    Args:
        config: Runtime configuration dictionary.
        
    Returns:
        plist XML string.
    """
    label = config["runtime"]["daemon"]["launchd_label"]
    python_path = sys.executable
    yui_module = Path(__file__).parent.parent  # src/yui -> src
    
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>-m</string>
        <string>yui</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>ThrottleInterval</key>
    <integer>5</integer>
    <key>StandardOutPath</key>
    <string>/tmp/yui.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/yui.err</string>
</dict>
</plist>
"""
    return plist


def daemon_start(config: dict) -> None:
    """Start Yui as launchd daemon (AC-23, AC-24).
    
    Args:
        config: Runtime configuration dictionary.
    """
    label = config["runtime"]["daemon"]["launchd_label"]
    plist_path = Path(f"~/Library/LaunchAgents/{label}.plist").expanduser()
    
    # Generate and write plist
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_content = generate_plist(config)
    plist_path.write_text(plist_content, encoding="utf-8")
    logger.info("Generated plist at %s", plist_path)
    
    # Load with launchctl
    try:
        subprocess.run(["launchctl", "load", str(plist_path)], check=True, capture_output=True)
        print(f"[yui] Daemon started: {label}")
        print(f"[yui] Logs: /tmp/yui.log, /tmp/yui.err")
    except subprocess.CalledProcessError as e:
        print(f"[yui] Failed to start daemon: {e.stderr.decode()}", file=sys.stderr)
        sys.exit(1)


def daemon_stop(config: dict) -> None:
    """Stop Yui daemon (AC-25).
    
    Args:
        config: Runtime configuration dictionary.
    """
    label = config["runtime"]["daemon"]["launchd_label"]
    plist_path = Path(f"~/Library/LaunchAgents/{label}.plist").expanduser()
    
    try:
        subprocess.run(["launchctl", "unload", str(plist_path)], check=True, capture_output=True)
        print(f"[yui] Daemon stopped: {label}")
    except subprocess.CalledProcessError as e:
        print(f"[yui] Failed to stop daemon: {e.stderr.decode()}", file=sys.stderr)
        sys.exit(1)


def daemon_status(config: dict) -> None:
    """Check Yui daemon status (AC-25).
    
    Args:
        config: Runtime configuration dictionary.
    """
    label = config["runtime"]["daemon"]["launchd_label"]
    
    try:
        result = subprocess.run(
            ["launchctl", "list", label],
            check=False,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"[yui] Daemon running: {label}")
            print(result.stdout)
        else:
            print(f"[yui] Daemon not running: {label}")
    except Exception as e:
        print(f"[yui] Failed to check status: {e}", file=sys.stderr)
        sys.exit(1)
