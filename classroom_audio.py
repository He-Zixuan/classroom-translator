# Copyright (c) 2026 He-Zixuan
# SPDX-License-Identifier: LicenseRef-Classroom-Personal-NonCommercial-1.0
"""Bounded gain for quiet classroom PCM and its speech detector."""
import numpy as np

def condition_pcm(pcm):
    if not pcm:
        return pcm
    audio=np.frombuffer(pcm,dtype='<i2').astype(np.float64)
    rms=float(np.sqrt(np.mean(audio*audio)))/32768
    gain=min(8.0,max(1.0,0.1/max(rms,1e-8)))
    if gain==1.0:
        return pcm
    return np.clip(audio*gain,-32768,32767).astype('<i2').tobytes()

class ConditionedVAD:
    def __init__(self, detector, silence_ms=800):
        self.detector = detector
        # Ordinary hesitations should not force Whisper to finalize a phrase.
        if hasattr(detector,'min_silence_samples'):
            detector.min_silence_samples=detector.sampling_rate*silence_ms/1000

    def __call__(self, audio):
        if not audio.size:
            return self.detector(audio)
        rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
        gain = min(8.0, max(1.0, 0.1 / max(rms, 1e-8)))
        # The gate needs audible input to avoid discarding distant speech.
        # Keep the incoming array untouched and retain archive timestamps.
        conditioned = np.clip(audio * gain, -1.0, 1.0).astype(np.float32)
        return self.detector(conditioned)
