// The right panel: the moment (class, outcome as a probability gauge), how the chance was built (every fact as
// gloss + meter, the raw metric only in Analyst), the decision (chosen vs better option) and the summary.
//
// In Story the stage's step card is the hero, so the chain starts collapsed here; in Explore it is open and
// is the way in. Every word and number is a field of the bundle; a slot it has nothing for is left out.

import { decisionView, evidenceRows, momentHeader, outcomeView, summary } from "../account";
import type { Viewer } from "../controller";
import { button, el, icon, meter, radial } from "./dom";
import type { UIState } from "./state";

export interface PanelHandle {
  render(): void; // rebuild for the current mode / view
  mark(): void; // reflect the active fact
}

export function buildPanel(root: HTMLElement, viewer: Viewer, state: UIState, onJump: (id: string) => void,
                           onStep: (index: number) => void): PanelHandle {
  const { bundle } = viewer;
  let open: boolean | null = null; // the chain list: null = follow the view
  let rows = new Map<string, HTMLElement>();

  const moment = (): HTMLElement => {
    const h = momentHeader(bundle, state.mode);
    const o = outcomeView(bundle, state.mode);
    const box = el("section", "rr-block rr-moment");
    const top = el("div", "rr-card-head");
    top.append(el("span", "rr-class-chip", h.classLabel), el("span", `rr-chip rr-${h.framing}`, h.framing.toUpperCase()),
               el("span", "rr-micro rr-push", h.clock));
    const value = el("div", "rr-outcome");
    const words = el("div", "rr-outcome-words");
    words.append(el("span", "rr-outcome-result", o.result), el("span", "rr-outcome-primary", o.primary));
    if (o.metric) words.append(el("span", "rr-metric", o.metric));
    value.append(radial(o.fraction, 44), words);
    box.append(top, value);
    if (h.description) box.append(el("p", "rr-lede", h.description));
    return box;
  };

  const chain = (): HTMLElement => {
    const all = evidenceRows(bundle);
    const box = el("section", "rr-block rr-chain");
    const expanded = open ?? state.view === "explore";
    const toggle = button("rr-section-toggle", expanded ? "Collapse the chain" : "Show every fact",
                          `<span class="rr-section-title">How the chance was built</span>${icon("chevron", 14)}`);
    toggle.setAttribute("aria-expanded", String(expanded));
    toggle.addEventListener("click", () => {
      open = !expanded;
      render();
    });
    box.append(toggle);
    rows = new Map();
    if (!expanded) return box;
    const list = el("ol", "rr-chain-list");
    for (const r of all) {
      const b = el("button", `rr-row${r.headline ? " rr-headline" : ""}`);
      b.type = "button";
      b.dataset.id = r.id;
      b.dataset.frame = String(r.frameId);
      const ic = el("span", "rr-row-icon");
      ic.innerHTML = icon(r.icon, 14);
      ic.style.setProperty("--team", bundle.teams.find((t) => t.team_id === r.teamId)?.kit.shirt ?? "#64748b");
      const main = el("span", "rr-row-main");
      main.append(el("span", "rr-row-who", r.player), el("span", "rr-row-gloss", r.gloss));
      const value = el("span", "rr-row-value");
      value.append(meter(r.magnitude, r.positive ? "pos" : "neg"));
      if (state.mode === "analyst") value.append(el("span", "rr-metric", r.metric));
      b.append(ic, main, value, el("span", "rr-micro rr-row-time", r.clock));
      b.addEventListener("click", () => onJump(r.id));
      rows.set(r.id, b);
      const li = el("li");
      li.append(b);
      list.append(li);
    }
    box.append(list);
    return box;
  };

  const decision = (): HTMLElement | null => {
    const cf = bundle.account.counterfactuals[0];
    if (!cf) return null;
    const v = decisionView(bundle, cf, state.mode);
    const box = el("section", "rr-block rr-decision");
    box.append(el("h2", "rr-section-title", "The decision"));
    for (const [opt, tone] of [[v.chosen, "chosen"], [v.better, "better"]] as const) {
      const row = el("div", "rr-meter-row");
      row.append(el("span", "rr-gloss", opt.label), meter(opt.fraction, tone));
      if (opt.metric) row.append(el("span", "rr-metric", opt.metric));
      box.append(row);
    }
    const at = bundle.story.findIndex((s) => s.kind === "counterfactual" && s.contribution_id === cf.contribution_id);
    if (at >= 0) {
      const show = button("rr-link", "Show the options on the pitch", `<span>Show on the pitch</span>${icon("chevron", 14)}`);
      show.addEventListener("click", () => onStep(at));
      box.append(show);
    }
    return box;
  };

  const story = (): HTMLElement | null => {
    const s = summary(bundle, state.mode);
    if (!s) return null;
    const box = el("details", "rr-block rr-summary");
    const sum = el("summary", "rr-section-title", "Summary");
    const list = el("ol", "rr-summary-list");
    for (const line of s.lines) list.append(el("li", undefined, line));
    box.append(sum, list, el("div", "rr-micro rr-source", s.source));
    return box;
  };

  function render(): void {
    root.dataset.mode = state.mode;
    root.replaceChildren(...[moment(), chain(), decision(), story()].filter((x): x is HTMLElement => x !== null));
    mark();
  }

  function mark(): void {
    for (const [id, b] of rows) b.classList.toggle("rr-active", id === viewer.active);
    rows.get(viewer.active ?? "")?.scrollIntoView?.({ block: "nearest" });
  }

  render();
  return { render, mark };
}
