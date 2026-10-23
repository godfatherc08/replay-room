// Shared UI state: Story / Explore and Analyst / Fan, with listeners. Kept tiny on purpose.

import type { View } from "../controller";
import type { Mode } from "../overlays";

export type { Mode, View };

type Listener = () => void;

export class UIState {
  mode: Mode;
  view: View;
  private listeners: Listener[] = [];

  constructor(mode: Mode = "analyst", view: View = "story") {
    this.mode = mode;
    this.view = view;
  }

  onChange(fn: Listener): void {
    this.listeners.push(fn);
  }

  setMode(mode: Mode): void {
    this.mode = mode;
    this.emit();
  }

  setView(view: View): void {
    this.view = view;
    this.emit();
  }

  private emit(): void {
    for (const l of this.listeners) l();
  }
}
