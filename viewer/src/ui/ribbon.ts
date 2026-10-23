// The causal-chain ribbon: one node per story step, left to right in play order, joined by arrowed connectors.
//
// A contribution's node shows its role icon, a ring in its team's colour and a bar whose height is its
// normalized |effect| (green helped the chance, red cost it), so the shape of the attack reads at a glance.
// The headline's node carries the accent ring. The outcome and the counterfactual close the chain. A fill
// sweeps along the track as Story plays; the current node pulses. Clicking a node shows that step.

import { meaningOf, playerLabel, stepCaption } from "../account";
import type { Bundle, StoryStep } from "../bundle";
import type { Viewer } from "../controller";
import { el, icon } from "./dom";
import type { UIState } from "./state";

export interface RibbonHandle {
  sync(): void; // the fill and the current node (call once per frame)
}

function nodeIcon(bundle: Bundle, step: StoryStep): string {
  if (step.kind === "contribution") return meaningOf(bundle, step.contribution_id!).icon;
  if (step.kind === "outcome") return bundle.account.outcome.scored ? "goal" : "nogoal";
  return "fork";
}

export function buildRibbon(root: HTMLElement, viewer: Viewer, state: UIState, onPick: (index: number) => void): RibbonHandle {
  const { bundle, story } = viewer;
  root.replaceChildren();
  root.setAttribute("aria-label", "causal chain");
  const head = bundle.account.headline_contribution_id;
  const shirts = new Map(bundle.teams.map((t) => [t.team_id, t.kit.shirt]));

  const track = el("div", "rr-ribbon-track");
  const fill = el("div", "rr-ribbon-fill");
  track.append(fill);
  const nodes = el("ol", "rr-ribbon-nodes");
  const items = bundle.story.map((step, i) => {
    const li = el("li", `rr-node rr-node-${step.kind}`);
    const b = el("button", "rr-node-btn");
    b.type = "button";
    b.dataset.index = String(i);
    const bar = el("span", "rr-node-bar");
    let teamId: string | null = null;
    let label: string;
    if (step.kind === "contribution") {
      const c = bundle.account.contributions.find((x) => x.contribution_id === step.contribution_id)!;
      const m = meaningOf(bundle, c.contribution_id);
      bar.style.height = `${Math.max(m.magnitude, 0.08) * 100}%`;
      bar.classList.add(m.positive ? "rr-pos" : "rr-neg");
      teamId = c.team_id;
      label = playerLabel(bundle, c.player_id).split(" ").at(-1) ?? "";
      if (c.contribution_id === head && step.kind === "contribution") li.classList.add("rr-headline");
      b.setAttribute("aria-label", `${i + 1}. ${playerLabel(bundle, c.player_id)}: ${m.gloss}`);
    } else {
      bar.classList.add("rr-none");
      label = step.kind === "outcome" ? (bundle.account.outcome.scored ? "Goal" : bundle.account.outcome.realized ? "No goal" : "Denied")
                                      : "Better option";
      b.setAttribute("aria-label", `${i + 1}. ${stepCaption(step, state.mode)}`);
    }
    const dot = el("span", "rr-node-dot");
    dot.innerHTML = icon(nodeIcon(bundle, step), 14);
    if (teamId) dot.style.setProperty("--team", shirts.get(teamId) ?? "#64748b");
    const name = el("span", "rr-node-label", label);
    b.append(el("span", "rr-node-barbox", undefined), dot, name);
    b.firstElementChild!.append(bar);
    b.addEventListener("click", () => onPick(i));
    li.append(b);
    nodes.append(li);
    return li;
  });
  // nodes sit in equal columns: the track runs from the first node's centre to the last one's
  nodes.style.gridTemplateColumns = `repeat(${items.length}, minmax(0, 1fr))`;
  track.style.left = track.style.right = `calc(100% / ${2 * Math.max(items.length, 1)})`;
  root.append(track, nodes);

  let lastIndex = Number.NaN;
  const sync = () => {
    const i = story.index;
    if (i !== lastIndex) {
      items.forEach((li, k) => {
        li.classList.toggle("rr-done", k < i);
        li.classList.toggle("rr-current", k === i);
      });
      lastIndex = i;
    }
    // the fill reaches the current node, then creeps towards the next one through the step's dwell
    const n = items.length;
    const at = i < 0 ? 0 : Math.min(i + (i < n - 1 ? story.within : 0), n - 1);
    fill.style.width = n > 1 ? `${((100 * at) / (n - 1)).toFixed(2)}%` : "0";
  };
  sync();
  return { sync };
}
