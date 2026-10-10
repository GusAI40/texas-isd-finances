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
  await (await chatOpener(page)).click();
  await expect(page.locator('.ta-wrap')).toBeVisible();
  return page.locator('.ta-wrap');
}

async function chatOpener(page) {
  const floating = page.locator('.ta-fab');
  return await floating.isVisible() ? floating : page.locator('#ask-your-own');
}

async function ask(page, question = 'Where does Dallas ISD school money go?') {
  const chat = await openChat(page);
  await chat.locator('.ta-row input').fill(question);
  await chat.getByRole('button', { name: 'Ask', exact: true }).click();
  return chat;
}

async function checkAA(page, include) {
  if(!await page.evaluate(()=>!!window.axe)) await page.addScriptTag({path:require.resolve('axe-core/axe.min.js')});
  const violations=await page.evaluate(async include=>{
    const result=await axe.run({include},{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});
    return result.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}));
  },include);
  expect(violations).toEqual([]);
}

for (const width of [320, 390, 430, 1440]) {
  test(`landing, setup, and sourced chat at ${width}px`, async ({ page }, info) => {
    const height = ({320:740,390:844,430:932,1440:900})[width];
    await page.setViewportSize({ width, height });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const audit = await prepared(page);
    await expect(page.locator('#welcome')).toBeVisible();
    await expect(page.locator('.landing-purpose')).toContainText(/Gus|TAG/);
    await expect(page.locator('.landing-purpose')).toContainText(/ChatGPT/);
    await expect(page.locator('#welcome')).toContainText(/Dallas ISD/);
    await expect(page.locator('#welcome')).toContainText(/2025/);
    const recorded = JSON.parse(fs.readFileSync(path.join(evidence, 'dallas-example.json'), 'utf8'));
    const cells = await page.locator('.dallas-cell').evaluateAll(nodes => nodes.map(n => ({
      dollars: Number(n.dataset.dollars), group: n.dataset.group,
      area: n.getBoundingClientRect().width * n.getBoundingClientRect().height,
      fillRatio:n.querySelector('.dallas-fill').getBoundingClientRect().width/n.getBoundingClientRect().width
    })));
    const values = [0, 3, 1, 2].map(index => recorded.groups[index].dollars);
    expect(values.reduce((sum, n) => sum + n, 0)).toBe(3319208715);
    expect(cells).toHaveLength(4);
    if (width < 700) {
      const grid = await page.locator('.dallas-grid i').evaluateAll(nodes => nodes.map(n => n.className));
      expect(grid).toHaveLength(100);
      expect(grid.filter(x => x === 'classroom')).toHaveLength(33);
      expect(grid.filter(x => x === 'construction')).toHaveLength(23);
      expect(grid.filter(x => x === 'debt')).toHaveLength(15);
      expect(grid.filter(x => x === 'other')).toHaveLength(29);
      await expect(page.locator('.dallas-grid-note')).toContainText(/Each square is about 1%/);
    } else {
      const paintedArea = cells.reduce((sum, cell) => sum + cell.area, 0);
      cells.forEach((cell, index) => {
        expect(cell.dollars).toBe(values[index]);
        const expected = values[index] / recorded.total_spending_dollars * 100;
        expect(Math.abs(cell.area / paintedArea * 100 - expected)).toBeLessThan(0.4);
      });
    }
    const sizes = await page.locator('.dallas-record figcaption, .dallas-cell strong, .dallas-cell span, .dallas-cell small')
      .evaluateAll(nodes => nodes.map(n => parseFloat(getComputedStyle(n).fontSize)));
    expect(Math.min(...sizes)).toBeGreaterThanOrEqual(14);
    await expect(page.locator('.dallas-total')).toHaveAttribute('aria-label', /3,319,208,715/);
    await expect(page.locator('#welcome #tx-pennies-2')).toBeHidden();
    await expect(page.locator('#welcome #tx-cap-2')).toBeHidden();
    expect(await page.locator('#example-dallas').evaluate(el => parseFloat(getComputedStyle(el).fontSize)))
      .toBeGreaterThanOrEqual(14);
    await expect(page.locator('.source-records .record-row')).toHaveCount(4);
    await expect(page.locator('.district-match .match-code')).toHaveText('057905');
    await expect(page.locator('.source-answer .answer-stack i')).toHaveCount(4);
    const sourceShares = await page.locator('.source-answer .answer-stack i').evaluateAll(nodes =>
      nodes.map(n => n.getBoundingClientRect().width / n.parentElement.getBoundingClientRect().width * 100));
    [32.9177,23.0873,15.0691,28.9259].forEach((share,index) =>
      expect(Math.abs(sourceShares[index] - share)).toBeLessThan(.5));
    await expect(page.locator('.source-answer')).toContainText('$1,092,607,589');
    await expect(page.locator('.source-answer a')).toHaveAttribute('href','/sources');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const composition = await page.evaluate(() => {
      const chart=document.querySelector('.dallas-map').getBoundingClientRect();
      const source=document.querySelector('.landing-caption').getBoundingClientRect();
      const action=document.querySelector('#example-dallas').getBoundingClientRect();
      const name=document.querySelector('.dallas-cell.construction strong');
      const range=document.createRange();range.selectNodeContents(name);
      return {chartTop:chart.top,chartBottom:chart.bottom,sourceBottom:source.bottom,actionBottom:action.bottom,
        constructionLines:range.getClientRects().length,constructionText:name.textContent,
        labels:[...document.querySelectorAll('.dallas-cell strong')].map(n=>({
          width:n.scrollWidth,available:n.clientWidth,text:n.textContent
        }))};
    });
    if (width < 700) expect(await page.locator('.dallas-grid').isVisible()).toBe(true);
    else {
      expect(composition.chartTop).toBeLessThan(350);
      expect(composition.chartBottom).toBeLessThanOrEqual(height);
      expect(composition.sourceBottom).toBeLessThanOrEqual(height);
      expect(composition.constructionLines).toBe(1);
      expect(composition.constructionText).toBe('Construction');
      composition.labels.forEach(label=>expect(label.width).toBeLessThanOrEqual(label.available));
    }
    await expect(page.locator('.ta-fab')).toBeHidden();
    const ordered = await page.evaluate(() => document.querySelector('#welcome')
      .compareDocumentPosition(document.querySelector('#picker-section')) & Node.DOCUMENT_POSITION_FOLLOWING);
    expect(ordered).toBeTruthy();
    fs.mkdirSync(evidence, { recursive: true });
    await page.screenshot({ path: path.join(evidence, `${info.project.name}-landing-${width}.png`) });
    const guide = page.locator('#chatgpt-setup');
    const clip=await page.evaluate(()=>{
      const first=document.querySelector('#welcome').getBoundingClientRect();
      const last=document.querySelector('#chatgpt-setup').getBoundingClientRect();
      return {x:first.left,y:first.top+scrollY,width:first.width,height:last.bottom-first.top};
    });
    await page.screenshot({path:path.join(evidence,`${info.project.name}-landing-full-${width}.png`),fullPage:true,clip});
    await guide.locator(':scope > summary').click();
    await expect(guide).toBeVisible();
    await expect(guide).toHaveAttribute('open', '');
    await expect(guide.locator('.setup-body')).toBeVisible();
    for (const label of ['Add custom MCP server', 'Texas ISD Finances', 'https://txisd.dev/mcp',
      'No authentication', 'Create as a plugin', 'Personal']) await expect(guide).toContainText(label);
    await expect(guide).toContainText(/account and workspace/);
    const qualification = guide.locator('.setup-qualification');
    await expect(qualification).toBeVisible();
    expect(await guide.evaluate(node => {
      const notice=node.querySelector('.setup-qualification');
      const link=node.querySelector('a[href="https://chatgpt.com/plugins"]');
      return !!(notice.compareDocumentPosition(link)&Node.DOCUMENT_POSITION_FOLLOWING) &&
        notice.getBoundingClientRect().bottom<link.getBoundingClientRect().top;
    })).toBe(true);
    await guide.screenshot({ path: path.join(evidence, `${info.project.name}-setup-${width}.png`) });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const chat = await ask(page);
    await expect(chat.locator('.ta-cards')).toContainText('139,776');
    await expect(chat.locator('.ta-thread')).toContainText('fiscal 2025');
    await expect(chat.locator('.ta-thread')).toContainText('TEA PEIMS');
    await expect(chat.locator('.ta-context')).toBeVisible();
    await expect(chat.locator('.ta-context')).toContainText('2025');
    await expect(chat.locator('.ta-context')).toContainText('All funds');
    await expect(chat.locator('.ta-answer-source')).toBeVisible();
    await expect(chat.locator('.ta-answer-source')).toContainText('TEA PEIMS');
    await expect(chat.locator('.ta-chart-record')).toContainText('TEA PEIMS actual finance');
    await expect(chat.locator('.ta-chart-record')).toContainText(/Dallas ISD.*Fiscal 2025.*All funds/);
    await expect(chat.locator('.ta-limit')).toBeVisible();
    await expect(chat.locator('.ta-limit')).toContainText('not a live budget');
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

test('recorded Dallas example highlights evidence without a paid query', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  const audit = await prepared(page);
  const example = page.locator('#example-dallas');
  await example.click();
  await expect(page.locator('#example-answer')).toContainText('Classroom teaching accounted for $1.09B');
  await expect(example).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('.dallas-cell.is-highlighted')).toHaveCount(1);
  await expect(page.locator('.dallas-cell.classroom')).toHaveClass(/is-highlighted/);
  expect(audit.paidRequests).toHaveLength(0);
  await expect(page.locator('.ta-wrap')).toBeHidden();
});

test('landing keeps the original pipeline in the DOM but shows only the recorded hero', async ({page}) => {
  await prepared(page);
  const welcome = page.locator('#welcome');
  await expect(welcome.locator(':scope > .pipeline')).toBeAttached();
  await expect(welcome.locator(':scope > .pipeline')).toBeHidden();
  await expect(welcome.locator(':scope > .hero-grid')).toBeVisible();
  const visibleChildren = await welcome.locator(':scope > *').evaluateAll(nodes => nodes
    .filter(node => getComputedStyle(node).display !== 'none').map(node => node.className));
  expect(visibleChildren).toEqual(['hero-grid', 'source-path']);
});

test('landing purpose immediately follows the welcome card with no visual gap', async ({page}) => {
  await page.setViewportSize({width:1440,height:900});
  await prepared(page);
  const adjacent = await page.evaluate(() => {
    const welcome = document.querySelector('#welcome');
    const purpose = document.querySelector('.landing-purpose');
    const r = welcome.getBoundingClientRect(), p = purpose.getBoundingClientRect();
    return { adjacent: welcome.nextElementSibling === purpose, gap: p.top - r.bottom };
  });
  expect(adjacent.adjacent).toBe(true);
  expect(adjacent.gap).toBeLessThanOrEqual(32);
});

test('mobile example action matches the landing content width', async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await prepared(page);
  const widths = await page.evaluate(() => {
    const button = document.querySelector('#welcome .example-question').getBoundingClientRect();
    const content = document.querySelector('#welcome .hero-left').getBoundingClientRect();
    return { button: button.width, content: content.width };
  });
  expect(Math.abs(widths.button - widths.content)).toBeLessThanOrEqual(1);
});

test('exact example figures and definitions remain available through keyboard disclosure', async({page})=>{
  await prepared(page);
  const detail=page.locator('.dallas-evidence');
  await expect(detail).not.toHaveAttribute('open','');
  await detail.locator('summary').focus();
  await page.keyboard.press('Enter');
  await expect(detail).toHaveAttribute('open','');
  for(const exact of ['3,319,208,715','1,092,607,589','766,316,261','500,174,938','960,109,927','139,776'])
    await expect(detail).toContainText(exact);
  await expect(detail).toContainText(/11, 12, (and )?13/);
  await expect(detail).toContainText('6600');
  await expect(detail).toContainText('6500');
  await expect(detail).toContainText(/remaining|minus/i);
});

test('chart, provenance and inline chat access remain unobstructed while scrolling', async ({page})=>{
  await page.setViewportSize({width:390,height:844});
  await prepared(page);
  for(const selector of ['.dallas-grid','.landing-caption','#ask-your-own']) {
    await page.locator(selector).scrollIntoViewIfNeeded();
    const obstruction = await page.locator(selector).evaluate(node=>{
      const r=node.getBoundingClientRect(),fab=document.querySelector('.ta-fab');
      const f=fab.getBoundingClientRect();
      const intersects=getComputedStyle(fab).display!=='none' && f.right>r.left && f.left<r.right && f.bottom>r.top && f.top<r.bottom;
      const x=(r.left+r.right)/2,y=Math.max(1,Math.min(innerHeight-1,(r.top+r.bottom)/2));
      const hit=document.elementFromPoint(x,y);
      return {intersects,hit:hit===node || node.contains(hit)};
    });
    expect(obstruction).toEqual({intersects:false,hit:true});
  }
  await page.locator('#ask-your-own').click();
  await expect(page.locator('.ta-wrap')).toBeVisible();
});

test('keyboard dismissal, focus trap, and reopening preserve the conversation', async ({page}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await prepared(page);
  await ask(page);
  const chat = page.locator('.ta-wrap');
  await expect(chat.locator('.ta-chart')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(chat).toBeHidden();
  await expect(await chatOpener(page)).toBeFocused();
  await openChat(page);
  await expect(chat.locator('.ta-chart')).toBeVisible();
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
  await expect(await chatOpener(page)).toBeFocused();
});

test('setup anchor remains usable for a returning district reader', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  await prepared(page,{url:'/?d=057905#chatgpt-setup'});
  await expect(page.locator('#welcome')).toBeHidden();
  await expect(page.locator('#chatgpt-setup')).toBeVisible();
  await expect(page.locator('#chatgpt-setup')).toContainText('Add custom MCP server');
});

test('single setup disclosure toggles with keyboard and hash navigation opens it', async ({page}) => {
  await prepared(page);
  const guide = page.locator('#chatgpt-setup');
  await expect(guide).not.toHaveAttribute('open', '');
  const action = guide.locator(':scope > summary');
  await action.focus();
  await page.keyboard.press('Enter');
  await expect(guide.locator('.setup-body')).toBeVisible();
  await guide.locator(':scope > summary').focus();
  await page.keyboard.press('Enter');
  await expect(guide.locator('.setup-body')).toBeHidden();
  await page.evaluate(()=>{ location.hash='chatgpt-setup'; });
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
    await expect(chat.locator('.ta-chart')).toBeVisible();
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
  await expect(chat.locator('.ta-chart')).toBeVisible();
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
  await expect(chat.locator('.ta-example-head')).toContainText('Recorded example');
  await expect(chat.locator('.ta-example-stage')).toHaveCount(3);
  await expect(chat.locator('.ta-example-match')).toContainText('057905');
  await expect(chat.locator('.ta-example-stack i')).toHaveCount(4);
  const exampleShares=await chat.locator('.ta-example-stack i').evaluateAll(nodes=>
    nodes.map(n=>n.getBoundingClientRect().width/n.parentElement.getBoundingClientRect().width*100));
  [32.9177,23.0873,15.0691,28.9259].forEach((share,index)=>
    expect(Math.abs(exampleShares[index]-share)).toBeLessThan(.7));
  await expect(chat.locator('.ta-empty')).toContainText(/TEA PEIMS.*FY 2025 all funds/);
  await expect(chat.locator('.ta-empty')).toContainText(/Classroom: \$1\.093B.*32\.9%/);
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
  await expect(page.locator('.ta-chart')).toBeVisible();
  expect(audit.paidRequests).toHaveLength(1);
  await page.locator('.ta-x').click();
  await page.route('**/static/ask.js',route=>route.fulfill({contentType:'application/javascript',body:'/* unavailable widget */'}));
  await page.reload();
  await page.locator('#question').fill('Where does Dallas ISD school money go?');
  await page.locator('#askbtn').click();
  await expect(page.locator('#answer')).toContainText(/Dallas|3.32/);
  expect(audit.paidRequests).toHaveLength(2);
});

test('dark theme preserves readable landing and chat at every target width', async ({page}, info) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  for (const width of [320,390,430,1440]) {
    await page.setViewportSize({width,height:width === 1440 ? 900 : 844});
    const audit = await prepared(page,{theme:'dark'});
    await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
    await page.screenshot({path:path.join(evidence,`${info.project.name}-landing-dark-${width}.png`)});
    await checkAA(page,[['#welcome'],['.landing-purpose'],['#chatgpt-setup']]);
    await ask(page);
    await expect(page.locator('.ta-chart')).toBeVisible();
    await page.screenshot({path:path.join(evidence,`${info.project.name}-chat-dark-${width}.png`)});
    await checkAA(page,[['.ta-wrap']]);
    expect(audit.errors).toEqual([]);
  }
});

test('closing a loading chat cancels it and never moves focus into hidden controls', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  await prepared(page,{query:route=>new Promise(resolve=>setTimeout(()=>resolve(route.fulfill({contentType:'application/json',body:JSON.stringify(answer)}).catch(()=>{})),800))});
  await ask(page);
  await page.keyboard.press('Escape');
  await expect(page.locator('.ta-wrap')).toBeHidden();
  await expect(await chatOpener(page)).toBeFocused();
  await page.waitForTimeout(950);
  await expect(await chatOpener(page)).toBeFocused();
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
  await expect(page.locator('.ta-chart')).toBeVisible();
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

test('currency answer puts an exact visual before optional complete evidence', async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await page.emulateMedia({reducedMotion:'reduce'});
  const longLead = 'Classroom teaching was the largest featured category. This second sentence remains available with the complete explanation.';
  const supplied = structuredClone(answer);
  supplied.structured.lead = longLead;
  supplied.structured.lead_runs = [{t:longLead}];
  supplied.structured.blocks[0].rows.push(['Total spending', '$3,319,208,715']);
  supplied.structured.blocks.push({type:'paragraph',runs:[{t:'Additional supplied explanation remains available.'}]});
  await prepared(page,{query:r=>r.fulfill({contentType:'application/json',body:JSON.stringify(supplied)})});
  const chat = await ask(page);
  await expect(chat.locator('.ta-chart')).toBeVisible();
  const bars = await chat.locator('.ta-chart-bar').evaluateAll(nodes=>nodes.map(n=>({
    value:Number(n.dataset.value),width:n.getBoundingClientRect().width
  })));
  const values = answer.structured.blocks[0].rows.map(row=>Number(row[1].replace(/[$,]/g,'')));
  expect(bars.map(bar=>bar.value)).toEqual(values);
  bars.forEach((bar,index)=>expect(Math.abs(bar.width / bars[0].width - values[index]/values[0])).toBeLessThan(0.01));
  await expect(chat.locator('.ta-lead')).toHaveText('Classroom teaching was the largest featured category.');
  await expect(chat.locator('.ta-lead')).not.toContainText('second sentence');
  const evidenceDetails = chat.locator('.ta-evidence').first();
  await expect(evidenceDetails).not.toHaveAttribute('open','');
  await expect(evidenceDetails.locator('summary')).toContainText('5 rows');
  await evidenceDetails.locator('summary').click();
  await expect(evidenceDetails.locator('tbody tr')).toHaveCount(5);
  for(const row of supplied.structured.blocks[0].rows) await expect(evidenceDetails).toContainText(row[1]);
  const support = chat.locator('.ta-support');
  await support.locator('summary').click();
  await expect(support).toContainText(longLead);
  await expect(support).toContainText('Additional supplied explanation remains available.');
  await expect(support.getByRole('link',{name:'TEA PEIMS actual finance'})).toHaveAttribute('href','/sources');
});

for(const [name,head,rows] of [
  ['ambiguous unit',['Category','Value'],[['Teaching','100'],['Buildings','50']]],
  ['mixed currencies',['Category','Dollars'],[['Teaching','$100'],['Buildings','\u00a350']]],
  ['malformed number',['Category','Dollars'],[['Teaching','$1,00'],['Buildings','$50']]],
  ['missing value',['Category','Dollars'],[['Teaching','$100'],['Buildings','']]],
  ['negative value',['Category','Dollars'],[['Teaching','$100'],['Buildings','-$50']]],
  ['mixed unit text',['Category','Dollars'],[['Teaching','$100 per student'],['Buildings','$50']]],
  ['contradictory header unit',['Category','Amount (EUR)'],[['Teaching','$100'],['Buildings','$50']]],
  ['unsupported scale',['Category','Dollars in millions'],[['Teaching','$100'],['Buildings','$50']]],
  ['unsupported third column',['Category','Dollars','Year'],[['Teaching','$100','2025'],['Buildings','$50','2025']]],
]) {
  test(`${name} retains the table without an invented financial visual`, async ({page})=>{
    await page.emulateMedia({reducedMotion:'reduce'});
    const supplied = structuredClone(answer);
    supplied.structured.blocks = [{type:'table',head,rows}];
    await prepared(page,{query:r=>r.fulfill({contentType:'application/json',body:JSON.stringify(supplied)})});
    const chat = await ask(page);
    await expect(chat.locator('.ta-lead')).toBeVisible();
    await expect(chat.locator('.ta-chart')).toHaveCount(0);
    const disclosure = chat.locator('.ta-evidence');
    if(await disclosure.count()) await disclosure.first().locator('summary').click();
    await expect(chat.locator('tbody tr')).toHaveCount(rows.length);
    for(const row of rows) for(const value of row) if(value) await expect(chat.locator('.ta-tb')).toContainText(value);
  });
}

test('a currency table without district, year, scope or source context stays a table',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});
  const supplied=structuredClone(answer);
  delete supplied.structured.figures;
  supplied.structured.sources=[];
  await prepared(page,{query:r=>r.fulfill({contentType:'application/json',body:JSON.stringify(supplied)})});
  const chat=await ask(page);
  await expect(chat.locator('.ta-lead')).toBeVisible();
  await expect(chat.locator('.ta-chart')).toHaveCount(0);
  await expect(chat.locator('tbody tr')).toHaveCount(4);
  await expect(chat.locator('.ta-thread')).not.toContainText('undefined');
});

test('eligible visual keeps district, year and scope visible even without figure cards',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});
  const supplied=structuredClone(answer);
  supplied.structured.figures.cards=[];
  await prepared(page,{query:r=>r.fulfill({contentType:'application/json',body:JSON.stringify(supplied)})});
  const chat=await ask(page);
  await expect(chat.locator('.ta-chart')).toBeVisible();
  await expect(chat.locator('.ta-context')).toBeVisible();
  await expect(chat.locator('.ta-context')).toContainText('Dallas ISD');
  await expect(chat.locator('.ta-context')).toContainText('2025');
  await expect(chat.locator('.ta-context')).toContainText('All funds');
});

test('new landing, setup and chat controls meet automated WCAG AA checks', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  await prepared(page);
  await page.locator('#chatgpt-setup > summary').click();
  await checkAA(page,[['#welcome'],['.landing-purpose'],['#chatgpt-setup']]);
  await ask(page);
  await expect(page.locator('.ta-chart')).toBeVisible();
  await checkAA(page,[['.ta-wrap']]);
});
