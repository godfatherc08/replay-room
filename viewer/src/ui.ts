// The DOM around the canvas: outcome banner, contribution panel (headline first), transport.
// Every label is a field of the account or the bundle; nothing here is generated prose.

import { outcomeBanner, panelItems } from "./account";
import type { IndexEntry } from "./bundle";
import type { Viewer } from "./controller";

export interface UIOptions {
  moments?: IndexEntry[];
  current?: string;
  onPick?: (momentId: string) => void;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

export function buildUI(root: HTMLElement, viewer: Viewer, opts: UIOptions = {}): void {
  const { bundle, clock } = viewer;
  root.replaceChildren();

  const header = el("header", "rr-header");
  if (opts.moments && opts.moments.length) {
    const pick = el("select", "rr-moment");
    pick.setAttribute("aria-label", "moment");
    for (const m of opts.moments) {
      const o = el("option", undefined, `${m.moment_id}${m.realized ? "" : " (prevented)"}`);
      o.value = m.moment_id;
      o.selected = m.moment_id === opts.current;
      pick.append(o);
    }
    pick.addEventListener("change", () => opts.onPick?.(pick.value));
    header.append(pick);
  }
  const banner = outcomeBanner(bundle);
  const b = el("div", `rr-banner rr-${banner.framing}`);
  b.dataset.framing = banner.framing;
  b.append(el("strong", undefined, banner.title), el("span", undefined, banner.detail));
  header.append(b);

  const panel = el("ol", "rr-panel");
  panel.setAttribute("aria-label", "contributions");
  const buttons = new Map<string, HTMLButtonElement>();
  for (const item of panelItems(bundle)) {
    const li = el("li");
    const btn = el("button", `rr-item rr-${item.track}${item.headline ? " rr-headline" : ""}`);
    btn.type = "button";
    btn.dataset.id = item.id;
    btn.dataset.frame = String(item.frameId);
    btn.style.setProperty("--team", bundle.teams.find((t) => t.team_id === item.teamId)?.side === "home" ? "#3b82f6" : "#ef4444");
    btn.append(
      el("span", "rr-rank", item.headline ? "headline" : `#${item.rank}`),
      el("span", "rr-player", `${item.playerLabel} · ${item.teamName}`),
      el("span", "rr-label", `${item.label} · ${item.role.replace(/_/g, " ")}`),
      el("span", `rr-effect ${item.effect >= 0 ? "rr-pos" : "rr-neg"}`, item.effectText),
      el("span", "rr-meta", `${item.track.replace("_", "-")} · frame ${item.frameId}${item.inWindow ? "" : " (event before the window)"}${item.hasCounterfactual ? " · counterfactual" : ""}`),
    );
    btn.addEventListener("click", () => {
      viewer.jump(item.id);
      for (const [id, other] of buttons) other.classList.toggle("rr-active", id === item.id);
    });
    buttons.set(item.id, btn);
    li.append(btn);
    panel.append(li);
  }

  const transport = el("div", "rr-transport");
  const play = el("button", "rr-play", "Play");
  play.type = "button";
  play.addEventListener("click", () => clock.toggle());
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
  const speed = el("select", "rr-speed");
  speed.setAttribute("aria-label", "speed");
  for (const s of [0.25, 0.5, 1, 2]) {
    const o = el("option", undefined, `${s}×`);
    o.value = String(s);
    o.selected = s === 1;
    speed.append(o);
  }
  speed.addEventListener("change", () => clock.setSpeed(Number(speed.value)));
  const reset = el("button", "rr-clear", "Clear");
  reset.type = "button";
  reset.addEventListener("click", () => {
    viewer.clear();
    for (const other of buttons.values()) other.classList.remove("rr-active");
  });
  const time = el("span", "rr-time");
  transport.append(play, scrub, speed, reset, time);

  const sync = () => {
    play.textContent = clock.playing ? "Pause" : "Play";
    scrub.value = String(clock.pos);
    time.textContent = `P${bundle.frames.period_id} ${clock.time.toFixed(1)} s · frame ${clock.frameId}`;
  };
  clock.onChange(sync);
  sync();

  root.append(header, panel, transport);
}
