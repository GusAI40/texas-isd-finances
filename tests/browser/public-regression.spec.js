const { test, expect } = require('@playwright/test');

for (const viewport of [{ width: 1440, height: 900 }, { width: 768, height: 1024 }, { width: 390, height: 844 }]) {
  test(`public landing retains finder and statewide visual at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.goto('/');
    await expect(page.locator('#search')).toBeVisible();
    await expect(page.locator('#welcome-fig')).toBeVisible();
    await expect(page.locator('#hero-fig')).toBeVisible();
    expect(errors).toEqual([]);
  });
}
