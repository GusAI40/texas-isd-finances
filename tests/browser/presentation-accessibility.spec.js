/* Recorded public data and mocked answers: this suite makes no provider calls. */
const { test, expect } = require('@playwright/test');
const { installPublicFixtures, cleanState, waitForDashboard } = require('./public-fixtures');
const axePath = require.resolve('axe-core/axe.min.js');
const response = { success: true, structured: {
  lead: 'Dallas ISD recorded $3.32 billion in all-funds spending in fiscal 2025.',
  figures: { name: 'Dallas ISD', district_number: '057905', year: 2025, note: 'All funds.' },
  blocks: [{ type: 'table', head: ['Spending category', 'Dollars'], rows: [
    ['Classroom teaching', '$1,092,607,589'], ['Construction', '$766,316,261'],
    ['Debt payments', '$500,174,938'], ['Other spending, combined', '$960,109,927'] ] }],
  sources: [{ name: 'TEA PEIMS actual finance', url: '/sources' }],
  limitations: ['Historical records, not a live budget.']
} };

async function audit(page, scope = 'body') {
  await page.addScriptTag({ path: axePath });
  const issues = await page.evaluate(async selector => {
    const result = await axe.run({ include: [[selector]] }, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] }
    });
    return result.violations.map(v => ({ id: v.id, targets: v.nodes.map(n => n.target) }));
  }, scope);
  expect(issues).toEqual([]);
  const small = await page.locator(scope).evaluate(root => [...root.querySelectorAll('button,summary,input')]
    .filter(e => e.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }))
    .map(e => ({ text: e.textContent.trim(), width: e.getBoundingClientRect().width, height: e.getBoundingClientRect().height }))
    .filter(r => r.width < 43.9 || r.height < 43.9));
  expect(small).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

for (const [width, height] of [[320, 740], [390, 844], [430, 932], [1440, 900]]) {
  for (const theme of ['light', 'dark']) {
    test(`page and chat remain readable at ${width}px ${theme}`, async ({ page }) => {
      test.setTimeout(60000);
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await cleanState(page, theme);
      await installPublicFixtures(page);
      let unavailable = false;
      await page.route('**/query', r => r.fulfill({ status: unavailable ? 503 : 200,
        contentType: 'application/json', body: JSON.stringify(unavailable ? { detail: 'Unavailable' } : response) }));
      await page.goto('/');
      await expect(page.locator('#welcome-h')).toBeVisible();
      await audit(page);
      await page.setViewportSize({ width: Math.round(width / 2), height: Math.round(height / 2) });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.setViewportSize({ width, height });
      await page.locator('#ask-your-own').click();
      await audit(page, '.ta-wrap');
      await page.locator('.ta-row input').fill('Where does Dallas ISD school money go?');
      await page.locator('.ta-row button').click();
      await expect(page.locator('.ta-chart')).toBeVisible();
      await audit(page, '.ta-wrap');
      await page.locator('.ta-evidence>summary').click();
      await page.locator('.ta-support>summary').click();
      await audit(page, '.ta-wrap');
      unavailable = true;
      await page.locator('.ta-row input').fill('Please check that record again.');
      await page.locator('.ta-row button').click();
      await expect(page.locator('.ta-retry')).toBeVisible();
      await audit(page, '.ta-wrap');
      await page.keyboard.press('Escape');
      await page.goto('/?d=057905');
      await waitForDashboard(page);
      await audit(page);
      await page.setViewportSize({ width: Math.round(width / 2), height: Math.round(height / 2) });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
  }
}
