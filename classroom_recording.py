# Copyright (c) 2026 He-Zixuan
# SPDX-License-Identifier: LicenseRef-Classroom-Personal-NonCommercial-1.0
"""Incremental local WAV archive for the exact PCM received from the browser."""
import os
from pathlib import Path
import re
import time
import wave


class Recordings:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.open_sessions = set()

    def path(self, sid):
        if not re.fullmatch(r'[0-9a-f]{32}', sid):
            raise ValueError('无效课堂编号')
        return self.directory / f'{sid}.wav'

    def begin(self, sid):
        return Recording(self, sid)

    def delete(self, sid):
        if sid in self.open_sessions:
            raise ValueError('请先结束录音')
        path = self.path(sid)
        path.with_suffix('.complete').unlink(missing_ok=True)
        path.unlink(missing_ok=True)

    def info(self, sid):
        path = self.path(sid)
        size = path.stat().st_size if path.is_file() else 0
        state = ('recording' if sid in self.open_sessions else
                 'saved' if path.with_suffix('.complete').is_file() else
                 'interrupted' if size > 44 else 'none')
        return {'state': state, 'available': size > 44 and state != 'recording',
                'duration': max(0, size - 44) / 32000, 'bytes': size}


class Recording:
    def __init__(self, recordings, sid):
        self.recordings, self.sid = recordings, sid
        self.path = recordings.path(sid)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open('xb')
        self.writer = wave.open(self.file, 'wb')
        self.writer.setnchannels(1)
        self.writer.setsampwidth(2)
        self.writer.setframerate(16000)
        self.writer.writeframes(b'')
        self.file.flush()
        self.last_sync = time.monotonic()
        self.closed = False
        recordings.open_sessions.add(sid)

    def write(self, pcm):
        if self.closed:
            raise ValueError('录音已经结束')
        if len(pcm) % 2:
            raise ValueError('音频数据不完整')
        # writeframes patches the header on each chunk: a lost connection or
        # process termination still leaves a readable archive of prior chunks.
        self.writer.writeframes(pcm)
        self.file.flush()
        if time.monotonic() - self.last_sync >= 2:
            os.fsync(self.file.fileno())
            self.last_sync = time.monotonic()

    def close(self, completed=False):
        if self.closed:
            return
        try:
            self.writer.close()
            self.file.flush()
            os.fsync(self.file.fileno())
            if completed:
                self.path.with_suffix('.complete').write_text('saved', encoding='ascii')
        finally:
            self.closed = True
            self.file.close()
            self.recordings.open_sessions.discard(self.sid)
