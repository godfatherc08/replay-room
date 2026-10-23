// Screenshots of the running viewer for visual verification (Build 5 v2, §8).
//
//   npm run dev                        (in another terminal; serves http://localhost:5173)
//   npm run shots -- [outDir] [moment]
//
// Drives the locally installed Microsoft Edge (or Chrome: SHOTS_CHANNEL=chrome) headlessly through
// playwright-core; no browser download. Captures the hero moment in the states the acceptance criteria
// name: (a) ready, (b) a mid-story step, (c) the ribbon mid-play, (d) the counterfactual climax,
// (e) Fan vs (f) Analyst of one step, and (g) an Explore jump.

import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright-core";

const out = process.argv[2] ?? "shots";
const moment = process.argv[3] ?? "SYN-0007-big_chance_saved-3";
const base = process.env.SHOTS_URL ?? "http://localhost:5173/";
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({
  channel: process.env.SHOTS_CHANNEL ?? "msedge",
  headless: true,
  args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
});
const page = await browser.newPage({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1 });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

async function open(query, settle = 2500) {
  await page.goto(`${base}?moment=${moment}&${query}`);
  await page.waitForFunction(() => "replayRoom" in window, null, { timeout: 30000 });
  await page.waitForTimeout(settle);
}
const shot = (name, opts = {}) => page.screenshot({ path: join(out, `${name}.png`), ...opts });

const head = await (async () => {
  await open("", 500);
  return page.evaluate(() => {
    const b = window.replayRoom.bundle;
    return { n: b.story.length, assist: b.story.findIndex((s) => s.kind === "contribution" && s.contribution_id === "a161") + 1 };
  });
})();

await open("", 2500);
await shot("a-ready");

await open(`step=${head.assist}`, 3000);
await shot("b-step");

await open("play=1", 16000);
await shot("c-ribbon-full");
await page.locator("#ribbon").screenshot({ path: join(out, "c-ribbon.png") });

await open(`step=${head.n}`, 3500);
await shot("d-counterfactual");

await open(`step=${head.assist}&mode=fan`, 3000);
await shot("e-fan");
await open(`step=${head.assist}&mode=analyst`, 3000);
await shot("f-analyst");

await open(`step=${head.n}&mode=fan`, 3500);
await shot("e2-fan-counterfactual");

await open("jump=sEPA-11", 3000);
await shot("g-explore-jump");

// (h) a close-up of the figures: the camera pulled in on the focused player of the assist step
await open(`step=${head.assist}`, 3000);
await page.evaluate(() => {
  const { scene } = window.replayRoom;
  const at = scene.markers.get(scene.highlighted[0]).root.position;
  scene.desiredTarget = null; // stop the eased focus so the manual pose holds
  scene.desiredRadius = null;
  scene.camera.setTarget(at.clone());
  scene.camera.beta = 1.2;
  scene.camera.radius = 11;
});
await page.waitForTimeout(1500);
await shot("h-closeup");

// probes: numbers a still cannot show
await open("", 1500);
const probe = {};
probe.fonts = await page.evaluate(() => {
  const sizes = new Map();
  for (const e of document.querySelectorAll("body *")) {
    if (![...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
    const px = getComputedStyle(e).fontSize;
    sizes.set(px, (sizes.get(px) ?? 0) + 1);
  }
  return Object.fromEntries([...sizes].sort());
});
// the camera eases: sample its target for a second after a step change
probe.camera = await page.evaluate(async () => {
  const { viewer, scene } = window.replayRoom;
  viewer.story.goto(3);
  const out = [];
  for (let k = 0; k < 8; k++) {
    const t = scene.camera.target;
    out.push([+t.x.toFixed(2), +t.z.toFixed(2), +scene.camera.radius.toFixed(1)]);
    await new Promise((r) => setTimeout(r, 150));
  }
  return out;
});
// the story plays itself: step index once a second from Play analysis
probe.story = await page.evaluate(async () => {
  const { viewer } = window.replayRoom;
  viewer.story.reset();
  document.querySelector(".rr-cta").click();
  const out = [];
  for (let k = 0; k < 8; k++) {
    out.push([viewer.story.index, viewer.story.state, document.querySelector(".rr-ribbon-fill").style.width]);
    await new Promise((r) => setTimeout(r, 1000));
  }
  return out;
});
console.log(JSON.stringify(probe));

await browser.close();
if (errors.length) {
  console.error(errors.join("\n"));
  process.exitCode = 1;
}
console.log(`wrote ${out}/ (${head.n} story steps)`);
