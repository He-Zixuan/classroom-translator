import numpy as np
from classroom_audio import ConditionedVAD

def test_input_conditioning_preserves_pcm_length_and_boosts_quiet_speech():
    from classroom_audio import condition_pcm
    raw=np.full(4000,327,dtype='<i2').tobytes()
    boosted=condition_pcm(raw)
    assert len(boosted)==len(raw)
    np.testing.assert_array_equal(np.frombuffer(boosted,dtype='<i2'),np.full(4000,2616))

def test_input_conditioning_preserves_normal_level_and_limits_peaks():
    from classroom_audio import condition_pcm
    raw=np.full(4000,8000,dtype='<i2').tobytes()
    assert condition_pcm(raw)==raw
    audio=np.zeros(4000,dtype='<i2');audio[0]=20000
    assert np.max(np.frombuffer(condition_pcm(audio.tobytes()),dtype='<i2'))==32767

def test_gate_boost_is_bounded_and_original_asr_audio_unchanged():
    received=[];audio=np.full(4000,.01,dtype=np.float32);original=audio.copy()
    gate=ConditionedVAD(lambda x:received.append(x) or [])
    assert gate(audio)==[]
    np.testing.assert_array_equal(audio,original)
    np.testing.assert_allclose(received[0],original*8,rtol=1e-6)

def test_normal_volume_is_not_attenuated_and_silence_stays_zero():
    received=[];gate=ConditionedVAD(lambda x:received.append(x) or [])
    audio=np.full(4000,.2,dtype=np.float32);gate(audio);gate(np.zeros(4000,dtype=np.float32))
    np.testing.assert_array_equal(received[0],audio)
    assert not np.any(received[1])

def test_amplified_spikes_cannot_exceed_detector_range():
    received=[];audio=np.zeros(4000,dtype=np.float32);audio[0]=.3
    ConditionedVAD(lambda x:received.append(x) or [])(audio)
    assert np.max(np.abs(received[0]))<=1
