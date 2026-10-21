// Shared UI state: the active mode and tab, with listeners. Kept tiny on purpose.

export type Mode = "analyst" | "fan";
export type Tab = "event" | "tactics" | "metrics" | "players";

type Listener = () => void;

export class UIState {
  mode: Mode;
  tab: Tab = "event";
  private listeners: Listener[] = [];

  constructor(mode: Mode = "analyst") {
    this.mode = mode;
  }

  onChange(fn: Listener): void {
    this.listeners.push(fn);
  }

  setMode(mode: Mode): void {
    this.mode = mode;
    this.emit();
  }

  setTab(tab: Tab): void {
    this.tab = tab;
    this.emit();
  }

  private emit(): void {
    for (const l of this.listeners) l();
  }
}
