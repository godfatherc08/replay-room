// Entry point: load the index and a bundle (?moment=<id>; default: the first prevented moment), build the
// shell, pre-select the headline (or ?jump=<contribution>), then load the player model and play.

import { Engine } from "@babylonjs/core/Engines/engine";
import { CreateScreenshot } from "@babylonjs/core/Misc/screenshotTools";

import { type IndexEntry, loadBundle } from "./bundle";
import { Viewer } from "./controller";
import { PitchScene } from "./scene";
import { buildUI } from "./ui";

const MODEL_URL = new URL("../assets/kenney-character-male-a.glb", import.meta.url).href;

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
    side.textContent = "No bundles found. Run: python -m replay_room.render data/fixtures/synthetic_match_01";
    return;
  }
  const bundle = await loadBundle(url);
  const engine = new Engine(canvas, true, { preserveDrawingBuffer: true, stencil: true });
  const scene = new PitchScene(engine, bundle, { labels: true });
  scene.camera.attachControl(canvas, true);
  const viewer = new Viewer(bundle, scene);
  const open = (id: string) => {
    params.set("moment", id);
    params.delete("bundle");
    params.delete("jump");
    location.search = params.toString();
  };
  const ui = buildUI(
    { topbar: byId("topbar"), rail: byId("rail"), stage: byId("stage-ui"), side, footer: byId("footer") },
    viewer,
    {
      moments,
      onPick: open,
      mode: params.get("mode") === "fan" ? "fan" : "analyst",
      stage: {
        set2D: (on) => scene.set2D(on),
        resetView: () => scene.resetView(),
        toggleAutoRotate: () => scene.toggleAutoRotate(),
        screenshot: () => CreateScreenshot(engine, scene.camera, { precision: 1 }),
        frameSelection: () => (viewer.active ? viewer.jump(viewer.active) : scene.resetView()),
        heading: () => scene.heading,
      },
    },
  );
  viewer.jump(params.get("jump") ?? bundle.account.headline_contribution_id);
  document.querySelector<HTMLButtonElement>(`.rr-evidence-row[data-id="${viewer.active}"]`)?.classList.add("rr-active");
  engine.runRenderLoop(() => {
    viewer.frame(engine.getDeltaTime() / 1000);
    ui.sync();
    scene.render();
  });
  window.addEventListener("resize", () => engine.resize());
  void scene.useModel(MODEL_URL).then(() => viewer.frame(0));
  (window as unknown as { replayRoom: unknown }).replayRoom = { viewer, scene, bundle };
}

start().catch((err: unknown) => {
  const side = document.getElementById("side");
  if (side) side.textContent = `Could not start the viewer: ${String(err)}`;
  console.error(err);
});
