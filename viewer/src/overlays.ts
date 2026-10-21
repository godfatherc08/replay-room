// On-pitch overlays for a contribution: schematic drawings of what its numbers mean.
// Pure geometry (pitch metres) from the bundle; the scene turns these specs into meshes.
// Every position drawn is an observed one; every number is the account's.
//
// Vocabulary (the on-pitch legend): dashed yellow = pass / movement; solid red = shot / goal attempt;
// translucent cyan = threat zone (the space at the key spot Build 4 measured); green = the better
// option of a counterfactual; a yellow ring under the selected player(s).

import { contribution, counterfactualFor, playerLabel, signed } from "./account";
import type { Bundle, BundleEvent, Contribution, Counterfactual } from "./bundle";
import { positionAt, velocityAt } from "./bundle";

export type Vec2 = [number, number];

export type Overlay =
  | { type: "arrow"; from: Vec2; to: Vec2; color: string; width: number; dashed?: boolean; label?: string }
  | { type: "disc"; center: Vec2; radius: number; color: string; alpha: number; label?: string }
  | { type: "line"; a: Vec2; b: Vec2; color: string; dashed?: boolean; label?: string }
  | { type: "trail"; points: Vec2[]; color: string }
  | { type: "cross"; at: Vec2; color: string; label?: string };

export const COLORS = {
  home: "#e5484d", // shirts by side: home red, away blue
  away: "#4c9aff",
  keeper: "#c6e34c",
  highlight: "#fbbf24", // selection ring
  pass: "#facc15",
  shot: "#ef4444",
  zone: "#22d3ee",
  better: "#22c55e",
  marking: "#fbbf24",
  denied: "#f97316",
  label: "#f8fafc",
};

const SHOT_TYPES = new Set(["shot", "shot_freekick", "shot_penalty"]);

const TRAIL_FRAMES = 20; // 2 s at 10 Hz
const VELOCITY_LOOKAHEAD = 1.0; // s: a velocity arrow shows where the player would be in a second

export function teamColor(bundle: Bundle, teamId: string): string {
  return bundle.teams.find((t) => t.team_id === teamId)?.side === "home" ? COLORS.home : COLORS.away;
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

function spot(bundle: Bundle, effect: number, label: string): Overlay {
  const alpha = 0.15 + 0.3 * Math.min(Math.abs(effect) / 0.05, 1);
  return { type: "disc", center: [bundle.key_spot.x, bundle.key_spot.y], radius: 2 * bundle.key_spot.sigma_m,
           color: COLORS.zone, alpha, label };
}

function jumpFrame(bundle: Bundle, c: Contribution): number {
  const j = bundle.jumps.find((x) => x.contribution_id === c.contribution_id);
  if (!j) throw new Error(`no jump frame for ${c.contribution_id}`);
  return j.frame_id;
}

/** The outcome, always drawn: the terminal action's track, ending in a goal or in what denied it. */
export function outcomeOverlays(bundle: Bundle): Overlay[] {
  const { outcome } = bundle.account;
  const shot = event(bundle, outcome.ref.action_id);
  const v = `${outcome.value_source === "xg" ? "xG" : "xT"} ${outcome.value.toFixed(3)}`;
  const solid = SHOT_TYPES.has(shot.type);
  const out: Overlay[] = [{ type: "arrow", from: shot.start, to: shot.end, color: solid ? COLORS.shot : COLORS.pass,
                            width: 0.22, dashed: !solid }];
  if (outcome.scored) {
    out.push({ type: "cross", at: shot.end, color: COLORS.label, label: `goal · ${v}` });
    return out;
  }
  const denial = bundle.account.contributions.find((c) => c.kind === "chance_denied");
  const at = denial && denial.evidence[0].kind === "event" ? event(bundle, denial.evidence[0].action_id).start : shot.end;
  out.push({ type: "cross", at, color: outcome.realized ? COLORS.label : COLORS.denied,
             label: outcome.realized ? `no goal · ${v}` : `denied · ${v}` });
  return out;
}

export function contributionOverlays(bundle: Bundle, id: string): Overlay[] {
  const c = contribution(bundle, id);
  const frame = jumpFrame(bundle, c);
  const color = COLORS.pass;
  const out: (Overlay | null)[] = [];
  const name = playerLabel(bundle, c.player_id);
  switch (c.kind) {
    case "space_creation":
      out.push(trail(bundle, c.player_id, frame, color), velocityArrow(bundle, c.player_id, frame),
               spot(bundle, c.effect, `${name} · ${c.signal} · space created ${signed(c.effect)}`));
      break;
    case "space_conceded": {
      const p = positionAt(bundle, c.player_id, frame);
      out.push(spot(bundle, c.effect, `${name} · space conceded ${signed(c.effect)}`),
               trail(bundle, c.player_id, frame, color));
      if (p) out.push({ type: "line", a: p, b: [bundle.key_spot.x, bundle.key_spot.y], color: COLORS.zone, dashed: true });
      break;
    }
    case "marking_break": {
      const man = c.evidence.find((r) => r.kind === "frame" && r.player_ids.length > 1);
      const manId = man && man.kind === "frame" ? man.player_ids[1] : undefined;
      const a = positionAt(bundle, c.player_id, frame);
      const b = manId ? positionAt(bundle, manId, frame) : null;
      const sep = c.metrics.separation_start !== undefined
        ? ` · separation ${c.metrics.separation_start.toFixed(1)} → ${c.metrics.separation_end.toFixed(1)} m` : "";
      if (a && b) out.push({ type: "line", a, b, color: COLORS.marking, label: `${name} · ${c.signal}${sep}` });
      out.push(velocityArrow(bundle, c.player_id, frame));
      if (manId) out.push(velocityArrow(bundle, manId, frame));
      out.push(spot(bundle, c.effect, `space conceded ${signed(c.effect)}`));
      break;
    }
    case "action_value":
    case "chance_denied": {
      const ref = c.evidence[0];
      if (ref.kind !== "event") break;
      const e = event(bundle, ref.action_id);
      const label = `${name} · ${c.action} · ${signed(c.effect)}`;
      const moved = Math.hypot(e.end[0] - e.start[0], e.end[1] - e.start[1]) > 0.5;
      const shot = SHOT_TYPES.has(e.type);
      const kindColor = c.kind === "chance_denied" ? COLORS.denied : shot ? COLORS.shot : COLORS.pass;
      out.push(moved ? { type: "arrow", from: e.start, to: e.end, color: kindColor, width: 0.2, dashed: !shot, label }
                     : { type: "cross", at: e.start, color: kindColor, label });
      break;
    }
  }
  return out.filter((o): o is Overlay => o !== null);
}

/** Chosen vs better options at the decision frame, as arrows from the ball, labelled with their values. */
export function counterfactualOverlays(bundle: Bundle, cf: Counterfactual): Overlay[] {
  const frame = cf.decision_frame.frame_id;
  const ball = positionAt(bundle, "ball", frame);
  if (!ball) return [];
  const c = contribution(bundle, cf.contribution_id);
  const ref = c.evidence[0];
  const out: Overlay[] = [];
  if (ref.kind === "event") {
    const e = event(bundle, ref.action_id);
    out.push({ type: "arrow", from: ball, to: e.end, color: COLORS.pass, width: 0.18, dashed: true,
               label: `chosen: ${cf.chosen} ${cf.chosen_value.toFixed(3)}` });
  }
  cf.alternatives.forEach((alt, i) => {
    const target = alt.target_player_id ? positionAt(bundle, alt.target_player_id, frame) : null;
    if (!target) return;
    const comp = alt.completion_prob !== null ? ` (completion ${alt.completion_prob.toFixed(2)})` : "";
    out.push({ type: "arrow", from: ball, to: target, color: COLORS.better, width: i === 0 ? 0.25 : 0.1, dashed: true,
               label: i === 0 ? `better: ${alt.description} ${alt.value.toFixed(3)}${comp}` : undefined });
  });
  return out;
}

/** Everything drawn while a contribution is selected: the outcome, its own overlays, its counterfactual.
 *  With a counterfactual, the chosen arrow is the action itself, so the action's own arrow is not drawn twice. */
export function overlaysFor(bundle: Bundle, id: string): Overlay[] {
  const cf = counterfactualFor(bundle, id);
  if (cf) return [...outcomeOverlays(bundle), ...counterfactualOverlays(bundle, cf)];
  return [...outcomeOverlays(bundle), ...contributionOverlays(bundle, id)];
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
