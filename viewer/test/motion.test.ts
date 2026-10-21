import { describe, expect, it } from "vitest";
import type { Track } from "../src/bundle";
import { sampleTrack } from "../src/motion";

const track = (x: (number | null)[], vx: (number | null)[]): Track => ({
  x,
  y: x.map((v) => (v === null ? null : 0)),
  vx,
  vy: vx.map((v) => (v === null ? null : 0)),
});

describe("sampleTrack", () => {
  it("passes exactly through every observed frame", () => {
    const t = track([0, 1, 2.5], [10, 12, 15]);
    for (const i of [0, 1, 2]) expect(sampleTrack(t, i, 10)).toMatchObject({ x: t.x[i], observed: true });
  });

  it("uses velocities between frames (Hermite), not straight lines", () => {
    const rest = track([0, 1], [0, 0]); // at rest at both ends: eases in, so a quarter in is short of 0.25
    const s = sampleTrack(rest, 0.25, 10)!;
    expect(s.observed).toBe(true);
    expect(s.x).toBeLessThan(0.25);
    const steady = track([0, 1], [10, 10]); // a steady 10 m/s at 10 Hz: Hermite is exactly linear
    expect(sampleTrack(steady, 0.25, 10)!.x).toBeCloseTo(0.25);
  });

  it("crosses a gap linearly and says so", () => {
    const t = track([0, null, null, 3], [0, null, null, 0]);
    const s = sampleTrack(t, 1.5, 10)!;
    expect(s.observed).toBe(false);
    expect(s.x).toBeCloseTo(1.5);
  });

  it("never extrapolates beyond the observations", () => {
    const t = track([null, 1, 2, null], [null, 0, 0, null]);
    expect(sampleTrack(t, 0, 10)).toBeNull();
    expect(sampleTrack(t, 3, 10)).toBeNull();
    expect(sampleTrack(t, 2.5, 10)).toBeNull();
    expect(sampleTrack(t, -1, 10)).toBeNull();
  });
});
