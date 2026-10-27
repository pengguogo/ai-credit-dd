import json, wave
from pathlib import Path
root = Path(r'release/_rec')
scenes = json.loads((root/'scenes.json').read_text(encoding='utf-8'))
ready = []
total = 0.0
for sc in scenes:
    w = wave.open(str(root/'tts'/f"{sc['id']}.wav"))
    dur = w.getnframes()/w.getframerate()
    total += dur
    ready.append({**sc, 'narrationSec': round(dur, 3)})
    print(sc['id'], round(dur,1), 's')
(root/'scenes.ready.json').write_text(json.dumps(ready, ensure_ascii=False, indent=2), encoding='utf-8')
print('total narration', round(total,1), 's =', round(total/60,2), 'min')
