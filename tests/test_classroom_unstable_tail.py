import numpy as np
from types import SimpleNamespace
from whisperlivekit.local_agreement.online_asr import OnlineASRProcessor,HypothesisBuffer
from whisperlivekit.timed_objects import ASRToken

def test_unstable_prefix_reset_preserves_latest_recognized_tail():
    latest=[ASRToken(0,2,' This'),ASRToken(2,3,' is'),ASRToken(4,6,' my name is Alex.')]
    asr=SimpleNamespace(tokenizer=None,confidence_validation=False,buffer_trimming='segment',buffer_trimming_sec=15,sep='',transcribe=lambda *args,**kwargs:latest,ts_words=lambda r:r,segments_end_ts=lambda r:[20])
    online=OnlineASRProcessor(asr)
    online.insert_audio_chunk(np.zeros(20*16000,dtype=np.float32))
    # No preceding hypothesis can confirm the prefix before the size guard.
    committed,end=online.process_iter()
    assert 'my name is Alex' in ''.join(t.text for t in committed)
    assert end==20
    assert not online.audio_buffer.size
    assert not online.finish()[0]
    assert online.last_unstable_recovery

def test_unstable_first_word_does_not_block_a_time_aligned_stable_phrase():
    def words(first):
        return [ASRToken(i,i+.5,' '+w) for i,w in enumerate([first,'English','and','my','name','is','Alex.'])]
    buffer=HypothesisBuffer(preserve_unstable_prefix=True)
    buffer.insert(words('Polish'),0);assert not buffer.flush()
    buffer.insert(words('Paulist'),0)
    committed=buffer.flush()
    assert 'my name is Alex' in ''.join(t.text for t in committed)
    assert buffer.last_unstable_recovery
    buffer.insert(words('Paulist'),0)
    assert not buffer.flush()

def test_unstable_prefix_cannot_use_similar_words_at_a_different_time():
    buffer=HypothesisBuffer(preserve_unstable_prefix=True)
    first=[ASRToken(i,i+.5,' '+w) for i,w in enumerate(['noisy','my','name','is','Alex.'])]
    second=[ASRToken(i+4,i+4.5,' '+w) for i,w in enumerate(['different','my','name','is','Alex.'])]
    buffer.insert(first,0);buffer.flush();buffer.insert(second,0)
    assert not buffer.flush()
