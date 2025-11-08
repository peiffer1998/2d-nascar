import wave
import math
from pathlib import Path

FRAMERATE = 22050

def sine_wave(freq, duration, volume=0.4, freq_mod=None):
    samples = int(FRAMERATE * duration)
    data = bytearray()
    for i in range(samples):
        t = i / FRAMERATE
        current_freq = freq_mod(t) if freq_mod else freq
        angle = 2 * math.pi * current_freq * t
        amplitude = volume * math.sin(angle)
        val = int(amplitude * 127 + 128)
        data.append(max(0, min(255, val)))
    return bytes(data)

def write_wave(path, data):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(1)
        f.setframerate(FRAMERATE)
        f.writeframes(data)
    print(f"Wrote {path}")

def create_engine(path):
    def mod(t):
        return 60 + 12 * math.sin(2 * math.pi * t * 0.5)
    data = sine_wave(80, 2.5, volume=0.35, freq_mod=mod)
    write_wave(path, data)

def create_draft(path):
    def mod(t):
        return 320 + 80 * math.sin(2 * math.pi * t * 1.2)
    data = sine_wave(360, 0.9, volume=0.25, freq_mod=mod)
    write_wave(path, data)

def create_click(path):
    data = sine_wave(880, 0.18, volume=0.6)
    write_wave(path, data)

def create_start(path):
    def mod(t):
        return 220 + 110 * t
    data = sine_wave(220, 0.8, volume=0.35, freq_mod=mod)
    write_wave(path, data)

def create_finish(path):
    def mod(t):
        return 180 + 50 * math.cos(2 * math.pi * t * 1.3)
    data = sine_wave(250, 1.0, volume=0.4, freq_mod=mod)
    write_wave(path, data)

def ensure_audio_dir():
    target = Path("assets/audio")
    target.mkdir(parents=True, exist_ok=True)
    return target

def main():
    assets_dir = ensure_audio_dir()
    create_engine(assets_dir / "engine_hum.wav")
    create_draft(assets_dir / "draft_sizzle.wav")
    create_click(assets_dir / "ui_click.wav")
    create_start(assets_dir / "start_chime.wav")
    create_finish(assets_dir / "finish_chime.wav")

if __name__ == "__main__":
    main()
