// Wires the clock, the story, the scene and the account together. It shows what Build 4 computed; it decides nothing.
//
// Two ways through a moment:
// * Story (default): Story walks the bundle's steps; each step leads the replay into its frame, puts its players
//   in focus (everyone else dimmed), names the first of them, eases the camera onto them and, once the replay
//   reaches the frame, draws that step's overlay alone.
// * Explore: free scrubbing; clicking a fact (jump) seeks straight to its frame with the same focus and drawing.
// * Evidence (either way): opening a claim's proof pauses, seeks to the proof's frame, rings and names every
//   player the proof involves, and frames them close; closing it returns to the step.

import { contribution, highlightedPlayers, evidenceRows, shortLabel, stepPlayers } from "./account";
import { type Bundle, positionAt, type Proof, type StoryStep } from "./bundle";
import { type Sample, sampleTrack } from "./motion";
import { type Mode, type Overlay, overlayPoints, overlaysFor, stepOverlays, type Vec2 } from "./overlays";
import { Story } from "./story";
import { Clock } from "./timeline";

/** What the controller needs from a scene (the Babylon PitchScene, or a fake in tests). */
export interface SceneLike {
  update(samples: Map<string, Sample | null>): void;
  setHighlight(ids: string[]): void; // ringed and lit; everyone else dimmed (none: all lit)
  setLabel(id: string | null, text?: string): void; // the one floating name tag
  setLabels(entries: { id: string; text: string }[]): void; // a proof's players, all named
  setOverlays(overlays: Overlay[]): void;
  focus(points: Vec2[], fit?: number): void; // eases, never snaps
  step(dtSeconds: number): void;
}

export const LEAD_IN_S = 1.2;
const REVEAL_FIT = 2.0; // an opened proof frames its players close (a step frames the play wide) // a step replays this much of the play before its frame
const CONTINUE_WITHIN_S = 3.0; // closer than this ahead: keep playing from where we are instead of rewinding

export type View = "story" | "explore";

export class Viewer {
  readonly clock: Clock;
  readonly story: Story;
  active: string | null = null; // the selected contribution (Explore), or the current step's contribution (Story)
  mode: Mode = "analyst";
  view: View = "story";
  proof: Proof | null = null; // the evidence open on the pitch, if any
  private readonly jumps: Map<string, number>;
  private pending: Overlay[] | null = null; // drawn when the lead-in reaches the frame

  constructor(readonly bundle: Bundle, readonly scene: SceneLike) {
    this.clock = new Clock(bundle.frames.frame_ids, bundle.frames.timestamps, bundle.pitch.frame_rate_hz);
    this.jumps = new Map(bundle.jumps.map((j) => [j.contribution_id, j.frame_id]));
    this.story = new Story(bundle.story, (step) => this.showStep(step));
    this.clear();
  }

  samples(): Map<string, Sample | null> {
    const out = new Map<string, Sample | null>();
    for (const o of this.bundle.objects) {
      out.set(o.id, sampleTrack(this.bundle.tracks[o.id], this.clock.pos, this.clock.fps));
    }
    return out;
  }

  /** One animation step: advance the story and the clock, draw a step once its frame is reached, ease the camera. */
  frame(dtSeconds: number): void {
    this.story.tick(dtSeconds);
    this.clock.tick(dtSeconds);
    if (this.pending && !this.clock.playing) {
      this.scene.setOverlays(this.pending);
      this.pending = null;
    }
    this.scene.update(this.samples());
    this.scene.step(dtSeconds);
  }

  private focusOn(players: string[], frameId: number, overlays: Overlay[]): void {
    this.scene.setHighlight(players);
    this.scene.setLabel(players[0] ?? null, players[0] ? shortLabel(this.bundle, players[0]) : undefined);
    const points = players.map((p) => positionAt(this.bundle, p, frameId)).filter((p): p is Vec2 => p !== null);
    this.scene.focus([...points, ...overlayPoints(overlays)]);
  }

  /** Open a claim's proof on the pitch: pause, seek to its frame, ring and name everyone it involves, frame them
   *  close. The beat's (or fact's) own drawing stays. */
  reveal(proof: Proof, overlays: Overlay[] = []): void {
    this.story.pause();
    this.clock.pause();
    this.clock.seekFrame(proof.focus_frame);
    this.pending = null;
    this.proof = proof;
    const ids = proof.players.map((p) => p.player_id).filter((id) => this.bundle.tracks[id]);
    this.scene.setOverlays(overlays);
    this.scene.setHighlight(ids);
    this.scene.setLabels(ids.map((id) => ({ id, text: shortLabel(this.bundle, id) })));
    const points = ids.map((p) => positionAt(this.bundle, p, proof.focus_frame)).filter((p): p is Vec2 => p !== null);
    this.scene.focus([...points, ...overlayPoints(overlays)], REVEAL_FIT);
    this.scene.update(this.samples());
  }

  /** Close the proof: back to the step (Story) or the selected fact (Explore). */
  conceal(): void {
    if (!this.proof) return;
    this.proof = null;
    const step = this.story.current;
    if (this.view === "story" && step) this.showStep(step);
    else if (this.active) this.jump(this.active);
    else this.clear();
  }

  /** Story: show one step (called by Story on every step change). */
  showStep(step: StoryStep): void {
    this.view = "story";
    this.proof = null;
    this.active = step.contribution_id;
    const target = this.clock.frameIds.indexOf(step.frame_id);
    const lead = Math.round(LEAD_IN_S * this.clock.fps);
    const ahead = target - this.clock.pos;
    this.clock.pause();
    if (!(ahead > 0 && ahead <= CONTINUE_WITHIN_S * this.clock.fps)) this.clock.seekIndex(Math.max(target - lead, 0));
    this.clock.setSpeed(this.story.speed);
    this.clock.playTo(target);
    const overlays = stepOverlays(this.bundle, step, this.mode);
    this.pending = this.clock.playing ? overlays : null;
    this.scene.setOverlays(this.clock.playing ? [] : overlays); // already at the frame: draw now
    this.focusOn(stepPlayers(this.bundle, step), step.frame_id, overlays);
  }

  /** Explore: jump to a contribution: pause, seek to its frame, focus its players, draw it, frame them. */
  jump(id: string): void {
    this.proof = null;
    const frameId = this.jumps.get(id);
    if (frameId === undefined) throw new Error(`no jump frame for ${id}`);
    const c = contribution(this.bundle, id);
    this.story.pause();
    this.clock.pause();
    this.clock.seekFrame(frameId);
    this.active = id;
    this.pending = null;
    const overlays = overlaysFor(this.bundle, id, this.mode);
    this.scene.setOverlays(overlays);
    this.focusOn(highlightedPlayers(c), frameId, overlays);
    this.scene.update(this.samples());
  }

  /** Jump to the previous / next piece of evidence in story order (from the active one, or from the start). */
  stepEvidence(dir: 1 | -1): string | null {
    const rows = evidenceRows(this.bundle);
    if (rows.length === 0) return null;
    const at = rows.findIndex((r) => r.id === this.active);
    const next = at < 0 ? (dir > 0 ? 0 : rows.length - 1) : Math.min(Math.max(at + dir, 0), rows.length - 1);
    this.jump(rows[next].id);
    return rows[next].id;
  }

  /** Switch Story / Explore. Explore keeps what is on the pitch; Story resumes at its step (or the title card). */
  setView(view: View): void {
    this.view = view;
    if (view === "explore") {
      this.story.pause();
      return;
    }
    const step = this.story.current;
    if (step) this.showStep(step);
    else this.clear();
  }

  /** Analyst / Fan changes the words and numbers, never the facts: redraw what is up in the new register. */
  setMode(mode: Mode): void {
    this.mode = mode;
    if (this.view === "story" && this.story.current) {
      const overlays = stepOverlays(this.bundle, this.story.current, mode);
      if (this.pending) this.pending = overlays;
      else this.scene.setOverlays(overlays);
    } else if (this.view === "explore" && this.active) {
      this.scene.setOverlays(overlaysFor(this.bundle, this.active, mode));
    }
  }

  /** The plain replay: nobody in focus, nothing drawn, the camera on the whole move. */
  clear(): void {
    this.active = null;
    this.pending = null;
    this.scene.setHighlight([]);
    this.scene.setLabel(null);
    this.scene.setOverlays([]);
  }
}
