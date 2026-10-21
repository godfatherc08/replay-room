// The app shell around the canvas, composed from ui/*: top bar, left rail, stage overlays, the right
// panel (Event / Tactics / Metrics / Players), and the footer (transport + timeline).
//
// Every word and number shown is a field of the bundle (account, display rows, narration, match info);
// a slot the bundle has nothing for (no narration, no counterfactual) is left out, never filled in.
// Fan mode is the seam for Build 7: today it shows the moment header and the summary only.

import { scoreAt } from "./account";
import type { IndexEntry } from "./bundle";
import type { Viewer } from "./controller";
import { el } from "./ui/dom";
import { buildEvent, type Store } from "./ui/event";
import { buildFooter } from "./ui/footer";
import { buildRail } from "./ui/rail";
import { buildStage, type StageControls } from "./ui/stage";
import { type Mode, type Tab, UIState } from "./ui/state";
import { buildMetrics, buildMoments, buildPlayers, buildTactics } from "./ui/tabs";
import { buildTopbar } from "./ui/topbar";

export type { Mode, Tab, StageControls };

export interface UIRoots {
  topbar: HTMLElement;
  rail: HTMLElement;
  stage: HTMLElement; // overlays on top of the canvas
  side: HTMLElement;
  footer: HTMLElement;
}

export interface UIOptions {
  moments?: IndexEntry[];
  onPick?: (momentId: string) => void;
  stage?: StageControls;
  storage?: Store;
  mode?: Mode;
}

export interface UIHandle {
  state: UIState;
  sync(): void; // refresh what depends on the playhead or the camera (call once per frame)
}

export function buildUI(roots: UIRoots, viewer: Viewer, opts: UIOptions = {}): UIHandle {
  const { bundle, clock } = viewer;
  const state = new UIState(opts.mode ?? "analyst");
  const storage = opts.storage === undefined ? safeStorage() : opts.storage;

  const top = buildTopbar(roots.topbar, bundle, clock, state);
  const stage = buildStage(roots.stage, opts.stage);
  top.legendToggle.addEventListener("change", () => (stage.legend.hidden = !top.legendToggle.checked));

  const event = buildEvent(viewer, storage);
  const fanNote = el("p", "rr-fan-note",
    "Fan view arrives with personalization (Build 7). Switch to Analyst for the full evidence.");
  let showingMoments = false;

  roots.side.replaceChildren();
  const tabs = el("div", "rr-tabs");
  tabs.setAttribute("role", "tablist");
  const tabButtons = (["event", "tactics", "metrics", "players"] as Tab[]).map((t) => {
    const b = el("button", "rr-tab", t[0].toUpperCase() + t.slice(1));
    b.type = "button";
    b.dataset.tab = t;
    b.setAttribute("role", "tab");
    b.addEventListener("click", () => {
      showingMoments = false;
      state.setTab(t);
    });
    tabs.append(b);
    return b;
  });
  const body = el("div", "rr-side-body");
  roots.side.append(tabs, body);

  const afterJump = () => event.markActive();
  const render = () => {
    roots.side.dataset.mode = state.mode;
    tabs.hidden = state.mode === "fan";
    for (const b of tabButtons) b.classList.toggle("rr-on", b.dataset.tab === state.tab && !showingMoments);
    const parts: HTMLElement[] = [];
    if (state.mode === "fan") {
      parts.push(event.header);
      if (event.summary) parts.push(event.summary);
      parts.push(fanNote);
    } else if (showingMoments) {
      parts.push(buildMoments(viewer, opts.onPick));
    } else if (state.tab === "event") {
      parts.push(event.header, event.evidence);
      if (event.summary) parts.push(event.summary);
    } else if (state.tab === "tactics") {
      parts.push(buildTactics(viewer, afterJump));
    } else if (state.tab === "metrics") {
      parts.push(buildMetrics(viewer));
    } else {
      parts.push(buildPlayers(viewer, afterJump));
    }
    body.replaceChildren(...parts);
  };
  state.onChange(render);

  buildRail(roots.rail, state, {
    showMoments: () => {
      showingMoments = true;
      render();
    },
    showEvidence: () => event.evidence.scrollIntoView?.({ block: "start" }),
  });
  const footer = buildFooter(roots.footer, viewer, opts.onPick);
  footer.onJump(afterJump);
  render();
  event.markActive();

  const sync = () => {
    const s = scoreAt(bundle, clock.time);
    event.setScore(`${s.home} - ${s.away}`);
    top.sync();
    stage.sync();
  };
  clock.onChange(sync);
  sync();
  return { state, sync };
}

function safeStorage(): Store {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null; // private mode or blocked storage: the first-run hint just shows every time
  }
}
