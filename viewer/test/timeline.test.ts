import { describe, expect, it } from "vitest";
import { Clock } from "../src/timeline";

const clock = () => new Clock([100, 101, 102, 103], [9.0, 9.1, 9.2, 9.3], 10);

describe("Clock", () => {
  it("plays at the frame rate and speed, stopping at the end", () => {
    const c = clock();
    c.play();
    c.tick(0.1);
    expect(c.pos).toBeCloseTo(1);
    c.setSpeed(2);
    c.tick(0.05);
    expect(c.pos).toBeCloseTo(2);
    expect(c.time).toBeCloseTo(9.2);
    c.tick(10);
    expect(c.pos).toBe(3);
    expect(c.playing).toBe(false);
  });

  it("does not move while paused", () => {
    const c = clock();
    c.tick(1);
    expect(c.pos).toBe(0);
  });

  it("seeks only to frames of the window", () => {
    const c = clock();
    c.seekFrame(102);
    expect(c.frameId).toBe(102);
    expect(() => c.seekFrame(99)).toThrow(/not in the window/);
    c.seekIndex(-5);
    expect(c.pos).toBe(0);
  });

  it("restarts from the top when played at the end, and notifies listeners", () => {
    const c = clock();
    const seen: number[] = [];
    c.onChange((k) => seen.push(k.pos));
    c.seekIndex(3);
    c.play();
    expect(c.pos).toBe(0);
    expect(seen).toEqual([3, 0]);
  });
});
