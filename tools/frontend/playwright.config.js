// Візуальні тести фронтенду (фаза 19). Запуск: `make frontend-test` у корені репозиторію
// (готує окрему базу, юніт-тести JS, потім цей прогін). Еталони — docs/frontend/baseline/.
const path = require('path');
const { defineConfig } = require('@playwright/test');

const ROOT = path.resolve(__dirname, '../..');
const PORT = Number(process.env.UI_PORT || 8765);
const PYTHON = process.env.PYTHON || 'python';
const DB_PATH = process.env.DB_PATH || path.join(__dirname, 'ui.sqlite3');

module.exports = defineConfig({
  testDir: '.',
  testMatch: '*.spec.js',
  outputDir: 'test-results',
  // Еталони окремо для кожної ОС: шрифти Windows і Linux рендеряться по-різному.
  snapshotPathTemplate: path.join(ROOT, 'docs/frontend/baseline/{arg}-{projectName}-{platform}{ext}'),
  // Локально відсутній еталон створюється сам; у CI відсутній еталон — помилка.
  updateSnapshots: process.env.CI ? 'none' : 'missing',
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.01, animations: 'disabled' } },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    reducedMotion: 'reduce',            // без пульсу, конфеті й появ — знімки стабільні
    locale: 'uk-UA',
  },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
  webServer: {
    command: `${PYTHON} manage.py runserver 127.0.0.1:${PORT} --noreload`,
    cwd: ROOT,
    env: { ...process.env, DB_PATH },
    url: `http://127.0.0.1:${PORT}/accounts/login/`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
