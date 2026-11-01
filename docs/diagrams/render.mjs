// 把本目录的 *.mmd 渲染成 2 倍清晰度的 PNG，供 README 和设计文档引用。
// GitHub 自带的 Mermaid 渲染按浏览器字体估算宽度，中文常被截断，所以改为提交渲染好的图片。
// 用法：node docs/diagrams/render.mjs（需要 playwright-core 与带中文字体的 Chromium，PW_CHROME 指向浏览器）
import { createRequire } from "node:module";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const { chromium } = createRequire(join(process.env.NODE_PATH ?? ".", "x"))("playwright-core");
const dir = dirname(fileURLToPath(import.meta.url));
const MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js";
const only = process.argv.slice(2);

const browser = await chromium.launch({ executablePath: process.env.PW_CHROME });
const page = await browser.newPage({ deviceScaleFactor: 2, viewport: { width: 1600, height: 1000 } });
await page.setContent(`<html><body style="margin:0;background:#fff"><div id="out" style="display:inline-block;padding:24px"></div></body></html>`);
await page.addScriptTag({ content: await (await fetch(MERMAID)).text() });
await page.evaluate(() => window.mermaid.initialize({
  startOnLoad: false,
  theme: "base",
  fontFamily: '"WenQuanYi Zen Hei", "Microsoft YaHei", sans-serif',
  themeVariables: {
    fontSize: "15px",
    primaryColor: "#eef2ff", primaryBorderColor: "#6366f1", primaryTextColor: "#1e1b4b",
    lineColor: "#64748b", clusterBkg: "#f8fafc", clusterBorder: "#cbd5e1",
    actorBkg: "#eef2ff", actorBorder: "#6366f1", noteBkgColor: "#fef9c3", noteBorderColor: "#ca8a04",
    signalColor: "#334155", signalTextColor: "#1e293b",
  },
  markdownAutoWrap: false,
  flowchart: { useMaxWidth: false, padding: 18, wrappingWidth: 480, nodeSpacing: 40, rankSpacing: 50, curve: "basis" },
  sequence: { useMaxWidth: false, actorMargin: 60, messageMargin: 36, noteMargin: 12, wrap: false },
}));

for (const f of readdirSync(dir).filter((f) => f.endsWith(".mmd"))) {
  const name = f.replace(/\.mmd$/, "");
  if (only.length && !only.includes(name)) continue;
  const src = readFileSync(join(dir, f), "utf8");
  await page.evaluate(async ([id, src]) => {
    const { svg } = await window.mermaid.render(id, src);
    document.getElementById("out").innerHTML = svg;
  }, ["g_" + name.replace(/-/g, "_"), src]);
  await page.locator("#out").screenshot({ path: join(dir, `${name}.png`) });
  console.log("已生成", `${name}.png`);
}
await browser.close();
