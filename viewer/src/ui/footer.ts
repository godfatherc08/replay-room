// Footer: transport (play/pause, previous/next evidence, speed), the timeline, Live (not connected), match time.
//
// The timeline has two rows. The match strip spans the whole match with a marker per exported moment
// (click to open it) and the replayed window highlighted. Under it, the scrubber spans the window we
// have tracking for, with a marker per piece of evidence (click to jump) and a bubble at the playhead.

import { evidenceRows, matchClock } from "../account";
import type { Viewer } from "../controller";
import { button, el, icon, mmss } from "./dom";

export interface FooterHandle {
  sync(): void;
  onJump(fn: () => void): void;
}

function clockSeconds(text: string): number {
  const [m, s] = text.split(":").map(Number);
  return 60 * m + s;
}

export function buildFooter(root: HTMLElement, viewer: Viewer, onPick: ((id: string) => void) | undefined): FooterHandle {
  const { bundle, clock } = viewer;
  const jumped: (() => void)[] = [];
  const afterJump = () => jumped.forEach((f) => f());
  root.replaceChildren();

  const transport = el("div", "rr-transport");
  const play = button("rr-play", "Play", icon("play", 22));
  play.addEventListener("click", () => clock.toggle());
  const prev = button("rr-step", "Previous evidence", icon("prev", 16));
  prev.addEventListener("click", () => { viewer.stepEvidence(-1); afterJump(); });
  const next = button("rr-step", "Next evidence", icon("next", 16));
  next.addEventListener("click", () => { viewer.stepEvidence(1); afterJump(); });
  const speed = el("select", "rr-speed");
  speed.setAttribute("aria-label", "speed");
  for (const s of [0.25, 0.5, 1, 2]) {
    const o = el("option", undefined, `${s}x`);
    o.value = String(s);
    o.selected = s === 1;
    speed.append(o);
  }
  speed.addEventListener("change", () => clock.setSpeed(Number(speed.value)));
  transport.append(play, prev, next, speed);

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
    if (!current) mark.addEventListener("click", () => onPick?.(m.moment_id));
    strip.append(mark);
  }
  const stripLabels = el("div", "rr-strip-labels");
  stripLabels.append(el("span", undefined, "00:00"), el("span", undefined, mmss(total)));

  // window scrubber
  const track = el("div", "rr-track");
  const scrub = el("input", "rr-scrub");
  scrub.type = "range";
  scrub.min = "0";
  scrub.max = String(clock.last);
  scrub.step = "0.01";
  scrub.setAttribute("aria-label", "timeline");
  scrub.addEventListener("input", () => {
    clock.pause();
    clock.seekIndex(Number(scrub.value));
  });
  const span = Math.max(ts[ts.length - 1] - ts[0], 1e-6);
  for (const r of evidenceRows(bundle)) {
    const m = button(`rr-tl-marker ${r.headline ? "rr-headline" : r.positive ? "rr-pos" : "rr-neg"}`,
                     `${r.number}. ${r.title} (${r.valueText}) at ${r.clock}`, "");
    m.dataset.id = r.id;
    m.style.left = `${(100 * (Math.min(Math.max(r.t, ts[0]), ts[ts.length - 1]) - ts[0])) / span}%`;
    m.addEventListener("click", () => { viewer.jump(r.id); afterJump(); });
    track.append(m);
  }
  const bubble = el("div", "rr-bubble");
  track.append(scrub, bubble);
  const ticks = el("div", "rr-ticks");
  ticks.append(el("span", undefined, matchClock(bundle, ts[0])), el("span", undefined, matchClock(bundle, ts[ts.length - 1])));
  timeline.append(strip, stripLabels, track, ticks);

  const live = el("label", "rr-live");
  live.title = "Live feed not connected: this is a replay";
  const liveBox = el("input");
  liveBox.type = "checkbox";
  liveBox.disabled = true;
  live.append(el("span", undefined, "Live"), liveBox);
  const readout = el("div", "rr-readout");
  const now = el("strong", "rr-now");
  readout.append(el("span", undefined, "Match time"), now);
  root.append(transport, timeline, live, readout);

  const sync = () => {
    play.innerHTML = icon(clock.playing ? "pause" : "play", 22);
    play.title = clock.playing ? "Pause" : "Play";
    scrub.value = String(clock.pos);
    const text = matchClock(bundle, clock.time);
    bubble.textContent = text;
    bubble.style.left = `${(100 * clock.pos) / Math.max(clock.last, 1)}%`;
    now.textContent = text;
  };
  clock.onChange(sync);
  sync();
  return { sync, onJump: (fn) => jumped.push(fn) };
}
