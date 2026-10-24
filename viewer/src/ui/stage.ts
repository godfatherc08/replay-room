// Overlays on the canvas: the title card (Story's ready state), the step card (one caption, its gloss and
// meter), the 2D/3D toggle, the camera tools, and a compact, collapsible legend.

import { momentHeader, outcomeView, stepView } from "../account";
import type { Viewer } from "../controller";
import { COLORS } from "../overlays";
import { button, el, icon, meter, radial } from "./dom";
import type { UIState } from "./state";

/** Camera tools the stage drives (PitchScene in the app, a fake in tests). */
export interface StageControls {
  set2D(on: boolean): void;
  resetView(): void;
  toggleAutoRotate(): boolean;
  screenshot(): void;
  frameSelection(): void;
}

export interface StageHandle {
  render(): void; // title card / step card for the current story state and mode
}

export function buildStage(root: HTMLElement, viewer: Viewer, state: UIState, controls: StageControls | undefined): StageHandle {
  const { bundle, story } = viewer;
  root.replaceChildren();

  const view = el("div", "rr-view-toggle");
  const v2 = button("rr-view-btn", "Top-down 2D view", "2D");
  const v3 = button("rr-view-btn rr-on", "3D view", "3D");
  for (const [b, flat] of [[v2, true], [v3, false]] as const) {
    b.addEventListener("click", () => {
      controls?.set2D(flat);
      v2.classList.toggle("rr-on", flat);
      v3.classList.toggle("rr-on", !flat);
    });
  }
  view.append(v2, v3);

  const tools = el("div", "rr-tools");
  const shot = button("rr-tool", "Save a screenshot", icon("camera", 16));
  shot.addEventListener("click", () => controls?.screenshot());
  const rotate = button("rr-tool", "Auto-rotate", icon("rotate", 16));
  rotate.addEventListener("click", () => rotate.classList.toggle("rr-on", controls?.toggleAutoRotate() ?? false));
  const zoom = button("rr-tool", "Frame the current step", icon("zoom", 16));
  zoom.addEventListener("click", () => controls?.frameSelection());
  tools.append(shot, rotate, zoom);

  const legend = el("div", "rr-legend");
  const legendToggle = button("rr-legend-toggle", "Show the legend", `${icon("layers", 14)}<span>Legend</span>`);
  legendToggle.setAttribute("aria-expanded", "false");
  const keys = el("div", "rr-legend-keys");
  keys.hidden = true;
  const key = (cls: string, color: string, label: string) => {
    const row = el("div");
    const k = el("span", `rr-key ${cls}`);
    k.style.setProperty("--c", color);
    row.append(k, el("span", undefined, label));
    return row;
  };
  keys.append(
    key("rr-key-ring", COLORS.highlight, "In focus"),
    key("rr-key-dash", COLORS.pass, "Pass / movement"),
    key("rr-key-solid", COLORS.shot, "Shot"),
    key("rr-key-zone", COLORS.zone, "Threat zone"),
    key("rr-key-solid", COLORS.chosen, "Option chosen"),
    key("rr-key-dash", COLORS.better, "Better option"),
  );
  legendToggle.addEventListener("click", () => {
    keys.hidden = !keys.hidden;
    legendToggle.setAttribute("aria-expanded", String(!keys.hidden));
  });
  legend.append(legendToggle, keys);

  const title = el("section", "rr-title-card");
  title.setAttribute("aria-label", "moment");
  const card = el("section", "rr-step-card");
  card.setAttribute("aria-live", "polite");
  root.append(view, tools, legend, title, card);

  const renderTitle = () => {
    const h = momentHeader(bundle, state.mode);
    const o = outcomeView(bundle, state.mode);
    const head = el("div", "rr-card-head");
    head.append(el("span", "rr-class-chip", h.classLabel), el("span", "rr-micro", h.clock));
    const value = el("div", "rr-outcome");
    const words = el("div", "rr-outcome-words");
    words.append(el("span", "rr-outcome-primary", o.primary));
    if (o.metric) words.append(el("span", "rr-metric", o.metric));
    value.append(radial(o.fraction, 40), words);
    const play = button("rr-cta", "Play the analysis", `${icon("play", 16)}<span>Play analysis</span>`);
    play.addEventListener("click", () => {
      state.setView("story");
      story.play();
    });
    const explore = button("rr-ghost", "Explore freely", "Explore freely");
    explore.addEventListener("click", () => state.setView("explore"));
    const actions = el("div", "rr-card-actions");
    actions.append(play, explore);
    title.replaceChildren(head, el("h1", "rr-display", o.result));
    if (h.description) title.append(el("p", "rr-lede", h.description));
    title.append(value, actions);
  };

  const renderStep = () => {
    const step = story.current;
    if (!step) return card.replaceChildren();
    const v = stepView(bundle, step, state.mode);
    const top = el("div", "rr-step-top");
    const counter = el("span", "rr-micro rr-counter", `Step ${v.index + 1} of ${v.total}`);
    const who = el("span", "rr-step-who");
    if (v.teamId) {
      const sw = el("span", "rr-swatch");
      sw.style.background = bundle.teams.find((t) => t.team_id === v.teamId)?.kit.shirt ?? "";
      who.append(sw);
    }
    who.append(el("span", undefined, v.title));
    top.append(who, counter);
    if (v.chip) top.insertBefore(el("span", `rr-headline-chip${v.headline ? "" : " rr-chip-support"}`, v.chip), counter);
    const caption = el("p", "rr-caption", v.caption);
    const meters = el("div", "rr-step-meters");
    for (const m of v.meters) {
      const row = el("div", "rr-meter-row");
      row.append(el("span", "rr-gloss", m.label), meter(m.fraction, m.tone));
      if (m.metric) row.append(el("span", "rr-metric", m.metric));
      meters.append(row);
    }
    card.dataset.kind = v.kind;
    card.replaceChildren(top, caption, meters);
  };

  const render = () => {
    const ready = state.view === "story" && story.state === "ready";
    title.hidden = !ready;
    card.hidden = state.view !== "story" || ready;
    if (ready) renderTitle();
    else if (!card.hidden) renderStep();
  };
  render();
  return { render };
}
