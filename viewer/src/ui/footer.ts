// The Match Timeline (docs/evidence-treatise.md §5.3): one dark panel, three tiers and the selected moment.
//
// 1. Header: MATCH TIMELINE, and the clock `<current> / <total>` (the replay position; the match length).
// 2. Replay progress: the amber play / pause disc (in step with Space), the seek bar (amber = played, drag to
//    seek) and the speed. In Story it plays the guided analysis; in Explore, the replay.
// 3. Match events: one dot per event of the moment's window, placed at its time and coloured by its kind
//    (pass / build-up, defensive error, shot / outcome; the exporter's `timeline` field), with the legend and
//    window-scoped ticks. A dot seeks the replay to its event and, when the account cites it, opens its proof.
// 4. Selected moment: the moment's time, its one-line claim (the telling's headline) and its outcome metric
//    (Fan: the gloss only).
//
// Four colours and no more: amber owns progress; blue, orange and green are the event kinds.

import { matchClock, momentHeader, outcomeView } from "../account";
import type { BundleEvent } from "../bundle";
import type { Viewer } from "../controller";
import { button, el, icon, mmss } from "./dom";
import type { EvidenceKey, UIState } from "./state";

export interface FooterHandle {
  sync(): void;
}

export const SPEEDS = [0.5, 1, 1.5, 2];

export const EVENT_KINDS: [BundleEvent["timeline"], string][] = [
  ["build_up", "Pass / build-up"],
  ["defensive_error", "Defensive error"],
  ["shot_outcome", "Shot / outcome"],
];

export interface FooterActions {
  onPick?: (momentId: string) => void;
  jump(id: string): void; // a fact, in Explore
  afterJump(): void; // the viewer jumped by itself
  scrub(): void; // the user took the playhead: leave Story
  evidence?(key: EvidenceKey): void; // open a fact's proof
}

export function buildFooter(root: HTMLElement, viewer: Viewer, state: UIState, actions: FooterActions): FooterHandle {
  const { bundle, clock, story } = viewer;
  root.replaceChildren();
  const ts = bundle.frames.timestamps;
  const t0 = ts[0];
  const span = Math.max(ts[ts.length - 1] - t0, 1e-6);
  const at = (t: number) => `${(100 * (Math.min(Math.max(t, t0), t0 + span) - t0)) / span}%`;

  // 1. header
  const head = el("div", "rr-tl-head");
  const now = el("span", "rr-tl-clock");
  head.append(el("span", "rr-tl-title", "MATCH TIMELINE"), now);

  // 2. replay progress
  const progress = el("div", "rr-tl-row rr-tl-progress");
  const play = button("rr-play", "Play analysis", icon("play", 16));
  play.addEventListener("click", () => (state.view === "story" ? story.toggle() : clock.toggle()));
  const scrub = el("input", "rr-scrub");
  scrub.type = "range";
  scrub.min = "0";
  scrub.max = String(clock.last);
  scrub.step = "0.01";
  scrub.setAttribute("aria-label", "Replay progress");
  scrub.addEventListener("input", () => {
    actions.scrub();
    clock.pause();
    clock.seekIndex(Number(scrub.value));
  });
  const speed = el("select", "rr-speed");
  speed.setAttribute("aria-label", "speed");
  for (const s of SPEEDS) {
    const o = el("option", undefined, `${s}×`);
    o.value = String(s);
    o.selected = s === 1;
    speed.append(o);
  }
  speed.addEventListener("change", () => {
    story.setSpeed(Number(speed.value));
    clock.setSpeed(Number(speed.value));
  });
  const progressLabels = el("div", "rr-tl-labels");
  const right = el("span", "rr-tl-right");
  right.append(el("span", "rr-tl-hint", "Drag to seek"), speed);
  progressLabels.append(el("span", "rr-tl-label", "Replay progress"), right);
  const progressBody = el("div", "rr-tl-body");
  progressBody.append(progressLabels, scrub);
  progress.append(play, progressBody);

  // 3. match events: the window's events, as they are
  const events = el("div", "rr-tl-row rr-tl-events");
  const eventLabels = el("div", "rr-tl-labels");
  eventLabels.append(el("span", "rr-tl-label", "Match events"), el("span", "rr-tl-hint", "Select an event to jump to it"));
  const track = el("div", "rr-tl-track");
  const cited = new Map(bundle.account.contributions
    .filter((c) => c.track === "on_ball" && c.evidence[0].kind === "event")
    .map((c) => [(c.evidence[0] as { action_id: number }).action_id, c.contribution_id]));
  for (const e of bundle.events.filter((x) => x.in_window)) {
    const dot = button(`rr-tl-dot rr-ev-${e.timeline}`,
                       `${e.original_event_id}: ${e.type.replace(/_/g, " ")} at ${matchClock(bundle, e.t)}`, "");
    dot.dataset.event = e.original_event_id;
    dot.dataset.kind = e.timeline;
    dot.style.left = at(e.t);
    dot.addEventListener("click", () => {
      actions.scrub();
      const id = cited.get(e.action_id);
      if (id) {
        actions.jump(id);
        actions.evidence?.({ contribution: id });
      } else {
        clock.pause();
        clock.seekFrame(e.frame_id);
      }
    });
    track.append(dot);
  }
  const ticks = el("div", "rr-tl-ticks");
  for (const f of [0, 0.25, 0.5, 0.75, 1]) {
    const tick = el("span", undefined, matchClock(bundle, t0 + f * span));
    tick.style.left = `${100 * f}%`;
    ticks.append(tick);
  }
  const legend = el("div", "rr-tl-legend");
  for (const [kind, label] of EVENT_KINDS) {
    const item = el("span", "rr-tl-key");
    item.append(el("span", `rr-tl-dot-key rr-ev-${kind}`), el("span", undefined, label));
    legend.append(item);
  }
  const eventBody = el("div", "rr-tl-body");
  eventBody.append(eventLabels, track, ticks, legend);
  events.append(eventBody);

  // 4. the selected moment
  const card = el("div", "rr-tl-card");
  const renderCard = () => {
    const h = momentHeader(bundle, state.mode);
    const o = outcomeView(bundle, state.mode);
    const top = el("div", "rr-tl-card-top");
    top.append(el("span", "rr-tl-moment-icon", "◎"), el("span", "rr-tl-label", `Selected moment · ${h.clock}`));
    const claim = el("p", "rr-tl-claim", h.description ?? o.result);
    const metric = el("p", "rr-tl-metric", `${bundle.outcome_display.label}${o.metric ? ` · ${o.metric}` : ""}`);
    card.replaceChildren(top, claim, metric);
  };
  renderCard();

  root.append(head, progress, events, card);

  let shown = "";
  let mode = state.mode;
  const sync = () => {
    const playing = state.view === "story" ? story.playing : clock.playing;
    const label = state.view === "story" ? (playing ? "Pause analysis" : "Play analysis") : playing ? "Pause" : "Play";
    if (label !== shown) {
      play.innerHTML = icon(playing ? "pause" : "play", 16);
      play.title = label;
      play.setAttribute("aria-label", label);
      shown = label;
    }
    if (state.mode !== mode) {
      mode = state.mode;
      renderCard();
    }
    scrub.value = String(clock.pos);
    scrub.style.setProperty("--played", `${(100 * clock.pos) / Math.max(clock.last, 1)}%`);
    now.textContent = `${matchClock(bundle, clock.time)} / ${mmss(bundle.match.duration_s)}`;
  };
  clock.onChange(sync);
  story.onChange(sync);
  state.onChange(sync);
  sync();
  return { sync };
}
