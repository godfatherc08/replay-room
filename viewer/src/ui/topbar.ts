// Top bar: logo, the scoreline (home, score at the replay time, match clock, away), mode switch, icons.

import { matchClock, scoreAt } from "../account";
import type { Bundle } from "../bundle";
import type { Clock } from "../timeline";
import { COLORS } from "../overlays";
import { button, el, icon } from "./dom";
import type { Mode, UIState } from "./state";

/** A plain shield in the side's shirt colour with the team's short name: decoration, not a crest. */
export function badge(bundle: Bundle, teamId: string): HTMLElement {
  const team = bundle.teams.find((t) => t.team_id === teamId);
  const color = team?.side === "home" ? COLORS.home : COLORS.away;
  const span = el("span", "rr-badge");
  span.innerHTML = `<svg viewBox="0 0 32 36" width="26" height="30" aria-hidden="true">`
    + `<path d="M16 1l14 5v11c0 9-6.5 15.5-14 18C8.5 32.5 2 26 2 17V6z" fill="${color}" stroke="#0b1220" stroke-width="1.5"/>`
    + `<text x="16" y="21" text-anchor="middle" font-size="8.5" font-weight="700" fill="#fff" `
    + `font-family="Inter,system-ui,sans-serif">${team?.short_name ?? teamId}</text></svg>`;
  return span;
}

export interface TopbarHandle {
  sync(): void;
  legendToggle: HTMLInputElement;
}

export function buildTopbar(root: HTMLElement, bundle: Bundle, clock: Clock, state: UIState): TopbarHandle {
  root.replaceChildren();
  const logo = el("div", "rr-logo");
  logo.innerHTML = `<svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true"><path d="M6 26V6h11a6 6 0 0 1 0 12h-6l9 8" `
    + `fill="none" stroke="#e6edf5" stroke-width="3.4" stroke-linejoin="round"/></svg><span>REPLAY ROOM</span>`;

  const line = el("div", "rr-scoreline");
  const home = el("div", "rr-team");
  home.append(badge(bundle, bundle.match.home.team_id), el("span", "rr-team-name", bundle.match.home.name));
  const mid = el("div", "rr-score-mid");
  const score = el("div", "rr-score");
  const time = el("div", "rr-clock");
  mid.append(score, time);
  const away = el("div", "rr-team");
  away.append(el("span", "rr-team-name", bundle.match.away.name), badge(bundle, bundle.match.away.team_id));
  line.append(home, mid, away);

  const right = el("div", "rr-top-right");
  const modes = el("div", "rr-mode");
  const modeButtons = (["analyst", "fan"] as Mode[]).map((m) => {
    const b = button("rr-mode-btn", m === "analyst" ? "Analyst view" : "Fan view", m === "analyst" ? "Analyst" : "Fan");
    b.dataset.mode = m;
    b.addEventListener("click", () => state.setMode(m));
    modes.append(b);
    return b;
  });
  const settings = button("rr-icon-btn", "Display settings", icon("settings"));
  const menu = el("div", "rr-menu");
  menu.hidden = true;
  const item = el("label", "rr-menu-item");
  const legendToggle = el("input");
  legendToggle.type = "checkbox";
  legendToggle.checked = true;
  item.append(legendToggle, el("span", undefined, "Show legend"));
  menu.append(item);
  settings.addEventListener("click", () => (menu.hidden = !menu.hidden));
  const full = button("rr-icon-btn", "Fullscreen", icon("fullscreen"));
  full.addEventListener("click", () => {
    if (document.fullscreenElement) void document.exitFullscreen?.();
    else void document.documentElement.requestFullscreen?.();
  });
  const profile = button("rr-icon-btn", "Not signed in", icon("profile"));
  profile.disabled = true;
  right.append(modes, settings, full, profile, menu);
  root.append(logo, line, right);

  const sync = () => {
    const s = scoreAt(bundle, clock.time);
    score.textContent = `${s.home} - ${s.away}`;
    time.textContent = matchClock(bundle, clock.time);
    for (const b of modeButtons) b.classList.toggle("rr-on", b.dataset.mode === state.mode);
  };
  state.onChange(sync);
  sync();
  return { sync, legendToggle };
}
