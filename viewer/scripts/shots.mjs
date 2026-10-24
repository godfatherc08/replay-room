// Screenshots of the running viewer for visual verification.
//
//   npm run dev                        (in another terminal; serves http://localhost:5173)
//   npm run shots -- [outDir] [moment]
//
// Drives the locally installed Microsoft Edge (or Chrome: SHOTS_CHANNEL=chrome) headlessly through
// playwright-core; no browser download. Captures the hero moment: (a) ready, (b) a build-up beat, (c) the
// ribbon mid-play, (d) the counterfactual climax, (e) Fan vs (f) Analyst of one beat, (g) an Explore jump,
// (h) a close-up of the figures, (i) the defensive flaw told through its computed link, (j) the match-context
// beat in both registers, (k) the bare pitch without the stadium. Probes: font sizes, camera easing, the
// story playing itself, and the keyboard: Space must pause without scrolling the page, arrows must step.

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

const probe = {};
const at = await (async () => {
  await open("", 500);
  return page.evaluate(() => {
    const s = window.replayRoom.bundle.story;
    const find = (f) => s.findIndex(f) + 1;
    const assist = find((x) => x.contribution_id === "a161" && x.kind === "build_up") || find((x) => x.kind === "build_up");
    const b = window.replayRoom.bundle;
    const off = b.account.contributions.find((c) => c.track === "off_ball") ?? b.account.contributions[0];
    return { n: s.length, assist, flaw: find((x) => x.kind === "flaw"), context: find((x) => x.kind === "context"),
             lead: find((x) => x.emphasis === "lead"), jump: off.contribution_id };
  });
})();

await open("", 2500);
await shot("a-ready");

await open(`step=${at.assist}`, 3000);
await shot("b-step");

await open("play=1", 16000);
await shot("c-ribbon-full");
await page.locator("#ribbon").screenshot({ path: join(out, "c-ribbon.png") });

await open(`step=${at.n}`, 3500);
await shot("d-counterfactual");

await open(`step=${at.assist}&mode=fan`, 3000);
await shot("e-fan");
await open(`step=${at.assist}&mode=analyst`, 3000);
await shot("f-analyst");

await open(`step=${at.n}&mode=fan`, 3500);
await shot("e2-fan-counterfactual");

await open(`jump=${at.jump}`, 3000);
await shot("g-explore-jump");

if (at.flaw) {
  await open(`step=${at.flaw}`, 3500);
  await shot("i-flaw-link");
  await open(`step=${at.flaw}&mode=fan`, 3500);
  await shot("i2-flaw-link-fan");
}
if (at.context) {
  await open(`step=${at.context}`, 3500);
  await shot("j-context-analyst");
  await open(`step=${at.context}&mode=fan`, 3500);
  await shot("j2-context-fan");
}
await open(`step=${at.lead}&stadium=0`, 3000);
await shot("k-no-stadium");

// v3: the card at rest (compact), expanded (the full reasoning), and the evidence drill-down open on the flaw
if (at.flaw) {
  await open(`step=${at.flaw}`, 3500);
  await shot("v3-a-compact-card");
  await page.locator(".rr-expand").click();
  await page.waitForTimeout(600);
  await shot("v3-b-expanded-card");
  await page.locator(".rr-claim").click();
  await page.waitForTimeout(2500);
  await shot("v3-c-evidence-open");
  await page.locator(".rr-evidence").screenshot({ path: join(out, "v3-c-evidence-panel.png") });
  await page.locator(".rr-mode-fan, .rr-modes .rr-seg-btn[data-value=fan]").first().click();
  await page.waitForTimeout(800);
  await shot("v3-c2-evidence-open-fan");
}
// evidence treatise L3: Go deeper on the flaw (the control surface fading, ghosts, distances), both registers;
// the timeline with an event selected; and a broken marking drawn red on another moment
if (at.flaw) {
  await open(`step=${at.flaw}`, 3500);
  await page.locator(".rr-expand").click();
  await page.waitForTimeout(800);
  await shot("l3-a-deep-start");
  await page.waitForTimeout(6000); // the swing has played: the surface shows its end
  await shot("l3-b-deep-analyst");
  await page.locator(".rr-modes .rr-seg-btn[data-value=fan]").click();
  await page.waitForTimeout(1500);
  await shot("l3-c-deep-fan");
  await page.locator("#footer").screenshot({ path: join(out, "l3-d-timeline.png") });
  await page.locator(".rr-tl-dot").nth(2).click();
  await page.waitForTimeout(2500);
  await shot("l3-e-timeline-event-selected");
}
await page.goto(`${base}?moment=SYN-0007-turnover_to_shot-1&step=1`);
await page.waitForFunction(() => "replayRoom" in window, null, { timeout: 30000 });
await page.waitForTimeout(3500);
await page.locator(".rr-expand").click();
await page.waitForTimeout(2500);
await shot("l3-f-marking-broken");

// v3 (d): the wide default framing of a step, and (e) two consecutive playback frames, 100 ms apart
await open(`step=${at.assist}`, 3500);
await shot("v3-d-wide-step");
await open("play=1", 6000);
probe.motion = [];
for (const k of [0, 1]) {
  await shot(`v3-e-playback-${k}`);
  probe.motion.push(await page.evaluate(() => {
    const { viewer, scene } = window.replayRoom;
    const id = "EPA-11";
    const m = scene.markers.get(id).root.position;
    return { clockPos: +viewer.clock.pos.toFixed(3), x: +m.x.toFixed(3), z: +m.z.toFixed(3) };
  }));
  await page.waitForTimeout(100);
}

// v3: the card at rest (compact), expanded (the full reasoning), and the evidence drill-down open on the flaw
if (at.flaw) {
  await open(`step=${at.flaw}`, 3500);
  await shot("v3-a-compact-card");
  await page.locator(".rr-expand").click();
  await page.waitForTimeout(600);
  await shot("v3-b-expanded-card");
  await page.locator(".rr-claim").click();
  await page.waitForTimeout(2500);
  await shot("v3-c-evidence-open");
  await page.locator(".rr-evidence").screenshot({ path: join(out, "v3-c-evidence-panel.png") });
  await page.locator(".rr-mode-fan, .rr-modes .rr-seg-btn[data-value=fan]").first().click();
  await page.waitForTimeout(800);
  await shot("v3-c2-evidence-open-fan");
}
// v3 (d): the wide default framing of a step, and (e) two consecutive playback frames, 100 ms apart
await open(`step=${at.assist}`, 3500);
await shot("v3-d-wide-step");
await open("play=1", 6000);
probe.motion = [];
for (const k of [0, 1]) {
  await shot(`v3-e-playback-${k}`);
  probe.motion.push(await page.evaluate(() => {
    const { viewer, scene } = window.replayRoom;
    const id = "EPA-11";
    const m = scene.markers.get(id).root.position;
    return { clockPos: +viewer.clock.pos.toFixed(3), x: +m.x.toFixed(3), z: +m.z.toFixed(3) };
  }));
  await page.waitForTimeout(100);
}

// motion: 30 consecutive rendered frames of one running player: no jump bigger than the speed allows, and the
// figure facing within a few degrees of its velocity
await open("play=1", 5000);
probe.frames = await page.evaluate(async () => {
  const { viewer, scene } = window.replayRoom;
  const id = "EPA-11";
  const i = scene.markers.get(id).index;
  const out = [];
  for (let k = 0; k < 30; k++) {
    await new Promise((r) => requestAnimationFrame(r));
    const p = scene.markers.get(id).root.position;
    const s = viewer.samples().get(id);
    const v = s ? Math.atan2(s.vx, s.vy) : null;
    out.push({ pos: +viewer.clock.pos.toFixed(3), x: p.x, z: p.z, speed: s ? Math.hypot(s.vx, s.vy) : 0,
               heading: scene.bodies.heading[i], velocity: v });
  }
  const steps = out.slice(1).map((f, k) => Math.hypot(f.x - out[k].x, f.z - out[k].z));
  // implied speed: distance over the clock time between frames (a teleport would imply an impossible speed)
  const implied = out.slice(1).map((f, k) => (f.pos > out[k].pos
    ? steps[k] / ((f.pos - out[k].pos) / viewer.clock.fps) : 0));
  const turn = out.filter((f) => f.speed > 1).map((f) => {
    const d = Math.atan2(Math.sin(f.heading - f.velocity), Math.cos(f.heading - f.velocity));
    return Math.abs(d) * 180 / Math.PI;
  });
  return { frames: out.length, fractional: out.filter((f) => f.pos % 1 > 0.01).length,
           maxStepM: +Math.max(...steps).toFixed(3), maxImpliedSpeed: +Math.max(...implied).toFixed(2),
           maxObservedSpeed: +Math.max(...out.map((f) => f.speed)).toFixed(2),
           maxFacingErrorDeg: turn.length ? +Math.max(...turn).toFixed(1) : null };
});

// (h) a close-up of the figures: the camera pulled in on the focused player of the assist step
await open(`step=${at.assist}`, 3000);
await page.evaluate(() => {
  const { scene } = window.replayRoom;
  const p = scene.markers.get(scene.highlighted[0]).root.position;
  scene.desiredTarget = null; // stop the eased focus so the manual pose holds
  scene.desiredRadius = null;
  scene.camera.setTarget(p.clone());
  scene.camera.beta = 1.2;
  scene.camera.radius = 11;
});
await page.waitForTimeout(1500);
await shot("h-closeup");

// probes: what a still cannot show
await open("", 1500);
probe.fonts = await page.evaluate(() => {
  const sizes = new Map();
  for (const e of document.querySelectorAll("body *")) {
    if (![...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
    const px = getComputedStyle(e).fontSize;
    sizes.set(px, (sizes.get(px) ?? 0) + 1);
  }
  return Object.fromEntries([...sizes].sort());
});
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
probe.story = await page.evaluate(async () => {
  const { viewer } = window.replayRoom;
  viewer.story.reset();
  document.querySelector(".rr-cta").click();
  const out = [];
  for (let k = 0; k < 6; k++) {
    out.push([viewer.story.index, viewer.story.state, document.querySelector(".rr-ribbon-fill").style.width]);
    await new Promise((r) => setTimeout(r, 1000));
  }
  return out;
});

// the keyboard: make the page scrollable (a tall spacer), prove a key that scrolls does scroll (PageDown), then
// Space, from a focused button and from the page, must play / pause without moving it; arrows must step.
await page.setViewportSize({ width: 1280, height: 520 });
await open("", 1500);
probe.keys = await (async () => {
  await page.evaluate(() => {
    const spacer = document.createElement("div");
    spacer.id = "probe-spacer";
    spacer.style.height = "2000px";
    document.body.append(spacer);
    document.documentElement.style.overflow = "auto";
    document.body.style.overflow = "visible";
    document.body.style.height = "auto";
  });
  const state = () => page.evaluate(() => {
    const { viewer } = window.replayRoom;
    const doc = document.scrollingElement;
    return { scrollY: Math.round(window.scrollY), scrollable: doc.scrollHeight > doc.clientHeight,
             playing: viewer.story.playing, index: viewer.story.index };
  });
  await page.mouse.click(640, 300);
  await page.keyboard.press("PageDown");
  await page.waitForTimeout(400);
  const control = await state(); // the page can scroll
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(200);
  await page.locator(".rr-cta").focus(); // a focused button is the hard case
  await page.keyboard.press("Space");
  await page.waitForTimeout(400);
  const afterPlay = await state();
  await page.mouse.click(640, 300);
  await page.keyboard.press("Space");
  await page.waitForTimeout(400);
  const afterPause = await state();
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(300);
  const afterRight = await state();
  await page.keyboard.press("ArrowLeft");
  await page.waitForTimeout(300);
  const afterLeft = await state();
  return { control, afterPlay, afterPause, afterRight, afterLeft };
})();
await shot("l-keyboard-short-window");
console.log(JSON.stringify(probe));

await browser.close();
if (errors.length) {
  console.error(errors.join("\n"));
  process.exitCode = 1;
}
console.log(`wrote ${out}/ (${at.n} story steps)`);
