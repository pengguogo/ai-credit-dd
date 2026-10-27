# 赛题04 自动化演示录屏（M6）

用无头 Chrome 在真实系统上按脚本走完整链路，边跑边用 CDP screencast 截帧，并叠加中文字幕、SAPI 中文旁白，最后用 ffmpeg 编码为 8~10 分钟的 MP4。**不预录、不拼接结果**：画面里的每次尽调、追问、合规拦截都是后端当场执行。

产物：`release/_rec/run/demo.mp4` → 复制到 `submission/dd04/artifacts/智算先锋队_赛题04_演示视频.mp4`，`submission/assemble_dd04_dir.py` 会把它收进提交目录。

## 前置

- Windows + 已安装 Chrome；后端 `http://127.0.0.1:8000` 已启动、可登录（演示账号 `admin / Admin@123`），样例数据已导入。
- Node.js 与 `playwright-core`（本机 DSH 环境自带，路径见下方 `NODE_PATH`）。
- ffmpeg：本目录脚本默认从 `release/_rec/pylibs/imageio_ffmpeg/binaries/` 取；没有时执行
  `ocft-backend\.venv\Scripts\python.exe -m pip install --target release\_rec\pylibs imageio-ffmpeg`。
- 中文 TTS：Windows SAPI `Microsoft Huihui Desktop`（系统自带）。

## 生成步骤（仓库根目录执行）

```bat
mkdir release\_rec
copy submission\record_dd04_demo\scenes.json release\_rec\scenes.json

powershell -ExecutionPolicy Bypass -File submission\record_dd04_demo\tts.ps1
ocft-backend\.venv\Scripts\python.exe submission\record_dd04_demo\measure.py

set NODE_PATH=C:\Users\Administrator\.dsh\profiles\desktop\node_modules
node submission\record_dd04_demo\record.js

ocft-backend\.venv\Scripts\python.exe submission\record_dd04_demo\build_audio.py
ocft-backend\.venv\Scripts\python.exe submission\record_dd04_demo\encode_video.py
copy /Y release\_rec\run\demo.mp4 submission\dd04\artifacts\智算先锋队_赛题04_演示视频.mp4
```

录制约 9 分钟（真实模型调用：LA001 完整尽调 + LA003 追问 + 一次合规拦截），编码约 5~8 分钟。

## 场景与文件

| 文件 | 作用 |
|------|------|
| `scenes.json` | 17 个场景的旁白与字幕；改文案改这里，再跑 tts/measure |
| `tts.ps1` | SAPI 逐场景生成 `release/_rec/tts/*.wav`（语速 `-Rate -2`） |
| `measure.py` | 量旁白时长，写 `release/_rec/scenes.ready.json` |
| `record.js` | 登录、完整尽调、报告预览滚动、六个单步页、任务与资产、LA003 追问、合规拦截、片尾；CDP 截帧到 `release/_rec/run/frames` |
| `build_audio.py` | 按录屏时间轴把旁白铺到静音轨，输出 `narration.wav` |
| `encode_video.py` | 帧序列 + 旁白 → `demo.mp4`（H.264 + AAC，25fps，1600×1000） |

## 注意

- 录制过程中**不要刷新页面**（执行过程面板会清空）；脚本已按页面实际耗时做等待。
- 画幅固定 1600×1000；字幕条含 `REC` 呼吸点，用于保证静态页面也有帧可截。
- 报告预览是新标签页，脚本用 `activeTag` 只采当前页，避免工作台与预览页交错闪帧。
- 旁白是 TTS 合成；如需人声，替换 `release/_rec/tts/*.wav` 后重跑 measure 之后的步骤（时长会变，需重录）。
- 片尾以最后一个场景旁白结束为准截断，防止机器休眠把片尾拉长。
- 自动化录屏不代替团队现场彩排；评委现场仍按《赛题04现场非公开集操作卡》实时重算。
