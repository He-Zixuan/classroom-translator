import asyncio
import importlib.util
from pathlib import Path
import sqlite3
import struct
import sys
from types import SimpleNamespace
import wave

import pytest
from fastapi.testclient import TestClient

import classroom_core
from classroom_recording import Recordings


def test_incremental_wav_preserves_pcm_and_survives_interruption(tmp_path):
    archive = Recordings(tmp_path)
    sid = 'a' * 32
    writer = archive.begin(sid)
    pcm = struct.pack('<4h', 1, -22, 32767, -32768)
    writer.write(pcm)
    # The header is already playable before finalization.
    with wave.open(str(archive.path(sid))) as reader:
        assert (reader.getnchannels(), reader.getsampwidth(), reader.getframerate()) == (1, 2, 16000)
        assert reader.readframes(4) == pcm
    assert archive.info(sid)['state'] == 'recording'
    assert not archive.info(sid)['available']
    writer.close()
    recovered = Recordings(tmp_path).info(sid)
    assert recovered['state'] == 'interrupted'
    assert recovered['available']
    assert recovered['duration'] == 4 / 16000


def test_complete_independent_files_and_invalid_input(tmp_path):
    archive = Recordings(tmp_path)
    first, second = 'a' * 32, 'b' * 32
    one = archive.begin(first)
    one.write(b'\x01\x00' * 16000)
    one.close(completed=True)
    one.close()
    two = archive.begin(second)
    two.write(b'\x02\x00' * 8000)
    two.close(completed=True)
    assert Recordings(tmp_path).info(first)['duration'] == 1
    assert Recordings(tmp_path).info(second)['duration'] == .5
    assert archive.info(first)['state'] == 'saved'
    with pytest.raises(FileExistsError):
        archive.begin(first)
    with pytest.raises(ValueError):
        archive.path('../secrets')
    with pytest.raises(ValueError):
        one.write(b'\x00\x00')
    three = archive.begin('c' * 32)
    with pytest.raises(ValueError):
        three.write(b'\x00')
    three.close()


@pytest.fixture
def service(tmp_path, monkeypatch):
    # Import the application against an isolated DB; never open user history.
    store = classroom_core.Store(tmp_path / 'history.sqlite3')
    store.db.close()
    store.db = sqlite3.connect(tmp_path / 'history.sqlite3', check_same_thread=False)
    store.db.row_factory = sqlite3.Row
    monkeypatch.setattr(classroom_core, 'Store', lambda _: store)
    spec = importlib.util.spec_from_file_location('recording_test_app', Path(__file__).resolve().parents[1] / 'classroom_app.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.recordings = Recordings(tmp_path / 'recordings')
    module.state['ready'] = True

    async def idle_runtime():
        await asyncio.Event().wait()

    module.initialize = idle_runtime
    module.translation_worker = idle_runtime

    class Processor:
        def __init__(self, **kwargs):
            self.vac = None
            self.is_stopping = False
            self.done = asyncio.Event()

        async def create_tasks(self):
            async def results():
                await self.done.wait()
                if False:
                    yield
            return results()

        async def process_audio(self, pcm):
            if not pcm:
                self.is_stopping = True
                self.done.set()

        async def cleanup(self):
            pass

    monkeypatch.setitem(sys.modules, 'whisperlivekit', SimpleNamespace(AudioProcessor=Processor))
    yield module
    store.db.close()


def test_websocket_saves_exact_audio_download_and_preserves_subtitles(service):
    pcm = struct.pack('<4h', 16, -16, 700, -700) * 4000
    with TestClient(service.app) as client:
        with client.websocket_connect('/classroom') as socket:
            socket.send_json({'title': '原始录音测试', 'course': 'economics'})
            sid = socket.receive_json()['id']
            socket.send_bytes(pcm)
            socket.send_text('stop')
            assert socket.receive_json()['type'] == 'stopped'
            info = client.get(f'/sessions/{sid}/audio/info').json()
            assert info['state'] == 'saved' and info['duration'] == 1
            row = service.store.add(sid, 'A complete English sentence.', 0, 1)
            service.store.update(row['id'], 'done', '完整的英文句子。')
            client.patch(f'/sessions/{sid}', json={'title': '改名后的课堂'})
            response = client.get(f'/sessions/{sid}/audio')
            assert response.status_code == 200
            assert response.headers['content-type'] == 'audio/wav'
            assert response.content[44:] == pcm
            assert client.get(f'/sessions/{sid}').json()[0]['chinese'] == '完整的英文句子。'
            socket.send_text('close')
        assert service.recordings.open_sessions == set()
        # Old lessons and unknown IDs do not invent an audio archive.
        old = service.store.session('旧课堂', {})
        assert client.get(f'/sessions/{old}/audio/info').json()['state'] == 'none'
        assert client.get(f'/sessions/{old}/audio').status_code == 404
        assert client.get('/sessions/' + 'f' * 32 + '/audio').status_code == 404


def test_disconnect_keeps_partial_audio_and_rejects_live_download(service):
    with TestClient(service.app) as client:
        with client.websocket_connect('/classroom') as socket:
            socket.send_json({'title': '中断测试'})
            sid = socket.receive_json()['id']
            socket.send_bytes(b'\x01\x00' * 16000)
            assert client.get(f'/sessions/{sid}/audio').status_code == 409
        assert service.recordings.info(sid)['state'] == 'interrupted'
        assert client.get(f'/sessions/{sid}/audio').content[44:] == b'\x01\x00' * 16000
