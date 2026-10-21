// Position of a tracked object at a fractional frame position, from the observed samples only.
//
// Between two observed frames: cubic Hermite on positions and velocities (the
// feed's own velocities, so motion between 10 Hz samples is smooth and passes
// exactly through every observation). Across a gap (missing samples): straight
// line between the nearest observed frames, flagged `observed: false` so the
// marker is drawn as interpolated. Before the first or after the last
// observation nothing is shown: positions are never extrapolated.

import type { Track } from "./bundle";

export interface Sample {
  x: number;
  y: number;
  vx: number;
  vy: number;
  observed: boolean;
}

function known(t: Track, i: number): boolean {
  return t.x[i] !== null && t.y[i] !== null;
}

function hermite(p0: number, v0: number, p1: number, v1: number, u: number, dt: number): number {
  const u2 = u * u;
  const u3 = u2 * u;
  return (2 * u3 - 3 * u2 + 1) * p0 + (u3 - 2 * u2 + u) * v0 * dt + (-2 * u3 + 3 * u2) * p1 + (u3 - u2) * v1 * dt;
}

export function sampleTrack(t: Track, pos: number, fps: number): Sample | null {
  const n = t.x.length;
  if (pos < 0 || pos > n - 1) return null;
  const i = Math.min(Math.floor(pos), n - 1);
  const u = pos - i;
  if (u === 0 && known(t, i)) {
    return { x: t.x[i]!, y: t.y[i]!, vx: t.vx[i] ?? 0, vy: t.vy[i] ?? 0, observed: true };
  }
  if (i + 1 < n && known(t, i) && known(t, i + 1)) {
    const dt = 1 / fps;
    const [vx0, vy0, vx1, vy1] = [t.vx[i] ?? 0, t.vy[i] ?? 0, t.vx[i + 1] ?? 0, t.vy[i + 1] ?? 0];
    return {
      x: hermite(t.x[i]!, vx0, t.x[i + 1]!, vx1, u, dt),
      y: hermite(t.y[i]!, vy0, t.y[i + 1]!, vy1, u, dt),
      vx: vx0 + u * (vx1 - vx0),
      vy: vy0 + u * (vy1 - vy0),
      observed: true,
    };
  }
  // A gap: interpolate linearly between the nearest observations, visibly.
  let a = i;
  while (a >= 0 && !known(t, a)) a--;
  let b = u === 0 ? i : i + 1;
  while (b < n && !known(t, b)) b++;
  if (a < 0 || b >= n) return null;
  const w = (pos - a) / (b - a);
  return {
    x: t.x[a]! + w * (t.x[b]! - t.x[a]!),
    y: t.y[a]! + w * (t.y[b]! - t.y[a]!),
    vx: 0,
    vy: 0,
    observed: false,
  };
}
