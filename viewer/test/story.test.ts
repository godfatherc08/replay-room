import { describe, expect, it } from "vitest";
import { CLIMAX_DWELL, DEFAULT_DWELL, Story } from "../src/story";
import { fixture } from "./helpers";

describe("Story", () => {
  it("opens on the title card and walks every step in order on play", () => {
    const b = fixture();
    const seen: number[] = [];
    const s = new Story(b.story, (step) => seen.push(step.index));
    expect(s.state).toBe("ready");
    s.play();
    expect(s.index).toBe(0);
    for (let k = 0; k < 200 && s.playing; k++) s.tick(0.5);
    expect(seen).toEqual(b.story.map((x) => x.index));
    expect(s.state).toBe("done");
  });

  it("dwells the default time per step, longer on the climax, scaled by speed", () => {
    const b = fixture();
    const s = new Story(b.story);
    s.play();
    s.tick(DEFAULT_DWELL - 0.01);
    expect(s.index).toBe(0);
    s.tick(0.02);
    expect(s.index).toBe(1);
    s.setSpeed(2);
    s.tick(DEFAULT_DWELL / 2 + 0.01);
    expect(s.index).toBe(2);
    const head = b.story.findIndex((x) => x.emphasis === "lead");
    expect([...s.climax].sort((x, y) => x - y)).toEqual(
      b.story.filter((x) => x.emphasis === "lead" || x.kind === "outcome" || x.kind === "counterfactual")
        .map((x) => x.index));
    s.goto(head);
    expect(s.dwell).toBeCloseTo((DEFAULT_DWELL * CLIMAX_DWELL) / 2);
  });

  it("steps by hand, clamped, and pauses without losing its place", () => {
    const b = fixture();
    const s = new Story(b.story);
    s.goto(3);
    s.prev();
    expect(s.index).toBe(2);
    s.goto(99);
    expect(s.index).toBe(b.story.length - 1);
    s.play();
    s.pause();
    s.tick(10);
    expect(s.index).toBe(b.story.length - 1);
    s.reset();
    expect(s.state).toBe("ready");
  });
});
