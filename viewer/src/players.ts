// Player bodies: ONE shared figure drawn as thin instances (one instance per player), coloured per instance.
//
// The figure is built from smooth primitives (no downloaded asset): a near-white matte body (head, arms,
// legs), a team-coloured shirt (tapered torso + sleeves) and shorts. Three meshes share one matrix buffer;
// each has its own per-instance colour buffer, so the kit takes the team's colours, the goalkeeper wears
// their own, and any player can be dimmed while another is the focus. If the figure cannot be built every
// player is a capsule instead: same instancing, same API, so the viewer never breaks.
//
// Each frame, each instance is translated to its player's observed position and turned to face its
// observed velocity. No per-player rig or animation: lean, and every pose is a real position.

import "@babylonjs/core/Meshes/thinInstanceMesh"; // thin-instance methods on Mesh
import type { Scene } from "@babylonjs/core/scene";
import { Color3 } from "@babylonjs/core/Maths/math.color";
import { Matrix, Quaternion, Vector3 } from "@babylonjs/core/Maths/math.vector";
import { Mesh } from "@babylonjs/core/Meshes/mesh";
import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";

export const PLAYER_HEIGHT = 2.9; // m: about 1.6x life size, so players read from a broadcast camera
const MIN_FACING_SPEED = 0.6; // m/s: slower than this, keep the last heading
const BODY = "#eef1f5"; // near-white matte skin of the figure
const DIM = 0.38; // how far players who are not the focus fade towards grey: the kit's hue stays readable
export const TURN_RATE = 14; // 1/s: heading eases towards the direction of travel (time constant ~70 ms)
const GAP_DIM = 0.45; // brightness of a player interpolated across a tracking gap
const FADE = [0.3, 0.36, 0.4]; // the grey they fade to: muted, never a muddy darkened kit

export type Slot = "shirt" | "shorts" | "body";

export interface BodyPart {
  mesh: Mesh;
  slot: Slot; // which colour this part takes per instance
}

export interface PlayerKit {
  shirt: string;
  shorts: string;
}

export class PlayerBodies {
  readonly ids: string[];
  readonly kind: "figure" | "capsule";
  readonly parts: BodyPart[];
  private readonly matrices: Float32Array;
  private readonly base: Record<Slot, Float32Array>; // undimmed colours
  private readonly colors: Map<BodyPart, Float32Array>;
  private readonly heading: number[];
  private readonly placed: boolean[];
  turn = 1; // share of the remaining turn taken this update (set from the frame time by the scene) // drawn last update (a figure appearing faces its travel at once)
  private readonly dim: number[]; // 0 = full colour, DIM = faded

  constructor(ids: string[], kits: PlayerKit[], parts: BodyPart[], kind: "figure" | "capsule") {
    this.ids = ids;
    this.kind = kind;
    this.parts = parts;
    const n = ids.length;
    this.matrices = new Float32Array(16 * n);
    this.base = { shirt: new Float32Array(4 * n), shorts: new Float32Array(4 * n), body: new Float32Array(4 * n) };
    this.heading = ids.map(() => 0);
    this.placed = ids.map(() => false);
    this.dim = ids.map(() => 0);
    kits.forEach((k, i) => this.setKit(i, k));
    for (let i = 0; i < n; i++) Matrix.Scaling(0, 0, 0).copyToArray(this.matrices, 16 * i);
    this.colors = new Map(parts.map((p) => [p, new Float32Array(this.base[p.slot])]));
    for (const p of parts) {
      p.mesh.thinInstanceSetBuffer("matrix", this.matrices, 16, false);
      p.mesh.thinInstanceSetBuffer("color", this.colors.get(p)!, 4, false);
      p.mesh.isPickable = false;
      p.mesh.alwaysSelectAsActiveMesh = true; // instances span the whole pitch
    }
  }

  get instanceCount(): number {
    return this.parts[0].mesh.thinInstanceCount;
  }

  setKit(i: number, kit: PlayerKit): void {
    const put = (slot: Slot, hex: string) => {
      const c = Color3.FromHexString(hex);
      this.base[slot].set([c.r, c.g, c.b, 1], 4 * i);
    };
    put("shirt", kit.shirt);
    put("shorts", kit.shorts);
    put("body", BODY);
  }

  /** Dim every player except ``focus`` (an empty focus lights everyone). */
  setFocus(focus: Set<number>): void {
    for (let i = 0; i < this.ids.length; i++) this.dim[i] = focus.size === 0 || focus.has(i) ? 0 : DIM;
  }

  isDimmed(i: number): boolean {
    return this.dim[i] > 0;
  }

  /** Place player i at world (x, z), facing its velocity; hidden when ``visible`` is false. */
  setPose(i: number, x: number, z: number, vx: number, vz: number, visible: boolean, gap = false): void {
    if (Math.hypot(vx, vz) >= MIN_FACING_SPEED) { // face the direction of travel; standing still: hold it
      const target = Math.atan2(vx, vz);
      const turn = Math.atan2(Math.sin(target - this.heading[i]), Math.cos(target - this.heading[i]));
      this.heading[i] += visible && this.placed[i] ? turn * this.turn : turn;
    }
    this.placed[i] = visible;
    const s = visible ? 1 : 0;
    Matrix.Compose(new Vector3(s, s, s), Quaternion.RotationYawPitchRoll(this.heading[i], 0, 0), new Vector3(x, 0, z))
      .copyToArray(this.matrices, 16 * i);
    const k = gap ? GAP_DIM : 1; // interpolated across a gap: drawn darker, never as if observed
    const f = this.dim[i];
    for (const p of this.parts) {
      const out = this.colors.get(p)!;
      const base = this.base[p.slot];
      for (let j = 0; j < 3; j++) out[4 * i + j] = (base[4 * i + j] * (1 - f) + FADE[j] * f) * k;
    }
  }

  flush(): void {
    for (const p of this.parts) {
      p.mesh.thinInstanceBufferUpdated("matrix");
      p.mesh.thinInstanceBufferUpdated("color");
    }
  }

  /** The primitive figure (falls back to capsules if it cannot be built). */
  static create(scene: Scene, ids: string[], kits: PlayerKit[]): PlayerBodies {
    try {
      return new PlayerBodies(ids, kits, buildFigure(scene), "figure");
    } catch (err) {
      console.warn("[replay-room] player figure unavailable, using capsules:", err);
      return PlayerBodies.capsules(scene, ids, kits);
    }
  }

  /** Capsule bodies in the shirt colour: the fallback. */
  static capsules(scene: Scene, ids: string[], kits: PlayerKit[]): PlayerBodies {
    const mesh = MeshBuilder.CreateCapsule("player-capsule", { height: PLAYER_HEIGHT * 0.8, radius: 0.45 }, scene);
    mesh.bakeTransformIntoVertices(Matrix.Translation(0, PLAYER_HEIGHT * 0.4, 0));
    mesh.material = matte(scene, "player-capsule-mat");
    return new PlayerBodies(ids, kits, [{ mesh, slot: "shirt" }], "capsule");
  }
}

function matte(scene: Scene, name: string): StandardMaterial {
  const m = new StandardMaterial(name, scene);
  m.diffuseColor = Color3.White(); // the per-instance colour does the tinting
  m.specularColor = new Color3(0.08, 0.08, 0.08);
  m.specularPower = 24;
  return m;
}

/** Bake a primitive into place: scale, then rotate about z, then move. */
function place(m: Mesh, at: [number, number, number], opts: { scale?: [number, number, number]; tilt?: number } = {}): Mesh {
  const [sx, sy, sz] = opts.scale ?? [1, 1, 1];
  m.bakeTransformIntoVertices(Matrix.Scaling(sx, sy, sz)
    .multiply(Matrix.RotationZ(opts.tilt ?? 0))
    .multiply(Matrix.Translation(...at)));
  return m;
}

/** A stylized footballer, ~PLAYER_HEIGHT tall, facing +z, feet at y = 0. */
function buildFigure(scene: Scene): BodyPart[] {
  const H = PLAYER_HEIGHT;
  const u = H / 2.6; // the proportions below are in a 2.6-unit figure
  const cap = (name: string, height: number, radius: number, radiusTop?: number) =>
    MeshBuilder.CreateCapsule(name, { height: height * u, radius: radius * u, radiusTop: (radiusTop ?? radius) * u,
                                      tessellation: 18, subdivisions: 2, capSubdivisions: 6 }, scene);
  const merge = (name: string, meshes: Mesh[], slot: Slot): BodyPart => {
    const mesh = Mesh.MergeMeshes(meshes, true, true);
    if (!mesh) throw new Error(`could not merge ${name}`);
    mesh.name = name;
    mesh.material = matte(scene, `${name}-mat`);
    return { mesh, slot };
  };

  const head = place(MeshBuilder.CreateSphere("head", { diameter: 0.38 * u, segments: 20 }, scene), [0, 2.38 * u, 0],
                     { scale: [0.9, 1.05, 0.96] });
  const neck = place(MeshBuilder.CreateCylinder("neck", { diameter: 0.16 * u, height: 0.18 * u, tessellation: 12 }, scene),
                     [0, 2.16 * u, 0]);
  const arms = [-1, 1].map((s) => place(cap(`arm${s}`, 0.8, 0.072, 0.08), [s * 0.47 * u, 1.6 * u, 0], { tilt: s * 0.12 }));
  const legs = [-1, 1].map((s) => place(cap(`leg${s}`, 1.12, 0.088, 0.11), [s * 0.17 * u, 0.56 * u, 0]));
  const boots = [-1, 1].map((s) => place(cap(`boot${s}`, 0.3, 0.07), [s * 0.17 * u, 0.07 * u, 0.06 * u],
                                         { scale: [1.1, 1, 1] }));
  const torso = place(cap("torso", 0.94, 0.25, 0.36), [0, 1.66 * u, 0], { scale: [1, 1, 0.62] });
  const shoulders = place(cap("shoulders", 0.86, 0.13), [0, 2.0 * u, 0], { tilt: Math.PI / 2, scale: [1, 1, 0.9] });
  const sleeves = [-1, 1].map((s) => place(cap(`sleeve${s}`, 0.36, 0.105), [s * 0.45 * u, 1.9 * u, 0], { tilt: s * 0.14 }));
  const shorts = place(MeshBuilder.CreateCylinder("shorts", { diameterTop: 0.56 * u, diameterBottom: 0.66 * u, height: 0.36 * u,
                                                              tessellation: 24 }, scene),
                       [0, 1.16 * u, 0], { scale: [1, 1, 0.7] });
  return [
    merge("player-body", [head, neck, ...arms, ...legs, ...boots], "body"),
    merge("player-shirt", [torso, shoulders, ...sleeves], "shirt"),
    merge("player-shorts", [shorts], "shorts"),
  ];
}
