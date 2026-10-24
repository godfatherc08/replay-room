// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { evidenceRows, firstSentence, highlightedPlayers, matchClock, stepPlayers } from "../src/account";
import { type SceneLike, Viewer } from "../src/controller";
import type { Sample } from "../src/motion";
import { type Overlay, stepOverlays, type Vec2 } from "../src/overlays";
import { buildUI } from "../src/ui";
import { fixture } from "./helpers";

class FakeScene implements SceneLike {
  samples = new Map<string, Sample | null>();
  highlighted: string[] = [];
  label: [string | null, string | undefined] = [null, undefined];
  overlays: Overlay[] = [];
  focused: Vec2[] = [];
  update(s: Map<string, Sample | null>) {
    this.samples = s;
  }
  setHighlight(ids: string[]) {
    this.highlighted = ids;
  }
  labels: string[] = [];
  setLabel(id: string | null, text?: string) {
    this.label = [id, text];
  }
  setLabels(entries: { id: string; text: string }[]) {
    this.labels = entries.map((e) => e.text);
  }
  setOverlays(o: Overlay[]) {
    this.overlays = o;
  }
  focus(p: Vec2[]) {
    this.focused = p;
  }
  step() {}
}

/** Run the viewer's frame loop for this many seconds of wall time. */
function run(v: Viewer, seconds: number, dt = 1 / 30) {
  for (let t = 0; t < seconds; t += dt) v.frame(dt);
}

describe("viewer: Explore", () => {
  it("jumping to a contribution seeks to its frame, focuses its players, names the first, and frames them", () => {
    const b = fixture();
    const scene = new FakeScene();
    const v = new Viewer(b, scene);
    v.clock.play();
    for (const c of b.account.contributions) {
      v.jump(c.contribution_id);
      const frame = b.jumps.find((j) => j.contribution_id === c.contribution_id)!.frame_id;
      expect(v.clock.frameId).toBe(frame);
      expect(v.clock.playing).toBe(false);
      expect(scene.highlighted).toEqual(highlightedPlayers(c));
      expect(scene.label[0]).toBe(c.player_id);
      expect(scene.focused.length).toBeGreaterThan(0);
    }
  });

  it("animates every object from its track", () => {
    const b = fixture();
    const scene = new FakeScene();
    new Viewer(b, scene).frame(0);
    expect(scene.samples.size).toBe(b.objects.length);
    expect(scene.samples.get("EPA-11")).toMatchObject({ x: b.tracks["EPA-11"].x[0], observed: true });
  });

  it("stepping walks the evidence in story order", () => {
    const b = fixture();
    const v = new Viewer(b, new FakeScene());
    const order = evidenceRows(b).map((r) => r.id);
    expect(v.stepEvidence(1)).toBe(order[0]);
    expect(v.stepEvidence(1)).toBe(order[1]);
    expect(v.stepEvidence(-1)).toBe(order[0]);
  });
});

describe("viewer: Story", () => {
  it("opens with nothing drawn and nobody in focus", () => {
    const scene = new FakeScene();
    const v = new Viewer(fixture(), scene);
    expect(v.story.state).toBe("ready");
    expect(scene.overlays).toEqual([]);
    expect(scene.highlighted).toEqual([]);
  });

  it("each step leads the replay into its frame, then draws that step's overlay alone", () => {
    const b = fixture();
    const scene = new FakeScene();
    const v = new Viewer(b, scene);
    v.story.goto(0);
    const step = b.story[0];
    expect(scene.highlighted).toEqual(stepPlayers(b, step));
    expect(v.clock.playing).toBe(true); // the lead-in
    expect(scene.overlays).toEqual([]);
    run(v, 2);
    expect(v.clock.frameId).toBe(step.frame_id);
    expect(scene.overlays).toEqual(stepOverlays(b, step));
  });

  it("plays the whole account in order and climaxes on the outcome and the counterfactual", () => {
    const b = fixture();
    const scene = new FakeScene();
    const v = new Viewer(b, scene);
    const seen: number[] = [];
    v.story.onChange((s) => (seen.at(-1) !== s.index ? seen.push(s.index) : 0));
    v.story.play();
    run(v, 120, 0.1);
    expect(seen).toEqual(b.story.map((s) => s.index));
    expect(v.story.state).toBe("done");
    const last = b.story.at(-1)!;
    expect(last.kind).toBe("counterfactual");
    expect(v.clock.frameId).toBe(last.frame_id);
    expect(scene.overlays).toEqual(stepOverlays(b, last, "analyst"));
    expect(scene.highlighted).toEqual(["EPA-08", "EPA-09"]);
  });

  it("Fan mode redraws the decision without values", () => {
    const b = fixture();
    const scene = new FakeScene();
    const v = new Viewer(b, scene);
    v.story.goto(b.story.length - 1);
    run(v, 3);
    v.setMode("fan");
    const labels = scene.overlays.map((o) => ("label" in o ? o.label : undefined)).filter(Boolean);
    expect(labels).toEqual(["Chosen", "Better option"]);
  });
});

function shell(b = fixture(), opts: Parameters<typeof buildUI>[2] = {}) {
  const v = new Viewer(b, new FakeScene());
  const roots = { topbar: div(), stage: div(), ribbon: div(), side: div(), footer: div() };
  const keys = opts.keys ?? new EventTarget(); // keep each shell's shortcuts to itself
  const ui = buildUI(roots, v, { ...opts, keys });
  return { b, v, roots, ui, keys };
}

function div(): HTMLDivElement {
  return document.createElement("div");
}

function texts(root: HTMLElement): string[] {
  const out: string[] = [];
  const nodes = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = nodes.nextNode(); n; n = nodes.nextNode()) out.push(n.textContent ?? "");
  return out;
}

describe("app shell", () => {
  it("opens on the title card: class, outcome, the narration's line, and Play analysis", () => {
    const { b, roots } = shell();
    const card = roots.stage.querySelector<HTMLElement>(".rr-title-card")!;
    expect(card.hidden).toBe(false);
    expect(roots.stage.querySelector<HTMLElement>(".rr-step-card")!.hidden).toBe(true);
    expect(card.querySelector(".rr-class-chip")!.textContent).toBe("BIG CHANCE SAVED");
    expect(card.querySelector(".rr-display")!.textContent).toBe("A goal that didn't happen");
    expect(card.querySelector(".rr-lede")!.textContent).toBe("Ferraro misses a good chance for Eastport."); // no repeat
    expect(b.narration.headline).toBe("A goal that didn't happen: Ferraro misses a good chance for Eastport.");
    expect(card.querySelector(".rr-cta")!.textContent).toBe("Play analysis");
  });

  it("Play analysis swaps the title card for a compact step card: the claim and its evidence status", () => {
    const { b, v, roots, ui } = shell();
    roots.stage.querySelector<HTMLButtonElement>(".rr-cta")!.click();
    expect(v.story.playing).toBe(true);
    const card = roots.stage.querySelector<HTMLElement>(".rr-step-card")!;
    expect(card.hidden).toBe(false);
    expect(card.querySelector(".rr-claim")!.textContent).toBe(firstSentence(b.story[0].caption));
    expect(card.querySelector(".rr-evidence-chip")!.textContent).toBe("✓Evidence · 1 event · frame 2354");
    expect(card.querySelector(".rr-detail")).toBeNull(); // compact at rest
    expect(card.querySelector(".rr-counter")!.textContent).toBe(`Step 1 of ${b.story.length}`);
    run(v, 3.2);
    ui.sync();
    expect(v.story.index).toBe(1);
    const nodes = [...roots.ribbon.querySelectorAll(".rr-node")];
    expect(nodes).toHaveLength(b.story.length);
    expect(nodes[0].classList.contains("rr-done")).toBe(true);
    expect(nodes[1].classList.contains("rr-current")).toBe(true);
    expect(parseFloat(roots.ribbon.querySelector<HTMLElement>(".rr-ribbon-fill")!.style.width)).toBeGreaterThan(0);
  });

  it("the ribbon has one node per step, marks the headline, and a click shows that step", () => {
    const { b, v, roots, ui } = shell();
    ui.state.setView("explore");
    const nodes = [...roots.ribbon.querySelectorAll<HTMLElement>(".rr-node")];
    const head = b.story.findIndex((s) => s.emphasis === "lead");
    expect(nodes.map((n, i) => (n.classList.contains("rr-headline") ? i : -1)).filter((i) => i >= 0)).toEqual([head]);
    nodes[4].querySelector<HTMLButtonElement>("button")!.click();
    expect(ui.state.view).toBe("story");
    expect(v.story.index).toBe(4);
    expect(v.active).toBe(b.story[4].contribution_id);
  });

  it("Fan mode shows no raw metric anywhere; Analyst shows them as secondary text", () => {
    const { b, roots, ui } = shell(fixture(), { mode: "fan" });
    ui.state.setView("explore"); // the open chain: every fact's row
    const step = b.story.length - 1;
    const fanText = () => Object.values(roots).flatMap(texts).join(" ").replace(/\d(\.\d)?×/g, ""); // speeds are not metrics
    expect(roots.side.querySelectorAll(".rr-row")).toHaveLength(b.account.contributions.length);
    expect(fanText()).not.toMatch(/\d\.\d/);
    expect(roots.side.querySelectorAll(".rr-metric")).toHaveLength(0);
    ui.state.setView("story");
    roots.ribbon.querySelectorAll<HTMLButtonElement>(".rr-node-btn")[step].click();
    ui.state.setExpanded(true);
    roots.stage.querySelector<HTMLButtonElement>(".rr-evidence-chip")!.click(); // the proof, in Fan words
    expect(roots.side.querySelector(".rr-evidence")).not.toBeNull();
    expect(fanText()).not.toMatch(/\d\.\d/);
    ui.state.setMode("analyst");
    expect(roots.stage.querySelectorAll(".rr-step-card .rr-metric")).toHaveLength(2);
    expect(roots.stage.querySelector(".rr-step-card .rr-metric")!.textContent).toMatch(/^option value 0\.097/);
  });

  it("every value in the chain is a meter with a gloss", () => {
    const { roots, ui } = shell();
    ui.state.setView("explore");
    for (const row of roots.side.querySelectorAll(".rr-row")) {
      expect(row.querySelector(".rr-meter")).not.toBeNull();
      expect(row.querySelector(".rr-row-gloss")!.textContent).not.toBe("");
    }
  });

  it("shows no number the bundle does not contain", () => {
    for (const mode of ["analyst", "fan"] as const) {
      const { b, roots, ui } = shell(fixture(), { mode });
      ui.state.setView("explore");
      const allowed = new Set<string>();
      const add = (v: number) => { for (const d of [0, 1, 2, 3]) allowed.add(Math.abs(v).toFixed(d)); };
      const walk = (x: unknown): void => {
        if (typeof x === "number") add(x);
        else if (typeof x === "string") (x.match(/\d+(?:\.\d+)?/g) ?? []).forEach((s) => allowed.add(s));
        else if (x && typeof x === "object") Object.values(x).forEach(walk);
      };
      walk(b);
      const chrome = new Set(["0.5", "1", "1.5", "2", "2D", "3D", ...b.story.map((s) => String(s.index + 1))]); // speeds, steps
      const strangers: string[] = [];
      for (const story of [false, true]) {
        if (story) {
          ui.state.setView("story");
          roots.ribbon.querySelectorAll<HTMLButtonElement>(".rr-node-btn")[b.story.length - 1].click();
        }
        for (const root of Object.values(roots)) {
          for (let text of texts(root)) {
            for (const clock of text.match(/\b\d{2}:\d{2}\b/g) ?? []) {  // match clocks: must lie within the match
              const [m, s] = clock.split(":").map(Number);
              if (60 * m + s > b.match.duration_s) strangers.push(clock);
            }
            text = text.replace(/\b\d{2}:\d{2}\b/g, " ");
            for (const num of text.match(/\d+(?:\.\d+)?/g) ?? []) if (!allowed.has(num) && !chrome.has(num)) strangers.push(num);
          }
        }
      }
      expect(strangers).toEqual([]);
    }
  });

  it("clicking a fact in the chain switches to Explore, seeks, focuses and marks it", () => {
    const { v, roots, ui } = shell();
    ui.state.setView("explore");
    const row = [...roots.side.querySelectorAll<HTMLButtonElement>(".rr-row")][2];
    row.click();
    expect(ui.state.view).toBe("explore");
    expect(v.clock.frameId).toBe(Number(row.dataset.frame));
    expect(v.active).toBe(row.dataset.id);
    expect(row.classList.contains("rr-active")).toBe(true);
    expect(roots.footer.querySelector(".rr-tl-clock")!.textContent).toBe(`${matchClock(v.bundle, v.clock.time)} / 05:00`);
  });

  it("Space plays and pauses without scrolling the page; Left / Right step between beats", () => {
    const { v, ui, keys } = shell();
    const press = (key: string, target: EventTarget = keys, type = "keydown") => {
      const e = new KeyboardEvent(type, { key, code: key === " " ? "Space" : key, cancelable: true, bubbles: true });
      Object.defineProperty(e, "target", { value: target });
      keys.dispatchEvent(e);
      return e;
    };
    const space = press(" ");
    expect(space.defaultPrevented).toBe(true); // the browser's scroll-on-space never runs
    expect(v.story.playing).toBe(true);
    expect(press(" ", keys, "keyup").defaultPrevented).toBe(true); // nor a focused button's click
    press(" ");
    expect(v.story.playing).toBe(false);
    const at = v.story.index;
    expect(press("ArrowRight").defaultPrevented).toBe(true);
    expect(v.story.index).toBe(at + 1);
    press("ArrowLeft");
    expect(v.story.index).toBe(at);
    const input = document.createElement("input"); // typing is left alone
    expect(press(" ", input).defaultPrevented).toBe(false);
    ui.state.setView("explore"); // Explore: Space plays / pauses the replay itself
    const was = v.clock.playing;
    press(" ");
    expect(v.clock.playing).toBe(!was);
    press("ArrowRight");
    expect(v.active).not.toBeNull();
  });

  it("tells the flaw and the context as their own beats on the ribbon", () => {
    const { b, roots } = shell();
    const nodes = [...roots.ribbon.querySelectorAll<HTMLElement>(".rr-node")];
    const flaw = b.story.findIndex((s) => s.kind === "flaw");
    const ctx = b.story.findIndex((s) => s.kind === "context");
    expect(nodes[flaw].classList.contains("rr-flaw")).toBe(true);
    expect(nodes[ctx].querySelector(".rr-node-label")!.textContent).toBe("Context");
    nodes[ctx].querySelector<HTMLButtonElement>("button")!.click();
    const card = roots.stage.querySelector<HTMLElement>(".rr-step-card")!;
    expect(card.querySelector(".rr-headline-chip")!.textContent).toBe("Match context");
    card.querySelector<HTMLButtonElement>(".rr-expand")!.click(); // the full reasoning, on demand
    const open = roots.stage.querySelector<HTMLElement>(".rr-step-card")!;
    expect([...open.querySelectorAll(".rr-gloss")].map((g) => g.textContent)).toEqual(["Here", "Usually"]);
    expect(open.querySelector(".rr-why-line")!.textContent).toMatch(/^Northbridge FC's back line was 16\.3 m/);
  });

  it("clicking a claim opens its proof: players ringed and named, the frame, what was measured, the records", () => {
    const { b, v, roots } = shell();
    const scene = v.scene as FakeScene;
    const flaw = b.story.findIndex((s) => s.kind === "flaw");
    roots.ribbon.querySelectorAll<HTMLButtonElement>(".rr-node-btn")[flaw].click();
    roots.stage.querySelector<HTMLButtonElement>(".rr-claim")!.click();
    const proof = b.proofs.beats[b.story[flaw].beat_id];
    expect(v.proof).toBe(proof);
    expect(v.clock.frameId).toBe(2419); // the frame the link ends at
    expect(v.story.playing).toBe(false);
    expect(scene.highlighted).toEqual(["NBR-05", "EPA-11", "EPA-08"]); // Novak, the runner, the passer
    expect(scene.labels).toEqual(["#5 Novak", "#11 Ferraro", "#8 Hale"]);
    expect(scene.overlays.length).toBeGreaterThan(0); // the link stays drawn
    const box = roots.side.querySelector<HTMLElement>(".rr-evidence")!;
    const text = box.textContent!;
    expect(text).toContain("space worth +0.012 of a scoring chance"); // the measured change, with its meaning
    expect(text).toContain("frame 2419");
    expect(text).toContain("ev00220 · pass · Robin Hale"); // the feed's own event id
    expect([...box.querySelectorAll(".rr-player-chip")].map((c) => c.textContent)).toEqual(
      ["#5 Jordan Novakdefender", "#11 Jordan Ferrarorunner", "#8 Robin Haleused the space"]);
    box.querySelector<HTMLButtonElement>(".rr-icon-btn")!.click(); // close: back to the step
    expect(v.proof).toBeNull();
    expect(roots.side.querySelector(".rr-evidence")).toBeNull();
  });

  it("a fact in the chain opens its own proof", () => {
    const { v, roots, ui } = shell();
    ui.state.setView("explore");
    roots.side.querySelector<HTMLButtonElement>('.rr-row[data-id="a157"]')!.click();
    expect(v.proof).not.toBeNull();
    expect(roots.side.querySelector(".rr-evidence")!.textContent).toContain(
      "Sam Adeyemi's pass raised Eastport Athletic's chance of scoring by 0.087 (VAEP): the largest of the 8 facts");
  });

  it("the chain is collapsed in Story and open in Explore", () => {
    const { roots, ui } = shell();
    expect(roots.side.querySelector(".rr-row")).toBeNull();
    roots.side.querySelector<HTMLButtonElement>(".rr-section-toggle")!.click();
    expect(roots.side.querySelector(".rr-row")).not.toBeNull();
    ui.state.setView("explore");
    expect(roots.side.querySelector(".rr-row")).not.toBeNull();
  });

  it("leaves out what the bundle lacks", () => {
    const b = fixture();
    (b as { narration: unknown }).narration = null;
    b.account.counterfactuals = [];
    const { roots } = shell(b);
    expect(roots.side.querySelector(".rr-summary")).toBeNull();
    expect(roots.side.querySelector(".rr-decision")).toBeNull();
    expect(roots.stage.querySelector(".rr-lede")).toBeNull();
  });

  it("lists the match's moments and opens one", () => {
    const picked: string[] = [];
    const { b, roots } = shell(fixture(), { onPick: (id) => picked.push(id) });
    const picker = roots.topbar.querySelector<HTMLSelectElement>(".rr-picker")!;
    expect(picker.options).toHaveLength(b.match_moments.length);
    picker.value = b.match_moments.find((m) => m.moment_id !== b.account.moment.moment_id)!.moment_id;
    picker.dispatchEvent(new Event("change"));
    expect(picked).toHaveLength(1);
  });

  it("the Match Timeline: header and clock, amber progress, one coloured dot per event, the selected moment", () => {
    const { b, v, roots } = shell();
    const f = roots.footer;
    expect(f.querySelector(".rr-tl-title")!.textContent).toBe("MATCH TIMELINE");
    expect(f.querySelector(".rr-tl-clock")!.textContent).toBe(`${matchClock(b, v.clock.time)} / 05:00`);
    expect([...f.querySelectorAll(".rr-tl-label")].map((x) => x.textContent).slice(0, 2))
      .toEqual(["Replay progress", "Match events"]);
    expect([...f.querySelectorAll(".rr-tl-hint")].map((x) => x.textContent))
      .toEqual(["Drag to seek", "Select an event to jump to it"]);
    expect(f.querySelector<HTMLSelectElement>(".rr-speed")!.selectedOptions[0].textContent).toBe("1×");
    const dots = [...f.querySelectorAll<HTMLButtonElement>(".rr-tl-dot")];
    const inWindow = b.events.filter((e) => e.in_window);
    expect(dots.map((d) => d.dataset.event)).toEqual(inWindow.map((e) => e.original_event_id)); // the real events, only
    expect(dots.map((d) => d.dataset.kind)).toEqual(inWindow.map((e) => e.timeline));
    expect(new Set(dots.map((d) => d.dataset.kind))).toEqual(new Set(["build_up", "shot_outcome"])); // hero: no error event
    expect([...f.querySelectorAll(".rr-tl-key")].map((k) => k.textContent))
      .toEqual(["Pass / build-up", "Defensive error", "Shot / outcome"]);
    expect(f.querySelectorAll(".rr-tl-ticks span")).toHaveLength(5);
    const card = f.querySelector(".rr-tl-card")!;
    expect(card.querySelector(".rr-tl-label")!.textContent).toBe("Selected moment · 04:03");
    expect(card.querySelector(".rr-tl-claim")!.textContent).toBe("Ferraro misses a good chance for Eastport.");
    expect(card.querySelector(".rr-tl-metric")!.textContent).toBe("15% chance of scoring · xG 0.152");
    // a cited event's dot seeks to it and opens its proof
    const pass = dots.find((d) => d.dataset.event === "ev00220")!;
    pass.click();
    expect(v.proof).toBe(b.proofs.contributions.a161);
    expect(v.clock.frameId).toBe(b.proofs.contributions.a161.focus_frame);
    expect(roots.side.querySelector(".rr-evidence")).not.toBeNull();
  });

  it("the timeline's moment card drops the raw figure in Fan", () => {
    const { roots } = shell(fixture(), { mode: "fan" });
    expect(roots.footer.querySelector(".rr-tl-metric")!.textContent).toBe("15% chance of scoring");
  });
});
