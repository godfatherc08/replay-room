// Left rail: Match, Moments, Tactics, Evidence. Each switches what the right panel shows.

import { button, el, icon } from "./dom";
import type { UIState } from "./state";

export interface RailActions {
  showMoments(): void; // list the match's moments
  showEvidence(): void; // scroll the evidence list into view
}

export function buildRail(root: HTMLElement, state: UIState, actions: RailActions): void {
  root.replaceChildren();
  const items: [string, string, () => void][] = [
    ["match", "Match", () => state.setTab("event")],
    ["moments", "Moments", () => actions.showMoments()],
    ["tactics", "Tactics", () => state.setTab("tactics")],
    ["evidence", "Evidence", () => { state.setTab("event"); actions.showEvidence(); }],
  ];
  const buttons = items.map(([key, label, act]) => {
    const b = button("rr-rail-btn", label, `${icon(key)}<span>${label}</span>`);
    b.dataset.rail = key;
    b.addEventListener("click", () => {
      act();
      for (const o of buttons) o.classList.toggle("rr-on", o === b);
    });
    root.append(b);
    return b;
  });
  buttons[0].classList.add("rr-on");
  root.append(el("div", "rr-rail-spacer"));
}
