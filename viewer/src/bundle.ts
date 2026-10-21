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
  contributions: Contribution[];
  counterfactuals: Counterfactual[];
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

export interface TeamRoster {
  team_id: string;
  name: string;
  short_name: string;
  side: "home" | "away";
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

export interface NarrationSentence {
  index: number;
  contribution_id: string;
  role: string;
  headline: boolean;
  text: string;
  ref: Ref;
  t: number;
}

export interface Narration {
  moment_id: string;
  framing: "realized" | "prevented";
  source: "foundry" | "template";
  model: string | null;
  fallback_reason: string | null;
  headline_text: string;
  sentences: NarrationSentence[];
}

export interface Bundle {
  bundle_version: "2";
  match: MatchInfo;
  goalkeepers: string[];
  display: DisplayRow[];
  narration: Narration | null;
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
}

export interface IndexEntry {
  moment_id: string;
  type: string;
  game_id: string;
  realized: boolean;
  bundle: string;
}

const REQUIRED = ["account", "pitch", "teams", "frames", "objects", "tracks", "events", "key_spot", "jumps", "match",
                  "goalkeepers", "display", "narration", "match_moments"] as const;

export function parseBundle(data: unknown): Bundle {
  if (typeof data !== "object" || data === null) throw new Error("bundle is not an object");
  const b = data as Record<string, unknown>;
  if (b.bundle_version !== "2") throw new Error(`unsupported bundle version ${String(b.bundle_version)}`);
  for (const key of REQUIRED) if (!(key in b)) throw new Error(`bundle is missing "${key}"`);
  const bundle = data as Bundle;
  const frames = new Set(bundle.frames.frame_ids);
  for (const j of bundle.jumps) {
    if (!frames.has(j.frame_id)) throw new Error(`jump for ${j.contribution_id} targets frame ${j.frame_id}, not in the window`);
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
