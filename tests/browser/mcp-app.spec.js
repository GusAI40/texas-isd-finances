const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '../..');
const fixtureDocument = JSON.parse(fs.readFileSync(path.join(root, 'tests/fixtures/mcp_visual_payloads.json'), 'utf8'));
const fixture = fixtureDocument.views;
const app = fs.readFileSync(path.join(root, 'static/mcp-app.html'), 'utf8')
  .replace('/*__TXISD_VISUAL_COMPONENTS__*/', fs.readFileSync(path.join(root, 'static/visual-components.js'), 'utf8'))
  .replace('/*__TXISD_DESIGN_CSS__*/', fs.readFileSync(path.join(root, 'static/design.css'), 'utf8'));

const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'mobile', width: 390, height: 844 },
];
const themes = ['light', 'dark'];
const expectations = {
  district: { title: 'District finance', groups: 1, context: 'Dallas ISD (057905)', values: ['17,788', '14,210', '3,578', '7,206'] },
  comparison: { title: 'District comparison', groups: 4, context: 'Dallas ISD (057905) compared with Houston ISD (101912)', values: ['14,210', '3,578', '79', '5.5', '14,147', '2,267', '77', '3.9'] },
  statewide: { title: 'Statewide summary', groups: 2, context: 'Texas statewide public school districts', values: ['13,859,452,749', '1,538'] },
};

function hostPage(options) {
  const config = JSON.stringify({ mode: options.mode || 'success', delay: options.delay || 0 });
  return `<!doctype html><html><head><style>html,body{margin:0}#widget{display:block;width:100vw;height:calc(100vh - 40px);border:0}</style></head><body>
    <button id="host-send" type="button">Send host message</button>
    <button id="host-spoof" type="button">Send sibling message</button>
    <iframe id="widget" name="widget" title="Texas ISD report" sandbox="allow-scripts" src="http://widget.test/app"></iframe>
    <iframe id="attacker" name="attacker" title="Sibling frame" src="http://host.test/attacker" hidden></iframe>
    <script>
      (() => {
        const config = ${config};
        const widget = document.querySelector('#widget');
        const attacker = document.querySelector('#attacker');
        window.bridgeLog = [];
        document.querySelector('#host-send').addEventListener('click', event => {
          widget.contentWindow.postMessage(JSON.parse(event.currentTarget.dataset.message), '*');
        });
        document.querySelector('#host-spoof').addEventListener('click', event => {
          attacker.contentWindow.postMessage({ command: 'spoof', message: JSON.parse(event.currentTarget.dataset.message) }, '*');
        });
        window.addEventListener('message', event => {
          if (event.source !== widget.contentWindow || !event.data || event.data.jsonrpc !== '2.0') return;
          window.bridgeLog.push({ sourceMatchesWidget: event.source === widget.contentWindow, origin: event.origin, data: event.data });
          if (event.data.method !== 'ui/initialize' || !Number.isInteger(event.data.id) || config.mode === 'none') return;
          const response = config.mode === 'error'
            ? { jsonrpc: '2.0', id: event.data.id, error: { code: -32601, message: 'Bridge unavailable' } }
            : { jsonrpc: '2.0', id: event.data.id, result: { protocolVersion: '2026-01-26', hostCapabilities: {} } };
          setTimeout(() => event.source.postMessage(response, '*'), config.delay);
        });
      })();
    <\/script>
  </body></html>`;
}

const attackerPage = `<!doctype html><script>
  window.addEventListener('message', event => {
    if (event.source !== parent || !event.data || event.data.command !== 'spoof') return;
    parent.document.querySelector('#widget').contentWindow.postMessage(event.data.message, '*');
  });
<\/script>`;

async function embeddedFrame(page, viewport, options = {}) {
  const requests = [];
  page.on('request', request => requests.push(request.url()));
  await page.setViewportSize(viewport);
  await page.route('http://host.test/', route => route.fulfill({ contentType: 'text/html; charset=utf-8', body: hostPage(options) }));
  await page.route('http://host.test/attacker', route => route.fulfill({ contentType: 'text/html; charset=utf-8', body: attackerPage }));
  await page.route('http://widget.test/app', route => route.fulfill({ contentType: 'text/html; charset=utf-8', body: app }));
  await page.goto('http://host.test/');
  const frame = page.frame({ name: 'widget' });
  const attacker = page.frame({ name: 'attacker' });
  if (!frame || !attacker) throw new Error('The host did not create both test frames.');
  await Promise.all([frame.waitForLoadState('load'), attacker.waitForLoadState('load')]);
  if (options.waitForReady !== false && (options.mode || 'success') === 'success') {
    await expect(frame.locator('#status')).toHaveText('Ready for a public report.');
  }
  return { frame, requests };
}

async function dispatch(page, data, spoofed = false) {
  const selector = spoofed ? '#host-spoof' : '#host-send';
  await page.locator(selector).evaluate((button, message) => { button.dataset.message = JSON.stringify(message); }, data);
  await page.locator(selector).click();
}

async function toolResult(page, visual, extra = {}) {
  await dispatch(page, {
    jsonrpc: '2.0', method: 'ui/notifications/tool-result',
    params: { ...extra, structuredContent: { visual } },
  });
}

function flattenedMetrics(visual) {
  return visual.view === 'comparison' ? visual.metrics.flatMap(row => row.values) : visual.metrics;
}

for (const viewport of viewports) {
  for (const theme of themes) {
    for (const [name, visual] of Object.entries(fixture)) {
      test(`renders exact ${name} data at ${viewport.name} in ${theme} theme`, async ({ page }) => {
        const { frame, requests } = await embeddedFrame(page, viewport);
        await frame.evaluate(selected => { document.documentElement.dataset.theme = selected; }, theme);
        await toolResult(page, visual);

        const expected = expectations[name];
        await expect(frame.locator('h2')).toHaveText(expected.title);
        await expect(frame.locator('.mcp-context')).toHaveText(expected.context);
        await expect(frame.locator('.mcp-bar-group')).toHaveCount(expected.groups);
        if (name === 'statewide') {
          await expect(frame.locator('.mcp-metric-card')).toHaveCount(2);
          await expect(frame.locator('.mcp-bar-track')).toHaveCount(0);
        }
        await expect(frame.locator('table.visual-table tbody tr')).toHaveCount(flattenedMetrics(visual).length);
        expect(await frame.locator('table.visual-table tbody td:nth-child(2)').allTextContents()).toEqual(expected.values);
        expect(await frame.locator('table.visual-table tbody td:nth-child(3)').allTextContents()).toEqual(flattenedMetrics(visual).map(metric => metric.unit));
        await expect(frame.locator('.visual-metric-meta')).toHaveCount(flattenedMetrics(visual).length);
        for (const [index, metric] of flattenedMetrics(visual).entries()) {
          const metadata = frame.locator('.visual-metric-meta').nth(index);
          await expect(metadata).toContainText(`${metric.status} · ${metric.period} · ${metric.unit}`);
          await expect(metadata).toContainText(`${metric.population} · ${metric.denominator}`);
          await expect(metadata).toContainText(`Source: ${metric.source.label} (${metric.source.period})`);
        }
        const periods = [...new Set(flattenedMetrics(visual).map(metric => metric.period))];
        const statuses = [...new Set(flattenedMetrics(visual).map(metric => metric.status))];
        await expect(frame.locator('.mcp-frame')).toContainText(periods.join(' / '));
        await expect(frame.locator('.mcp-frame')).toContainText(statuses.join(' / '));
        if (name === 'comparison') {
          await expect(frame.locator('.mcp-frame')).toContainText('CompareMatching definition / period / unit / denominator');
          await expect(frame.locator('.mcp-frame')).toContainText('ModelNoncausal');
        } else {
          await expect(frame.locator('.mcp-frame')).toContainText('FrameOperating + annual debt service');
          await expect(frame.locator('.mcp-frame')).toContainText('ScopeExcludes construction');
          await expect(frame.locator('.mcp-frame')).toContainText('TotalNot all funds');
        }
        expect(await frame.locator('.mcp-limits details li').allTextContents()).toEqual(visual.limits);
        await expect(frame.locator('.mcp-limits details')).toHaveCount(1);
        for (const limit of visual.limits) await expect(frame.getByText(limit, { exact: true })).toHaveCount(1);
        await expect(frame.locator('#website')).toHaveAttribute('href', visual.websiteUrl);
        await expect(frame.locator('#status')).toHaveText('Public report data loaded.');
        await expect(frame.locator('html')).toHaveAttribute('data-theme', theme);
        expect(await frame.evaluate(() => ({ width: innerWidth, height: innerHeight }))).toEqual({
          width: viewport.width, height: viewport.height - 40,
        });
        const overflow = await frame.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow).toBeLessThanOrEqual(1);
        const colors = await frame.locator('body').evaluate(element => {
          const style = getComputedStyle(element);
          return { color: style.color, background: style.backgroundColor };
        });
        expect(colors.color).not.toBe(colors.background);
        await frame.locator('.mcp-table-scroll').focus();
        await expect(frame.locator('.mcp-table-scroll')).toBeFocused();
        await frame.locator('#website').focus();
        await expect(frame.locator('#website')).toBeFocused();
        await expect(frame.locator('.visual-metric-meta a').first()).toHaveAttribute('rel', 'noopener');

        if (name === 'comparison') {
          const moneyGroup = frame.locator('.mcp-bar-group').filter({ has: frame.locator('h3', { hasText: 'Operating spending per student · USD per student' }) });
          await expect(moneyGroup.locator('.mcp-bar-label')).toHaveCount(2);
          const widths = await moneyGroup.locator('.mcp-bar').evaluateAll(elements => elements.map(element => parseFloat(element.style.width)));
          expect(widths[0]).toBe(100);
          expect(widths[1]).toBeCloseTo(14147 / 14210 * 100, 4);
        }
        const captureId = `${name}-${viewport.name}-${theme}`;
        if (process.env.TXISD_CAPTURE_MCP_EVIDENCE === '1' && [
          'district-desktop-light', 'comparison-tablet-dark', 'statewide-mobile-light',
        ].includes(captureId)) {
          await frame.evaluate(() => scrollTo(0, 0));
          await page.locator('#widget').screenshot({
            path: path.join(root, 'docs/evidence/mcp', `e1-${captureId}-chromium.png`),
          });
        }
        expect(requests.filter(url => !['http://host.test/', 'http://host.test/attacker', 'http://widget.test/app'].includes(url))).toEqual([]);
      });
    }
  }
}

test('initializes through the parent bridge and announces readiness', async ({ page }) => {
  const { frame } = await embeddedFrame(page, viewports[0]);
  const log = await page.evaluate(() => window.bridgeLog);
  expect(log.every(entry => entry.sourceMatchesWidget)).toBe(true);
  expect(log[0].data).toEqual({
    jsonrpc: '2.0', id: 1, method: 'ui/initialize',
    params: {
      appInfo: { name: 'Texas ISD Finance Report', version: '1.0.0' },
      appCapabilities: {}, protocolVersion: '2026-01-26',
    },
  });
  expect(log.some(entry => entry.data.method === 'ui/notifications/initialized')).toBe(true);
  await expect(frame.locator('#status')).toHaveText('Ready for a public report.');
});

test('waits for a delayed initialize response', async ({ page }) => {
  const started = Date.now();
  const { frame } = await embeddedFrame(page, viewports[1], { delay: 1000, waitForReady: false });
  await expect(frame.locator('#status')).toHaveText('Waiting for public report data.');
  await expect(frame.locator('#status')).toHaveText('Ready for a public report.');
  expect(Date.now() - started).toBeGreaterThanOrEqual(900);
});

test('shows useful initialize-error and timeout states', async ({ page }) => {
  const { frame } = await embeddedFrame(page, viewports[2], { mode: 'error', waitForReady: false });
  await expect(frame.locator('#status')).toContainText('compatible host');
  await page.goto('about:blank');
  const second = await embeddedFrame(page, viewports[2], { mode: 'none', waitForReady: false });
  await expect(second.frame.locator('#status')).toContainText('compatible host', { timeout: 9000 });
});

test('shows a useful state when loaded without a parent bridge', async ({ page }) => {
  await page.route('http://widget.test/app', route => route.fulfill({ contentType: 'text/html; charset=utf-8', body: app }));
  await page.goto('http://widget.test/app');
  await expect(page.locator('#status')).toContainText('compatible host');
  await expect(page.locator('#website')).toHaveAttribute('href', 'https://txisd.dev/');
});

test('accepts repeated parent updates and rejects a genuine sibling-frame spoof', async ({ page }) => {
  const { frame } = await embeddedFrame(page, viewports[0]);
  await toolResult(page, fixture.district);
  await expect(frame.locator('h2')).toHaveText('District finance');
  await dispatch(page, {
    jsonrpc: '2.0', method: 'ui/notifications/tool-result',
    params: { structuredContent: { visual: fixture.statewide } },
  }, true);
  await page.waitForTimeout(100);
  await expect(frame.locator('h2')).toHaveText('District finance');
  await expect(frame.locator('table.visual-table tbody tr')).toHaveCount(4);
  await toolResult(page, fixture.statewide);
  await expect(frame.locator('h2')).toHaveText('Statewide summary');
  await toolResult(page, fixture.comparison);
  await expect(frame.locator('h2')).toHaveText('District comparison');
  await expect(frame.locator('table.visual-table tbody tr')).toHaveCount(8);
  await expect(frame.locator('h2')).toHaveCount(1);
  await expect(frame.locator('table.visual-table')).toHaveCount(1);
});

test('clears stale visuals for tool errors, absent visuals, and malformed visuals', async ({ page }) => {
  const { frame } = await embeddedFrame(page, viewports[1]);
  await toolResult(page, fixture.district);
  await expect(frame.locator('h2')).toHaveText('District finance');
  await toolResult(page, null, { isError: true });
  await expect(frame.locator('#report')).toBeEmpty();
  await expect(frame.locator('#status')).toContainText('tool error');
  await expect(frame.locator('#website')).toHaveAttribute('href', 'https://txisd.dev/');
  await toolResult(page, undefined);
  await expect(frame.locator('#report')).toBeEmpty();
  await expect(frame.locator('#status')).toContainText('visual report was not supplied');
  await toolResult(page, { schemaVersion: 1, view: 'district', metrics: 'not-an-array' });
  await expect(frame.locator('#report')).toBeEmpty();
  await expect(frame.locator('#status')).toContainText('visual report was not supplied');
});

test('shows the sourced-text fallback for an ambiguous district input request', async ({ page }) => {
  const { frame } = await embeddedFrame(page, viewports[1]);
  await dispatch(page, {
    jsonrpc: '2.0', method: 'ui/notifications/tool-result',
    params: { resultType: 'input_required', inputRequests: [{ id: 'district_number' }] },
  });
  await expect(frame.locator('#report')).toBeEmpty();
  await expect(frame.locator('#status')).toContainText('visual report was not supplied');
  const log = await page.evaluate(() => window.bridgeLog);
  expect(log.some(entry => entry.data.method === 'tools/call')).toBe(false);
});

test('rejects malformed, stale, and unsolicited response envelopes', async ({ page }) => {
  const { frame } = await embeddedFrame(page, viewports[2]);
  await dispatch(page, { jsonrpc: '2.0', id: 999, result: {} });
  await dispatch(page, { jsonrpc: '2.0', id: 1, method: 'ui/initialize', params: {} });
  await dispatch(page, { jsonrpc: '2.0', id: 1, result: {}, error: { message: 'ambiguous' } });
  await expect(frame.locator('#status')).toHaveText('Ready for a public report.');
  await expect(frame.locator('#report')).toBeEmpty();
});

test('keeps unsafe payload URLs inert', async ({ page }) => {
  const { frame } = await embeddedFrame(page, viewports[2]);
  const visual = JSON.parse(JSON.stringify(fixture.district));
  visual.websiteUrl = 'javascript:alert(1)';
  visual.metrics[0].source.url = 'javascript:alert(2)';
  await toolResult(page, visual);
  await expect(frame.locator('#website')).toHaveAttribute('href', 'https://txisd.dev/');
  await expect(frame.locator('.visual-metric-meta').first().locator('a')).toHaveCount(0);
});

test('renders synthetic negative, zero, missing, and mixed-period comparison edges without mixing scales', async ({ page }) => {
  const { frame } = await embeddedFrame(page, viewports[2]);
  const visual = JSON.parse(JSON.stringify(fixture.comparison));
  const dallasPoints = { ...visual.metrics[0].values.find(metric => metric.id === 'points_vs_predicted'), value: -2, period: '2025' };
  const houstonPoints = { ...visual.metrics[1].values.find(metric => metric.id === 'points_vs_predicted'), value: null, period: '2024' };
  const zeroPoints = { ...dallasPoints, value: 0, label: 'Points vs predicted' };
  visual.metrics = [
    { district_number: '057905', district_name: 'Dallas ISD', values: [dallasPoints] },
    { district_number: '101912', district_name: 'Houston ISD', values: [houstonPoints] },
    { district_number: '000000', district_name: 'Synthetic zero edge', values: [zeroPoints] },
  ];
  await toolResult(page, visual);

  await expect(frame.locator('.mcp-bar-group')).toHaveCount(2);
  const period2025 = frame.locator('.mcp-bar-group').filter({ has: frame.locator('h3', { hasText: '2025' }) });
  await expect(period2025.locator('.mcp-bar-label')).toHaveCount(2);
  await expect(period2025.locator('.mcp-bar[data-direction="negative"]')).toHaveCount(1);
  await expect(period2025.locator('.mcp-bar[data-direction="zero"]')).toHaveCount(1);
  await expect(period2025.locator('.mcp-bar-zero')).toHaveCount(2);
  const period2024 = frame.locator('.mcp-bar-group').filter({ has: frame.locator('h3', { hasText: '2024' }) });
  await expect(period2024.locator('.mcp-metric-card')).toHaveCount(1);
  await expect(period2024.locator('.mcp-bar')).toHaveCount(0);
  await expect(period2024.locator('.mcp-bar-zero')).toHaveCount(0);
  expect(await frame.locator('table.visual-table tbody td:nth-child(2)').allTextContents()).toEqual(['-2', 'Not available', '0']);
});
