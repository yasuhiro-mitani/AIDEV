
#!/usr/bin/env python3
"""
Tkinter GUI frontend for the MP3 length tool with multi-segment editing.

Allows selecting one or more segments on a timeline, previewing them,
reordering, and exporting through the shared processing pipeline.
"""
from __future__ import annotations

import subprocess
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from mp3_length_tool import (
    TOLERANCE,
    ProcessResult,
    SegmentSpec,
    format_command,
    format_duration,
    parse_duration,
    process_audio,
    probe_duration,
    resolve_executable,
)

DEFAULT_PREVIEW_SECONDS = 15.0


@dataclass(frozen=True)
class ProcessRequest:
    """Immutable data bundle capturing a processing run request."""

    input_path: Path
    output_path: Path
    target_duration: Optional[float]
    segments: tuple[SegmentSpec, ...]
    overwrite: bool
    dry_run: bool

def _parse_optional(value: str, *, allow_zero: bool, default: Optional[float]) -> Optional[float]:
    text = value.strip()
    if not text:
        return default
    return parse_duration(text, allow_zero=allow_zero)


class Mp3LengthToolApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("MP3 長さ調整ツール")
        self.resizable(False, False)

        self.total_duration: Optional[float] = None
        self.trim_start_seconds: float = 0.0
        self.trim_end_seconds: float = 0.0
        self.trim_end_explicit: bool = False

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.target_var = tk.StringVar()
        self.trim_start_var = tk.StringVar()
        self.trim_end_var = tk.StringVar()
        self.trim_length_var = tk.StringVar()
        self.overwrite_var = tk.BooleanVar(value=False)
        self.dry_run_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="準備完了")
        self.segment_info_var = tk.StringVar(value="セグメント 0 件")
        self.summary_var = tk.StringVar(value="出力 0.000 秒 / 残り 0.000 秒")

        self.timeline_width = 420
        self.timeline_height = 56
        self.timeline_padding = 18
        self.timeline_handle_half = 6
        self._active_handle: Optional[str] = None

        self.play_process: Optional[subprocess.Popen] = None
        self.playback_thread: Optional[threading.Thread] = None

        self.segments: List[SegmentSpec] = []

        self.playback_start_seconds: float = 0.0
        self.playback_start_var = tk.StringVar(value=format_duration(0.0))
        self.preview_length_var = tk.StringVar(value="15")

        self.segment_marker_ids: List[int] = []
        self.playback_marker_id: Optional[int] = None
        self.playback_marker_text_id: Optional[int] = None

        self._build_ui()
        self.processing_thread: Optional[threading.Thread] = None
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._set_trim_range(0.0, None, end_explicit=False)
        self._set_playback_start(0.0, update_entry=False, update_marker=True)
    def _build_ui(self) -> None:
        padding = {"padx": 10, "pady": 5}
        frame = ttk.Frame(self, padding=10)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)

        row = 0
        row = self._build_file_inputs(frame, padding, row)
        row = self._build_trim_section(frame, row)
        row = self._build_segments_section(frame, row)
        row = self._build_options_section(frame, row)
        self._build_status_bar(frame, row)

    def _build_file_inputs(self, frame: ttk.Frame, padding: dict[str, int], row: int) -> int:
        ttk.Label(frame, text="入力ファイル").grid(row=row, column=0, sticky="w", **padding)
        ttk.Entry(frame, textvariable=self.input_var, width=48).grid(row=row, column=1, sticky="ew", **padding)
        ttk.Button(frame, text="参照...", command=self._select_input).grid(row=row, column=2, **padding)

        row += 1
        ttk.Label(frame, text="出力ファイル").grid(row=row, column=0, sticky="w", **padding)
        ttk.Entry(frame, textvariable=self.output_var, width=48).grid(row=row, column=1, sticky="ew", **padding)
        ttk.Button(frame, text="参照...", command=self._select_output).grid(row=row, column=2, **padding)

        row += 1
        ttk.Label(frame, text="目標時間 (任意)").grid(row=row, column=0, sticky="w", **padding)
        ttk.Entry(frame, textvariable=self.target_var, width=20).grid(row=row, column=1, sticky="w", **padding)
        return row + 1

    def _build_trim_section(self, frame: ttk.Frame, row: int) -> int:
        trim_frame = ttk.LabelFrame(frame, text="トリミング", padding=10)
        trim_frame.grid(row=row, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 10))
        for column in range(6):
            trim_frame.columnconfigure(column, weight=1 if column % 2 else 0)

        self.duration_label = ttk.Label(trim_frame, text="全体長: 未取得")
        self.duration_label.grid(row=0, column=0, columnspan=6, sticky="w")

        bg_color = self._resolve_background("TLabelframe", self.cget("background"))
        self.timeline_canvas = tk.Canvas(
            trim_frame,
            width=self.timeline_width,
            height=self.timeline_height,
            highlightthickness=0,
            relief="flat",
            bg=bg_color,
        )
        self.timeline_canvas.grid(row=1, column=0, columnspan=6, sticky="ew", pady=(5, 10))
        self.timeline_canvas.bind("<ButtonPress-1>", self._on_timeline_press)
        self.timeline_canvas.bind("<B1-Motion>", self._on_timeline_drag)
        self.timeline_canvas.bind("<ButtonRelease-1>", self._on_timeline_release)
        self.timeline_canvas.bind("<ButtonPress-3>", self._on_timeline_set_playback)
        self._init_timeline_graphics()

        ttk.Label(trim_frame, text="開始").grid(row=2, column=0, sticky="w")
        start_entry = ttk.Entry(trim_frame, textvariable=self.trim_start_var, width=16)
        start_entry.grid(row=2, column=1, sticky="ew", padx=5)
        start_entry.bind("<FocusOut>", self._on_start_entry_change)
        start_entry.bind("<Return>", self._on_start_entry_change)

        ttk.Label(trim_frame, text="終了").grid(row=2, column=2, sticky="w")
        end_entry = ttk.Entry(trim_frame, textvariable=self.trim_end_var, width=16)
        end_entry.grid(row=2, column=3, sticky="ew", padx=5)
        end_entry.bind("<FocusOut>", self._on_end_entry_change)
        end_entry.bind("<Return>", self._on_end_entry_change)

        ttk.Label(trim_frame, text="長さ").grid(row=2, column=4, sticky="w")
        length_entry = ttk.Entry(trim_frame, textvariable=self.trim_length_var, width=16)
        length_entry.grid(row=2, column=5, sticky="ew", padx=5)
        length_entry.bind("<FocusOut>", self._on_trim_length_entry)
        length_entry.bind("<Return>", self._on_trim_length_entry)

        summary_frame = ttk.Frame(trim_frame)
        summary_frame.grid(row=3, column=0, columnspan=6, sticky="ew")
        ttk.Label(summary_frame, textvariable=self.summary_var).grid(row=0, column=0, sticky="w")

        playback_frame = ttk.Frame(trim_frame)
        playback_frame.grid(row=4, column=0, columnspan=6, sticky="ew", pady=(6, 0))
        playback_frame.columnconfigure(1, weight=1)
        playback_frame.columnconfigure(4, weight=1)

        ttk.Label(playback_frame, text="再生開始").grid(row=0, column=0, sticky="w")
        playback_entry = ttk.Entry(playback_frame, textvariable=self.playback_start_var, width=16)
        playback_entry.grid(row=0, column=1, sticky="w", padx=(5, 10))
        playback_entry.bind("<FocusOut>", self._on_playback_start_change)
        playback_entry.bind("<Return>", self._on_playback_start_change)

        ttk.Button(playback_frame, text="選択開始を適用", command=self._set_playback_from_selection).grid(
            row=0, column=2, sticky="w", padx=(0, 10)
        )

        ttk.Label(playback_frame, text="プレビュー長さ").grid(row=0, column=3, sticky="w")
        preview_entry = ttk.Entry(playback_frame, textvariable=self.preview_length_var, width=12)
        preview_entry.grid(row=0, column=4, sticky="w", padx=(5, 10))
        preview_entry.bind("<FocusOut>", self._on_preview_length_change)
        preview_entry.bind("<Return>", self._on_preview_length_change)

        ttk.Button(playback_frame, text="選択長を適用", command=self._set_preview_from_selection).grid(
            row=0, column=5, sticky="w", padx=(0, 10)
        )

        self.play_button = ttk.Button(playback_frame, text="再生", command=self.toggle_playback)
        self.play_button.grid(row=0, column=6, sticky="e")
        return row + 1

    def _build_segments_section(self, frame: ttk.Frame, row: int) -> int:
        segments_frame = ttk.LabelFrame(frame, text="セグメント", padding=10)
        segments_frame.grid(row=row, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 10))
        segments_frame.columnconfigure(0, weight=1)

        self.segment_listbox = tk.Listbox(
            segments_frame,
            height=6,
            exportselection=False,
            width=48,
        )
        self.segment_listbox.grid(row=0, column=0, rowspan=6, sticky="nsew")
        self.segment_listbox.bind("<Double-Button-1>", self._load_selected_segment)

        scrollbar = ttk.Scrollbar(
            segments_frame,
            orient=tk.VERTICAL,
            command=self.segment_listbox.yview,
        )
        scrollbar.grid(row=0, column=1, rowspan=6, sticky="ns")
        self.segment_listbox.config(yscrollcommand=scrollbar.set)

        button_column = ttk.Frame(segments_frame)
        button_column.grid(row=0, column=2, rowspan=6, sticky="nsw", padx=(10, 0))
        ttk.Button(button_column, text="追加", command=self._add_segment).grid(row=0, column=0, sticky="ew", pady=2)
        ttk.Button(button_column, text="削除", command=self._remove_segment).grid(row=1, column=0, sticky="ew", pady=2)
        ttk.Button(button_column, text="上へ", command=lambda: self._move_segment(-1)).grid(row=2, column=0, sticky="ew", pady=2)
        ttk.Button(button_column, text="下へ", command=lambda: self._move_segment(1)).grid(row=3, column=0, sticky="ew", pady=2)
        ttk.Button(button_column, text="クリア", command=self._clear_segments).grid(row=4, column=0, sticky="ew", pady=2)

        ttk.Label(segments_frame, textvariable=self.segment_info_var).grid(row=6, column=0, columnspan=3, sticky="w", pady=(5, 0))
        return row + 1

    def _build_options_section(self, frame: ttk.Frame, row: int) -> int:
        checkbox_frame = ttk.Frame(frame)
        checkbox_frame.grid(row=row, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 10))
        ttk.Checkbutton(
            checkbox_frame,
            text="既存の出力を上書き",
            variable=self.overwrite_var,
        ).grid(row=0, column=0, sticky="w", padx=(0, 15))
        ttk.Checkbutton(
            checkbox_frame,
            text="ドライラン (コマンドのみ)",
            variable=self.dry_run_var,
        ).grid(row=0, column=1, sticky="w")

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=row + 1, column=0, columnspan=3, sticky="ew", padx=10)
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)

        self.run_button = ttk.Button(button_frame, text="実行", command=self.run_processing)
        self.run_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(button_frame, text="閉じる", command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(5, 0))
        return row + 2

    def _build_status_bar(self, frame: ttk.Frame, row: int) -> None:
        ttk.Label(frame, textvariable=self.status_var, relief="sunken", anchor="w").grid(
            row=row, column=0, columnspan=3, sticky="ew", padx=10, pady=(5, 0)
        )

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _require_input_path(self, *, must_exist: bool = True) -> Optional[Path]:
        text = self.input_var.get().strip()
        if not text:
            messagebox.showerror("エラー", "入力ファイルを選択してください。")
            return None
        path = Path(text).expanduser()
        if must_exist and not path.exists():
            messagebox.showerror("エラー", "入力ファイルが存在しません。")
            return None
        return path

    def _require_output_path(self) -> Optional[Path]:
        text = self.output_var.get().strip()
        if not text:
            messagebox.showerror("エラー", "出力ファイルを指定してください。")
            return None
        return Path(text).expanduser()

    def _parse_target_duration(self) -> tuple[bool, Optional[float]]:
        try:
            value = _parse_optional(self.target_var.get(), allow_zero=False, default=None)
        except ValueError as exc:
            messagebox.showerror("エラー", f"目標時間の指定が不正です: {exc}")
            return False, None
        return True, value

    def _ensure_total_duration(self) -> bool:
        if self.total_duration is None:
            messagebox.showerror("エラー", "先に入力ファイルの長さを取得してください。")
            return False
        if self.total_duration <= 0:
            messagebox.showerror("エラー", "ファイルの長さを取得できていません。")
            return False
        return True

    def _resolve_segments(self) -> Optional[List[SegmentSpec]]:
        if not self._ensure_total_duration():
            return None
        if self.segments:
            return list(self.segments)
        if self.trim_end_explicit or self.trim_start_seconds > TOLERANCE:
            end = self.trim_end_seconds
            if end - self.trim_start_seconds <= TOLERANCE:
                messagebox.showerror("エラー", "出力する範囲を指定してください。")
                return None
            return [SegmentSpec(start=self.trim_start_seconds, end=end)]
        return [SegmentSpec(start=0.0, end=self.total_duration or 0.0)]

    def _will_trim(self, segments: List[SegmentSpec]) -> bool:
        if self.total_duration is None:
            return False
        return not (
            len(segments) == 1
            and segments[0].start <= TOLERANCE
            and abs(segments[0].end - self.total_duration) <= TOLERANCE
        )

    def _gather_process_request(self) -> Optional[ProcessRequest]:
        if not self._apply_pending_entry_values():
            return None

        input_path = self._require_input_path()
        if input_path is None:
            return None

        output_path = self._require_output_path()
        if output_path is None:
            return None

        ok, target_duration = self._parse_target_duration()
        if not ok:
            return None

        segments = self._resolve_segments()
        if segments is None:
            return None

        if target_duration is None and not self._will_trim(segments):
            messagebox.showerror(
                "エラー",
                "目標時間またはトリミング範囲を指定してください。",
            )
            return None

        return ProcessRequest(
            input_path=input_path,
            output_path=output_path,
            target_duration=target_duration,
            segments=tuple(segments),
            overwrite=self.overwrite_var.get(),
            dry_run=self.dry_run_var.get(),
        )

    def _start_processing(self, request: ProcessRequest) -> None:
        self._set_status("処理中...")
        self.run_button.config(state=tk.DISABLED)
        self.processing_thread = threading.Thread(
            target=self._process_worker,
            args=(request,),
            daemon=True,
        )
        self.processing_thread.start()
    def _resolve_background(self, style_name: str, fallback: str) -> str:
        style = ttk.Style()
        color = style.lookup(style_name, "background")
        if not color:
            color = style.lookup(style_name, "fieldbackground")
        return color or fallback

    def _init_timeline_graphics(self) -> None:
        canvas = self.timeline_canvas
        canvas.delete("all")
        center = self.timeline_height / 2
        top = center - 8
        bottom = center + 8
        left = self.timeline_padding
        right = self.timeline_width - self.timeline_padding

        self.timeline_track_id = canvas.create_rectangle(
            left,
            top,
            right,
            bottom,
            fill="#e0e0e0",
            outline="#b5b5b5",
        )
        self.timeline_selection_id = canvas.create_rectangle(
            left,
            top,
            left,
            bottom,
            fill="#4f83d1",
            outline="",
        )
        handle_half = self.timeline_handle_half
        self.timeline_start_handle_id = canvas.create_rectangle(
            left - handle_half,
            top - 5,
            left + handle_half,
            bottom + 5,
            fill="#1f4b8f",
            outline="",
        )
        self.timeline_end_handle_id = canvas.create_rectangle(
            left - handle_half,
            top - 5,
            left + handle_half,
            bottom + 5,
            fill="#1f4b8f",
            outline="",
        )
        self.timeline_start_text_id = canvas.create_text(
            left,
            bottom + 16,
            text="0:00",
            fill="#333333",
            font=("Segoe UI", 9),
        )
        self.timeline_end_text_id = canvas.create_text(
            left,
            bottom + 16,
            text="0:00",
            fill="#333333",
            font=("Segoe UI", 9),
        )

        marker_top = center - 14
        marker_bottom = center + 14
        self.playback_marker_id = canvas.create_line(
            left,
            marker_top,
            left,
            marker_bottom,
            fill="#d04f4f",
            width=2,
        )
        self.playback_marker_text_id = canvas.create_text(
            left,
            marker_top - 4,
            text="▶",
            fill="#d04f4f",
            font=("Segoe UI", 9, "bold"),
        )
        self.segment_marker_ids = []

    def _draw_segment_markers(self) -> None:
        canvas = self.timeline_canvas
        for marker in self.segment_marker_ids:
            canvas.delete(marker)
        self.segment_marker_ids = []

        if self.total_duration is None or self.total_duration <= 0:
            return

        markers: List[int] = []
        track_top = self.timeline_height / 2 - 11
        track_bottom = self.timeline_height / 2 + 11
        for segment in self.segments:
            start_x = self._time_to_canvas_x(segment.start)
            end_x = self._time_to_canvas_x(segment.end)
            marker = canvas.create_rectangle(
                start_x,
                track_top,
                end_x,
                track_bottom,
                fill="#cfe2ff",
                outline="",
            )
            canvas.tag_lower(marker, self.timeline_selection_id)
            markers.append(marker)
        self.segment_marker_ids = markers

    def _update_timeline_canvas(self) -> None:
        canvas = self.timeline_canvas
        center = self.timeline_height / 2
        top = center - 8
        bottom = center + 8
        left = self.timeline_padding
        handle_half = self.timeline_handle_half

        if self.total_duration is None or self.total_duration <= 0:
            canvas.coords(self.timeline_selection_id, left, top, left, bottom)
            canvas.coords(
                self.timeline_start_handle_id,
                left - handle_half,
                top - 5,
                left + handle_half,
                bottom + 5,
            )
            canvas.coords(
                self.timeline_end_handle_id,
                left - handle_half,
                top - 5,
                left + handle_half,
                bottom + 5,
            )
            canvas.itemconfig(self.timeline_start_text_id, text="未取得")
            canvas.coords(self.timeline_start_text_id, left, bottom + 16)
            canvas.itemconfig(self.timeline_end_text_id, text="")
            self._draw_segment_markers()
            self._update_playback_marker()
            return

        start_x = self._time_to_canvas_x(self.trim_start_seconds)
        end_x = self._time_to_canvas_x(self.trim_end_seconds)
        if end_x - start_x < 2:
            end_x = start_x + 2

        canvas.coords(self.timeline_selection_id, start_x, top, end_x, bottom)
        canvas.coords(
            self.timeline_start_handle_id,
            start_x - handle_half,
            top - 5,
            start_x + handle_half,
            bottom + 5,
        )
        canvas.coords(
            self.timeline_end_handle_id,
            end_x - handle_half,
            top - 5,
            end_x + handle_half,
            bottom + 5,
        )
        canvas.itemconfig(self.timeline_start_text_id, text=format_duration(self.trim_start_seconds))
        canvas.coords(self.timeline_start_text_id, start_x, bottom + 16)
        canvas.itemconfig(self.timeline_end_text_id, text=format_duration(self.trim_end_seconds))
        canvas.coords(self.timeline_end_text_id, end_x, bottom + 16)

        self._draw_segment_markers()
        self._update_playback_marker()
    def _set_trim_range(
        self,
        start: float,
        end: Optional[float],
        *,
        update_entries: bool = True,
        update_canvas: bool = True,
        end_explicit: Optional[bool] = None,
    ) -> None:
        start = max(0.0, start)
        if end_explicit is None:
            end_explicit = end is not None
        if end is None:
            if self.total_duration is not None:
                end = self.total_duration
            else:
                end = start
        else:
            end = max(start, end)
        if self.total_duration is not None:
            start = min(start, self.total_duration)
            end = min(max(end, start), self.total_duration)
        self.trim_start_seconds = start
        self.trim_end_seconds = end
        self.trim_end_explicit = end_explicit
        if update_entries:
            self._update_trim_entries()
        if update_canvas:
            self._update_timeline_canvas()
        self._update_duration_summary()

    def _update_trim_entries(self) -> None:
        self.trim_start_var.set(format_duration(self.trim_start_seconds))
        if self.trim_end_explicit or self.total_duration is None:
            self.trim_end_var.set(format_duration(self.trim_end_seconds))
        else:
            self.trim_end_var.set("")
        length_seconds = max(self.trim_end_seconds - self.trim_start_seconds, 0.0)
        self.trim_length_var.set(format_duration(length_seconds))

    def _time_to_canvas_x(self, seconds: float) -> float:
        usable = self.timeline_width - (self.timeline_padding * 2)
        ratio = 0.0
        if self.total_duration and self.total_duration > 0:
            ratio = min(max(seconds / self.total_duration, 0.0), 1.0)
        return self.timeline_padding + (ratio * usable)

    def _canvas_x_to_time(self, x: float) -> float:
        clamped = self._clamp_canvas_x(x)
        usable = self.timeline_width - (self.timeline_padding * 2)
        if usable <= 0 or not self.total_duration:
            return 0.0
        return ((clamped - self.timeline_padding) / usable) * self.total_duration

    def _clamp_canvas_x(self, x: float) -> float:
        return min(max(x, self.timeline_padding), self.timeline_width - self.timeline_padding)

    def _update_segment_list(self) -> None:
        self.segment_listbox.delete(0, tk.END)
        total = 0.0
        for index, segment in enumerate(self.segments, 1):
            duration = max(segment.end - segment.start, 0.0)
            total += duration
            label = (
                f"{index:>2}: {format_duration(segment.start)}"
                f" -> {format_duration(segment.end)}"
                f" ({duration:.3f} 秒)"
            )
            self.segment_listbox.insert(tk.END, label)
        self.segment_info_var.set(f"セグメント {len(self.segments)} 件 / 合計 {total:.3f} 秒")
        self._draw_segment_markers()
        self._update_duration_summary()

    def _add_segment(self) -> None:
        if self.total_duration is None:
            messagebox.showerror("エラー", "入力ファイルの長さを取得してから追加してください。")
            return
        if self.trim_end_seconds - self.trim_start_seconds <= TOLERANCE:
            messagebox.showerror("エラー", "追加する範囲をタイムラインで指定してください。")
            return
        new_segment = SegmentSpec(start=self.trim_start_seconds, end=self.trim_end_seconds)
        self.segments.append(new_segment)
        self._update_segment_list()
        self._set_status("セグメントを追加しました")

    def _remove_segment(self) -> None:
        selection = self.segment_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        self.segments.pop(index)
        self._update_segment_list()
        self._set_status("セグメントを削除しました")

    def _move_segment(self, offset: int) -> None:
        selection = self.segment_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        new_index = index + offset
        if new_index < 0 or new_index >= len(self.segments):
            return
        self.segments[index], self.segments[new_index] = (
            self.segments[new_index],
            self.segments[index],
        )
        self._update_segment_list()
        self.segment_listbox.selection_set(new_index)
        self.segment_listbox.activate(new_index)
        self._set_status("セグメントの順番を変更しました")

    def _clear_segments(self) -> None:
        if not self.segments:
            return
        if not messagebox.askyesno("確認", "セグメントをすべて削除しますか?"):
            return
        self.segments.clear()
        self._update_segment_list()
        self._set_status("セグメントをクリアしました")

    def _load_selected_segment(self, event: Optional[tk.Event] = None) -> None:
        selection = self.segment_listbox.curselection()
        if not selection:
            return
        segment = self.segments[selection[0]]
        self._set_trim_range(segment.start, segment.end, end_explicit=True)
        self._set_playback_start(segment.start)
        self._set_status("セグメントをタイムラインに読み込みました")
    def _select_input(self) -> None:
        file_path = filedialog.askopenfilename(
            title="入力MP3を選択",
            filetypes=[("MP3", "*.mp3"), ("すべてのファイル", "*.*")],
        )
        if not file_path:
            return
        self._stop_playback()
        self.input_var.set(file_path)
        if not self.output_var.get().strip():
            path = Path(file_path)
            self.output_var.set(str(path.with_name(f"{path.stem}_edited.mp3")))
        self._set_status("長さを取得中...")
        self.update_idletasks()
        self._load_input_duration(Path(file_path))
        self.segments.clear()
        self._update_segment_list()
        self._set_playback_start(0.0)

    def _select_output(self) -> None:
        file_path = filedialog.asksaveasfilename(
            title="出力先を選択",
            defaultextension=".mp3",
            filetypes=[("MP3", "*.mp3"), ("すべてのファイル", "*.*")],
        )
        if file_path:
            self.output_var.set(file_path)

    def _load_input_duration(self, path: Path) -> None:
        try:
            ffprobe_path = resolve_executable("ffprobe")
        except FileNotFoundError:
            self.total_duration = None
            self.duration_label.config(text="全体長: 取得できません (ffprobe未検出)")
            self._set_trim_range(0.0, None, end_explicit=False)
            self._set_status("ffprobeが見つからないため長さを取得できません")
            return

        try:
            duration = probe_duration(path, ffprobe_path)
        except RuntimeError as exc:
            self.total_duration = None
            self.duration_label.config(text="全体長: 取得できません")
            messagebox.showerror("エラー", str(exc))
            self._set_trim_range(0.0, None, end_explicit=False)
            self._set_status("長さの取得に失敗しました")
            return

        self.total_duration = max(duration, 0.0)
        self.duration_label.config(
            text=f"全体長: {format_duration(self.total_duration)} ({self.total_duration:.3f} 秒)"
        )
        self._set_trim_range(0.0, None, end_explicit=False)
        self._set_playback_start(0.0)
        self._set_status("長さを取得しました")
    def _on_start_entry_change(self, event: Optional[tk.Event] = None) -> None:
        try:
            value = _parse_optional(
                self.trim_start_var.get(),
                allow_zero=True,
                default=self.trim_start_seconds,
            )
        except ValueError as exc:
            messagebox.showerror("エラー", f"開始位置の入力が不正です: {exc}")
            self._update_trim_entries()
            return
        start_value = value if value is not None else 0.0
        self._set_trim_range(start_value, self.trim_end_seconds, end_explicit=self.trim_end_explicit)

    def _on_end_entry_change(self, event: Optional[tk.Event] = None) -> None:
        text = self.trim_end_var.get()
        if not text.strip():
            self._set_trim_range(self.trim_start_seconds, None, end_explicit=False)
            return
        try:
            value = parse_duration(text, allow_zero=True)
        except ValueError as exc:
            messagebox.showerror("エラー", f"終了位置の入力が不正です: {exc}")
            self._update_trim_entries()
            return
        self._set_trim_range(self.trim_start_seconds, value, end_explicit=True)

    def _on_trim_length_entry(self, event: Optional[tk.Event] = None) -> None:
        text = self.trim_length_var.get()
        if not text.strip():
            self._update_trim_entries()
            return
        try:
            length = parse_duration(text, allow_zero=False)
        except ValueError as exc:
            messagebox.showerror("エラー", f"長さの入力が不正です: {exc}")
            self._update_trim_entries()
            return
        end_value = self.trim_start_seconds + length
        self._set_trim_range(self.trim_start_seconds, end_value, end_explicit=True)

    def _on_timeline_press(self, event: tk.Event) -> None:
        if self.total_duration is None or self.total_duration <= 0:
            return
        if getattr(event, "num", 1) == 3:
            return
        if event.state & 0x0004:
            seconds = self._canvas_x_to_time(self._clamp_canvas_x(event.x))
            self._set_playback_start(seconds)
            self._set_status(f"再生開始を {format_duration(seconds)} に設定しました")
            return
        x = self._clamp_canvas_x(event.x)
        start_x = self._time_to_canvas_x(self.trim_start_seconds)
        end_x = self._time_to_canvas_x(self.trim_end_seconds)
        if abs(x - start_x) <= abs(x - end_x):
            self._active_handle = "start"
            new_start = self._canvas_x_to_time(x)
            self._set_trim_range(new_start, self.trim_end_seconds, end_explicit=self.trim_end_explicit)
        else:
            self._active_handle = "end"
            new_end = self._canvas_x_to_time(x)
            self._set_trim_range(self.trim_start_seconds, new_end, end_explicit=True)

    def _on_timeline_drag(self, event: tk.Event) -> None:
        if self._active_handle is None:
            return
        if self.total_duration is None or self.total_duration <= 0:
            return
        x = self._clamp_canvas_x(event.x)
        seconds = self._canvas_x_to_time(x)
        if self._active_handle == "start":
            self._set_trim_range(seconds, self.trim_end_seconds, end_explicit=self.trim_end_explicit)
        else:
            self._set_trim_range(self.trim_start_seconds, seconds, end_explicit=True)

    def _on_timeline_release(self, event: tk.Event) -> None:
        self._active_handle = None

    def _on_timeline_set_playback(self, event: tk.Event) -> None:
        if self.total_duration is None or self.total_duration <= 0:
            return
        seconds = self._canvas_x_to_time(self._clamp_canvas_x(event.x))
        self._set_playback_start(seconds)
        self._set_status(f"再生開始を {format_duration(seconds)} に設定しました")
    def _set_playback_start(
        self,
        seconds: float,
        *,
        update_entry: bool = True,
        update_marker: bool = True,
    ) -> None:
        if self.total_duration is not None:
            seconds = min(max(0.0, seconds), self.total_duration)
        else:
            seconds = max(0.0, seconds)
        self.playback_start_seconds = seconds
        if update_entry:
            self.playback_start_var.set(format_duration(seconds))
        if update_marker:
            self._update_playback_marker()

    def _update_playback_marker(self) -> None:
        if self.playback_marker_id is None or self.playback_marker_text_id is None:
            return
        if self.total_duration is None or self.total_duration <= 0:
            x = self.timeline_padding
        else:
            x = self._time_to_canvas_x(self.playback_start_seconds)
        marker_top = self.timeline_height / 2 - 14
        marker_bottom = self.timeline_height / 2 + 14
        self.timeline_canvas.coords(self.playback_marker_id, x, marker_top, x, marker_bottom)
        self.timeline_canvas.coords(self.playback_marker_text_id, x, marker_top - 4)

    def _update_duration_summary(self) -> None:
        if self.total_duration is None:
            self.summary_var.set("出力 0.000 秒 / 残り --.- 秒")
            return
        if self.segments:
            kept = sum(max(segment.end - segment.start, 0.0) for segment in self.segments)
        else:
            if self.trim_end_explicit or self.trim_start_seconds > TOLERANCE:
                kept = max(self.trim_end_seconds - self.trim_start_seconds, 0.0)
            else:
                kept = self.total_duration
        kept = min(max(kept, 0.0), self.total_duration)
        remaining = max(self.total_duration - kept, 0.0)
        self.summary_var.set(f"出力 {kept:.3f} 秒 / 残り {remaining:.3f} 秒")

    def toggle_playback(self) -> None:
        if self.play_process and self.play_process.poll() is None:
            self._stop_playback()
            return

        if not self._apply_pending_entry_values():
            return

        input_path = self._require_input_path()
        if input_path is None:
            return
        if not self._ensure_total_duration():
            return

        if not self._on_playback_start_change():
            return

        try:
            preview_duration = self._get_preview_duration(self.playback_start_seconds)
        except ValueError as exc:
            messagebox.showerror("エラー", str(exc))
            return

        if preview_duration <= TOLERANCE:
            messagebox.showerror("エラー", "プレビュー長さが短すぎます。")
            return

        self._start_playback(input_path, self.playback_start_seconds, preview_duration)

    def _on_playback_start_change(self, event: Optional[tk.Event] = None) -> bool:
        text = self.playback_start_var.get()
        try:
            seconds = parse_duration(text, allow_zero=True)
        except ValueError as exc:
            messagebox.showerror("エラー", f"再生開始の入力が不正です: {exc}")
            self.playback_start_var.set(format_duration(self.playback_start_seconds))
            return False
        self._set_playback_start(seconds, update_entry=True)
        return True

    def _set_playback_from_selection(self) -> None:
        self._set_playback_start(self.trim_start_seconds)
        self._set_status("再生開始位置を選択開始に合わせました")

    def _on_preview_length_change(self, event: Optional[tk.Event] = None) -> None:
        text = self.preview_length_var.get().strip()
        if not text:
            return
        try:
            parse_duration(text, allow_zero=False)
        except ValueError as exc:
            messagebox.showerror("エラー", f"プレビュー長さの入力が不正です: {exc}")
            self.preview_length_var.set("")

    def _set_preview_from_selection(self) -> None:
        length = max(self.trim_end_seconds - self.trim_start_seconds, 0.0)
        if length <= TOLERANCE:
            messagebox.showerror("エラー", "選択範囲が設定されていません。")
            return
        self.preview_length_var.set(f"{length:.3f}")
        self._set_status("プレビュー長さを選択範囲に合わせました")

    def _get_preview_duration(self, start: float) -> float:
        text = self.preview_length_var.get().strip()
        if text:
            duration = parse_duration(text, allow_zero=False)
        else:
            if self.trim_end_explicit and self.trim_end_seconds > start + TOLERANCE:
                duration = self.trim_end_seconds - start
            elif self.total_duration is not None:
                duration = max(self.total_duration - start, 0.0)
            else:
                duration = DEFAULT_PREVIEW_SECONDS
        if self.total_duration is not None:
            duration = min(duration, max(self.total_duration - start, 0.0))
        if duration <= 0.0:
            raise ValueError("プレビュー長さが短すぎます。")
        return duration
    def _start_playback(self, input_path: Path, start: float, duration: float) -> None:
        try:
            ffplay_path = resolve_executable("ffplay")
        except FileNotFoundError:
            messagebox.showerror(
                "エラー",
                "ffplay が見つかりません。FFmpeg の ffplay を PATH に追加してください。",
            )
            return

        self._stop_playback()
        cmd = [
            ffplay_path,
            "-nodisp",
            "-autoexit",
            "-hide_banner",
            "-loglevel",
            "error",
        ]
        if start > TOLERANCE:
            cmd.extend(["-ss", f"{start:.6f}"])
        if duration > TOLERANCE:
            cmd.extend(["-t", f"{duration:.6f}"])
        cmd.append(str(input_path))

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            messagebox.showerror("エラー", f"ffplay の起動に失敗しました: {exc}")
            return

        self.play_process = process
        self._set_play_button_state(playing=True)
        self._set_status(f"再生中... (開始: {format_duration(start)})")
        self.playback_thread = threading.Thread(
            target=self._monitor_playback,
            args=(process,),
            daemon=True,
        )
        self.playback_thread.start()

    def _monitor_playback(self, process: subprocess.Popen) -> None:
        try:
            process.wait()
        finally:
            self.after(0, lambda proc=process: self._playback_finished(proc))

    def _playback_finished(self, process: subprocess.Popen) -> None:
        if self.play_process is not process:
            return
        self.play_process = None
        self.playback_thread = None
        self._set_play_button_state(playing=False)
        self._set_status("再生完了")

    def _stop_playback(self) -> None:
        process = self.play_process
        if process and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        self.play_process = None
        self.playback_thread = None
        self._set_play_button_state(playing=False)

    def _set_play_button_state(self, *, playing: bool) -> None:
        if not hasattr(self, "play_button"):
            return
        if playing:
            self.play_button.config(text="停止", state=tk.NORMAL)
        else:
            self.play_button.config(text="再生", state=tk.NORMAL)

    def _on_close(self) -> None:
        self._stop_playback()
        super().destroy()

    def _apply_pending_entry_values(self) -> bool:
        try:
            start_value = _parse_optional(
                self.trim_start_var.get(),
                allow_zero=True,
                default=self.trim_start_seconds,
            )
            end_text = self.trim_end_var.get().strip()
            end_value = parse_duration(end_text, allow_zero=True) if end_text else None
            length_text = self.trim_length_var.get().strip()
            length_value = parse_duration(length_text, allow_zero=False) if length_text else None
        except ValueError as exc:
            messagebox.showerror("エラー", f"時間の指定が不正です: {exc}")
            return False

        start = start_value if start_value is not None else self.trim_start_seconds
        if length_value is not None:
            end = start + length_value
            end_explicit = True
        elif end_value is not None:
            end = end_value
            end_explicit = True
        else:
            if self.trim_end_explicit:
                end = self.trim_end_seconds
                end_explicit = True
            else:
                end = None
                end_explicit = False

        self._set_trim_range(start, end, end_explicit=end_explicit)
        return True

    def run_processing(self) -> None:
        if self.processing_thread and self.processing_thread.is_alive():
            return

        self._stop_playback()

        request = self._gather_process_request()
        if request is None:
            return

        self._start_processing(request)

    def _process_worker(self, request: ProcessRequest) -> None:
        try:
            result = process_audio(
                input_path=request.input_path,
                output_path=request.output_path,
                target_duration=request.target_duration,
                segments=list(request.segments),
                overwrite=request.overwrite,
                dry_run=request.dry_run,
            )
        except Exception as exc:  # noqa: BLE001 - surface error to the UI
            self.after(0, lambda err=exc: self._handle_error(err))
        else:
            self.after(0, lambda res=result: self._handle_success(res))

    def _handle_success(self, result: ProcessResult) -> None:
        self.run_button.config(state=tk.NORMAL)
        summary = self._format_summary(result)
        self._set_status("完了しました")
        if result.dry_run:
            messagebox.showinfo("ドライラン", summary)
        else:
            messagebox.showinfo("完了", summary)

    def _handle_error(self, exc: Exception) -> None:
        self.run_button.config(state=tk.NORMAL)
        self._set_status("エラーが発生しました")
        messagebox.showerror("エラー", str(exc))

    def _format_summary(self, result: ProcessResult) -> str:
        lines = [
            f"入力全体: {format_duration(result.total_input_duration)} ({result.total_input_duration:.3f} 秒)",
            "セグメント:",
        ]
        for idx, segment in enumerate(result.segments, 1):
            lines.append(
                f"  {idx:>2}: {format_duration(segment.start)} -> {format_duration(segment.end)} ({segment.duration:.3f} 秒)"
            )
        lines.append(
            f"合計長: {format_duration(result.total_segment_duration)} ({result.total_segment_duration:.3f} 秒)"
        )
        if result.target_duration is not None:
            lines.append(
                f"目標時間: {format_duration(result.target_duration)} ({result.target_duration:.3f} 秒)"
            )
            lines.append(f"再生速度倍率: {result.tempo_factor:.6f}x")
        else:
            lines.append("再生速度倍率: 1.000000x (変更なし)")
        if result.new_duration is not None:
            lines.append(
                f"出力時間: {format_duration(result.new_duration)} ({result.new_duration:.3f} 秒)"
            )
            reference = (
                result.target_duration
                if result.target_duration is not None
                else result.total_segment_duration
            )
            if reference is not None:
                delta = result.new_duration - reference
                lines.append(f"差分: {delta:+.3f} 秒")
        else:
            lines.append("出力時間: <unknown>")
        if result.dry_run:
            lines.append("")
            lines.append("コマンド:")
            lines.append(format_command(result.ffmpeg_command))
        else:
            lines.append("")
            lines.append(f"出力ファイル: {result.output_path}")
        return "\n".join(lines)

def main() -> None:
    app = Mp3LengthToolApp()
    app.mainloop()


if __name__ == "__main__":
    main()
