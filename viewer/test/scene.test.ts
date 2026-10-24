import { NullEngine } from "@babylonjs/core/Engines/nullEngine";
import { describe, expect, it } from "vitest";
import { Viewer } from "../src/controller";
import { PitchScene } from "../src/scene";
import { fixture } from "./helpers";

describe("PitchScene (headless)", () => {
  it("draws 22 players as thin instances of one figure and places them at the observed positions", () => {
    const b = fixture();
    const scene = new PitchScene(new NullEngine(), b, { labels: false });
    expect(scene.markers.size).toBe(b.objects.length);
    const players = b.objects.filter((o) => o.kind === "player").length;
    expect(players).toBe(22);
    expect(scene.bodies.kind).toBe("figure");
    expect(scene.bodies.parts.map((p) => p.slot)).toEqual(["body", "shirt", "shorts"]); // one shared figure...
    for (const p of scene.bodies.parts) expect(p.mesh.thinInstanceCount).toBe(players); // ...drawn 22 times
    expect(scene.shirt(b.goalkeepers[0])).not.toBe(scene.shirt(b.objects.find((o) => o.kind === "player" && !b.goalkeepers.includes(o.id))!.id));
    new Viewer(b, scene).frame(0);
    const m = scene.markers.get("EPA-11")!;
    expect(m.root.isEnabled()).toBe(true);
    expect(m.root.position.x).toBeCloseTo(b.tracks["EPA-11"].x[0]! - b.pitch.length / 2);
    expect(m.root.position.z).toBeCloseTo(b.tracks["EPA-11"].y[0]! - b.pitch.width / 2);
    scene.render();
  });

  it("puts the pitch in a stadium only when asked, and keeps it out of picking", () => {
    const b = fixture();
    expect(new PitchScene(new NullEngine(), b, { labels: false }).stadium).toHaveLength(0);
    const scene = new PitchScene(new NullEngine(), b, { labels: false, stadium: true });
    const names = scene.stadium.map((m) => m.name);
    for (const side of ["north", "south", "east", "west"]) expect(names).toContain(`stand-${side}`);
    expect(names.filter((n) => n.startsWith("tower"))).toHaveLength(4);
    expect(names).toContain("sky");
    expect(scene.stadium.every((m) => !m.isPickable)).toBe(true);
    // the stands start beyond the apron: nothing overlaps the field of play
    for (const m of scene.stadium.filter((x) => x.name.startsWith("stand-"))) {
      const box = m.getBoundingInfo().boundingBox;
      const clearX = box.minimumWorld.x > b.pitch.length / 2 || box.maximumWorld.x < -b.pitch.length / 2;
      const clearZ = box.minimumWorld.z > b.pitch.width / 2 || box.maximumWorld.z < -b.pitch.width / 2;
      expect(clearX || clearZ).toBe(true);
    }
    scene.render();
  });

  it("rings the focus, dims everyone else, and draws the jump", () => {
    const b = fixture();
    const scene = new PitchScene(new NullEngine(), b, { labels: false });
    const v = new Viewer(b, scene);
    v.jump(b.account.counterfactuals[0].contribution_id);
    const rings = [...scene.markers.entries()].filter(([, m]) => m.ring?.isVisible).map(([id]) => id);
    expect(rings).toEqual(scene.highlighted);
    const dimmed = [...scene.markers.entries()].filter(([, m]) => m.index >= 0 && scene.bodies.isDimmed(m.index)).map(([id]) => id);
    expect(dimmed).toHaveLength(22 - scene.highlighted.length);
    expect(dimmed.some((id) => scene.highlighted.includes(id))).toBe(false);
    expect(scene.overlayMeshes.length).toBeGreaterThan(2);
    v.clear();
    expect([...scene.markers.values()].some((m) => m.ring?.isVisible)).toBe(false);
    expect(scene.overlayMeshes).toHaveLength(0);
  });
});
