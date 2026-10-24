// What the panels, the ribbon and Story Mode say, straight from the bundle: no re-ranking, no new numbers.
//
// Number discipline: a value is presented as a meter (its normalized magnitude) and a gloss (plain words,
// from the exporter). The raw metric is secondary text, and only in Analyst mode. Fan mode never shows one.

import { type Bundle, type ContextFact, type Contribution, type Counterfactual, FACT_KINDS, type Link, type Meaning,
         type Proof, type StoryStep } from "./bundle";
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

/** A short name that never makes two players look like one: the surname, or "A. Larsen" when another player in
 *  this moment's bundle shares it (Alex Larsen and Casey Larsen). Display only: the names are the bundle's. */
export function shortName(bundle: Bundle, playerId: string): string {
  const all = bundle.teams.flatMap((t) => t.players);
  const p = all.find((q) => q.player_id === playerId);
  if (!p) return playerId;
  const parts = p.name.split(" ");
  const surname = parts.at(-1)!;
  const inMoment = new Set([...bundle.account.participants.map((q) => q.player_id),
                            ...bundle.objects.filter((o) => o.kind === "player").map((o) => o.id)]);
  const shared = all.some((q) => q.player_id !== playerId && inMoment.has(q.player_id)
                                 && q.name.split(" ").at(-1) === surname);
  return shared && parts.length > 1 ? `${parts[0][0]}. ${surname}` : surname;
}

/** "#11 Ferraro": the on-pitch name tag. */
export function shortLabel(bundle: Bundle, playerId: string): string {
  const p = bundle.teams.flatMap((t) => t.players).find((q) => q.player_id === playerId);
  return p ? `#${p.shirt_number} ${shortName(bundle, playerId)}` : playerId;
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

export function linkOf(bundle: Bundle, id: string): Link {
  const k = bundle.account.links.find((x) => x.link_id === id);
  if (!k) throw new Error(`no link ${id}`);
  return k;
}

export function contextFactOf(bundle: Bundle, id: string): ContextFact {
  const f = bundle.context?.facts.find((x) => x.fact_id === id);
  if (!f) throw new Error(`no context fact ${id}`);
  return f;
}

/** The players a link names: the defender first (the beat is about them), then the runner and the man. */
export function linkPlayers(link: Link): string[] {
  return [...new Set([link.defender_id, link.runner_id, link.marked_player_id].filter((x): x is string => !!x))];
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

/** The one caption line of a step, in the register: the analyst telling, or the fan telling (no numbers). */
export function stepCaption(step: StoryStep, mode: Mode): string {
  return mode === "fan" ? step.plain : step.caption;
}

/** Who a step puts in focus: a fact's named players; the outcome's shooter (and whoever denied it); the decider
 *  and the better option's target at a counterfactual. The first is the one who gets the name tag. */
export function stepPlayers(bundle: Bundle, step: StoryStep): string[] {
  if (FACT_KINDS.has(step.kind)) {
    const own = highlightedPlayers(contribution(bundle, step.contribution_id!));
    return step.link_id ? [...new Set([...own, ...linkPlayers(linkOf(bundle, step.link_id))])] : own;
  }
  if (step.kind === "link") return linkPlayers(linkOf(bundle, step.link_id!));
  if (step.kind === "context") return [];
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
  title: string; // "Robin Hale" / "The outcome" / "The decision" / "Match context"
  teamId: string | null;
  gloss: string;
  meters: { label: string; fraction: number; tone: "pos" | "neg" | "chosen" | "better" | "outcome"; metric: string | null }[];
  headline: boolean;
  chip: string | null; // "Key moment" / "Where it went wrong" / "Computed link" / "Match context"
}

const LINK_GLOSS: Record<Link["kind"], string> = {
  run_past: "beaten by a run into the space",
  dragged_out: "pulled out of the zone by a run",
  decoy_run: "taken away from the man by a run",
  lost_man: "lost the man into the zone",
};

const CONTEXT_TITLE: Record<ContextFact["kind"], string> = {
  line_height: "Back line height",
  marking_distance: "Room for the attackers",
  counter_press: "Winning the ball back",
};

/** A fact step's meter says only which way and how much (the caption already says what happened). */
const direction = (positive: boolean) => (positive ? "Helped the chance" : "Cost the chance");

function participant(bundle: Bundle, id: string): string {
  return bundle.account.participants.find((p) => p.player_id === id)?.name ?? id;
}

/** One chip at most, and never a repeat of the caption: the lead is the key moment; a beat told through a link
 *  the engine measured says so. A flaw's caption already says it is the flaw. */
function chipFor(step: StoryStep): string | null {
  if (step.emphasis === "lead") return "Key moment";
  if (step.link_id) return "Computed link";
  return null;
}

/** Everything the step card shows, mode-aware. Numbers appear only as Analyst `metric` text. */
export function stepView(bundle: Bundle, step: StoryStep, mode: Mode): StepView {
  const base = { index: step.index, total: bundle.story.length, kind: step.kind, caption: stepCaption(step, mode),
                 headline: step.emphasis === "lead" };
  const analyst = mode === "analyst";
  if (FACT_KINDS.has(step.kind)) {
    const c = contribution(bundle, step.contribution_id!);
    const m = meaningOf(bundle, c.contribution_id);
    const gloss = step.link_id ? LINK_GLOSS[linkOf(bundle, step.link_id).kind] : m.gloss;
    return { ...base, title: participant(bundle, c.player_id), teamId: c.team_id, gloss, chip: chipFor(step),
             meters: [{ label: direction(m.positive), fraction: m.magnitude, tone: m.positive ? "pos" : "neg",
                        metric: analyst ? metricText(bundle, c.contribution_id) : null }] };
  }
  if (step.kind === "link") {
    const k = linkOf(bundle, step.link_id!);
    const own = bundle.meaning.find((x) => x.contribution_id === k.defender_contribution_id);
    const away = k.metrics.spot_distance_end;
    return { ...base, title: participant(bundle, k.defender_id), teamId: bundle.account.outcome.conceding_team_id,
             gloss: LINK_GLOSS[k.kind], chip: "Computed link",
             meters: own ? [{ label: direction(own.positive), fraction: own.magnitude, tone: "pos",
                              metric: analyst && away !== undefined ? `${away.toFixed(1)} m from the shot` : null }] : [] };
  }
  if (step.kind === "context") {
    const f = contextFactOf(bundle, step.context_fact_id!);
    const top = Math.max(f.here, f.baseline, 1e-9);
    const unit = f.unit === "share" ? "" : ` ${f.unit}`;
    const fmt = (v: number) => (f.unit === "share" ? `${Math.round(100 * v)}%` : `${v.toFixed(1)}${unit}`);
    const spread = f.spread ? ` · usual ${fmt(f.spread[0])}–${fmt(f.spread[1])}` : "";
    return { ...base, title: CONTEXT_TITLE[f.kind], teamId: f.team_id, gloss: CONTEXT_TITLE[f.kind], chip: "Match context",
             meters: [{ label: "Here", fraction: f.here / top, tone: "neg", metric: analyst ? fmt(f.here) : null },
                      { label: "Usually", fraction: f.baseline / top, tone: "chosen",
                        metric: analyst ? `${fmt(f.baseline)}${spread} · ${f.confidence} confidence, ${f.sample_size} samples`
                                        : null }] };
  }
  if (step.kind === "outcome") {
    const o = outcomeView(bundle, mode);
    return { ...base, title: o.result, teamId: bundle.account.outcome.beneficiary_team_id, gloss: o.primary, chip: null,
             headline: false, meters: [{ label: o.primary, fraction: o.fraction, tone: "outcome", metric: o.metric }] };
  }
  const cf = counterfactualFor(bundle, step.contribution_id!)!;
  const v = decisionView(bundle, cf, mode);
  return { ...base, title: "The decision", teamId: contribution(bundle, cf.contribution_id).team_id,
           gloss: "a better option was on", headline: false, chip: null,
           meters: [{ label: v.chosen.label, fraction: v.chosen.fraction, tone: "chosen", metric: v.chosen.metric },
                    { label: v.better.label, fraction: v.better.fraction, tone: "better", metric: v.better.metric }] };
}

// ------------------------------------------------------------------------------------------ the proof

/** The proof behind a story beat or a fact of the account. */
export function proofOf(bundle: Bundle, key: { beat: string } | { contribution: string }): Proof {
  const p = "beat" in key ? bundle.proofs.beats[key.beat] : bundle.proofs.contributions[key.contribution];
  if (!p) throw new Error(`no proof for ${JSON.stringify(key)}`);
  return p;
}

/** The at-a-glance evidence status: "2 events · frame 2419" (every count from the proof itself). */
export function evidenceChip(p: Proof): string {
  const parts: string[] = [];
  if (p.events.length) parts.push(`${p.events.length} event${p.events.length > 1 ? "s" : ""}`);
  if (p.frames.length) parts.push(`frame ${p.frames[p.frames.length - 1].frame_id}`);
  else parts.push(`frame ${p.focus_frame}`);
  return parts.join(" · ");
}

export interface ProofView {
  players: { id: string; label: string; role: string; teamId: string | null }[];
  frames: string[]; // "frame 2419 · 04:01 · where the run ended"
  events: string[]; // "ev00220 · pass · Robin Hale · 04:00"
  measured: { text: string; magnitude: number | null; metric: string | null }[];
}

/** The proof in the register: Analyst states the measured number and its meaning; Fan the same meaning in words.
 *  Ids and match clocks are records, not metrics: both registers list them. */
export function proofView(p: Proof, mode: Mode): ProofView {
  const analyst = mode === "analyst";
  return {
    players: p.players.map((x) => ({ id: x.player_id, role: x.role, teamId: x.team_id,
                                     label: x.shirt_number !== null ? `#${x.shirt_number} ${x.name}` : x.name })),
    frames: p.frames.map((f) => `frame ${f.frame_id} · ${f.match_clock} · ${f.what}`),
    events: p.events.map((e) => `${e.original_event_id} · ${e.type.replace(/_/g, " ")} · ${e.player} · ${e.match_clock}`),
    measured: p.measured.map((m) => ({ text: analyst ? m.statement : m.plain, magnitude: m.magnitude,
                                       metric: analyst ? m.metric : null })),
  };
}

/** The first sentence of a telling: the card's one-line claim. */
export function firstSentence(text: string): string {
  const m = text.match(/^.*?[.!?](?=\s+[A-Z"]|$)/);
  return (m ? m[0] : text).trim();
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
  description: string | null; // the telling's headline, in the register
}

export function momentHeader(bundle: Bundle, mode: Mode = "analyst"): MomentHeader {
  const { outcome, moment } = bundle.account;
  return {
    classLabel: moment.type.replace(/_/g, " ").toUpperCase(),
    framing: outcome.realized ? "realized" : "prevented",
    clock: bundle.match.moment_clock,
    description: lede(bundle, mode),
  };
}

/** The telling's headline, without the result it would repeat ("A goal that didn't happen: ..."). */
function lede(bundle: Bundle, mode: Mode): string | null {
  const line = (mode === "fan" ? bundle.narration?.headline_fan : bundle.narration?.headline) ?? null;
  const result = `${bundle.outcome_display.result}: `;
  if (!line || !line.startsWith(result)) return line;
  const rest = line.slice(result.length);
  return rest.charAt(0).toUpperCase() + rest.slice(1);
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
  lines: string[]; // every beat, in the register
  source: string; // who planned and wrote it, as recorded by the agents
}

export function summary(bundle: Bundle, mode: Mode = "analyst"): Summary | null {
  const n = bundle.narration;
  if (!n) return null;
  const writer = n.source === "foundry" ? `Told by ${n.model?.split("@")[0] ?? "Foundry"} on Microsoft Foundry`
                                        : "Told by the deterministic composer (no model)";
  const planner = n.plan_source === "foundry" ? "planned by the Foundry Analyst" : "planned by the rules";
  return { lines: bundle.story.map((s) => stepCaption(s, mode)),
           source: `${writer}, ${planner} · every line checked by the Critic` };
}
