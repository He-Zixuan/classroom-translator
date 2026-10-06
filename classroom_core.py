# Copyright (c) 2026 He-Zixuan
# SPDX-License-Identifier: LicenseRef-Classroom-Personal-NonCommercial-1.0
"""Durable sentence queue; independent of the recognition/model runtime."""
import json
import re
import sqlite3
import time
import uuid
from pathlib import Path


class SentenceBuffer:
    """Consume committed ASR tokens once, retaining unfinished English."""
    def __init__(self, emit, max_words=120, min_words=4, pause_seconds=1.5):
        self.emit = emit
        self.text = ""
        self.start = 0.0
        self.end = 0.0
        self.max_words = max_words
        self.min_words = min_words
        self.pause_seconds = pause_seconds

    @staticmethod
    def unfinished_clause(text):
        # Streaming ASR can invent a period before a clause is complete.
        words=re.findall(r"[A-Za-z]+",text.lower())
        return bool(words and words[-1] in {'is','are','was','were','be','been','being','the','a','an','of','for','to','and','or','but','with','at','from','will','would','can','could','should','because','than'})

    def insert(self, tokens):
        for token in tokens:
            if not token.text:
                continue
            if self.text and token.start - self.end > self.pause_seconds:
                self.flush()
            if not self.text:
                self.start = token.start
            self.end = token.end
            self.text += token.text
            # A decimal or known abbreviation is not a sentence boundary.
            while True:
                match = re.search(r'[.!?]["\u201d\u2019]?\s+(?=[A-Z0-9])', self.text)
                if not match:
                    break
                candidate = self.text[:match.end()].strip()
                if len(candidate.split()) < self.min_words:
                    break
                if self.unfinished_clause(candidate):
                    break
                if re.search(r'\b(?:Dr|Mr|Mrs|Ms|Prof|vs|e\.g|i\.e)\.$', candidate) or re.search(r'\b[A-Z]\.$', candidate):
                    break
                self.emit(candidate, self.start, self.end)
                self.text = self.text[match.end():]
                self.start = self.end
            if len(self.text.split()) >= self.min_words and (re.search(r'[!?]["\u201d\u2019]?$', self.text.strip()) or (
                self.text.strip().endswith('.') and not self.unfinished_clause(self.text) and not re.search(r'\b(?:Dr|Mr|Mrs|Ms|Prof|vs|[A-Z])\.$', self.text.strip())
            )):
                self.flush()
            # Long speech without punctuation gets a bounded clause, with
            # previous sentences supplied as translation context.
            if len(self.text.split()) >= self.max_words:
                self.flush()

    def flush(self):
        if self.text.strip() and re.search(r'\w', self.text):
            self.emit(self.text.strip(), self.start, self.end)
        self.text = ""


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, created REAL, title TEXT, settings TEXT);
            CREATE TABLE IF NOT EXISTS segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT,
                start REAL, end REAL, english TEXT, chinese TEXT DEFAULT '',
                status TEXT DEFAULT 'waiting', error TEXT DEFAULT '',
                created REAL, translated REAL);
        ''')
        self.db.execute("UPDATE segments SET status='waiting' WHERE status='translating'")
        self.db.commit()

    def session(self, title, settings):
        sid = uuid.uuid4().hex
        self.db.execute('INSERT INTO sessions VALUES (?,?,?,?)', (sid, time.time(), title, json.dumps(settings, ensure_ascii=False)))
        self.db.commit()
        return sid

    def add(self, sid, text, start, end):
        cur = self.db.execute('INSERT INTO segments(session,start,end,english,created) VALUES (?,?,?,?,?)', (sid, start, end, text, time.time()))
        self.db.commit()
        return self.segment(cur.lastrowid)

    def segment(self, row_id):
        row = self.db.execute('SELECT * FROM segments WHERE id=?', (row_id,)).fetchone()
        return dict(row) if row else None

    def update(self, row_id, status, chinese='', error=''):
        self.db.execute('UPDATE segments SET status=?, chinese=?, error=?, translated=? WHERE id=?', (status, chinese, error, time.time() if status == 'done' else None, row_id))
        self.db.commit()
        return self.segment(row_id)

    def next(self):
        row = self.db.execute("SELECT * FROM segments WHERE status='waiting' ORDER BY id LIMIT 1").fetchone()
        return dict(row) if row else None

    def settings(self, sid):
        row = self.db.execute('SELECT settings FROM sessions WHERE id=?', (sid,)).fetchone()
        return json.loads(row[0])

    def context(self, row):
        rows = self.db.execute('SELECT english,chinese FROM segments WHERE session=? AND id<? ORDER BY id DESC LIMIT 3', (row['session'], row['id'])).fetchall()
        return '\n'.join(r['english'] for r in reversed(rows))[-2800:]

    def rows(self, sid, after=0):
        return [dict(r) for r in self.db.execute('SELECT * FROM segments WHERE session=? AND id>? ORDER BY id', (sid, after))]

    def sessions(self):
        return [dict(r) for r in self.db.execute('SELECT id,created,title FROM sessions ORDER BY created DESC LIMIT 100')]

    def rename_session(self, sid, title):
        title = title.strip()
        if not title or len(title) > 200:
            raise ValueError('课堂名称需要 1–200 个字符')
        cursor = self.db.execute('UPDATE sessions SET title=? WHERE id=?', (title, sid))
        self.db.commit()
        if cursor.rowcount == 0:
            return None
        return dict(self.db.execute('SELECT id,created,title FROM sessions WHERE id=?', (sid,)).fetchone())

    def delete_session(self, sid, remove_audio):
        with self.db:
            if not self.db.execute('SELECT 1 FROM sessions WHERE id=?', (sid,)).fetchone():
                return False
            self.db.execute('DELETE FROM segments WHERE session=?', (sid,))
            self.db.execute('DELETE FROM sessions WHERE id=?', (sid,))
            # Roll back the database if the audio files cannot be removed.
            remove_audio(sid)
        return True


def translation_prompt(text, context='', terms='', course=''):
    prefix = ''
    matched_terms=[]
    for line in terms[:2000].splitlines():
        pair=re.match(r'^\s*(.*?)\s*(?:翻译成|→|->|=|：|:)\s*(.+)$',line)
        if pair and pair[1].strip() and re.search(r'(?<!\w)'+re.escape(pair[1].strip())+r'(?!\w)',text,re.IGNORECASE):
            matched_terms.append(line)
    if matched_terms:
        prefix += '参考下面的翻译（术语对照）：\n'+'\n'.join(matched_terms)+'\n\n'
    references = []
    if course.strip():
        references.append(f'课程背景（仅供参考，不要输出）：{course[:200]}')
    if context.strip():
        references.append(context)
    if references:
        reference = '\n'.join(references)
        return prefix + f'{reference}\n参考上面的信息，把下面的文本翻译成中文，注意不需要翻译上文，也不要额外解释。原文来自实时语音识别，标点可能不准确，请按连贯句意翻译。术语对照仅在原文实际出现该术语时使用。不要添加原文没有的内容，也不要用上文补全或扩写本段：\n{text}'
    return prefix + f'将以下文本翻译为中文，注意只需要输出翻译后的结果，不要额外解释：\n\n{text}'
