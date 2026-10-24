// The moment bundle written by `python -m replay_room.render` (src/replay_room/render/export.py).
// The viewer only reads it: every number shown comes from here.

export interface EventRef {
  kind: "event";
  action_id: number;
  original_event_id: string;
  period_id: number;
  time_seconds: number;
}

export interface FrameRef {
  kind: "frame";
  frame_id: number;
  timestamp: number;
  player_ids: string[];
}

export type Ref = EventRef | FrameRef;

export interface Contribution {
  contribution_id: string;
  rank: number;
  track: "on_ball" | "off_ball";
  kind: "action_value" | "space_creation" | "space_conceded" | "marking_break" | "chance_denied";
  role: string;
  action: string | null;
  signal: string | null;
  player_id: string;
  team_id: string;
  t: number;
  effect: number;
  metrics: Record<string, number>;
  evidence: Ref[];
}

export interface Alternative {
  description: string;
  target_player_id: string | null;
  completion_prob: number | null;
  value: number;
  evidence: Ref[];
}

export interface Counterfactual {
  contribution_id: string;
  decision_frame: FrameRef;
  chosen: string;
  chosen_value: number;
  alternatives: Alternative[];
}

export interface Outcome {
  ref: EventRef;
  value: number;
  value_source: "xg" | "xt";
  scored: boolean;
  realized: boolean;
  beneficiary_team_id: string;
  conceding_team_id: string;
  zone: string | null; // "the middle of the box"
}

/** An off-ball causal link the engine measured on the tracking (attribution.links). */
export interface Link {
  link_id: string;
  kind: "decoy_run" | "dragged_out" | "run_past" | "lost_man";
  defender_contribution_id: string;
  defender_id: string;
  marked_player_id: string | null;
  runner_id: string | null;
  runner_contribution_id: string | null;
  zone: string;
  enabled: EventRef | null;
  enabled_contribution_id: string | null;
  metrics: Record<string, number>;
  evidence: FrameRef[];
}

export interface Moment {
  moment_id: string;
  type: string;
  period_id: number;
  t_event: number;
  attacking_team_id: string;
  defending_team_id: string;
  key_event_ref: EventRef;
  key_player_id: string;
  outcome_ref: EventRef;
}

export interface Account {
  account_id: string;
  game_id: string;
  moment: Moment;
  outcome: Outcome;
  teams: { team_id: string; name: string }[];
  participants: { player_id: string; name: string; team_id: string; shirt_number: number | null }[];
  headline_contribution_id: string;
  supporting_contribution_id: string | null;
  contributions: Contribution[];
  counterfactuals: Counterfactual[];
  links: Link[];
  evidence: { events: number[]; frames: number[] };
}

export interface Track {
  x: (number | null)[];
  y: (number | null)[];
  vx: (number | null)[];
  vy: (number | null)[];
}

export interface BundleEvent {
  action_id: number;
  original_event_id: string;
  type: string;
  result: string;
  player_id: string;
  team_id: string;
  t: number;
  frame_id: number;
  in_window: boolean;
  start: [number, number];
  end: [number, number];
}

export interface Jump {
  contribution_id: string;
  frame_id: number;
  source: "frame" | "event";
  in_window: boolean;
}

export interface Kit {
  shirt: string;
  shorts: string;
  keeper: string;
}

export interface TeamRoster {
  team_id: string;
  name: string;
  short_name: string;
  side: "home" | "away";
  kit: Kit;
  players: { player_id: string; name: string; shirt_number: number; position: string }[];
}

export interface DisplayRow {
  contribution_id: string;
  title: string;
  subtitle: string;
  player: string;
  unit: string;
  t: number;
  match_clock: string;
}

export interface MatchInfo {
  game_id: string;
  competition: string;
  home: { team_id: string; name: string; short_name: string };
  away: { team_id: string; name: string; short_name: string };
  score_before: { home: number; away: number };
  period_offset_s: number;
  duration_s: number;
  moment_clock: string;
}

export interface MatchMoment {
  moment_id: string;
  type: string;
  period_id: number;
  t_event: number;
  realized: boolean;
  match_clock: string;
}

export type BeatKind = "build_up" | "lead" | "flaw" | "punish" | "link" | "context" | "outcome" | "counterfactual";

/** One told beat of the framing plan (explain.schema.NarratedBeat). */
export interface NarratedBeat {
  index: number;
  beat_id: string;
  kind: BeatKind;
  emphasis: "lead" | "support" | "detail";
  contribution_id: string | null;
  link_id: string | null;
  context_fact_id: string | null;
  text: string; // analyst register
  fan: string; // fan register
  refs: Ref[];
  t: number;
}

export interface Narration {
  narration_version: "2";
  moment_id: string;
  framing: "realized" | "prevented";
  plan_source: "rules" | "foundry";
  source: "foundry" | "template";
  model: string | null;
  fallback_reason: string | null;
  headline: string;
  headline_fan: string;
  beats: NarratedBeat[];
}

/** A match-context fact: a per-match baseline for the defending team and this moment's value (context.baselines). */
export interface ContextFact {
  fact_id: string;
  kind: "counter_press" | "line_height" | "marking_distance";
  team_id: string;
  unit: "m" | "s" | "share";
  baseline: number;
  here: number;
  spread: [number, number] | null;
  deviates: boolean;
  direction: "higher" | "lower" | "same";
  sample_size: number;
  confidence: "low" | "medium" | "high";
  metrics: Record<string, number>;
  evidence: Ref[];
}

export interface MatchContext {
  moment_id: string;
  team_id: string;
  facts: ContextFact[];
  insufficient: [string, string][];
}

export interface Plan {
  source: "rules" | "foundry";
  lead_contribution_id: string;
  flaw_contribution_id: string | null;
  beats: { beat_id: string; kind: BeatKind; emphasis: string; contribution_id: string | null; link_id: string | null;
           context_fact_id: string | null }[];
}

/** Plain-language meaning of a contribution (render.display.meaning). */
export interface Meaning {
  contribution_id: string;
  gloss: string;
  icon: "pass" | "carry" | "shot" | "save" | "turnover" | "run" | "space" | "marking";
  positive: boolean;
  magnitude: number; // |effect| / the moment's largest |effect|, 0..1
}

export interface OutcomeDisplay {
  percent: number;
  label: string; // "15% chance of scoring"
  band: string; // "a good chance"
  result: string; // "Goal" | "No goal" | "A goal that didn't happen"
}

/** One beat of Story Mode, in play order (render.export.story_steps): the plan's beat, as told. */
export interface StoryStep {
  index: number;
  kind: BeatKind;
  emphasis: "lead" | "support" | "detail";
  beat_id: string;
  contribution_id: string | null;
  link_id: string | null;
  context_fact_id: string | null;
  frame_id: number;
  caption: string; // analyst register
  plain: string; // fan register: no numbers, no jargon
}

/** The proof behind a claim (render.proof): who, which frames, which feed events, what was measured. */
export interface ProofPlayer {
  player_id: string;
  name: string;
  shirt_number: number | null;
  team_id: string | null;
  role: string; // "actor", "defender", "runner", "used the space", "shooter", "chose", ...
}

export interface ProofFrame {
  frame_id: number;
  timestamp: number;
  match_clock: string;
  what: string; // "where the run ended", "the decision", ...
}

export interface ProofEvent {
  action_id: number;
  original_event_id: string; // the feed's own id
  type: string;
  result: string;
  player_id: string;
  player: string;
  t: number;
  match_clock: string;
}

export interface Measured {
  metric: string; // "VAEP", "ΔxT", "pitch control", "xG", "tracking", "line height", "pass model"
  value: number | null;
  statement: string; // the number with its meaning (Analyst)
  plain: string; // the same meaning without a number (Fan)
  magnitude: number | null; // |effect| / the moment's largest, for the meter
}

export interface Proof {
  players: ProofPlayer[];
  frames: ProofFrame[];
  events: ProofEvent[];
  measured: Measured[];
  focus_frame: number;
}

/** Story kinds that tell one contribution of the account. */
export const FACT_KINDS: ReadonlySet<BeatKind> = new Set(["build_up", "lead", "flaw", "punish"]);

export interface Bundle {
  bundle_version: "5";
  match: MatchInfo;
  goalkeepers: string[];
  display: DisplayRow[];
  narration: Narration;
  plan: Plan;
  context: MatchContext | null;
  editions: Record<string, unknown>;
  match_moments: MatchMoment[];
  account: Account;
  pitch: { length: number; width: number; units: "m"; origin: string; x_axis: string; frame_rate_hz: number };
  teams: TeamRoster[];
  frames: { period_id: number; frame_ids: number[]; timestamps: number[] };
  objects: { id: string; team_id: string | null; kind: "player" | "ball" }[];
  tracks: Record<string, Track>;
  events: BundleEvent[];
  key_spot: { x: number; y: number; sigma_m: number };
  jumps: Jump[];
  meaning: Meaning[];
  outcome_display: OutcomeDisplay;
  story: StoryStep[];
  proofs: { contributions: Record<string, Proof>; beats: Record<string, Proof> };
}

export interface IndexEntry {
  moment_id: string;
  type: string;
  game_id: string;
  realized: boolean;
  bundle: string;
}

const REQUIRED = ["account", "pitch", "teams", "frames", "objects", "tracks", "events", "key_spot", "jumps", "match",
                  "goalkeepers", "display", "narration", "plan", "context", "match_moments", "meaning",
                  "outcome_display", "story", "proofs"] as const;

export function parseBundle(data: unknown): Bundle {
  if (typeof data !== "object" || data === null) throw new Error("bundle is not an object");
  const b = data as Record<string, unknown>;
  if (b.bundle_version !== "5") throw new Error(`unsupported bundle version ${String(b.bundle_version)}`);
  for (const key of REQUIRED) if (!(key in b)) throw new Error(`bundle is missing "${key}"`);
  const bundle = data as Bundle;
  const frames = new Set(bundle.frames.frame_ids);
  for (const j of bundle.jumps) {
    if (!frames.has(j.frame_id)) throw new Error(`jump for ${j.contribution_id} targets frame ${j.frame_id}, not in the window`);
  }
  for (const s of bundle.story) {
    if (!frames.has(s.frame_id)) throw new Error(`story step ${s.index} targets frame ${s.frame_id}, not in the window`);
  }
  for (const p of [...Object.values(bundle.proofs.contributions), ...Object.values(bundle.proofs.beats)]) {
    if (!frames.has(p.focus_frame)) throw new Error(`a proof opens at frame ${p.focus_frame}, not in the window`);
  }
  return bundle;
}

export async function loadBundle(url: string, fetcher: typeof fetch = fetch): Promise<Bundle> {
  const res = await fetcher(url);
  if (!res.ok) throw new Error(`could not load ${url}: ${res.status}`);
  return parseBundle(await res.json());
}

export function frameIndex(bundle: Bundle, frameId: number): number {
  const i = frameId - bundle.frames.frame_ids[0];
  if (i < 0 || i >= bundle.frames.frame_ids.length || bundle.frames.frame_ids[i] !== frameId) {
    throw new Error(`frame ${frameId} is not in the window`);
  }
  return i;
}

/** Observed position of an object at a window frame, or null if it is missing there. */
export function positionAt(bundle: Bundle, id: string, frameId: number): [number, number] | null {
  const t = bundle.tracks[id];
  if (!t) return null;
  const i = frameIndex(bundle, frameId);
  const x = t.x[i];
  const y = t.y[i];
  return x === null || y === null ? null : [x, y];
}

export function velocityAt(bundle: Bundle, id: string, frameId: number): [number, number] | null {
  const t = bundle.tracks[id];
  if (!t) return null;
  const i = frameIndex(bundle, frameId);
  const vx = t.vx[i];
  const vy = t.vy[i];
  return vx === null || vy === null ? null : [vx, vy];
}
