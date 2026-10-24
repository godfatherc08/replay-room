// The fixed-viewport probe (viewer fix v4 §7): measures layout, aspect, dpr scaling and duplicate cards.
//   npm run dev; node scripts/viewport-check.mjs [outDir] [width] [height] [dpr] [moment]
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright-core";

const [out = "viewport", w = "1101", h = "696", dpr = "1.25", moment = "SYN-0007-goal-2"] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ channel: process.env.SHOTS_CHANNEL ?? "msedge", headless: true,
                                        args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: +w, height: +h }, deviceScaleFactor: +dpr });
await page.goto(`${process.env.SHOTS_URL ?? "http://localhost:5173/"}?moment=${moment}`);
await page.waitForFunction(() => "replayRoom" in window, null, { timeout: 30000 });
await page.waitForTimeout(3000);
const probe = () => page.evaluate(() => {
  const c = document.querySelector("canvas"), r = c.getBoundingClientRect();
  return {
    viewport: [window.innerWidth, window.innerHeight, window.devicePixelRatio],
    canvasCss: [Math.round(r.width), Math.round(r.height)], canvasBuffer: [c.width, c.height],
    noPageScroll: document.documentElement.scrollHeight <= window.innerHeight + 2,
    pitchShare: +(r.height / window.innerHeight).toFixed(2),
    cssAspect: +(r.width / r.height).toFixed(2),
    bufferMatchesCss: Math.abs((c.width / c.height) - (r.width / r.height)) < 0.02,
    dprScaled: c.width >= Math.round(r.width * Math.min(window.devicePixelRatio, 2)) - 2,
    goalCards: [...document.querySelectorAll("*")].filter((e) => /REALIZED/.test(e.textContent) && e.textContent.length < 200).length,
  };
});
const before = await probe();
await page.screenshot({ path: join(out, "a-viewport.png") });
// (c) the ribbon, and (d) a close crop of the pitch at the device's pixel ratio (sharpness)
await page.locator("#ribbon").screenshot({ path: join(out, "c-ribbon.png") });
await page.locator("#footer").screenshot({ path: join(out, "b-timeline.png") });
const box = await page.locator("canvas").boundingBox();
await page.screenshot({ path: join(out, "d-pitch-crop.png"),
                        clip: { x: box.x + box.width * 0.55, y: box.y + box.height * 0.3, width: 320, height: 180 } });
console.log(JSON.stringify({ atLoad: before }));
// a resize must be tracked: shrink the window, measure again
await page.setViewportSize({ width: Math.round(+w * 0.8), height: Math.round(+h * 0.9) });
await page.waitForTimeout(1500);
console.log(JSON.stringify({ afterResize: await probe() }));
await browser.close();
