// The replay clock over a moment window: a fractional position in frames, play/pause/seek/speed.

export type ClockListener = (clock: Clock) => void;

export class Clock {
  readonly frameIds: number[];
  readonly timestamps: number[];
  readonly fps: number;
  pos = 0; // fractional index into frameIds
  playing = false;
  speed = 1;
  stopAt: number | null = null; // playTo: pause on reaching this index
  private listeners: ClockListener[] = [];

  constructor(frameIds: number[], timestamps: number[], fps: number) {
    if (frameIds.length === 0 || frameIds.length !== timestamps.length) throw new Error("empty or ragged window");
    this.frameIds = frameIds;
    this.timestamps = timestamps;
    this.fps = fps;
  }

  get last(): number {
    return this.frameIds.length - 1;
  }

  /** The window frame currently shown (nearest). */
  get frameId(): number {
    return this.frameIds[Math.round(this.pos)];
  }

  /** Match time at the current position (interpolated between frames). */
  get time(): number {
    const i = Math.floor(this.pos);
    const u = this.pos - i;
    if (i >= this.last) return this.timestamps[this.last];
    return this.timestamps[i] + u * (this.timestamps[i + 1] - this.timestamps[i]);
  }

  onChange(fn: ClockListener): () => void {
    this.listeners.push(fn);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== fn);
    };
  }

  private emit(): void {
    for (const l of this.listeners) l(this);
  }

  play(): void {
    if (this.pos >= this.last) this.pos = 0;
    this.stopAt = null;
    this.playing = true;
    this.emit();
  }

  /** Play from the current position up to index i, then pause there (a lead-in to a frame). */
  playTo(i: number): void {
    this.stopAt = Math.min(Math.max(i, 0), this.last);
    if (this.stopAt <= this.pos) {
      this.seekIndex(this.stopAt);
      this.stopAt = null;
      return;
    }
    this.playing = true;
    this.emit();
  }

  pause(): void {
    this.playing = false;
    this.stopAt = null;
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

  seekIndex(i: number): void {
    this.pos = Math.min(Math.max(i, 0), this.last);
    this.emit();
  }

  /** Seek to a window frame. Only frames of this window exist; anything else is an error. */
  seekFrame(frameId: number): void {
    const i = this.frameIds.indexOf(frameId);
    if (i < 0) throw new Error(`frame ${frameId} is not in the window`);
    this.seekIndex(i);
  }

  /** Advance by wall-clock seconds while playing; stops at the end of the window. */
  tick(dtSeconds: number): void {
    if (!this.playing) return;
    this.pos += dtSeconds * this.fps * this.speed;
    const end = this.stopAt ?? this.last;
    if (this.pos >= end) {
      this.pos = end;
      this.playing = false;
      this.stopAt = null;
    }
    this.emit();
  }
}
