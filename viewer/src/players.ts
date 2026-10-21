// Player bodies: ONE shared mesh drawn as thin instances (one instance per player), tinted per instance.
//
// The body is Kenney's CC0 character (assets/kenney-character-male-a.glb), loaded once, its skeleton
// dropped and its bind pose baked into plain vertices, then scaled to PLAYER_HEIGHT. If it cannot be
// loaded (or there is no loader, e.g. headless tests) every player is a capsule instead: same
// instancing, same API, so the viewer never breaks.
//
// Each frame, each instance is translated to its player's observed position and turned to face its
// observed velocity. No per-player rig or animation: lean, and every pose is a real position.

import "@babylonjs/core/Meshes/thinInstanceMesh"; // thin-instance methods on Mesh
import type { Scene } from "@babylonjs/core/scene";
import { Color3 } from "@babylonjs/core/Maths/math.color";
import { Matrix, Quaternion, Vector3 } from "@babylonjs/core/Maths/math.vector";
import { Mesh } from "@babylonjs/core/Meshes/mesh";
import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder";
import { VertexBuffer } from "@babylonjs/core/Buffers/buffer";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";

export const PLAYER_HEIGHT = 2.6; // m: about 1.4x life size, so players read from a broadcast camera
const MIN_FACING_SPEED = 0.6; // m/s: slower than this, keep the last heading
const SKIN = "#c99a7a";

export interface BodyPart {
  mesh: Mesh;
  tinted: boolean; // takes the per-instance team colour (the head keeps a neutral colour)
}

export class PlayerBodies {
  readonly ids: string[];
  readonly kind: "model" | "capsule";
  readonly parts: BodyPart[];
  private readonly matrices: Float32Array;
  private readonly colors: Float32Array;
  private readonly base: Float32Array; // undimmed team colours
  private readonly heading: number[];

  constructor(ids: string[], colors: string[], parts: BodyPart[], kind: "model" | "capsule") {
    this.ids = ids;
    this.kind = kind;
    this.parts = parts;
    this.matrices = new Float32Array(16 * ids.length);
    this.colors = new Float32Array(4 * ids.length);
    this.base = new Float32Array(4 * ids.length);
    this.heading = ids.map(() => 0);
    colors.forEach((hex, i) => this.setColor(i, hex));
    for (let i = 0; i < ids.length; i++) Matrix.Scaling(0, 0, 0).copyToArray(this.matrices, 16 * i);
    for (const p of parts) {
      p.mesh.thinInstanceSetBuffer("matrix", this.matrices, 16, false);
      if (p.tinted) p.mesh.thinInstanceSetBuffer("color", this.colors, 4, false);
      p.mesh.isPickable = false;
      p.mesh.alwaysSelectAsActiveMesh = true; // instances span the whole pitch
    }
  }

  get instanceCount(): number {
    return this.parts[0].mesh.thinInstanceCount;
  }

  /** Place player i at world (x, z), facing its velocity; hidden when ``visible`` is false. */
  setPose(i: number, x: number, z: number, vx: number, vz: number, visible: boolean, dim = false): void {
    if (Math.hypot(vx, vz) >= MIN_FACING_SPEED) this.heading[i] = Math.atan2(vx, vz);
    const s = visible ? 1 : 0;
    Matrix.Compose(new Vector3(s, s, s), Quaternion.RotationYawPitchRoll(this.heading[i], 0, 0), new Vector3(x, 0, z))
      .copyToArray(this.matrices, 16 * i);
    const k = dim ? 0.4 : 1; // interpolated across a gap: drawn darker, never as if observed
    for (let j = 0; j < 3; j++) this.colors[4 * i + j] = this.base[4 * i + j] * k;
  }

  setColor(i: number, hex: string): void {
    const c = Color3.FromHexString(hex);
    this.base.set([c.r, c.g, c.b, 1], 4 * i);
    this.colors.set([c.r, c.g, c.b, 1], 4 * i);
  }

  flush(): void {
    for (const p of this.parts) {
      p.mesh.thinInstanceBufferUpdated("matrix");
      if (p.tinted) p.mesh.thinInstanceBufferUpdated("color");
    }
  }

  /** Capsule bodies: no asset needed. */
  static capsules(scene: Scene, ids: string[], colors: string[]): PlayerBodies {
    const mesh = MeshBuilder.CreateCapsule("player-capsule", { height: PLAYER_HEIGHT * 0.8, radius: 0.45 }, scene);
    mesh.bakeTransformIntoVertices(Matrix.Translation(0, PLAYER_HEIGHT * 0.4, 0));
    mesh.material = tintable(scene, "player-capsule-mat");
    return new PlayerBodies(ids, colors, [{ mesh, tinted: true }], "capsule");
  }

  /** The CC0 humanoid, falling back to capsules if it cannot be loaded. */
  static async load(scene: Scene, url: string, ids: string[], colors: string[]): Promise<PlayerBodies> {
    try {
      const parts = await loadHumanoid(scene, url);
      return new PlayerBodies(ids, colors, parts, "model");
    } catch (err) {
      console.warn("[replay-room] player model unavailable, using capsules:", err);
      return PlayerBodies.capsules(scene, ids, colors);
    }
  }
}

function tintable(scene: Scene, name: string, hex = "#ffffff"): StandardMaterial {
  const m = new StandardMaterial(name, scene);
  m.diffuseColor = Color3.FromHexString(hex);
  m.specularColor = new Color3(0.12, 0.12, 0.12);
  return m;
}

async function loadHumanoid(scene: Scene, url: string): Promise<BodyPart[]> {
  await import("@babylonjs/loaders/glTF/2.0"); // registers the glTF loader (browser only)
  const { ImportMeshAsync } = await import("@babylonjs/core/Loading/sceneLoader");
  const result = await ImportMeshAsync(url, scene);
  for (const g of result.animationGroups) g.dispose();
  const meshes = result.meshes.filter((m): m is Mesh => m instanceof Mesh && m.getTotalVertices() > 0);
  if (meshes.length === 0) throw new Error("the model has no geometry");
  for (const m of meshes) {
    m.skeleton = null; // bind pose, baked: one static body for every instance
    m.removeVerticesData(VertexBuffer.MatricesIndicesKind);
    m.removeVerticesData(VertexBuffer.MatricesWeightsKind);
    m.computeWorldMatrix(true);
    m.setParent(null);
    m.bakeCurrentTransformIntoVertices();
  }
  for (const s of result.skeletons) s.dispose();
  for (const m of result.meshes) if (!meshes.includes(m as Mesh)) m.dispose();

  let min = new Vector3(Infinity, Infinity, Infinity);
  let max = new Vector3(-Infinity, -Infinity, -Infinity);
  for (const m of meshes) {
    m.refreshBoundingInfo();
    const b = m.getBoundingInfo().boundingBox;
    min = Vector3.Minimize(min, b.minimumWorld);
    max = Vector3.Maximize(max, b.maximumWorld);
  }
  const k = PLAYER_HEIGHT / (max.y - min.y);
  const fit = Matrix.Translation(-(min.x + max.x) / 2, -min.y, -(min.z + max.z) / 2).multiply(Matrix.Scaling(k, k, k));
  return meshes.map((m) => {
    m.bakeTransformIntoVertices(fit);
    const head = /head/i.test(m.name);
    m.material = tintable(scene, `player-${m.name}-mat`, head ? SKIN : "#ffffff");
    m.hasVertexAlpha = false;
    return { mesh: m, tinted: !head };
  });
}

