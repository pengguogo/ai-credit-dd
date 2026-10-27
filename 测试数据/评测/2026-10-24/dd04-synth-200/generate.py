"""以赛题04官方 10 家企业为模板，推导生成 200 家新企业 + 200 笔贷款申请（模拟现场非公开集）。

- 只读官方 9 张业务表，不读 question_public.csv / 公开测试集答案.csv。
- 每家新企业 = 某个模板企业的特征结构（行业、事件类型、诉讼/担保/关联结构、风险标记）
  × 全局规模系数 k × 逐字段 ±3% 扰动；名称、法人、编号全部重新生成。
- 勾稽保持：owners_equity = total_assets - total_liabilities；对外担保总额 = 担保明细之和。
- 输出 data/（9 张业务表 + 原样复制的 schema_relationships.csv，可 `python -m app.dd_import <data目录>` 导入）、
  facts.csv（机械事实标签，仅供 eval 离线对照，不含评级/额度答案）。
用法：python generate.py [--seed 20261024]
"""
import argparse
import csv
import random
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[3] / "docs" / "00-rules" / "赛题" / "赛题04_企业智能信贷尽调" / "data"
OUT = HERE / "data"
TABLES = ["enterprise_basic", "enterprise_shareholder", "enterprise_finance",
          "enterprise_public_opinion", "enterprise_lawsuit", "enterprise_related",
          "enterprise_guarantee", "enterprise_risk", "loan_application"]
N = 200
FIRST_EID = 101

# 模板企业名 = 品牌 + 行业后缀；新企业替换品牌，关联方名称里的品牌同步替换
TEMPLATE_BRAND = {"E001": "华东精密", "E002": "星辰", "E003": "鑫达", "E004": "远洋", "E005": "绿源",
                  "E006": "宏基", "E007": "蜀香", "E008": "顺达", "E009": "康宁", "E010": "光耀"}
BRANDS = list(dict.fromkeys(
    "瑞丰 恒泰 汇通 锦程 盛达 华信 中联 天成 永兴 鼎盛 金桥 宏远 正和 嘉禾 博瑞 聚源 安泰 润泽 "
    "德隆 致远 凯越 同创 利达 新拓 海纳 明德 卓越 方圆 东升 万嘉 祥和 天合 信达 国泰 银河 星耀 "
    "鸿运 鑫源 弘毅 泰和 晨光 华瑞 腾跃 远航 益丰 隆基 晟达 拓普 华铭 盈科".split()))
SURNAMES = "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾萧田董袁潘蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
GIVEN = "伟 芳 娜 敏 静 强 磊 军 洋 勇 艳 杰 涛 明 超 秀英 华 慧 建华 志强 海燕 振国 文博 俊杰 宏伟 丽娟 国庆 晓东 立新 春生 德明 雪梅 永刚 子轩 浩然 嘉怡 思远 宇航 建平 卫东".split()
MONEY = {"register_capital", "registered_capital_paid", "contribution_amount", "revenue", "net_profit",
         "total_assets", "total_liabilities", "operating_cashflow", "accounts_receivable", "inventory",
         "fixed_assets", "short_term_loan", "long_term_loan", "accounts_payable", "other_receivable",
         "prepayment", "rd_expense", "sales_expense", "admin_expense", "finance_expense", "amount",
         "guarantee_amount", "existing_loan_balance", "overdue_amount"}


def read(name):
    with open(SRC / f"{name}.csv", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def money(rng, value, k):
    """金额按规模系数缩放并扰动 ±3%，保持符号，取整到万元。"""
    v = float(value)
    if v == 0:
        return 0
    return int(round(v * k * rng.uniform(0.97, 1.03)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20261024)
    rng = random.Random(parser.parse_args().seed)

    headers, src = {}, {}
    for t in TABLES:
        headers[t], src[t] = read(t)
    by_eid = {t: {} for t in TABLES}
    for t in TABLES:
        for r in src[t]:
            by_eid[t].setdefault(r["enterprise_id"], []).append(r)
    templates = sorted(TEMPLATE_BRAND)
    out = {t: [] for t in TABLES}
    facts = []
    brands = BRANDS[:]
    rng.shuffle(brands)
    used_names, used_people = set(), set()

    def person():
        while True:
            name = rng.choice(SURNAMES) + rng.choice(GIVEN)
            if name not in used_people:
                used_people.add(name)
                return name

    for i in range(N):
        tid = templates[i % len(templates)]
        eid, aid = f"E{FIRST_EID + i}", f"LA{FIRST_EID + i}"
        k = round(rng.uniform(0.5, 2.0), 3)
        old = TEMPLATE_BRAND[tid]
        base = by_eid["enterprise_basic"][tid][0]
        suffix = base["enterprise_name"].removeprefix(old)
        brand = brands[i % len(brands)]
        name = brand + suffix
        n = 2
        while name in used_names:  # 品牌池不足时加序号区分
            name = f"{brand}{'一二三四五六七八九'[n - 2]}{suffix}"
            n += 1
        used_names.add(name)
        new_brand = name.removesuffix(suffix)
        rename = lambda s: s.replace(old, new_brand)
        legal = person()
        names = {base["legal_person"]: legal}  # 模板自然人 → 新自然人

        # enterprise_basic
        b = dict(base)
        region = base["credit_code"][2:5]  # 与模板注册地一致，避免工商核验误报地区不一致
        year = int(base["establish_date"][:4]) + rng.randint(-3, 3)
        b.update(enterprise_id=eid, enterprise_name=name, legal_person=legal, actual_controller=legal,
                 legal_person_id=f"{region}***********{rng.randint(1000, 9999)}",
                 credit_code="91" + region + "000MA" + "".join(rng.choices("0123456789ABCDEFGHJKLMNPQRTUWXY", k=8)),
                 establish_date=f"{year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                 employee_count=str(max(10, int(int(base["employee_count"]) * k))),
                 register_address=re.sub(r"\d+号", f"{rng.randint(1, 999)}号", base["register_address"]))
        cap = round(float(base["register_capital"]) * k / 100) * 100 or 100
        paid_ratio = float(base["registered_capital_paid"]) / float(base["register_capital"])
        b["register_capital"], b["registered_capital_paid"] = str(cap), str(round(cap * paid_ratio))
        out["enterprise_basic"].append(b)

        for r in by_eid["enterprise_shareholder"][tid]:
            s = dict(r, enterprise_id=eid)
            if s["shareholder_type"] == "自然人股东":
                s["shareholder_name"] = names.setdefault(r["shareholder_name"], person())
            else:
                s["shareholder_name"] = rename(r["shareholder_name"])
            s["contribution_amount"] = str(round(cap * float(r["shareholding_ratio"]) / 100))
            out["enterprise_shareholder"].append(s)

        fin = {}
        for r in by_eid["enterprise_finance"][tid]:
            f = dict(r, enterprise_id=eid)
            for key in r:
                if key in MONEY:
                    f[key] = str(money(rng, r[key], k))
            # 负债率按模板比率 ±3% 重算，避免分别扰动后漂移出模板档位
            ratio = float(r["total_liabilities"]) / float(r["total_assets"]) * rng.uniform(0.97, 1.03)
            f["total_liabilities"] = str(round(int(f["total_assets"]) * ratio))
            f["owners_equity"] = str(int(f["total_assets"]) - int(f["total_liabilities"]))
            fin[int(r["year"])] = f
            out["enterprise_finance"].append(f)

        seq = 1
        for r in by_eid["enterprise_public_opinion"][tid]:
            content = rename(r["event_content"])
            content = re.sub(r"(\d+(?:\.\d+)?)万", lambda m: f"{max(1, round(float(m.group(1)) * k))}万", content)
            out["enterprise_public_opinion"].append(dict(
                r, enterprise_id=eid, event_id=f"PO{FIRST_EID + i}{seq:02d}", event_content=content))
            seq += 1

        lawsuits = []
        for j, r in enumerate(by_eid["enterprise_lawsuit"].get(tid, []), 1):
            num = re.sub(r"\d+号$", f"{rng.randint(1000, 9999)}号", r["case_number"])
            row = dict(r, enterprise_id=eid, case_id=f"C{FIRST_EID + i}{j:02d}", case_number=num,
                       amount=str(max(1, money(rng, r["amount"], k))))
            lawsuits.append(row)
        out["enterprise_lawsuit"] += lawsuits

        related = [dict(r, enterprise_id=eid, related_enterprise_name=rename(r["related_enterprise_name"]))
                   for r in by_eid["enterprise_related"].get(tid, [])]
        out["enterprise_related"] += related

        guarantees = [dict(r, enterprise_id=eid, guaranteed_party=rename(r["guaranteed_party"]),
                           guarantee_amount=str(max(10, round(float(r["guarantee_amount"]) * k / 10) * 10)))
                      for r in by_eid["enterprise_guarantee"].get(tid, [])]
        out["enterprise_guarantee"] += guarantees
        guarantee_total = sum(int(g["guarantee_amount"]) for g in guarantees)

        risk = dict(by_eid["enterprise_risk"][tid][0], enterprise_id=eid)
        risk["existing_loan_balance"] = str(money(rng, risk["existing_loan_balance"], k))
        risk["overdue_amount"] = str(money(rng, risk["overdue_amount"], k))
        risk["external_guarantee_amount"] = str(guarantee_total)
        risk["public_opinion_score"] = str(min(99, max(1, int(risk["public_opinion_score"]) + rng.randint(-3, 3))))
        out["enterprise_risk"].append(risk)

        app = dict(by_eid["loan_application"][tid][0], application_id=aid, enterprise_id=eid)
        app["apply_amount"] = str(max(50, round(float(app["apply_amount"]) * k / 50) * 50))
        app["apply_date"] = f"2024-{rng.randint(1, 6):02d}-{rng.randint(1, 28):02d}"
        out["loan_application"].append(app)

        # 机械事实标签（eval 离线对照用；不是评级/额度答案）
        f23, f21 = fin[2023], fin[2021]
        num = lambda f, key: float(f[key])
        rev = num(f23, "revenue")
        facts.append({
            "application_id": aid, "enterprise_id": eid, "enterprise_name": name, "template_enterprise_id": tid,
            "scale_k": k, "apply_amount": app["apply_amount"], "loan_term_months": app["loan_term_months"],
            "guarantee_type": app["guarantee_type"],
            "revenue_2023": f23["revenue"], "net_profit_2023": f23["net_profit"],
            "debt_ratio_2023": f"{num(f23, 'total_liabilities') / num(f23, 'total_assets'):.4f}",
            "net_margin_2023": f"{num(f23, 'net_profit') / rev:.4f}",
            "revenue_cagr_2021_2023": f"{(rev / num(f21, 'revenue')) ** 0.5 - 1:.4f}",
            "ocf_to_net_profit_2023": f"{num(f23, 'operating_cashflow') / num(f23, 'net_profit'):.4f}",
            "ar_to_revenue_2023": f"{num(f23, 'accounts_receivable') / rev:.4f}",
            "other_receivable_to_revenue_2023": f"{num(f23, 'other_receivable') / rev:.4f}",
            "existing_loan_balance": risk["existing_loan_balance"], "overdue_count": risk["overdue_count"],
            "overdue_amount": risk["overdue_amount"], "external_guarantee_amount": guarantee_total,
            "overdue_guarantee_count": sum(g["is_overdue"] == "是" for g in guarantees),
            "lawsuit_count": len(lawsuits), "lawsuit_amount": sum(int(x["amount"]) for x in lawsuits),
            "executed_case_count": sum(x["litigation_role"] == "被执行人" for x in lawsuits),
            "related_count": len(related), "guarantee_circle_count": sum(r["is_guarantee_circle"] == "是" for r in related),
            "negative_opinion_count": sum(r["sentiment"] == "负面" for r in by_eid["enterprise_public_opinion"][tid]),
            "public_opinion_score": risk["public_opinion_score"],
            "legal_person_dishonest": b["legal_person_dishonest"],
            "legal_person_consumption_limit": b["legal_person_consumption_limit"],
            "abnormal_operation": risk["abnormal_operation"],
        })

    OUT.mkdir(exist_ok=True)
    for t in TABLES:
        with open(OUT / f"{t}.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=headers[t], lineterminator="\n")
            w.writeheader()
            w.writerows(out[t])
    shutil.copy(SRC / "schema_relationships.csv", OUT / "schema_relationships.csv")  # 表关系说明原样沿用
    with open(HERE / "facts.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(facts[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(facts)
    print({t: len(out[t]) for t in TABLES}, "facts", len(facts))


if __name__ == "__main__":
    main()
