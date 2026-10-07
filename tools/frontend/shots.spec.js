const { test } = require('@playwright/test');

test('home', async ({ page }, info) => {
  await page.goto('/');
  await page.screenshot({ path: `shots/home-${info.project.name}.png`, fullPage: true });
});