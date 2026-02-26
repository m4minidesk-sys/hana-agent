# Phase 2.5 Meeting Transcription — Implementation Spec

## Phase 2.5a: Audio Capture + Whisper Core

### New files:
- `src/yui/meeting/__init__.py`
- `src/yui/meeting/recorder.py` — Audio capture via ScreenCaptureKit/sounddevice
- `src/yui/meeting/transcriber.py` — mlx-whisper real-time transcription
- `src/yui/meeting/manager.py` — Meeting lifecycle (start/stop/status/list/search)
- `src/yui/meeting/models.py` — Meeting data models

### CLI integration (cli.py):
```
yui meeting start [--name "weekly standup"]
yui meeting stop
yui meeting status
yui meeting list
yui meeting search "keyword"
```

### Audio Capture (recorder.py):
- Primary: `sounddevice` InputStream (16kHz mono)
- System audio: ScreenCaptureKit via PyObjC (macOS 13+) or BlackHole fallback
- Mic mixing when `include_mic: true` in config
- Audio buffer: 5-second chunks → queue for Whisper

### Whisper Transcription (transcriber.py):
- Engine: mlx-whisper (Apple Silicon optimized)
- Model: large-v3-turbo (configurable)
- Language: auto-detect or config override
- VAD (Voice Activity Detection): skip silence chunks
- Output: timestamped text chunks → append to transcript file

### Storage:
```
~/.yui/meetings/
  <meeting_id>/
    transcript.md      # Full transcript (appended in real-time)
    audio.wav          # Raw audio (optional, config.save_audio)
    metadata.json      # Start time, duration, config used
    minutes.md         # Generated after stop (Phase 2.5b)
    analysis.md        # Real-time analysis log (Phase 2.5b)
```

### Config (config.yaml):
```yaml
meeting:
  audio:
    capture_method: screencapturekit
    include_mic: true
    sample_rate: 16000
    channels: 1
  whisper:
    engine: mlx
    model: large-v3-turbo
    language: auto
    chunk_seconds: 5
    vad_enabled: true
  output:
    transcript_dir: ~/.yui/meetings/
    format: markdown
    save_audio: false
  retention_days: 90
```

### Error handling:
- E-15: Screen Recording permission denied → clear guidance message
- E-16: Whisper model download fails → retry + fallback to smaller model
- E-17: Audio device not found → list available devices + guidance
- E-18: Meeting already recording → "meeting already in progress" error
- E-19: Meeting crash recovery → resume from last chunk if possible
- E-20: HuggingFace token missing (for gated models) → guidance

### Tests:
- Mock audio capture + Whisper transcription
- Meeting lifecycle (start → status → stop)
- Error scenarios (E-15 through E-20)
- Config validation

---

## Phase 2.5b: Bedrock Minutes Generation

### New files:
- `src/yui/meeting/minutes.py` — Minutes generation via Bedrock

### Features:
- Post-meeting: full transcript → Bedrock → structured minutes
- Real-time analysis (opt-in): 60s intervals, sliding 5-min window
- Budget guard: max_cost_per_meeting_usd (default $2)
- Slack notification with summary

### Minutes template:
```markdown
# Meeting Minutes — {date} {time}
## Summary
## Key Decisions
## Action Items
## Discussion Topics
## Open Questions
## Raw Transcript (link)
```

---

## Phase 2.5c: Menu Bar UI + Hotkeys

### New files:
- `src/yui/meeting/menubar.py` — rumps menu bar app
- `src/yui/meeting/hotkeys.py` — pynput global hotkeys
- `src/yui/meeting/ipc.py` — Unix socket IPC

### Features:
- Menu bar icon: 🎤 (idle) / 🔴 (recording) / ⏳ (generating)
- Global hotkeys: ⌘⇧R (toggle), ⌘⇧S (stop), ⌘⇧M (open minutes)
- Unix socket IPC between menu bar and daemon
- macOS notifications
- `yui menubar --install` for launchd
