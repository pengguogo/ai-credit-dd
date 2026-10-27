# submission · 提交包材料

按《[通用提交材料说明](../docs/00-rules/通用提交材料说明.md)》与《[赛题04 提交材料说明](../docs/00-rules/赛题/赛题04_企业智能信贷尽调/提交材料说明.md)》准备。本目录保存赛题 04 提交材料与组装脚本；封包产物默认写到 `release/`。正式流程以 `pack_dd04.py --prep` / `--pack` 为准，手工生成步骤只用于排查。

## 当前实物与状态

| 文件 / 目录 | 对应材料 | 当前状态 |
|-------------|----------|----------|
| `dd04/manifest.draft.yaml`、`dd04/manifest.generated.yaml` | manifest 底稿 / 生成稿 | 赛题 04 字段已填；六位成员联系方式已补齐；最终 40 位 SHA、日期仍需更新后重生 |
| `dd04/智算先锋队_赛题04_团队与元信息表.xlsx` | M10 团队与元信息表 | 已生成；六位成员联系方式已补齐；最终 SHA / 日期待更新 |
| `dd04/第三方声明/智算先锋队_赛题04_第三方组件与License声明.md` | M12 第三方声明 | 已生成；依赖冻结后由 `--prep` / `--pack` 重生并人工核对 |
| `dd04/技术方案.md`、`dd04/artifacts/智算先锋队_赛题04_技术方案.pdf` | M3 技术方案 MD / PDF | 正式候选已存在，对应 `00e905f`；最终 SHA 复核后必要时重出 PDF |
| `dd04/测试报告.md`、`dd04/artifacts/智算先锋队_赛题04_测试报告.pdf` | M7 测试报告 MD / PDF | MD §5 已含官方非公开集实测；PDF 已于 2026-10-25 按当日最新 MD 重出（4 页，A4、正文 11pt、表格 10.5pt）；最终 SHA 复核后必要时再重出 |
| `../测试数据/评测/2026-10-25/m4-refresh-54e490e/m4-screenshots/截图01_尽调报告_完整.png` | M4 截图 01 | 2026-10-25 已在 `54e490e` 用真实模型重拍（1280×12456）并复制入 `dd04/artifacts/` |
| `../测试数据/评测/2026-10-25/m4-refresh-54e490e/m4-screenshots/截图02_财务分析.png` | M4 截图 02 | 同上（1280×3420） |
| `../测试数据/评测/2026-10-25/m4-refresh-54e490e/m4-screenshots/截图03_风险提示与反欺诈.png` | M4 截图 03 | 同上（1280×6125） |
| `../测试数据/评测/2026-10-25/m4-refresh-54e490e/m4-screenshots/截图04_自然语言问询.png` | M4 截图 04 | 同上（1600×1000，LA003 追问 + 执行过程）；旧版见 `a5-walkthrough/M4/` |
| `dd04/artifacts/尽调报告样例_E001.md/.pdf` | M9 脱敏尽调报告样例 | 已有真实 run 候选材料，对应 `00e905f` |
| `../系统输出/智算先锋队_赛题04_公开测评集结果.csv` | 正式命名公开集 CSV | 已有候选；最终 SHA 必须实时重跑、校验并替换 |
| `../系统输出/智算先锋队_赛题04_非公开测评集结果.csv` | 正式命名非公开集 CSV | 当前仅为团队衍生演练占位，不是官方现场非公开结果；现场取得输入后必须替换 |
| `pack_dd04.py` | M1 / M8 / M10 / M12 组装入口 | 支持 `--prep` 与 `--pack`；`--allow-missing` 仅可生成草稿包 |

当前 DD04 真实业务链路为：`app.dd_import`（现场数据需要时）→ `eval.dd04 prepare` → `eval.run` → `eval.dd04 export` → `eval.dd04 validate`。`validate` 只验证六列结构、编码和编号完整性，不代表评级、额度或报告全文业务正确。

## A6 环境预演状态

- 已完成本机模拟离线预演（2026-10-25，`5d98b16`）：空目录解压、离线依赖安装、`/api/health/ready`、前端路由及 LA001 的 `prepare → run → export → validate` 链路通过。
- 尚未在另一台干净 Windows 机器真断网完成安装、双击 `start.bat`、批量链路，并验证评委机对 DeepSeek API、云 MySQL / Redis 与白名单的访问。
- 本机预演不能替代最终 SHA、最终压缩包和目标评委机验收。

## 封包步骤

干净机实测操作卡：[赛题04干净机断网实测操作卡](../docs/50-runbooks/赛题04干净机断网实测操作卡.md)。

1. 仅当依赖或前端有变化时，在有网 Windows 上执行 `pack-offline.ps1`，并将更新后的 `vendor/` 与 `ocft-starter/dist/` 纳入最终版本。
2. 可先不带队名预生成材料：
   ```bat
   ocft-backend\.venv\Scripts\python.exe submission\pack_dd04.py --prep
   ```
   产出 / 重生第三方组件、`dd04/manifest.generated.yaml`、`dd04/团队与元信息表.xlsx`、`release/OCFT-DD04-<sha>.zip` 和邮件正文模板。
3. 最终 SHA、日期确定后再次准备（第一联系人信息已补齐）：
   ```bat
   ocft-backend\.venv\Scripts\python.exe submission\pack_dd04.py --prep --team 智算先锋队 ^
     --contact-name 黎锦涛 --contact-phone <手机> --contact-email <邮箱> ^
     --commit <40位SHA> --date <YYYY-MM-DD>
   ```
4. 把四张 M4 截图复制到 `submission/dd04/artifacts/`，保持脚本 `optional_map` 约定的无队名前缀源文件名；`智算先锋队_赛题04_演示视频.mp4`（8:45、H.264/AAC）及 `.srt` 已在该目录。技术方案 / 测试报告 PDF 与 M9 样例也在该目录。
5. 在最终 SHA 重跑后端测试、红线扫描、前端 lint / build、公开集实时评测与 DD04 导出校验；现场取得官方非公开输入后实时导入、运行并替换正式命名非公开 CSV，不得把团队衍生演练称为官方结果。
6. 最终封包：
   ```bat
   ocft-backend\.venv\Scripts\python.exe submission\pack_dd04.py --pack --team 智算先锋队 ^
     --contact-name 黎锦涛 --contact-phone <手机> --contact-email <邮箱> ^
     --commit <40位SHA> --date <YYYY-MM-DD>
   ```
   缺材料时可加 `--allow-missing` 生成草稿包自检，但不得用于正式投递。
7. 解压 `release/04_智算先锋队_Agent大赛提交.zip` 自检：根目录直接可见 `README.md`、`manifest.yaml`、技术方案；无加密、分卷、`.git` 或额外目录层；总包 ≤500MB。
8. 换干净 Windows 机按 A6 操作卡真断网复验最终系统包（双击 `start.bat` 并批量跑一笔）。
9. 发邮件：外网 `2364245903@qq.com`，内网 `<内网提交邮箱>`；主题与包名 `04_智算先锋队_Agent大赛提交` 一致；正文用 `dd04/智算先锋队_赛题04_投递邮件正文.txt`；收到组委会回复才算提交成功。包 ≥200MB 时按官方时限用 U 盘拷到评委电脑。

## 正式投递前仍缺

- M6：8:45 真实链路演示视频已生成；封包前按最终 SHA 重验材料一致性；
- 最终提交日期（第一联系人黎锦涛及六位成员联系方式已补齐）；
- 最终 40 位 commit SHA 下的全套重验、材料复核、必要的 PDF 重出与重新 `--prep` / `--pack`；
- A6 异机真断网及模型接口、云 MySQL / Redis、白名单闭环；
- 现场官方非公开输入的实时运行与正式结果替换；
- 最终包解压验收、邮件投递和组委会回执。

提交包不得出现真实客户数据。比赛期间仅按团队决策向私有交付包提供 `.env`、`config.yaml` 中的密文配置及 `master.key`；不得提交或展示明文密码、API Key、真实连接串，赛后删除并轮换全部凭据。
