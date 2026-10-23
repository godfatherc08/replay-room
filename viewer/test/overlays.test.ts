import { describe, expect, it } from "vitest";
import { positionAt } from "../src/bundle";
import { COLORS, contributionOverlays, counterfactualOverlays, kitOf, outcomeOverlays, overlaysFor, stepOverlays,
         teamColor } from "../src/overlays";
import { fixture } from "./helpers";

describe("overlays", () => {
  it("draws the counterfactual as a solid chosen arrow and a dashed better arrow from the ball", () => {
    const b = fixture();
    const cf = b.account.counterfactuals[0];
    const [chosen, best] = counterfactualOverlays(b, cf, "analyst");
    const ball = positionAt(b, "ball", cf.decision_frame.frame_id);
    expect(chosen).toMatchObject({ type: "arrow", from: ball, color: COLORS.chosen, dashed: false,
                                   label: `Chosen · ${cf.chosen_value.toFixed(3)}` });
    const target = positionAt(b, cf.alternatives[0].target_player_id!, cf.decision_frame.frame_id);
    expect(best).toMatchObject({ type: "arrow", from: ball, to: target, color: COLORS.better, dashed: true,
                                 label: `Better option · ${cf.alternatives[0].value.toFixed(3)}` });
    const fan = counterfactualOverlays(b, cf, "fan");
    expect(fan.map((o) => (o.type === "arrow" ? o.label : null))).toEqual(["Chosen", "Better option"]);
    expect(overlaysFor(b, cf.contribution_id)).toEqual(counterfactualOverlays(b, cf));
  });

  it("puts no metric tag on the pitch outside the decision", () => {
    const b = fixture();
    for (const step of b.story.filter((s) => s.kind !== "counterfactual")) {
      for (const o of stepOverlays(b, step, "analyst")) expect("label" in o ? o.label : undefined).toBeUndefined();
    }
  });

  it("a story step draws only its own fact; the counterfactual waits for its own beat", () => {
    const b = fixture();
    const assist = b.story.find((s) => s.kind === "contribution" && s.contribution_id === "a161")!;
    expect(stepOverlays(b, assist)).toEqual(contributionOverlays(b, "a161"));
    expect(stepOverlays(b, b.story.find((s) => s.kind === "outcome")!)).toEqual(outcomeOverlays(b));
  });

  it("ends a prevented shot at what denied it, never at a goal", () => {
    const b = fixture();
    const o = outcomeOverlays(b);
    const shot = b.events.find((e) => e.action_id === b.account.outcome.ref.action_id)!;
    expect(o[0]).toMatchObject({ type: "arrow", from: shot.start, to: shot.end, color: COLORS.shot, dashed: false });
    expect(o[1]).toMatchObject({ type: "cross", color: COLORS.denied });
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
      evidence: [{ kind: "frame", frame_id: frame, timestamp: 0, player_ids: [c.player_id, man] }],
    });
    const line = contributionOverlays(b, c.contribution_id).find((x) => x.type === "line")!;
    expect(line).toMatchObject({ a: positionAt(b, c.player_id, frame), b: positionAt(b, man, frame), color: COLORS.marking });
  });

  it("draws an on-ball action from where it started to where it ended", () => {
    const b = fixture();
    const pass = b.events.find((e) => e.action_id === 161)!;
    expect(contributionOverlays(b, "a161")[0]).toMatchObject({ type: "arrow", from: pass.start, to: pass.end });
  });

  it("dresses players in their team's kit and keepers in their own", () => {
    const b = fixture();
    const home = b.teams.find((t) => t.side === "home")!;
    const away = b.teams.find((t) => t.side === "away")!;
    expect(teamColor(b, home.team_id)).toBe(home.kit.shirt);
    expect(teamColor(b, home.team_id)).not.toBe(teamColor(b, away.team_id));
    const outfield = b.objects.find((o) => o.team_id === home.team_id && !b.goalkeepers.includes(o.id))!;
    const keeper = b.goalkeepers.find((id) => b.objects.find((o) => o.id === id)?.team_id === home.team_id)!;
    expect(kitOf(b, outfield.id)).toEqual({ shirt: home.kit.shirt, shorts: home.kit.shorts });
    expect(kitOf(b, keeper).shirt).toBe(home.kit.keeper);
  });
});
