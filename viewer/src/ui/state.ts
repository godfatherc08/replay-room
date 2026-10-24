// Shared UI state: Story / Explore and Analyst / Fan, with listeners. Kept tiny on purpose.

import type { View } from "../controller";
import { ALL_DEEP_LAYERS, type DeepLayers, type Mode } from "../overlays";

export type { Mode, View };

type Listener = () => void;

/** Which claim's evidence is open: a story beat, or a fact of the account. */
export type EvidenceKey = { beat: string } | { contribution: string };

export class UIState {
  mode: Mode;
  view: View;
  evidence: EvidenceKey | null = null;
  expanded = false; // the step card's full reasoning, and the deep view on the pitch
  layers: DeepLayers = { ...ALL_DEEP_LAYERS }; // which deep layers are drawn (the legend's toggles)
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

  setEvidence(key: EvidenceKey | null): void {
    this.evidence = key;
    this.emit();
  }

  setExpanded(on: boolean): void {
    this.expanded = on;
    this.emit();
  }

  setLayer(layer: keyof DeepLayers, on: boolean): void {
    this.layers = { ...this.layers, [layer]: on };
    this.emit();
  }

  private emit(): void {
    for (const l of this.listeners) l();
  }
}
