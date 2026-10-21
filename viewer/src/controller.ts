// Wires the clock, the scene and the account together. It shows what Build 4 computed; it decides nothing.

import { contribution, highlightedPlayers } from "./account";
import { type Bundle, positionAt } from "./bundle";
import { type Sample, sampleTrack } from "./motion";
import { outcomeOverlays, type Overlay, overlayPoints, overlaysFor, type Vec2 } from "./overlays";
import { Clock } from "./timeline";

/** What the controller needs from a scene (the Babylon PitchScene, or a fake in tests). */
export interface SceneLike {
  update(samples: Map<string, Sample | null>): void;
  setHighlight(ids: string[]): void;
  setOverlays(overlays: Overlay[]): void;
  focus(points: Vec2[]): void;
  step(dtSeconds: number): void;
}

export class Viewer {
  readonly clock: Clock;
  active: string | null = null;
  private readonly jumps: Map<string, number>;

  constructor(readonly bundle: Bundle, readonly scene: SceneLike) {
    this.clock = new Clock(bundle.frames.frame_ids, bundle.frames.timestamps, bundle.pitch.frame_rate_hz);
    this.jumps = new Map(bundle.jumps.map((j) => [j.contribution_id, j.frame_id]));
    this.clear();
  }

  samples(): Map<string, Sample | null> {
    const out = new Map<string, Sample | null>();
    for (const o of this.bundle.objects) {
      out.set(o.id, sampleTrack(this.bundle.tracks[o.id], this.clock.pos, this.clock.fps));
    }
    return out;
  }

  /** One animation step: advance the clock (if playing), move the markers, ease the camera. */
  frame(dtSeconds: number): void {
    this.clock.tick(dtSeconds);
    this.scene.update(this.samples());
    this.scene.step(dtSeconds);
  }

  /** Jump to a contribution: pause, seek to its frame, highlight its players, draw its overlays, frame them. */
  jump(id: string): void {
    const frameId = this.jumps.get(id);
    if (frameId === undefined) throw new Error(`no jump frame for ${id}`);
    const c = contribution(this.bundle, id);
    this.clock.pause();
    this.clock.seekFrame(frameId);
    this.active = id;
    const players = highlightedPlayers(c);
    this.scene.setHighlight(players);
    const overlays = overlaysFor(this.bundle, id);
    this.scene.setOverlays(overlays);
    // Frame the named players and what this fact draws (the outcome's track is always drawn; leave it out).
    const own = overlays.slice(outcomeOverlays(this.bundle).length);
    const points = players.map((p) => positionAt(this.bundle, p, frameId)).filter((p): p is Vec2 => p !== null);
    this.scene.focus([...points, ...overlayPoints(own)]);
    this.scene.update(this.samples());
  }

  /** Back to the plain replay: no highlight, only the outcome drawn. */
  clear(): void {
    this.active = null;
    this.scene.setHighlight([]);
    this.scene.setOverlays(outcomeOverlays(this.bundle));
  }
}
