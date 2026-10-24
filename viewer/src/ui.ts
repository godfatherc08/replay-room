// The app shell around the canvas, composed from ui/*: top bar, stage overlays (title card, step card), the
// causal-chain ribbon under the pitch, the right panel, and the footer (transport + timeline).
//
// Story (the default) opens on a title card; "Play analysis" walks the account step by step. Explore is the
// free mode: scrub, orbit, click any fact. Analyst / Fan is orthogonal to both: it changes the register and
// whether raw metrics appear (Analyst: as small secondary text; Fan: never), never the facts.
//
// Every word and number shown is a field of the bundle (account, meaning, story, narration, match info);
// a slot the bundle has nothing for (no narration, no counterfactual) is left out, never filled in.
//
// Keys: Space plays / pauses (the story, or the replay in Explore) and never scrolls the page; Left / Right
// step between beats (Story) or facts (Explore). Typing in a field is left alone.

import type { IndexEntry } from "./bundle";
import type { View, Viewer } from "./controller";
import type { Mode } from "./overlays";
import { buildFooter } from "./ui/footer";
import { buildPanel } from "./ui/panel";
import { buildRibbon } from "./ui/ribbon";
import { buildStage, type StageControls } from "./ui/stage";
import { UIState } from "./ui/state";
import { buildTopbar } from "./ui/topbar";
import { proofOf } from "./account";
import { overlaysFor, stepOverlays } from "./overlays";
import type { EvidenceKey } from "./ui/state";

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
  keys?: EventTarget; // where keyboard shortcuts listen (default: window)
}

/** Keys the viewer owns: Space (play / pause), Left / Right (previous / next beat or fact). */
export function isTyping(target: EventTarget | null): boolean {
  if (!target || typeof (target as HTMLElement).tagName !== "string") return false;
  const t = target as HTMLElement;
  return t.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(t.tagName);
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

  /** Open (or close) a claim's proof: on the pitch (players ringed and named, the frame, the drawing) and in the
   *  panel (what was measured, who, which frame, which records). */
  const evidence = (key: EvidenceKey | null) => {
    if (!key) {
      viewer.conceal();
      state.setEvidence(null);
      return;
    }
    const step = "beat" in key ? viewer.bundle.story.find((s) => s.beat_id === key.beat) : undefined;
    const overlays = step ? stepOverlays(viewer.bundle, step, state.mode)
      : overlaysFor(viewer.bundle, (key as { contribution: string }).contribution, state.mode);
    viewer.reveal(proofOf(viewer.bundle, key), overlays);
    state.setEvidence(key);
  };

  const top = buildTopbar(roots.topbar, viewer.bundle, clock, state, opts.onPick);
  const stage = buildStage(roots.stage, viewer, state, opts.stage, evidence);
  const ribbon = buildRibbon(roots.ribbon, viewer, state, showStep);
  const panel = buildPanel(roots.side, viewer, state, jump, showStep, evidence);
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
    if (state.evidence && !viewer.proof) state.evidence = null; // the story moved on: the proof closed with it
    const key = `${story.index}|${story.state === "ready"}|${state.evidence ? 1 : 0}`;
    if (key === shown) return;
    shown = key;
    panel.render();
    stage.render();
    panel.mark();
  });

  const keys = opts.keys ?? (typeof window !== "undefined" ? window : null);
  const isSpace = (e: KeyboardEvent) => e.key === " " || e.code === "Space" || e.key === "Spacebar";
  keys?.addEventListener("keydown", (ev) => {
    const e = ev as KeyboardEvent;
    if (e.altKey || e.ctrlKey || e.metaKey || isTyping(e.target)) return;
    if (isSpace(e)) {
      e.preventDefault(); // the page must not scroll, and a focused button must not also fire
      if (e.repeat) return;
      if (state.view === "story") story.toggle();
      else clock.toggle();
    } else if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      const dir = e.key === "ArrowRight" ? 1 : -1;
      if (state.view === "story") {
        if (story.index < 0) story.goto(0);
        else if (dir > 0) story.next();
        else story.prev();
      } else {
        viewer.stepEvidence(dir);
        panel.mark();
      }
    }
  }, { capture: true });
  keys?.addEventListener("keyup", (ev) => {
    const e = ev as KeyboardEvent;
    if (isSpace(e) && !isTyping(e.target)) e.preventDefault(); // buttons activate on keyup
  }, { capture: true });

  const sync = () => {
    top.sync();
    ribbon.sync();
    footer.sync();
  };
  clock.onChange(sync);
  sync();
  return { state, sync };
}
