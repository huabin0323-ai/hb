const { chromium } = require('playwright');
const path = require('path');

const args = process.argv.slice(2);
const htmlPath = args[0];
const outPath = args[1];

if (!htmlPath || !outPath) {
  console.error('Usage: node render.cjs <html-file> <output-png>');
  process.exit(1);
}

(async () => {
  const browser = await chromium.launch({ channel: 'msedge' });
  const page = await browser.newPage({ viewport: { width: 1080, height: 800 } });

  const htmlUrl = `file://${path.resolve(htmlPath)}`;
  // 用 'load' 不用 'networkidle'，避免外部字体加载超时
  await page.goto(htmlUrl, { waitUntil: 'load', timeout: 30000 });
  // 给字体和渲染更多时间
  await page.waitForTimeout(2000);

  // 全页截图 — 高度自适应
  const body = await page.$('.page');
  if (body) {
    await body.screenshot({ path: outPath, type: 'png', fullPage: false });
    console.log(`OK: ${outPath}`);
  } else {
    await page.screenshot({ path: outPath, type: 'png', fullPage: true });
    console.log(`OK (fullPage fallback): ${outPath}`);
  }

  await browser.close();
  console.log('Done.');
})();
