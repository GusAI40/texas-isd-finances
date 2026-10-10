const {test,expect}=require('@playwright/test');
const {installPublicFixtures,cleanState}=require('./public-fixtures');
const health=require('./fixtures/current-public-health.json');

test('landing names the provider from recorded production health',async({page})=>{
  await cleanState(page);await installPublicFixtures(page);
  await page.goto('/');
  expect(health.payload.revision).toBe('14326baf497f782db702f12427d6432af1df46be');
  expect(health.payload.llm).toContain('deepseek:deepseek-v4-flash');
  await expect(page.locator('#ask-model')).toContainText(/DeepSeek.*deepseek-v4-flash/i);
  await expect(page.locator('#ask-model')).not.toContainText('OpenAI');
});

test('missing health leaves a neutral provider label',async({page})=>{
  await cleanState(page);await installPublicFixtures(page);
  await page.route('**/health',r=>r.fulfill({status:503,contentType:'application/json',body:'{"detail":"Unavailable"}'}));
  await page.goto('/');
  await expect(page.locator('#ask-model')).toHaveText('the configured AI model');
  await expect(page.locator('#ask-model')).not.toContainText(/OpenAI|DeepSeek/);
});
