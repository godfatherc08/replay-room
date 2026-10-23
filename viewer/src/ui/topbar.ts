// Top bar: logo, the scoreline (home, score at the replay time, match clock, away), the Story / Explore and
// Analyst / Fan switches, and the match's moments.

import { matchClock, scoreAt } from "../account";
import type { Bundle } from "../bundle";
import type { Clock } from "../timeline";
import { teamColor } from "../overlays";
import { el } from "./dom";
import type { Mode, UIState, View } from "./state";

/** A plain shield in the team's shirt colour with its short name: decoration, not a crest. */
export function badge(bundle: Bundle, teamId: string, size = 22): HTMLElement {
  const team = bundle.teams.find((t) => t.team_id === teamId);
  const span = el("span", "rr-badge");
  span.innerHTML = `<svg viewBox="0 0 32 36" width="${size}" height="${Math.round(size * 1.12)}" aria-hidden="true">`
    + `<path d="M16 1l14 5v11c0 9-6.5 15.5-14 18C8.5 32.5 2 26 2 17V6z" fill="${teamColor(bundle, teamId)}" stroke="#0b1220" stroke-width="1.5"/>`
    + `<text x="16" y="21" text-anchor="middle" font-size="8.5" font-weight="700" fill="#fff" `
    + `font-family="Inter,system-ui,sans-serif">${team?.short_name ?? teamId}</text></svg>`;
  return span;
}

export interface TopbarHandle {
  sync(): void;
}

function segmented<T extends string>(cls: string, items: [T, string][], pick: (v: T) => void): { root: HTMLElement; set(v: T): void } {
  const root = el("div", `rr-seg ${cls}`);
  root.setAttribute("role", "radiogroup");
  const buttons = items.map(([value, label]) => {
    const b = el("button", "rr-seg-btn", label);
    b.type = "button";
    b.dataset.value = value;
    b.setAttribute("role", "radio");
    b.addEventListener("click", () => pick(value));
    root.append(b);
    return b;
  });
  return {
    root,
    set: (v) => {
      for (const b of buttons) {
        const on = b.dataset.value === v;
        b.classList.toggle("rr-on", on);
        b.setAttribute("aria-checked", String(on));
      }
    },
  };
}

export function buildTopbar(root: HTMLElement, bundle: Bundle, clock: Clock, state: UIState,
                            onPick: ((momentId: string) => void) | undefined): TopbarHandle {
  root.replaceChildren();
  const logo = el("div", "rr-logo");
  logo.innerHTML = `<svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true"><path d="M6 26V6h11a6 6 0 0 1 0 12h-6l9 8" `
    + `fill="none" stroke="currentColor" stroke-width="3.4" stroke-linejoin="round"/></svg><span>REPLAY ROOM</span>`;

  const line = el("div", "rr-scoreline");
  const home = el("div", "rr-team");
  home.append(el("span", "rr-team-name", bundle.match.home.name), badge(bundle, bundle.match.home.team_id));
  const mid = el("div", "rr-score-mid");
  const score = el("div", "rr-score");
  const time = el("div", "rr-clock");
  mid.append(score, time);
  const away = el("div", "rr-team");
  away.append(badge(bundle, bundle.match.away.team_id), el("span", "rr-team-name", bundle.match.away.name));
  line.append(home, mid, away);

  const right = el("div", "rr-top-right");
  const views = segmented<View>("rr-views", [["story", "Story"], ["explore", "Explore"]], (v) => state.setView(v));
  const modes = segmented<Mode>("rr-modes", [["analyst", "Analyst"], ["fan", "Fan"]], (m) => state.setMode(m));
  const picker = el("select", "rr-picker");
  picker.setAttribute("aria-label", "moment");
  for (const m of bundle.match_moments) {
    const o = el("option", undefined, `${m.match_clock} · ${m.type.replace(/_/g, " ")}`);
    o.value = m.moment_id;
    o.selected = m.moment_id === bundle.account.moment.moment_id;
    picker.append(o);
  }
  picker.addEventListener("change", () => onPick?.(picker.value));
  right.append(views.root, modes.root, picker);
  root.append(logo, line, right);

  const sync = () => {
    const s = scoreAt(bundle, clock.time);
    score.textContent = `${s.home} – ${s.away}`;
    time.textContent = matchClock(bundle, clock.time);
    views.set(state.view);
    modes.set(state.mode);
  };
  state.onChange(sync);
  sync();
  return { sync };
}
