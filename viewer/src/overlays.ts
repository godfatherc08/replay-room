// On-pitch overlays: schematic drawings of what a fact means. One step's overlay at a time.
// Pure geometry (pitch metres) from the bundle; the scene turns these specs into meshes.
// Every position drawn is an observed one; every number is the account's.
//
// Vocabulary (the on-pitch legend): dashed yellow = pass / movement; solid red = shot; translucent cyan =
// threat zone (the space at the key spot Build 4 measured); amber line = marking; at a decision, a solid
// white arrow is the option chosen and a dashed green arrow the better option. No floating metric tags:
// the only labels on the pitch are the counterfactual's two options (values in Analyst mode only).

import { contribution, counterfactualFor } from "./account";
import type { Bundle, BundleEvent, Contribution, Counterfactual, StoryStep } from "./bundle";
import { positionAt, velocityAt } from "./bundle";

export type Vec2 = [number, number];
export type Mode = "analyst" | "fan";

export type Overlay =
  | { type: "arrow"; from: Vec2; to: Vec2; color: string; width: number; dashed?: boolean; label?: string }
  | { type: "disc"; center: Vec2; radius: number; color: string; alpha: number; label?: string }
  | { type: "line"; a: Vec2; b: Vec2; color: string; dashed?: boolean; label?: string }
  | { type: "trail"; points: Vec2[]; color: string }
  | { type: "cross"; at: Vec2; color: string; label?: string };

export const COLORS = {
  highlight: "#fbbf24", // focus ring
  pass: "#facc15",
  shot: "#f43f5e",
  zone: "#22d3ee",
  chosen: "#f1f5f9",
  better: "#22c55e",
  marking: "#fbbf24",
  denied: "#fb923c",
  label: "#f8fafc",
};

const SHOT_TYPES = new Set(["shot", "shot_freekick", "shot_penalty"]);

const TRAIL_FRAMES = 20; // 2 s at 10 Hz
const VELOCITY_LOOKAHEAD = 1.0; // s: a velocity arrow shows where the player would be in a second

function team(bundle: Bundle, teamId: string) {
  return bundle.teams.find((t) => t.team_id === teamId);
}

/** The team's shirt colour (bundle teams[].kit). */
export function teamColor(bundle: Bundle, teamId: string): string {
  return team(bundle, teamId)?.kit.shirt ?? "#94a3b8";
}

/** A player's kit: their team's shirt and shorts, or the team's keeper colour for a goalkeeper. */
export function kitOf(bundle: Bundle, playerId: string): { shirt: string; shorts: string } {
  const teamId = bundle.objects.find((o) => o.id === playerId)?.team_id ?? "";
  const kit = team(bundle, teamId)?.kit ?? { shirt: "#94a3b8", shorts: "#334155", keeper: "#c8e64a" };
  return bundle.goalkeepers.includes(playerId) ? { shirt: kit.keeper, shorts: kit.keeper } : { shirt: kit.shirt, shorts: kit.shorts };
}

function event(bundle: Bundle, actionId: number): BundleEvent {
  const e = bundle.events.find((x) => x.action_id === actionId);
  if (!e) throw new Error(`event #${actionId} is not in the bundle`);
  return e;
}

function velocityArrow(bundle: Bundle, id: string, frameId: number): Overlay | null {
  const p = positionAt(bundle, id, frameId);
  const v = velocityAt(bundle, id, frameId);
  if (!p || !v || Math.hypot(v[0], v[1]) < 0.5) return null;
  return { type: "arrow", from: p, to: [p[0] + v[0] * VELOCITY_LOOKAHEAD, p[1] + v[1] * VELOCITY_LOOKAHEAD],
           color: COLORS.pass, width: 0.15, dashed: true };
}

function trail(bundle: Bundle, id: string, frameId: number, color: string): Overlay | null {
  const ids = bundle.frames.frame_ids;
  const end = ids.indexOf(frameId);
  const points: Vec2[] = [];
  for (let i = Math.max(0, end - TRAIL_FRAMES); i <= end; i++) {
    const p = positionAt(bundle, id, ids[i]);
    if (p) points.push(p);
  }
  return points.length >= 2 ? { type: "trail", points, color } : null;
}

function spot(bundle: Bundle, effect: number): Overlay {
  const alpha = 0.15 + 0.3 * Math.min(Math.abs(effect) / 0.05, 1);
  return { type: "disc", center: [bundle.key_spot.x, bundle.key_spot.y], radius: 2 * bundle.key_spot.sigma_m,
           color: COLORS.zone, alpha };
}

function jumpFrame(bundle: Bundle, c: Contribution): number {
  const j = bundle.jumps.find((x) => x.contribution_id === c.contribution_id);
  if (!j) throw new Error(`no jump frame for ${c.contribution_id}`);
  return j.frame_id;
}

/** The outcome: the terminal action's track, ending in a goal or in what denied it. */
export function outcomeOverlays(bundle: Bundle): Overlay[] {
  const { outcome } = bundle.account;
  const shot = event(bundle, outcome.ref.action_id);
  const solid = SHOT_TYPES.has(shot.type) || shot.type.startsWith("shot");
  const out: Overlay[] = [{ type: "arrow", from: shot.start, to: shot.end, color: solid ? COLORS.shot : COLORS.pass,
                            width: 0.22, dashed: !solid }];
  if (outcome.scored) {
    out.push({ type: "cross", at: shot.end, color: COLORS.label });
    return out;
  }
  const denial = bundle.account.contributions.find((c) => c.kind === "chance_denied");
  const at = denial && denial.evidence[0].kind === "event" ? event(bundle, denial.evidence[0].action_id).end : shot.end;
  out.push({ type: "cross", at, color: outcome.realized ? COLORS.label : COLORS.denied });
  return out;
}

export function contributionOverlays(bundle: Bundle, id: string): Overlay[] {
  const c = contribution(bundle, id);
  const frame = jumpFrame(bundle, c);
  const color = COLORS.pass;
  const out: (Overlay | null)[] = [];
  switch (c.kind) {
    case "space_creation":
      out.push(trail(bundle, c.player_id, frame, color), velocityArrow(bundle, c.player_id, frame), spot(bundle, c.effect));
      break;
    case "space_conceded": {
      const p = positionAt(bundle, c.player_id, frame);
      out.push(spot(bundle, c.effect), trail(bundle, c.player_id, frame, color));
      if (p) out.push({ type: "line", a: p, b: [bundle.key_spot.x, bundle.key_spot.y], color: COLORS.zone, dashed: true });
      break;
    }
    case "marking_break": {
      const man = c.evidence.find((r) => r.kind === "frame" && r.player_ids.length > 1);
      const manId = man && man.kind === "frame" ? man.player_ids[1] : undefined;
      const a = positionAt(bundle, c.player_id, frame);
      const b = manId ? positionAt(bundle, manId, frame) : null;
      if (a && b) out.push({ type: "line", a, b, color: COLORS.marking });
      out.push(velocityArrow(bundle, c.player_id, frame));
      if (manId) out.push(velocityArrow(bundle, manId, frame));
      out.push(spot(bundle, c.effect));
      break;
    }
    case "action_value":
    case "chance_denied": {
      const ref = c.evidence[0];
      if (ref.kind !== "event") break;
      const e = event(bundle, ref.action_id);
      const moved = Math.hypot(e.end[0] - e.start[0], e.end[1] - e.start[1]) > 0.5;
      const shot = e.type.startsWith("shot");
      const kindColor = c.kind === "chance_denied" ? COLORS.denied : shot ? COLORS.shot : COLORS.pass;
      out.push(moved ? { type: "arrow", from: e.start, to: e.end, color: kindColor, width: 0.2, dashed: !shot }
                     : { type: "cross", at: e.start, color: kindColor });
      break;
    }
  }
  return out.filter((o): o is Overlay => o !== null);
}

/** Option value as stored, for Analyst labels. */
const value3 = (v: number) => v.toFixed(3);

/** Chosen vs better options at the decision frame, as arrows from the ball. Analyst labels carry the values. */
export function counterfactualOverlays(bundle: Bundle, cf: Counterfactual, mode: Mode = "analyst"): Overlay[] {
  const frame = cf.decision_frame.frame_id;
  const ball = positionAt(bundle, "ball", frame);
  if (!ball) return [];
  const c = contribution(bundle, cf.contribution_id);
  const ref = c.evidence[0];
  const out: Overlay[] = [];
  const tag = (word: string, v: number) => (mode === "analyst" ? `${word} · ${value3(v)}` : word);
  if (ref.kind === "event") {
    const e = event(bundle, ref.action_id);
    out.push({ type: "arrow", from: ball, to: e.end, color: COLORS.chosen, width: 0.16, dashed: false,
               label: tag("Chosen", cf.chosen_value) });
  }
  cf.alternatives.forEach((alt, i) => {
    const target = alt.target_player_id ? positionAt(bundle, alt.target_player_id, frame) : null;
    if (!target) return;
    out.push({ type: "arrow", from: ball, to: target, color: COLORS.better, width: i === 0 ? 0.26 : 0.1, dashed: true,
               label: i === 0 ? tag("Better option", alt.value) : undefined });
  });
  return out;
}

/** Explore mode: what a selected contribution draws (its counterfactual instead, when it has one). */
export function overlaysFor(bundle: Bundle, id: string, mode: Mode = "analyst"): Overlay[] {
  const cf = counterfactualFor(bundle, id);
  if (cf) return counterfactualOverlays(bundle, cf, mode);
  return contributionOverlays(bundle, id);
}

/** Story mode: only this step's drawing. A contribution step draws the action itself, never its counterfactual
 *  (that is the final beat). */
export function stepOverlays(bundle: Bundle, step: StoryStep, mode: Mode = "analyst"): Overlay[] {
  switch (step.kind) {
    case "contribution":
      return contributionOverlays(bundle, step.contribution_id!);
    case "outcome":
      return outcomeOverlays(bundle);
    case "counterfactual": {
      const cf = counterfactualFor(bundle, step.contribution_id!);
      return cf ? counterfactualOverlays(bundle, cf, mode) : [];
    }
  }
}

/** Every pitch point an overlay touches (for framing the camera on what is drawn). */
export function overlayPoints(overlays: Overlay[]): Vec2[] {
  return overlays.flatMap((o): Vec2[] => {
    switch (o.type) {
      case "arrow": return [o.from, o.to];
      case "disc": return [o.center];
      case "line": return [o.a, o.b];
      case "trail": return o.points;
      case "cross": return [o.at];
    }
  });
}
