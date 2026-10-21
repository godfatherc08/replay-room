// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { evidenceRows, highlightedPlayers, matchClock } from "../src/account";
import { type SceneLike, Viewer } from "../src/controller";
import type { Sample } from "../src/motion";
import type { Overlay, Vec2 } from "../src/overlays";
import { buildUI } from "../src/ui";
import { fixture } from "./helpers";

class FakeScene implements SceneLike {
  samples = new Map<string, Sample | null>();
  highlighted: string[] = [];
  overlays: Overlay[] = [];
  focused: Vec2[] = [];
  update(s: Map<string, Sample | null>) {
    this.samples = s;
  }
  setHighlight(ids: string[]) {
    this.highlighted = ids;
  }
  setOverlays(o: Overlay[]) {
    this.overlays = o;
  }
  focus(p: Vec2[]) {
    this.focused = p;
  }
  step() {}
}

describe("viewer", () => {
  it("jumping to a contribution seeks to its frame, highlights its players and frames them", () => {
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

function shell(b = fixture(), opts: Parameters<typeof buildUI>[2] = {}) {
  const v = new Viewer(b, new FakeScene());
  const roots = { topbar: div(), rail: div(), stage: div(), side: div(), footer: div() };
  const memory = new Map<string, string>();
  const storage = { getItem: (k: string) => memory.get(k) ?? null, setItem: (k: string, x: string) => void memory.set(k, x) };
  const ui = buildUI(roots, v, { storage, ...opts });
  const all = () => Object.values(roots).map((r) => r.textContent ?? "").join(" ");
  return { b, v, roots, ui, all, memory };
}

function div(): HTMLDivElement {
  return document.createElement("div");
}

describe("app shell", () => {
  it("binds the header, evidence and summary to the bundle", () => {
    const { b, roots } = shell();
    const side = roots.side;
    expect(side.querySelector(".rr-moment-class")!.textContent).toBe("BIG CHANCE SAVED");
    expect(side.querySelector(".rr-chip")!.textContent).toBe("PREVENTED");
    expect(side.querySelector(".rr-moment-meta")!.textContent).toBe(`xG ${b.account.outcome.value.toFixed(3)} · ${b.match.moment_clock}`);
    expect(side.querySelector(".rr-desc")!.textContent).toBe(b.narration!.headline_text);
    const rows = [...side.querySelectorAll<HTMLButtonElement>(".rr-evidence-row")];
    expect(rows.map((r) => r.dataset.id)).toEqual(evidenceRows(b).map((r) => r.id));
    const head = rows.filter((r) => r.classList.contains("rr-headline"));
    expect(head.map((r) => r.dataset.id)).toEqual([b.account.headline_contribution_id]);
    const lead = b.narration!.sentences.slice(0, 3).map((s) => s.text).join(" ");
    expect(side.querySelector(".rr-summary-text")!.textContent).toBe(lead);
    expect(roots.topbar.querySelector(".rr-team-name")!.textContent).toBe(b.match.home.name);
  });

  it("shows no number the bundle does not contain", () => {
    const { b, roots } = shell();
    const allowed = new Set<string>();
    const add = (v: number) => { for (const d of [0, 1, 2, 3]) allowed.add(Math.abs(v).toFixed(d)); };
    const walk = (x: unknown): void => {
      if (typeof x === "number") add(x);
      else if (typeof x === "string") (x.match(/\d+(?:\.\d+)?/g) ?? []).forEach((s) => allowed.add(s));
      else if (x && typeof x === "object") Object.values(x).forEach(walk);
    };
    walk(b);
    const chrome = new Set(["0.25", "0.5", "1", "2", ...evidenceRows(b).map((r) => String(r.number))]); // speeds, row ordinals
    const strangers: string[] = [];
    for (const root of Object.values(roots)) {
      const nodes = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      for (let n = nodes.nextNode(); n; n = nodes.nextNode()) {
        let text = n.textContent ?? "";
        for (const clock of text.match(/\b\d{2}:\d{2}\b/g) ?? []) {  // match clocks: must lie within the match
          const [m, s] = clock.split(":").map(Number);
          if (60 * m + s > b.match.duration_s) strangers.push(clock);
        }
        text = text.replace(/\b\d{2}:\d{2}\b/g, " ");
        for (const num of text.match(/\d+(?:\.\d+)?/g) ?? []) if (!allowed.has(num) && !chrome.has(num)) strangers.push(num);
      }
    }
    expect(strangers).toEqual([]);
  });

  it("clicking an evidence row seeks, highlights and marks it, and dismisses the hint", () => {
    const { v, roots, memory } = shell();
    const hint = roots.side.querySelector<HTMLElement>(".rr-hint")!;
    expect(hint.hidden).toBe(false);
    const row = [...roots.side.querySelectorAll<HTMLButtonElement>(".rr-evidence-row")][2];
    row.click();
    expect(v.clock.frameId).toBe(Number(row.dataset.frame));
    expect(v.active).toBe(row.dataset.id);
    expect(row.classList.contains("rr-active")).toBe(true);
    expect(hint.hidden).toBe(true);
    expect(memory.get("replay-room.hint-dismissed")).toBe("1");
    expect(roots.footer.querySelector(".rr-now")!.textContent).toBe(matchClock(v.bundle, v.clock.time));
  });

  it("fan mode is a seam: header and summary only", () => {
    const { roots, ui } = shell();
    ui.state.setMode("fan");
    expect(roots.side.querySelector(".rr-evidence-row")).toBeNull();
    expect(roots.side.querySelector(".rr-summary")).not.toBeNull();
    expect(roots.side.querySelector(".rr-moment")).not.toBeNull();
    ui.state.setMode("analyst");
    expect(roots.side.querySelector(".rr-evidence-row")).not.toBeNull();
  });

  it("leaves out what the bundle lacks", () => {
    const b = fixture();
    b.narration = null;
    b.account.counterfactuals = [];
    const { roots, ui } = shell(b);
    expect(roots.side.querySelector(".rr-summary")).toBeNull();
    expect(roots.side.querySelector(".rr-desc")).toBeNull();
    ui.state.setTab("tactics");
    expect(roots.side.querySelector(".rr-cf")).toBeNull();
  });

  it("lists the match's moments and opens one on click", () => {
    const picked: string[] = [];
    const { b, roots } = shell(fixture(), { onPick: (id) => picked.push(id) });
    roots.rail.querySelector<HTMLButtonElement>('[data-rail="moments"]')!.click();
    const items = [...roots.side.querySelectorAll<HTMLButtonElement>(".rr-moment-item")];
    expect(items).toHaveLength(b.match_moments.length);
    items.find((i) => !i.disabled)!.click();
    expect(picked).toHaveLength(1);
    expect(roots.footer.querySelectorAll(".rr-strip-mark")).toHaveLength(b.match_moments.length);
  });
});
