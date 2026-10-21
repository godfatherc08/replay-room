import { describe, expect, it } from "vitest";
import { positionAt } from "../src/bundle";
import { COLORS, contributionOverlays, counterfactualOverlays, outcomeOverlays, overlaysFor } from "../src/overlays";
import { fixture } from "./helpers";

describe("overlays", () => {
  it("draws the counterfactual as chosen vs better arrows from the ball, with the account's values", () => {
    const b = fixture();
    const cf = b.account.counterfactuals[0];
    const [chosen, best] = counterfactualOverlays(b, cf);
    const ball = positionAt(b, "ball", cf.decision_frame.frame_id);
    expect(chosen).toMatchObject({ type: "arrow", from: ball, color: COLORS.chosen,
                                   label: `chosen: ${cf.chosen} ${cf.chosen_value.toFixed(3)}` });
    const target = positionAt(b, cf.alternatives[0].target_player_id!, cf.decision_frame.frame_id);
    expect(best).toMatchObject({ type: "arrow", from: ball, to: target, color: COLORS.better });
    expect(best.type === "arrow" && best.label).toContain(cf.alternatives[0].value.toFixed(3));
    const drawn = overlaysFor(b, cf.contribution_id);
    expect(drawn).toEqual(expect.arrayContaining([chosen, best]));
    expect(drawn).not.toEqual(expect.arrayContaining(contributionOverlays(b, cf.contribution_id))); // not drawn twice
  });

  it("ends a prevented shot at what denied it, never at a goal", () => {
    const b = fixture();
    const o = outcomeOverlays(b);
    const shot = b.events.find((e) => e.action_id === b.account.outcome.ref.action_id)!;
    expect(o[0]).toMatchObject({ type: "arrow", from: shot.start, to: shot.end, dashed: true });
    expect(o[1]).toMatchObject({ type: "cross", color: COLORS.denied });
    expect(o[1].type === "cross" && o[1].label).toMatch(/^denied/);
    expect(JSON.stringify(o)).not.toContain("goal ·");
  });

  it("shades the space at the key spot for an off-ball fact, from the observed run", () => {
    const b = fixture();
    const c = b.account.contributions.find((x) => x.kind === "space_creation")!;
    const o = contributionOverlays(b, c.contribution_id);
    expect(o.find((x) => x.type === "disc")).toMatchObject({
      center: [b.key_spot.x, b.key_spot.y], radius: 2 * b.key_spot.sigma_m });
    const trail = o.find((x) => x.type === "trail")!;
    const frame = b.jumps.find((j) => j.contribution_id === c.contribution_id)!.frame_id;
    expect(trail.type === "trail" && trail.points.at(-1)).toEqual(positionAt(b, c.player_id, frame));
  });

  it("draws a marking break as the line from the defender to the man he stopped tracking", () => {
    const b = fixture();
    const c = b.account.contributions.find((x) => x.kind === "space_conceded")!;
    const frame = b.jumps.find((j) => j.contribution_id === c.contribution_id)!.frame_id;
    const man = "EPA-11";
    Object.assign(c, {
      kind: "marking_break", signal: "stopped_tracking_runner",
      metrics: { ...c.metrics, separation_start: 1.8, separation_end: 5.2 },
      evidence: [{ kind: "frame", frame_id: frame, timestamp: 0, player_ids: [c.player_id, man] }],
    });
    const line = contributionOverlays(b, c.contribution_id).find((x) => x.type === "line")!;
    expect(line).toMatchObject({ a: positionAt(b, c.player_id, frame), b: positionAt(b, man, frame) });
    expect(line.type === "line" && line.label).toContain("separation 1.8 → 5.2 m");
  });

  it("draws an on-ball action from where it started to where it ended", () => {
    const b = fixture();
    const pass = b.events.find((e) => e.action_id === 161)!;
    expect(contributionOverlays(b, "a161")[0]).toMatchObject({ type: "arrow", from: pass.start, to: pass.end });
  });
});
