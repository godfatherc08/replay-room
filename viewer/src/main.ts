// Entry point: load the index and a bundle (?moment=<id>; default: the first prevented moment), build the shell,
// and open Story Mode on its title card, the camera framed on the whole move.
//
// URL parameters: ?mode=fan, ?view=explore, ?jump=<contribution> (Explore, at that fact),
// ?step=<n> (Story, paused at step n, 1-based), ?play=1 (start the analysis), ?stadium=0 (the bare pitch).

import { Engine } from "@babylonjs/core/Engines/engine";
import { CreateScreenshot } from "@babylonjs/core/Misc/screenshotTools";

import { type IndexEntry, loadBundle } from "./bundle";
import { Viewer } from "./controller";
import type { Vec2 } from "./overlays";
import { PitchScene } from "./scene";
import { buildUI } from "./ui";

const MAX_DPR = 2; // sharper than this costs frame rate for little gain

function byId(id: string): HTMLElement {
  const e = document.getElementById(id);
  if (!e) throw new Error(`missing #${id}`);
  return e;
}

async function start(): Promise<void> {
  const canvas = byId("pitch") as HTMLCanvasElement;
  const side = byId("side");
  const params = new URLSearchParams(location.search);
  let moments: IndexEntry[] = [];
  try {
    const res = await fetch("./index.json");
    if (res.ok) moments = (await res.json()) as IndexEntry[];
  } catch {
    // no index: a single bundle can still be opened with ?bundle=<path>
  }
  const wanted = params.get("moment");
  const entry = moments.find((m) => m.moment_id === wanted) ?? moments.find((m) => !m.realized) ?? moments[0];
  const url = params.get("bundle") ?? (entry ? `./${entry.bundle}` : null);
  if (!url) {
    side.textContent = "No bundles found. Run: python -m replay_room.render data/fixtures/synthetic_match_02";
    return;
  }
  const bundle = await loadBundle(url);
  const engine = new Engine(canvas, true, { preserveDrawingBuffer: true, stencil: true, antialias: true });
  engine.setHardwareScalingLevel(1 / Math.min(window.devicePixelRatio || 1, MAX_DPR));
  const scene = new PitchScene(engine, bundle, { labels: true, stadium: params.get("stadium") !== "0" });
  scene.camera.attachControl(canvas, true);
  const viewer = new Viewer(bundle, scene);
  const open = (id: string) => {
    params.set("moment", id);
    for (const k of ["bundle", "jump", "step", "play"]) params.delete(k);
    location.search = params.toString();
  };
  // the whole move: every action of the chain, start and end
  const move: Vec2[] = bundle.events.flatMap((e) => [e.start, e.end]);
  const overview = () => scene.focus(move, 1.5);
  const ui = buildUI(
    { topbar: byId("topbar"), stage: byId("stage-ui"), ribbon: byId("ribbon"), side, footer: byId("footer") },
    viewer,
    {
      moments,
      onPick: open,
      mode: params.get("mode") === "fan" ? "fan" : "analyst",
      view: params.get("view") === "explore" || params.has("jump") ? "explore" : "story",
      stage: {
        set2D: (on) => scene.set2D(on),
        resetView: () => scene.resetView(),
        toggleAutoRotate: () => scene.toggleAutoRotate(),
        screenshot: () => CreateScreenshot(engine, scene.camera, { precision: 1 }),
        frameSelection: () => {
          const step = viewer.story.current;
          if (viewer.view === "story" && step) viewer.showStep(step);
          else if (viewer.active) viewer.jump(viewer.active);
          else overview();
        },
      },
    },
  );
  overview();
  const jump = params.get("jump");
  const step = Number(params.get("step"));
  if (jump) viewer.jump(jump);
  else if (step >= 1) viewer.story.goto(step - 1);
  if (params.get("play") === "1") viewer.story.play();
  engine.runRenderLoop(() => {
    viewer.frame(Math.min(engine.getDeltaTime() / 1000, 0.1));
    ui.sync();
    scene.render();
  });
  // the renderer follows the canvas's own box (layout changes, the panel drawer, window resizes), so the backing
  // buffer always matches the CSS size and the camera's aspect is the canvas's
  // and the backing store is scaled by the device pixel ratio (clamped at 2 for the frame rate), re-read on the same
  // path so moving the window to another screen stays sharp
  const fit = () => {
    engine.setHardwareScalingLevel(1 / Math.min(window.devicePixelRatio || 1, MAX_DPR));
    engine.resize();
  };
  new ResizeObserver(fit).observe(byId("stage"));
  window.addEventListener("resize", fit);
  (window as unknown as { replayRoom: unknown }).replayRoom = { viewer, scene, bundle, ui };
}

start().catch((err: unknown) => {
  const side = document.getElementById("side");
  if (side) side.textContent = `Could not start the viewer: ${String(err)}`;
  console.error(err);
});
