import { NullEngine } from "@babylonjs/core/Engines/nullEngine";
import { describe, expect, it } from "vitest";
import { Viewer } from "../src/controller";
import { PitchScene } from "../src/scene";
import { fixture } from "./helpers";

describe("PitchScene (headless)", () => {
  it("builds one marker per tracked object and places them at the observed positions", () => {
    const b = fixture();
    const scene = new PitchScene(new NullEngine(), b, { labels: false });
    expect(scene.markers.size).toBe(b.objects.length);
    new Viewer(b, scene).frame(0);
    const m = scene.markers.get("EPA-11")!;
    expect(m.root.isEnabled()).toBe(true);
    expect(m.root.position.x).toBeCloseTo(b.tracks["EPA-11"].x[0]! - b.pitch.length / 2);
    expect(m.root.position.z).toBeCloseTo(b.tracks["EPA-11"].y[0]! - b.pitch.width / 2);
    scene.render();
  });

  it("highlights and draws overlays for a jump", () => {
    const b = fixture();
    const scene = new PitchScene(new NullEngine(), b, { labels: false });
    const v = new Viewer(b, scene);
    v.jump(b.account.counterfactuals[0].contribution_id);
    const rings = [...scene.markers.entries()].filter(([, m]) => m.ring?.isVisible).map(([id]) => id);
    expect(rings).toEqual(scene.highlighted);
    expect(scene.overlayMeshes.length).toBeGreaterThan(4);
    v.clear();
    expect([...scene.markers.values()].some((m) => m.ring?.isVisible)).toBe(false);
  });
});
