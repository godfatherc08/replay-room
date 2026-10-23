// What the panels, the ribbon and Story Mode say, straight from the bundle: no re-ranking, no new numbers.
//
// Number discipline: a value is presented as a meter (its normalized magnitude) and a gloss (plain words,
// from the exporter). The raw metric is secondary text, and only in Analyst mode. Fan mode never shows one.

import type { Bundle, Contribution, Counterfactual, Meaning, NarrationSentence, StoryStep } from "./bundle";
import type { Mode } from "./overlays";

export function signed(v: number): string {
  return `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(3)}`;
}

export function playerLabel(bundle: Bundle, playerId: string): string {
  for (const t of bundle.teams) {
    const p = t.players.find((q) => q.player_id === playerId);
    if (p) return `#${p.shirt_number} ${p.name}`;
  }
  return playerId;
}

/** "#11 Ferraro": the on-pitch name tag. */
export function shortLabel(bundle: Bundle, playerId: string): string {
  for (const t of bundle.teams) {
    const p = t.players.find((q) => q.player_id === playerId);
    if (p) return `#${p.shirt_number} ${p.name.split(" ").at(-1)}`;
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

export function meaningOf(bundle: Bundle, id: string): Meaning {
  const m = bundle.meaning.find((x) => x.contribution_id === id);
  if (!m) throw new Error(`no meaning for ${id}`);
  return m;
}

/** The raw metric, as stored, with its unit: "VAEP +0.087". Analyst-only secondary text. */
export function metricText(bundle: Bundle, id: string): string {
  const unit = bundle.display.find((d) => d.contribution_id === id)?.unit ?? "";
  return `${unit} ${signed(contribution(bundle, id).effect)}`.trim();
}

/** The players a contribution names: its actor, then everyone its frame evidence names. */
export function highlightedPlayers(c: Contribution): string[] {
  const ids = [c.player_id];
  for (const r of c.evidence) if (r.kind === "frame") ids.push(...r.player_ids);
  return [...new Set(ids)];
}

// ------------------------------------------------------------------------------------------- the chain

export interface ChainRow {
  id: string;
  number: number; // position in the story (chronological)
  title: string;
  player: string; // "#9 Sam Adeyemi"
  playerId: string;
  teamId: string;
  gloss: string;
  icon: Meaning["icon"];
  magnitude: number;
  positive: boolean;
  metric: string; // Analyst only
  clock: string; // match clock of the cited record
  t: number;
  frameId: number;
  headline: boolean;
  track: Contribution["track"];
  hasCounterfactual: boolean;
}

/** The account's contributions in story (time) order, numbered, with the headline flagged. */
export function evidenceRows(bundle: Bundle): ChainRow[] {
  const display = new Map(bundle.display.map((d) => [d.contribution_id, d]));
  const jumps = new Map(bundle.jumps.map((j) => [j.contribution_id, j.frame_id]));
  return bundle.account.contributions
    .map((c) => ({ c, d: display.get(c.contribution_id) }))
    .filter((x): x is { c: Contribution; d: NonNullable<typeof x.d> } => x.d !== undefined)
    .sort((x, y) => x.d.t - y.d.t || x.c.rank - y.c.rank)
    .map(({ c, d }, i) => {
      const m = meaningOf(bundle, c.contribution_id);
      return {
        id: c.contribution_id,
        number: i + 1,
        title: d.title,
        player: d.player,
        playerId: c.player_id,
        teamId: c.team_id,
        gloss: m.gloss,
        icon: m.icon,
        magnitude: m.magnitude,
        positive: m.positive,
        metric: metricText(bundle, c.contribution_id),
        clock: d.match_clock,
        t: d.t,
        frameId: jumps.get(c.contribution_id) ?? bundle.frames.frame_ids[0],
        headline: c.contribution_id === bundle.account.headline_contribution_id,
        track: c.track,
        hasCounterfactual: counterfactualFor(bundle, c.contribution_id) !== undefined,
      };
    });
}

// ------------------------------------------------------------------------------------------- the story

const QUOTES_A_METRIC = /\d\.\d|\d+%/;

/** The one caption line of a step. Fan mode never shows a caption that quotes a metric (it gets the plain line). */
export function stepCaption(step: StoryStep, mode: Mode): string {
  if (!step.caption) return step.plain;
  return mode === "fan" && QUOTES_A_METRIC.test(step.caption) ? step.plain : step.caption;
}

/** Who a step puts in focus: a fact's named players; the outcome's shooter (and whoever denied it); the decider
 *  and the better option's target at a counterfactual. The first is the one who gets the name tag. */
export function stepPlayers(bundle: Bundle, step: StoryStep): string[] {
  if (step.kind === "contribution") return highlightedPlayers(contribution(bundle, step.contribution_id!));
  if (step.kind === "outcome") {
    const shot = bundle.events.find((e) => e.action_id === bundle.account.outcome.ref.action_id);
    const denial = bundle.account.contributions.find((c) => c.kind === "chance_denied");
    return [...new Set([shot?.player_id, denial?.player_id].filter((x): x is string => !!x))];
  }
  const cf = counterfactualFor(bundle, step.contribution_id!);
  if (!cf) return [];
  const targets = cf.alternatives.map((a) => a.target_player_id).filter((x): x is string => !!x);
  return [...new Set([...cf.decision_frame.player_ids, ...targets.slice(0, 1)])];
}

export interface StepView {
  index: number;
  total: number;
  kind: StoryStep["kind"];
  caption: string;
  title: string; // "Robin Hale" / "The outcome" / "The decision"
  teamId: string | null;
  gloss: string;
  meters: { label: string; fraction: number; tone: "pos" | "neg" | "chosen" | "better" | "outcome"; metric: string | null }[];
  headline: boolean;
}

/** Everything the step card shows, mode-aware. Numbers appear only as Analyst `metric` text. */
export function stepView(bundle: Bundle, step: StoryStep, mode: Mode): StepView {
  const base = { index: step.index, total: bundle.story.length, kind: step.kind, caption: stepCaption(step, mode) };
  const analyst = mode === "analyst";
  if (step.kind === "contribution") {
    const c = contribution(bundle, step.contribution_id!);
    const m = meaningOf(bundle, c.contribution_id);
    const name = bundle.account.participants.find((p) => p.player_id === c.player_id)?.name ?? c.player_id;
    return { ...base, title: name, teamId: c.team_id, gloss: m.gloss,
             headline: c.contribution_id === bundle.account.headline_contribution_id,
             meters: [{ label: m.gloss, fraction: m.magnitude, tone: m.positive ? "pos" : "neg",
                        metric: analyst ? metricText(bundle, c.contribution_id) : null }] };
  }
  if (step.kind === "outcome") {
    const o = outcomeView(bundle, mode);
    return { ...base, title: o.result, teamId: bundle.account.outcome.beneficiary_team_id, gloss: o.primary,
             headline: false, meters: [{ label: o.primary, fraction: o.fraction, tone: "outcome", metric: o.metric }] };
  }
  const cf = counterfactualFor(bundle, step.contribution_id!)!;
  const v = decisionView(bundle, cf, mode);
  return { ...base, title: "The decision", teamId: contribution(bundle, cf.contribution_id).team_id,
           gloss: "a better option was on", headline: false,
           meters: [{ label: v.chosen.label, fraction: v.chosen.fraction, tone: "chosen", metric: v.chosen.metric },
                    { label: v.better.label, fraction: v.better.fraction, tone: "better", metric: v.better.metric }] };
}

// ------------------------------------------------------------------------------- outcome and decision

export interface OutcomeView {
  result: string; // "A goal that didn't happen"
  primary: string; // Analyst: "15% chance of scoring"; Fan: "A good chance"
  fraction: number; // the outcome's value, 0..1, for the radial / bar
  metric: string | null; // Analyst: "xG 0.152"
  realized: boolean;
}

export function outcomeView(bundle: Bundle, mode: Mode): OutcomeView {
  const { outcome } = bundle.account;
  const d = bundle.outcome_display;
  const band = d.band.charAt(0).toUpperCase() + d.band.slice(1);
  return {
    result: d.result,
    primary: mode === "analyst" ? d.label : band,
    fraction: outcome.value,
    metric: mode === "analyst" ? `${outcome.value_source === "xg" ? "xG" : "xT"} ${outcome.value.toFixed(3)}` : null,
    realized: outcome.realized,
  };
}

export interface OptionView {
  label: string;
  fraction: number; // relative to the better of the two
  metric: string | null;
}

/** Chosen vs best alternative: plain labels, bars relative to the better option, values in Analyst only. */
export function decisionView(bundle: Bundle, cf: Counterfactual, mode: Mode): { chosen: OptionView; better: OptionView } {
  const best = cf.alternatives[0];
  const top = Math.max(best.value, cf.chosen_value, 1e-9);
  const named = (text: string) => text.replace(/[A-Z]{2,4}-\d{2}/g, (id) => playerLabel(bundle, id));
  const analyst = mode === "analyst";
  return {
    chosen: { label: `Chosen: ${named(cf.chosen)}`, fraction: cf.chosen_value / top,
              metric: analyst ? `option value ${cf.chosen_value.toFixed(3)}` : null },
    better: { label: `Better: ${named(best.description)}`, fraction: best.value / top,
              metric: analyst ? `option value ${best.value.toFixed(3)}`
                + (best.completion_prob !== null ? ` · completion ${best.completion_prob.toFixed(2)}` : "") : null },
  };
}

// ------------------------------------------------------------------------------------------ the header

export interface MomentHeader {
  classLabel: string;
  framing: "realized" | "prevented";
  clock: string;
  description: string | null; // the narration's headline line, when there is a narration
}

export function momentHeader(bundle: Bundle): MomentHeader {
  const { outcome, moment } = bundle.account;
  return {
    classLabel: moment.type.replace(/_/g, " ").toUpperCase(),
    framing: outcome.realized ? "realized" : "prevented",
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
  all: NarrationSentence[];
  source: string; // who wrote it, as recorded by Build 6
}

export function summary(bundle: Bundle): Summary | null {
  const n = bundle.narration;
  if (!n) return null;
  const source = n.source === "foundry" ? `Narrated by ${n.model?.split("@")[0] ?? "Foundry"} on Microsoft Foundry`
                                        : "Template narration (no model)";
  return { all: n.sentences, source: `${source} · grounded in the account` };
}
