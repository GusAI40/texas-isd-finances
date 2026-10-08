/* MCP widget visual evidence: native sandboxed iframe geometry, never a site-page proxy. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import zlib from 'node:zlib';
import { chromium, firefox } from '@playwright/test';
import { classifyPage } from './measurement-core.mjs';

const root = path.resolve('../..');
const evidence = path.join(root, 'docs/evidence/mcp');
const fixtureSource = fs.readFileSync(path.join(root, 'tests/fixtures/mcp_visual_payloads.json'));
const widgetSource = fs.readFileSync(path.join(root, 'static/mcp-app.html'));
const helperSource = fs.readFileSync(path.join(root, 'static/visual-components.js'));
const designSource = fs.readFileSync(path.join(root, 'static/design.css'));
const manifestSource = fs.readFileSync('visual-regions-mcp.json');
const collectorSource = fs.readFileSync(new URL(import.meta.url));
const fixtures = JSON.parse(fixtureSource.toString('utf8'));
const manifest = JSON.parse(fs.readFileSync('visual-regions-mcp.json', 'utf8'));
const widget = widgetSource.toString('utf8')
  .replace('/*__TXISD_VISUAL_COMPONENTS__*/', helperSource.toString('utf8'))
  .replace('/*__TXISD_DESIGN_CSS__*/', designSource.toString('utf8'));
const viewports = [{ width: 1440, height: 900 }, { width: 768, height: 1024 }, { width: 390, height: 844 }];
const sha256 = value => crypto.createHash('sha256').update(value).digest('hex');
const normalizedSha256 = value => sha256(Buffer.from(value.toString('utf8').replace(/\r\n?/g, '\n'), 'utf8'));
const crop = (regions, scrollX, scrollY, viewport) => regions.map(region => ({ ...region,
  left: Math.max(region.left, scrollX), top: Math.max(region.top, scrollY),
  right: Math.min(region.right, scrollX + viewport.width), bottom: Math.min(region.bottom, scrollY + viewport.height),
})).filter(region => region.right > region.left && region.bottom > region.top);

function hostPage() {
  return `<!doctype html><meta charset="utf-8"><style>html,body{margin:0}#host-toolbar{height:40px}#widget{display:block;border:0;width:100vw;height:calc(100vh - 40px)}</style><button id="host-toolbar">Host toolbar</button><iframe id="widget" name="widget" sandbox="allow-scripts" src="http://widget.test/app"></iframe><script>addEventListener('message',e=>{const w=document.querySelector('#widget');if(e.source!==w.contentWindow||!e.data)return;if(e.data.method==='ui/initialize')e.source.postMessage({jsonrpc:'2.0',id:e.data.id,result:{protocolVersion:'2026-01-26',hostCapabilities:{}}},'*');else if(e.data.method==='test/tool-result')w.contentWindow.postMessage(e.data.result,'*')})<\/script>`;
}
async function annotate(frame, regions) {
  await frame.evaluate(items => {
    const overlay = document.createElement('div'); overlay.id = 'measurement-overlay';
    overlay.style.cssText = 'position:absolute;inset:0;z-index:2147483647;pointer-events:none';
    for (const region of items) { const mark = document.createElement('i'); const color = region.kind === 'visual' ? '#0067ff' : '#d60000'; mark.style.cssText = `position:absolute;left:${region.left}px;top:${region.top}px;width:${region.right-region.left}px;height:${region.bottom-region.top}px;border:1px solid ${color};background:${color}18;box-sizing:border-box`; overlay.append(mark); }
    document.body.append(overlay);
  }, regions);
}
async function clearAnnotation(frame) { await frame.locator('#measurement-overlay').evaluate(el => el.remove()); }
async function settled(frame, visual) {
  await frame.waitForSelector('#status');
  await frame.waitForFunction(() => document.querySelector('#status')?.textContent === 'Ready for a public report.');
  await frame.evaluate(data => parent.postMessage({ method: 'test/tool-result', result: { jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: { structuredContent: { visual: data } } } }, '*'), visual);
  await frame.waitForFunction(() => document.querySelector('#status')?.textContent === 'Public report data loaded.');
  await frame.evaluate(async () => { if (document.fonts?.ready) await document.fonts.ready; await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); });
}

fs.mkdirSync(evidence, { recursive: true });
const cases = [];
for (const [browserName, engine] of [['chromium', chromium], ['firefox', firefox]]) {
  const browser = await engine.launch();
  for (const viewport of viewports) for (const theme of ['light', 'dark']) for (const [state, visual] of Object.entries(fixtures.views)) {
    const page = await browser.newPage({ viewport, colorScheme: theme, reducedMotion: 'reduce' });
    const pageErrors = [], requests = [];
    page.on('pageerror', error => pageErrors.push(error.message)); page.on('request', request => requests.push(request.url()));
    await page.route('http://host.test/', route => route.fulfill({ contentType: 'text/html', body: hostPage() }));
    await page.route('http://widget.test/app', route => route.fulfill({ contentType: 'text/html', body: widget }));
    await page.goto('http://host.test/');
    const frame = page.frame({ name: 'widget' }); if (!frame) throw new Error('missing sandboxed widget frame');
    await settled(frame, visual); await frame.evaluate(value => document.documentElement.dataset.theme = value, theme);
    const frameViewport = await frame.evaluate(() => ({ width: innerWidth, height: innerHeight }));
    const fullDocument = await frame.evaluate(() => ({ width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight }));
    const id = `mcp-${browserName}-${state}-${viewport.width}x${viewport.height}-${theme}`;
    const files = { screenshot: `docs/evidence/mcp/${id}.png`, annotation: `docs/evidence/mcp/${id}-annotated.png`, initial_screenshot: `docs/evidence/mcp/${id}-initial.png`, initial_annotation: `docs/evidence/mcp/${id}-initial-annotated.png` };
    const hostFrame = page.locator('#widget');
    const initial = await classifyPage(frame, manifest); const initialRegions = crop(initial.regions, initial.scrollX, initial.scrollY, frameViewport);
    await hostFrame.screenshot({ path: path.join(root, files.initial_screenshot) });
    await annotate(frame, initialRegions); await hostFrame.screenshot({ path: path.join(root, files.initial_annotation) }); await clearAnnotation(frame);
    await frame.locator('html').screenshot({ path: path.join(root, files.screenshot), fullPage: true });
    const measured = await classifyPage(frame, manifest);
    await annotate(frame, measured.regions); await frame.locator('html').screenshot({ path: path.join(root, files.annotation), fullPage: true }); await clearAnnotation(frame);
    cases.push({ id, state, status: 'measured', browser: browserName, browser_version: browser.version(), viewport, widget_viewport: frameViewport, full_document: fullDocument, host_toolbar_height: 40, theme, reduced_motion: true, zoom: 1, ...files, regions: measured.regions, initial_regions: initialRegions, inventory: measured.inventory, unclassified: measured.unclassified, graphics: measured.graphics, manifest_errors: measured.manifest_errors, page_errors: pageErrors, renderer_warnings: [], blocked_external_requests: requests.filter(url => !['http://host.test/', 'http://widget.test/app'].includes(url)), reviewed: false, review_note: 'Geometry is automated; independent visual review remains pending.' });
    await page.close();
  }
  await browser.close();
}
const report = { source_revision: process.env.TISD_REVISION || 'working-tree', captured_at: new Date().toISOString(), collector: 'tests/browser/capture-mcp-visuals.mjs', rubric_version: manifest.rubric_version, sources: {
  fixture: { path: 'tests/fixtures/mcp_visual_payloads.json', sha256: sha256(fixtureSource), normalized_utf8_lf_sha256: normalizedSha256(fixtureSource) },
  widget: { path: 'static/mcp-app.html', sha256: sha256(widgetSource), normalized_utf8_lf_sha256: normalizedSha256(widgetSource), composed_sha256: sha256(widget), composed_normalized_utf8_lf_sha256: normalizedSha256(Buffer.from(widget, 'utf8')) },
  helper: { path: 'static/visual-components.js', sha256: sha256(helperSource), normalized_utf8_lf_sha256: normalizedSha256(helperSource) },
  design: { path: 'static/design.css', sha256: sha256(designSource), normalized_utf8_lf_sha256: normalizedSha256(designSource) },
  manifest: { path: 'tests/browser/visual-regions-mcp.json', sha256: sha256(manifestSource), normalized_utf8_lf_sha256: normalizedSha256(manifestSource) },
  collector: { path: 'tests/browser/capture-mcp-visuals.mjs', sha256: sha256(collectorSource), normalized_utf8_lf_sha256: normalizedSha256(collectorSource) },
}, widget: { host: 'sandboxed synthetic MCP parent; actual ChatGPT host rendering remains unverified' }, cases };
fs.writeFileSync(path.join(evidence, 'visual-measurements.json.gz'), zlib.gzipSync(JSON.stringify(report)));
console.log(JSON.stringify({ cases: cases.length, output: 'docs/evidence/mcp/visual-measurements.json.gz' }));
