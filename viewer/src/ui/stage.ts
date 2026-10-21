// Overlays on the canvas: 2D/3D toggle, compass (reset view), camera toolbar, and the legend.

import { COLORS } from "../overlays";
import { button, el, icon } from "./dom";

/** Camera tools the stage drives (PitchScene in the app, a fake in tests). */
export interface StageControls {
  set2D(on: boolean): void;
  resetView(): void;
  toggleAutoRotate(): boolean;
  screenshot(): void;
  frameSelection(): void;
  heading(): number;
}

export interface StageHandle {
  legend: HTMLElement;
  sync(): void; // turn the compass with the camera
}

export function buildStage(root: HTMLElement, controls: StageControls | undefined): StageHandle {
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
  view.append(v2, el("span", "rr-sep", "/"), v3);

  const compass = button("rr-compass", "Reset view",
    `<span>N</span><svg class="rr-needle" viewBox="0 0 24 24" width="26" height="26" aria-hidden="true">`
    + `<path d="M12 3l4 9-4-2-4 2z" fill="#e6edf5"/><path d="M12 21l-4-9 4 2 4-2z" fill="#64748b"/></svg>`);
  compass.addEventListener("click", () => controls?.resetView());

  const tools = el("div", "rr-tools");
  const shot = button("rr-tool", "Save a screenshot", icon("camera"));
  shot.addEventListener("click", () => controls?.screenshot());
  const rotate = button("rr-tool", "Auto-rotate", icon("rotate"));
  rotate.addEventListener("click", () => rotate.classList.toggle("rr-on", controls?.toggleAutoRotate() ?? false));
  const zoom = button("rr-tool", "Frame the selected evidence", icon("zoom"));
  zoom.addEventListener("click", () => controls?.frameSelection());
  tools.append(shot, rotate, zoom);

  const legend = el("div", "rr-legend");
  const key = (cls: string, color: string, label: string) => {
    const row = el("div");
    const k = el("span", `rr-key ${cls}`);
    k.style.setProperty("--c", color);
    row.append(k, el("span", undefined, label));
    return row;
  };
  legend.append(
    key("rr-key-ring", COLORS.highlight, "Selected player"),
    key("rr-key-dash", COLORS.pass, "Pass / movement"),
    key("rr-key-solid", COLORS.shot, "Shot / goal attempt"),
    key("rr-key-zone", COLORS.zone, "Threat zone"),
    key("rr-key-dash", COLORS.better, "Better option"),
  );
  root.append(view, compass, tools, legend);

  const needle = compass.querySelector<SVGElement>(".rr-needle");
  return {
    legend,
    sync: () => {
      if (needle && controls) needle.style.transform = `rotate(${(-controls.heading() * 180) / Math.PI}deg)`;
    },
  };
}
