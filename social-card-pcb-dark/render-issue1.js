const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

(async () => {
  // Ensure output directory exists
  const outDir = 'D:/hb/social-card-pcb-dark/output/issue1';
  if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir, { recursive: true });
  }

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1440 } });

  const htmlPath = 'file:///' + path.resolve('D:/hb/social-card-pcb-dark/issue1.html').replace(/\\/g, '/');
  console.log('Loading:', htmlPath);
  await page.goto(htmlPath, { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(3000);

  const cards = await page.$$('.card');
  console.log(`Found ${cards.length} cards`);

  for (let i = 0; i < cards.length; i++) {
    const num = String(i + 1).padStart(2, '0');
    const outPath = path.join(outDir, `page-${num}.png`);
    await cards[i].screenshot({ path: outPath });
    console.log(`  page-${num}.png rendered`);
  }

  await browser.close();
  console.log('Done. All 5 pages rendered to', outDir);
})();
