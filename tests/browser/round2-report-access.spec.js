/* Recorded data only: the integration contract for disclosed finance chapters. */
const {test,expect}=require('@playwright/test');
const {installPublicFixtures,cleanState,waitForDashboard}=require('./public-fixtures');
const available=['kpi-section','dollar-section','outcomes-section','econ-section','equity-section','bond-section','insights-section','trend-section','peers-section','money-section','object-section','program-section','flags-section'];
async function prepare(page,url='/?d=057905'){
 await page.emulateMedia({reducedMotion:'reduce'});await cleanState(page);await installPublicFixtures(page);await page.goto(url);await waitForDashboard(page);
}
for(const width of [320,390,430,1440])for(const theme of ['light','dark']){
 test(`expanded chart tooltip stays in the ${width}px ${theme} viewport after hover and scroll`,async({page})=>{
  await page.setViewportSize({width,height:844});await page.emulateMedia({reducedMotion:'reduce'});
  await cleanState(page,theme);await installPublicFixtures(page);await page.goto('/?d=057905');await waitForDashboard(page);
  await page.evaluate(()=>{for(const d of document.querySelectorAll('#dash details,.report-details'))if(d.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))d.open=true;dispatchEvent(new Event('resize'));});
  await page.locator('#econ-levers [data-tip]').first().hover();
  const tip=page.locator('.econ-tip');await expect(tip).toHaveCSS('opacity','1');
  const bounds=await tip.boundingBox();expect(bounds.x).toBeGreaterThanOrEqual(0);expect(bounds.x+bounds.width).toBeLessThanOrEqual(width);
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.mouse.move(0,0);await page.evaluate(()=>scrollTo(0,document.documentElement.scrollHeight));
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 });
}
for(const [width,height] of [[320,740],[390,844],[430,932],[1440,900]])for(const selected of [false,true]){
 test(`${selected?'selected':'landing'} opening viewport contains real data at ${width}px`,async({page})=>{
  await page.setViewportSize({width,height});
  if(selected)await prepare(page);
  else{await page.emulateMedia({reducedMotion:'reduce'});await cleanState(page);await installPublicFixtures(page);await page.goto('/');await expect(page.locator('#welcome-h')).toBeVisible();}
  const selectors=selected?'.pennies i,#trendchart polyline,#peerchart rect':'.dallas-grid i,.dallas-fill';
  await expect.poll(()=>page.locator(selectors).evaluateAll(es=>es.some(e=>{
   const r=e.getBoundingClientRect();return e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})&&r.width>0&&r.height>0&&r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth;
  })),{timeout:3000}).toBe(true);
 });
}

test('default district overview retains actual allocation, history and peer comparison',async({page})=>{
 await page.setViewportSize({width:390,height:844});await prepare(page);
 for(const id of ['dollar-section','trend-section','peers-section'])await expect(page.locator('#'+id)).toBeVisible();
 for(const id of ['trendchart','peerchart'])expect(await page.locator('#'+id).evaluate(e=>e.viewBox.baseVal.width>0&&e.querySelectorAll('path,rect,circle,line').length>0)).toBe(true);
 for(const id of available)await expect(page.locator('#'+id)).toBeAttached();
 await expect(page.locator('#takeover-section')).toBeHidden();await expect(page.locator('#turnaround-section')).toBeHidden();
});
test('primary report chapters start open and remain keyboard accessible',async({page})=>{
 await prepare(page);
 const details=page.locator('details.report-details');expect(await details.count()).toBeGreaterThan(0);
 for(const detail of await details.all()){
  await expect(detail).toHaveAttribute('open','');
  await detail.locator(':scope > summary').focus();await page.keyboard.press('Enter');await expect(detail).not.toHaveAttribute('open','');
  await page.keyboard.press('Enter');await expect(detail).toHaveAttribute('open','');
 }
 for(const id of available)await expect(page.locator('#'+id)).toBeVisible();
 for(const id of ['moneychart','objchart','progchart','eq-bars','bond-timeline'])expect(await page.locator('#'+id).evaluate(e=>e.viewBox.baseVal.width>0&&e.querySelectorAll('path,rect,circle,line').length>0)).toBe(true);
 await page.setViewportSize({width:320,height:740});await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
for(const id of ['money-section','econ-section','bond-section'])test(`direct ${id} hash opens the ancestor chapter`,async({page})=>{
 await prepare(page,'/?d=057905#'+id);await expect(page.locator('#'+id)).toBeVisible();
 expect(await page.locator('#'+id).evaluate(e=>{for(let p=e.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS'&&!p.open)return false;return true})).toBe(true);
 await expect(page).toHaveURL(new RegExp('d=057905.*#'+id));
});
test('native hash navigation and back retain selection and reveal the target',async({page})=>{
 await prepare(page);await page.evaluate(()=>{location.hash='money-section'});await expect(page.locator('#money-section')).toBeVisible();
 await page.evaluate(()=>{location.hash='econ-section'});await expect(page.locator('#econ-section')).toBeVisible();
 await page.goBack();await expect(page).toHaveURL(/d=057905.*#money-section/);await expect(page.locator('#money-section')).toBeVisible();
 await expect(page.locator('#dname')).toContainText(/Dallas/i);
});
test('print expansion preserves available chapters and restores disclosure state',async({page})=>{
 await prepare(page);const before=await page.locator('details.report-details').evaluateAll(es=>es.map(e=>e.open));
 await page.evaluate(()=>dispatchEvent(new Event('beforeprint')));
 for(const id of available)await expect(page.locator('#'+id)).toBeVisible();
 await expect(page.locator('#takeover-section')).toBeHidden();
 await page.evaluate(()=>dispatchEvent(new Event('afterprint')));
 expect(await page.locator('details.report-details').evaluateAll(es=>es.map(e=>e.open))).toEqual(before);
});
test('peer spending averages stay separate from the selected fiscal-year record',async({page})=>{
 await prepare(page);
 const spending=page.locator('#econ-peers .peer-spending-comparison');
 await expect(spending.locator('h4')).toHaveText('Matched peers: operating dollars per student');
 await expect(spending.locator('.peer-panel-basis')).toContainText('TEA Snapshot');
 await expect(spending.locator('.peer-panel-basis')).toContainText(/available 2022.2024 records/);
 await expect(spending.locator('.peer-panel-basis')).toContainText('Available years may vary');
 expect(await spending.locator('.rank-row.you').count()).toBe(0);
 expect(await spending.locator('.rank-row').count()).toBeGreaterThan(0);
 await expect(spending.locator('.selected-peer-context')).toBeVisible();
 await expect(spending.locator('.selected-peer-context')).toContainText('FY 2025');
 await expect(spending.locator('.selected-peer-context')).toContainText('TEA PEIMS');
 await expect(spending.locator('.selected-peer-context')).toContainText('$14,210');
 await expect(spending.locator('.selected-peer-context')).toContainText('separate context');
 await expect(page.locator('#econ-peers-support')).toContainText('emergent-bilingual');
 await expect(page.locator('#econ-peers .peer-panel').first()).toContainText('Multi-year average');
 const records=page.locator('#econ-peers details.reference-table');
 await records.locator('summary').click();
 await expect(records.locator('caption')).toContainText('Selected enrollment and operating spending are FY 2025 PEIMS');
 await expect(records.locator('caption')).toContainText('selected poverty and turnover are Snapshot averages');
});
