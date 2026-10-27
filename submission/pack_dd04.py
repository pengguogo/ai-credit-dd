#!/usr/bin/env python3
"""赛题 04 提交材料组装（陈修活：M1 / M8 / M10 / M12）。

在仓库根目录执行。队名未定时也可生成 draft 产物；正式封包必须提供 --team。

用法示例：
  # 重生第三方 + 写出草稿 manifest / 元信息表 / 系统包（队名占位）
  ocft-backend/.venv/bin/python submission/pack_dd04.py --prep

  # 队名确定后：写出正式命名材料 + 系统包 zip（仍不组最终邮件包）
  ocft-backend/.venv/bin/python submission/pack_dd04.py --prep --team 某某队

  # 最终封包（要求截图/视频/PDF 等已就位，或用 --allow-missing 只组现有文件）
  ocft-backend/.venv/bin/python submission/pack_dd04.py --pack --team 某某队 \\
      --commit "$(git rev-parse HEAD)" --date 2026-10-25
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUB = ROOT / "submission"
DD04 = SUB / "dd04"
RELEASE = ROOT / "release"
OUT_STAGING = RELEASE / "dd04-staging"

FORBIDDEN_NAME_CHARS = re.compile(r'[<>:"|?*\\/]')


def _run(cmd: list[str], **kw) -> None:
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT, **kw)


def _load_yaml(path: Path) -> dict:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _dump_yaml(data: dict, path: Path) -> None:
    import yaml
    # 保持可读：unicode、不排序、块样式
    text = yaml.safe_dump(
        data, allow_unicode=True, sort_keys=False, default_flow_style=False, width=100
    )
    path.write_text(text, encoding="utf-8")


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _validate_team(team: str | None) -> str | None:
    if team is None:
        return None
    team = team.strip()
    if not team or team in ("TBD", "星火队"):
        raise SystemExit("队名不能为空、TBD 或官方示例「星火队」")
    if FORBIDDEN_NAME_CHARS.search(team):
        raise SystemExit(f"队名含非法文件名字符：{team}")
    return team


def regen_third_party() -> None:
    py = ROOT / "ocft-backend" / ".venv" / "bin" / "python"
    if not py.exists():
        py = Path(sys.executable)
    _run([str(py), str(SUB / "gen_third_party.py")])


def build_manifest(
    team: str | None,
    commit: str,
    submit_date: str,
    *,
    contact_name: str | None = None,
    contact_phone: str | None = None,
    contact_email: str | None = None,
) -> dict:
    draft = _load_yaml(DD04 / "manifest.draft.yaml")
    tp = _load_yaml(SUB / "third_party_components.yaml")
    draft["third_party_components"] = tp["third_party_components"]
    draft["code"]["commit_sha"] = commit
    draft["code"]["is_private"] = True
    draft["submission"]["submit_date"] = submit_date

    if team:
        draft["submission"]["team_name"] = team
        draft["submission"]["submission_name"] = f"04_{team}_Agent大赛提交"
        prefix = f"{team}_赛题04"
        draft["attachments"] = [
            "manifest.yaml",
            "README.md",
            f"{prefix}_技术方案.pdf",
            f"{prefix}_技术方案.md",
            f"{prefix}_测试报告.pdf",
            f"{prefix}_测试报告.md",
            f"{prefix}_演示视频.mp4",
            f"{prefix}_团队与元信息表.xlsx",
            f"{prefix}_可运行系统包.zip",
            f"{prefix}_截图01_尽调报告_完整.png",
            f"{prefix}_截图02_财务分析.png",
            f"{prefix}_截图03_风险提示与反欺诈.png",
            f"{prefix}_截图04_自然语言问询.png",
            f"系统输出/{prefix}_公开测评集结果.csv",
            f"系统输出/{prefix}_非公开测评集结果.csv",
            f"附录/{prefix}_尽调报告样例_E001.pdf",
            f"附录/{prefix}_尽调报告样例_E001.md",
            f"附录/{prefix}_演示脚本.md",
            f"第三方声明/{prefix}_第三方组件与License声明.md",
            "数据使用与脱敏说明.md",
            "关键技术难点与权衡说明.md",
        ]
    else:
        draft["attachments"] = ["manifest.yaml", "README.md", "（队名确定后由 pack_dd04.py 按实物填充）"]

    if contact_name:
        draft["contact"]["primary_name"] = contact_name
    if contact_phone:
        draft["contact"]["primary_phone"] = contact_phone
    if contact_email:
        draft["contact"]["primary_email"] = contact_email
        # 同步第一联系人到 members 同名行（若能匹配）
        for m in draft.get("members") or []:
            if m.get("name") == contact_name:
                m["phone"] = contact_phone or m.get("phone")
                m["email"] = contact_email or m.get("email")

    return draft


def write_manifest(data: dict, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _dump_yaml(data, dest)
    print(f"wrote {dest.relative_to(ROOT)}")


def write_meta_xlsx(manifest: dict, dest: Path) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    # 01_团队成员
    ws1 = wb.active
    ws1.title = "01_团队成员"
    ws1.append(["姓名", "角色", "手机", "邮箱", "是否第一联系人"])
    primary = (manifest.get("contact") or {}).get("primary_name")
    for m in manifest.get("members") or []:
        ws1.append([
            m.get("name"), m.get("role"), m.get("phone"), m.get("email"),
            "是" if m.get("name") == primary else "",
        ])
    contact = manifest.get("contact") or {}
    ws1.append([])
    ws1.append(["第一联系人", contact.get("primary_name"), contact.get("primary_phone"), contact.get("primary_email")])

    # 02_环境与依赖
    ws2 = wb.create_sheet("02_环境与依赖")
    env = manifest.get("demo_env") or {}
    ws2.append(["字段", "值"])
    for k in ("type", "os", "runtime", "startup_command", "access_url", "gpu_required", "network_required", "notes"):
        ws2.append([k, env.get(k)])
    ws2.append([])
    ws2.append(["依赖名", "版本"])
    for d in manifest.get("dependencies") or []:
        ws2.append([d.get("name"), d.get("version")])
    code = manifest.get("code") or {}
    ws2.append([])
    ws2.append(["repo_url", code.get("repo_url")])
    ws2.append(["commit_sha", code.get("commit_sha")])
    ws2.append(["branch", code.get("branch")])
    ws2.append(["is_private", code.get("is_private")])

    # 03_外部服务与组件声明
    ws3 = wb.create_sheet("03_外部服务与组件声明")
    ws3.append(["类型", "名称", "版本/模型", "License/用途", "凭据来源", "离线降级", "脱敏说明"])
    for s in manifest.get("external_services") or []:
        ws3.append([
            "外部服务", s.get("name"), "", s.get("purpose"),
            s.get("credential_source"), s.get("offline_fallback"), s.get("desensitization"),
        ])
    for llm in manifest.get("llm_declaration") or []:
        ws3.append([
            "大模型声明", llm.get("provider"), llm.get("model"), llm.get("usage"),
            "", "", llm.get("data_sent"),
        ])
    for c in manifest.get("third_party_components") or []:
        ws3.append([
            "第三方组件", c.get("name"), c.get("version"), f"{c.get('license')} / {c.get('usage')}",
            "", "", "",
        ])

    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(dest)
    print(f"wrote {dest.relative_to(ROOT)}")


def write_third_party_named(team: str | None, dest_dir: Path) -> Path:
    src = SUB / "第三方组件.md"
    dest_dir.mkdir(parents=True, exist_ok=True)
    if team:
        dest = dest_dir / f"{team}_赛题04_第三方组件与License声明.md"
    else:
        dest = dest_dir / "第三方组件与License声明.md"
    shutil.copy2(src, dest)
    # 顶部加一行命名说明
    body = dest.read_text(encoding="utf-8")
    if not body.startswith("# 第三方组件与 License 声明"):
        header = (
            "# 第三方组件与 License 声明\n\n"
            f"> 赛题 04 · 团队：{team or 'TBD'} · 由 `submission/gen_third_party.py` 生成后复制。\n\n"
        )
        dest.write_text(header + body, encoding="utf-8")
    print(f"wrote {dest.relative_to(ROOT)}")
    return dest


def build_system_zip(commit: str, team: str | None) -> Path:
    RELEASE.mkdir(parents=True, exist_ok=True)
    short = commit[:7]
    if team:
        name = f"{team}_赛题04_可运行系统包.zip"
    else:
        name = f"OCFT-DD04-{short}.zip"
    dest = RELEASE / name
    if dest.exists():
        dest.unlink()
    # 根目录不套层：git archive 直接出仓库内容
    _run(["git", "archive", "--format=zip", f"--output={dest}", commit])
    size_mb = dest.stat().st_size / (1024 * 1024)
    print(f"system zip {dest.relative_to(ROOT)} = {size_mb:.1f} MB (commit {commit})")
    if size_mb >= 200:
        print("WARNING: 系统包 ≥200MB，周日 11:30 前需 U 盘拷到评委电脑")
    return dest


def _copy_if_exists(src: Path, dest: Path) -> bool:
    if not src.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
    else:
        shutil.copy2(src, dest)
    return True


def assemble_submission(
    team: str,
    commit: str,
    submit_date: str,
    *,
    allow_missing: bool,
    contact_name: str | None,
    contact_phone: str | None,
    contact_email: str | None,
) -> Path:
    """按专属说明 3.1 组装 04_<队名>_Agent大赛提交.zip（根目录直接可见 README/manifest/技术方案）。"""
    prefix = f"{team}_赛题04"
    staging = OUT_STAGING / f"04_{team}_Agent大赛提交"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    manifest = build_manifest(
        team, commit, submit_date,
        contact_name=contact_name, contact_phone=contact_phone, contact_email=contact_email,
    )
    write_manifest(manifest, staging / "manifest.yaml")
    write_meta_xlsx(manifest, staging / f"{prefix}_团队与元信息表.xlsx")
    write_third_party_named(team, staging / "第三方声明")

    # README：优先仓库根 README
    shutil.copy2(ROOT / "README.md", staging / "README.md")
    for name in ("数据使用与脱敏说明.md", "关键技术难点与权衡说明.md"):
        shutil.copy2(SUB / name, staging / name)

    system_zip = build_system_zip(commit, team)
    shutil.copy2(system_zip, staging / f"{prefix}_可运行系统包.zip")

    # 系统输出（队名确定后复制；无前缀演练文件作回退）
    out_dir = staging / "系统输出"
    out_dir.mkdir()
    public_src = ROOT / "系统输出" / f"{prefix}_公开测评集结果.csv"
    if not public_src.exists():
        public_src = ROOT / "系统输出" / "公开测评集结果.csv"
    private_src = ROOT / "系统输出" / f"{prefix}_非公开测评集结果.csv"
    if not private_src.exists():
        private_src = ROOT / "系统输出" / "非公开测评集结果-演练衍生.csv"
    _copy_if_exists(public_src, out_dir / f"{prefix}_公开测评集结果.csv")
    _copy_if_exists(private_src, out_dir / f"{prefix}_非公开测评集结果.csv")

    # 可选/待他方交付的材料：从 submission/dd04/artifacts/ 或约定路径取
    optional_map = {
        f"{prefix}_技术方案.md": DD04 / "技术方案.md",
        f"{prefix}_技术方案.pdf": DD04 / "artifacts" / f"{prefix}_技术方案.pdf",
        f"{prefix}_测试报告.md": DD04 / "测试报告.md",
        f"{prefix}_测试报告.pdf": DD04 / "artifacts" / f"{prefix}_测试报告.pdf",
        f"{prefix}_演示视频.mp4": DD04 / "artifacts" / f"{prefix}_演示视频.mp4",
        f"{prefix}_截图01_尽调报告_完整.png": DD04 / "artifacts" / "截图01_尽调报告_完整.png",
        f"{prefix}_截图02_财务分析.png": DD04 / "artifacts" / "截图02_财务分析.png",
        f"{prefix}_截图03_风险提示与反欺诈.png": DD04 / "artifacts" / "截图03_风险提示与反欺诈.png",
        f"{prefix}_截图04_自然语言问询.png": DD04 / "artifacts" / "截图04_自然语言问询.png",
    }
    missing: list[str] = []
    for dest_name, src in optional_map.items():
        if not _copy_if_exists(src, staging / dest_name):
            missing.append(dest_name)

    appendix = staging / "附录"
    appendix.mkdir(exist_ok=True)
    appendix_map = {
        f"{prefix}_尽调报告样例_E001.pdf": DD04 / "artifacts" / "尽调报告样例_E001.pdf",
        f"{prefix}_尽调报告样例_E001.md": DD04 / "artifacts" / "尽调报告样例_E001.md",
        f"{prefix}_演示脚本.md": ROOT / "docs" / "60-pitch" / "演示脚本.md",
    }
    for dest_name, src in appendix_map.items():
        if not _copy_if_exists(src, appendix / dest_name):
            missing.append(f"附录/{dest_name}")

    required_always = [
        "README.md", "manifest.yaml",
        f"{prefix}_可运行系统包.zip",
        f"{prefix}_团队与元信息表.xlsx",
        f"第三方声明/{prefix}_第三方组件与License声明.md",
        f"系统输出/{prefix}_公开测评集结果.csv",
    ]
    for rel in required_always:
        if not (staging / rel).exists():
            missing.append(rel)

    if missing and not allow_missing:
        raise SystemExit(
            "以下材料缺失，无法封包（可用 --allow-missing 先打草稿包）：\n  - "
            + "\n  - ".join(missing)
        )
    if missing:
        print("WARNING missing (allow-missing):")
        for m in missing:
            print("  -", m)

    # 根目录必须直接看到 README / manifest；打 zip 时用 staging 的父目录内容
    final_zip = RELEASE / f"04_{team}_Agent大赛提交.zip"
    if final_zip.exists():
        final_zip.unlink()
    # zip 内顶层为「04_<队名>_Agent大赛提交/」还是直接文件？
    # 专属说明：压缩包解压后根目录必须直接看到 README.md、manifest.yaml —— 所以 zip 内不要再套一层。
    _run(["bash", "-lc", f"cd {staging} && zip -qr {final_zip} ."])
    size_mb = final_zip.stat().st_size / (1024 * 1024)
    print(f"submission zip {final_zip.relative_to(ROOT)} = {size_mb:.1f} MB")
    if size_mb > 500:
        raise SystemExit("提交包超过 500MB")
    return final_zip


def write_email_template(
    team: str,
    submit_date: str,
    dest: Path,
    *,
    contact_name: str | None = None,
    contact_phone: str | None = None,
    contact_email: str | None = None,
) -> None:
    contact_line = contact_name or "TBD"
    if contact_phone or contact_email:
        contact_line += f"，{contact_phone or '手机TBD'}，{contact_email or '邮箱TBD'}"
    else:
        contact_line += "（手机与邮箱封包前补齐）"
    body = f"""评审组老师：

您好！

我们提交 Agent 大赛「赛题04 企业智能信贷尽调」参赛材料，信息如下。

一、基本信息
- 赛题编号：04
- 赛题名称：企业智能信贷尽调
- 团队名称：{team}
- 提交版本：v1.0
- 提交日期：{submit_date}

二、团队成员
- 王小文（Agent 开发）
- 胡乾豪（数据开发与导入）
- 程柳（前端交互与报告展示）
- 彭国（评测与批量答题）
- 陈修活（合规与提交包）
- 黎锦涛（文档与路演）
- 第一联系人：{contact_line}

三、系统概述（200 字以内）
本系统以官方 10 张 CSV + 关系表构建企业信贷尽调数据层，输入贷款申请后由主控与六个角色 Agent
分工完成财报解析、工商核验、舆情扫描、反欺诈检测、评级与额度测算，并生成结构化尽调报告，
支持自然语言追问。反欺诈规则、财务指标口径、评分卡与额度模型均为 YAML 可配置，业务数字由工具计算。

四、演示环境
- 部署方式：本地一键启动（start.bat / start.ps1 -Offline）
- 运行环境：Windows 11，内置 Python 3.14.9
- 启动命令：双击 start.bat
- 访问地址：http://127.0.0.1:8000
- 依赖外网：是（DeepSeek API + 云端 MySQL / Redis；依赖本身离线安装，network_required: true）
- 需要 GPU：否

五、附件清单
1. 04_{team}_Agent大赛提交.zip（≤500MB，解压后根目录见 README.md / manifest.yaml）

六、自测结论摘要
- 公开测评集归档见测试报告（引用冻结版本）；失败与待确认如实披露
- 同一输入双跑一致性、非公开演练流水线已跑通（详见测试报告）

请查收。收到组委会确认回复前，我们保持联系人可达。

{team}
"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body, encoding="utf-8")
    print(f"wrote {dest.relative_to(ROOT)}")


def cmd_prep(args: argparse.Namespace) -> None:
    team = _validate_team(args.team)
    commit = args.commit or _git_sha()
    submit_date = args.date or date.today().isoformat()
    regen_third_party()
    manifest = build_manifest(
        team, commit, submit_date,
        contact_name=args.contact_name,
        contact_phone=args.contact_phone,
        contact_email=args.contact_email,
    )
    # 草稿始终写到 dd04；队名确定后再写根目录正式文件（封包时写入 staging）
    write_manifest(manifest, DD04 / "manifest.generated.yaml")
    xlsx_name = f"{team}_赛题04_团队与元信息表.xlsx" if team else "团队与元信息表.xlsx"
    write_meta_xlsx(manifest, DD04 / xlsx_name)
    write_third_party_named(team, DD04 / "第三方声明")
    build_system_zip(commit, team)
    email_kwargs = dict(
        contact_name=args.contact_name,
        contact_phone=args.contact_phone,
        contact_email=args.contact_email,
    )
    if team:
        write_email_template(
            team, submit_date, DD04 / f"{team}_赛题04_投递邮件正文.txt", **email_kwargs
        )
        print(f"prep done · 队名={team} · commit={commit[:12]} · 系统包在 release/")
        if not args.contact_phone or not args.contact_email:
            print("提醒：第一联系人手机/邮箱仍缺，正式投递前补齐后重跑 --prep。")
    else:
        write_email_template("<队名>", submit_date, DD04 / "投递邮件正文.template.txt")
        print("prep done. 队名仍为 TBD 时，勿把 generated 文件当正式提交物。")


def cmd_pack(args: argparse.Namespace) -> None:
    team = _validate_team(args.team)
    if not team:
        raise SystemExit("--pack 必须提供 --team")
    commit = args.commit or _git_sha()
    submit_date = args.date or date.today().isoformat()
    regen_third_party()
    final = assemble_submission(
        team, commit, submit_date,
        allow_missing=args.allow_missing,
        contact_name=args.contact_name,
        contact_phone=args.contact_phone,
        contact_email=args.contact_email,
    )
    write_email_template(
        team, submit_date, DD04 / f"{team}_赛题04_投递邮件正文.txt",
        contact_name=args.contact_name,
        contact_phone=args.contact_phone,
        contact_email=args.contact_email,
    )
    print()
    print("投递：")
    print(f"  外网邮箱：2364245903@qq.com")
    print(f"  内网邮箱：<内网提交邮箱>")
    print(f"  主题：04_{team}_Agent大赛提交")
    print(f"  附件：{final}")
    print(f"  正文：submission/dd04/{team}_赛题04_投递邮件正文.txt")
    print("  收到组委会回复才算提交成功。")


def main() -> None:
    p = argparse.ArgumentParser(description="赛题 04 提交材料组装")
    p.add_argument("--prep", action="store_true", help="重生第三方、manifest、xlsx、系统包")
    p.add_argument("--pack", action="store_true", help="组装最终提交 zip")
    p.add_argument("--team", default=None, help="队名（不能是星火队）")
    p.add_argument("--commit", default=None, help="40 位 commit SHA，默认 HEAD")
    p.add_argument("--date", default=None, help="提交日期 YYYY-MM-DD")
    p.add_argument("--contact-name", default=None)
    p.add_argument("--contact-phone", default=None)
    p.add_argument("--contact-email", default=None)
    p.add_argument("--allow-missing", action="store_true", help="封包时允许缺截图/视频/PDF")
    args = p.parse_args()
    if not args.prep and not args.pack:
        p.error("请指定 --prep 和/或 --pack")
    if args.prep:
        cmd_prep(args)
    if args.pack:
        cmd_pack(args)


if __name__ == "__main__":
    main()
