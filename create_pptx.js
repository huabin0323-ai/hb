const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "张雅馨";
pres.title = "梯次利用电池在用户侧储能项目的投资效益与政策建议研究";

// === Color Palette ===
const C = {
  navy: "1A365D",
  medBlue: "2C5282",
  accent: "3182CE",
  lightBg: "EBF4FF",
  white: "FFFFFF",
  dark: "1A202C",
  muted: "4A5568",
  lightGray: "E2E8F0",
  green: "2F855A",
  orange: "C05621",
  red: "C53030",
  gold: "B7791F",
};

// === Helper functions ===
const makeShadow = () => ({ type: "outer", blur: 4, offset: 2, angle: 135, color: "000000", opacity: 0.08 });

// Section divider helper: a thin accent bar under title
function addTitleBar(slide, y) {
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: y, w: 0.8, h: 0.06, fill: { color: C.accent } });
}

// === Slide 1: Title Slide ===
{
  const slide = pres.addSlide();
  slide.background = { color: C.navy };

  // Top decorative line
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.08, fill: { color: C.accent } });

  // School name
  slide.addText("上海电力大学 · 经济与管理学院", {
    x: 1, y: 0.6, w: 8, h: 0.5, fontSize: 14, fontFace: "Microsoft YaHei",
    color: "A0C4E8", align: "center", margin: 0,
  });

  // Title
  slide.addText("梯次利用电池在用户侧储能项目的\n投资效益与政策建议研究", {
    x: 0.8, y: 1.6, w: 8.4, h: 1.8, fontSize: 30, fontFace: "Microsoft YaHei",
    color: C.white, bold: true, align: "center", valign: "middle", margin: 0,
  });

  // Decorative separator
  slide.addShape(pres.shapes.RECTANGLE, { x: 3.5, y: 3.6, w: 3, h: 0.03, fill: { color: C.accent } });

  // Info
  slide.addText([
    { text: "答辩人：张雅馨", options: { breakLine: true } },
    { text: "专  业：能源服务工程 2022级", options: { breakLine: true } },
    { text: "指导教师：孙波", options: { breakLine: true } },
    { text: "2026年4月", options: {} },
  ], {
    x: 1.5, y: 3.9, w: 7, h: 1.3, fontSize: 15, fontFace: "Microsoft YaHei",
    color: "B0C8E0", align: "center", lineSpacingMultiple: 1.5, margin: 0,
  });

  // Bottom line
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 5.545, w: 10, h: 0.08, fill: { color: C.accent } });
}

// === Slide 2: Table of Contents ===
{
  const slide = pres.addSlide();
  slide.background = { color: C.white };

  slide.addText("汇报提纲", {
    x: 0.6, y: 0.35, w: 5, h: 0.55, fontSize: 28, fontFace: "Microsoft YaHei",
    color: C.navy, bold: true, margin: 0,
  });
  addTitleBar(slide, 0.95);
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.15, w: 8.8, h: 0.015, fill: { color: C.lightGray } });

  const tocItems = [
    ["01", "研究背景与意义"],
    ["02", "国内外研究综述"],
    ["03", "产业链与市场现状"],
    ["04", "投资效益模型构建"],
    ["05", "实证分析与结果"],
    ["06", "敏感性分析"],
    ["07", "政策建议"],
    ["08", "研究结论"],
  ];

  tocItems.forEach((item, i) => {
    const col = i < 4 ? 0 : 1;
    const row = i % 4;
    const x = col === 0 ? 0.8 : 5.2;
    const y = 1.5 + row * 0.95;

    // Number circle
    slide.addShape(pres.shapes.OVAL, { x: x, y: y + 0.05, w: 0.45, h: 0.45, fill: { color: C.accent } });
    slide.addText(item[0], {
      x: x, y: y + 0.05, w: 0.45, h: 0.45, fontSize: 13, fontFace: "Arial",
      color: C.white, bold: true, align: "center", valign: "middle", margin: 0,
    });

    // Item text
    slide.addText(item[1], {
      x: x + 0.6, y: y + 0.05, w: 3.2, h: 0.45, fontSize: 15, fontFace: "Microsoft YaHei",
      color: C.dark, align: "left", valign: "middle", margin: 0,
    });
  });
}

// === Slide 3: Research Background ===
{
  const slide = pres.addSlide();
  slide.background = { color: C.white };

  slide.addText("一、研究背景与意义", {
    x: 0.6, y: 0.35, w: 6, h: 0.55, fontSize: 26, fontFace: "Microsoft YaHei",
    color: C.navy, bold: true, margin: 0,
  });
  addTitleBar(slide, 0.95);
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.1, w: 8.8, h: 0.015, fill: { color: C.lightGray } });

  // Left column - background
  slide.addText("研究背景", {
    x: 0.6, y: 1.3, w: 4.2, h: 0.4, fontSize: 18, fontFace: "Microsoft YaHei",
    color: C.medBlue, bold: true, margin: 0,
  });

  slide.addText([
    { text: `全球能源转型与“双碳”目标驱动`, options: { bold: true, breakLine: true, fontSize: 14 } },
    { text: "截至2024年底，新能源汽车保有量达3140万辆", options: { breakLine: true, fontSize: 13 } },
    { text: "预计2030年退役动力电池超350万吨", options: { breakLine: true, fontSize: 13 } },
    { text: "2026-2029年将迎来退役高潮", options: { breakLine: true, fontSize: 13 } },
    { text: "电池容量衰减至80%时需退役", options: { breakLine: true, fontSize: 13 } },
    { text: "梯次利用可将退役电池用于储能等场景", options: { breakLine: true, fontSize: 13 } },
  ], {
    x: 0.6, y: 1.75, w: 4.2, h: 2.8, fontSize: 13, fontFace: "Microsoft YaHei",
    color: C.muted, paraSpaceAfter: 6, margin: 0,
  });

  // Right column - significance
  slide.addText("研究意义", {
    x: 5.3, y: 1.3, w: 4.2, h: 0.4, fontSize: 18, fontFace: "Microsoft YaHei",
    color: C.medBlue, bold: true, margin: 0,
  });

  // Theory card
  slide.addShape(pres.shapes.RECTANGLE, { x: 5.3, y: 1.85, w: 4.2, h: 1.4, fill: { color: C.lightBg }, shadow: makeShadow() });
  slide.addShape(pres.shapes.RECTANGLE, { x: 5.3, y: 1.85, w: 0.07, h: 1.4, fill: { color: C.accent } });
  slide.addText([
    { text: "理论意义", options: { bold: true, breakLine: true, fontSize: 14 } },
    { text: `将废弃电池重新定义为“资源”，丰富“产品全生命周期管理”与“循环经济闭环”理论的产业实践`, options: { fontSize: 12 } },
  ], {
    x: 5.55, y: 1.9, w: 3.8, h: 1.3, fontSize: 12, fontFace: "Microsoft YaHei",
    color: C.muted, paraSpaceAfter: 4, margin: 0,
  });

  // Practice card
  slide.addShape(pres.shapes.RECTANGLE, { x: 5.3, y: 3.5, w: 4.2, h: 1.4, fill: { color: C.lightBg }, shadow: makeShadow() });
  slide.addShape(pres.shapes.RECTANGLE, { x: 5.3, y: 3.5, w: 0.07, h: 1.4, fill: { color: C.accent } });
  slide.addText([
    { text: "实践意义", options: { bold: true, breakLine: true, fontSize: 14 } },
    { text: "为投资者测算IRR与回收期；为政策制定者（发改委、能源局、工信部）制定产业政策提供关键参考", options: { fontSize: 12 } },
  ], {
    x: 5.55, y: 3.55, w: 3.8, h: 1.3, fontSize: 12, fontFace: "Microsoft YaHei",
    color: C.muted, paraSpaceAfter: 4, margin: 0,
  });
}

// === Slide 4: Literature Review ===
{
  const slide = pres.addSlide();
  slide.background = { color: C.white };

  slide.addText("二、国内外研究综述", {
    x: 0.6, y: 0.35, w: 6, h: 0.55, fontSize: 26, fontFace: "Microsoft YaHei",
    color: C.navy, bold: true, margin: 0,
  });
  addTitleBar(slide, 0.95);
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.1, w: 8.8, h: 0.015, fill: { color: C.lightGray } });

  // Domestic
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.3, w: 4.1, h: 0.42, fill: { color: C.medBlue } });
  slide.addText("国内研究进展", {
    x: 0.6, y: 1.3, w: 4.1, h: 0.42, fontSize: 14, fontFace: "Microsoft YaHei",
    color: C.white, bold: true, align: "center", valign: "middle", margin: 0,
  });

  slide.addText([
    { text: "技术验证方面：", options: { bold: true, breakLine: true, fontSize: 12 } },
    { text: "退役锂电池以40%容量为终结点，仍可正常工作约800天", options: { breakLine: true, fontSize: 11 } },
    { text: "示范应用方面：", options: { bold: true, breakLine: true, fontSize: 12 } },
    { text: "北京大兴100kWh梯次利用储能示范工程；南京江北13MW梯次储能电站等", options: { breakLine: true, fontSize: 11 } },
    { text: "标准体系方面：", options: { bold: true, breakLine: true, fontSize: 12 } },
    { text: "已着手建立梯次利用动力电池国家标准体系，但安全标准尚需完善", options: { fontSize: 11 } },
  ], {
    x: 0.8, y: 1.85, w: 3.8, h: 2.1, fontSize: 11, fontFace: "Microsoft YaHei",
    color: C.muted, paraSpaceAfter: 6, margin: 0,
  });

  // International
  slide.addShape(pres.shapes.RECTANGLE, { x: 5.3, y: 1.3, w: 4.1, h: 0.42, fill: { color: C.medBlue } });
  slide.addText("国外研究进展", {
    x: 5.3, y: 1.3, w: 4.1, h: 0.42, fontSize: 14, fontFace: "Microsoft YaHei",
    color: C.white, bold: true, align: "center", valign: "middle", margin: 0,
  });

  slide.addText([
    { text: "欧盟：", options: { bold: true, breakLine: true, fontSize: 12 } },
    { text: "2023年施行《电池和废电池法规》，要求2025年回收率达65%，钴/锂/镍回收率分别95%/70%/95%", options: { breakLine: true, fontSize: 11 } },
    { text: "美国：", options: { bold: true, breakLine: true, fontSize: 12 } },
    { text: "通过立法与激励措施推动规范化发展", options: { breakLine: true, fontSize: 11 } },
    { text: "学术研究：", options: { bold: true, breakLine: true, fontSize: 12 } },
    { text: "Lih等提出动力电池储能商业模式；Heymans等研究用户侧参与调峰的可行性", options: { fontSize: 11 } },
  ], {
    x: 5.5, y: 1.85, w: 3.8, h: 2.1, fontSize: 11, fontFace: "Microsoft YaHei",
    color: C.muted, paraSpaceAfter: 6, margin: 0,
  });

  // Gap box at bottom - moved lower to avoid collision
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 4.15, w: 8.8, h: 0.7, fill: { color: "FFF5F5" }, shadow: makeShadow() });
  slide.addText([
    { text: "现有研究不足：", options: { bold: true, fontSize: 12, color: C.red } },
    { text: "用户侧储能精细化投资模型不足 | 关键参数敏感性研究不深入 | 激励政策具体作用路径探讨薄弱", options: { fontSize: 11, color: C.muted } },
  ], {
    x: 0.8, y: 4.2, w: 8.4, h: 0.55, fontSize: 11, fontFace: "Microsoft YaHei",
    color: C.muted, margin: 0,
  });
}

// === Slide 5: Industry Chain ===
{
  const slide = pres.addSlide();
  slide.background = { color: C.white };

  slide.addText("三、产业链与市场现状", {
    x: 0.6, y: 0.35, w: 6, h: 0.55, fontSize: 26, fontFace: "Microsoft YaHei",
    color: C.navy, bold: true, margin: 0,
  });
  addTitleBar(slide, 0.95);
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.1, w: 8.8, h: 0.015, fill: { color: C.lightGray } });

  // Three columns: Upstream / Midstream / Downstream
  const chainData = [
    { title: "上游：供给端", items: "电池生产企业（边角料、不合格品）\n汽车制造商、公交公司\n保险公司、报废车拆解企业\n多渠道形成稳定原料供给", color: C.accent },
    { title: "中游：处理端", items: "行业门槛不高、标准待完善\n参与主体多元、格局分散\n第三方企业凭借灵活模式\n占据当前市场主导地位", color: C.medBlue },
    { title: "下游：利用端", items: "梯次利用：电网储能、\n低速电动车、通信基站等\n再生利用：提取镍钴锂等\n有价金属，完成资源回流", color: C.navy },
  ];

  chainData.forEach((item, i) => {
    const x = 0.6 + i * 3.05;
    // Card
    slide.addShape(pres.shapes.RECTANGLE, { x: x, y: 1.4, w: 2.85, h: 2.7, fill: { color: C.white }, shadow: makeShadow() });
    // Top accent bar
    slide.addShape(pres.shapes.RECTANGLE, { x: x, y: 1.4, w: 2.85, h: 0.06, fill: { color: item.color } });
    // Arrow between cards
    if (i < 2) {
      slide.addText("→", {
        x: x + 2.85, y: 2.4, w: 0.2, h: 0.5, fontSize: 22, fontFace: "Arial",
        color: C.accent, align: "center", valign: "middle", margin: 0,
      });
    }
    slide.addText(item.title, {
      x: x + 0.15, y: 1.6, w: 2.55, h: 0.4, fontSize: 14, fontFace: "Microsoft YaHei",
      color: item.color, bold: true, margin: 0,
    });
    slide.addText(item.items, {
      x: x + 0.15, y: 2.1, w: 2.55, h: 1.8, fontSize: 11, fontFace: "Microsoft YaHei",
      color: C.muted, paraSpaceAfter: 4, margin: 0,
    });
  });

  // Bottom stats
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 4.3, w: 8.8, h: 1.05, fill: { color: C.lightBg }, shadow: makeShadow() });
  slide.addText([
    { text: "市场数据一览", options: { bold: true, breakLine: true, fontSize: 13, color: C.navy } },
    { text: "▸ 2019-2024年动力电池回收量从12.9万吨增至超38万吨    ▸ 截至2024年累计退役量约60万吨", options: { breakLine: true, fontSize: 11 } },
    { text: "▸ 全国回收服务网点10235个    ▸ 2026年4月《新管理办法》施行，具有强制法律约束力", options: { fontSize: 11 } },
  ], {
    x: 0.8, y: 4.35, w: 8.4, h: 0.95, fontSize: 11, fontFace: "Microsoft YaHei",
    color: C.muted, paraSpaceAfter: 4, margin: 0,
  });
}

// === Slide 6: Model Framework ===
{
  const slide = pres.addSlide();
  slide.background = { color: C.white };

  slide.addText("四、投资效益模型构建", {
    x: 0.6, y: 0.35, w: 6, h: 0.55, fontSize: 26, fontFace: "Microsoft YaHei",
    color: C.navy, bold: true, margin: 0,
  });
  addTitleBar(slide, 0.95);
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.1, w: 8.8, h: 0.015, fill: { color: C.lightGray } });

  // Left: model overview
  slide.addText("模型框架", {
    x: 0.6, y: 1.25, w: 4, h: 0.35, fontSize: 16, fontFace: "Microsoft YaHei",
    color: C.medBlue, bold: true, margin: 0,
  });

  slide.addText([
    { text: "研究视角：", options: { bold: true, fontSize: 12 } },
    { text: `"从摇篮到坟墓"全生命周期评价（LCA）`, options: { fontSize: 12, breakLine: true } },
    { text: "对比对象：", options: { bold: true, fontSize: 12 } },
    { text: "梯次利用电池系统 vs 全新电池系统", options: { fontSize: 12, breakLine: true } },
    { text: "功能单位：", options: { bold: true, fontSize: 12 } },
    { text: "1 kWh 梯次利用阶段放电量", options: { fontSize: 12, breakLine: true } },
    { text: "应用场景：", options: { bold: true, fontSize: 12 } },
    { text: "工商业用户侧储能（工业园区/商业建筑）", options: { fontSize: 12, breakLine: true } },
  ], {
    x: 0.6, y: 1.7, w: 4.2, h: 2.4, fontSize: 12, fontFace: "Microsoft YaHei",
    color: C.muted, paraSpaceAfter: 6, margin: 0,
  });

  // Right: two model cards
  // Economic model card
  slide.addShape(pres.shapes.RECTANGLE, { x: 5.3, y: 1.25, w: 4.2, h: 1.9, fill: { color: C.lightBg }, shadow: makeShadow() });
  slide.addShape(pres.shapes.RECTANGLE, { x: 5.3, y: 1.25, w: 0.07, h: 1.9, fill: { color: C.accent } });
  slide.addText("经济效益模型", {
    x: 5.55, y: 1.35, w: 3.8, h: 0.35, fontSize: 14, fontFace: "Microsoft YaHei",
    color: C.medBlue, bold: true, margin: 0,
  });
  slide.addText([
    { text: "NPV = PVB − PVC（净现值）", options: { breakLine: true, fontSize: 12 } },
    { text: "PVC: 全生命周期总成本现值", options: { breakLine: true, fontSize: 11 } },
    { text: "PVB: 全生命周期总收益现值", options: { breakLine: true, fontSize: 11 } },
    { text: "LCOE: 平准化度电成本（元/kWh）", options: { fontSize: 11 } },
  ], {
    x: 5.55, y: 1.75, w: 3.8, h: 1.2, fontSize: 11, fontFace: "Microsoft YaHei",
    color: C.muted, paraSpaceAfter: 4, margin: 0,
  });

  // Environmental model card
  slide.addShape(pres.shapes.RECTANGLE, { x: 5.3, y: 3.4, w: 4.2, h: 1.9, fill: { color: C.lightBg }, shadow: makeShadow() });
  slide.addShape(pres.shapes.RECTANGLE, { x: 5.3, y: 3.4, w: 0.07, h: 1.9, fill: { color: C.green } });
  slide.addText("环境效益模型", {
    x: 5.55, y: 3.5, w: 3.8, h: 0.35, fontSize: 14, fontFace: "Microsoft YaHei",
    color: C.green, bold: true, margin: 0,
  });
  slide.addText([
    { text: "CEtotal = ∑(Ei × EFi) + ∑(Mj × CFj)", options: { breakLine: true, fontSize: 12 } },
    { text: "ΔCE = CEnew − CEsecond（减排量）", options: { breakLine: true, fontSize: 11 } },
    { text: "含生产、使用、回收三阶段排放", options: { breakLine: true, fontSize: 11 } },
    { text: "碳排放因子：0.5366 kgCO₂e/kWh", options: { fontSize: 11 } },
  ], {
    x: 5.55, y: 3.9, w: 3.8, h: 1.2, fontSize: 11, fontFace: "Microsoft YaHei",
    color: C.muted, paraSpaceAfter: 4, margin: 0,
  });
}

// === Slide 7: Case Parameters ===
{
  const slide = pres.addSlide();
  slide.background = { color: C.white };

  slide.addText("五、案例参数设定", {
    x: 0.6, y: 0.35, w: 6, h: 0.55, fontSize: 26, fontFace: "Microsoft YaHei",
    color: C.navy, bold: true, margin: 0,
  });
  addTitleBar(slide, 0.95);
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.1, w: 8.8, h: 0.015, fill: { color: C.lightGray } });

  // Case description
  slide.addText("典型工商业储能项目：5MW / 10MWh 磷酸铁锂储能系统", {
    x: 0.6, y: 1.3, w: 8.8, h: 0.4, fontSize: 14, fontFace: "Microsoft YaHei",
    color: C.medBlue, bold: true, margin: 0,
  });

  // Key parameters table
  const tableData = [
    [
      { text: "参数", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 11 } },
      { text: "梯次利用系统", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 11 } },
      { text: "全新电池系统", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 11 } },
      { text: "单位", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 11 } },
    ],
    [
      { text: "系统容量", options: { fontSize: 11 } }, { text: "10000", options: { fontSize: 11 } },
      { text: "10000", options: { fontSize: 11 } }, { text: "kWh", options: { fontSize: 11 } },
    ],
    [
      { text: "初始投资", options: { fontSize: 11, bold: true } }, { text: "600", options: { fontSize: 11, bold: true, color: C.green } },
      { text: "900", options: { fontSize: 11 } }, { text: "元/kWh", options: { fontSize: 11 } },
    ],
    [
      { text: "年运维率", options: { fontSize: 11 } }, { text: "3.5%", options: { fontSize: 11 } },
      { text: "2%", options: { fontSize: 11 } }, { text: "占初始投资", options: { fontSize: 11 } },
    ],
    [
      { text: "系统效率", options: { fontSize: 11 } }, { text: "88%", options: { fontSize: 11 } },
      { text: "90%", options: { fontSize: 11 } }, { text: "首年充放电", options: { fontSize: 11 } },
    ],
    [
      { text: "系统寿命", options: { fontSize: 11, bold: true } }, { text: "5年", options: { fontSize: 11, bold: true, color: C.red } },
      { text: "8年", options: { fontSize: 11 } }, { text: "年", options: { fontSize: 11 } },
    ],
    [
      { text: "峰谷价差", options: { fontSize: 11 } }, { text: "0.80", options: { fontSize: 11 } },
      { text: "0.80", options: { fontSize: 11 } }, { text: "元/kWh", options: { fontSize: 11 } },
    ],
    [
      { text: "贴现率", options: { fontSize: 11 } }, { text: "8%", options: { fontSize: 11 } },
      { text: "8%", options: { fontSize: 11 } }, { text: "WACC", options: { fontSize: 11 } },
    ],
  ];

  slide.addTable(tableData, {
    x: 0.8, y: 1.85, w: 8.4, colW: [2.2, 2.1, 2.1, 2.0],
    border: { pt: 0.5, color: C.lightGray },
    rowH: [0.35, 0.35, 0.35, 0.35, 0.35, 0.35, 0.35, 0.35],
    autoPage: false,
  });

  // Highlight box
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 4.7, w: 8.8, h: 0.6, fill: { color: C.lightBg }, shadow: makeShadow() });
  slide.addText("运营策略：谷时段（0.4107元/kWh）充电，峰时段（1.2114元/kWh）放电，单次循环套利约0.80元/kWh，年循环350次", {
    x: 0.8, y: 4.75, w: 8.4, h: 0.5, fontSize: 12, fontFace: "Microsoft YaHei",
    color: C.muted, valign: "middle", margin: 0,
  });
}

// === Slide 8: Economic Results ===
{
  const slide = pres.addSlide();
  slide.background = { color: C.white };

  slide.addText("六、经济效益分析结果", {
    x: 0.6, y: 0.35, w: 6, h: 0.55, fontSize: 26, fontFace: "Microsoft YaHei",
    color: C.navy, bold: true, margin: 0,
  });
  addTitleBar(slide, 0.95);
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.1, w: 8.8, h: 0.015, fill: { color: C.lightGray } });

  // Key metrics callouts
  const metrics = [
    { label: "初始投资降低", value: "-33.3%", sub: "600 vs 900 元/kWh", color: C.green },
    { label: "LCOE", value: "0.4815", sub: "元/kWh（全新: 0.5409）", color: C.accent },
    { label: "NPV", value: "453.34", sub: "万元（全新: 469.01）", color: C.medBlue },
    { label: "投资回收期", value: "2.66年", sub: "（全新: 3.85年）", color: C.navy },
  ];

  metrics.forEach((m, i) => {
    const x = 0.5 + i * 2.25;
    slide.addShape(pres.shapes.RECTANGLE, { x: x, y: 1.35, w: 2.1, h: 1.5, fill: { color: C.lightBg }, shadow: makeShadow() });
    slide.addText(m.value, {
      x: x, y: 1.45, w: 2.1, h: 0.55, fontSize: 22, fontFace: "Arial",
      color: m.color, bold: true, align: "center", valign: "middle", margin: 0,
    });
    slide.addText(m.label, {
      x: x, y: 2.05, w: 2.1, h: 0.35, fontSize: 11, fontFace: "Microsoft YaHei",
      color: C.muted, align: "center", margin: 0,
    });
    slide.addText(m.sub, {
      x: x, y: 2.35, w: 2.1, h: 0.35, fontSize: 10, fontFace: "Microsoft YaHei",
      color: C.muted, align: "center", margin: 0,
    });
  });

  // Comparison table
  const econTable = [
    [
      { text: "指标", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 10 } },
      { text: "梯次利用", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 10 } },
      { text: "全新电池", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 10 } },
      { text: "优势方", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 10 } },
    ],
    [
      { text: "总成本现值PVC（万元）", options: { fontSize: 10 } }, { text: "685.74", options: { fontSize: 10, color: C.green, bold: true } },
      { text: "979.13", options: { fontSize: 10 } }, { text: "梯次利用 ✓", options: { fontSize: 10, color: C.green } },
    ],
    [
      { text: "总收益现值PVB（万元）", options: { fontSize: 10 } }, { text: "1139.08", options: { fontSize: 10 } },
      { text: "1448.14", options: { fontSize: 10, bold: true } }, { text: "全新电池 ✓", options: { fontSize: 10, color: C.medBlue } },
    ],
    [
      { text: "年运营收益（万元）", options: { fontSize: 10 } }, { text: "246.40", options: { fontSize: 10 } },
      { text: "252.00", options: { fontSize: 10 } }, { text: "基本持平", options: { fontSize: 10 } },
    ],
    [
      { text: "年净现金流（万元）", options: { fontSize: 10 } }, { text: "225.40", options: { fontSize: 10 } },
      { text: "234.00", options: { fontSize: 10 } }, { text: "基本持平", options: { fontSize: 10 } },
    ],
  ];

  slide.addTable(econTable, {
    x: 0.8, y: 3.1, w: 8.4, colW: [2.8, 2.0, 2.0, 1.6],
    border: { pt: 0.5, color: C.lightGray },
    rowH: [0.32, 0.32, 0.32, 0.32, 0.32],
  });

  // Bottom insight
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 4.75, w: 8.8, h: 0.6, fill: { color: C.lightBg }, shadow: makeShadow() });
  slide.addText("核心洞察：梯次利用系统以低33.3%的初始投资，实现与全新系统基本持平的NPV（差距仅3.3%），且LCOE低11.0%，投资回收期快1.19年", {
    x: 0.8, y: 4.78, w: 8.4, h: 0.55, fontSize: 12, fontFace: "Microsoft YaHei",
    color: C.navy, bold: true, valign: "middle", margin: 0,
  });
}

// === Slide 9: Environmental Results ===
{
  const slide = pres.addSlide();
  slide.background = { color: C.white };

  slide.addText("六（续）、环境效益分析结果", {
    x: 0.6, y: 0.35, w: 6, h: 0.55, fontSize: 26, fontFace: "Microsoft YaHei",
    color: C.navy, bold: true, margin: 0,
  });
  addTitleBar(slide, 0.95);
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.1, w: 8.8, h: 0.015, fill: { color: C.lightGray } });

  // Big stat: 26.4%
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.3, w: 3.5, h: 1.8, fill: { color: C.lightBg }, shadow: makeShadow() });
  slide.addText("26.4%", {
    x: 0.6, y: 1.45, w: 3.5, h: 0.7, fontSize: 42, fontFace: "Arial",
    color: C.green, bold: true, align: "center", valign: "middle", margin: 0,
  });
  slide.addText("碳排放减少比例", {
    x: 0.6, y: 2.2, w: 3.5, h: 0.35, fontSize: 13, fontFace: "Microsoft YaHei",
    color: C.medBlue, bold: true, align: "center", margin: 0,
  });
  slide.addText("减排 458.6 万 kgCO₂e", {
    x: 0.6, y: 2.55, w: 3.5, h: 0.35, fontSize: 12, fontFace: "Microsoft YaHei",
    color: C.muted, align: "center", margin: 0,
  });

  // Breakdown table
  const envTable = [
    [
      { text: "生命周期阶段", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 10 } },
      { text: "梯次利用系统", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 10 } },
      { text: "全新电池系统", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 10 } },
    ],
    [
      { text: "生产阶段排放", options: { fontSize: 10 } },
      { text: "0 kg（避免新生产）", options: { fontSize: 10, color: C.green, bold: true } },
      { text: "724,000 kg", options: { fontSize: 10 } },
    ],
    [
      { text: "使用阶段排放", options: { fontSize: 10 } },
      { text: "12,826,776 kg", options: { fontSize: 10 } },
      { text: "16,722,488 kg", options: { fontSize: 10 } },
    ],
    [
      { text: "回收阶段排放", options: { fontSize: 10 } },
      { text: "−51,000 kg", options: { fontSize: 10 } },
      { text: "−85,000 kg", options: { fontSize: 10 } },
    ],
    [
      { text: "合计总排放量", options: { fontSize: 10, bold: true } },
      { text: "12,775,776 kg", options: { fontSize: 10, bold: true, color: C.green } },
      { text: "17,361,488 kg", options: { fontSize: 10, bold: true } },
    ],
    [
      { text: "单位排放强度", options: { fontSize: 10 } },
      { text: "0.6913 kgCO₂e/kWh", options: { fontSize: 10 } },
      { text: "0.6889 kgCO₂e/kWh", options: { fontSize: 10 } },
    ],
  ];

  slide.addTable(envTable, {
    x: 4.3, y: 1.3, w: 5.2, colW: [1.7, 1.75, 1.75],
    border: { pt: 0.5, color: C.lightGray },
    rowH: [0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
  });

  // Key insights
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 3.35, w: 8.8, h: 2.0, fill: { color: C.lightBg }, shadow: makeShadow() });
  slide.addText("关键发现", {
    x: 0.8, y: 3.4, w: 4, h: 0.35, fontSize: 15, fontFace: "Microsoft YaHei",
    color: C.medBlue, bold: true, margin: 0,
  });

  slide.addText([
    { text: "1. 避免新电池生产阶段排放72.4万kg，是减排的主要来源", options: { breakLine: true, fontSize: 12 } },
    { text: "2. 单位排放强度基本持平（差异仅0.3%），主要因寿命与效率差异抵消", options: { breakLine: true, fontSize: 12 } },
    { text: "3. 若以相同8年总放电量为基准，梯次利用系统累计排放仍低2.1%", options: { breakLine: true, fontSize: 12 } },
    { text: "4. 效率每提升1个百分点，使用阶段排放降低约1.14%", options: { breakLine: true, fontSize: 12 } },
    { text: "5. 若寿命延长至8年且效率维持88%，单位排放强度降至0.5185，显著优于全新电池", options: { fontSize: 12 } },
  ], {
    x: 0.8, y: 3.85, w: 8.4, h: 1.4, fontSize: 12, fontFace: "Microsoft YaHei",
    color: C.muted, paraSpaceAfter: 4, margin: 0,
  });
}

// === Slide 10: Sensitivity Analysis - Coefficients ===
{
  const slide = pres.addSlide();
  slide.background = { color: C.white };

  slide.addText("七、敏感性分析", {
    x: 0.6, y: 0.35, w: 6, h: 0.55, fontSize: 26, fontFace: "Microsoft YaHei",
    color: C.navy, bold: true, margin: 0,
  });
  addTitleBar(slide, 0.95);
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.1, w: 8.8, h: 0.015, fill: { color: C.lightGray } });

  slide.addText("单因素敏感性分析（±20%变动范围）", {
    x: 0.6, y: 1.25, w: 5, h: 0.35, fontSize: 14, fontFace: "Microsoft YaHei",
    color: C.medBlue, bold: true, margin: 0,
  });

  // Sensitivity coefficient cards
  const sensData = [
    { param: "峰谷电价差", coef: "2.51", rank: "1", color: C.red, detail: "NPV波动±50.3%" },
    { param: "系统效率", coef: "2.51", rank: "1", color: C.red, detail: "NPV波动±50.3%" },
    { param: "循环寿命", coef: "1.80", rank: "2", color: C.orange, detail: "NPV波动-37.6%/+34.3%" },
    { param: "电池成本", coef: "1.51", rank: "3", color: C.gold, detail: "NPV波动±30.3%" },
  ];

  sensData.forEach((s, i) => {
    const x = 0.5 + i * 2.25;
    slide.addShape(pres.shapes.RECTANGLE, { x: x, y: 1.75, w: 2.1, h: 1.7, fill: { color: C.white }, shadow: makeShadow() });
    slide.addShape(pres.shapes.RECTANGLE, { x: x, y: 1.75, w: 2.1, h: 0.06, fill: { color: s.color } });
    slide.addText(s.coef, {
      x: x, y: 1.9, w: 2.1, h: 0.55, fontSize: 28, fontFace: "Arial",
      color: s.color, bold: true, align: "center", valign: "middle", margin: 0,
    });
    slide.addText(s.param, {
      x: x, y: 2.5, w: 2.1, h: 0.3, fontSize: 12, fontFace: "Microsoft YaHei",
      color: C.dark, bold: true, align: "center", margin: 0,
    });
    slide.addText(s.detail, {
      x: x, y: 2.85, w: 2.1, h: 0.3, fontSize: 10, fontFace: "Microsoft YaHei",
      color: C.muted, align: "center", margin: 0,
    });
    slide.addText("敏感度排序: #" + s.rank, {
      x: x, y: 3.15, w: 2.1, h: 0.2, fontSize: 9, fontFace: "Microsoft YaHei",
      color: C.muted, align: "center", margin: 0,
    });
  });

  // NPV change chart table
  slide.addText("NPV变动情景分析（万元）", {
    x: 0.6, y: 3.65, w: 5, h: 0.35, fontSize: 14, fontFace: "Microsoft YaHei",
    color: C.medBlue, bold: true, margin: 0,
  });

  const sensTable = [
    [
      { text: "参数", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 9 } },
      { text: "基准NPV", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 9 } },
      { text: "−20%情景", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 9 } },
      { text: "+20%情景", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 9 } },
      { text: "变动幅度", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 9 } },
    ],
    [
      { text: "峰谷价差", options: { fontSize: 9 } }, { text: "453.34", options: { fontSize: 9 } },
      { text: "225.53", options: { fontSize: 9, color: C.red } }, { text: "681.16", options: { fontSize: 9, color: C.green } },
      { text: "±50.3%", options: { fontSize: 9, bold: true } },
    ],
    [
      { text: "系统效率", options: { fontSize: 9 } }, { text: "453.34", options: { fontSize: 9 } },
      { text: "225.53", options: { fontSize: 9, color: C.red } }, { text: "567.25", options: { fontSize: 9, color: C.green } },
      { text: "−50.3%/+25.1%", options: { fontSize: 9, bold: true } },
    ],
    [
      { text: "循环寿命", options: { fontSize: 9 } }, { text: "453.34", options: { fontSize: 9 } },
      { text: "282.78", options: { fontSize: 9, color: C.red } }, { text: "608.95", options: { fontSize: 9, color: C.green } },
      { text: "−37.6%/+34.3%", options: { fontSize: 9, bold: true } },
    ],
    [
      { text: "电池成本", options: { fontSize: 9 } }, { text: "453.34", options: { fontSize: 9 } },
      { text: "590.49", options: { fontSize: 9, color: C.green } }, { text: "316.19", options: { fontSize: 9, color: C.red } },
      { text: "±30.3%", options: { fontSize: 9, bold: true } },
    ],
  ];

  slide.addTable(sensTable, {
    x: 0.6, y: 4.05, w: 8.8, colW: [1.5, 1.5, 1.8, 1.8, 2.2],
    border: { pt: 0.5, color: C.lightGray },
    rowH: [0.28, 0.28, 0.28, 0.28, 0.28],
  });
}

// === Slide 11: Sensitivity Comparison ===
{
  const slide = pres.addSlide();
  slide.background = { color: C.white };

  slide.addText("七、敏感性对比：梯次利用 vs 全新电池", {
    x: 0.6, y: 0.35, w: 8, h: 0.55, fontSize: 26, fontFace: "Microsoft YaHei",
    color: C.navy, bold: true, margin: 0,
  });
  addTitleBar(slide, 0.95);
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.1, w: 8.8, h: 0.015, fill: { color: C.lightGray } });

  // Comparison table
  const compTable = [
    [
      { text: "参数", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 10 } },
      { text: "梯次利用\n敏感度系数", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 10, align: "center" } },
      { text: "全新电池\n敏感度系数", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 10, align: "center" } },
      { text: "抗风险评价", options: { bold: true, color: C.white, fill: { color: C.medBlue }, fontSize: 10, align: "center" } },
    ],
    [
      { text: "峰谷价差", options: { fontSize: 11 } }, { text: "2.51", options: { fontSize: 14, bold: true, color: C.red, align: "center" } },
      { text: "3.09", options: { fontSize: 14, bold: true, color: "9B2C2C", align: "center" } },
      { text: "梯次利用抗风险能力更强", options: { fontSize: 10, color: C.green } },
    ],
    [
      { text: "系统效率", options: { fontSize: 11 } }, { text: "2.51", options: { fontSize: 14, bold: true, color: C.red, align: "center" } },
      { text: "3.09", options: { fontSize: 14, bold: true, color: "9B2C2C", align: "center" } },
      { text: "梯次利用抗风险能力更强", options: { fontSize: 10, color: C.green } },
    ],
    [
      { text: "循环寿命", options: { fontSize: 11 } }, { text: "1.88", options: { fontSize: 14, bold: true, color: C.orange, align: "center" } },
      { text: "2.18", options: { fontSize: 14, bold: true, color: C.orange, align: "center" } },
      { text: "梯次利用抗风险能力更强", options: { fontSize: 10, color: C.green } },
    ],
    [
      { text: "电池成本", options: { fontSize: 11 } }, { text: "1.51", options: { fontSize: 14, bold: true, color: C.gold, align: "center" } },
      { text: "2.09", options: { fontSize: 14, bold: true, color: C.gold, align: "center" } },
      { text: "成本优势显著且稳定", options: { fontSize: 10, color: C.green } },
    ],
  ];

  slide.addTable(compTable, {
    x: 0.8, y: 1.4, w: 8.4, colW: [1.6, 2.0, 2.0, 2.8],
    border: { pt: 0.5, color: C.lightGray },
    rowH: [0.45, 0.5, 0.5, 0.5, 0.5],
  });

  // Key insights
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 3.6, w: 4.2, h: 1.7, fill: { color: C.lightBg }, shadow: makeShadow() });
  slide.addText("核心发现", {
    x: 0.8, y: 3.7, w: 3.8, h: 0.3, fontSize: 14, fontFace: "Microsoft YaHei",
    color: C.medBlue, bold: true, margin: 0,
  });
  slide.addText([
    { text: "梯次利用系统在所有四个参数上", options: { breakLine: true, fontSize: 12 } },
    { text: "敏感度均低于全新电池系统", options: { breakLine: true, fontSize: 12 } },
    { text: "", options: { breakLine: true, fontSize: 6 } },
    { text: "电池成本敏感度差异最显著：", options: { bold: true, breakLine: true, fontSize: 12 } },
    { text: "梯次1.51 vs 全新2.09", options: { breakLine: true, fontSize: 12 } },
    { text: "", options: { breakLine: true, fontSize: 6 } },
    { text: "峰谷价差降至约0.53元/kWh时", options: { breakLine: true, fontSize: 12 } },
    { text: "项目NPV将归零（盈亏平衡点）", options: { fontSize: 12 } },
  ], {
    x: 0.8, y: 4.05, w: 3.8, h: 1.2, fontSize: 12, fontFace: "Microsoft YaHei",
    color: C.muted, paraSpaceAfter: 2, margin: 0,
  });

  slide.addShape(pres.shapes.RECTANGLE, { x: 5.3, y: 3.6, w: 4.2, h: 1.7, fill: { color: C.lightBg }, shadow: makeShadow() });
  slide.addText("启示", {
    x: 5.5, y: 3.7, w: 3.8, h: 0.3, fontSize: 14, fontFace: "Microsoft YaHei",
    color: C.medBlue, bold: true, margin: 0,
  });
  slide.addText([
    { text: "梯次利用系统在供应链价格波动、", options: { breakLine: true, fontSize: 12 } },
    { text: "电价政策不确定的市场环境中", options: { breakLine: true, fontSize: 12 } },
    { text: "具有更强的投资稳健性", options: { breakLine: true, fontSize: 12 } },
    { text: "", options: { breakLine: true, fontSize: 6 } },
    { text: "为动力电池规模化退役后的", options: { breakLine: true, fontSize: 12 } },
    { text: "商业化应用提供了理论支撑", options: { fontSize: 12 } },
  ], {
    x: 5.5, y: 4.05, w: 3.8, h: 1.2, fontSize: 12, fontFace: "Microsoft YaHei",
    color: C.muted, paraSpaceAfter: 2, margin: 0,
  });
}

// === Slide 12: Policy Recommendations ===
{
  const slide = pres.addSlide();
  slide.background = { color: C.white };

  slide.addText("八、政策建议", {
    x: 0.6, y: 0.35, w: 6, h: 0.55, fontSize: 26, fontFace: "Microsoft YaHei",
    color: C.navy, bold: true, margin: 0,
  });
  addTitleBar(slide, 0.95);
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.1, w: 8.8, h: 0.015, fill: { color: C.lightGray } });

  const policies = [
    { num: "01", title: "完善电价机制", sub: "强化项目收益保障", body: "设定峰谷价差底线标准（0.3-0.6元/kWh）；出台储能电价补偿机制；鼓励签订长期购电协议（PPA）锁定电价", icon: "⚡" },
    { num: "02", title: "设立专项补贴", sub: "攻坚核心技术优化", body: "重点支持无损检测、快速分选与高效重组技术；加大BMS优化研发支持；弥合退役电池单体差异，提升效率与寿命", icon: "🔬" },
    { num: "03", title: "建立溯源平台", sub: "实现数据透明化监管", body: "建立全生命周期数据溯源与监管平台；强制全链条登记；为残值评估、保险定价、环保回收提供数据依据", icon: "📊" },
    { num: "04", title: "丰富金融激励", sub: "降低企业融资门槛", body: `税收减免、固定资产加速折旧等优惠；推出专属"绿色信贷"产品；降低贷款利率与融资门槛，吸引社会资本`, icon: "💰" },
  ];

  policies.forEach((p, i) => {
    const y = 1.25 + i * 0.98;
    // Card
    slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: y, w: 8.8, h: 0.88, fill: { color: C.white }, shadow: makeShadow() });
    // Num badge
    slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: y, w: 0.55, h: 0.88, fill: { color: C.medBlue } });
    slide.addText(p.num, {
      x: 0.6, y: y, w: 0.55, h: 0.88, fontSize: 16, fontFace: "Arial",
      color: C.white, bold: true, align: "center", valign: "middle", margin: 0,
    });
    // Title + subtitle
    slide.addText(p.title, {
      x: 1.3, y: y + 0.05, w: 2.5, h: 0.35, fontSize: 14, fontFace: "Microsoft YaHei",
      color: C.navy, bold: true, margin: 0,
    });
    slide.addText(p.sub, {
      x: 1.3, y: y + 0.4, w: 2.5, h: 0.35, fontSize: 11, fontFace: "Microsoft YaHei",
      color: C.accent, bold: true, margin: 0,
    });
    // Body
    slide.addText(p.body, {
      x: 3.9, y: y + 0.08, w: 5.3, h: 0.72, fontSize: 11, fontFace: "Microsoft YaHei",
      color: C.muted, valign: "middle", margin: 0,
    });
  });
}

// === Slide 13: Conclusions (1) ===
{
  const slide = pres.addSlide();
  slide.background = { color: C.white };

  slide.addText("九、研究结论", {
    x: 0.6, y: 0.35, w: 6, h: 0.55, fontSize: 26, fontFace: "Microsoft YaHei",
    color: C.navy, bold: true, margin: 0,
  });
  addTitleBar(slide, 0.95);
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.1, w: 8.8, h: 0.015, fill: { color: C.lightGray } });

  const conclusions = [
    {
      num: "结论一",
      title: "梯次利用电池在用户侧储能领域具有良好的经济可行性",
      body: "初始投资较全新电池系统低约33%，全生命周期总成本现值降低约30%，NPV与全新系统基本持平（差距仅3.3%），LCOE为0.48元/kWh（低于全新0.54元/kWh），投资回收期仅2.66年，展现良好商业化应用潜力。",
    },
    {
      num: "结论二",
      title: "梯次利用电池在全生命周期内具有明显的碳减排优势",
      body: "完整生命周期内总碳排放较全新电池系统减少约26%（458.6万kgCO₂e），主要源于避免新电池生产阶段72.4万kg排放。随着电池寿命延长和效率提升，环境优势将更加明显。",
    },
    {
      num: "结论三",
      title: "峰谷电价差和系统效率是影响项目经济性的关键因素",
      body: "峰谷价差敏感度系数2.51居首位，系统效率同样达2.51，循环寿命1.80，电池成本1.51。峰谷价差降至约0.53元/kWh时项目NPV归零，政策保障至关重要。",
    },
  ];

  conclusions.forEach((c, i) => {
    const y = 1.3 + i * 1.38;
    slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: y, w: 8.8, h: 1.25, fill: { color: C.lightBg }, shadow: makeShadow() });
    slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: y, w: 0.07, h: 1.25, fill: { color: C.accent } });

    slide.addText([
      { text: c.num, options: { fontSize: 11, color: C.accent, bold: true, breakLine: true } },
      { text: c.title, options: { fontSize: 14, color: C.navy, bold: true } },
    ], {
      x: 0.85, y: y + 0.08, w: 8.3, h: 0.6, fontFace: "Microsoft YaHei", margin: 0,
    });

    slide.addText(c.body, {
      x: 0.85, y: y + 0.65, w: 8.3, h: 0.5, fontSize: 11, fontFace: "Microsoft YaHei",
      color: C.muted, margin: 0,
    });
  });
}

// === Slide 14: Conclusions (2) ===
{
  const slide = pres.addSlide();
  slide.background = { color: C.white };

  slide.addText("九、研究总结与展望", {
    x: 0.6, y: 0.35, w: 6, h: 0.55, fontSize: 26, fontFace: "Microsoft YaHei",
    color: C.navy, bold: true, margin: 0,
  });
  addTitleBar(slide, 0.95);
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.1, w: 8.8, h: 0.015, fill: { color: C.lightGray } });

  // Key insight
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.3, w: 8.8, h: 0.6, fill: { color: C.navy } });
  slide.addText("核心结论：梯次利用电池以更低成本、更强抗风险能力、更优碳减排表现，在用户侧储能领域具备显著的商业化推广价值", {
    x: 0.8, y: 1.3, w: 8.4, h: 0.6, fontSize: 14, fontFace: "Microsoft YaHei",
    color: C.white, bold: true, align: "center", valign: "middle", margin: 0,
  });

  // Innovation points
  slide.addText("研究贡献", {
    x: 0.6, y: 2.15, w: 3, h: 0.4, fontSize: 16, fontFace: "Microsoft YaHei",
    color: C.medBlue, bold: true, margin: 0,
  });

  slide.addText([
    { text: "1. 构建了融合经济与环境效益的全生命周期综合评价框架", options: { breakLine: true, fontSize: 12 } },
    { text: "2. 通过±20%单因素敏感性分析，精确识别关键风险变量", options: { breakLine: true, fontSize: 12 } },
    { text: "3. 进行了梯次利用与全新电池系统的全维度对比分析", options: { breakLine: true, fontSize: 12 } },
    { text: "4. 提出了具有可操作性的四级政策建议体系", options: { fontSize: 12 } },
  ], {
    x: 0.6, y: 2.6, w: 4.2, h: 1.8, fontSize: 12, fontFace: "Microsoft YaHei",
    color: C.muted, paraSpaceAfter: 8, margin: 0,
  });

  // Limitations & Future
  slide.addText("研究局限与展望", {
    x: 5.3, y: 2.15, w: 3, h: 0.4, fontSize: 16, fontFace: "Microsoft YaHei",
    color: C.medBlue, bold: true, margin: 0,
  });

  slide.addText([
    { text: "局限：", options: { bold: true, breakLine: true, fontSize: 12 } },
    { text: "电池效率衰减及运维成本进行了理想化处理；案例集中于典型工商业场景", options: { breakLine: true, fontSize: 11 } },
    { text: "", options: { breakLine: true, fontSize: 6 } },
    { text: "展望：", options: { bold: true, breakLine: true, fontSize: 12 } },
    { text: "结合多区域实际运行数据优化模型参数；深入探讨政策激励对商业模式的影响", options: { fontSize: 11 } },
  ], {
    x: 5.3, y: 2.6, w: 4.2, h: 1.8, fontSize: 11, fontFace: "Microsoft YaHei",
    color: C.muted, paraSpaceAfter: 6, margin: 0,
  });

  // Bottom: significance
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 4.55, w: 8.8, h: 0.7, fill: { color: C.lightBg }, shadow: makeShadow() });
  slide.addText("随着技术进步、市场机制完善及政策支持力度的提升，梯次利用电池有望在未来储能产业中发挥更重要的作用，为推动新能源产业可持续发展和实现低碳能源转型提供重要支撑。", {
    x: 0.8, y: 4.58, w: 8.4, h: 0.65, fontSize: 12, fontFace: "Microsoft YaHei",
    color: C.medBlue, bold: true, align: "center", valign: "middle", margin: 0,
  });
}

// === Slide 15: Thank You ===
{
  const slide = pres.addSlide();
  slide.background = { color: C.navy };

  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.08, fill: { color: C.accent } });

  slide.addText("感谢聆听", {
    x: 1, y: 1.4, w: 8, h: 1.0, fontSize: 48, fontFace: "Microsoft YaHei",
    color: C.white, bold: true, align: "center", valign: "middle", margin: 0,
  });

  slide.addShape(pres.shapes.RECTANGLE, { x: 3.5, y: 2.6, w: 3, h: 0.03, fill: { color: C.accent } });

  slide.addText([
    { text: "梯次利用电池在用户侧储能项目的投资效益与政策建议研究", options: { breakLine: true, fontSize: 16 } },
    { text: "", options: { breakLine: true, fontSize: 10 } },
    { text: "答辩人：张雅馨", options: { breakLine: true, fontSize: 15 } },
    { text: "指导教师：孙波", options: { breakLine: true, fontSize: 15 } },
    { text: "上海电力大学 · 经济与管理学院", options: { breakLine: true, fontSize: 14 } },
    { text: "", options: { breakLine: true, fontSize: 10 } },
    { text: "敬请各位老师批评指正", options: { fontSize: 14 } },
  ], {
    x: 2, y: 2.9, w: 6, h: 2.2, fontSize: 14, fontFace: "Microsoft YaHei",
    color: "A0C4E8", align: "center", lineSpacingMultiple: 1.4, margin: 0,
  });

  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 5.545, w: 10, h: 0.08, fill: { color: C.accent } });
}

// === Save ===
pres.writeFile({ fileName: "D:\\hb\\毕业论文答辩PPT.pptx" }).then(() => {
  console.log("PPT saved successfully!");
}).catch((err) => {
  console.error("Error:", err);
});
