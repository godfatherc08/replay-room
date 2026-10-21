// Entry point: load the index and a bundle (?moment=<id>, default: the first prevented moment), then play.

import { Engine } from "@babylonjs/core/Engines/engine";

import { type IndexEntry, loadBundle } from "./bundle";
import { Viewer } from "./controller";
import { PitchScene } from "./scene";
import { buildUI } from "./ui";

async function start(): Promise<void> {
  const canvas = document.getElementById("pitch") as HTMLCanvasElement;
  const side = document.getElementById("side") as HTMLElement;
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
  buildUI(side, viewer, {
    moments,
    current: bundle.account.moment.moment_id,
    onPick: (id) => {
      params.set("moment", id);
      params.delete("bundle");
      location.search = params.toString();
    },
  });
  const jumpTo = params.get("jump");
  if (jumpTo) viewer.jump(jumpTo);
  engine.runRenderLoop(() => {
    viewer.frame(engine.getDeltaTime() / 1000);
    scene.render();
  });
  window.addEventListener("resize", () => engine.resize());
  (window as unknown as { replayRoom: unknown }).replayRoom = { viewer, scene, bundle };
}

start().catch((err: unknown) => {
  const side = document.getElementById("side");
  if (side) side.textContent = `Could not start the viewer: ${String(err)}`;
  console.error(err);
});
