/* Shared chat must work on the production report and map surfaces without a live query. */
const { test, expect } = require('@playwright/test');
const { installPublicFixtures, cleanState, waitForDashboard, waitForMap } = require('./public-fixtures');

const answer = {
  success: true,
  structured: {
    lead: 'Dallas ISD recorded $3.32 billion in all-funds spending in fiscal 2025.',
    lead_runs: [{ t: 'Dallas ISD recorded $3.32 billion in all-funds spending in fiscal 2025.' }],
    figures: { name: 'Dallas ISD', district_number: '057905', year: 2025, note: 'All funds.',
      cards: [{ label: 'Total spending', value: '$3.32 billion' }] },
    blocks: [{ type: 'table', head: ['Spending category', 'Dollars'], rows: [
      ['Classroom teaching', '$1,092,607,589'], ['Construction', '$766,316,261']
    ] }],
    sources: [{ name: 'TEA PEIMS actual finance', url: '/sources' }]
  }
};

async function prepared(page, url) {
  const audit = { errors: [], queries: [], blocked: [] };
  page.on('pageerror', error => audit.errors.push(error.message));
  await cleanState(page);
  await installPublicFixtures(page, { baseURL: process.env.TISD_BASE_URL, blockedRequests: audit.blocked });
  await page.route('**/query', route => {
    audit.queries.push(route.request().postDataJSON());
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(answer) });
  });
  await page.goto(url);
  if (url.startsWith('/?')) await waitForDashboard(page);
  else await waitForMap(page);
  return audit;
}

for (const [label, url] of [['report', '/?d=057905'], ['map', '/map?d=057905']]) {
  for (const width of [390, 1440]) {
    test(`${label} shared chat is sourced and cancelable at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ reducedMotion: 'reduce' });
      const audit = await prepared(page, url);
      const fab = page.locator('.ta-fab');
      await expect(fab).toBeVisible();
      await fab.click();
      const chat = page.locator('.ta-wrap');
      await expect(chat).toBeVisible();
      await chat.locator('.ta-row input').fill('Where does Dallas school money go?');
      await chat.getByRole('button', { name: 'Ask', exact: true }).click();
      await expect(chat.locator('.ta-context')).toContainText('Dallas ISD');
      await expect(chat.locator('.ta-context')).toContainText('2025');
      await expect(chat.locator('.ta-answer-source')).toContainText('TEA PEIMS');
      await expect(chat.locator('.ta-chart')).toBeVisible();
      await chat.locator('.ta-evidence summary').click();
      await expect(chat.locator('.ta-evidence table')).toBeVisible();
      expect(audit.queries).toHaveLength(1);
      expect(audit.queries[0].district_number).toBe('057905');
      await page.keyboard.press('Escape');
      await expect(chat).toBeHidden();
      await expect(fab).toBeFocused();
      expect(audit.errors).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
  }
}
