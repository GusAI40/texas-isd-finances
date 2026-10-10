/* UI behavior is verified with mocked /query responses. No provider calls. */
const { test, expect } = require('@playwright/test');
const { installPublicFixtures, cleanState } = require('./public-fixtures');
const fs = require('node:fs');
const path = require('node:path');

const evidence = path.join(__dirname, '../../docs/evidence/landing');
const answer = {
  success: true,
  answer: 'Dallas ISD spent $3.32 billion across all funds in fiscal 2025. Source: TEA PEIMS actual finance. These are historical records, not a live budget.',
  structured: {
    lead: 'Dallas ISD spent $3.32 billion across all funds in fiscal 2025.',
    lead_runs: [{ t: 'Dallas ISD spent $3.32 billion across all funds in fiscal 2025.' }],
    figures: { name: 'Dallas ISD', district_number: '057905', year: 2025,
      note: 'All funds, including construction and debt payments.',
      cards: [{ label: 'Total spending', value: '$3.32 billion' },
        { label: 'Students', value: '139,776' }] },
    blocks: [{ type: 'table', head: ['Spending category', 'Dollars'],
      rows: [['Classroom teaching', '$1,092,607,589'], ['Construction', '$766,316,261'],
        ['Debt payments', '$500,174,938'], ['Other spending, combined', '$960,109,927']] }],
    sources: [{ name: 'TEA PEIMS actual finance', url: '/sources' }],
    limitations: ['Historical records, not a live budget.'],
    follow_ups: [{ label: 'Compare districts', question: 'Compare Dallas ISD with similar districts in fiscal 2025.' }]
  }
};

async function prepared(page, options = {}) {
  const audit = { errors: [], assetFailures: [], paidRequests: [] };
  page.on('pageerror', e => audit.errors.push(e.message));
  page.on('response', r => {
    if (r.status() >= 400 && ['script', 'stylesheet', 'image', 'font'].includes(r.request().resourceType()))
      audit.assetFailures.push(`${r.status()} ${r.url()}`);
  });
  await cleanState(page, options.theme || 'light');
  await installPublicFixtures(page);
  // Register last so this mock always handles /query before the GET fixture.
  await page.route('**/query', async route => {
    audit.paidRequests.push(route.request().postDataJSON());
    if (options.query) return options.query(route, audit.paidRequests.length);
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(answer) });
  });
  await page.goto(options.url || '/');
  await expect(page.locator('#welcome-h')).toBeAttached();
  return audit;
}

async function openChat(page) {
  await page.locator('.ta-fab').click();
  await expect(page.locator('.ta-wrap')).toBeVisible();
  return page.locator('.ta-wrap');
}

async function ask(page, question = 'Where does Dallas ISD school money go?') {
  const chat = await openChat(page);
  await chat.locator('.ta-row input').fill(question);
  await chat.getByRole('button', { name: 'Ask', exact: true }).click();
  return chat;
}

for (const width of [320, 390, 430, 1440]) {
  test(`landing, setup, and sourced chat at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const audit = await prepared(page);
    await expect(page.locator('#welcome')).toBeVisible();
    await expect(page.locator('#welcome')).toContainText(/Gus|TAG/);
    await expect(page.locator('#welcome')).toContainText(/ChatGPT/);
    await expect(page.locator('#welcome')).toContainText(/Dallas ISD/);
    await expect(page.locator('#welcome')).toContainText(/2025/);
    const recorded = JSON.parse(fs.readFileSync(path.join(evidence, 'dallas-example.json'), 'utf8'));
    const cells = await page.locator('.dallas-cell').evaluateAll(nodes => nodes.map(n => ({
      dollars: Number(n.dataset.dollars), group: n.dataset.group,
      area: n.getBoundingClientRect().width * n.getBoundingClientRect().height
    })));
    const values = [0, 3, 1, 2].map(index => recorded.groups[index].dollars);
    expect(values.reduce((sum, n) => sum + n, 0)).toBe(3319208715);
    expect(cells).toHaveLength(4);
    const paintedArea = cells.reduce((sum, cell) => sum + cell.area, 0);
    cells.forEach((cell, index) => {
      expect(cell.dollars).toBe(values[index]);
      const expected = values[index] / recorded.total_spending_dollars * 100;
      // Grid dividers consume a few pixels; proportions must remain faithful.
      expect(Math.abs(cell.area / paintedArea * 100 - expected)).toBeLessThan(0.4);
    });
    const sizes = await page.locator('.dallas-record figcaption, .dallas-cell strong, .dallas-cell span, .dallas-cell small')
      .evaluateAll(nodes => nodes.map(n => parseFloat(getComputedStyle(n).fontSize)));
    expect(Math.min(...sizes)).toBeGreaterThanOrEqual(14);
    await expect(page.locator('.dallas-total')).toHaveAttribute('aria-label', /3,319,208,715/);
    await expect(page.locator('#welcome #tx-pennies-2')).toBeHidden();
    await expect(page.locator('#welcome #tx-cap-2')).toBeHidden();
    expect(await page.locator('#example-dallas').evaluate(el => parseFloat(getComputedStyle(el).fontSize)))
      .toBeGreaterThanOrEqual(14);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const ordered = await page.evaluate(() => document.querySelector('#welcome')
      .compareDocumentPosition(document.querySelector('#picker-section')) & Node.DOCUMENT_POSITION_FOLLOWING);
    expect(ordered).toBeTruthy();
    fs.mkdirSync(evidence, { recursive: true });
    await page.screenshot({ path: path.join(evidence, `${info.project.name}-landing-${width}.png`) });
    await page.locator('#welcome').screenshot({ path: path.join(evidence, `${info.project.name}-landing-full-${width}.png`) });
    await page.getByRole('link', { name: 'Set up in ChatGPT', exact: true }).first().click();
    const guide = page.locator('#chatgpt-setup');
    await expect(guide).toBeVisible();
    await expect(guide).toHaveAttribute('open', '');
    await expect(guide.locator('.setup-body')).toBeVisible();
    for (const label of ['Add custom MCP server', 'Texas ISD Finances', 'https://txisd.dev/mcp',
      'No authentication', 'Create as a plugin', 'Personal']) await expect(guide).toContainText(label);
    await expect(guide).toContainText(/account and workspace/);
    await guide.screenshot({ path: path.join(evidence, `${info.project.name}-setup-${width}.png`) });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const chat = await ask(page);
    await expect(chat.locator('.ta-cards')).toContainText('139,776');
    await expect(chat.locator('.ta-thread')).toContainText('fiscal 2025');
    await expect(chat.locator('.ta-thread')).toContainText('TEA PEIMS');
    await expect(chat.getByRole('button', {name: 'Ask', exact: true})).toBeEnabled();
    await page.screenshot({ path: path.join(evidence, `${info.project.name}-chat-${width}.png`) });
    expect(await chat.locator('.ta-sheet').evaluate(el => el.getBoundingClientRect().width <= innerWidth)).toBe(true);
    expect(audit.errors).toEqual([]);
    expect(audit.assetFailures).toEqual([]);
    expect(audit.paidRequests).toHaveLength(1);
    expect(audit.paidRequests[0]).toMatchObject({ question: 'Where does Dallas ISD school money go?' });
    expect(audit.paidRequests[0].conversation_id).toBeTruthy();
    expect(audit.paidRequests[0].turn).toBe(1);
  });
}

test('visible Dallas example asks once with district context and returns focus', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  const audit = await prepared(page);
  const example = page.locator('#example-dallas');
  await example.click();
  const chat = page.locator('.ta-wrap');
  await expect(chat.locator('.ta-cards')).toContainText('139,776');
  await expect(chat.locator('.ta-thread')).toContainText('Where did Dallas ISD money go?');
  expect(audit.paidRequests).toHaveLength(1);
  expect(audit.paidRequests[0]).toMatchObject({question:'Where did Dallas ISD money go?',district_number:'057905',turn:1});
  await page.keyboard.press('Escape');
  await expect(example).toBeFocused();
});

test('keyboard dismissal, focus trap, and reopening preserve the conversation', async ({page}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await prepared(page);
  await ask(page);
  const chat = page.locator('.ta-wrap');
  await expect(chat.locator('.ta-cards')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(chat).toBeHidden();
  await expect(page.locator('.ta-fab')).toBeFocused();
  await openChat(page);
  await expect(chat.locator('.ta-cards')).toBeVisible();
  await chat.locator('.ta-x').focus();
  await page.keyboard.press('Shift+Tab');
  expect(await page.evaluate(() => !!document.activeElement.closest('.ta-wrap'))).toBe(true);
  await page.keyboard.press('Tab');
  expect(await page.evaluate(() => !!document.activeElement.closest('.ta-wrap'))).toBe(true);
});

test('follow-up submission keeps original focus return and full question attribution', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  const audit = await prepared(page);
  const chat = await ask(page);
  await expect(chat.getByRole('button',{name:'Compare districts',exact:true})).toBeVisible();
  await chat.getByRole('button',{name:'Compare districts',exact:true}).click();
  await expect(chat.locator('.ta-cards')).toHaveCount(2);
  expect(audit.paidRequests).toHaveLength(2);
  expect(audit.paidRequests[1]).toMatchObject({question:answer.structured.follow_ups[0].question,followup_label:'Compare districts'});
  await page.keyboard.press('Escape');
  await expect(page.locator('.ta-fab')).toBeFocused();
});

test('setup anchor remains usable for a returning district reader', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  await prepared(page,{url:'/?d=057905#chatgpt-setup'});
  await expect(page.locator('#welcome')).toBeHidden();
  await expect(page.locator('#chatgpt-setup')).toBeVisible();
  await expect(page.locator('#chatgpt-setup')).toContainText('Add custom MCP server');
});

test('setup disclosure toggles with keyboard and repeated setup links reopen it', async ({page}) => {
  await prepared(page);
  const guide = page.locator('#chatgpt-setup');
  await expect(guide).not.toHaveAttribute('open', '');
  const action = page.getByRole('link', {name:'Set up in ChatGPT',exact:true}).first();
  await action.click();
  await expect(guide.locator('.setup-body')).toBeVisible();
  await guide.locator(':scope > summary').focus();
  await page.keyboard.press('Enter');
  await expect(guide.locator('.setup-body')).toBeHidden();
  await action.click();
  await expect(guide.locator('.setup-body')).toBeVisible();
});

for (const [name, mock, expected] of [
  ['rate limited', route => route.fulfill({status:429, contentType:'application/json', body:'{}'}), /wait|minute/i],
  ['service error', route => route.fulfill({status:503, contentType:'application/json', body:'{"error":"test unavailable"}'}), /unavailable|try|service/i],
  ['network failure', route => route.abort('failed'), /connection|reached|network/i],
  ['empty answer', route => route.fulfill({contentType:'application/json',body:'{"success":true,"answer":""}'}), /No answer|rephrasing|rephrase/i]
]) {
  test(`${name} has a manual retry that retains the question`, async ({page}, info) => {
    await page.setViewportSize({width:390,height:844});
    await page.emulateMedia({reducedMotion:'reduce'});
    const audit = await prepared(page, {query:(r,n) => n === 1 ? mock(r) : r.fulfill({contentType:'application/json',body:JSON.stringify(answer)})});
    const chat = await ask(page);
    await expect(chat.locator('.ta-thread')).toContainText(expected);
    await expect(chat.locator('.ta-retry')).toBeVisible();
    if (name === 'service error') await page.screenshot({path:path.join(evidence,`${info.project.name}-chat-error-390.png`)});
    expect(audit.paidRequests).toHaveLength(1);
    await chat.locator('.ta-retry').last().click();
    await expect(chat.locator('.ta-cards')).toBeVisible();
    expect(audit.paidRequests).toHaveLength(2);
    expect(audit.paidRequests[1].question).toBe(audit.paidRequests[0].question);
    expect(audit.paidRequests[1].conversation_id).toBe(audit.paidRequests[0].conversation_id);
    expect(audit.paidRequests[1].turn).toBe(2);
  });
}

test('Stop cancels a pending question and Retry ignores its late response', async ({page}, info) => {
  await page.setViewportSize({width:390,height:844});
  await page.emulateMedia({reducedMotion:'reduce'});
  let release;
  const waiting = new Promise(resolve => { release = resolve; });
  const audit = await prepared(page, {query:async(r,n) => {
    if(n === 1) { await waiting; return r.fulfill({contentType:'application/json',body:'{"success":true,"answer":"STALE ANSWER"}'}).catch(()=>{}); }
    return r.fulfill({contentType:'application/json',body:JSON.stringify(answer)});
  }});
  const chat = await ask(page);
  await expect(chat.locator('.ta-stop')).toBeVisible();
  await page.screenshot({path:path.join(evidence,`${info.project.name}-chat-loading-390.png`)});
  await chat.locator('.ta-stop').click();
  await expect(chat.locator('.ta-skel')).toHaveCount(0);
  await expect(chat.locator('.ta-retry')).toBeVisible();
  await page.screenshot({path:path.join(evidence,`${info.project.name}-chat-stopped-390.png`)});
  await chat.locator('.ta-retry').click();
  await expect(chat.locator('.ta-cards')).toBeVisible();
  release();
  await page.waitForTimeout(100);
  await expect(chat.locator('.ta-thread')).not.toContainText('STALE ANSWER');
  expect(audit.paidRequests).toHaveLength(2);
});

test('empty chat gives examples; very short and composing input do not send', async ({page}, info) => {
  await page.setViewportSize({width:390,height:844});
  await page.emulateMedia({reducedMotion:'reduce'});
  const audit = await prepared(page);
  const chat = await openChat(page);
  await expect(chat.locator('.ta-empty')).toBeVisible();
  await expect(chat.locator('.ta-chips button').first()).toBeVisible();
  await page.screenshot({path:path.join(evidence,`${info.project.name}-chat-empty-390.png`)});
  await chat.locator('.ta-row input').fill('Hi');
  await chat.getByRole('button',{name:'Ask',exact:true}).click();
  expect(audit.paidRequests).toHaveLength(0);
  await chat.locator('.ta-row input').fill('Dallas school money');
  await chat.locator('.ta-row input').dispatchEvent('keydown',{key:'Enter',isComposing:true});
  expect(audit.paidRequests).toHaveLength(0);
});

test('inline question uses shared chat once; missing widget leaves the fallback usable', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  const audit = await prepared(page);
  await page.locator('#question').fill('Where does Dallas ISD school money go?');
  await page.locator('#askbtn').click();
  await expect(page.locator('.ta-wrap')).toBeVisible();
  await expect(page.locator('.ta-cards')).toBeVisible();
  expect(audit.paidRequests).toHaveLength(1);
  await page.locator('.ta-x').click();
  await page.route('**/static/ask.js',route=>route.fulfill({contentType:'application/javascript',body:'/* unavailable widget */'}));
  await page.reload();
  await page.locator('#question').fill('Where does Dallas ISD school money go?');
  await page.locator('#askbtn').click();
  await expect(page.locator('#answer')).toContainText(/Dallas|3.32/);
  expect(audit.paidRequests).toHaveLength(2);
});

test('dark theme preserves readable landing and chat at phone width', async ({page}, info) => {
  await page.setViewportSize({width:390,height:844});
  await page.emulateMedia({reducedMotion:'reduce'});
  const audit = await prepared(page,{theme:'dark'});
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  await page.screenshot({path:path.join(evidence,`${info.project.name}-landing-dark-390.png`)});
  await ask(page);
  await expect(page.locator('.ta-cards')).toBeVisible();
  await page.screenshot({path:path.join(evidence,`${info.project.name}-chat-dark-390.png`)});
  expect(audit.errors).toEqual([]);
});

test('closing a loading chat cancels it and never moves focus into hidden controls', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  await prepared(page,{query:route=>new Promise(resolve=>setTimeout(()=>resolve(route.fulfill({contentType:'application/json',body:JSON.stringify(answer)}).catch(()=>{})),800))});
  await ask(page);
  await page.keyboard.press('Escape');
  await expect(page.locator('.ta-wrap')).toBeHidden();
  await expect(page.locator('.ta-fab')).toBeFocused();
  await page.waitForTimeout(950);
  await expect(page.locator('.ta-fab')).toBeFocused();
  await openChat(page);
  await expect(page.locator('.ta-skel')).toHaveCount(0);
  await expect(page.locator('.ta-retry')).toBeVisible();
});

test('bounded timeout has retry and no auto-resubmission', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.clock.install();
  const audit = await prepared(page, {query:()=>new Promise(()=>{})});
  const chat = await ask(page);
  await expect(chat.locator('.ta-stop')).toBeVisible();
  await page.clock.fastForward(70_000);
  await expect(chat.locator('.ta-retry')).toBeVisible();
  await expect(chat.locator('.ta-thread')).toContainText(/long|timed|try again/i);
  expect(audit.paidRequests).toHaveLength(1);
});

test('linked district context survives website-chat submission', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  const audit = await prepared(page,{url:'/?d=057905'});
  await expect(page.locator('#welcome')).toBeHidden();
  await ask(page);
  await expect(page.locator('.ta-cards')).toBeVisible();
  expect(audit.paidRequests[0].district_number).toBe('057905');
});

test('structured hostile text is presented as text, never executed markup', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  await prepared(page,{query:r=>r.fulfill({contentType:'application/json',body:JSON.stringify({success:true,structured:{lead:'<img src=x onerror="window.injected=true">',lead_runs:[{t:'<img src=x onerror="window.injected=true">'}],blocks:[{type:'paragraph',runs:[{t:'<script>window.injected=true</script>'}]}]}})})});
  const chat = await ask(page);
  await expect(chat.locator('.ta-thread')).toContainText('<img');
  expect(await page.evaluate(()=>window.injected)).toBeUndefined();
  expect(await chat.locator('.ta-thread img, .ta-thread script').count()).toBe(0);
});

test('new landing, setup and chat controls meet automated WCAG AA checks', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  await prepared(page);
  await page.getByRole('link',{name:'Set up in ChatGPT',exact:true}).first().click();
  await page.addScriptTag({path:require.resolve('axe-core/axe.min.js')});
  const run = async include => page.evaluate(async include => {
    const results = await axe.run({include},{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});
    return results.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}));
  },include);
  expect(await run([['#welcome'],['#chatgpt-setup']])).toEqual([]);
  await ask(page);
  await expect(page.locator('.ta-cards')).toBeVisible();
  expect(await run([['.ta-wrap']])).toEqual([]);
});
