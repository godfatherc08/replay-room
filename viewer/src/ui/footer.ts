// Footer: transport, speed, the timeline, and the match time.
//
// In Story the transport plays the guided analysis (◀ / ▶ step through it, speed sets the dwell); in Explore
// it plays the replay (◀ / ▶ jump between facts). The timeline has two rows: the match strip spans the
// whole match with a marker per exported moment (click to open it) and the replayed window highlighted;
// under it, the scrubber spans the window we have tracking for, with a marker per fact (click to jump).

import { evidenceRows, matchClock } from "../account";
import type { Viewer } from "../controller";
import { button, el, icon, mmss } from "./dom";
import type { UIState } from "./state";

export interface FooterHandle {
  sync(): void;
}

export const SPEEDS = [0.5, 1, 1.5, 2];

function clockSeconds(text: string): number {
  const [m, s] = text.split(":").map(Number);
  return 60 * m + s;
}

export interface FooterActions {
  onPick?: (momentId: string) => void;
  jump(id: string): void; // a fact, in Explore
  afterJump(): void; // the viewer jumped by itself (◀ / ▶ in Explore)
  scrub(): void; // the user took the playhead: leave Story
}

export function buildFooter(root: HTMLElement, viewer: Viewer, state: UIState, actions: FooterActions): FooterHandle {
  const { bundle, clock, story } = viewer;
  root.replaceChildren();

  const transport = el("div", "rr-transport");
  const prev = button("rr-step", "Previous step", icon("prev", 14));
  const play = button("rr-play", "Play analysis", icon("play", 18));
  const next = button("rr-step", "Next step", icon("next", 14));
  const stepBy = (dir: 1 | -1) => {
    if (state.view === "story") {
      if (dir > 0) story.next();
      else story.prev();
      return;
    }
    viewer.stepEvidence(dir);
    actions.afterJump();
  };
  prev.addEventListener("click", () => stepBy(-1));
  next.addEventListener("click", () => stepBy(1));
  play.addEventListener("click", () => (state.view === "story" ? story.toggle() : clock.toggle()));
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
  transport.append(prev, play, next, speed);

  // match strip
  const timeline = el("div", "rr-timeline");
  const strip = el("div", "rr-match-strip");
  const total = bundle.match.duration_s;
  const ts = bundle.frames.timestamps;
  const w0 = bundle.match.period_offset_s + ts[0];
  const w1 = bundle.match.period_offset_s + ts[ts.length - 1];
  const win = el("div", "rr-strip-window");
  win.style.left = `${(100 * w0) / total}%`;
  win.style.width = `${(100 * (w1 - w0)) / total}%`;
  strip.append(win);
  for (const m of bundle.match_moments) {
    const current = m.moment_id === bundle.account.moment.moment_id;
    const mark = button(`rr-strip-mark rr-${m.realized ? "realized" : "prevented"}${current ? " rr-current" : ""}`,
                        `${m.type.replace(/_/g, " ")} at ${m.match_clock}`, "");
    mark.dataset.moment = m.moment_id;
    mark.style.left = `${(100 * clockSeconds(m.match_clock)) / total}%`;
    if (!current) mark.addEventListener("click", () => actions.onPick?.(m.moment_id));
    strip.append(mark);
  }

  // window scrubber
  const track = el("div", "rr-track");
  const scrub = el("input", "rr-scrub");
  scrub.type = "range";
  scrub.min = "0";
  scrub.max = String(clock.last);
  scrub.step = "0.01";
  scrub.setAttribute("aria-label", "timeline");
  scrub.addEventListener("input", () => {
    actions.scrub();
    clock.pause();
    clock.seekIndex(Number(scrub.value));
  });
  const span = Math.max(ts[ts.length - 1] - ts[0], 1e-6);
  for (const r of evidenceRows(bundle)) {
    const m = button(`rr-tl-marker ${r.headline ? "rr-headline" : r.positive ? "rr-pos" : "rr-neg"}`,
                     `${r.number}. ${r.player}: ${r.gloss} (${r.clock})`, "");
    m.dataset.id = r.id;
    m.style.left = `${(100 * (Math.min(Math.max(r.t, ts[0]), ts[ts.length - 1]) - ts[0])) / span}%`;
    m.addEventListener("click", () => actions.jump(r.id));
    track.append(m);
  }
  track.append(scrub);
  const ends = el("div", "rr-ticks");
  ends.append(el("span", undefined, matchClock(bundle, ts[0])), el("span", undefined, `of ${mmss(total)}`),
              el("span", undefined, matchClock(bundle, ts[ts.length - 1])));
  timeline.append(strip, track, ends);

  const readout = el("div", "rr-readout");
  const now = el("strong", "rr-now");
  readout.append(el("span", "rr-micro", "Match time"), now);
  root.append(transport, timeline, readout);

  let shown = "";
  const sync = () => {
    const playing = state.view === "story" ? story.playing : clock.playing;
    const label = state.view === "story" ? (playing ? "Pause analysis" : "Play analysis") : playing ? "Pause" : "Play";
    if (label !== shown) {
      play.innerHTML = icon(playing ? "pause" : "play", 18);
      play.title = label;
      play.setAttribute("aria-label", label);
      prev.title = state.view === "story" ? "Previous step" : "Previous fact";
      next.title = state.view === "story" ? "Next step" : "Next fact";
      shown = label;
    }
    scrub.value = String(clock.pos);
    now.textContent = matchClock(bundle, clock.time);
  };
  clock.onChange(sync);
  story.onChange(sync);
  state.onChange(sync);
  sync();
  return { sync };
}
