// What the contribution panel lists, straight from the account: no re-ranking, no new numbers.
// Order: the headline first, then the account's own rank order.

import type { Bundle, Contribution, Counterfactual } from "./bundle";

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
