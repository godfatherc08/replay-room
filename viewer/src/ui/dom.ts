// Small DOM helpers, the inline icon set, and the two value visuals (meter, radial) shared by the UI modules.

export function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

export function button(cls: string, label: string, html: string): HTMLButtonElement {
  const b = el("button", cls);
  b.type = "button";
  b.setAttribute("aria-label", label);
  b.title = label;
  b.innerHTML = html;
  return b;
}

const PATHS: Record<string, string> = {
  camera: '<rect x="3" y="7" width="18" height="13" rx="2"/><circle cx="12" cy="13.5" r="3.5"/>',
  rotate: '<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v5h-5"/>',
  zoom: '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
  play: '<path d="M8 5v14l11-7z" fill="currentColor" stroke="none"/>',
  pause: '<path d="M6.5 5h4v14h-4zM13.5 5h4v14h-4z" fill="currentColor" stroke="none"/>',
  prev: '<path d="M7 5v14"/><path d="M19 5L9 12l10 7z" fill="currentColor" stroke="none"/>',
  next: '<path d="M17 5v14"/><path d="M5 5l10 7-10 7z" fill="currentColor" stroke="none"/>',
  restart: '<path d="M4 12a8 8 0 1 0 2.3-5.7"/><path d="M4 4v5h5"/>',
  chevron: '<path d="M9 6l6 6-6 6"/>',
  layers: '<path d="M12 4l8 4-8 4-8-4z"/><path d="M4 12l8 4 8-4"/><path d="M4 16l8 4 8-4"/>',
  // ribbon roles
  pass: '<path d="M4 17L17 6"/><path d="M11 6h6v6"/>',
  carry: '<circle cx="7" cy="16" r="3"/><path d="M10 14l8-8M13 6h5v5"/>',
  shot: '<circle cx="8" cy="15" r="3.2"/><path d="M11 12l9-7M15 5h5v5"/>',
  save: '<path d="M6 11V6a2 2 0 0 1 4 0v4M10 9V5a2 2 0 0 1 4 0v5M14 9V6a2 2 0 0 1 4 0v7a6 6 0 0 1-6 6h-1a6 6 0 0 1-5-3l-2-4a1.6 1.6 0 0 1 2.6-1.8L8 13"/>',
  turnover: '<path d="M7 7h10l-3-3M17 17H7l3 3"/>',
  run: '<circle cx="15" cy="4.5" r="2"/><path d="M8 21l3-6 3 2v4M6 12l3-4h5l3 4M11 8l-1 5"/>',
  space: '<rect x="4" y="4" width="16" height="16" rx="3" stroke-dasharray="3 3"/><circle cx="12" cy="12" r="2"/>',
  marking: '<circle cx="8" cy="12" r="3"/><circle cx="17" cy="12" r="3"/><path d="M11 12h3" stroke-dasharray="1.5 2"/>',
  goal: '<rect x="3" y="6" width="18" height="12" rx="1"/><path d="M3 10h18M3 14h18M9 6v12M15 6v12" stroke-width="1"/>',
  nogoal: '<rect x="3" y="6" width="18" height="12" rx="1"/><path d="M8 9l8 6M16 9l-8 6"/>',
  fork: '<path d="M6 20V12a4 4 0 0 1 4-4h8"/><path d="M15 5l3 3-3 3"/><path d="M6 12V4" stroke-dasharray="2 2"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  context: '<path d="M4 6h16"/><path d="M4 12h16" stroke-dasharray="2 2.5"/><path d="M4 18h16"/><circle cx="15" cy="12" r="2"/>',
};

export function icon(name: string, size = 20): string {
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" `
    + `stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PATHS[name] ?? ""}</svg>`;
}

/** "MM:SS" for a number of seconds. */
export function mmss(seconds: number): string {
  const s = Math.max(seconds, 0);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

export type Tone = "pos" | "neg" | "chosen" | "better" | "outcome";

/** A horizontal micro-meter: fill ∝ fraction (0..1), coloured by tone, growing in when created. */
export function meter(fraction: number, tone: Tone, cls = ""): HTMLElement {
  const m = el("span", `rr-meter rr-${tone}${cls ? ` ${cls}` : ""}`);
  m.setAttribute("role", "meter");
  m.setAttribute("aria-valuemin", "0");
  m.setAttribute("aria-valuemax", "1");
  m.setAttribute("aria-valuenow", String(fraction));
  const fill = el("span", "rr-meter-fill");
  fill.style.width = `${Math.max(Math.min(fraction, 1), 0.03) * 100}%`;
  m.append(fill);
  return m;
}

/** A radial gauge for a probability (0..1). */
export function radial(fraction: number, size = 44): HTMLElement {
  const r = 18;
  const c = 2 * Math.PI * r;
  const span = el("span", "rr-radial");
  span.innerHTML = `<svg viewBox="0 0 44 44" width="${size}" height="${size}" aria-hidden="true">`
    + `<circle cx="22" cy="22" r="${r}" class="rr-radial-track"/>`
    + `<circle cx="22" cy="22" r="${r}" class="rr-radial-fill" stroke-dasharray="${(c * Math.min(Math.max(fraction, 0), 1)).toFixed(2)} ${c.toFixed(2)}" transform="rotate(-90 22 22)"/></svg>`;
  return span;
}
