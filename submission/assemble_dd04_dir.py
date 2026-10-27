#!/usr/bin/env python3
"""按《赛题04 提交材料说明》组装「一个目录」的提交材料包。

与 pack_dd04.py 的分工：pack_dd04.py 负责 manifest / 元信息表 / 系统包等底层产物，
本脚本负责把散落在仓库各处的材料按官方 3.1 目录结构归拢到一个目录，逐项核对，
并生成 00_资料清单与自检.md（缺失项如实标注，不伪造）。

默认输出 release/04_<队名>_Agent大赛提交/（release/ 不入库）。

用法（仓库根目录）：
  ocft-backend/.venv/Scripts/python.exe submission/assemble_dd04_dir.py --dry-run --no-zip
  ocft-backend/.venv/Scripts/python.exe submission/assemble_dd04_dir.py --date 2026-10-25

缺演示视频等材料时仍会组装，但退出码为 2 并在清单中标记 ⛔。
"""
from __future__ import annotations

import argparse
import csv
import io
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUB = ROOT / "submission"
DD04 = SUB / "dd04"
RELEASE = ROOT / "release"
DEFAULT_TEAM = "智算先锋队"

sys.path.insert(0, str(SUB))
import pack_dd04 as pk  # noqa: E402  (同目录工具，复用 manifest / xlsx 生成)

TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".txt"}


def _posix(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def copy_item(src: Path, dest: Path) -> bool:
    if not src.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return True


def png_info(path: Path) -> tuple[int, int]:
    """只读 PNG IHDR，避免引入 Pillow 依赖。"""
    with path.open("rb") as fh:
        head = fh.read(33)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return 0, 0
    width = int.from_bytes(head[16:20], "big")
    height = int.from_bytes(head[20:24], "big")
    return width, height


def csv_info(path: Path) -> dict:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0] if rows else []
    return {"bom": bom, "header": header, "data_rows": max(len(rows) - 1, 0), "rows": rows}


def build_system_zip(dest: Path, commit: str) -> tuple[bool, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    cmd = ["git", "archive", "--format=zip", f"--output={dest}", commit]
    try:
        subprocess.check_call(cmd, cwd=ROOT)
    except subprocess.CalledProcessError as exc:
        return False, f"git archive 失败：{exc}"
    size_mb = dest.stat().st_size / (1024 * 1024)
    return True, f"{size_mb:.1f} MB（git archive {commit[:10]}）"


def write_index(
    out: Path,
    *,
    team: str,
    prefix: str,
    commit: str,
    submit_date: str,
    png_rows: list[dict],
    csv_rows: list[dict],
    checks: list[tuple[str, str, str]],
    missing: list[str],
    deferred: list[str],
    zip_note: str,
    dry_run: bool,
) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_mb = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / (1024 * 1024)
    lines: list[str] = []
    lines += [
        f"# 提交材料清单与自检 · 赛题04 企业智能信贷尽调 · {team}",
        "",
        f"> 生成时间：{now} ｜ 版本：v1.0 ｜ 计划提交日：{submit_date} ｜ 代码 SHA：`{commit}`",
        f"> 本目录即提交包根目录（解压/打开后直接看到 `README.md`、`manifest.yaml`、`{prefix}_技术方案.pdf`）。",
        "> 依据：`docs/00-rules/通用提交材料说明.md`、`docs/00-rules/赛题/赛题04_企业智能信贷尽调/提交材料说明.md`。",
        "",
    ]
    if dry_run:
        lines.append("> ⚠️ 本次为 dry-run，系统包与最终目录未封版。")
        lines.append("")

    if missing:
        lines.append(f"> **当前缺口 {len(missing)} 项必需材料**：" + "、".join(missing) + "。其余材料已就位。")
    else:
        lines.append("> **十项材料均已就位。**" if not deferred else "> **十项材料均已就位，另有待现场/待确认项。**")
    lines.append("")

    lines += ["## 一、十项材料对照", "", "| # | 材料 | 官方要求 | 本目录文件 | 状态 |", "|---|---|---|---|---|"]
    items = [
        ("1", "可运行系统包", "目录/zip，含批量测评入口", f"`{prefix}_可运行系统包.zip`",
         "✅" if (out / f"{prefix}_可运行系统包.zip").exists() else "⛔ 缺失"),
        ("2", "源代码与部署说明", "README.md", "`README.md`",
         "✅" if (out / "README.md").exists() else "⛔ 缺失"),
        ("3", "技术方案说明", "PDF + 同名 MD", f"`{prefix}_技术方案.pdf` / `.md`",
         "✅" if (out / f"{prefix}_技术方案.pdf").exists() else "⛔ 缺失"),
        ("4", "系统答案截图", "≥3 张真实界面", "`截图01`~`截图04`",
         "✅" if len(png_rows) >= 3 else "⛔ 缺失"),
        ("5", "系统输出结果文件", "公开集 + 非公开集 CSV", "`系统输出/` 下 2 个 CSV",
         "⚠️ 非公开为演练样本" if (out / "系统输出").exists() else "⛔ 缺失"),
        ("6", "演示视频", "MP4，8~10 分钟完整链路", f"`{prefix}_演示视频.mp4`",
         "✅" if (out / f"{prefix}_演示视频.mp4").exists() else "⛔ 缺失"),
        ("7", "测试报告", "PDF + 同名 MD，量化一致率", f"`{prefix}_测试报告.pdf` / `.md`",
         "✅" if (out / f"{prefix}_测试报告.pdf").exists() else "⛔ 缺失"),
        ("8", "团队与元信息表", "manifest.yaml + xlsx", f"`manifest.yaml` / `{prefix}_团队与元信息表.xlsx`",
         "✅（联系人 TBD）" if (out / "manifest.yaml").exists() else "⛔ 缺失"),
        ("9", "尽调报告样例", "≥1 份完整结构化报告", f"`附录/{prefix}_尽调报告样例_E001.pdf` / `.md`",
         "✅" if (out / "附录" / f"{prefix}_尽调报告样例_E001.pdf").exists() else "⛔ 缺失"),
        ("10", "第三方组件与 License 声明", "可选（建议）", f"`第三方声明/{prefix}_第三方组件与License声明.md`",
         "✅" if (out / "第三方声明").exists() else "⛔ 缺失"),
    ]
    for row in items:
        lines.append("| " + " | ".join(row) + " |")
    lines += [
        "",
        "另附：`数据使用与脱敏说明.md`、`关键技术难点与权衡说明.md`（通用说明可选项 8、9）。",
        "",
    ]
    if (out / f"{prefix}_演示视频.mp4").exists():
        lines += [
            "演示视频：8:45、1600×1000、25fps、H.264 + AAC、约 23.6 MB；自动化录屏（真实系统实时运行 + 中文 TTS 旁白），"
            "内容覆盖登录 → LA001 完整尽调 → 六个单步页 → LA003 高风险追问 → 合规拦截；生成工具在 `submission/record_dd04_demo/`。",
            "",
        ]
    lines += [
        "",
        "## 二、系统答案截图（本赛题专属硬性项）",
        "",
        "| 文件 | 尺寸 | 大小 | 内容 | 来源（真实运行） |",
        "|---|---|---|---|---|",
    ]
    shot_desc = {
        "截图01": "尽调报告全文：企业概况 + 财务分析 + 风险提示 + 额度建议 + 风控条件",
        "截图02": "财务分析明细：近三年科目、趋势、回款与勾稽",
        "截图03": "风险提示与反欺诈：评级维度、额度建议、F01–F06 明细",
        "截图04": "自然语言问询：工作台追问 + 执行详情（角色步骤/证据/token）",
    }
    for row in png_rows:
        key = row["file"].split("_")[2] if "_" in row["file"] else ""
        lines.append(
            f"| `{row['file']}` | {row['width']}×{row['height']} | {row['mb']:.2f} MB | "
            f"{shot_desc.get(key, '')} | {'✅ 系统真实截图' if row['ok'] else '⚠️ 待核'} |"
        )
    lines += [
        "",
        "来源目录：`测试数据/评测/2026-10-25/a5-walkthrough/M4/`（run_bbc525c5982f 报告预览页、run_b082124f7c64 追问）。"
        "截图中实控人 / 股东已显示为 `****`。",
        "",
        "## 三、系统输出结果文件",
        "",
        "| 文件 | 数据行 | 列数 | utf-8-sig | 说明 |",
        "|---|---|---|---|---|",
    ]
    for row in csv_rows:
        lines.append(
            f"| `{row['file']}` | {row['data_rows']} | {len(row['header'])} | "
            f"{'是' if row['bom'] else '否'} | {row['note']} |"
        )
    lines += [
        "",
        "公开集以 `00e905f` 归档结果为准，非公开集当前是 **A4 团队衍生样本演练**（LA101–LA105）；"
        "周日现场拿到官方「仅输入」样本后按操作卡重跑并覆盖，不能把演练结果说成官方成绩。",
        "",
        "## 四、本次自动核对",
        "",
        "| 检查项 | 方法 | 结果 |",
        "|---|---|---|",
    ]
    for name, method, result in checks:
        lines.append(f"| {name} | {method} | {result} |")
    lines += [
        "",
        "## 五、必须人工实测（脚本不代替）",
        "",
        "| # | 项目 | 实测方法 | 状态 |",
        "|---|---|---|---|",
        "| 1 | 干净 Windows 机解压一键启动 | 空目录解压最终包，双击 `start.bat`，访问 `http://127.0.0.1:8000` | ☐ 待执行 |",
        "| 2 | 断网依赖安装 | 断网后启动，确认不触发 pip / npm 联网下载 | ☐ 待执行 |",
        "| 3 | 上传/截图/报表用 Excel 打开无乱码 | 双击 `系统输出/*.csv` 与元信息 xlsx | ☐ 待执行 |",
        "| 4 | 演示视频可播放、非加密、界面文字无水印 | 系统播放器打开 MP4 | ☐ 待执行 |",
        "| 5 | 同一输入跑两次结论一致 | 公开集抽 1 笔双跑 diff | ☐ 待执行 |",
        "| 6 | 现场非公开集实时重算并覆盖结果文件 | 按《赛题04现场非公开集操作卡》 | ☐ 待现场 |",
        "",
        "## 六、缺失与待办",
        "",
    ]
    if not missing and not deferred:
        lines.append("- 无。")
    for idx, item in enumerate(missing, 1):
        lines.append(f"{idx}. ⛔ **{item}**（必需）：补齐后重跑本脚本。")
    offset = len(missing)
    for idx, item in enumerate(deferred, offset + 1):
        lines.append(f"{idx}. ⚠️ {item}")
    lines += [
        "",
        "## 七、更新与复现",
        "",
        "```bat",
        "cd /d <仓库根目录>",
        "ocft-backend\\.venv\\Scripts\\python.exe submission\\assemble_dd04_dir.py --date 2026-10-25",
        "```",
        "",
        f"系统包：`{zip_note}`。改过依赖或前端后先跑 `pack-offline.ps1` 再重跑本脚本。",
        "",
        "## 八、投递",
        "",
        "- 外网 `2364245903@qq.com`；内网 `<内网提交邮箱>`",
        f"- 主题 / 压缩包名：`04_{team}_Agent大赛提交`",
        "- 正文模板：`submission/dd04/智算先锋队_赛题04_投递邮件正文.txt`",
        "- 包 ≥200MB 时周日 11:30 前 U 盘拷到评委电脑；收到组委会回复确认邮件才算提交成功。",
        "",
        f"本目录合计（含可运行系统包）：{total_mb:.1f} MB。",
        "",
    ]
    (out / "00_资料清单与自检.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:  # Windows 控制台默认 GBK，避免打印 ✅ / ⛔ 时崩溃
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="组装赛题04提交材料目录")
    parser.add_argument("--team", default=DEFAULT_TEAM)
    parser.add_argument("--commit", default=None, help="代码 SHA，默认 git HEAD")
    parser.add_argument("--date", default="2026-10-25", help="计划提交日 YYYY-MM-DD")
    parser.add_argument("--contact-name", default=None, help="第一联系人姓名（同步 manifest / 元信息表）")
    parser.add_argument("--contact-phone", default=None, help="第一联系人手机")
    parser.add_argument("--contact-email", default=None, help="第一联系人邮箱")
    parser.add_argument("--out", default=None, help="输出目录，默认 release/04_<队名>_Agent大赛提交")
    parser.add_argument("--no-zip", action="store_true", help="不生成可运行系统包（快速自检）")
    parser.add_argument("--dry-run", action="store_true", help="输出到 release/_dryrun 并标注未封版")
    args = parser.parse_args()

    team = pk._validate_team(args.team)
    assert team is not None
    prefix = f"{team}_赛题04"
    commit = args.commit or pk._git_sha()
    submit_date = args.date

    if args.dry_run:
        out = RELEASE / "_dryrun" / f"04_{team}_Agent大赛提交"
    else:
        out = Path(args.out) if args.out else RELEASE / f"04_{team}_Agent大赛提交"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    missing: list[str] = []
    deferred: list[str] = []

    # 1) 技术方案 / 测试报告 / 团队表 / 附录
    copy_map = {
        f"{prefix}_技术方案.md": DD04 / "技术方案.md",
        f"{prefix}_技术方案.pdf": DD04 / "artifacts" / f"{prefix}_技术方案.pdf",
        f"{prefix}_测试报告.md": DD04 / "测试报告.md",
        f"{prefix}_测试报告.pdf": DD04 / "artifacts" / f"{prefix}_测试报告.pdf",
        "附录/" + f"{prefix}_尽调报告样例_E001.pdf": DD04 / "artifacts" / "尽调报告样例_E001.pdf",
        "附录/" + f"{prefix}_尽调报告样例_E001.md": DD04 / "artifacts" / "尽调报告样例_E001.md",
        "附录/" + f"{prefix}_演示脚本.md": ROOT / "docs" / "60-pitch" / "赛题04演示脚本.md",
        "数据使用与脱敏说明.md": SUB / "数据使用与脱敏说明.md",
        "关键技术难点与权衡说明.md": SUB / "关键技术难点与权衡说明.md",
        "README.md": ROOT / "README.md",
    }
    for dest_name, src in copy_map.items():
        if not copy_item(src, out / dest_name):
            missing.append(dest_name)

    # 2) 系统答案截图（真实界面，命名按专属说明）
    shot_src = ROOT / "测试数据" / "评测" / "2026-10-25" / "a5-walkthrough" / "M4"
    shot_names = [
        ("截图01_尽调报告_完整.png", f"{prefix}_截图01_尽调报告_完整.png"),
        ("截图02_财务分析.png", f"{prefix}_截图02_财务分析.png"),
        ("截图03_风险提示与反欺诈.png", f"{prefix}_截图03_风险提示与反欺诈.png"),
        ("截图04_自然语言问询.png", f"{prefix}_截图04_自然语言问询.png"),
    ]
    png_rows: list[dict] = []
    for src_name, dest_name in shot_names:
        if copy_item(shot_src / src_name, out / dest_name):
            width, height = png_info(out / dest_name)
            size = (out / dest_name).stat().st_size
            png_rows.append({
                "file": dest_name, "width": width, "height": height,
                "mb": size / (1024 * 1024), "bytes": size,
                "ok": width >= 1280 and height >= 720 and size <= 5 * 1024 * 1024,
            })
        else:
            missing.append(dest_name)
    if len(png_rows) < 3:
        missing.append("系统答案截图（至少 3 张）")

    # 3) 系统输出（公开集 / 非公开集）
    out_dir = out / "系统输出"
    out_dir.mkdir(exist_ok=True)
    csv_sources = [
        (f"{prefix}_公开测评集结果.csv", ROOT / "系统输出" / f"{prefix}_公开测评集结果.csv",
         "官方公开 10 笔（基线 00e905f）"),
        (f"{prefix}_非公开测评集结果.csv", ROOT / "系统输出" / f"{prefix}_非公开测评集结果.csv",
         "⚠️ 当前为 A4 演练衍生 5 笔，现场覆盖"),
    ]
    csv_rows: list[dict] = []
    for dest_name, src, note in csv_sources:
        if copy_item(src, out_dir / dest_name):
            info = csv_info(out_dir / dest_name)
            csv_rows.append({
                "file": dest_name, "header": info["header"],
                "data_rows": info["data_rows"], "bom": info["bom"], "note": note,
            })
        else:
            missing.append(f"系统输出/{dest_name}")

    # 4) 演示视频
    video_src = DD04 / "artifacts" / f"{prefix}_演示视频.mp4"
    if not copy_item(video_src, out / f"{prefix}_演示视频.mp4"):
        missing.append("演示视频 MP4（放在 submission/dd04/artifacts/ 后重跑）")
    subtitle_src = DD04 / "artifacts" / f"{prefix}_演示视频.srt"
    if subtitle_src.exists():
        copy_item(subtitle_src, out / f"{prefix}_演示视频.srt")

    # 5) 第三方声明
    pk.write_third_party_named(team, out / "第三方声明")

    # 6) 可运行系统包
    zip_path = out / f"{prefix}_可运行系统包.zip"
    if args.no_zip:
        zip_note = "本次 --no-zip 未生成"
        missing.append("可运行系统包（去掉 --no-zip 生成）")
    else:
        ok, zip_note = build_system_zip(zip_path, commit)
        if not ok:
            missing.append("可运行系统包（git archive 失败）")

    # 7) manifest + 元信息表（attachments 与实际文件逐一对齐）
    index_name = "00_资料清单与自检.md"
    xlsx_name = f"{prefix}_团队与元信息表.xlsx"
    manifest = pk.build_manifest(
        team, commit, submit_date,
        contact_name=args.contact_name,
        contact_phone=args.contact_phone,
        contact_email=args.contact_email,
    )
    planned = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
    planned |= {"manifest.yaml", xlsx_name, index_name}
    manifest["attachments"] = sorted(planned)
    pk.write_manifest(manifest, out / "manifest.yaml")
    pk.write_meta_xlsx(manifest, out / xlsx_name)
    (out / index_name).write_text("", encoding="utf-8")  # 占位，供实物比对；随后重写正文

    # 8) 核对
    checks: list[tuple[str, str, str]] = []
    root_ok = all((out / n).exists() for n in ("README.md", "manifest.yaml", f"{prefix}_技术方案.pdf"))
    checks.append(("根目录直见 README/manifest/技术方案", "os.path.exists", "✅ 通过" if root_ok else "⛔ 失败"))

    if png_rows:
        bad = [r["file"] for r in png_rows if not r["ok"]]
        checks.append((
            f"截图 {len(png_rows)} 张 ≥1280×720、单张 ≤5MB",
            "PNG IHDR + 文件大小",
            "✅ 通过" if not bad else "⛔ " + "、".join(bad),
        ))
    else:
        checks.append(("截图 ≥3 张", "文件存在性", "⛔ 无截图"))

    for row in csv_rows:
        ok = row["data_rows"] > 0 and len(row["header"]) == 6 and row["bom"]
        checks.append((
            f"{row['file']} 六列 + utf-8-sig",
            "csv 读取并数行",
            ("✅ 通过，" + str(row["data_rows"]) + " 行") if ok else "⛔ 列/编码/行数异常",
        ))

    paired = [
        f"{prefix}_技术方案", f"{prefix}_测试报告",
    ]
    pair_ok = all((out / f"{n}.pdf").exists() and (out / f"{n}.md").exists() for n in paired)
    checks.append(("PDF 与同名 MD 成对", "文件存在性", "✅ 通过" if pair_ok else "⛔ 缺同名 MD"))

    big_pdf = [p.name for p in out.glob("*.pdf") if p.stat().st_size > 30 * 1024 * 1024]
    checks.append(("单份 PDF ≤30MB", "文件大小", "✅ 通过" if not big_pdf else "⛔ " + "、".join(big_pdf)))

    bom_bad: list[str] = []
    for p in out.rglob("*"):
        if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES:
            if p.read_bytes().startswith(b"\xef\xbb\xbf"):
                bom_bad.append(p.name)
    checks.append(("Markdown/YAML 无 BOM", "读取前 3 字节", "✅ 通过" if not bom_bad else "⛔ " + "、".join(bom_bad)))

    manifest_now = pk._load_yaml(out / "manifest.yaml")
    attached = set(manifest_now.get("attachments") or [])
    actual = set(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    diff = attached ^ actual
    checks.append((
        "manifest.attachments 与实物一致",
        "集合比对",
        "✅ 通过" if not diff else "⛔ 差异：" + "、".join(sorted(diff)),
    ))
    total_mb = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / (1024 * 1024)
    checks.append(("本目录体积 ≤500MB", "累加文件大小", f"✅ {total_mb:.1f} MB" if total_mb <= 500 else "⛔ 超限"))

    # 待现场 / 待确认
    deferred += [
        "非公开测评集结果：当前为团队衍生样本演练，周日现场拿到官方输入后重跑覆盖（`系统输出/` 与测试报告 §5 同步更新）。",
        "第一联系人手机 / 邮箱仍为 `TBD`：补齐后用 `--contact-phone`、`--contact-email` 重跑（manifest 与元信息表同步）。",
        "最终提交 SHA / 提交日：投递前用当日 HEAD 重跑，manifest `code.commit_sha` 自动对齐。",
    ]

    write_index(
        out,
        team=team, prefix=prefix, commit=commit, submit_date=submit_date,
        png_rows=png_rows, csv_rows=csv_rows, checks=checks,
        missing=missing, deferred=deferred, zip_note=zip_note, dry_run=args.dry_run,
    )

    print()
    print(f"输出目录：{_posix(out) if out.is_relative_to(ROOT) else out}")
    final_files = [p for p in out.rglob("*") if p.is_file()]
    final_mb = sum(p.stat().st_size for p in final_files) / (1024 * 1024)
    print(f"篇幅：{final_mb:.1f} MB，文件 {len(final_files)} 个")
    for name, method, result in checks:
        print(f"  [{ 'OK ' if result.startswith('✅') else '!! ' }] {name} -> {result}")
    if missing:
        print()
        print("缺失（必需）：")
        for m in missing:
            print("  -", m)
        return 2
    print()
    print("十项材料就位；待现场/待确认项见 00_资料清单与自检.md §六。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
