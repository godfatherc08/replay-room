// The 3D scene: a dark striped pitch to scale with goal frames, instanced humanoid players, the ball,
// overlays, and an orbit camera with broadcast-style tools (2D/3D, heading, auto-rotate, fit, screenshot).
//
// Pitch metres (x along the touchline, y across, origin bottom-left) map to world coordinates
// (x - L/2, height, y - W/2), so the pitch is centred on the origin.

import { ArcRotateCamera } from "@babylonjs/core/Cameras/arcRotateCamera";
import type { AbstractEngine } from "@babylonjs/core/Engines/abstractEngine";
import { DirectionalLight } from "@babylonjs/core/Lights/directionalLight";
import { HemisphericLight } from "@babylonjs/core/Lights/hemisphericLight";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import { DynamicTexture } from "@babylonjs/core/Materials/Textures/dynamicTexture";
import { Color3, Color4 } from "@babylonjs/core/Maths/math.color";
import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import { Mesh } from "@babylonjs/core/Meshes/mesh";
import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder";
import { TransformNode } from "@babylonjs/core/Meshes/transformNode";
import { Scene } from "@babylonjs/core/scene";

import type { Bundle } from "./bundle";
import type { Sample } from "./motion";
import { COLORS, type Overlay, teamColor, type Vec2 } from "./overlays";
import { PLAYER_HEIGHT, PlayerBodies } from "./players";

export interface SceneOptions {
  labels: boolean; // text needs a 2D canvas (off in headless tests)
}

interface Marker {
  root: TransformNode; // follows the player: number plate and selection ring
  ring: Mesh | null;
  index: number; // instance index in PlayerBodies (-1 for the ball)
}

const VIEW_3D = { alpha: -Math.PI / 2, beta: 0.95, radius: 92 };
const VIEW_2D_BETA = 0.0001;

export class PitchScene {
  readonly scene: Scene;
  readonly camera: ArcRotateCamera;
  readonly markers = new Map<string, Marker>();
  bodies: PlayerBodies;
  ball: Mesh;
  highlighted: string[] = [];
  overlayMeshes: Mesh[] = [];
  is2D = false;
  private readonly half: Vec2;
  private readonly materials = new Map<string, StandardMaterial>();
  private readonly playerIds: string[];
  private desiredTarget: Vector3 | null = null;
  private desiredRadius: number | null = null;

  constructor(engine: AbstractEngine, private readonly bundle: Bundle, private readonly opts: SceneOptions) {
    this.half = [bundle.pitch.length / 2, bundle.pitch.width / 2];
    this.scene = new Scene(engine);
    this.scene.clearColor = new Color4(0.035, 0.05, 0.075, 1);
    this.camera = new ArcRotateCamera("camera", VIEW_3D.alpha, VIEW_3D.beta, VIEW_3D.radius, Vector3.Zero(), this.scene);
    this.camera.lowerRadiusLimit = 8;
    this.camera.upperRadiusLimit = 170;
    this.camera.upperBetaLimit = Math.PI / 2 - 0.05;
    this.camera.wheelDeltaPercentage = 0.02;
    const hemi = new HemisphericLight("sky", new Vector3(0.1, 1, -0.2), this.scene);
    hemi.intensity = 0.75;
    hemi.groundColor = new Color3(0.12, 0.16, 0.14);
    const sun = new DirectionalLight("sun", new Vector3(-0.4, -1, 0.5), this.scene);
    sun.intensity = 0.55;
    this.buildPitch();
    this.playerIds = bundle.objects.filter((o) => o.kind === "player").map((o) => o.id);
    this.bodies = PlayerBodies.capsules(this.scene, this.playerIds, this.playerIds.map((id) => this.shirt(id)));
    this.ball = MeshBuilder.CreateSphere("ball", { diameter: 0.8, segments: 16 }, this.scene);
    this.ball.material = this.material("#ffffff", 1, true);
    this.buildMarkers();
  }

  /** Swap the capsules for the humanoid model (falls back to capsules on any failure). */
  async useModel(url: string): Promise<void> {
    const bodies = await PlayerBodies.load(this.scene, url, this.playerIds, this.playerIds.map((id) => this.shirt(id)));
    if (bodies.kind === "capsule") {
      for (const p of bodies.parts) p.mesh.dispose();
      return;
    }
    for (const p of this.bodies.parts) p.mesh.dispose();
    this.bodies = bodies;
  }

  shirt(id: string): string {
    if (this.bundle.goalkeepers.includes(id)) return COLORS.keeper;
    const o = this.bundle.objects.find((x) => x.id === id);
    return teamColor(this.bundle, o?.team_id ?? "");
  }

  world([x, y]: Vec2, height = 0): Vector3 {
    return new Vector3(x - this.half[0], height, y - this.half[1]);
  }

  private material(color: string, alpha = 1, emissive = false): StandardMaterial {
    const key = `${color}|${alpha}|${emissive}`;
    let m = this.materials.get(key);
    if (!m) {
      m = new StandardMaterial(`m${this.materials.size}`, this.scene);
      const c = Color3.FromHexString(color);
      m.diffuseColor = c;
      m.specularColor = Color3.Black();
      if (emissive) {
        m.emissiveColor = c;
        m.disableLighting = true;
      }
      m.alpha = alpha;
      this.materials.set(key, m);
    }
    return m;
  }

  private buildPitch(): void {
    const { length: L, width: W } = this.bundle.pitch;
    const apron = MeshBuilder.CreateGround("apron", { width: L + 16, height: W + 14 }, this.scene);
    apron.position.y = -0.02;
    apron.material = this.material("#123a24");
    const stripes = 18;
    const parts: Mesh[] = [];
    for (let k = 0; k < stripes; k++) {
      const s = MeshBuilder.CreateGround(`stripe${k}`, { width: L / stripes, height: W }, this.scene);
      s.position.x = -L / 2 + (k + 0.5) * (L / stripes);
      s.material = this.material(k % 2 ? "#1b5a34" : "#1f6538");
      parts.push(s);
    }
    const pitch = Mesh.MergeMeshes(parts, true, false, undefined, false, true);
    if (pitch) pitch.isPickable = false;
    const white = Color3.FromHexString("#dfeee4");
    const line = (pts: Vec2[], name: string) => {
      const l = MeshBuilder.CreateLines(name, { points: pts.map((p) => this.world(p, 0.03)) }, this.scene);
      l.color = white;
      l.alpha = 0.85;
      l.isPickable = false;
    };
    const rect = (x0: number, y0: number, x1: number, y1: number, name: string) =>
      line([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]], name);
    rect(0, 0, L, W, "touchlines");
    line([[L / 2, 0], [L / 2, W]], "halfway");
    const arc = (cx: number, cy: number, r: number, a0: number, a1: number, name: string) => {
      const pts: Vec2[] = [];
      for (let k = 0; k <= 48; k++) {
        const a = a0 + ((a1 - a0) * k) / 48;
        pts.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]);
      }
      line(pts, name);
    };
    arc(L / 2, W / 2, 9.15, 0, 2 * Math.PI, "centre-circle");
    for (const [x0, dir] of [[0, 1], [L, -1]] as const) {
      rect(x0, W / 2 - 20.16, x0 + dir * 16.5, W / 2 + 20.16, `box${x0}`);
      rect(x0, W / 2 - 9.16, x0 + dir * 5.5, W / 2 + 9.16, `six${x0}`);
      const half = Math.acos(5.5 / 9.15);
      arc(x0 + dir * 11, W / 2, 9.15, dir > 0 ? -half : Math.PI - half, dir > 0 ? half : Math.PI + half, `d${x0}`);
      this.buildGoal(x0, dir);
    }
  }

  private buildGoal(x0: number, dir: number): void {
    const W = this.bundle.pitch.width;
    const frame = this.material("#f1f5f9");
    const post = (y: number) => {
      const p = MeshBuilder.CreateCylinder(`post${x0}${y}`, { diameter: 0.15, height: 2.44, tessellation: 10 }, this.scene);
      p.position = this.world([x0, y], 1.22);
      p.material = frame;
    };
    post(W / 2 - 3.66);
    post(W / 2 + 3.66);
    const bar = MeshBuilder.CreateCylinder(`bar${x0}`, { diameter: 0.15, height: 7.32, tessellation: 10 }, this.scene);
    bar.rotation.x = Math.PI / 2;
    bar.position = this.world([x0, W / 2], 2.44);
    bar.material = frame;
    const net: Vector3[][] = [];
    const back = x0 - dir * 2;
    for (let k = 0; k <= 8; k++) {
      const y = W / 2 - 3.66 + (7.32 * k) / 8;
      net.push([this.world([x0, y], 2.44), this.world([back, y], 1.6), this.world([back, y], 0)]);
    }
    const lines = MeshBuilder.CreateLineSystem(`net${x0}`, { lines: net }, this.scene);
    lines.color = Color3.FromHexString("#cbd5e1");
    lines.alpha = 0.5;
  }

  private buildMarkers(): void {
    const numbers = new Map<string, number>();
    for (const t of this.bundle.teams) for (const p of t.players) numbers.set(p.player_id, p.shirt_number);
    for (const o of this.bundle.objects) {
      const root = new TransformNode(`obj-${o.id}`, this.scene);
      let ring: Mesh | null = null;
      if (o.kind === "player") {
        ring = MeshBuilder.CreateTorus(`ring-${o.id}`, { diameter: 2.4, thickness: 0.18, tessellation: 40 }, this.scene);
        ring.position.y = 0.06;
        ring.material = this.material(COLORS.highlight, 1, true);
        ring.parent = root;
        ring.isVisible = false;
        if (this.opts.labels) {
          const plate = this.textPlane(`n-${o.id}`, String(numbers.get(o.id) ?? o.id), this.shirt(o.id), 1.1, 0.88);
          plate.position.y = PLAYER_HEIGHT + 0.9;
          plate.parent = root;
        }
      }
      root.setEnabled(false);
      this.markers.set(o.id, { root, ring, index: o.kind === "player" ? this.playerIds.indexOf(o.id) : -1 });
    }
  }

  private textPlane(name: string, text: string, accent: string, height: number, bgAlpha = 0.78): Mesh {
    const h = 64;
    const w = Math.max(64, Math.ceil(text.length * 26 + 28));
    const tex = new DynamicTexture(`${name}-tex`, { width: w, height: h }, this.scene, false);
    tex.hasAlpha = true;
    const ctx = tex.getContext();
    ctx.fillStyle = `rgba(10,16,24,${bgAlpha})`;
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = accent;
    ctx.fillRect(0, h - 6, w, 6);
    tex.drawText(text, null, 42, "600 34px Inter, system-ui, sans-serif", "#f8fafc", null, true);
    const mat = new StandardMaterial(`${name}-mat`, this.scene);
    mat.diffuseTexture = tex;
    mat.useAlphaFromDiffuseTexture = true;
    mat.emissiveColor = Color3.White();
    mat.disableLighting = true;
    mat.backFaceCulling = false;
    const plane = MeshBuilder.CreatePlane(name, { width: (height * w) / h, height }, this.scene);
    plane.material = mat;
    plane.billboardMode = TransformNode.BILLBOARDMODE_ALL;
    plane.isPickable = false;
    return plane;
  }

  /** Move every player instance and the ball to its sample; hide what has no sample; dim what crosses a gap. */
  update(samples: Map<string, Sample | null>): void {
    for (const [id, m] of this.markers) {
      const s = samples.get(id) ?? null;
      m.root.setEnabled(s !== null);
      if (m.index < 0) {
        this.ball.setEnabled(s !== null);
        if (s) this.ball.position.copyFrom(this.world([s.x, s.y], 0.4));
        continue;
      }
      if (!s) {
        this.bodies.setPose(m.index, 0, 0, 0, 0, false);
        continue;
      }
      const p = this.world([s.x, s.y]);
      m.root.position.copyFrom(p);
      this.bodies.setPose(m.index, p.x, p.z, s.vx, s.vy, true, !s.observed);
    }
    this.bodies.flush();
  }

  setHighlight(ids: string[]): void {
    this.highlighted = [...ids];
    for (const [id, m] of this.markers) if (m.ring) m.ring.isVisible = ids.includes(id);
  }

  setOverlays(overlays: Overlay[]): void {
    for (const mesh of this.overlayMeshes) mesh.dispose(false, false);
    this.overlayMeshes = [];
    overlays.forEach((o, i) => this.overlayMeshes.push(...this.drawOverlay(o, `ov${i}`)));
  }

  /** A thick dashed line as short tube segments, merged into one mesh. */
  private dashes(name: string, from: Vector3, to: Vector3, radius: number, color: string): Mesh | null {
    const dir = to.subtract(from);
    const len = dir.length();
    const dash = 1.1;
    const gap = 0.7;
    const parts: Mesh[] = [];
    for (let s = 0; s < len; s += dash + gap) {
      const a = from.add(dir.scale(s / len));
      const b = from.add(dir.scale(Math.min(s + dash, len) / len));
      parts.push(MeshBuilder.CreateTube(`${name}-${s}`, { path: [a, b], radius, tessellation: 6 }, this.scene));
    }
    if (parts.length === 0) return null;
    const merged = Mesh.MergeMeshes(parts, true, true);
    if (merged) merged.material = this.material(color, 1, true);
    return merged;
  }

  private drawOverlay(o: Overlay, name: string): Mesh[] {
    const out: Mesh[] = [];
    const label = (text: string | undefined, at: Vec2, color: string) => {
      if (!text || !this.opts.labels) return;
      const p = this.textPlane(`${name}-label`, text, color, 1.15);
      p.position = this.world(at, PLAYER_HEIGHT + 2.4);
      out.push(p);
    };
    switch (o.type) {
      case "arrow": {
        const from = this.world(o.from, 0.3);
        const to = this.world(o.to, 0.3);
        const dir = to.subtract(from);
        const len = dir.length();
        if (len < 1e-3) break;
        const head = Math.min(1.8, len * 0.4);
        const shaftEnd = from.add(dir.scale((len - head) / len));
        const radius = Math.max(o.width / 2, 0.1);
        const shaft = o.dashed
          ? this.dashes(`${name}-shaft`, from, shaftEnd, radius, o.color)
          : MeshBuilder.CreateTube(`${name}-shaft`, { path: [from, shaftEnd], radius, tessellation: 8 }, this.scene);
        if (shaft) {
          if (!o.dashed) shaft.material = this.material(o.color, 1, true);
          out.push(shaft);
        }
        const cone = MeshBuilder.CreateCylinder(`${name}-head`, { diameterTop: 0, diameterBottom: Math.max(o.width * 6, 0.9), height: head, tessellation: 12 }, this.scene);
        cone.material = this.material(o.color, 1, true);
        cone.rotation.x = Math.PI / 2; // tip from +y to +z, baked, so lookAt can aim it
        cone.bakeCurrentTransformIntoVertices();
        cone.position = shaftEnd.add(dir.scale(head / (2 * len)));
        cone.lookAt(to);
        out.push(cone);
        label(o.label, [(o.from[0] + o.to[0]) / 2, (o.from[1] + o.to[1]) / 2], o.color);
        break;
      }
      case "disc": {
        const disc = MeshBuilder.CreateDisc(name, { radius: o.radius, tessellation: 48 }, this.scene);
        disc.rotation.x = Math.PI / 2;
        disc.position = this.world(o.center, 0.05);
        disc.material = this.material(o.color, o.alpha, true);
        out.push(disc);
        label(o.label, [o.center[0], o.center[1] + o.radius], o.color);
        break;
      }
      case "line": {
        const a = this.world(o.a, 0.3);
        const b = this.world(o.b, 0.3);
        const l = o.dashed
          ? this.dashes(name, a, b, 0.08, o.color)
          : MeshBuilder.CreateTube(name, { path: [a, b], radius: 0.12, tessellation: 8 }, this.scene);
        if (l) {
          if (!o.dashed) l.material = this.material(o.color, 1, true);
          out.push(l);
        }
        label(o.label, [(o.a[0] + o.b[0]) / 2, (o.a[1] + o.b[1]) / 2], o.color);
        break;
      }
      case "trail": {
        const l = MeshBuilder.CreateTube(name, { path: o.points.map((p) => this.world(p, 0.12)), radius: 0.07, tessellation: 6 }, this.scene);
        l.material = this.material(o.color, 0.55, true);
        out.push(l);
        break;
      }
      case "cross": {
        for (const [k, rot] of [[0, Math.PI / 4], [1, -Math.PI / 4]] as const) {
          const bar = MeshBuilder.CreateBox(`${name}-${k}`, { width: 2.4, height: 0.14, depth: 0.34 }, this.scene);
          bar.position = this.world(o.at, 0.4);
          bar.rotation.y = rot;
          bar.material = this.material(o.color, 1, true);
          out.push(bar);
        }
        label(o.label, o.at, o.color);
        break;
      }
    }
    for (const m of out) m.isPickable = false;
    return out;
  }

  /** Ease the camera onto these pitch points (centroid; zoom to fit their spread). */
  focus(points: Vec2[]): void {
    if (points.length === 0) return;
    const cx = points.reduce((s, p) => s + p[0], 0) / points.length;
    const cy = points.reduce((s, p) => s + p[1], 0) / points.length;
    const spread = Math.max(...points.map((p) => Math.hypot(p[0] - cx, p[1] - cy)), 6);
    this.desiredTarget = this.world([cx, cy]);
    this.desiredRadius = Math.min(Math.max(spread * 2.6, 26), 120);
  }

  /** Whole pitch, broadcast angle (or straight down in 2D). */
  resetView(): void {
    this.desiredTarget = Vector3.Zero();
    this.desiredRadius = this.is2D ? 110 : VIEW_3D.radius;
    this.camera.alpha = VIEW_3D.alpha;
    this.camera.beta = this.is2D ? VIEW_2D_BETA : VIEW_3D.beta;
  }

  set2D(on: boolean): void {
    this.is2D = on;
    this.camera.lowerBetaLimit = on ? VIEW_2D_BETA : 0.01;
    this.camera.beta = on ? VIEW_2D_BETA : VIEW_3D.beta;
    this.camera.alpha = VIEW_3D.alpha;
  }

  /** Toggle a slow orbit around the target; returns whether it is on. */
  toggleAutoRotate(): boolean {
    this.camera.useAutoRotationBehavior = !this.camera.useAutoRotationBehavior;
    const b = this.camera.autoRotationBehavior;
    if (b) {
      b.idleRotationSpeed = 0.15;
      b.idleRotationWaitTime = 0;
      b.idleRotationSpinupTime = 500;
    }
    return this.camera.useAutoRotationBehavior;
  }

  /** Compass heading in radians: 0 when looking up the pitch from the broadcast side. */
  get heading(): number {
    return this.camera.alpha - VIEW_3D.alpha;
  }

  /** Per-frame camera easing towards the last focus. */
  step(dtSeconds: number): void {
    const k = 1 - Math.exp(-dtSeconds * 4);
    if (this.desiredTarget) {
      this.camera.target = Vector3.Lerp(this.camera.target, this.desiredTarget, k);
      if (Vector3.Distance(this.camera.target, this.desiredTarget) < 0.01) this.desiredTarget = null;
    }
    if (this.desiredRadius !== null) {
      this.camera.radius += (this.desiredRadius - this.camera.radius) * k;
      if (Math.abs(this.camera.radius - this.desiredRadius) < 0.01) this.desiredRadius = null;
    }
  }

  get focusTarget(): Vector3 | null {
    return this.desiredTarget;
  }

  render(): void {
    this.scene.render();
  }
}
