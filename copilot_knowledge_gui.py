#!/usr/bin/env python3
"""Lightweight GUI tool to capture, answer, and aggregate Copilot / LLM usage knowledge.

MVP Features:
- Create question (title, context, attempts, tags, priority)
- List / filter questions (status, tag substring)
- Answer / append answer history
- Promote to pattern (auto markdown file)
- Generate aggregated markdown overview

Data stored in docs/copilot/data/store.json
"""
from __future__ import annotations

import json
import re
import tkinter as tk
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from tkinter import ttk, messagebox
from typing import List, Optional

DATA_PATH = Path('docs/copilot/data/store.json')
PATTERN_DIR = Path('docs/copilot/patterns')
AGGREGATED_PATH = Path('docs/copilot/AGGREGATED_OVERVIEW.md')

ISO = '%Y-%m-%dT%H:%M:%SZ'

PRIORITIES = ['low', 'medium', 'high']
STATUSES = ['open', 'answered', 'archived']

@dataclass
class AnswerEntry:
    timestamp: str
    content: str

@dataclass
class Question:
    id: str
    title: str
    context: str
    attempts: str
    tags: List[str]
    priority: str
    status: str
    answer: str
    answer_history: List[AnswerEntry]
    created: str
    updated: str

    def to_json(self) -> dict:
        d = asdict(self)
        d['answer_history'] = [asdict(a) for a in self.answer_history]
        return d

    @staticmethod
    def from_json(d: dict) -> 'Question':
        return Question(
            id=d['id'],
            title=d.get('title',''),
            context=d.get('context',''),
            attempts=d.get('attempts',''),
            tags=list(d.get('tags', [])),
            priority=d.get('priority','medium'),
            status=d.get('status','open'),
            answer=d.get('answer',''),
            answer_history=[AnswerEntry(**a) for a in d.get('answer_history', [])],
            created=d.get('created', datetime.utcnow().strftime(ISO)),
            updated=d.get('updated', datetime.utcnow().strftime(ISO)),
        )

class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.questions: List[Question] = []
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.questions = []
            return
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            self.questions = [Question.from_json(q) for q in data.get('questions', [])]
        except Exception as exc:  # noqa: BLE001
            backup = self.path.with_suffix(f'.corrupt-{datetime.utcnow().strftime(ISO)}.json')
            try:
                self.path.rename(backup)
            except Exception:
                pass
            messagebox.showerror('Load Error', f'store.json corrupted, moved to {backup}: {exc}')
            self.questions = []

    def save(self) -> None:
        payload = {'questions': [q.to_json() for q in self.questions]}
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(self.path)

    def next_id(self) -> str:
        today = datetime.utcnow().strftime('%Y%m%d')
        seq = 1
        pattern = re.compile(rf'^Q-{today}-(\d+)$')
        for q in self.questions:
            m = pattern.match(q.id)
            if m:
                seq = max(seq, int(m.group(1)) + 1)
        return f'Q-{today}-{seq:03d}'

    def add(self, q: Question) -> None:
        self.questions.append(q)
        self.save()

    def update(self, q: Question) -> None:
        # already mutated; just persist
        q.updated = datetime.utcnow().strftime(ISO)
        self.save()

    def get(self, qid: str) -> Optional[Question]:
        for q in self.questions:
            if q.id == qid:
                return q
        return None

class KnowledgeGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title('Copilot Knowledge')
        self.geometry('1080x640')
        self.store = Store(DATA_PATH)

        self.filter_status = tk.StringVar(value='all')
        self.filter_tag = tk.StringVar()
        self.selected_id: Optional[str] = None

        self._build_layout()
        self._refresh_list()

    # Layout
    def _build_layout(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill='both', expand=True)
        left = ttk.Frame(top, padding=6)
        left.pack(side='left', fill='y')
        right = ttk.Notebook(top)
        right.pack(side='left', fill='both', expand=True)

        # Filters
        fbar = ttk.Frame(left)
        fbar.pack(fill='x')
        ttk.Label(fbar, text='Status').pack(side='left')
        status_cb = ttk.Combobox(fbar, values=['all'] + STATUSES, textvariable=self.filter_status, width=10, state='readonly')
        status_cb.pack(side='left', padx=4)
        status_cb.bind('<<ComboboxSelected>>', lambda e: self._refresh_list())
        ttk.Label(fbar, text='Tag').pack(side='left')
        tag_entry = ttk.Entry(fbar, textvariable=self.filter_tag, width=14)
        tag_entry.pack(side='left', padx=4)
        tag_entry.bind('<Return>', lambda e: self._refresh_list())
        ttk.Button(fbar, text='Clear', command=self._clear_filters).pack(side='left')
        ttk.Button(fbar, text='Refresh', command=self._refresh_list).pack(side='left', padx=4)

        # List
        columns = ('id','title','status','priority','tags')
        self.tree = ttk.Treeview(left, columns=columns, show='headings', height=26)
        for c, w in [('id',110),('title',220),('status',80),('priority',70),('tags',160)]:
            self.tree.heading(c, text=c.upper())
            self.tree.column(c, width=w, stretch=False)
        self.tree.pack(fill='y', expand=False, pady=4)
        self.tree.bind('<<TreeviewSelect>>', self._on_select)

        # Tabs
        self.detail_frame = ttk.Frame(right, padding=10)
        self.create_frame = ttk.Frame(right, padding=10)
        self.aggregate_frame = ttk.Frame(right, padding=10)
        right.add(self.detail_frame, text='Detail')
        right.add(self.create_frame, text='New Question')
        right.add(self.aggregate_frame, text='Overview')

        self._build_create_tab()
        self._build_detail_tab()
        self._build_overview_tab()

    def _clear_filters(self) -> None:
        self.filter_status.set('all')
        self.filter_tag.set('')
        self._refresh_list()

    # Create Tab
    def _build_create_tab(self) -> None:
        frm = self.create_frame
        self.new_title = tk.StringVar()
        self.new_priority = tk.StringVar(value='medium')
        self.new_tags = tk.StringVar()
        self.new_context = tk.Text(frm, height=6)
        self.new_attempts = tk.Text(frm, height=6)

        row = 0
        ttk.Label(frm, text='Title *').grid(row=row, column=0, sticky='w')
        ttk.Entry(frm, textvariable=self.new_title, width=60).grid(row=row, column=1, sticky='w')
        row += 1
        ttk.Label(frm, text='Priority').grid(row=row, column=0, sticky='w')
        ttk.Combobox(frm, values=PRIORITIES, textvariable=self.new_priority, width=12, state='readonly').grid(row=row, column=1, sticky='w')
        row += 1
        ttk.Label(frm, text='Tags (comma)').grid(row=row, column=0, sticky='w')
        ttk.Entry(frm, textvariable=self.new_tags, width=60).grid(row=row, column=1, sticky='w')
        row += 1
        ttk.Label(frm, text='Context').grid(row=row, column=0, sticky='nw')
        self.new_context.grid(row=row, column=1, sticky='ew')
        row += 1
        ttk.Label(frm, text='Attempts').grid(row=row, column=0, sticky='nw')
        self.new_attempts.grid(row=row, column=1, sticky='ew')
        row += 1
        ttk.Button(frm, text='Create', command=self._create_question).grid(row=row, column=1, sticky='w', pady=6)
        frm.columnconfigure(1, weight=1)

    # Detail Tab
    def _build_detail_tab(self) -> None:
        frm = self.detail_frame
        self.detail_title_var = tk.StringVar()
        self.detail_priority_var = tk.StringVar()
        self.detail_status_var = tk.StringVar()
        self.detail_tags_var = tk.StringVar()
        self.detail_context = tk.Text(frm, height=8)
        self.detail_attempts = tk.Text(frm, height=6)
        self.detail_answer = tk.Text(frm, height=8)

        r = 0
        ttk.Label(frm, text='ID').grid(row=r, column=0, sticky='w')
        self.detail_id_label = ttk.Label(frm, text='-')
        self.detail_id_label.grid(row=r, column=1, sticky='w')
        r += 1
        ttk.Label(frm, text='Title').grid(row=r, column=0, sticky='w')
        ttk.Entry(frm, textvariable=self.detail_title_var, width=60).grid(row=r, column=1, sticky='w')
        r += 1
        ttk.Label(frm, text='Priority').grid(row=r, column=0, sticky='w')
        ttk.Combobox(frm, values=PRIORITIES, textvariable=self.detail_priority_var, width=12, state='readonly').grid(row=r, column=1, sticky='w')
        r += 1
        ttk.Label(frm, text='Status').grid(row=r, column=0, sticky='w')
        ttk.Combobox(frm, values=STATUSES, textvariable=self.detail_status_var, width=12, state='readonly').grid(row=r, column=1, sticky='w')
        r += 1
        ttk.Label(frm, text='Tags (comma)').grid(row=r, column=0, sticky='w')
        ttk.Entry(frm, textvariable=self.detail_tags_var, width=60).grid(row=r, column=1, sticky='w')
        r += 1
        ttk.Label(frm, text='Context').grid(row=r, column=0, sticky='nw')
        self.detail_context.grid(row=r, column=1, sticky='ew')
        r += 1
        ttk.Label(frm, text='Attempts').grid(row=r, column=0, sticky='nw')
        self.detail_attempts.grid(row=r, column=1, sticky='ew')
        r += 1
        ttk.Label(frm, text='Answer (append) *').grid(row=r, column=0, sticky='nw')
        self.detail_answer.grid(row=r, column=1, sticky='ew')
        r += 1
        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=r, column=1, sticky='w', pady=6)
        ttk.Button(btn_frame, text='Save Changes', command=self._save_detail).pack(side='left')
        ttk.Button(btn_frame, text='Append Answer', command=self._append_answer).pack(side='left', padx=6)
        ttk.Button(btn_frame, text='Promote to Pattern', command=self._promote).pack(side='left')
        frm.columnconfigure(1, weight=1)

    # Overview Tab
    def _build_overview_tab(self) -> None:
        frm = self.aggregate_frame
        self.overview_text = tk.Text(frm, wrap='none')
        self.overview_text.pack(fill='both', expand=True)
        btns = ttk.Frame(frm)
        btns.pack(fill='x')
        ttk.Button(btns, text='Regenerate Overview', command=self._generate_overview).pack(side='left')

    # Helpers
    def _refresh_list(self) -> None:
        for i in self.tree.get_children():
            self.tree.delete(i)
        status_filter = self.filter_status.get()
        tag_filter = self.filter_tag.get().strip().lower()
        items = list(self.store.questions)
        items.sort(key=lambda q: (PRIORITIES.index(q.priority) if q.priority in PRIORITIES else 99, q.created))
        for q in items:
            if status_filter != 'all' and q.status != status_filter:
                continue
            if tag_filter and not any(tag_filter in t.lower() for t in q.tags):
                continue
            self.tree.insert('', 'end', iid=q.id, values=(q.id, q.title[:40], q.status, q.priority, ','.join(q.tags)))

    def _on_select(self, _event) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        qid = sel[0]
        q = self.store.get(qid)
        if not q:
            return
        self.selected_id = q.id
        self.detail_id_label.config(text=q.id)
        self.detail_title_var.set(q.title)
        self.detail_priority_var.set(q.priority)
        self.detail_status_var.set(q.status)
        self.detail_tags_var.set(','.join(q.tags))
        self.detail_context.delete('1.0', 'end'); self.detail_context.insert('1.0', q.context)
        self.detail_attempts.delete('1.0', 'end'); self.detail_attempts.insert('1.0', q.attempts)
        self.detail_answer.delete('1.0', 'end'); self.detail_answer.insert('1.0', '')

    def _create_question(self) -> None:
        title = self.new_title.get().strip()
        if not title:
            messagebox.showerror('Error', 'Title is required')
            return
        q = Question(
            id=self.store.next_id(),
            title=title,
            context=self.new_context.get('1.0','end').strip(),
            attempts=self.new_attempts.get('1.0','end').strip(),
            tags=[t.strip() for t in self.new_tags.get().split(',') if t.strip()],
            priority=self.new_priority.get(),
            status='open',
            answer='',
            answer_history=[],
            created=datetime.utcnow().strftime(ISO),
            updated=datetime.utcnow().strftime(ISO),
        )
        self.store.add(q)
        self.new_title.set(''); self.new_tags.set(''); self.new_context.delete('1.0','end'); self.new_attempts.delete('1.0','end')
        self._refresh_list()
        messagebox.showinfo('Created', f'Created {q.id}')

    def _save_detail(self) -> None:
        if not self.selected_id:
            return
        q = self.store.get(self.selected_id)
        if not q:
            return
        q.title = self.detail_title_var.get().strip()
        q.priority = self.detail_priority_var.get()
        q.status = self.detail_status_var.get()
        q.tags = [t.strip() for t in self.detail_tags_var.get().split(',') if t.strip()]
        q.context = self.detail_context.get('1.0','end').strip()
        q.attempts = self.detail_attempts.get('1.0','end').strip()
        self.store.update(q)
        self._refresh_list()
        messagebox.showinfo('Saved', 'Changes saved')

    def _append_answer(self) -> None:
        if not self.selected_id:
            return
        q = self.store.get(self.selected_id)
        if not q:
            return
        text = self.detail_answer.get('1.0','end').strip()
        if not text:
            messagebox.showerror('Error', 'Answer text empty')
            return
        entry = AnswerEntry(timestamp=datetime.utcnow().strftime(ISO), content=text)
        q.answer_history.append(entry)
        if q.answer:
            q.answer += '\n\n' + text
        else:
            q.answer = text
        if q.status == 'open':
            q.status = 'answered'
        self.store.update(q)
        self.detail_answer.delete('1.0','end')
        self._refresh_list()
        messagebox.showinfo('Updated', 'Answer appended')

    def _slug(self, text: str) -> str:
        s = re.sub(r'[^a-zA-Z0-9]+', '-', text.lower()).strip('-')
        return s[:40] or 'pattern'

    def _promote(self) -> None:
        if not self.selected_id:
            return
        q = self.store.get(self.selected_id)
        if not q:
            return
        if not q.answer:
            messagebox.showerror('Error', 'No answer to promote')
            return
        slug = self._slug(q.title)
        seq = 1
        while True:
            fname = PATTERN_DIR / f'auto-{slug}-{seq:02d}.md'
            if not fname.exists():
                break
            seq += 1
        content = self._pattern_markdown(q)
        fname.write_text(content, encoding='utf-8')
        messagebox.showinfo('Promoted', f'Pattern written: {fname.name}')

    def _pattern_markdown(self, q: Question) -> str:
        duration = ''
        return (
            f"---\nid: {q.id.replace('Q-','P-')}\ntype: pattern\nsource_question: {q.id}\ncreated: {q.created}\nupdated: {q.updated}\nstatus: draft\ntags: [{', '.join(q.tags)}]\n---\n\n"
            f"# Pattern: {q.title}\n\n## Context\n{q.context or '(none)'}\n\n## Attempts\n{q.attempts or '(none)'}\n\n## Solution / Answer\n{q.answer}\n\n## Why it Works\n- (explain here)\n\n## References\n- Source Question: {q.id}\n{duration}"
        )

    def _generate_overview(self) -> None:
        text = self._build_overview_markdown()
        AGGREGATED_PATH.write_text(text, encoding='utf-8')
        self.overview_text.delete('1.0','end'); self.overview_text.insert('1.0', text)
        messagebox.showinfo('Overview', 'Aggregated overview regenerated')

    def _build_overview_markdown(self) -> str:
        qs = list(self.store.questions)
        now = datetime.utcnow().strftime(ISO)
        open_q = [q for q in qs if q.status == 'open']
        answered_q = [q for q in qs if q.status == 'answered']
        # Tag freq
        tag_freq = {}
        for q in qs:
            for t in q.tags:
                tag_freq[t] = tag_freq.get(t, 0) + 1
        tag_lines = ['| Tag | Count |', '|-----|-------|'] + [f"| {k} | {v} |" for k, v in sorted(tag_freq.items(), key=lambda x: (-x[1], x[0]))[:10]]
        def short(q: Question) -> str:
            return f"- {q.id} [{q.priority}] {q.title} (tags: {', '.join(q.tags)})"
        lines = [
            f"# Copilot Knowledge Overview (Generated)",
            f"Generated: {now}",
            "",
            f"## Open Questions ({len(open_q)})",
            *(short(q) for q in open_q[:50]),
            "",
            f"## Recently Answered (latest 10)",
            *(short(q) for q in sorted(answered_q, key=lambda q: q.updated, reverse=True)[:10]),
            "",
            "## Tag Frequency (Top 10)",
            *tag_lines,
        ]
        return '\n'.join(lines) + '\n'


def main() -> None:
    PATTERN_DIR.mkdir(parents=True, exist_ok=True)
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    app = KnowledgeGUI()
    app.mainloop()

if __name__ == '__main__':
    main()
