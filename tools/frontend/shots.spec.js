// Знімки сторінок для порівняння з дизайном (docs/frontend/design/).
// Запуск: сервер `python manage.py runserver`, потім `npm run shots` у tools/frontend.
const { test } = require('@playwright/test');

const PAGES = [
  ['home', '/'],
  ['ui-tokens', '/ui/tokens/'],
  ['ui-kit', '/ui/kit/'],
];

for (const [name, url] of PAGES) {
  test(name, async ({ page }, info) => {
    await page.goto(url);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: `shots/${name}-${info.project.name}.png`, fullPage: true });
  });
}
