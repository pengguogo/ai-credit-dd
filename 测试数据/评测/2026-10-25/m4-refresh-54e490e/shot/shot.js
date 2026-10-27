// M4 截图重拍（HEAD 54e490e）：LA001 完整尽调报告（预览页正文在 iframe srcdoc，单独渲染后截图）+ LA003 问询工作台。
// 产物：截图01_尽调报告_完整.png / 截图02_财务分析.png / 截图03_风险提示与反欺诈.png / 截图04_自然语言问询.png
const path = require('node:path');
const fs = require('node:fs');
const { chromium } = require('playwright-core');

const BASE = 'http://127.0.0.1:8000';
const OUT = path.resolve(__dirname, '..', 'm4-screenshots');
const VP = { width: 1600, height: 1000 };
const REPORT_W = 1280;
const PASSWORD = 'Admin@123';
const Q_LA001 = '对贷款申请 LA001 生成完整尽调报告';
const Q_LA003 = '鑫达置业有限公司的对外担保合计是多少？有没有逾期？';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (msg) => console.log(`[${new Date().toISOString().slice(11, 19)}] ${msg}`);

async function newSession(page) {
  const btn = page.locator('button:has-text("新会话")');
  if ((await btn.count()) && (await btn.first().isEnabled().catch(() => false))) {
    await btn.first().click();
    await sleep(600);
  }
}

async function openExecPanel(page) {
  const btn = page.locator('button:has-text("执行过程")');
  if (await btn.count()) await btn.first().click().catch(() => {});
  await sleep(400);
}

async function ask(page, question) {
  await page.fill('textarea', question);
  await page.click('button[aria-label="发送"]');
}

// 从预览页 popup 取 iframe srcdoc（完整自包含报告 HTML）
async function readReportHtml(popup) {
  for (let i = 0; i < 20; i++) {
    const html = await popup.evaluate(() => {
      const f = document.querySelector('iframe[title="企业信贷尽调报告正文"]');
      return f ? f.getAttribute('srcdoc') : null;
    }).catch(() => null);
    if (html && html.length > 1000) return html;
    await sleep(500);
  }
  throw new Error('预览页 iframe srcdoc 读取失败');
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--font-render-hinting=none'] });
  const ctx = await browser.newContext({ viewport: VP, deviceScaleFactor: 1, locale: 'zh-CN' });
  const page = await ctx.newPage();

  // --- 登录（用户名默认 admin） ---
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[autocomplete="current-password"]', PASSWORD);
  await page.click('button[type=submit]');
  await page.waitForURL(`${BASE}/`, { timeout: 30000 });
  await page.waitForSelector('textarea');
  log('登录完成，进入工作台');

  // --- LA001 完整尽调（真实模型） ---
  await ask(page, Q_LA001);
  log(`已发送 LA001 问句：${Q_LA001}`);
  await page.waitForSelector('button:has-text("预览报告")', { timeout: 240000 });
  log('LA001 尽调完成，预览报告按钮出现');

  // --- 打开预览页并读取报告 HTML ---
  const [popup] = await Promise.all([
    ctx.waitForEvent('page'),
    page.locator('button:has-text("预览报告")').first().click(),
  ]);
  await popup.waitForLoadState('domcontentloaded');
  await popup.waitForSelector('iframe[title="企业信贷尽调报告正文"]', { timeout: 30000 });
  const reportHtml = await readReportHtml(popup);
  log(`已读取报告 HTML（${reportHtml.length} 字符）`);

  // --- 独立页面渲染 srcdoc，按 1280 宽截图 ---
  const report = await ctx.newPage();
  await report.setViewportSize({ width: REPORT_W, height: 1000 });
  await report.setContent(reportHtml, { waitUntil: 'load' });
  await report.evaluate(() => document.fonts.ready).catch(() => {});
  await sleep(1200);

  await report.screenshot({ path: path.join(OUT, '截图01_尽调报告_完整.png'), fullPage: true });
  log(`截图01 完成（fullPage ${REPORT_W}×${(await shot01Metadata(report)).height}）`);

  // --- 章节定位：截图02=财务分析节；截图03=风险提示至文末 ---
  const doc = await report.evaluate(() => {
    const heads = [...document.querySelectorAll('.section-head h2')].map((e) => ({
      text: (e.textContent || '').trim(),
      top: e.getBoundingClientRect().top + window.scrollY,
    }));
    return { heads, height: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight) };
  });
  log(`h2 章节：${doc.heads.map((h) => `${h.text}@${Math.round(h.top)}`).join(' | ')}；文档高 ${Math.round(doc.height)}`);

  const firstFinance = doc.heads.find((h) => h.text.includes('财务分析'));
  const risk = doc.heads.find((h) => h.text.includes('风险提示'));
  if (!firstFinance || !risk) throw new Error(`章节定位失败：finance=${!!firstFinance} risk=${!!risk}`);

  // clip 需落在视口内：把视口高度调到整个文档高（1280 宽下 ≤16k，安全），并重测章节坐标
  await report.setViewportSize({ width: REPORT_W, height: Math.ceil(doc.height) });
  await sleep(600);
  const pos = await report.evaluate(() => {
    const map = {};
    for (const e of document.querySelectorAll('.section-head h2')) {
      const t = (e.textContent || '').trim();
      if (t.includes('财务分析') && !map.finance) map.finance = e.getBoundingClientRect().top + window.scrollY;
      if (t.includes('风险提示') && !map.risk) map.risk = e.getBoundingClientRect().top + window.scrollY;
    }
    map.height = Math.max(document.documentElement.scrollHeight, document.body.scrollHeight);
    return map;
  });
  log(`视口调整后重测：finance@${Math.round(pos.finance)} risk@${Math.round(pos.risk)} 文档高 ${Math.round(pos.height)}`);

  const clip02 = { x: 0, y: pos.finance, width: REPORT_W, height: pos.risk - pos.finance };
  await report.screenshot({ path: path.join(OUT, '截图02_财务分析.png'), clip: clip02 });
  log(`截图02 完成（财务分析节，高 ${Math.round(clip02.height)}）`);

  const clip03 = { x: 0, y: pos.risk, width: REPORT_W, height: pos.height - pos.risk };
  await report.screenshot({ path: path.join(OUT, '截图03_风险提示与反欺诈.png'), clip: clip03 });
  log(`截图03 完成（风险提示至文末，高 ${Math.round(clip03.height)}）`);

  await report.close();
  await popup.close().catch(() => {});

  // --- LA003 自然语言问询（工作台 1600×1000） ---
  await page.bringToFront();
  await newSession(page);
  await page.waitForSelector('textarea');
  await ask(page, Q_LA003);
  log(`已发送 LA003 问句：${Q_LA003}`);
  await openExecPanel(page);
  await page.waitForFunction(() => /依据\s*\d+\s*条证据/.test(document.body.innerText || ''), { timeout: 180000 });
  await sleep(1500);
  await page.screenshot({ path: path.join(OUT, '截图04_自然语言问询.png') });
  log('截图04 完成（工作台 LA003 问询 + 执行过程）');

  await browser.close();
  const files = fs.readdirSync(OUT).map((f) => `${f} ${fs.statSync(path.join(OUT, f)).size}`);
  console.log(`\n产物目录：${OUT}\n${files.join('\n')}`);
})().catch((err) => { console.error('截图失败：', err && err.stack || err); process.exit(1); });

async function shot01Metadata(report) {
  const size = await report.evaluate(() => ({ height: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight) }));
  return size;
}
