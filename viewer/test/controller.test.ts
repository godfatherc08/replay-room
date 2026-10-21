// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { highlightedPlayers } from "../src/account";
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

  it("UI: the headline is listed first and clicking an item seeks to its frame", () => {
    const b = fixture();
    const v = new Viewer(b, new FakeScene());
    const root = document.createElement("div");
    buildUI(root, v);
    const items = [...root.querySelectorAll<HTMLButtonElement>(".rr-item")];
    expect(items).toHaveLength(b.account.contributions.length);
    expect(items[0].dataset.id).toBe(b.account.headline_contribution_id);
    expect(items[0].classList.contains("rr-headline")).toBe(true);
    const target = items[3];
    target.click();
    expect(v.clock.frameId).toBe(Number(target.dataset.frame));
    expect(v.active).toBe(target.dataset.id);
    expect(target.classList.contains("rr-active")).toBe(true);
    expect(root.querySelector<HTMLElement>(".rr-banner")!.dataset.framing).toBe("prevented");
    expect(root.querySelector(".rr-time")!.textContent).toContain(`frame ${target.dataset.frame}`);
  });
});
