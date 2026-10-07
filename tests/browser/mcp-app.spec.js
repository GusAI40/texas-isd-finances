const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '../..');
const fixture = JSON.parse(fs.readFileSync(path.join(root, 'tests/fixtures/mcp_visual_payloads.json'), 'utf8'));
const app = fs.readFileSync(path.join(root, 'static/mcp-app.html'), 'utf8')
  .replace('/*__TXISD_VISUAL_COMPONENTS__*/', fs.readFileSync(path.join(root, 'static/visual-components.js'), 'utf8'))
  .replace('/*__TXISD_DESIGN_CSS__*/', fs.readFileSync(path.join(root, 'static/design.css'), 'utf8'));

async function embeddedFrame(page, viewport) {
  await page.setViewportSize(viewport);
  await page.setContent('<iframe title="report" srcdoc="' + app.replace(/&/g, '&amp;').replace(/"/g, '&quot;') + '"></iframe>');
  return page.frames().find(candidate => candidate !== page.mainFrame());
}
async function dispatch(frame, data, trusted = true) {
  await frame.evaluate(({ data, trusted }) => window.dispatchEvent(new MessageEvent('message', {
    source: trusted ? window.parent : window, data,
  })), { data, trusted });
}
async function initialize(frame, result = {}) {
  await dispatch(frame, { jsonrpc: '2.0', id: 1, result });
}
async function toolResult(frame, visual) {
  await dispatch(frame, {
    jsonrpc: '2.0', method: 'ui/notifications/tool-result',
    params: { structuredContent: { visual } },
  });
}

for (const viewport of [{ width: 1280, height: 950 }, { width: 390, height: 844 }]) {
  test('MCP app has a useful no-bridge state at ' + viewport.width + 'px', async ({ page }) => {
    const requests = [];
    page.on('request', request => requests.push(request.url()));
    const frame = await embeddedFrame(page, viewport);
    await expect(frame.locator('h1')).toHaveText('Texas ISD finance report');
    await expect(frame.locator('#website')).toHaveAttribute('href', 'https://txisd.dev/');
    await expect(frame.locator('body')).not.toHaveCSS('overflow-x', 'scroll');
    expect(requests.filter(url => !url.startsWith('about:'))).toEqual([]);
  });
}

for (const [name, visual] of Object.entries(fixture)) {
  test('renders the ' + name + ' tool result with grouped accessible figures', async ({ page }) => {
    const frame = await embeddedFrame(page, { width: 390, height: 844 });
    await initialize(frame);
    await toolResult(frame, visual);
    await expect(frame.locator('h2')).toBeVisible();
    await expect(frame.locator('table.visual-table')).toBeVisible();
    await expect(frame.locator('.mcp-bar-group')).toHaveCount(name === 'comparison' ? 3 : name === 'statewide' ? 2 : 1);
    await expect(frame.locator('.visual-metric-meta').first()).toContainText('2025');
    await expect(frame.locator('#status')).toHaveText('Public report data loaded.');
  });
}

test('handles initialize responses, repeated updates, errors, and spoofed messages', async ({ page }) => {
  const frame = await embeddedFrame(page, { width: 1280, height: 950 });
  await initialize(frame);
  await expect(frame.locator('#status')).toHaveText('Ready for a public report.');
  await toolResult(frame, fixture.district);
  await expect(frame.locator('h2')).toHaveText('District finance');
  await toolResult(frame, fixture.statewide);
  await expect(frame.locator('h2')).toHaveText('Statewide summary');
  await dispatch(frame, { jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: { structuredContent: { visual: fixture.district } } }, false);
  await expect(frame.locator('h2')).toHaveText('Statewide summary');
  const failed = await embeddedFrame(page, { width: 390, height: 844 });
  await dispatch(failed, { jsonrpc: '2.0', id: 1, error: { message: 'unsupported' } });
  await expect(failed.locator('#status')).toContainText('compatible host');
});
