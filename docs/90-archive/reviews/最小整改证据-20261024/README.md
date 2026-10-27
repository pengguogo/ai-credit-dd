# 最小整改验证证据（2026-10-24）

见[整改记录](../最小整改-评委问题-20261024.md)。被修改的是main fe2e9ae之上的工作区；原未提交改动保留，未提交推送。

- pytest.log：本轮最终全量463 passed/15 warnings。
- lint.log、build.log：本轮最终前端检查及重建dist，退出0；Node版本与包体积告警未隐瞒。
- redline.log：0 ERROR/3 WARN（seed.py注释误报），非全路径合规证明。
- live-check.json：运行中的后端就绪、图片422、工商步骤成功。
- name-fields-live.json、姓名掩码实测.png：本轮补齐topShareholder及说明文本后，真实接口及页面均掩码；截图不是正式1280×720交付物。
- [真实公开样例](../../../../测试数据/评测/2026-10-24/minimal-review-fixes/summary.json)：一次收费调用批次，1条成功；同目录scorer-format-recheck.json为离线格式修正后的重核。原summary/results不回填，不声称全公开集通过。

浏览器使用页面列出的只读演示账号，检验E001→E002选择、无匹配输入及后退回E001，未作任何业务审批；未使用网络故障注入穷尽乱序组合。
