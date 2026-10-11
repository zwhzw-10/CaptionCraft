"""Seekable local audio decoding: bounded memory, absolute media timestamps."""
def decode_window(path, start, end):
    import av
    import numpy as np
    arrays = []
    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        if start > 0:
            container.seek(max(0, int((start - 1) * av.time_base)), backward=True)
        resampler = av.AudioResampler(format='fltp', layout='mono', rate=16000)
        cursor = None
        def append(frame):
            nonlocal cursor
            t = float(frame.pts * frame.time_base) if frame.pts is not None else (cursor or 0)
            values = frame.to_ndarray().reshape(-1)
            cursor = t + len(values) / 16000
            lo = max(0, round((start - t) * 16000))
            hi = min(len(values), round((end - t) * 16000))
            if hi > lo:
                arrays.append(values[lo:hi])
        for frame in container.decode(stream):
            for output in resampler.resample(frame):
                append(output)
            if cursor is not None and cursor >= end:
                break
        else:
            for output in resampler.resample(None):
                append(output)
    return np.concatenate(arrays).astype('float32') if arrays else np.zeros(0, dtype='float32')

def audio_duration(path):
    import av
    with av.open(str(path)) as container:
        if container.duration:
            return container.duration / av.time_base
        stream = container.streams.audio[0]
        if stream.duration is not None:
            return float(stream.duration * stream.time_base)
    return None
