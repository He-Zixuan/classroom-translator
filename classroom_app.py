# Copyright (c) 2026 He-Zixuan
# SPDX-License-Identifier: LicenseRef-Classroom-Personal-NonCommercial-1.0
"""Local-only classroom frontend and HY-MT worker over WhisperLiveKit."""
import asyncio
import contextlib
import json
import logging
import os
from pathlib import Path
import subprocess
import time
import secrets

ROOT = Path(__file__).resolve().parent
os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
os.environ.setdefault('HF_HOME', str(ROOT / 'runtime' / 'hf-cache'))
os.environ.setdefault('PYTORCH_ALLOC_CONF', 'garbage_collection_threshold:0.65,max_split_size_mb:128')

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from classroom_core import SentenceBuffer, Store, translation_prompt
from classroom_audio import ConditionedVAD, condition_pcm
from classroom_recording import Recordings

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('classroom')
store = Store(ROOT / 'history' / 'classroom.sqlite3')
recordings = Recordings(ROOT / 'history' / 'recordings')
DEFAULT_ASR_MODEL = 'large-v3-turbo'
state = {'ready': False, 'stage': '正在加载本地模型…', 'error': '', 'model': DEFAULT_ASR_MODEL, 'translation_ready': False}
engine = None
llama = None
active = False
active_owner = None
peers = set()
translation_wake = asyncio.Event()
LLAMA_URL = 'http://127.0.0.1:8767'
LOCAL_KEY = secrets.token_urlsafe(32)
server = None


async def broadcast(message):
    for peer in list(peers):
        try:
            await asyncio.wait_for(peer.send_json(message), timeout=2)
        except Exception:
            peers.discard(peer)


async def translation_worker():
    async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
        while True:
            row = store.next() if state['translation_ready'] else None
            if not row:
                translation_wake.clear()
                try:
                    await asyncio.wait_for(translation_wake.wait(), 1)
                except asyncio.TimeoutError:
                    pass
                continue
            settings = store.settings(row['session'])
            prompt = translation_prompt(row['english'], store.context(row), settings.get('terms', ''), settings.get('course', ''))
            await broadcast({'type': 'segment', 'row': store.update(row['id'], 'translating')})
            try:
                response = await client.post(LLAMA_URL + '/v1/chat/completions', headers={'Authorization': 'Bearer ' + LOCAL_KEY}, json={
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': 0.7, 'top_p': 0.6, 'top_k': 20,
                    'repeat_penalty': 1.05, 'max_tokens': 700,
                })
                response.raise_for_status()
                result = response.json()['choices'][0]
                chinese = result['message']['content'].strip()
                if not chinese or result.get('finish_reason') == 'length':
                    raise ValueError('译文为空或超出长度限制，请缩短段落后重试')
                updated = store.update(row['id'], 'done', chinese)
            except Exception as exc:
                log.exception('Translation failed')
                updated = store.update(row['id'], 'error', error=str(exc)[:250])
            if updated:
                await broadcast({'type': 'segment', 'row': updated})


def load_english():
    global engine
    import torch
    from whisperlivekit import TranscriptionEngine
    from whisperlivekit.config import WhisperLiveKitConfig
    if not torch.cuda.is_available():
        raise RuntimeError('未检测到可用 NVIDIA GPU，请查看 runtime/app.log')
    torch.set_num_threads(6)
    torch.cuda.set_per_process_memory_fraction(0.65)
    torch.backends.cuda.matmul.allow_tf32 = True
    model = os.getenv('CLASSROOM_ASR_MODEL', DEFAULT_ASR_MODEL)
    path = ROOT / 'models' / f'{model}.pt'
    if not path.is_file():
        raise FileNotFoundError(f'缺少英文模型：{path}')
    # Use the official model-name lookup to retain tuned alignment heads;
    # its verified cache file exists locally, so no remote request is needed.
    backend=os.getenv('CLASSROOM_ASR_BACKEND','faster-whisper')
    model_dir=str(ROOT/'models'/f'{model}-ct2') if backend=='faster-whisper' else None
    config = WhisperLiveKitConfig(
        model_size=model, model_cache_dir=str(ROOT / 'models'), lan='en',
        model_dir=model_dir, backend=backend, disable_fast_encoder=True, pcm_input=True,
        backend_policy=os.getenv('CLASSROOM_ASR_POLICY', 'localagreement'),
        vac=os.getenv('CLASSROOM_VAC','1')=='1',
        min_chunk_size=0.25, asr_coalesce_min_s=1.0,
        pause_segmentation_seconds=1.5, frame_threshold=15,
        max_context_tokens=224, log_level='WARNING',
        retention_seconds=90,
    )
    engine = TranscriptionEngine(config=config)
    engine.asr.preserve_unstable_prefix=True
    loaded_model=getattr(engine.asr,'shared_model',None)
    if loaded_model is None:
        loaded_model=engine.asr.model
    if hasattr(loaded_model,'half'):
        loaded_model.half()
    torch.cuda.empty_cache()
    warmup = ROOT / 'runtime' / 'warmup.wav'
    if warmup.is_file():
        import soundfile as sf
        from whisperlivekit.core import online_factory
        audio, rate = sf.read(warmup, dtype='float32')
        if rate != 16000:
            raise ValueError('预热音频需为 16kHz')
        online = online_factory(engine.args, engine.asr)
        online.insert_audio_chunk(audio, len(audio) / 16000)
        with torch.inference_mode(), torch.autocast('cuda', dtype=torch.float16):
            if config.backend_policy=='simulstreaming':
                online.process_iter(is_last=True)
            else:
                online.process_iter()
        if getattr(online, 'last_error', None):
            raise RuntimeError(online.last_error)
        del online
    state.update(model=model, backend=backend, policy=config.backend_policy, speech_gate=config.vac, gpu=torch.cuda.get_device_name(), ready=True)


async def initialize():
    global llama
    try:
        await asyncio.to_thread(load_english)
        state['stage'] = '英文模型就绪，正在加载中文模型…'
        exe = ROOT / 'runtime' / 'llama' / 'llama-server.exe'
        if not exe.is_file():
            exe = next((ROOT / 'runtime' / 'llama').rglob('llama-server.exe'))
        logfile = open(ROOT / 'runtime' / 'translation.log', 'a', encoding='utf-8')
        llama = subprocess.Popen([
            str(exe), '-m', str(ROOT / 'models' / 'HY-MT1.5-1.8B-Q4_K_M.gguf'),
            '--host', '127.0.0.1', '--port', '8767', '-c', '4096',
            '-ngl', '99', '-t', '6', '--parallel', '1', '--no-webui',
            '--api-key', LOCAL_KEY,
        ], cwd=exe.parent, stdout=logfile, stderr=logfile,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
            for _ in range(180):
                if llama.poll() is not None:
                    raise RuntimeError('中文模型进程退出，请查看 runtime/translation.log')
                try:
                    if (await client.get(LLAMA_URL + '/health')).status_code == 200:
                        state['stage'] = '正在预热中文翻译…'
                        warm = await client.post(LLAMA_URL + '/v1/chat/completions',
                            headers={'Authorization': 'Bearer ' + LOCAL_KEY},
                            json={'messages': [{'role': 'user', 'content': translation_prompt('Welcome to the class.')}], 'max_tokens': 32}, timeout=120)
                        warm.raise_for_status()
                        state.update(translation_ready=True, stage='本地模型已就绪')
                        translation_wake.set()
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(1)
        raise RuntimeError('中文模型启动超时，英文仍可使用')
    except Exception as exc:
        log.exception('Initialization failed')
        state.update(stage='模型准备失败', error=str(exc))


@contextlib.asynccontextmanager
async def lifespan(app):
    init_task = asyncio.create_task(initialize())
    worker = asyncio.create_task(translation_worker())
    yield
    init_task.cancel()
    worker.cancel()
    await asyncio.gather(init_task, worker, return_exceptions=True)
    if llama and llama.poll() is None:
        llama.terminate()
        try:
            await asyncio.to_thread(llama.wait, 8)
        except subprocess.TimeoutExpired:
            llama.kill()
    store.db.close()


app = FastAPI(lifespan=lifespan)
app.mount('/assets', StaticFiles(directory=ROOT / 'classroom_web'), name='assets')


@app.get('/')
async def home():
    return FileResponse(ROOT / 'classroom_web' / 'index.html')


@app.get('/health')
async def health():
    return {**state, 'active': active, 'pending': store.db.execute("SELECT count(*) FROM segments WHERE status IN ('waiting','translating')").fetchone()[0]}


@app.post('/shutdown')
async def shutdown(request: Request):
    if request.headers.get('x-local-key') != LOCAL_KEY:
        raise HTTPException(403)
    if active:
        raise HTTPException(409, '请先结束录音，再关闭服务')
    if server:
        server.should_exit = True
    return {'ok': True}


@app.get('/sessions')
async def sessions():
    return store.sessions()


def recording_info(sid):
    if not store.db.execute('SELECT 1 FROM sessions WHERE id=?', (sid,)).fetchone():
        raise HTTPException(404, '课堂记录不存在')
    try:
        return recordings.info(sid)
    except ValueError:
        raise HTTPException(404, '课堂记录不存在')


@app.get('/sessions/{sid}/audio/info')
async def audio_info(sid: str):
    return recording_info(sid)


@app.get('/sessions/{sid}/audio')
async def download_audio(sid: str):
    info = recording_info(sid)
    if info['state'] == 'recording':
        raise HTTPException(409, '请先结束录音，再下载文件')
    if not info['available']:
        raise HTTPException(404, '这堂课没有保存的录音')
    return FileResponse(recordings.path(sid), media_type='audio/wav',
                        filename=f'classroom-{sid[:8]}.wav')


@app.get('/sessions/{sid}')
async def history(sid: str):
    if not store.db.execute('SELECT 1 FROM sessions WHERE id=?', (sid,)).fetchone():
        raise HTTPException(404, '课堂记录不存在')
    return store.rows(sid)


@app.delete('/sessions/{sid}')
async def delete_session(sid: str, request: Request):
    origin = request.headers.get('origin', '')
    if origin and origin not in ('http://127.0.0.1:8766', 'http://localhost:8766'):
        raise HTTPException(403, '请在本机页面删除课堂')
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(400, '请先确认永久删除')
    if not isinstance(payload, dict) or payload.get('confirm') is not True:
        raise HTTPException(400, '请先确认永久删除')
    if active or sid in recordings.open_sessions:
        raise HTTPException(409, '请先结束录音并等待保存完成，再删除课堂')
    try:
        removed = store.delete_session(sid, recordings.delete)
    except OSError:
        log.exception('Classroom deletion failed')
        raise HTTPException(500, '录音文件暂时无法删除，请关闭占用文件的软件后重试')
    except ValueError:
        raise HTTPException(400, '无效课堂编号')
    if not removed:
        raise HTTPException(404, '课堂记录不存在')
    return {'ok': True, 'id': sid}


@app.patch('/sessions/{sid}')
async def rename_session(sid: str, request: Request):
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(400, '课堂名称格式不正确')
    if not isinstance(payload, dict) or not isinstance(payload.get('title'), str):
        raise HTTPException(400, '请填写课堂名称')
    try:
        renamed = store.rename_session(sid, payload['title'])
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if renamed is None:
        raise HTTPException(404, '课堂记录不存在')
    return renamed


@app.post('/segments/{row_id}/retry')
async def retry(row_id: int):
    found = store.db.execute('SELECT status FROM segments WHERE id=?', (row_id,)).fetchone()
    if not found:
        raise HTTPException(404)
    if found[0] == 'error':
        store.update(row_id, 'waiting')
        translation_wake.set()
    return {'ok': True}


@app.get('/sessions/{sid}/export')
async def export(sid: str, format: str = 'md'):
    if not store.db.execute('SELECT 1 FROM sessions WHERE id=?', (sid,)).fetchone():
        raise HTTPException(404, '课堂记录不存在')
    rows = store.rows(sid)
    if format == 'json':
        data = json.dumps(rows, ensure_ascii=False, indent=2)
        mime = 'application/json'
    else:
        data = '# 课堂中英对照\n\n' + '\n\n'.join(f"[{r['start']:.1f}s–{r['end']:.1f}s]\n\n{r['english']}\n\n{r['chinese'] or '（中文尚未完成）'}" for r in rows)
        mime = 'text/markdown'
        format = 'md'
    return Response(data, media_type=mime, headers={'Content-Disposition': f'attachment; filename="classroom-{sid[:8]}.{format}"'})


@app.websocket('/classroom')
async def classroom(ws: WebSocket):
    global active, active_owner
    origin = ws.headers.get('origin', '')
    if origin and origin not in ('http://127.0.0.1:8766', 'http://localhost:8766'):
        await ws.close(code=4403)
        return
    await ws.accept()
    if not state['ready'] or active:
        await ws.send_json({'type': 'error', 'error': '模型还未就绪，或另一个窗口正在录音'})
        await ws.close()
        return
    active = True
    state['unconfirmed_recoveries']=0
    if state['translation_ready']:
        state['stage']='本地模型已就绪'
    active_owner = ws
    peers.add(ws)
    processor = None
    sender = None
    archive = None
    try:
        payload = await ws.receive_json()
        settings = {key: str(payload.get(key, ''))[:2000] for key in ('course', 'terms')}
        lesson_title = str(payload.get('title', ''))[:200].strip()
        sid = store.session(lesson_title or settings['course'] or '课堂录音', settings)
        archive = recordings.begin(sid)
        await ws.send_json({'type': 'session', 'id': sid})
        from whisperlivekit import AudioProcessor

        def emit(text, start, end):
            row = store.add(sid, text, start, end)
            translation_wake.set()
            # Network sends are performed by the formatter, never ASR.
            new_rows.append(row)

        new_rows = []
        buffer = SentenceBuffer(emit, max_words=80, min_words=18, pause_seconds=3)

        class ClassroomProcessor(AudioProcessor):
            backend_error = ''
            last_cache_release = 0.0

            async def _run_counted_transcription_call(self, method, *args):
                def infer(*values):
                    import torch
                    try:
                        with torch.inference_mode(), torch.autocast('cuda', dtype=torch.float16):
                            result=method(*values)
                            if getattr(self.transcription,'last_unstable_recovery',False):
                                state['unconfirmed_recoveries']+=1
                                state['stage']='本地模型已就绪 · 有英文未稳定，请结合原音核对'
                            return result
                    finally:
                        state.update(torch_allocated_mib=round(torch.cuda.memory_allocated()/1048576), torch_reserved_mib=round(torch.cuda.memory_reserved()/1048576))
                        # Variable streaming shapes otherwise let the CUDA
                        # caching allocator crowd out the Vulkan translator.
                        if time.perf_counter() - self.last_cache_release > 2:
                            torch.cuda.empty_cache()
                            self.last_cache_release = time.perf_counter()
                result = await super()._run_counted_transcription_call(infer, *args)
                if getattr(self.transcription, 'last_error', None):
                    self.backend_error = '英文识别失败，已停止收音。请关闭服务后重新启动；未定稿尾部可能尚未保存。'
                    state.update(ready=False, stage='英文识别出错，请重新启动', error=self.backend_error)
                    await self.process_audio(b'')
                return result

            async def _finish_transcription(self, pending_tokens=None):
                if self.backend_error:
                    buffer.flush()
                    return
                await super()._finish_transcription(pending_tokens)

            async def _queue_tokens_for_translation(self, tokens):
                buffer.insert(tokens)

            async def _flush_pending_translation_tokens(self):
                buffer.flush()

        processor = ClassroomProcessor(transcription_engine=engine, language='en')
        if processor.vac is not None:
            processor.vac = ConditionedVAD(processor.vac)
        results = await processor.create_tasks()

        async def send_results():
            failure_sent = False
            async for response in results:
                if processor.backend_error and not failure_sent:
                    failure_sent = True
                    await ws.send_json({'type': 'fatal', 'error': processor.backend_error})
                if response.error:
                    await ws.send_json({'type': 'error', 'error': response.error})
                while new_rows:
                    await ws.send_json({'type': 'segment', 'row': store.segment(new_rows.pop(0)['id'])})
                # Committed unfinished tokens + unstable tail: independent of HY-MT.
                live = (buffer.text + (response.buffer_transcription or '')).strip()
                await ws.send_json({'type': 'english', 'text': live, 'lag': response.remaining_time_transcription})
            buffer.flush()
            while new_rows:
                await ws.send_json({'type': 'segment', 'row': store.segment(new_rows.pop(0)['id'])})
            await ws.send_json({'type': 'stopped'})

        sender = asyncio.create_task(send_results())
        while True:
            message = await ws.receive()
            if message['type'] == 'websocket.disconnect':
                break
            if message.get('bytes') is not None:
                if archive.closed:
                    raise ValueError('录音已经结束，请新建课堂')
                if len(message['bytes']) > 128000:
                    raise ValueError('音频数据包过大')
                archive.write(message['bytes'])
                await processor.process_audio(condition_pcm(message['bytes']))
            elif message.get('text') == 'stop':
                archive.close(completed=True)
                await processor.process_audio(b'')
                await asyncio.wait_for(sender, 90)
                # Keep connection alive for remaining Chinese results. New
                # sessions may start while the old translation queue drains.
                active = False
                active_owner = None
            elif message.get('text') == 'close':
                break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.exception('Session failed')
        with contextlib.suppress(Exception):
            await ws.send_json({'type': 'error', 'error': str(exc)})
    finally:
        if archive:
            try:
                archive.close()
            except OSError:
                log.exception('Recording finalization failed')
        if processor:
            if not processor.is_stopping:
                with contextlib.suppress(Exception):
                    await processor.process_audio(b'')
                    if sender:
                        await asyncio.wait_for(asyncio.shield(sender), 30)
            buffer.flush()
            await processor.cleanup()
        if sender and not sender.done():
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)
        peers.discard(ws)
        # A closed old session must not release a newer microphone session.
        if active_owner is ws:
            active = False
            active_owner = None


if __name__ == '__main__':
    import uvicorn
    (ROOT / 'runtime' / 'server.pid').write_text(str(os.getpid()), encoding='ascii')
    (ROOT / 'runtime' / 'local.key').write_text(LOCAL_KEY, encoding='ascii')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8766, log_level='warning'))
    server.run()
