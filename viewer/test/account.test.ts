import { describe, expect, it } from "vitest";
import { decisionView, evidenceRows, highlightedPlayers, metricText, outcomeView, signed, stepCaption, stepPlayers,
         stepView } from "../src/account";
import { parseBundle } from "../src/bundle";
import { fixture } from "./helpers";

const FLOAT = /\d\.\d/;

describe("the chain", () => {
  it("lists every contribution once, in time order, with its gloss, meter and metric", () => {
    const b = fixture();
    const rows = evidenceRows(b);
    expect(rows.map((r) => r.id).sort()).toEqual(b.account.contributions.map((c) => c.contribution_id).sort());
    expect(rows.map((r) => r.t)).toEqual([...rows.map((r) => r.t)].sort((x, y) => x - y));
    const head = rows.find((r) => r.headline)!;
    expect(head).toMatchObject({ id: "d163", gloss: "the miss that let them off", positive: false, magnitude: 1,
                                 metric: "xG −0.152", player: "#11 Jordan Ferraro" });
    expect(rows.find((r) => r.id === "a161")!.hasCounterfactual).toBe(true);
    expect(metricText(b, "a157")).toBe("VAEP +0.087");
    expect(signed(0.0371)).toBe("+0.037");
  });

  it("highlights exactly the players a contribution names", () => {
    const b = fixture();
    const c = b.account.contributions.find((x) => x.track === "off_ball")!;
    const named = new Set([c.player_id, ...c.evidence.flatMap((r) => (r.kind === "frame" ? r.player_ids : []))]);
    expect(new Set(highlightedPlayers(c))).toEqual(named);
  });

  it("refuses a bundle whose jump or story step leaves the window", () => {
    const b = structuredClone(fixture());
    b.jumps[0].frame_id = 1;
    expect(() => parseBundle(b)).toThrow(/not in the window/);
    const c = structuredClone(fixture());
    c.story[0].frame_id = 1;
    expect(() => parseBundle(c)).toThrow(/story step 0/);
  });
});

describe("number discipline", () => {
  it("Fan shows the outcome as a band, Analyst as a probability with the metric secondary", () => {
    const b = fixture();
    expect(outcomeView(b, "fan")).toMatchObject({ result: "A goal that didn't happen", primary: "A good chance", metric: null });
    expect(outcomeView(b, "analyst")).toMatchObject({ primary: "15% chance of scoring", metric: "xG 0.152" });
    expect(outcomeView(b, "analyst").fraction).toBe(b.account.outcome.value);
  });

  it("a step's view never carries a raw metric in Fan mode", () => {
    const b = fixture();
    for (const step of b.story) {
      const fan = stepView(b, step, "fan");
      expect(fan.caption).not.toMatch(FLOAT);
      for (const m of fan.meters) {
        expect(m.metric).toBeNull();
        expect(m.label).not.toMatch(FLOAT);
        expect(m.fraction).toBeGreaterThanOrEqual(0);
        expect(m.fraction).toBeLessThanOrEqual(1);
      }
      const analyst = stepView(b, step, "analyst");
      expect(analyst.meters.every((m) => m.metric !== null)).toBe(true);
    }
  });

  it("Fan swaps a caption that quotes a metric for the plain line", () => {
    const b = fixture();
    const step = { ...b.story[0], caption: "Sam Adeyemi: pass, build up, effect +0.087." };
    expect(stepCaption(step, "analyst")).toBe(step.caption);
    expect(stepCaption(step, "fan")).toBe(step.plain);
    expect(stepCaption(b.story[0], "fan")).toBe(b.story[0].caption); // Foundry's plain sentence stays
  });

  it("the decision compares chosen and better on one scale, names players, values in Analyst only", () => {
    const b = fixture();
    const cf = b.account.counterfactuals[0];
    const fan = decisionView(b, cf, "fan");
    expect(fan.chosen.label).toBe("Chosen: pass to #11 Jordan Ferraro");
    expect(fan.better.label).toBe("Better: pass to #9 Sam Adeyemi");
    expect(fan.better.fraction).toBe(1);
    expect(fan.chosen.fraction).toBeCloseTo(cf.chosen_value / cf.alternatives[0].value);
    expect(fan.chosen.metric).toBeNull();
    expect(decisionView(b, cf, "analyst").better.metric).toBe("option value 0.206 · completion 0.94");
  });
});

describe("story steps", () => {
  it("focus the fact's players, the shooter at the outcome, the decider and the better target at the decision", () => {
    const b = fixture();
    const byKind = (k: string) => b.story.find((s) => s.kind === k)!;
    expect(stepPlayers(b, byKind("outcome"))).toEqual(["EPA-11"]);
    expect(stepPlayers(b, byKind("counterfactual"))).toEqual(["EPA-08", "EPA-09"]);
    const first = b.story[0];
    expect(stepPlayers(b, first)[0]).toBe(b.account.contributions.find((c) => c.contribution_id === first.contribution_id)!.player_id);
    const head = b.story.find((s) => s.contribution_id === b.account.headline_contribution_id && s.kind === "contribution")!;
    expect(stepView(b, head, "fan").headline).toBe(true);
  });
});
