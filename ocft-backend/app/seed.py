"""运行时样本数据 — 只含原始业务字段（redline-scan 对本 docstring 的命中属于说明文字，可忽略）。

@why 红线 R4/R5：结论、标签、预期答案不进运行时数据。
     - 信贷申请的审批状态（status）、交易的 isFraud/fraudType、理赔的 decision/decisionReason、
       文档的 extractedKpis 已迁至 eval/fixtures/sample_labels.json，仅供离线评分。
     - 运行时结论一律由规则引擎/工具基于下列原始字段实时计算。
     - 新增样本时只写原始字段；任何答案放评测目录。
"""

# status 统一为 pending：运行时不暴露历史审批结论
CREDIT_APPLICATIONS = [
    {"applicationId": "APP-2026-1001", "customerName": "王建国", "businessType": "房抵贷", "applyAmount": 1500000, "termMonths": 240, "creditScore": 720, "debtRatio": 0.38, "collateral": 2600000, "riskTags": [], "status": "pending", "appliedAt": "2026-09-02T09:14:00+08:00"},
    {"applicationId": "APP-2026-1002", "customerName": "李文静", "businessType": "小微贷", "applyAmount": 300000, "termMonths": 36, "creditScore": 665, "debtRatio": 0.52, "collateral": None, "riskTags": ["多头借贷"], "status": "pending", "appliedAt": "2026-09-05T14:32:00+08:00"},
    {"applicationId": "APP-2026-1003", "customerName": "陈志强", "businessType": "小微贷", "applyAmount": 500000, "termMonths": 24, "creditScore": 640, "debtRatio": 0.61, "collateral": None, "riskTags": ["多头借贷", "行业高风险"], "status": "pending", "appliedAt": "2026-09-08T10:05:00+08:00"},
    {"applicationId": "APP-2026-1004", "customerName": "赵美琳", "businessType": "消费贷", "applyAmount": 80000, "termMonths": 12, "creditScore": 755, "debtRatio": 0.22, "collateral": None, "riskTags": [], "status": "pending", "appliedAt": "2026-09-12T16:48:00+08:00"},
    {"applicationId": "APP-2026-1005", "customerName": "周海涛", "businessType": "房抵贷", "applyAmount": 2000000, "termMonths": 180, "creditScore": 688, "debtRatio": 0.45, "collateral": 3100000, "riskTags": ["评估价虚高风险"], "status": "pending", "appliedAt": "2026-09-15T11:20:00+08:00"},
    {"applicationId": "APP-2026-1006", "customerName": "吴晓芳", "businessType": "消费贷", "applyAmount": 120000, "termMonths": 24, "creditScore": 622, "debtRatio": 0.55, "collateral": None, "riskTags": ["近期查询频繁"], "status": "pending", "appliedAt": "2026-09-18T09:00:00+08:00"},
    {"applicationId": "APP-2026-1007", "customerName": "郑国栋", "businessType": "小微贷", "applyAmount": 1000000, "termMonths": 60, "creditScore": 798, "debtRatio": 0.31, "collateral": None, "riskTags": [], "status": "pending", "appliedAt": "2026-09-22T15:30:00+08:00"},
    {"applicationId": "APP-2026-1008", "customerName": "冯丽华", "businessType": "消费贷", "applyAmount": 50000, "termMonths": 12, "creditScore": 710, "debtRatio": 0.29, "collateral": None, "riskTags": [], "status": "pending", "appliedAt": "2026-09-26T08:45:00+08:00"},
    {"applicationId": "APP-2026-1009", "customerName": "蒋伟明", "businessType": "房抵贷", "applyAmount": 1800000, "termMonths": 240, "creditScore": 601, "debtRatio": 0.68, "collateral": 2500000, "riskTags": ["负债过高", "抵押物二押"], "status": "pending", "appliedAt": "2026-09-29T13:12:00+08:00"},
    {"applicationId": "APP-2026-1010", "customerName": "沈雅婷", "businessType": "小微贷", "applyAmount": 200000, "termMonths": 36, "creditScore": 735, "debtRatio": 0.33, "collateral": None, "riskTags": [], "status": "pending", "appliedAt": "2026-10-03T10:30:00+08:00"},
    {"applicationId": "APP-2026-1011", "customerName": "韩磊", "businessType": "小微贷", "applyAmount": 450000, "termMonths": 36, "creditScore": 630, "debtRatio": 0.58, "collateral": None, "riskTags": ["多头借贷", "经营流水下滑"], "status": "pending", "appliedAt": "2026-10-06T14:22:00+08:00"},
    {"applicationId": "APP-2026-1012", "customerName": "杨春梅", "businessType": "消费贷", "applyAmount": 95000, "termMonths": 18, "creditScore": 742, "debtRatio": 0.26, "collateral": None, "riskTags": [], "status": "pending", "appliedAt": "2026-10-10T09:38:00+08:00"},
]

TRANSACTIONS = [
    {"txnId": "TXN-88421001", "accountId": "ACC-10231", "channel": "app", "amount": 299.0, "city": "上海", "deviceFingerprint": "DF-a3f8", "minutesSinceLastTxn": 320, "occurredAt": "2026-10-01T08:12:00+08:00"},
    {"txnId": "TXN-88421002", "accountId": "ACC-10231", "channel": "app", "amount": 48800.0, "city": "上海", "deviceFingerprint": "DF-a3f8", "minutesSinceLastTxn": 4, "occurredAt": "2026-10-01T08:16:00+08:00"},
    {"txnId": "TXN-88421003", "accountId": "ACC-20455", "channel": "web", "amount": 0.01, "city": "深圳", "deviceFingerprint": "DF-b7c2", "minutesSinceLastTxn": 1440, "occurredAt": "2026-10-01T12:40:00+08:00"},
    {"txnId": "TXN-88421004", "accountId": "ACC-20455", "channel": "web", "amount": 29999.0, "city": "深圳", "deviceFingerprint": "DF-b7c2", "minutesSinceLastTxn": 2, "occurredAt": "2026-10-01T12:42:00+08:00"},
    {"txnId": "TXN-88421005", "accountId": "ACC-30712", "channel": "atm", "amount": 5000.0, "city": "广州", "deviceFingerprint": None, "minutesSinceLastTxn": 60, "occurredAt": "2026-10-02T21:05:00+08:00"},
    {"txnId": "TXN-88421006", "accountId": "ACC-30712", "channel": "atm", "amount": 5000.0, "city": "昆明", "deviceFingerprint": None, "minutesSinceLastTxn": 38, "occurredAt": "2026-10-02T21:43:00+08:00"},
    {"txnId": "TXN-88421007", "accountId": "ACC-40988", "channel": "pos", "amount": 1280.0, "city": "杭州", "deviceFingerprint": None, "minutesSinceLastTxn": 720, "occurredAt": "2026-10-03T10:20:00+08:00"},
    {"txnId": "TXN-88421008", "accountId": "ACC-51203", "channel": "app", "amount": 1.0, "city": "成都", "deviceFingerprint": "DF-e9d1", "minutesSinceLastTxn": 10080, "occurredAt": "2026-10-04T09:00:00+08:00"},
    {"txnId": "TXN-88421009", "accountId": "ACC-51203", "channel": "app", "amount": 19999.0, "city": "成都", "deviceFingerprint": "DF-e9d1", "minutesSinceLastTxn": 3, "occurredAt": "2026-10-04T09:03:00+08:00"},
    {"txnId": "TXN-88421010", "accountId": "ACC-61240", "channel": "app", "amount": 150.0, "city": "北京", "deviceFingerprint": "DF-f2a5", "minutesSinceLastTxn": 90, "occurredAt": "2026-10-05T18:30:00+08:00"},
    {"txnId": "TXN-88421011", "accountId": "ACC-71890", "channel": "web", "amount": 8600.0, "city": "武汉", "deviceFingerprint": "DF-c4b9", "minutesSinceLastTxn": 2880, "occurredAt": "2026-10-06T14:15:00+08:00"},
    {"txnId": "TXN-88421012", "accountId": "ACC-82003", "channel": "atm", "amount": 20000.0, "city": "东莞", "deviceFingerprint": None, "minutesSinceLastTxn": 15, "occurredAt": "2026-10-07T23:58:00+08:00"},
]

CLAIMS = [
    {"claimId": "CLM-2026-0301", "insurant": "孙晓东", "insuranceType": "车险", "incidentDate": "2026-09-18", "reportedAt": "2026-09-18T16:40:00+08:00", "claimAmount": 8600, "materials": ["事故认定书", "维修发票", "行驶证", "驾驶证"], "missingMaterials": []},
    {"claimId": "CLM-2026-0302", "insurant": "钱丽", "insuranceType": "意外", "incidentDate": "2026-09-22", "reportedAt": "2026-09-23T09:15:00+08:00", "claimAmount": 3200, "materials": ["门诊病历", "医疗发票"], "missingMaterials": ["事故经过说明"]},
    {"claimId": "CLM-2026-0303", "insurant": "许建军", "insuranceType": "健康", "incidentDate": "2026-09-25", "reportedAt": "2026-09-26T11:00:00+08:00", "claimAmount": 45000, "materials": ["住院病案", "医疗发票", "费用清单", "诊断证明"], "missingMaterials": []},
    {"claimId": "CLM-2026-0304", "insurant": "何美娟", "insuranceType": "健康", "incidentDate": "2026-09-28", "reportedAt": "2026-09-30T14:20:00+08:00", "claimAmount": 12800, "materials": ["门诊病历", "医疗发票"], "missingMaterials": ["既往病史授权书"]},
    {"claimId": "CLM-2026-0305", "insurant": "范伟", "insuranceType": "车险", "incidentDate": "2026-10-02", "reportedAt": "2026-10-02T20:05:00+08:00", "claimAmount": 38000, "materials": ["事故认定书", "维修报价单"], "missingMaterials": ["维修发票", "现场照片"]},
    {"claimId": "CLM-2026-0306", "insurant": "汪桂英", "insuranceType": "寿险", "incidentDate": "2026-10-05", "reportedAt": "2026-10-08T10:30:00+08:00", "claimAmount": 500000, "materials": ["死亡证明", "户籍注销证明"], "missingMaterials": ["受益人关系证明"]},
    {"claimId": "CLM-2026-0307", "insurant": "郭涛", "insuranceType": "意外", "incidentDate": "2026-10-08", "reportedAt": "2026-10-09T09:00:00+08:00", "claimAmount": 800, "materials": ["门诊病历", "医疗发票"], "missingMaterials": []},
    {"claimId": "CLM-2026-0308", "insurant": "林秀英", "insuranceType": "健康", "incidentDate": "2026-10-10", "reportedAt": "2026-10-11T15:45:00+08:00", "claimAmount": 6800, "materials": ["门诊病历", "医疗发票", "处方单"], "missingMaterials": []},
]

FIN_DOCS = [
    {"docId": "DOC-2026-001", "docType": "年报", "company": "某城商行", "period": "2025 年度", "rawText": "报告期内，本行实现营业收入 128.6 亿元，同比增长 7.3%；归属于母公司股东的净利润 46.2 亿元，同比增长 9.1%。截至报告期末，本行不良贷款率 1.42%，较上年末下降 0.08 个百分点；拨备覆盖率 212.5%，资本充足率 13.86%，核心一级资本充足率 10.21%。", "difficulty": "KPI 嵌入长句 + 同比/较上年末多种表述"},
    {"docId": "DOC-2026-002", "docType": "研报", "company": "某财险公司", "period": "2026 中期", "rawText": "综合成本率方面，车险业务 98.3%（其中赔付率 71.2%、费用率 27.1%），非车业务 102.6%。我们预计全年车险 COR 有望改善至 97.5% 左右，维持\"增持\"评级。", "difficulty": "括号内嵌套指标 + 预测值与实际值混排"},
    {"docId": "DOC-2026-003", "docType": "监管文件", "company": "监管通报", "period": "2026 Q3", "rawText": "各机构应当于每季度结束后 15 个工作日内报送流动性覆盖率。对于连续两个季度低于 100% 的机构，应当于 5 个工作日内提交书面说明及整改计划。本季度共 3 家机构触发报送义务，其中 1 家已立案调查。", "difficulty": "义务主体识别 + 条件句中的时限数字"},
    {"docId": "DOC-2026-004", "docType": "公告", "company": "某上市险企", "period": "2026-10", "rawText": "本公司接到股东通知，其持有的 1.2 亿股 H 股(占本公司总股本 5.23%)已被质押，用于其自身融资安排。本次质押不涉及本公司控制权变更。", "difficulty": "股权质押类公告的事件抽取(主体/动作/比例)"},
]
