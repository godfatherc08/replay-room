// A cheap stadium around the pitch, so it no longer floats in a void: tiered stands on all four sides with a
// low-detail crowd texture, four floodlight towers, and a night-sky dome. Procedural boxes, one merged mesh
// per side, no assets. Purely decorative: nothing here reads the bundle beyond the pitch size and the kits.
// Off with ?stadium=0; the demo stands without it.

import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import { DynamicTexture } from "@babylonjs/core/Materials/Textures/dynamicTexture";
import { Color3 } from "@babylonjs/core/Maths/math.color";
import { Mesh } from "@babylonjs/core/Meshes/mesh";
import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder";
import type { Scene } from "@babylonjs/core/scene";

export const STAND = { gap: 11, tiers: 7, tierDepth: 2.4, tierRise: 1.25, overhang: 14 };
const TOWER_HEIGHT = 38;

/** A small seeded generator: the crowd looks the same on every load. */
function lcg(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
}

function crowdTexture(scene: Scene, colors: string[]): DynamicTexture {
  const w = 512;
  const h = 64;
  const tex = new DynamicTexture("crowd-tex", { width: w, height: h }, scene, true);
  const ctx = tex.getContext() as CanvasRenderingContext2D;
  ctx.fillStyle = "#121a26";
  ctx.fillRect(0, 0, w, h);
  const rnd = lcg(7);
  const palette = [...colors, "#d6c3a5", "#8d6e57", "#3b4656", "#cbd5e1", "#5b6676"];
  for (let y = 2; y < h; y += 5) {
    for (let x = (y / 5) % 2 ? 1 : 3; x < w; x += 4) {
      if (rnd() < 0.12) continue; // empty seats
      ctx.fillStyle = palette[Math.floor(rnd() * palette.length)];
      ctx.globalAlpha = 0.55 + 0.35 * rnd();
      ctx.fillRect(x, y, 2, 3);
    }
  }
  ctx.globalAlpha = 1;
  tex.update();
  return tex;
}

function skyTexture(scene: Scene): DynamicTexture {
  const tex = new DynamicTexture("sky-tex", { width: 4, height: 256 }, scene, false);
  const ctx = tex.getContext() as CanvasRenderingContext2D;
  const g = ctx.createLinearGradient(0, 0, 0, 256);
  g.addColorStop(0, "#02040a");
  g.addColorStop(0.55, "#0a1424");
  g.addColorStop(1, "#1b2a40");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 4, 256);
  tex.update();
  return tex;
}

export interface StadiumOptions {
  length: number;
  width: number;
  kitColors: string[]; // shirts in the crowd
  textures: boolean; // needs a 2D canvas (off in headless tests)
}

/** Builds the stadium and returns its meshes (all unpickable). */
export function buildStadium(scene: Scene, opts: StadiumOptions): Mesh[] {
  const { length: L, width: W } = opts;
  const meshes: Mesh[] = [];
  const seats = new StandardMaterial("stand-mat", scene);
  seats.specularColor = Color3.Black();
  seats.diffuseColor = Color3.FromHexString("#1a2333");
  if (opts.textures) {
    const crowd = crowdTexture(scene, opts.kitColors);
    seats.diffuseTexture = crowd;
    seats.emissiveTexture = crowd; // stays readable at night without extra lights
    seats.emissiveColor = new Color3(0.55, 0.55, 0.6);
  }
  const concrete = new StandardMaterial("stand-concrete", scene);
  concrete.diffuseColor = Color3.FromHexString("#0e141e");
  concrete.specularColor = Color3.Black();

  // four stands: along each touchline (x) and behind each goal (z), tiers stepping up and back
  const sides: { name: string; along: number; at: (k: number) => [number, number]; alongX: boolean }[] = [
    { name: "north", along: L + 2 * STAND.overhang, alongX: true,
      at: (k) => [0, W / 2 + STAND.gap + (k + 0.5) * STAND.tierDepth] },
    { name: "south", along: L + 2 * STAND.overhang, alongX: true,
      at: (k) => [0, -(W / 2 + STAND.gap + (k + 0.5) * STAND.tierDepth)] },
    { name: "east", along: W + 2 * STAND.gap, alongX: false,
      at: (k) => [L / 2 + STAND.gap + (k + 0.5) * STAND.tierDepth, 0] },
    { name: "west", along: W + 2 * STAND.gap, alongX: false,
      at: (k) => [-(L / 2 + STAND.gap + (k + 0.5) * STAND.tierDepth), 0] },
  ];
  for (const side of sides) {
    const tiers: Mesh[] = [];
    for (let k = 0; k < STAND.tiers; k++) {
      const height = STAND.tierRise * (k + 1);
      const box = MeshBuilder.CreateBox(`${side.name}-tier${k}`, {
        width: side.alongX ? side.along : STAND.tierDepth, depth: side.alongX ? STAND.tierDepth : side.along,
        height }, scene);
      const [x, z] = side.at(k);
      box.position.set(x, height / 2, z);
      tiers.push(box);
    }
    const stand = Mesh.MergeMeshes(tiers, true, true);
    if (stand) {
      stand.name = `stand-${side.name}`;
      stand.material = seats;
      stand.isPickable = false;
      meshes.push(stand);
    }
    const [bx, bz] = side.at(STAND.tiers);
    const back = MeshBuilder.CreateBox(`${side.name}-back`, {
      width: side.alongX ? side.along : 0.6, depth: side.alongX ? 0.6 : side.along,
      height: STAND.tierRise * (STAND.tiers + 2) }, scene);
    back.position.set(bx, (STAND.tierRise * (STAND.tiers + 2)) / 2, bz);
    back.material = concrete;
    back.isPickable = false;
    meshes.push(back);
  }

  // floodlight towers at the corners, lamp banks facing the pitch
  const lamp = new StandardMaterial("lamp-mat", scene);
  lamp.emissiveColor = Color3.FromHexString("#fff7e0");
  lamp.disableLighting = true;
  const reach = STAND.gap + STAND.tiers * STAND.tierDepth + 3;
  for (const [sx, sz] of [[1, 1], [1, -1], [-1, 1], [-1, -1]] as const) {
    const x = sx * (L / 2 + reach * 0.6);
    const z = sz * (W / 2 + reach);
    const pole = MeshBuilder.CreateCylinder(`tower${sx}${sz}`, { diameter: 0.9, height: TOWER_HEIGHT, tessellation: 8 }, scene);
    pole.position.set(x, TOWER_HEIGHT / 2, z);
    pole.material = concrete;
    pole.isPickable = false;
    const bank = MeshBuilder.CreateBox(`lamps${sx}${sz}`, { width: 6, height: 3, depth: 0.5 }, scene);
    bank.position.set(x, TOWER_HEIGHT + 1, z);
    bank.lookAt(bank.position.scale(-1)); // towards the centre spot
    bank.material = lamp;
    bank.isPickable = false;
    meshes.push(pole, bank);
  }

  // night sky
  const sky = MeshBuilder.CreateSphere("sky", { diameter: 900, segments: 16, sideOrientation: Mesh.BACKSIDE }, scene);
  const skyMat = new StandardMaterial("sky-mat", scene);
  skyMat.disableLighting = true;
  skyMat.backFaceCulling = false;
  if (opts.textures) skyMat.emissiveTexture = skyTexture(scene);
  else skyMat.emissiveColor = Color3.FromHexString("#0a1424");
  sky.material = skyMat;
  sky.isPickable = false;
  sky.infiniteDistance = true;
  meshes.push(sky);
  return meshes;
}
