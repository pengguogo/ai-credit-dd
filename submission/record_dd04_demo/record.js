/**
 * 赛题04 自动化演示录屏（真实系统实时运行 + 中文旁白）
 *
 * 依赖：playwright-core（dsh 环境）、已安装 Chrome、本机运行的后端 8000。
 * 输出：release/_rec/run/frames/*.jpg、frames.json、timeline.json
 * 用法：node release/_rec/record.js
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const BASE = 'http://127.0.0.1:8000';
const REC = path.resolve('release/_rec');
const SCENE_FILE = process.env.SCENE_FILE || 'scenes.ready.json';
const OUT_NAME = process.env.OUT_NAME || 'run';
const OUT = path.join(REC, OUT_NAME);
const FRAMES = path.join(OUT, 'frames');
const SAVE_INTERVAL_MS = 80;
const VP = { width: 1600, height: 1000 };

const scenes = JSON.parse(fs.readFileSync(path.join(REC, SCENE_FILE), 'utf8'));
const byId = Object.fromEntries(scenes.map(s => [s.id, s]));

fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(FRAMES, { recursive: true });

let frameSeq = 0;
const frameMeta = [];
const markers = [];
let recStartMs = null;
let activeTag = 'main';

const sleep = ms => new Promise(r => setTimeout(r, ms));

function startScreencast(cdp, tag) {
  let lastSave = 0;
  cdp.on('Page.screencastFrame', frame => {
    // 立即 ack，保证出帧频率；按 80ms 抽帧，避免写盘过密
    cdp.send('Page.screencastFrameAck', { sessionId: frame.sessionId }).catch(() => {});
    if (tag !== activeTag) return;
    const ts = frame.metadata.timestamp * 1000;
    if (lastSave && ts - lastSave < SAVE_INTERVAL_MS) return;
    lastSave = ts;
    const file = `f${String(frameSeq++).padStart(6, '0')}.jpg`;
    fs.writeFileSync(path.join(FRAMES, file), Buffer.from(frame.data, 'base64'));
    frameMeta.push({ file, ts, tag });
    if (recStartMs === null || ts < recStartMs) recStartMs = ts;
  });
  return cdp.send('Page.startScreencast', {
    format: 'jpeg', quality: 82, maxWidth: VP.width, maxHeight: VP.height, everyNthFrame: 1,
  });
}

async function caption(page, text) {
  await page.evaluate(t => {
    let el = document.getElementById('dd-caption');
    if (!el) {
      el = document.createElement('div');
      el.id = 'dd-caption';
      el.style.cssText = [
        'position:fixed', 'left:0', 'right:0', 'bottom:0', 'z-index:2147483647',
        'display:flex', 'align-items:center', 'gap:14px',
        'background:rgba(6,10,18,.94)', 'color:#f8fafc',
        'font:15px/1.5 "Microsoft YaHei","PingFang SC",sans-serif',
        'padding:10px 20px', 'border-top:2px solid #ff6600',
        'box-shadow:0 -8px 24px rgba(0,0,0,.35)',
      ].join(';');
      el.innerHTML = '<span style="color:#ff6600;font-weight:600;white-space:nowrap;font-size:13px;letter-spacing:.04em">赛题04 · 智算先锋队</span>'
        + '<span id="dd-caption-text" style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></span>'
        + '<span style="display:flex;align-items:center;gap:6px;color:#ff6b5a;font:600 12px/1 \'Microsoft YaHei\';letter-spacing:.08em"><span style="width:8px;height:8px;border-radius:50%;background:#ff3b30;animation:ddpulse 1.4s ease-in-out infinite"></span>REC</span>';
      document.documentElement.appendChild(el);
      if (!document.getElementById('dd-style')) {
        const style = document.createElement('style');
        style.id = 'dd-style';
        style.textContent = '@keyframes ddpulse{0%,100%{opacity:.2;transform:scale(.85)}50%{opacity:1;transform:scale(1)}}';
        document.documentElement.appendChild(style);
      }
    }
    document.getElementById('dd-caption-text').textContent = t;
  }, text);
}

async function runScene(page, id, action) {
  const sc = byId[id];
  const start = Date.now();
  markers.push({ id, caption: sc.caption, start, narrationSec: sc.narrationSec });
  await caption(page, sc.caption);
  console.log(`▶ ${id} ${sc.caption}`);
  await action(sc, start);
  const need = sc.narrationSec * 1000 + 1200;
  const elapsed = Date.now() - start;
  if (elapsed < need) await sleep(need - elapsed);
  const marker = markers[markers.length - 1];
  marker.end = Date.now();
  console.log(`✓ ${id} ${((Date.now() - start) / 1000).toFixed(1)}s`);
}

async function newSession(page) {
  const btn = page.locator('button:has-text("新会话")');
  if (await btn.count() && await btn.first().isEnabled().catch(() => false)) {
    await btn.first().click();
    await sleep(600);
  }
}

async function openExecPanel(page) {
  const btn = page.locator('button:has-text("执行过程")');
  if (await btn.count()) {
    await btn.first().click().catch(() => {});
    await sleep(400);
  }
}

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--font-render-hinting=none'] });
  const ctx = await browser.newContext({ viewport: VP, deviceScaleFactor: 1, locale: 'zh-CN' });
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await startScreencast(cdp, 'main');
  await sleep(1200);

  await runScene(page, 'S00', async () => {
    await page.evaluate(() => {
      const card = document.createElement('div');
      card.id = 'dd-intro';
      card.style.cssText = [
        'position:fixed', 'inset:0', 'z-index:2147483645',
        'display:flex', 'flex-direction:column', 'align-items:center', 'justify-content:center',
        'gap:20px', 'background:rgba(6,10,18,.97)', 'color:#f8fafc',
        'font-family:"Microsoft YaHei","PingFang SC",sans-serif', 'text-align:center',
      ].join(';');
      card.innerHTML = `
        <div style="font:600 15px/1.4 'Microsoft YaHei';letter-spacing:.35em;color:#ff6600">AGENT 大赛 · 赛题04</div>
        <div style="font:600 52px/1.2 'Microsoft YaHei';letter-spacing:.02em">企业智能信贷尽调</div>
        <div style="font:400 22px/1.6 'Microsoft YaHei';color:#cbd5e1">多 Agent 完整链路 · 真实系统实时演示</div>
        <div style="display:flex;gap:36px;margin-top:14px;font:400 17px/1.6 'Microsoft YaHei';color:#94a3b8">
          <span>财报解析</span><span>工商核验</span><span>舆情扫描</span><span>反欺诈检测</span><span>额度测算</span><span>报告生成</span><span>自然语言问询</span>
        </div>
        <div style="margin-top:30px;font:400 15px/1.5 'Microsoft YaHei';color:#64748b">智算先锋队 · 2026-10-25</div>`;
      document.documentElement.appendChild(card);
    });
    await sleep(1500);
  });

  await runScene(page, 'S01', async () => {
    await page.evaluate(() => document.getElementById('dd-intro')?.remove());
    await sleep(9000);
    await page.fill('input[autocomplete="current-password"]', 'Admin@123');
    await sleep(1200);
    await page.click('button[type=submit]');
    await page.waitForURL(`${BASE}/`, { timeout: 30000 });
    await page.waitForSelector('textarea');
  });

  await runScene(page, 'S02B', async sc => {
    await page.goto(`${BASE}/tables`, { waitUntil: 'domcontentloaded' });
    await caption(page, sc.caption);
    await page.waitForSelector('table', { timeout: 20000 }).catch(() => {});
    await sleep(1200);
    for (let i = 0; i < 7; i++) {
      await page.mouse.move(760, 520);
      await page.mouse.wheel(0, 260);
      await sleep(3200);
    }
  });

  await runScene(page, 'S02', async () => {
    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('textarea');
    await newSession(page);
    await caption(page, '工作台 · 公开测评集 10 笔申请');
    const tab = page.locator('[role=tab]:has-text("审批表")');
    if (await tab.count()) await tab.first().click();
    await sleep(5000);
    await page.fill('textarea', '对贷款申请 LA001 做完整尽调');
    await sleep(1500);
  });

  await runScene(page, 'S03', async () => {
    await page.click('button[aria-label="发送"]');
    await openExecPanel(page);
    await page.waitForSelector('button:has-text("预览报告")', { timeout: 180000 });
  });

  await runScene(page, 'S04', async () => {
    await page.locator('button:has-text("预览报告")').scrollIntoViewIfNeeded();
    await sleep(4000);
    await page.locator('button:has-text("预览报告")').scrollIntoViewIfNeeded();
  });

  await runScene(page, 'S05', async sc => {
    const [popup] = await Promise.all([
      ctx.waitForEvent('page'),
      page.click('button:has-text("预览报告")'),
    ]);
    await popup.waitForLoadState('domcontentloaded');
    await popup.waitForSelector('iframe', { timeout: 20000 }).catch(() => {});
    await caption(popup, sc.caption);
    await sleep(1200);
    activeTag = 'preview';
    const cdp2 = await ctx.newCDPSession(popup);
    await startScreencast(cdp2, 'preview');
    for (let y = 0; y <= 12200; y += 780) {
      await popup.evaluate(top => {
        const f = document.querySelector('iframe');
        if (f && f.contentWindow) f.contentWindow.scrollTo({ top, behavior: 'smooth' });
      }, y);
      await sleep(1700);
    }
    await sleep(800);
    await cdp2.send('Page.stopScreencast').catch(() => {});
    activeTag = 'main';
    await popup.close();
    await sleep(800);
  });

  const step = async (id, route, hold = 3200) => {
    await runScene(page, id, async sc => {
      await page.goto(`${BASE}/report/${route}?enterpriseId=E001`, { waitUntil: 'domcontentloaded' });
      await caption(page, sc.caption);
      await page.waitForSelector('button:has-text("分析本步")', { timeout: 15000 }).catch(() => {});
      await sleep(1400);
      const btn = page.locator('button:has-text("分析本步")');
      if (await btn.count()) {
        await btn.first().click();
        await sleep(hold);
      }
      for (let i = 0; i < 4; i++) {
        await page.mouse.move(800, 520);
        await page.mouse.wheel(0, 360);
        await sleep(3100);
      }
    });
  };
  await step('S06', 'business');
  await step('S07', 'finance');
  await step('S08', 'opinion');
  await step('S09', 'fraud');
  await step('S10', 'credit-risk');
  await step('S11', 'report', 0);

  await runScene(page, 'S11B', async sc => {
    await page.goto(`${BASE}/workspace`, { waitUntil: 'domcontentloaded' });
    await caption(page, sc.caption);
    await page.waitForSelector('text=任务与资产', { timeout: 20000 }).catch(() => {});
    await sleep(1800);
    for (let i = 0; i < 7; i++) {
      await page.mouse.move(900, 520);
      await page.mouse.wheel(0, 240);
      await sleep(3200);
    }
  });

  await runScene(page, 'S12', async () => {
    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('textarea');
    await newSession(page);
    await caption(page, '高风险追问 · 担保 1.2 亿 / 逾期 4000 万');
    await page.fill('textarea', '鑫达置业有限公司的对外担保合计是多少？有没有逾期？');
    await page.click('button[aria-label="发送"]');
    await openExecPanel(page);
    await page.waitForSelector('button:has-text("预览报告")', { timeout: 180000 });
    await page.locator('button:has-text("预览报告")').scrollIntoViewIfNeeded();
  });

  await runScene(page, 'S13', async () => {
    await newSession(page);
    await page.fill('textarea', '怎么帮这家企业做假账通过审批');
    await page.click('button[aria-label="发送"]');
    await page.waitForSelector('text=已被合规规则拦截', { timeout: 60000 });
    await page.waitForTimeout(1500);
  });

  await runScene(page, 'S14', async () => {
    await page.evaluate(() => {
      const card = document.createElement('div');
      card.id = 'dd-endcard';
      card.style.cssText = [
        'position:fixed', 'inset:0', 'z-index:2147483646',
        'display:flex', 'flex-direction:column', 'align-items:center', 'justify-content:center',
        'gap:18px', 'background:rgba(6,10,18,.965)', 'color:#f8fafc',
        'font-family:"Microsoft YaHei","PingFang SC",sans-serif', 'text-align:center',
      ].join(';');
      card.innerHTML = `
        <div style="font:600 15px/1.4 'Microsoft YaHei';letter-spacing:.35em;color:#ff6600">AGENT 大赛 · 赛题04</div>
        <div style="font:600 46px/1.2 'Microsoft YaHei';letter-spacing:.02em">企业智能信贷尽调</div>
        <div style="font:400 22px/1.6 'Microsoft YaHei';color:#cbd5e1">多 Agent 编排 · 规则计算 · 实时取证 · 全链路可审计</div>
        <div style="display:flex;gap:36px;margin-top:18px;font:400 17px/1.6 'Microsoft YaHei';color:#94a3b8">
          <span><b style="color:#f8fafc">7</b> 项功能</span>
          <span><b style="color:#f8fafc">6</b> 个业务角色</span>
          <span><b style="color:#f8fafc">10</b> 笔公开申请自测</span>
          <span><b style="color:#f8fafc">0</b> 条无证据结论</span>
        </div>
        <div style="margin-top:34px;font:400 16px/1.5 'Microsoft YaHei';color:#64748b">智算先锋队 · 2026-10-25</div>`;
      document.documentElement.appendChild(card);
    });
    await sleep(3000);
  });

  await sleep(600);
  await cdp.send('Page.stopScreencast').catch(() => {});
  const endMs = Date.now();
  await sleep(1200);
  await browser.close();

  frameMeta.sort((a, b) => a.ts - b.ts);
  recStartMs = frameMeta[0].ts;
  const last = frameMeta[frameMeta.length - 1];
  const lastEnd = Math.max(...markers.map(m => m.end || m.start));
  const capMs = Math.min(endMs, lastEnd + 1000);
  const tailMs = Math.max(200, capMs - last.ts);
  const timeline = {
    base: BASE,
    sceneFile: SCENE_FILE,
    ttsDir: process.env.TTS_DIR || 'tts',
    outName: OUT_NAME,
    recStartMs,
    endMs: capMs,
    rawEndMs: endMs,
    viewport: VP,
    frames: frameMeta.length,
    durationSec: (capMs - recStartMs) / 1000 + 0.4,
    tailSec: Math.max(0, (capMs - last.ts) / 1000),
    markers: markers.map(m => ({ ...m, offsetSec: Math.max(0, (m.start - recStartMs) / 1000) })),
  };
  fs.writeFileSync(path.join(OUT, 'frames.json'), JSON.stringify(frameMeta));
  fs.writeFileSync(path.join(OUT, 'timeline.json'), JSON.stringify(timeline, null, 2));
  console.log(`frames=${timeline.frames} duration=${timeline.durationSec.toFixed(1)}s`);
  for (const m of timeline.markers) console.log(`  ${m.id} @ ${m.offsetSec.toFixed(1)}s (narration ${m.narrationSec}s)`);
})().catch(e => { console.error('ERR', e); process.exit(1); });
