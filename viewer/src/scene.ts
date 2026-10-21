// The 3D scene: a flat pitch to scale, one marker per player and the ball, overlays, an orbit camera.
// Markers, not models: discs with shirt numbers in team colours, a ball sphere, schematic overlays.
//
// Pitch metres (x along the touchline, y across, origin bottom-left) map to world
// coordinates (x - L/2, height, y - W/2), so the pitch is centred on the origin.

import { ArcRotateCamera } from "@babylonjs/core/Cameras/arcRotateCamera";
import type { AbstractEngine } from "@babylonjs/core/Engines/abstractEngine";
import { HemisphericLight } from "@babylonjs/core/Lights/hemisphericLight";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import { DynamicTexture } from "@babylonjs/core/Materials/Textures/dynamicTexture";
import { Color3, Color4 } from "@babylonjs/core/Maths/math.color";
import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import type { Mesh } from "@babylonjs/core/Meshes/mesh";
import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder";
import { TransformNode } from "@babylonjs/core/Meshes/transformNode";
import { Scene } from "@babylonjs/core/scene";

import type { Bundle } from "./bundle";
import type { Sample } from "./motion";
import { COLORS, type Overlay, teamColor, type Vec2 } from "./overlays";

export interface SceneOptions {
  labels: boolean; // text needs a 2D canvas (off in headless tests)
}

interface Marker {
  root: TransformNode;
  body: Mesh;
  ring: Mesh | null;
  material: StandardMaterial;
}

export class PitchScene {
  readonly scene: Scene;
  readonly camera: ArcRotateCamera;
  readonly markers = new Map<string, Marker>();
  highlighted: string[] = [];
  overlayMeshes: Mesh[] = [];
  private readonly half: Vec2;
  private readonly materials = new Map<string, StandardMaterial>();
  private desiredTarget: Vector3 | null = null;
  private desiredRadius: number | null = null;

  constructor(engine: AbstractEngine, private readonly bundle: Bundle, private readonly opts: SceneOptions) {
    this.half = [bundle.pitch.length / 2, bundle.pitch.width / 2];
    this.scene = new Scene(engine);
    this.scene.clearColor = new Color4(0.06, 0.09, 0.13, 1);
    this.camera = new ArcRotateCamera("camera", -Math.PI / 2, 0.9, 85, Vector3.Zero(), this.scene);
    this.camera.lowerRadiusLimit = 8;
    this.camera.upperRadiusLimit = 160;
    this.camera.upperBetaLimit = Math.PI / 2 - 0.05;
    this.camera.wheelDeltaPercentage = 0.02;
    new HemisphericLight("light", new Vector3(0.2, 1, -0.3), this.scene).intensity = 1.0;
    this.buildPitch();
    this.buildMarkers();
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
    const ground = MeshBuilder.CreateGround("pitch", { width: L + 8, height: W + 8 }, this.scene);
    ground.material = this.material("#1f6f3a");
    const white = Color3.FromHexString("#e5efe8");
    const line = (pts: Vec2[], name: string) => {
      const l = MeshBuilder.CreateLines(name, { points: pts.map((p) => this.world(p, 0.02)) }, this.scene);
      l.color = white;
      l.isPickable = false;
    };
    const rect = (x0: number, y0: number, x1: number, y1: number, name: string) =>
      line([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]], name);
    rect(0, 0, L, W, "touchlines");
    line([[L / 2, 0], [L / 2, W]], "halfway");
    const circle: Vec2[] = [];
    for (let k = 0; k <= 64; k++) {
      const a = (k / 64) * 2 * Math.PI;
      circle.push([L / 2 + 9.15 * Math.cos(a), W / 2 + 9.15 * Math.sin(a)]);
    }
    line(circle, "centre-circle");
    for (const [x0, dir] of [[0, 1], [L, -1]] as const) {
      rect(x0, W / 2 - 20.16, x0 + dir * 16.5, W / 2 + 20.16, `box${x0}`);
      rect(x0, W / 2 - 9.16, x0 + dir * 5.5, W / 2 + 9.16, `six${x0}`);
      rect(x0, W / 2 - 3.66, x0 - dir * 1.5, W / 2 + 3.66, `goal${x0}`);
    }
  }

  private buildMarkers(): void {
    const numbers = new Map<string, number>();
    for (const t of this.bundle.teams) for (const p of t.players) numbers.set(p.player_id, p.shirt_number);
    for (const o of this.bundle.objects) {
      const root = new TransformNode(`obj-${o.id}`, this.scene);
      let body: Mesh;
      let ring: Mesh | null = null;
      let material: StandardMaterial;
      if (o.kind === "ball") {
        body = MeshBuilder.CreateSphere(`ball`, { diameter: 0.7, segments: 12 }, this.scene);
        body.position.y = 0.35;
        material = this.material("#ffffff", 1, true);
      } else {
        body = MeshBuilder.CreateCylinder(`marker-${o.id}`, { diameter: 1.5, height: 0.4, tessellation: 24 }, this.scene);
        body.position.y = 0.2;
        material = this.material(teamColor(this.bundle, o.team_id ?? ""));
        ring = MeshBuilder.CreateTorus(`ring-${o.id}`, { diameter: 2.6, thickness: 0.22, tessellation: 32 }, this.scene);
        ring.position.y = 0.05;
        ring.material = this.material(COLORS.highlight, 1, true);
        ring.parent = root;
        ring.isVisible = false;
        if (this.opts.labels) {
          const label = this.textPlane(`n-${o.id}`, String(numbers.get(o.id) ?? o.id), "#ffffff", 1.4);
          label.position.y = 1.6;
          label.parent = root;
        }
      }
      body.material = material;
      body.parent = root;
      root.setEnabled(false);
      this.markers.set(o.id, { root, body, ring, material });
    }
  }

  private textPlane(name: string, text: string, color: string, height: number): Mesh {
    const h = 64;
    const w = Math.max(64, Math.ceil(text.length * 30 + 24));
    const tex = new DynamicTexture(`${name}-tex`, { width: w, height: h }, this.scene, false);
    tex.hasAlpha = true;
    const ctx = tex.getContext();
    ctx.fillStyle = "rgba(10,14,20,0.72)";
    ctx.fillRect(0, 0, w, h);
    tex.drawText(text, null, 46, "bold 40px system-ui, sans-serif", color, null, true);
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

  /** Move every marker to its sample; hide what has no sample; dim what is interpolated across a gap. */
  update(samples: Map<string, Sample | null>): void {
    for (const [id, m] of this.markers) {
      const s = samples.get(id) ?? null;
      m.root.setEnabled(s !== null);
      if (!s) continue;
      m.root.position.copyFrom(this.world([s.x, s.y]));
      m.body.visibility = s.observed ? 1 : 0.35;
    }
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

  private drawOverlay(o: Overlay, name: string): Mesh[] {
    const out: Mesh[] = [];
    const label = (text: string | undefined, at: Vec2, color: string) => {
      if (!text || !this.opts.labels) return;
      const p = this.textPlane(`${name}-label`, text, color, 1.3);
      p.position = this.world(at, 3.2);
      out.push(p);
    };
    switch (o.type) {
      case "arrow": {
        const from = this.world(o.from, 0.25);
        const to = this.world(o.to, 0.25);
        const dir = to.subtract(from);
        const len = dir.length();
        if (len < 1e-3) break;
        const head = Math.min(1.6, len * 0.4);
        const shaftEnd = from.add(dir.scale((len - head) / len));
        if (o.dashed) {
          const l = MeshBuilder.CreateDashedLines(`${name}-shaft`, { points: [from, shaftEnd], dashNb: Math.ceil(len), dashSize: 2, gapSize: 1 }, this.scene);
          l.color = Color3.FromHexString(o.color);
          out.push(l);
        } else {
          const tube = MeshBuilder.CreateTube(`${name}-shaft`, { path: [from, shaftEnd], radius: o.width / 2, tessellation: 8 }, this.scene);
          tube.material = this.material(o.color, 1, true);
          out.push(tube);
        }
        const cone = MeshBuilder.CreateCylinder(`${name}-head`, { diameterTop: 0, diameterBottom: Math.max(o.width * 5, 0.8), height: head, tessellation: 12 }, this.scene);
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
        disc.position = this.world(o.center, 0.03);
        disc.material = this.material(o.color, o.alpha, true);
        out.push(disc);
        label(o.label, [o.center[0], o.center[1] + o.radius], o.color);
        break;
      }
      case "line": {
        const pts = [this.world(o.a, 0.3), this.world(o.b, 0.3)];
        if (o.dashed) {
          const l = MeshBuilder.CreateDashedLines(name, { points: pts, dashNb: 20 }, this.scene);
          l.color = Color3.FromHexString(o.color);
          out.push(l);
        } else {
          const tube = MeshBuilder.CreateTube(name, { path: pts, radius: 0.1, tessellation: 8 }, this.scene);
          tube.material = this.material(o.color, 1, true);
          out.push(tube);
        }
        label(o.label, [(o.a[0] + o.b[0]) / 2, (o.a[1] + o.b[1]) / 2], o.color);
        break;
      }
      case "trail": {
        const l = MeshBuilder.CreateLines(name, { points: o.points.map((p) => this.world(p, 0.1)) }, this.scene);
        l.color = Color3.FromHexString(o.color);
        out.push(l);
        break;
      }
      case "cross": {
        for (const [k, rot] of [[0, Math.PI / 4], [1, -Math.PI / 4]] as const) {
          const bar = MeshBuilder.CreateBox(`${name}-${k}`, { width: 2.2, height: 0.12, depth: 0.3 }, this.scene);
          bar.position = this.world(o.at, 0.35);
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
    this.desiredRadius = Math.min(Math.max(spread * 2.6, 26), 110);
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
