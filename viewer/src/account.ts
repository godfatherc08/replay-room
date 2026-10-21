// What the contribution panel lists, straight from the account: no re-ranking, no new numbers.
// Order: the headline first, then the account's own rank order.

import type { Bundle, Contribution, Counterfactual, NarrationSentence } from "./bundle";

export interface PanelItem {
  id: string;
  headline: boolean;
  rank: number;
  track: Contribution["track"];
  role: string;
  label: string; // the account's signal (off-ball) or action (on-ball)
  playerId: string;
  playerLabel: string; // "#9 EPA-09"
  teamId: string;
  teamName: string;
  effect: number;
  effectText: string; // signed, 3 decimals, as stored
  frameId: number;
  inWindow: boolean;
  hasCounterfactual: boolean;
}

export function signed(v: number): string {
  return `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(3)}`;
}

export function playerLabel(bundle: Bundle, playerId: string): string {
  for (const t of bundle.teams) {
    const p = t.players.find((q) => q.player_id === playerId);
    if (p) return `#${p.shirt_number} ${p.player_id}`;
  }
  return playerId;
}

export function teamName(bundle: Bundle, teamId: string): string {
  return bundle.teams.find((t) => t.team_id === teamId)?.name ?? teamId;
}

export function contribution(bundle: Bundle, id: string): Contribution {
  const c = bundle.account.contributions.find((x) => x.contribution_id === id);
  if (!c) throw new Error(`no contribution ${id}`);
  return c;
}

export function counterfactualFor(bundle: Bundle, id: string): Counterfactual | undefined {
  return bundle.account.counterfactuals.find((cf) => cf.contribution_id === id);
}

export function panelItems(bundle: Bundle): PanelItem[] {
  const a = bundle.account;
  const jumps = new Map(bundle.jumps.map((j) => [j.contribution_id, j]));
  const items = a.contributions.map((c): PanelItem => {
    const jump = jumps.get(c.contribution_id);
    if (!jump) throw new Error(`no jump frame for ${c.contribution_id}`);
    return {
      id: c.contribution_id,
      headline: c.contribution_id === a.headline_contribution_id,
      rank: c.rank,
      track: c.track,
      role: c.role,
      label: (c.track === "off_ball" ? c.signal : c.action) ?? c.kind,
      playerId: c.player_id,
      playerLabel: playerLabel(bundle, c.player_id),
      teamId: c.team_id,
      teamName: teamName(bundle, c.team_id),
      effect: c.effect,
      effectText: signed(c.effect),
      frameId: jump.frame_id,
      inWindow: jump.in_window,
      hasCounterfactual: counterfactualFor(bundle, c.contribution_id) !== undefined,
    };
  });
  return [...items.filter((i) => i.headline), ...items.filter((i) => !i.headline)];
}

/** The players a contribution names: its actor, then everyone its frame evidence names. */
export function highlightedPlayers(c: Contribution): string[] {
  const ids = [c.player_id];
  for (const r of c.evidence) if (r.kind === "frame") ids.push(...r.player_ids);
  return [...new Set(ids)];
}

export interface OutcomeBanner {
  framing: "realized" | "prevented";
  title: string;
  detail: string;
}

/** A label of the outcome's fields (not narration): framing, V, result, and what denied it. */
export function outcomeBanner(bundle: Bundle): OutcomeBanner {
  const { outcome, moment } = bundle.account;
  const v = `${outcome.value_source === "xg" ? "xG" : "xT"} ${outcome.value.toFixed(3)}`;
  if (outcome.realized) {
    return { framing: "realized", title: `${moment.type.replace(/_/g, " ")} · realized`,
             detail: `${v} · ${outcome.scored ? "scored" : "no goal"}` };
  }
  const denial = bundle.account.contributions.find((c) => c.kind === "chance_denied");
  const by = denial ? ` · denied: ${denial.action} (${playerLabel(bundle, denial.player_id)})` : "";
  return { framing: "prevented", title: `${moment.type.replace(/_/g, " ")} · prevented`,
           detail: `${v} · no goal${by}` };
}

// ---------------------------------------------------------------------------------- v2 panel model

export interface EvidenceRow {
  id: string;
  number: number; // position in the story (chronological)
  title: string;
  subtitle: string;
  player: string;
  valueText: string; // signed value and its unit, e.g. "+0.087 VAEP"
  positive: boolean;
  clock: string; // match clock of the cited record
  t: number;
  frameId: number;
  headline: boolean;
  track: Contribution["track"];
  hasCounterfactual: boolean;
}

/** The account's contributions in story (time) order, numbered, with the headline flagged. */
export function evidenceRows(bundle: Bundle): EvidenceRow[] {
  const display = new Map(bundle.display.map((d) => [d.contribution_id, d]));
  const jumps = new Map(bundle.jumps.map((j) => [j.contribution_id, j.frame_id]));
  return bundle.account.contributions
    .map((c) => ({ c, d: display.get(c.contribution_id) }))
    .filter((x): x is { c: Contribution; d: NonNullable<typeof x.d> } => x.d !== undefined)
    .sort((x, y) => x.d.t - y.d.t || x.c.rank - y.c.rank)
    .map(({ c, d }, i) => ({
      id: c.contribution_id,
      number: i + 1,
      title: d.title,
      subtitle: d.subtitle,
      player: d.player,
      valueText: `${signed(c.effect)} ${d.unit}`,
      positive: c.effect >= 0,
      clock: d.match_clock,
      t: d.t,
      frameId: jumps.get(c.contribution_id) ?? bundle.frames.frame_ids[0],
      headline: c.contribution_id === bundle.account.headline_contribution_id,
      track: c.track,
      hasCounterfactual: counterfactualFor(bundle, c.contribution_id) !== undefined,
    }));
}

export interface MomentHeader {
  classLabel: string;
  framing: "realized" | "prevented";
  value: string; // "xG 0.152"
  clock: string;
  description: string | null; // the narration's headline line, when there is a narration
}

export function momentHeader(bundle: Bundle): MomentHeader {
  const { outcome, moment } = bundle.account;
  return {
    classLabel: moment.type.replace(/_/g, " ").toUpperCase(),
    framing: outcome.realized ? "realized" : "prevented",
    value: `${outcome.value_source === "xg" ? "xG" : "xT"} ${outcome.value.toFixed(3)}`,
    clock: bundle.match.moment_clock,
    description: bundle.narration?.headline_text ?? null,
  };
}

/** Elapsed match clock at a time in the moment's period. */
export function matchClock(bundle: Bundle, t: number): string {
  const total = Math.max(bundle.match.period_offset_s + t, 0);
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(Math.floor(total % 60)).padStart(2, "0")}`;
}

/** The score at time t of the replay: as the moment began, plus the outcome once it has been scored. */
export function scoreAt(bundle: Bundle, t: number): { home: number; away: number } {
  const s = { ...bundle.match.score_before };
  const { outcome } = bundle.account;
  if (outcome.scored && t >= outcome.ref.time_seconds) {
    if (outcome.beneficiary_team_id === bundle.match.home.team_id) s.home += 1;
    else s.away += 1;
  }
  return s;
}

export interface Summary {
  lead: NarrationSentence[]; // the first sentences of the narration (headline first)
  all: NarrationSentence[];
  source: string; // who wrote it, as recorded by Build 6
}

export const SUMMARY_SENTENCES = 3;

export function summary(bundle: Bundle): Summary | null {
  const n = bundle.narration;
  if (!n) return null;
  const source = n.source === "foundry" ? `Narrated by ${n.model?.split("@")[0] ?? "Foundry"} on Microsoft Foundry`
                                        : "Template narration (no model)";
  return { lead: n.sentences.slice(0, SUMMARY_SENTENCES), all: n.sentences, source: `${source} · grounded` };
}
