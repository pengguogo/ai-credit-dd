#!/usr/bin/env python3
"""测试报告 PDF 复现：submission/dd04/测试报告.md → HTML → Chrome headless A4 PDF。
排版口径（开发日志 2026-10-24「M7 测试报告定稿」）：正文 11pt、表格 10.5pt、无页眉页脚。
工具经 pip --target pytools 安装，不进入 requirements.txt。"""
import subprocess
import sys
from pathlib import Path

import markdown  # PYTHONPATH=pytools

ROOT = Path('/Users/dawn/ai马拉松')
MD = ROOT / 'submission/dd04/测试报告.md'
HTML_OUT = Path(__file__).resolve().parent / '测试报告.html'
PDF_OUT = ROOT / 'submission/dd04/artifacts/智算先锋队_赛题04_测试报告.pdf'
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

CSS = """
@page { size: A4; margin: 16mm 15mm; }
* { box-sizing: border-box; }
body {
  font-size: 11pt; line-height: 1.65; color: #1a2433; margin: 0;
  font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Source Han Sans SC", sans-serif;
}
h1 { font-size: 19pt; margin: 0 0 10pt; padding-bottom: 8pt; border-bottom: 2px solid #172b44; }
h2 { font-size: 14pt; margin: 18pt 0 8pt; padding-bottom: 4pt; border-bottom: 1px solid #c9d4e0; page-break-after: avoid; }
h3 { font-size: 12pt; margin: 12pt 0 6pt; page-break-after: avoid; }
p { margin: 6pt 0; }
strong { color: #172b44; }
code {
  font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 9.5pt;
  background: #f1f4f8; border: 1px solid #dde4ec; border-radius: 3px; padding: 0 3px;
}
blockquote {
  margin: 8pt 0; padding: 5pt 10pt; border-left: 3px solid #7b93b0;
  background: #f6f8fb; color: #37475e;
}
blockquote p { margin: 2pt 0; }
ul, ol { margin: 6pt 0; padding-left: 22pt; }
li { margin: 3pt 0; }
a { color: #2a5b8f; text-decoration: none; }
hr { border: none; border-top: 1px solid #c9d4e0; margin: 12pt 0; }
table {
  width: 100%; border-collapse: collapse; font-size: 10.5pt; margin: 8pt 0;
}
thead { display: table-header-group; }
th, td { border: 1px solid #c2cedd; padding: 4pt 7pt; vertical-align: top; text-align: left; }
th { background: #eef2f7; color: #172b44; font-weight: 600; }
tr { page-break-inside: avoid; }
tbody tr:nth-child(even) td { background: #fafbfd; }
"""


def main() -> int:
    text = MD.read_text(encoding='utf-8')
    body = markdown.markdown(text, extensions=['tables', 'fenced_code', 'sane_lists'])
    html = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        f'<title>{MD.stem}</title><style>{CSS}</style></head>'
        f'<body>{body}</body></html>'
    )
    HTML_OUT.write_text(html, encoding='utf-8')
    print(f'HTML 写出：{HTML_OUT}（{len(html)} 字符）')

    PDF_OUT.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        CHROME, '--headless', '--disable-gpu', '--no-pdf-header-footer',
        '--print-to-pdf-no-header', f'--print-to-pdf={PDF_OUT}',
        HTML_OUT.as_uri(),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    sys.stderr.write(result.stderr[-800:] if result.stderr else '')
    if result.returncode != 0 or not PDF_OUT.exists():
        print(f'Chrome 打印失败 rc={result.returncode}')
        return 1
    print(f'PDF 写出：{PDF_OUT}（{PDF_OUT.stat().st_size} bytes）')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
