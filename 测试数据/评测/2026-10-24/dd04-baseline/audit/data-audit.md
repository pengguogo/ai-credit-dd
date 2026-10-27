# 赛题 04 数据体检

结构检查通过：True（warning 仍需人工复核）

| 表 | 数据行数 |
|---|---:|
| enterprise_basic | 10 |
| enterprise_finance | 30 |
| enterprise_guarantee | 11 |
| enterprise_lawsuit | 22 |
| enterprise_public_opinion | 28 |
| enterprise_related | 27 |
| enterprise_risk | 10 |
| enterprise_shareholder | 23 |
| loan_application | 10 |

## 定位清单

| 级别 | 代码 | 表 | CSV 行 | 字段 | 说明 |
|---|---|---|---|---|---|

## 范围与待确认

- 实物为 9 张业务表；提交说明称 10 张，待负责人确认，未虚构额外业务表。
- 明细表采用候选业务键检查重复，最终数据库主键由数据负责人确定。
- 不读取 question_public.csv、公开测试集答案.csv；不导入数据库、不修改原文件。
- 金额单位、比率口径、财务时点和缺失科目须业务确认；体检通过不代表可授信。
- 现有科目缺流动资产、流动负债、营业成本；不推算流动/速动比率或毛利率。
