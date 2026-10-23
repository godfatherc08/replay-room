// The app shell around the canvas, composed from ui/*: top bar, stage overlays (title card, step card), the
// causal-chain ribbon under the pitch, the right panel, and the footer (transport + timeline).
//
// Story (the default) opens on a title card; "Play analysis" walks the account step by step. Explore is the
// free mode: scrub, orbit, click any fact. Analyst / Fan is orthogonal to both: it changes the register and
// whether raw metrics appear (Analyst: as small secondary text; Fan: never), never the facts.
//
// Every word and number shown is a field of the bundle (account, meaning, story, narration, match info);
// a slot the bundle has nothing for (no narration, no counterfactual) is left out, never filled in.

import type { IndexEntry } from "./bundle";
import type { View, Viewer } from "./controller";
import type { Mode } from "./overlays";
import { buildFooter } from "./ui/footer";
import { buildPanel } from "./ui/panel";
import { buildRibbon } from "./ui/ribbon";
import { buildStage, type StageControls } from "./ui/stage";
import { UIState } from "./ui/state";
import { buildTopbar } from "./ui/topbar";

export type { Mode, StageControls, View };

export interface UIRoots {
  topbar: HTMLElement;
  stage: HTMLElement; // overlays on top of the canvas
  ribbon: HTMLElement;
  side: HTMLElement;
  footer: HTMLElement;
}

export interface UIOptions {
  moments?: IndexEntry[];
  onPick?: (momentId: string) => void;
  stage?: StageControls;
  mode?: Mode;
  view?: View;
}

export interface UIHandle {
  state: UIState;
  sync(): void; // refresh what depends on the playhead or the story's progress (call once per frame)
}

export function buildUI(roots: UIRoots, viewer: Viewer, opts: UIOptions = {}): UIHandle {
  const { clock, story } = viewer;
  const state = new UIState(opts.mode ?? "analyst", opts.view ?? "story");
  viewer.mode = state.mode;
  viewer.view = state.view;

  const jump = (id: string) => {
    if (state.view !== "explore") state.setView("explore");
    viewer.jump(id);
    panel.mark();
  };
  const showStep = (index: number) => {
    if (state.view !== "story") state.setView("story");
    story.goto(index);
  };

  const top = buildTopbar(roots.topbar, viewer.bundle, clock, state, opts.onPick);
  const stage = buildStage(roots.stage, viewer, state, opts.stage);
  const ribbon = buildRibbon(roots.ribbon, viewer, state, showStep);
  const panel = buildPanel(roots.side, viewer, state, jump, showStep);
  const footer = buildFooter(roots.footer, viewer, state, {
    onPick: opts.onPick,
    jump,
    afterJump: () => panel.mark(),
    scrub: () => {
      if (state.view !== "explore") state.setView("explore");
    },
  });

  let mode = state.mode;
  let view = state.view;
  state.onChange(() => {
    if (state.mode !== mode) {
      mode = state.mode;
      viewer.setMode(mode);
    }
    if (state.view !== view) {
      view = state.view;
      viewer.setView(view);
    }
    roots.stage.dataset.view = view;
    stage.render();
    panel.render();
  });
  roots.stage.dataset.view = view;

  let shown = "";
  story.onChange(() => {
    const key = `${story.index}|${story.state === "ready"}`;
    if (key === shown) return;
    shown = key;
    stage.render();
    panel.mark();
  });

  const sync = () => {
    top.sync();
    ribbon.sync();
    footer.sync();
  };
  clock.onChange(sync);
  sync();
  return { state, sync };
}
