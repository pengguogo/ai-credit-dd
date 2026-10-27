"""把 CDP screencast 帧 + 旁白 WAV 编码为 MP4（H.264 + AAC，25fps）。

输入：release/_rec/run/frames.json、frames/*.jpg、narration.wav
输出：release/_rec/run/demo.mp4
用法：python release/_rec/encode_video.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REC = Path(os.environ.get("REC_DIR", "release/_rec")).resolve()
RUN = REC / (os.environ.get("OUT_NAME") or "run")
FFMPEG = REC / "pylibs" / "imageio_ffmpeg" / "binaries" / "ffmpeg-win-x86_64-v7.1.exe"

frames = json.loads((RUN / "frames.json").read_text(encoding="utf-8"))
frames.sort(key=lambda f: f["ts"])
if not frames:
    sys.exit("no frames")
timeline = json.loads((RUN / "timeline.json").read_text(encoding="utf-8"))

# 录制结束时间以最后一个场景的旁白结束为准，防止机器休眠/挂起把片尾拉长
markers = timeline.get("markers", [])
last_scene = max(markers, key=lambda m: m["offsetSec"])
cap_ms = timeline["recStartMs"] + (last_scene["offsetSec"] + last_scene["narrationSec"] + 1.6) * 1000
end_ms = min(timeline.get("endMs") or cap_ms, cap_ms)
frames = [f for f in frames if f["ts"] <= end_ms] or frames[-1:]

# 帧时长 = 下一帧时间差，限制在 0.02–0.8s；末帧一直保持到录制结束（静态片尾不丢）
lines = []
for i, frame in enumerate(frames):
    if i + 1 < len(frames):
        dur = (frames[i + 1]["ts"] - frame["ts"]) / 1000.0
    else:
        dur = (end_ms - frame["ts"]) / 1000.0
    dur = min(max(dur, 0.02), 120)
    lines.append(f"file 'frames/{frame['file']}'")
    lines.append(f"duration {dur:.4f}")
lines.append(f"file 'frames/{frames[-1]['file']}'")
(RUN / "frames.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

cmd = [
    str(FFMPEG), "-y", "-hide_banner", "-loglevel", "warning",
    "-f", "concat", "-safe", "0", "-i", str(RUN / "frames.txt"),
    "-i", str(RUN / "narration.wav"),
    "-r", "25", "-c:v", "libx264", "-preset", "medium", "-crf", "21",
    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
    "-shortest", "-movflags", "+faststart",
    str(RUN / "demo.mp4"),
]
print("+", " ".join(cmd))
subprocess.check_call(cmd)
size = (RUN / "demo.mp4").stat().st_size / 1024 / 1024
print(f"demo.mp4 = {size:.1f} MB")
