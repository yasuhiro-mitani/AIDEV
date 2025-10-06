# MP3 Length Tool

Utilities for trimming, rearranging, and stretching MP3 files with FFmpeg. The toolkit ships with a powerful command-line interface and a Tkinter-based GUI for visual editing.

## Features

- Keep one or multiple segments from the source audio and concatenate them in order.
- Stretch or shrink the combined result to a precise target duration using FFmpeg's `atempo` filter.
- Visual timeline overlays show saved segments, current selection, and running output/remaining duration totals.
- Independent playback controls let you set a preview start point and audition ranges with FFmpeg's `ffplay`.
- Optional dry-run mode that prints the underlying FFmpeg command.

## Requirements

- Python 3.9 or newer
- [FFmpeg](https://ffmpeg.org/) on your `PATH` (`ffmpeg`, `ffprobe`, and `ffplay` binaries)

## CLI usage

```powershell
python mp3_length_tool.py <input.mp3> <output.mp3> [options]
```

Key options:

- `-t, --target-duration` – seconds or `[[hh:]mm:]ss[.ms]`; when omitted, no tempo change is applied.
- `--segment START-END` – keep a segment; repeat to keep multiple. `START+LENGTH` is also accepted.
- `--trim-start`, `--trim-end`, `--trim-length` – legacy single-segment controls (cannot be combined with `--segment`).
- `--overwrite` – replace the output file if it exists.
- `--dry-run` – show the FFmpeg command without executing it.
- `--ffmpeg` / `--ffprobe` – point to custom binary locations.

### Examples

Keep two snippets and stitch them together:

```powershell
python mp3_length_tool.py talk.mp3 highlights.mp3 \
  --segment 00:00:30-00:00:50 \
  --segment 00:02:10+15 --overwrite
```

Trim the first 45 seconds, then stretch to an even minute:

```powershell
python mp3_length_tool.py intro.mp3 intro_long.mp3 --trim-length 45 -t 60
```

Dry-run a complex cut to inspect the FFmpeg command:

```powershell
python mp3_length_tool.py rehearsal.mp3 edit.mp3 \
  --segment 15-30 --segment 45-60 --dry-run
```

## GUI usage

```powershell
python mp3_length_tool_gui.py
```

- Pick input/output MP3 files, then drag the handles on the timeline to define a range. Right-click (??? Ctrl+????) ????????????????
- Use ???? to store the current range as a segment; reorder or delete entries from the list when building composites.
- The numeric fields stay in sync with the timeline for precise adjustments, and the summary keeps ??/?? ????????????????
- Adjust ?????? ? ????????? ???????????????????????????????
- Enable the dry-run checkbox to review the FFmpeg command before execution.
- The GUI relies on `ffprobe` to load the full duration; install FFmpeg and ensure `ffmpeg`, `ffprobe`, and `ffplay` are on `PATH`.

## How it works

The CLI probes the input duration with `ffprobe`, applies one or more `atrim` filters, chains the trimmed clips through `concat`, and optionally applies an `atempo` chain before encoding with `libmp3lame`. The GUI reuses the same processing logic while providing timeline editing, segment management, and preview playback.

## Limitations

- FFmpeg must be installed separately; the scripts do not bundle binaries.
- Time stretching quality depends on FFmpeg's implementation and may introduce artifacts for extreme changes.
- Non-audio metadata (artwork, ID3 tags) is not preserved in the output file.
