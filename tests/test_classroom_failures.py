import asyncio
import time
from types import SimpleNamespace
import numpy as np
import pytest
from whisperlivekit.audio_processor import AudioProcessor, SENTINEL
from whisperlivekit.simul_whisper.backend import SimulStreamingOnlineProcessor

def test_model_failure_is_exposed_and_clears_on_next_success():
    online=SimulStreamingOnlineProcessor.__new__(SimulStreamingOnlineProcessor)
    online.end=1.0
    def fail(**kwargs):
        raise RuntimeError('injected model failure')
    online.model=SimpleNamespace(infer=fail)
    assert online.process_iter()==([],1.0)
    assert online.last_error=='injected model failure'
    online.model.infer=lambda **kwargs: []
    assert online.process_iter()==([],1.0)
    assert online.last_error is None
    # Its normal destructor expects a fully constructed backend.
    online.asr=SimpleNamespace(use_full_mlx=True)

@pytest.mark.asyncio
async def test_processing_failure_does_not_acknowledge_queue_twice():
    p=AudioProcessor.__new__(AudioProcessor)
    p.args=SimpleNamespace(asr_coalesce_min_s=0)
    p.sample_rate=16000
    p.beg_loop=time.time()
    p.state=SimpleNamespace(end_buffer=0,tokens=[])
    p.transcription_queue=asyncio.Queue()
    await p.transcription_queue.put(np.zeros(1600,dtype=np.float32))
    await p.transcription_queue.put(SENTINEL)
    def fail(*args):
        raise RuntimeError('injected audio insertion failure')
    p.transcription=SimpleNamespace(audio_buffer=[],SAMPLING_RATE=16000,insert_audio_chunk=fail)
    p.is_stopping=True
    p.diarization_queue=p.translation_queue=None
    flushed=[]
    async def finish(**kwargs):
        flushed.append(True)
    p._finish_transcription=finish
    await asyncio.wait_for(p.transcription_processor(),2)
    await asyncio.wait_for(p.transcription_queue.join(),1)
    assert p._transcription_error=='injected audio insertion failure'
    assert flushed

@pytest.mark.asyncio
async def test_processing_error_reaches_frontend_formatter():
    p=AudioProcessor.__new__(AudioProcessor)
    p._transcription_error='injected failure'
    generator=p.results_formatter()
    response=await anext(generator)
    assert response.status=='error'
    assert response.error=='Transcription error: injected failure'
    await generator.aclose()
