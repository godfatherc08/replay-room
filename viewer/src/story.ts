// Story Mode's sequencer: walks the bundle's story steps (build-up -> headline -> outcome -> counterfactual)
// one at a time, auto-advancing after a dwell, or stepped by hand. It only keeps time and the index; what a
// step shows is the controller's job (Viewer.showStep).

import type { StoryStep } from "./bundle";

export const DEFAULT_DWELL = 3.0; // s per step at 1x
export const CLIMAX_DWELL = 1.6; // the headline, the outcome and the counterfactual stay up longer
export type StoryState = "ready" | "playing" | "paused" | "done";
type Listener = (story: Story) => void;

export class Story {
  index = -1; // -1: the ready state (title card), before the first step
  playing = false;
  speed = 1; // dwell = DEFAULT_DWELL / speed
  elapsed = 0; // s into the current step
  readonly climax: Set<number>; // step indexes of the headline, the outcome and the counterfactual(s)
  private listeners: Listener[] = [];

  constructor(readonly steps: StoryStep[], private readonly onStep: (step: StoryStep) => void = () => {}) {
    const lastFact = steps.map((s) => s.kind).lastIndexOf("contribution"); // the exporter puts the headline last
    this.climax = new Set(steps.filter((s, i) => s.kind !== "contribution" || i === lastFact).map((s) => s.index));
  }

  get state(): StoryState {
    if (this.index < 0) return "ready";
    if (this.playing) return "playing";
    return this.index >= this.steps.length - 1 && this.elapsed >= this.dwell ? "done" : "paused";
  }

  /** Seconds the current step stays up. */
  get dwell(): number {
    return (DEFAULT_DWELL * (this.climax.has(this.index) ? CLIMAX_DWELL : 1)) / this.speed;
  }

  get current(): StoryStep | null {
    return this.index >= 0 ? this.steps[this.index] : null;
  }

  /** 0..1 through the current step's dwell (the ribbon fills from this node towards the next). */
  get within(): number {
    return this.index < 0 ? 0 : Math.min(this.elapsed / this.dwell, 1);
  }

  onChange(fn: Listener): void {
    this.listeners.push(fn);
  }

  private emit(): void {
    for (const l of this.listeners) l(this);
  }

  /** Start (or resume) the guided sequence. From the ready state or the end, it starts at step one. */
  play(): void {
    if (this.steps.length === 0) return;
    if (this.index < 0 || this.state === "done") this.goto(0);
    this.playing = true;
    this.emit();
  }

  pause(): void {
    this.playing = false;
    this.emit();
  }

  toggle(): void {
    if (this.playing) this.pause();
    else this.play();
  }

  setSpeed(speed: number): void {
    if (!(speed > 0)) throw new Error(`bad speed ${speed}`);
    this.speed = speed;
    this.emit();
  }

  /** Show step i (clamped). Keeps playing if it was. */
  goto(i: number): void {
    if (this.steps.length === 0) return;
    this.index = Math.min(Math.max(i, 0), this.steps.length - 1);
    this.elapsed = 0;
    this.onStep(this.steps[this.index]);
    this.emit();
  }

  next(): void {
    this.goto(this.index + 1);
  }

  prev(): void {
    this.goto(this.index - 1);
  }

  /** Back to the title card. */
  reset(): void {
    this.index = -1;
    this.elapsed = 0;
    this.playing = false;
    this.emit();
  }

  /** Advance wall-clock time while playing: move on after each dwell; stop on the last step. */
  tick(dtSeconds: number): void {
    if (!this.playing || this.index < 0) return;
    this.elapsed += dtSeconds;
    if (this.elapsed >= this.dwell) {
      if (this.index < this.steps.length - 1) {
        this.goto(this.index + 1);
        return;
      }
      this.elapsed = this.dwell;
      this.playing = false;
    }
    this.emit();
  }
}
