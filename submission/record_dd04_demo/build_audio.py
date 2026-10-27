"""把逐场景 TTS 旁白按录屏时间轴拼成一条 WAV（22050Hz/16bit/mono）。

输入：release/_rec/run/timeline.json、release/_rec/scenes.ready.json、release/_rec/tts/*.wav
输出：release/_rec/run/narration.wav
"""
import json
import os
import wave
from pathlib import Path

REC = Path(os.environ.get("REC_DIR", "release/_rec")).resolve()
RUN = REC / (os.environ.get("OUT_NAME") or "run")
timeline = json.loads((RUN / "timeline.json").read_text(encoding="utf-8"))
scene_file = REC / timeline.get("sceneFile", "scenes.ready.json")
tts_dir = REC / timeline.get("ttsDir", "tts")
scenes = {s["id"]: s for s in json.loads(scene_file.read_text(encoding="utf-8"))}

markers = timeline.get("markers", [])
last_scene = max(markers, key=lambda m: m["offsetSec"])
cap_sec = last_scene["offsetSec"] + last_scene["narrationSec"] + 1.6
total_sec = min(timeline["durationSec"], cap_sec) + 0.8
rate = 22050
channels = 1
sampwidth = 2
total_frames = int(total_sec * rate)
buf = bytearray(total_frames * channels * sampwidth)

cursor = 0.0
placed = []
for marker in sorted(timeline["markers"], key=lambda m: m["offsetSec"]):
    wav_path = tts_dir / f"{marker['id']}.wav"
    with wave.open(str(wav_path)) as w:
        assert w.getframerate() == rate and w.getnchannels() == channels and w.getsampwidth() == sampwidth
        frames = w.readframes(w.getnframes())
        n = w.getnframes()
    start = max(marker["offsetSec"], cursor + 0.25)
    if start - marker["offsetSec"] > 0.05:
        print(f"WARN {marker['id']} shifted {start - marker['offsetSec']:.2f}s to avoid overlap")
    byte_off = int(start * rate) * channels * sampwidth
    end = byte_off + len(frames)
    if end > len(buf):
        buf.extend(bytes(end - len(buf)))
    buf[byte_off:end] = frames
    cursor = start + n / rate
    placed.append((marker["id"], start, n / rate))

with wave.open(str(RUN / "narration.wav"), "wb") as out:
    out.setnchannels(channels)
    out.setsampwidth(sampwidth)
    out.setframerate(rate)
    out.writeframes(bytes(buf))

print(f"narration.wav {len(buf) / (rate * sampwidth):.1f}s, {len(placed)} scenes")
for sid, start, dur in placed:
    print(f"  {sid} @ {start:7.1f}s  {dur:5.1f}s")
