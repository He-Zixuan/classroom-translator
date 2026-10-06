from fastapi.testclient import TestClient
import pytest

from test_classroom_recording import service


def make_lesson(service, title, with_audio=True):
    sid = service.store.session(title, {})
    row = service.store.add(sid, 'A saved English sentence.', 0, 1)
    service.store.update(row['id'], 'done', '已保存的中文。')
    if with_audio:
        audio = service.recordings.begin(sid)
        audio.write(b'\x02\x00' * 16000)
        audio.close(completed=True)
    return sid, row['id']


def test_delete_removes_only_confirmed_lesson_audio_and_queue(service):
    selected, row_id = make_lesson(service, '待删除课堂')
    retained, _ = make_lesson(service, '需要保留的课堂')
    service.store.update(row_id, 'waiting')
    with TestClient(service.app) as client:
        response = client.request('DELETE', f'/sessions/{selected}', json={'confirm': True})
        assert response.status_code == 200
        assert selected not in [s['id'] for s in client.get('/sessions').json()]
        assert service.store.segment(row_id) is None
        assert service.store.next() is None
        assert not service.recordings.path(selected).exists()
        assert not service.recordings.path(selected).with_suffix('.complete').exists()
        assert client.get(f'/sessions/{selected}').status_code == 404
        assert client.get(f'/sessions/{selected}/audio').status_code == 404
        assert client.get(f'/sessions/{selected}/export').status_code == 404
        assert client.get(f'/sessions/{retained}').json()[0]['chinese'] == '已保存的中文。'
        assert client.get(f'/sessions/{retained}/audio').status_code == 200
        # An in-flight translation result cannot recreate a deleted row.
        assert service.store.update(row_id, 'done', '晚到的译文') is None
        assert service.store.rows(selected) == []


def test_confirmation_origin_and_recording_guards(service):
    sid, _ = make_lesson(service, '受保护课堂')
    with TestClient(service.app) as client:
        for payload in [{}, {'confirm': False}, {'confirm': 1}, {'confirm': 'true'}, []]:
            assert client.request('DELETE', f'/sessions/{sid}', json=payload).status_code == 400
        assert client.delete(f'/sessions/{sid}').status_code == 400
        assert client.request('DELETE', f'/sessions/{sid}', json={'confirm': True}, headers={'Origin': 'https://example.com'}).status_code == 403
        service.active = True
        assert client.request('DELETE', f'/sessions/{sid}', json={'confirm': True}).status_code == 409
        service.active = False
        service.recordings.open_sessions.add(sid)
        assert client.request('DELETE', f'/sessions/{sid}', json={'confirm': True}).status_code == 409
        service.recordings.open_sessions.clear()
        assert service.store.rows(sid)
        assert service.recordings.path(sid).exists()


def test_file_failure_keeps_database_and_can_retry(service, monkeypatch):
    sid, _ = make_lesson(service, '文件被占用')
    original = service.recordings.delete
    def failure(_):
        raise PermissionError('test locked audio')
    monkeypatch.setattr(service.recordings, 'delete', failure)
    with TestClient(service.app) as client:
        assert client.request('DELETE', f'/sessions/{sid}', json={'confirm': True}).status_code == 500
        assert service.store.rows(sid)
        assert service.recordings.path(sid).exists()
        monkeypatch.setattr(service.recordings, 'delete', original)
        assert client.request('DELETE', f'/sessions/{sid}', json={'confirm': True}).status_code == 200


def test_legacy_no_audio_missing_and_repeated_delete(service):
    sid, _ = make_lesson(service, '没有录音的旧课堂', with_audio=False)
    with TestClient(service.app) as client:
        assert client.request('DELETE', f'/sessions/{sid}', json={'confirm': True}).status_code == 200
        assert client.request('DELETE', f'/sessions/{sid}', json={'confirm': True}).status_code == 404
        assert client.request('DELETE', '/sessions/'+'f'*32, json={'confirm': True}).status_code == 404
