#!/usr/bin/env python3
"""
Flexible MP3 trimming and stretching helper built on top of FFmpeg.

Supports multiple trimmed segments that are concatenated together and
optionally time-stretched to reach a target duration.
"""

from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

TOLERANCE = 1e-3


@dataclass(frozen=True)
class SegmentSpec:
    """Definition of a segment to keep from the source audio."""

    start: float
    end: float


@dataclass(frozen=True)
class SegmentResult:
    """Details about a processed segment."""

    start: float
    end: float
    duration: float


@dataclass
class ProcessResult:
    """Summary returned after running ``process_audio``."""

    input_path: Path
    output_path: Path
    total_input_duration: float
    segments: List[SegmentResult]
    total_segment_duration: float
    target_duration: Optional[float]
    new_duration: Optional[float]
    tempo_factor: float
    ffmpeg_command: List[str]
    dry_run: bool


def parse_duration(value: str, *, allow_zero: bool = False) -> float:
    """Parse a duration string into seconds."""

    value = value.strip()
    if not value:
        raise ValueError("Duration value cannot be empty.")

    try:
        seconds = float(value)
    except ValueError:
        parts = value.split(":")
        if len(parts) > 3:
            raise ValueError(f"Invalid duration format: {value}")
        parsed: List[float] = []
        for index, part in enumerate(parts):
            part = part.strip()
            if not part:
                raise ValueError(f"Invalid duration segment: {value}")
            if index == len(parts) - 1:
                parsed.append(float(part))
            else:
                if "." in part:
                    raise ValueError("Only the seconds segment may contain decimals.")
                parsed.append(float(int(part)))
        seconds = 0.0
        multiplier = 1.0
        for segment in reversed(parsed):
            seconds += segment * multiplier
            multiplier *= 60.0

    if seconds < 0:
        raise ValueError("Duration must be non-negative.")
    if not allow_zero and seconds == 0:
        raise ValueError("Duration must be positive.")
    return seconds


def parse_optional_duration(value: Optional[str], *, allow_zero: bool = False) -> Optional[float]:
    """Parse an optional duration string."""

    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return parse_duration(value, allow_zero=allow_zero)


def parse_segment_spec(text: str) -> SegmentSpec:
    """Parse ``START-END`` or ``START+LENGTH`` into a ``SegmentSpec``."""

    text = text.strip()
    if not text:
        raise ValueError("Segment value cannot be empty.")

    if "+" in text:
        start_text, length_text = text.split("+", 1)
        start = parse_duration(start_text, allow_zero=True)
        length = parse_duration(length_text, allow_zero=False)
        end = start + length
    elif "-" in text:
        start_text, end_text = text.split("-", 1)
        start = parse_duration(start_text, allow_zero=True)
        end = parse_duration(end_text, allow_zero=True)
    else:
        raise ValueError(
            "Segment must be formatted as START-END or START+LENGTH"
        )

    if end <= start:
        raise ValueError("Segment end must be greater than start.")

    return SegmentSpec(start=start, end=end)


def resolve_executable(candidate: str) -> str:
    """Return an absolute path to an executable, if it exists."""

    path_candidate = Path(candidate).expanduser()
    if path_candidate.is_file():
        return str(path_candidate.resolve())
    resolved = shutil.which(candidate)
    if resolved:
        return resolved
    raise FileNotFoundError(f"Unable to locate executable: {candidate}")


def probe_duration(source: Path, ffprobe: str) -> float:
    """Return the duration of an audio file in seconds using ``ffprobe``."""

    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(source),
    ]
    try:
        completed = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"ffprobe not found ({ffprobe}).") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffprobe failed: {exc.stderr.strip()}") from exc

    output = completed.stdout.strip()
    try:
        return float(output)
    except ValueError as exc:
        raise RuntimeError(
            f"Unable to parse duration from ffprobe output: {output}"
        ) from exc


def build_atempo_chain(tempo: float) -> List[float]:
    """Create a list of ``atempo`` factors that multiply to ``tempo``."""

    if tempo <= 0:
        raise ValueError("Tempo factor must be positive.")

    if abs(tempo - 1.0) <= TOLERANCE:
        return [1.0]

    factors: List[float] = []
    remaining = tempo
    while remaining > 2.0 + TOLERANCE:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5 - TOLERANCE:
        factors.append(0.5)
        remaining /= 0.5
    if abs(remaining - 1.0) > TOLERANCE:
        factors.append(remaining)
    return factors or [1.0]


def format_duration(seconds: float) -> str:
    """Return a human readable duration string."""

    seconds = max(seconds, 0.0)
    whole = int(seconds)
    fractional = seconds - whole
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        base = f"{hours:d}:{minutes:02d}:{secs:02d}"
    else:
        base = f"{minutes:d}:{secs:02d}"
    if fractional >= 1e-3:
        base += f".{int(round(fractional * 1000)):03d}"
    return base


def format_command(cmd: Sequence[str]) -> str:
    """Return a printable shell command."""

    return " ".join(shlex.quote(part) for part in cmd)


def _normalise_segments(
    segments: Iterable[SegmentSpec],
    *,
    total_duration: float,
) -> List[SegmentResult]:
    """Clamp and validate segment definitions."""

    results: List[SegmentResult] = []
    for spec in segments:
        start = max(0.0, spec.start)
        end = max(start, min(spec.end, total_duration))
        if end - start <= TOLERANCE:
            raise ValueError(
                "Segment duration must be greater than zero after clamping."
            )
        results.append(
            SegmentResult(start=start, end=end, duration=end - start)
        )
    if not results:
        raise ValueError("At least one segment must be provided.")
    return results


def process_audio(
    input_path: Path,
    output_path: Path,
    *,
    target_duration: Optional[float],
    segments: Optional[Iterable[SegmentSpec]] = None,
    trim_start: float = 0.0,
    trim_end: Optional[float] = None,
    trim_length: Optional[float] = None,
    overwrite: bool = False,
    dry_run: bool = False,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
) -> ProcessResult:
    """Run the audio processing pipeline and return a summary."""

    input_path = Path(input_path).expanduser()
    output_path = Path(output_path).expanduser()

    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")

    try:
        if input_path.resolve() == output_path.resolve():
            raise ValueError("Input and output paths must be different.")
    except FileNotFoundError:
        # ``output_path`` does not exist yet; safe to ignore.
        pass

    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output file already exists: {output_path} (use --overwrite to replace it)"
        )

    parent_dir = output_path.parent
    if not parent_dir.exists():
        if dry_run:
            raise FileNotFoundError(
                f"Output directory does not exist: {parent_dir}"
            )
        parent_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg_path = resolve_executable(ffmpeg)
    ffprobe_path = resolve_executable(ffprobe)

    total_duration = probe_duration(input_path, ffprobe_path)

    segment_specs: List[SegmentSpec] = []
    if segments is not None:
        segment_specs = list(segments)
    else:
        start = max(0.0, trim_start)
        if trim_length is not None:
            if trim_length <= 0:
                raise ValueError("Trim length must be positive.")
            end = start + trim_length
        elif trim_end is not None:
            end = max(start, trim_end)
        else:
            end = total_duration
        segment_specs = [SegmentSpec(start=start, end=end)]

    normalised_segments = _normalise_segments(segment_specs, total_duration=total_duration)

    total_segment_duration = sum(segment.duration for segment in normalised_segments)
    if total_segment_duration <= TOLERANCE:
        raise ValueError("Total segment duration must be positive.")

    if target_duration is not None:
        if target_duration <= 0:
            raise ValueError("Target duration must be positive.")
        tempo_factor = total_segment_duration / target_duration
        if tempo_factor <= 0:
            raise ValueError("Computed tempo factor is invalid.")
    else:
        tempo_factor = 1.0

    atempo_chain = build_atempo_chain(tempo_factor)
    apply_tempo = target_duration is not None and (
        len(atempo_chain) > 1 or abs(atempo_chain[0] - 1.0) > TOLERANCE
    )

    filter_parts: List[str] = []
    labels: List[str] = []
    for index, segment in enumerate(normalised_segments):
        label = f"s{index}"
        filter_parts.append(
            f"[0:a]atrim=start={segment.start:.6f}:end={segment.end:.6f},"
            f"asetpts=PTS-STARTPTS[{label}]"
        )
        labels.append(f"[{label}]")

    concat_label = "aconcat"
    concat_part = "".join(labels) + f"concat=n={len(labels)}:v=0:a=1[{concat_label}]"
    if apply_tempo:
        filter_parts.append(concat_part)
        current_label = concat_label
        for idx, factor in enumerate(atempo_chain):
            is_last = idx == len(atempo_chain) - 1
            next_label = "out" if is_last else f"tempo{idx}"
            filter_parts.append(
                f"[{current_label}]atempo={factor:.6f}[{next_label}]"
            )
            current_label = next_label
    else:
        filter_parts.append(
            "".join(labels) + f"concat=n={len(labels)}:v=0:a=1[out]"
        )

    filter_complex = ";".join(filter_parts)

    ffmpeg_cmd = [
        ffmpeg_path,
        "-hide_banner",
        "-y",
        "-i",
        str(input_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[out]",
        "-vn",
        "-c:a",
        "libmp3lame",
        str(output_path),
    ]

    if dry_run:
        return ProcessResult(
            input_path=input_path,
            output_path=output_path,
            total_input_duration=total_duration,
            segments=normalised_segments,
            total_segment_duration=total_segment_duration,
            target_duration=target_duration,
            new_duration=None,
            tempo_factor=tempo_factor,
            ffmpeg_command=ffmpeg_cmd,
            dry_run=True,
        )

    try:
        subprocess.run(ffmpeg_cmd, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg failed with exit code {exc.returncode}") from exc
    except FileNotFoundError:
        raise ValueError(f"Unable to locate ffmpeg executable: {ffmpeg_path}")

    try:
        new_duration = probe_duration(output_path, ffprobe_path)
    except RuntimeError as exc:
        sys.stderr.write(f"Warning: {exc}\n")
        new_duration = None

    return ProcessResult(
        input_path=input_path,
        output_path=output_path,
        total_input_duration=total_duration,
        segments=normalised_segments,
        total_segment_duration=total_segment_duration,
        target_duration=target_duration,
        new_duration=new_duration,
        tempo_factor=tempo_factor,
        ffmpeg_command=ffmpeg_cmd,
        dry_run=False,
    )


def _print_result(result: ProcessResult) -> None:
    """Pretty-print a ``ProcessResult`` to stdout."""

    print(
        f"Input duration:    {format_duration(result.total_input_duration)} "
        f"({result.total_input_duration:.3f} s)"
    )

    print("Segments:")
    for idx, segment in enumerate(result.segments, 1):
        print(
            f"  {idx:>2}: {format_duration(segment.start)}"
            f" -> {format_duration(segment.end)}"
            f" ({segment.duration:.3f} s)"
        )

    print(
        f"Total kept:       {format_duration(result.total_segment_duration)} "
        f"({result.total_segment_duration:.3f} s)"
    )

    if result.target_duration is not None:
        print(
            f"Target duration:  {format_duration(result.target_duration)} "
            f"({result.target_duration:.3f} s)"
        )
        print(f"Tempo factor:     {result.tempo_factor:.6f}x")
    else:
        print("Tempo factor:     1.000000x (no speed change)")

    if result.new_duration is not None:
        reference = (
            result.target_duration
            if result.target_duration is not None
            else result.total_segment_duration
        )
        delta = result.new_duration - reference if reference is not None else 0.0
        print(
            f"Output duration:  {format_duration(result.new_duration)} "
            f"({result.new_duration:.3f} s)"
        )
        if reference is not None:
            print(f"Difference:       {delta:+.3f} s")
    else:
        print("Output duration:  <unknown>")

    print(f"Output written to: {result.output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Trim one or more segments from an MP3, concatenate them, and optionally "
            "stretch the result to a target duration using FFmpeg."
        )
    )
    parser.add_argument("input", type=Path, help="Path to the source MP3 file")
    parser.add_argument("output", type=Path, help="Where to write the processed MP3")
    parser.add_argument(
        "-t",
        "--target-duration",
        help="Target duration (seconds or [[hh:]mm:]ss[.ms]); optional",
    )
    parser.add_argument(
        "--trim-start",
        help="Optional start position for trimming (seconds or [[hh:]mm:]ss[.ms])",
    )
    parser.add_argument(
        "--trim-end",
        help="Optional end position for trimming (seconds or [[hh:]mm:]ss[.ms])",
    )
    parser.add_argument(
        "--trim-length",
        help="Optional length of the trimmed segment starting at --trim-start",
    )
    parser.add_argument(
        "--segment",
        action="append",
        metavar="START-END|START+LENGTH",
        help=(
            "Keep an additional segment; repeat for multiple segments. "
            "Times accept seconds or [[hh:]mm:]ss[.ms]."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output file if it already exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the ffmpeg command without executing it",
    )
    parser.add_argument(
        "--ffmpeg",
        default="ffmpeg",
        help="Path to the ffmpeg executable (default: %(default)s)",
    )
    parser.add_argument(
        "--ffprobe",
        default="ffprobe",
        help="Path to the ffprobe executable (default: %(default)s)",
    )

    args = parser.parse_args()

    target_seconds = parse_optional_duration(args.target_duration)

    segment_specs: Optional[List[SegmentSpec]] = None
    if args.segment:
        segment_specs = []
        for entry in args.segment:
            try:
                segment_specs.append(parse_segment_spec(entry))
            except ValueError as exc:
                parser.error(f"Invalid --segment value '{entry}': {exc}")

        if args.trim_start or args.trim_end or args.trim_length:
            parser.error(
                "Do not combine --segment with --trim-start/--trim-end/--trim-length"
            )

    try:
        trim_start = parse_optional_duration(args.trim_start, allow_zero=True)
    except ValueError as exc:
        parser.error(f"Invalid --trim-start value: {exc}")
    if trim_start is None:
        trim_start = 0.0

    try:
        trim_end = parse_optional_duration(args.trim_end, allow_zero=True)
    except ValueError as exc:
        parser.error(f"Invalid --trim-end value: {exc}")

    try:
        trim_length = parse_optional_duration(args.trim_length, allow_zero=False)
    except ValueError as exc:
        parser.error(f"Invalid --trim-length value: {exc}")

    will_trim = bool(segment_specs) or (
        trim_start > TOLERANCE
        or trim_end is not None
        or trim_length is not None
    )

    if target_seconds is None and not will_trim:
        parser.error(
            "Nothing to do: specify --target-duration and/or trimming options."
        )

    try:
        result = process_audio(
            input_path=args.input,
            output_path=args.output,
            target_duration=target_seconds,
            segments=segment_specs,
            trim_start=trim_start,
            trim_end=trim_end,
            trim_length=trim_length,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
            ffmpeg=args.ffmpeg,
            ffprobe=args.ffprobe,
        )
    except FileNotFoundError as exc:
        parser.error(str(exc))
    except FileExistsError as exc:
        parser.error(str(exc))
    except ValueError as exc:
        parser.error(str(exc))
    except RuntimeError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    if result.dry_run:
        print(format_command(result.ffmpeg_command))
        return 0

    _print_result(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
