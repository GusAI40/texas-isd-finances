const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const zlib = require('node:zlib');
const equityArtifact = require('../../static/equity_data.json');
const outcomesArtifact = require('../../static/outcomes_data.json');
const economicsArtifact = require('../../static/economics_data.json');
const nationalArtifact = require('../../static/national_data.json');
const districtGeo = require('../../static/district_geo.json');
const argyleEvidence = require('../../docs/evidence/mcp/framing-argyle-public.json');
const { fixture, installPublicFixtures, cleanState, waitForDashboard, waitForMap } = require('./public-fixtures');

const viewports = [
  { width: 1440, height: 900, name: 'desktop' },
  { width: 768, height: 1024, name: 'tablet' },
  { width: 390, height: 844, name: 'mobile' },
];
const themes = ['light', 'dark'];
const expectedSpend = fixture.payloads.dallas_summary.at(-1).spend_per_student;

async function fixturePage(page, { theme = 'light', unavailable = false, geoPatches = null, geoDelayMs = 0 } = {}) {
  const blocked = [], requests = [], errors = [], renderErrors = [], assetErrors = [], serverErrors = [];
  const baseOrigin = new URL(test.info().project.use.baseURL).origin;
  const ownedAsset = request => new URL(request.url()).origin === baseOrigin
    && ['document', 'stylesheet', 'script', 'image', 'font'].includes(request.resourceType());
  page.on('pageerror', error => errors.push(error.message));
  page.on('requestfailed', request => {
    if (ownedAsset(request)) assetErrors.push(`${request.resourceType()} ${request.url()} ${request.failure()?.errorText || 'failed'}`);
  });
  page.on('response', response => {
    if (response.status() >= 500 && new URL(response.url()).origin === baseOrigin) {
      serverErrors.push(`${response.request().method()} ${new URL(response.url()).pathname}${new URL(response.url()).search} HTTP ${response.status()}`);
    }
    if (response.status() >= 400 && ownedAsset(response.request())) {
      assetErrors.push(`${response.request().resourceType()} ${response.url()} HTTP ${response.status()}`);
    }
  });
  page.on('console', message => {
    if (['warning', 'error'].includes(message.type()) &&
        /section .*could not render|citations could not render|ReferenceError|TypeError|map data failed|chart image export failed/i.test(message.text())) {
      renderErrors.push(message.text());
    }
  });
  await cleanState(page, theme);
  await installPublicFixtures(page, {
    baseURL: test.info().project.use.baseURL,
    unavailable,
    blockedRequests: blocked,
    requests,
    geoPatches,
    geoDelayMs,
  });
  return { blocked, requests, errors, renderErrors, assetErrors, serverErrors, unavailable };
}

function assertPassiveIsolation(audit) {
  expect(audit.errors, 'uncaught page errors').toEqual([]);
  expect(audit.renderErrors, 'renderer errors').toEqual([]);
  expect(audit.assetErrors, 'failed same-origin documents, styles, scripts, images, or fonts').toEqual([]);
  if (!audit.unavailable) expect(audit.serverErrors, 'unexpected same-origin server errors').toEqual([]);
  expect(audit.blocked,
    'passive public tasks must not attempt cross-origin, mutation, telemetry, private, or paid requests').toEqual([]);
}

function parseCsv(text) {
  const rows = [];
  let row = [], cell = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted && ch === '"' && text[i + 1] === '"') { cell += '"'; i++; }
    else if (ch === '"') quoted = !quoted;
    else if (ch === ',' && !quoted) { row.push(cell); cell = ''; }
    else if ((ch === '\n' || ch === '\r') && !quoted) {
      if (ch === '\r' && text[i + 1] === '\n') i++;
      row.push(cell); cell = '';
      if (row.some(value => value !== '')) rows.push(row);
      row = [];
    } else cell += ch;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

function decodePng(buffer) {
  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  if (!buffer.subarray(0, 8).equals(signature)) throw new Error('not a PNG');
  let offset = 8, width, height, bitDepth, colorType;
  const idat = [];
  while (offset < buffer.length) {
    const length = buffer.readUInt32BE(offset); const type = buffer.toString('ascii', offset + 4, offset + 8);
    const data = buffer.subarray(offset + 8, offset + 8 + length);
    if (type === 'IHDR') {
      width = data.readUInt32BE(0); height = data.readUInt32BE(4);
      bitDepth = data[8]; colorType = data[9];
    } else if (type === 'IDAT') idat.push(data);
    else if (type === 'IEND') break;
    offset += length + 12;
  }
  if (bitDepth !== 8 || ![2, 6].includes(colorType)) throw new Error(`unsupported PNG type ${colorType}/${bitDepth}`);
  const channels = colorType === 6 ? 4 : 3;
  const stride = width * channels;
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const pixels = Buffer.alloc(stride * height);
  let src = 0;
  for (let y = 0; y < height; y++) {
    const filter = raw[src++];
    for (let x = 0; x < stride; x++) {
      const value = raw[src++];
      const left = x >= channels ? pixels[y * stride + x - channels] : 0;
      const up = y ? pixels[(y - 1) * stride + x] : 0;
      const upperLeft = y && x >= channels ? pixels[(y - 1) * stride + x - channels] : 0;
      let decoded = value;
      if (filter === 1) decoded = value + left;
      else if (filter === 2) decoded = value + up;
      else if (filter === 3) decoded = value + Math.floor((left + up) / 2);
      else if (filter === 4) {
        const p = left + up - upperLeft;
        const pa = Math.abs(p - left), pb = Math.abs(p - up), pc = Math.abs(p - upperLeft);
        decoded = value + (pa <= pb && pa <= pc ? left : pb <= pc ? up : upperLeft);
      } else if (filter !== 0) throw new Error(`unsupported PNG filter ${filter}`);
      pixels[y * stride + x] = decoded & 255;
    }
  }
  const background = pixels.subarray(0, channels).toString('hex');
  const colors = new Set(); let nonBackground = 0;
  for (let i = 0; i < pixels.length; i += channels) {
    const color = pixels.subarray(i, i + channels).toString('hex');
    colors.add(color);
    if (color !== background) nonBackground++;
  }
  return { width, height, colors: colors.size, nonBackground };
}

async function selectDallas(page) {
  await page.locator('#search').fill('Dallas');
  await page.locator('#searchbtn').click();
  await expect(page.locator('#results button')).toHaveCount(1);
  await page.locator('#results button', { hasText: '057905' }).click();
  await waitForDashboard(page);
  await expect(page).toHaveURL(/\?d=057905/);
  await expect(page.locator('#dname')).toContainText(/Dallas/i);
}

async function assertAmbiguousFinder(page) {
  await page.locator('#search').fill('Wylie');
  await page.locator('#searchbtn').click();
  await expect(page.locator('#results button')).toHaveCount(2);
  await expect(page.locator('#results')).toContainText('043914');
  await expect(page.locator('#results')).toContainText('221912');
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator('#dash')).toHaveClass(/hidden/);
}

async function assertReportSemantics(page, audit) {
  await expect(page.locator('#t-records')).toHaveText('20,587');
  await expect(page.locator('#dbwarn'),
    `normal fixture must remain healthy; server errors: ${JSON.stringify(audit.serverErrors)}`).toBeHidden();
  await expect(page.locator('#kpis .kpi')).not.toHaveCount(0);
  await expect(page.locator('#live-finance-status')).toBeHidden();
  await expect(page.locator('#kpis')).not.toBeEmpty();
  for (const selector of ['#outcomes-section', '#econ-section', '#equity-section', '#bond-section']) {
    await expect(page.locator(selector)).toBeVisible();
    await expect(page.locator(selector)).not.toBeEmpty();
  }
  await expect(page.locator('#kpi-eyebrow')).toContainText(/(?:FY|Fiscal) 2025/i);
  await expect(page.locator('#outcomes-section > .metric-meta')).toContainText(`SY ${outcomesArtifact.meta.year}`);
  await expect(page.locator('#equity-section > .metric-meta')).toContainText(`SY ${equityArtifact.meta.year}`);
  await expect(page.locator('#econ-section > .metric-meta')).toContainText(`FY ${economicsArtifact.meta.year}`);
  await expect(page.locator('#econ-national')).toContainText(String(nationalArtifact.meta.fiscal_year));

  const trendDetails = page.locator('#trend-section details.tbl');
  if (!(await trendDetails.getAttribute('open'))) await trendDetails.locator('summary').click();
  await expect(page.locator('#trendtable')).toBeVisible();
  await expect(page.locator('#trendtable th')).not.toHaveCount(0);

  const econTableDetails = page.locator('#econ-a11y');
  if (!(await econTableDetails.getAttribute('open'))) await econTableDetails.locator('summary').click();
  await expect(page.locator('#econ-table')).toBeVisible();
  await expect(page.locator('#econ-table tbody tr')).not.toHaveCount(0);

  const bondTableDetails = page.locator('#bond-a11y');
  if (await bondTableDetails.isVisible()) {
    if (!(await bondTableDetails.getAttribute('open'))) await bondTableDetails.locator('summary').click();
    await expect(page.locator('#bond-table')).toBeVisible();
    await expect(page.locator('#bond-table th')).not.toHaveCount(0);
  }

  const sourceDisclosure = page.locator('#econ-section details.evidence-detail')
    .filter({ has: page.locator('summary', { hasText: 'Source, definitions and limits' }) });
  await expect(sourceDisclosure).toHaveCount(1);
  if (!(await sourceDisclosure.getAttribute('open'))) await sourceDisclosure.locator('summary').click();
  await expect(sourceDisclosure.locator('.ledger-detail-body')).toContainText(/Sources?:/i);

  await page.locator('#myhome').fill('500,000.00');
  await expect(page.locator('#myhome-out')).toContainText(/\$500,000.*100.*adopted rate/i);

  const citationDetails = page.locator('#methods-section details.tbl').filter({ has: page.locator('#citation-text') });
  if (!(await citationDetails.getAttribute('open'))) await citationDetails.locator('summary').click();
  await expect(page.locator('#citation-text')).toContainText(/Texas ISD Financial Resource Guide.*fiscal years 2009.2025/i);
  await page.locator('#btn-cite').click();
  await expect(page.locator('#btn-cite')).toHaveText(/Copied|Copy unavailable — citation selected/);
  if ((await page.locator('#btn-cite').textContent()).startsWith('Copy unavailable')) {
    expect(await page.evaluate(() => getSelection()?.toString())).toContain('Texas ISD Financial Resource Guide');
  }
}

async function assertSectionNavigation(page) {
  const buttons = page.locator('#sectionnav button');
  expect(await buttons.count()).toBeGreaterThan(10);
  for (const name of ['Overview', 'What it buys', 'What you pay', 'Bonds you voted on', 'Trends', 'Methods']) {
    const button = buttons.filter({ hasText: name }).first();
    if (!(await button.count())) continue;
    const target = await button.getAttribute('data-to');
    await button.click();
    await expect(page.locator(`#${target}`)).toBeVisible();
    await expect.poll(() => page.locator(`#${target}`).evaluate(el => {
      const r = el.getBoundingClientRect();
      const rail = document.querySelector('#sectionnav');
      return r.bottom > (rail?.offsetHeight || 0) && r.top < innerHeight;
    }), { timeout: 4000, message: `${name} should scroll #${target} into the viewport` }).toBe(true);
  }
}

async function assertExportsAndPrint(page) {
  const csvEvent = page.waitForEvent('download');
  await page.locator('#btn-trendcsv').click();
  const csv = await csvEvent;
  const rows = parseCsv(fs.readFileSync(await csv.path(), 'utf8'));
  expect(rows.length).toBeGreaterThan(10);
  expect(rows[0].join(' ')).toMatch(/year|fiscal/i);
  expect(rows.some(row => row.includes('2025') && row.includes(String(expectedSpend)))).toBe(true);

  const pngEvent = page.waitForEvent('download');
  await page.locator('[data-png="trendchart"]').click();
  const png = await pngEvent;
  const image = decodePng(fs.readFileSync(await png.path()));
  expect(image.width).toBeGreaterThanOrEqual(600);
  expect(image.height).toBeGreaterThanOrEqual(200);
  expect(image.colors).toBeGreaterThan(4);
  expect(image.nonBackground).toBeGreaterThan(1000);

  await page.emulateMedia({ media: 'print', reducedMotion: 'reduce' });
  const print = await page.evaluate(() => {
    const visible = el => {
      const style = getComputedStyle(el); const r = el.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && r.width > 0 && r.height > 0;
    };
    const charts = [...document.querySelectorAll('#dash svg[role="img"]')].filter(visible).map(el => {
      const r = el.getBoundingClientRect();
      return { id: el.id, left: r.left, right: r.right, width: r.width };
    });
    return {
      identity: document.querySelector('#dname')?.textContent || '',
      finance: document.querySelector('#dash')?.innerText || '',
      sources: [...document.querySelectorAll('#dash .cite')].filter(visible).map(el => el.textContent).join(' '),
      clientWidth: document.documentElement.clientWidth,
      charts,
    };
  });
  expect(print.identity).toMatch(/Dallas/i);
  expect(print.finance).toContain(expectedSpend.toLocaleString());
  expect(print.sources).toMatch(/TEA|Texas Education Agency/i);
  expect(print.charts.length).toBeGreaterThan(4);
  expect(print.charts.every(chart => chart.left >= -1 && chart.right <= print.clientWidth + 1 && chart.width > 100),
    JSON.stringify(print.charts)).toBe(true);
  await page.emulateMedia({ media: 'screen', reducedMotion: 'reduce' });

  await page.evaluate(() => { window.print = () => { window.__c4Printed = true; }; });
  await page.locator('#masthead .m-more summary').click();
  await page.locator('#mm-print').click();
  expect(await page.evaluate(() => window.__c4Printed)).toBe(true);
}

async function assertMapsAndHandoff(page) {
  await page.locator('#masthead a[href^="/geomap"]').first().click();
  await expect(page).toHaveURL(/\/geomap\?d=057905/);
  await waitForMap(page);
  await expect(page.locator('#p-name')).toContainText(/Dallas/i);
  await page.locator('#m-spend').click();
  await expect(page.locator('#m-spend')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#a11y-cap')).toContainText(/spending/i);
  await page.locator('#find').fill('Houston');
  await page.locator('#find').press('Enter');
  await expect(page.locator('#p-name')).toContainText(/Houston/i);
  await page.locator('#find').fill('Dallas');
  await page.locator('#find').press('Enter');
  await page.locator('#p-open').click();
  await waitForDashboard(page);
  await expect(page.locator('#dname')).toContainText(/Dallas/i);
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('tisd_district')).num)).toBe('057905');

  await page.goto('/map?d=057905');
  await waitForMap(page);
  await expect(page.locator('#p-name')).toContainText(/Dallas/i);
  await page.locator('#mode-arche').click();
  await expect(page.locator('#mode-arche')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#toggle-flags').click();
  await expect(page.locator('#toggle-flags')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#find').fill('Houston');
  await page.locator('#find').press('Enter');
  await expect(page.locator('#p-name')).toContainText(/Houston/i);
  await page.locator('#p-open').click();
  await waitForDashboard(page);
  await expect(page.locator('#dname')).toContainText(/Houston/i);
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('tisd_district')).num)).toBe('101912');
}

for (const viewport of viewports) for (const theme of themes) {
  test(`C-FLOW-01 complete public workflow ${viewport.name} ${viewport.width}x${viewport.height} ${theme}`, async ({ page }) => {
    test.setTimeout(120000);
    await page.setViewportSize(viewport);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const audit = await fixturePage(page, { theme });
    await page.goto('/');
    await expect(page.locator('#search')).toBeVisible();
    await expect(page.locator('#welcome-fig')).toBeVisible();
    await expect(page.locator('#hero-fig')).toBeVisible();
    if (theme === 'dark') await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');

    await assertAmbiguousFinder(page);
    await selectDallas(page);
    expect(await page.evaluate(() => JSON.parse(localStorage.getItem('tisd_district')).num)).toBe('057905');

    await page.evaluate(() => localStorage.setItem('tisd_district', JSON.stringify({ num: '101912', name: 'HOUSTON ISD' })));
    await page.goto('/?d=057905');
    await waitForDashboard(page);
    await expect(page.locator('#dname')).toContainText(/Dallas/i);

    for (const lens of ['Taxpayer / Grandparent', 'Reporter', 'Parent']) {
      await page.getByRole('button', { name: lens, exact: true }).click();
      await expect(page.getByRole('button', { name: lens, exact: true })).toHaveAttribute('aria-pressed', 'true');
      await expect(page.locator('#exec')).not.toBeEmpty();
    }

    await page.locator('#btn-compare').click();
    await page.locator('#csearch').fill('Houston');
    await page.locator('#csearch').press('Enter');
    await page.locator('#cresults button', { hasText: '101912' }).click();
    await expect(page.locator('#comparebar')).toContainText(/Houston/i);
    await expect(page.locator('#btn-uncompare')).toBeVisible();
    await page.locator('#btn-uncompare').click();
    await expect(page.locator('#comparebar')).not.toContainText(/Houston/i);

    await assertSectionNavigation(page);
    await assertReportSemantics(page, audit);
    await assertExportsAndPrint(page);
    await assertMapsAndHandoff(page);
    assertPassiveIsolation(audit);
  });
}

for (const viewport of [viewports[0], viewports[2]]) {
  test(`MAP-C4-01/02/03 active map/table parity ${viewport.name}`, async ({ page }) => {
    test.setTimeout(90000);
    await page.setViewportSize(viewport);
    const audit = await fixturePage(page, {
      geoDelayMs: 300,
      // Test-only edge case: the committed artifact is complete, so one real
      // district is patched to prove missing is not silently rendered as zero.
      geoPatches: { '101912': { t: null } },
    });
    await page.goto('/geomap', { waitUntil: 'domcontentloaded' });
    await page.locator('#m-pov').click();
    await waitForMap(page);
    await expect(page.locator('#m-pov')).toHaveAttribute('aria-pressed', 'true');

    const disclosure = page.locator('#a11y');
    await disclosure.locator('summary').click();
    await expect(disclosure).toHaveAttribute('open', '');
    await expect(page.locator('#a11y-table thead th')).toHaveCount(6);
    await expect(page.locator('#a11y-table tbody tr')).toHaveCount(districtGeo.meta.districts);
    await expect(page.locator('#a11y-table tbody a[href^="/?d="]')).toHaveCount(districtGeo.meta.districts);

    await page.locator('#find').fill('Dallas');
    await page.locator('#find').press('Enter');
    await expect(page.locator('#p-name')).toHaveText('Dallas ISD');
    await expect(page.locator('#p-id')).toContainText('057905');
    await expect(page.locator('#p-turn')).toHaveText('16.8%');
    await expect(page.locator('#p-spend')).toHaveText('$15,519');
    await expect(page.locator('#p-pov')).toHaveText('87.2%');
    await expect(page.locator('#p-gap')).toHaveText('+5.5 pts');
    const pinnedUrl = page.url();
    const viewBefore = await page.evaluate(() => JSON.parse(JSON.stringify(eval('view'))));

    const metricChecks = [
      { button: '#m-turn', key: 't', label: /Teacher turnover/i, column: 2, dallas: '16.8%' },
      { button: '#m-spend', key: 's', label: /Spending per student/i, column: 3, dallas: '$15,519' },
      { button: '#m-pov', key: 'p', label: /Students in poverty/i, column: 4, dallas: '87.2%' },
      { button: '#m-gap', key: 'g', label: /Beats its prediction/i, column: 5, dallas: '+5.5 pts' },
      { button: '#m-turn', key: 't', label: /Teacher turnover/i, column: 2, dallas: '16.8%' },
    ];
    for (const check of metricChecks) {
      const button = page.locator(check.button);
      await button.focus(); await page.keyboard.press('Enter');
      await expect(button).toBeFocused();
      await expect(button).toHaveAttribute('aria-pressed', 'true');
      await expect(page.locator('[id^="m-"][aria-pressed="true"]')).toHaveCount(1);
      await expect(page.locator('#a11y-cap')).toContainText(check.label);
      await expect(page.locator('#a11y-cap')).toContainText(/published values out of 1,016 mapped/i);
      await expect(page.locator('#a11y-note')).toContainText(/highest first.*without a published value are last/i);
      await expect(disclosure).toHaveAttribute('open', '');
      await expect(page.locator('#p-name')).toHaveText('Dallas ISD');
      await expect(page).toHaveURL(pinnedUrl);
      expect(await page.evaluate(() => JSON.parse(JSON.stringify(eval('view'))))).toEqual(viewBefore);

      const table = await page.locator('#a11y-table tbody tr').evaluateAll((rows, column) => rows.map(row => ({
        id: new URL(row.querySelector('a').href).searchParams.get('d'),
        selected: row.cells[column].textContent.trim(),
        cells: [...row.cells].map(cell => cell.textContent.trim()),
      })), check.column);
      expect(new Set(table.map(row => row.id)).size).toBe(districtGeo.meta.districts);
      const patchedValue = id => id === '101912' && check.key === 't' ? null : districtGeo.d[id].m[check.key];
      let sawMissing = false, previous = Infinity;
      for (const row of table) {
        const value = patchedValue(row.id);
        if (!Number.isFinite(value)) { sawMissing = true; expect(row.selected).toMatch(/Not published/i); }
        else {
          expect(sawMissing, `${check.key}: finite value after missing row`).toBe(false);
          expect(value).toBeLessThanOrEqual(previous);
          previous = value;
        }
      }
      const dallas = table.find(row => row.id === '057905');
      expect(dallas.selected).toBe(check.dallas);
      expect(dallas.cells).toEqual(['Dallas ISD', '139,096', '16.8%', '$15,519', '87.2%', '+5.5 pts']);
    }
    const houston = page.locator('#a11y-table tbody tr').filter({ has: page.locator('a[href="/?d=101912"]') });
    await expect(houston.locator('td').nth(2)).toHaveText('Not published');
    const zero = page.locator('#a11y-table tbody tr').filter({ has: page.locator('a[href="/?d=131001"]') });
    await expect(zero.locator('td').nth(2)).toHaveText('0%');

    await expect(page.locator('#zin')).toBeVisible();
    await expect(page.locator('#zout')).toBeVisible();
    await expect(page.locator('#reset')).toBeVisible();
    await page.locator('#p-open').click();
    await waitForDashboard(page);
    await expect(page.locator('#dname')).toContainText(/Dallas/i);
    assertPassiveIsolation(audit);
  });
}

for (const viewport of [viewports[0], viewports[2]]) {
  test(`DIALOG-C4-01/02/03/04 keyboard modal lifecycle ${viewport.name}`, async ({ page }) => {
    test.setTimeout(90000);
    await page.setViewportSize(viewport);
    const audit = await fixturePage(page);
    await page.goto('/?d=057905');
    await waitForDashboard(page);
    const more = page.locator('#masthead .m-more');
    const moreSummary = more.locator('summary');
    const disclaimer = page.locator('#mm-disclaimer');
    const discDialog = page.getByRole('dialog', { name: 'About this data — the honest version' });

    const openMoreDisclaimer = async () => {
      await moreSummary.focus(); await page.keyboard.press('Enter');
      await expect(more).toHaveAttribute('open', '');
      await disclaimer.focus(); await page.keyboard.press('Enter');
      await expect(discDialog).toBeVisible();
      await expect(discDialog).toHaveAttribute('aria-modal', 'true');
      await expect(page.locator('#disc-close')).toBeFocused();
      expect(await page.evaluate(() => document.querySelector('#disc-modal').contains(document.activeElement))).toBe(true);
    };

    await openMoreDisclaimer();
    await page.keyboard.press('Tab'); await expect(page.locator('#disc-close')).toBeFocused();
    await page.keyboard.press('Shift+Tab'); await expect(page.locator('#disc-close')).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(discDialog).toBeHidden();
    await expect(page.locator('#overlay')).toBeHidden();
    await expect(more).toHaveAttribute('open', '');
    await expect(disclaimer).toBeFocused();

    await disclaimer.focus(); await page.keyboard.press('Enter');
    await expect(discDialog).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(discDialog).toBeHidden();
    await expect(disclaimer).toBeFocused();

    await disclaimer.focus(); await page.keyboard.press('Enter');
    await expect(discDialog).toBeVisible();
    await page.locator('#overlay').click({ position: { x: 2, y: 2 } });
    await expect(discDialog).toBeHidden();
    await expect(disclaimer).toBeFocused();

    // Native <details> does not close on Escape, so toggle it explicitly before
    // exercising the independent in-page disclaimer entry point.
    if (await more.getAttribute('open') !== null) {
      await moreSummary.focus(); await page.keyboard.press('Enter');
      await expect(more).not.toHaveAttribute('open', '');
    }
    const directDisclaimer = page.locator('#open-disc');
    await directDisclaimer.focus(); await page.keyboard.press('Enter');
    await expect(discDialog).toBeVisible();
    await page.locator('#disc-close').press('Enter');
    await expect(discDialog).toBeHidden();
    await expect(directDisclaimer).toBeFocused();

    const compare = page.locator('#btn-compare');
    const compareDialog = page.getByRole('dialog', { name: 'Compare with which district?' });
    await compare.focus(); await page.keyboard.press('Enter');
    await expect(compareDialog).toBeVisible();
    await expect(compareDialog).toHaveAttribute('aria-modal', 'true');
    await expect(page.locator('#csearch')).toBeFocused();
    await page.keyboard.press('Tab'); await expect(page.locator('#csearchbtn')).toBeFocused();
    await page.keyboard.press('Shift+Tab'); await expect(page.locator('#csearch')).toBeFocused();
    await page.locator('#csearch').fill('Houston'); await page.locator('#csearch').press('Enter');
    const result = page.locator('#cresults button', { hasText: '101912' });
    await expect(result).toBeVisible();
    await result.focus(); await page.keyboard.press('Tab');
    await expect(page.locator('#csearch')).toBeFocused();
    await page.keyboard.press('Shift+Tab'); await expect(result).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(compareDialog).toBeHidden();
    await expect(page.locator('#comparebar')).toContainText(/Houston/i);
    await expect(compare).toBeFocused();
    await page.locator('#btn-uncompare').click();
    await expect(page.locator('#comparebar')).not.toContainText(/Houston/i);

    await compare.focus(); await page.keyboard.press('Enter');
    await page.locator('#csearch').fill('no such district zzz'); await page.locator('#csearch').press('Enter');
    await expect(page.locator('#cresults')).toContainText(/No districts found/i);
    await expect(page.locator('#csearch')).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(compare).toBeFocused();

    await compare.focus(); await page.keyboard.press('Enter');
    await expect(compareDialog).toBeVisible();
    await page.locator('#overlay').click({ position: { x: 2, y: 2 } });
    await expect(compareDialog).toBeHidden();
    await expect(compare).toBeFocused();

    await moreSummary.focus(); await page.keyboard.press('Enter');
    await expect(more).toHaveAttribute('open', '');
    const tourInvoker = page.locator('#mm-tour');
    await tourInvoker.focus(); await page.keyboard.press('Enter');
    const tour = page.locator('#tourbox');
    await expect(tour).toBeVisible();
    await expect(tour).toHaveAttribute('role', 'dialog');
    await expect(tour).toHaveAttribute('aria-modal', 'true');
    await expect(page.locator('#tour-title')).not.toBeEmpty();
    await expect(page.locator('#tour-next')).toBeFocused();
    await page.keyboard.press('Enter');
    await page.locator('#tour-skip').focus(); await page.keyboard.press('Enter');
    await expect(tour).toBeHidden();
    await expect(tourInvoker).toBeFocused();
    await expect(page.locator('.tour-highlight')).toHaveCount(0);
    await expect(page.locator('#overlay')).toBeHidden();

    await tourInvoker.focus(); await page.keyboard.press('Enter');
    await expect(tour).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(tour).toBeHidden();
    await expect(tourInvoker).toBeFocused();

    await page.keyboard.press('Escape');
    await compare.focus(); await page.keyboard.press('Enter');
    await expect(compareDialog).toBeVisible();
    await compare.evaluate(el => el.remove()); // test-only removed-invoker edge case
    await page.keyboard.press('Escape');
    await expect(page.locator('#search')).toBeFocused();
    await expect(page.locator('.sheet:visible')).toHaveCount(0);
    assertPassiveIsolation(audit);
  });
}

for (const viewport of [viewports[0], viewports[2]]) {
  test(`FRAME-03/05 Dallas and Argyle default finance frames ${viewport.name}`, async ({ page }) => {
    test.setTimeout(90000);
    await page.setViewportSize(viewport);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const audit = await fixturePage(page);
    const cases = [
      { id: '057905', name: 'Dallas', row: fixture.payloads.dallas_summary.at(-1), percentile: 70 },
      { id: '061910', name: 'Argyle', row: argyleEvidence.row, percentile: 85 },
    ];
    for (const item of cases) {
      await page.goto(`/?d=${item.id}`);
      await waitForDashboard(page);
      await expect(page.locator('#t-records')).toHaveText('20,587');
      await expect(page.locator('#dbwarn')).toBeHidden();
      const total = '$' + Math.round(item.row.spend_per_student).toLocaleString('en-US');
      const operating = '$' + Math.round(item.row.operating_spend / item.row.enrollment).toLocaleString('en-US');
      await expect(page.locator('#dname')).toContainText(new RegExp(item.name, 'i'));
      await expect(page.locator('#kpi-eyebrow')).toContainText(`Fiscal ${item.row.year}`);

      const hero = page.locator('#hero-kpis');
      await expect(hero).toBeVisible();
      await expect(hero).toContainText(`FY ${item.row.year}`);
      await expect(hero).toContainText(total);
      await expect(hero).toContainText(operating);
      await expect(hero).toContainText(/all funds \/ student.*includes construction & debt/i);
      await expect(hero).toContainText(/operations \/ student/i);

      const caption = page.locator('#tx-cap');
      await expect(caption).toBeVisible();
      await expect(caption).toContainText(new RegExp(`${item.name} ISD.s dollar`, 'i'));
      await expect(caption).toContainText(`FY ${item.row.year}`);
      await expect(caption).toContainText(total);
      await expect(caption).toContainText(operating);
      await expect(caption).toContainText(/construction & debt included/i);
      await expect(caption).toContainText(/construction and debt shown separately/i);

      const rank = page.locator('#kpis .kpi').filter({ has: page.locator('.label', { hasText: 'Statewide rank' }) });
      await expect(rank).toBeVisible();
      await rank.scrollIntoViewIfNeeded();
      await expect(rank.locator('.value')).toContainText(String(item.percentile));
      await expect(rank.locator('.metric-detail')).toContainText(/all funds \/ student.*includes construction & debt/i);
    }
    assertPassiveIsolation(audit);
  });
}

test('C-OFFLINE-01 recorded normal districts never show the degraded banner', async ({ page }) => {
  test.setTimeout(120000);
  const audit = await fixturePage(page);
  const districts = [
    ['057905', 'Dallas'], ['101912', 'Houston'], ['091907', 'Tioga'],
    ['003801', 'Pineywoods Community Academy'], ['061910', 'Argyle'],
  ];
  for (const [id, name] of districts) {
    await page.goto(`/?d=${id}`);
    await waitForDashboard(page);
    await expect(page.locator('#t-records')).toHaveText('20,587');
    await expect(page.locator('#dname')).toContainText(new RegExp(name, 'i'));
    await expect(page.locator('#dbwarn'), `${id} must use recorded healthy public responses`).toBeHidden();
    await expect(page.locator('#live-finance-status')).toBeHidden();
    await expect(page.locator('#kpis .kpi')).not.toHaveCount(0);
  }
  assertPassiveIsolation(audit);
});

test('C-OFFLINE-01 503 DB routes preserve artifacts and vendor-free maps', async ({ page }) => {
  test.setTimeout(90000);
  const audit = await fixturePage(page, { unavailable: true });
  await page.goto('/?d=057905');
  await waitForDashboard(page);
  await expect(page.locator('#dbwarn')).toBeVisible();
  await expect(page.locator('#dbwarn')).toContainText(/Live actual-finance unavailable.*saved public artifacts available/i);
  for (const selector of ['#outcomes-section', '#econ-section', '#equity-section', '#bond-section']) {
    await expect(page.locator(selector)).toBeVisible();
    await expect(page.locator(selector)).not.toBeEmpty();
  }
  await expect(page.locator('#kpis .kpi')).toHaveCount(0);
  await expect(page.locator('#live-finance-status')).toBeVisible();
  await expect(page.locator('#kpi-eyebrow')).toContainText(/actual-finance data unavailable/i);
  await expect(page.locator('#exec')).toContainText(/year-by-year budget summary.*could not be loaded/i);
  for (const selector of ['#econ-levers', '#eq-bars', '#bond-timeline']) {
    await expect(page.locator(selector)).toBeVisible();
    const box = await page.locator(selector).boundingBox();
    expect(box.width).toBeGreaterThan(100); expect(box.height).toBeGreaterThan(50);
  }
  expect(audit.requests.filter(value => /\/district\/057905\/(summary|peers|breakdown|spending-detail)|\/anomalies/.test(value)).length)
    .toBeGreaterThanOrEqual(5);
  expect(audit.blocked.some(value => /POST|\/query|\/feedback|\/track|\/telemetry/i.test(value))).toBe(false);

  await page.goto('/geomap?d=057905');
  await waitForMap(page);
  await expect(page.locator('#p-name')).toContainText(/Dallas/i);
  await expect(page.locator('#a11y-table tbody tr')).not.toHaveCount(0);
  await page.goto('/heatmap');
  await waitForMap(page, '#cv');
  await expect(page.locator('#msg')).toContainText(/Built-in map/i);
  await expect(page.locator('#a11y-table tbody tr')).not.toHaveCount(0);
  assertPassiveIsolation(audit);
});

test('C-A11Y-01 keyboard tasks, dialog return focus, 320px and 200% reflow', async ({ page }) => {
  test.setTimeout(90000);
  await page.setViewportSize({ width: 640, height: 900 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const audit = await fixturePage(page, { theme: 'dark' });
  await page.goto('/');
  await page.locator('#search').focus();
  await page.keyboard.type('Dallas');
  await page.keyboard.press('Enter');
  const result = page.locator('#results button', { hasText: '057905' });
  await result.focus();
  await page.keyboard.press('Enter');
  await waitForDashboard(page);

  const taxpayer = page.getByRole('button', { name: 'Taxpayer / Grandparent', exact: true });
  await taxpayer.focus(); await page.keyboard.press(' ');
  await expect(taxpayer).toHaveAttribute('aria-pressed', 'true');
  const nav = page.locator('#sectionnav button', { hasText: 'What you pay' });
  await nav.focus(); await page.keyboard.press('Enter');
  await expect(page.locator('#econ-section')).toBeVisible();

  const compare = page.locator('#btn-compare');
  await compare.focus(); await page.keyboard.press('Enter');
  await expect(page.locator('#compare-modal')).toBeVisible();
  await page.locator('#csearch').fill('Houston'); await page.locator('#csearch').press('Enter');
  const compareResult = page.locator('#cresults button', { hasText: '101912' });
  await compareResult.focus(); await page.keyboard.press('Enter');
  await expect(page.locator('#compare-modal')).toBeHidden();
  await expect(page.locator('#comparebar')).toContainText(/Houston/i);

  const sourceSummary = page.locator('#econ-section details.evidence-detail summary', { hasText: 'Source, definitions and limits' });
  await sourceSummary.focus(); await page.keyboard.press('Enter');
  await expect(sourceSummary.locator('..')).toHaveAttribute('open', '');
  const tableSummary = page.locator('#econ-a11y summary');
  await tableSummary.focus(); await page.keyboard.press('Enter');
  await expect(page.locator('#econ-table')).toBeVisible();

  await page.locator('#masthead .m-more summary').focus(); await page.keyboard.press('Enter');
  const disclaimer = page.locator('#mm-disclaimer');
  await disclaimer.focus(); await page.keyboard.press('Enter');
  await expect(page.locator('#disc-modal')).toBeVisible();
  await page.locator('#disc-close').focus(); await page.keyboard.press('Enter');
  await expect(page.locator('#disc-modal')).toBeHidden();
  await expect(disclaimer).toBeFocused();

  const reflow = () => page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    crossing: [...document.querySelectorAll('body *')].map(el => {
      const r = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      const clips = (() => { for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        if (/auto|scroll|hidden|clip/.test(getComputedStyle(p).overflowX)) return true;
      } return false; })();
      return { id: el.id, section: el.closest('[id]')?.id || '', cls: el.className?.baseVal || el.className || '', tag: el.tagName,
        left: r.left, right: r.right, width: r.width, clientWidth: el.clientWidth, scrollWidth: el.scrollWidth,
        position: style.position, overflowX: style.overflowX, clips };
    }).filter(r => !r.clips && r.left < document.documentElement.clientWidth && r.right > document.documentElement.clientWidth + 1)
      .sort((a, b) => b.right - a.right).slice(0, 12),
  }));
  // WCAG text-resize check: double the root text size while preserving the
  // CSS viewport, which exposes fixed-width controls without the false page
  // overflow caused by CSS `zoom` scaling the viewport itself.
  await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
  const at200 = await reflow();
  expect(at200.scrollWidth <= at200.clientWidth + 1, JSON.stringify(at200)).toBe(true);
  await page.evaluate(() => { document.documentElement.style.fontSize = ''; });
  await page.setViewportSize({ width: 320, height: 844 });
  const at320 = await reflow();
  expect(at320.scrollWidth <= 320, JSON.stringify(at320)).toBe(true);
  await expect(page.locator('#search')).toBeVisible();
  await expect(page.locator('#lensbar button[aria-pressed="true"]')).toHaveCount(1);
  assertPassiveIsolation(audit);
});

test('C-FLOW-01 public route render inventory stays available', async ({ page, browserName }) => {
  test.setTimeout(90000);
  const audit = await fixturePage(page);
  const routes = ['/feed', '/forensics', '/geomap', '/heatmap', '/about', '/sources', '/map', '/intel', '/transparency', '/docs'];
  for (const route of routes) {
    const response = await page.goto(route);
    expect(response.status(), `${browserName} ${route}`).toBe(200);
    await expect(page.locator('body')).not.toBeEmpty();
    await expect(page.locator('h1, [role="heading"]')).not.toHaveCount(0);
  }
  assertPassiveIsolation(audit);
});
