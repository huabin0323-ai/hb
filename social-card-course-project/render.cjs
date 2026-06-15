const { chromium } = require('playwright');
const path = require('path');

const TASK_DIR = __dirname;
const HTML_FILE = `file://${path.join(TASK_DIR, 'index.html')}`;

const targets = [
  ['#xhs-01-wrong', '图一_课设白写.png'],
  ['#xhs-02-right', '图二_课设变项目.png'],
];

(async () => {
  const browser = await chromium.launch({ channel: 'msedge' });
  const page = await browser.newPage({ viewport: { width: 1200, height: 1600 } });

  await page.goto(HTML_FILE, { waitUntil: 'networkidle' });
  // Wait for WebGL canvas + fonts
  await page.waitForTimeout(1200);

  for (const [selector, filename] of targets) {
    const el = await page.$(selector);
    if (!el) {
      console.error(`ERROR: selector "${selector}" not found`);
      continue;
    }
    const outPath = path.join(TASK_DIR, 'output', filename);
    await el.screenshot({ path: outPath, type: 'png' });
    console.log(`OK: ${outPath}`);
  }

  await browser.close();
  console.log('Done.');
})();
