/* Browser evidence collector. It measures rendered content, never CSS classes. */
import fs from 'node:fs';
import path from 'node:path';
import { chromium, firefox } from '@playwright/test';

const phase = process.argv[2];
if (!['baseline', 'prototype', 'final'].includes(phase)) throw new Error('phase required');
const baseURL = phase === 'baseline' ? (process.env.TISD_BASELINE_URL || 'http://127.0.0.1:8766') : (process.env.TISD_BASE_URL || 'http://127.0.0.1:8765');
const root = path.resolve('../..'), evidence = path.join(root, 'docs/evidence/visual'), output = path.join(evidence, 'measurements.json');
const { states } = JSON.parse(fs.readFileSync('fixtures/public-states.json', 'utf8'));
const manifest = JSON.parse(fs.readFileSync('visual-regions.json', 'utf8')).regions;
const endpointFixture = JSON.parse(fs.readFileSync('fixtures/public-endpoints.json', 'utf8'));
const viewports = [{ width: 1440, height: 900 }, { width: 768, height: 1024 }, { width: 390, height: 844 }];
const onlyStates = process.env.TISD_CAPTURE_STATES ? new Set(process.env.TISD_CAPTURE_STATES.split(',')) : null;

async function classify(page) {
  return page.evaluate(manifest => {
    const visible = el => { const s = getComputedStyle(el), b = el.getBoundingClientRect(); return !el.hidden && s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity) > 0 && b.width > 0 && b.height > 0; };
    const pageRect = b => ({ left: b.left + scrollX, top: b.top + scrollY, right: b.right + scrollX, bottom: b.bottom + scrollY });
    const rangeRect = el => { const r = document.createRange(); r.selectNodeContents(el); const bs = [...r.getClientRects()].filter(b => b.width && b.height); return bs.length ? pageRect({ left: Math.min(...bs.map(b => b.left)), top: Math.min(...bs.map(b => b.top)), right: Math.max(...bs.map(b => b.right)), bottom: Math.max(...bs.map(b => b.bottom)) }) : null; };
    const text = el => (el.textContent || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().slice(0, 180);
    const regions = [], exclusions = [];
    const classifiedElements = new Set();
    const identity = el => {
      if (el.id) return `#${el.id}`;
      const bits = [];
      for (let node = el; node && node !== document.body; node = node.parentElement) {
        const index = [...node.parentElement.children].indexOf(node) + 1;
        bits.unshift(`${node.tagName.toLowerCase()}:nth-child(${index})`);
      }
      return `body>${bits.join('>')}`;
    };
    function add(el, kind, reason, tight = false) {
      if (!visible(el)) return;
      const box = tight ? rangeRect(el) : pageRect(el.getBoundingClientRect()); if (!box) return;
      classifiedElements.add(el);
      const item = { selector: identity(el), kind, ...box, visible: true, text: text(el) };
      if (kind === 'excluded') { item.reason = reason; exclusions.push(item); } else regions.push(item);
    }
    // The external manifest is the stable reviewer-facing rubric.  Runtime
    // discovery supplements it; a selector which disappears is evidence, not
    // permission to omit that region.
    for (const rule of manifest) {
      const nodes = document.querySelectorAll(rule.selector);
      if (!nodes.length) exclusions.push({ selector: rule.selector, kind: 'excluded', reason: `manifest selector missing: ${rule.reason || 'classification required'}` });
      nodes.forEach(el => add(el, rule.kind, rule.reason || 'manifest classification', rule.kind !== 'visual'));
    }
    document.querySelectorAll('#masthead,header,nav,.tabs,.m-tabs,input,button,.results,footer,#ai-note,details,table,.tbl').forEach(el => add(el, 'excluded', 'navigation, control, disclosure, or alternate table'));
    document.querySelectorAll('svg:not([aria-hidden="true"]),canvas,[role="img"]').forEach(el => {
      if (el.matches('.pennies') && !el.querySelector('i,span,svg')) return;
      add(el, 'visual', 'rendered data mark');
    });
    document.querySelectorAll('figure figcaption,.kpi-grid .num,.kpi-grid .big,.metric-value,.hero-kpis>span,.metric-meta>span').forEach(el => add(el, 'visual', 'necessary visual label, unit, period, source, or status', true));
    document.querySelectorAll('#welcome .pipeline .pipe-col').forEach(el => add(el, 'visual', 'data-source flow diagram', true));
    document.querySelectorAll('main p,#welcome p,#picker-section p,#dash p,.note,.ask').forEach(el => {
      if (el.closest('details,table,nav,header,footer') || !text(el)) return;
      add(el, 'prose', 'standalone narrative', true);
    });
    const leaves = [...document.querySelectorAll('main *')].filter(el => visible(el) && el.children.length === 0 && text(el));
    const inventory = leaves.map(el => ({ tag: el.tagName, id: el.id || null, selector: identity(el), text: text(el) }));
    const unclassified = leaves.filter(el => ![...classifiedElements].some(owner => owner === el || owner.contains(el))).map(el => ({ tag: el.tagName, id: el.id || null, selector: identity(el), text: text(el) }));
    return { regions, exclusions, inventory, unclassified, scrollY };
  }, manifest);
}
async function annotate(page, outputPath, regions, fullPage = true) {
  await page.evaluate(regions => {
    const o = document.createElement('div'); o.id = 'visual-measurement-overlay'; o.style.cssText = 'position:absolute;inset:0;z-index:2147483647;pointer-events:none';
    for (const r of regions) { const e = document.createElement('i'); e.style.cssText = `position:absolute;left:${r.left}px;top:${r.top}px;width:${r.right-r.left}px;height:${r.bottom-r.top}px;border:2px solid ${r.kind === 'visual' ? '#0067ff' : '#d60000'};box-sizing:border-box`; o.appendChild(e); }
    document.body.appendChild(o);
  }, regions);
  await page.screenshot({ path: outputPath, fullPage, type: 'jpeg', quality: 88 });
  await page.locator('#visual-measurement-overlay').evaluate(el => el.remove());
}
async function installPublicFixtures(page) {
  const payload = endpointFixture.payloads;
  const districtKey = { '057905': 'dallas', '101912': 'houston', '091907': 'tioga', '003801': 'charter' };
  await page.route('**/stats', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(payload.stats) }));
  await page.route('**/district/*/summary', route => {
    const number = route.request().url().match(/district\/(\d{6})\/summary/)?.[1];
    const body = payload[`${districtKey[number]}_summary`];
    return body ? route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) }) : route.fulfill({ status: 503, body: '{"detail":"fixture unavailable"}' });
  });
  for (const suffix of ['peers', 'breakdown', 'spending-detail']) {
    await page.route(`**/district/*/${suffix}`, route => {
      const number = route.request().url().match(/district\/(\d{6})\//)?.[1];
      const key = `${districtKey[number]}_${suffix === 'spending-detail' ? 'detail' : suffix}`;
      const body = payload[key];
      return body ? route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) }) : route.fulfill({ status: 503, body: '{"detail":"fixture unavailable"}' });
    });
  }
  await page.route('**/anomalies?district_number=*&limit=50', route => {
    const number = route.request().url().match(/district_number=(\d{6})/)?.[1];
    const body = payload[`${districtKey[number]}_anomalies`];
    return body ? route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) }) : route.fulfill({ status: 503, body: '{"detail":"fixture unavailable"}' });
  });
}

async function activateScrollContent(page, viewportHeight) {
  const start = await page.evaluate(() => scrollY);
  const height = await page.evaluate(() => document.documentElement.scrollHeight);
  for (let y = start; y < height; y += Math.max(320, Math.floor(viewportHeight * .72))) {
    await page.evaluate(next => scrollTo(0, next), y);
    await page.waitForTimeout(18);
  }
  await page.evaluate(y => scrollTo(0, y), start);
  await page.waitForTimeout(80);
}

const report = fs.existsSync(output) ? JSON.parse(fs.readFileSync(output, 'utf8')) : { phases: {} };
const cases = []; fs.mkdirSync(evidence, { recursive: true });
for (const [browserName, type] of [['chromium', chromium], ['firefox', firefox]]) {
  const browser = await type.launch();
  for (const viewport of viewports) for (const theme of ['light', 'dark']) for (const [stateName, state] of Object.entries(states)) {
    if (onlyStates && !onlyStates.has(stateName)) continue;
    if (stateName === 'missing') continue; // synthetic edge fixture: not a public report.
    const page = await browser.newPage({ viewport, colorScheme: theme });
    if (stateName !== 'unavailable') await installPublicFixtures(page);
    const target = new URL(phase === 'prototype' ? '/design/public-portal-prototype.html' : state.route, baseURL).href;
    // Some deliberately-unavailable fixture routes keep a failed fetch pending.
    // DOM readiness plus a bounded settle preserves evidence without turning a
    // 72-cell matrix into a network-idle timeout test.
    await page.goto(target, { waitUntil: 'domcontentloaded', timeout: 15000 }); await page.waitForTimeout(700);
    const key = `${phase}-${browserName}-${stateName}-${viewport.width}x${viewport.height}-${theme}`;
    const screenshot = `docs/evidence/visual/${key}.jpg`, annotation = `docs/evidence/visual/${key}-annotated.jpg`, initialScreenshot = `docs/evidence/visual/${key}-initial.jpg`, initialAnnotation = `docs/evidence/visual/${key}-initial-annotated.jpg`;
    await page.screenshot({ path: path.join(root, initialScreenshot), fullPage: false, type: 'jpeg', quality: 88 });
    const initialMeasured = await classify(page);
    const viewTop = initialMeasured.scrollY, viewBottom = viewTop + viewport.height;
    const initialRegions = initialMeasured.regions
      .map(r => ({ ...r, top: Math.max(r.top, viewTop), bottom: Math.min(r.bottom, viewBottom) }))
      .filter(r => r.top < viewBottom && r.bottom > r.top);
    await activateScrollContent(page, viewport.height);
    await page.screenshot({ path: path.join(root, screenshot), fullPage: true, type: 'jpeg', quality: 88 });
    const measured = await classify(page); await annotate(page, path.join(root, annotation), measured.regions);
    await annotate(page, path.join(root, initialAnnotation), initialRegions, false);
    cases.push({ id: key, phase, state: stateName, browser: browserName, browser_version: browser.version(), viewport, theme, url: target, screenshot, annotation, initial_screenshot: initialScreenshot, initial_annotation: initialAnnotation, status: 'measured', regions: measured.regions, initial_regions: initialRegions, exclusions: measured.exclusions, inventory: measured.inventory, unclassified: measured.unclassified, reviewed: false, review_note: 'Geometry is automated. Screenshot and semantic-classification review remains required.' });
    await page.close();
  }
  await browser.close();
}
const retainedCases = onlyStates && report.phases[phase]
  ? report.phases[phase].cases.filter(item => !onlyStates.has(item.state)) : [];
report.source_revision = process.env.TISD_REVISION || 'working-tree'; report.captured_at = new Date().toISOString(); report.collector = 'tests/browser/capture-visuals.mjs'; report.phases[phase] = { base_url: baseURL, cases: [...retainedCases, ...cases] };
fs.writeFileSync(output, JSON.stringify(report, null, 2) + '\n');
