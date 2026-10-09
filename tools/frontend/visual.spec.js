// Візуальна регресія (фаза 19): 6 екранів × 2 розміри проти еталонів у docs/frontend/baseline/.
// Дані: мапа й гра — моки (?mock=demo, ?mock=1), решта — демо-база tools/frontend/seed_ui.py
// (урок id=1). Оновити еталони після навмисної зміни дизайну: `make frontend-baseline`.
const { test, expect } = require('@playwright/test');

async function ready(page) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForLoadState('networkidle');
}

const SCREENS = [
  ['world', '/?mock=demo'],
  ['map', '/grades/5/?mock=demo'],
  ['lesson', '/items/1/'],
  ['play', '/play/item/1/?mock=1'],
  ['login', '/accounts/login/'],
];

for (const [name, url] of SCREENS) {
  test(name, async ({ page }) => {
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto(url);
    await ready(page);
    await expect(page).toHaveScreenshot(`${name}.png`, { fullPage: name === 'lesson' });
    expect(errors, 'помилки JS на сторінці').toEqual([]);
  });
}

test('finish', async ({ page }) => {
  // Повний прохід мок-уроку: 3 авто-завдання (одне вже розв’язане) + ШІ-задача → фінал.
  await page.goto('/play/item/1/?mock=1');
  await ready(page);
  const main = page.locator('#mainBtn');
  for (const answer of ['13', '81']) {
    await page.fill('#answer', answer);
    await page.keyboard.press('Enter');
    await expect(main).toHaveText('Далі');                    // правильно → «Далі» у фокусі
    await page.keyboard.press('Enter');
  }
  await page.fill('#answer', 'x + x + 7 = 25, x = 9: KN = 9 см, MK = 16 см');
  await main.click();
  await expect(main).toHaveText('Далі');
  await main.click();
  await page.click('#skipBtn');                               // розв’язане раніше — пропустити
  await expect(page.locator('.finish__title')).toHaveText('Урок пройдено!');
  await expect(page).toHaveScreenshot('finish.png');
});
