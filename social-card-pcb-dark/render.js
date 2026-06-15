const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1440 } });

  const htmlPath = 'file:///' + path.resolve('D:/hb/social-card-pcb-dark/index.html').replace(/\\/g, '/');
  await page.goto(htmlPath, { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(3000);

  // Screenshot just the .poster.xhs element
  const poster = await page.$('.card');
  if (poster) {
    await poster.screenshot({ path: 'D:/hb/social-card-pcb-dark/output/page-01-cover.png' });
    console.log('Cover rendered: 1080x1440');
  } else {
    console.log('Poster element not found, taking full page screenshot');
    await page.screenshot({ path: 'D:/hb/social-card-pcb-dark/output/page-01-cover.png', fullPage: true });
  }

  await browser.close();
})();
