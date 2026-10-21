// The Event tab: moment header, the evidence list (the main call to action), and the summary.

import { evidenceRows, momentHeader, summary } from "../account";
import type { Viewer } from "../controller";
import { button, el, icon } from "./dom";
import { badge } from "./topbar";

const HINT_KEY = "replay-room.hint-dismissed";

export type Store = Pick<Storage, "getItem" | "setItem"> | null;

export interface EventParts {
  header: HTMLElement;
  evidence: HTMLElement;
  summary: HTMLElement | null; // null when the bundle carries no narration
  markActive(): void; // reflect viewer.active on the rows
  setScore(text: string): void;
}

export function buildEvent(viewer: Viewer, store: Store): EventParts {
  const { bundle } = viewer;
  const h = momentHeader(bundle);

  const header = el("section", "rr-moment");
  const title = el("div", "rr-moment-title");
  title.append(el("span", `rr-dot rr-${h.framing}`), el("span", "rr-moment-class", h.classLabel),
               el("span", `rr-chip rr-${h.framing}`, h.framing.toUpperCase()));
  header.append(title, el("div", "rr-moment-meta", `${h.value} · ${h.clock}`));
  if (h.description) header.append(el("p", "rr-desc", h.description));
  const card = el("div", "rr-scorecard");
  const cardScore = el("span", "rr-card-score");
  card.append(badge(bundle, bundle.match.home.team_id), el("span", "rr-card-team", bundle.match.home.name), cardScore,
              el("span", "rr-card-team", bundle.match.away.name), badge(bundle, bundle.match.away.team_id));
  header.append(card);

  const evidence = el("section", "rr-evidence");
  evidence.append(el("h2", undefined, "Evidence & Key Moments"));
  const hint = el("div", "rr-hint");
  hint.append(el("span", undefined, "Click an evidence item to see it on the pitch."));
  const close = button("rr-hint-close", "Dismiss hint", "×");
  hint.append(close);
  hint.hidden = readFlag(store);
  const dismiss = () => {
    hint.hidden = true;
    writeFlag(store);
  };
  close.addEventListener("click", dismiss);
  const list = el("ol", "rr-evidence-list");
  list.setAttribute("aria-label", "evidence");
  const rows = new Map<string, HTMLButtonElement>();
  for (const r of evidenceRows(bundle)) {
    const b = el("button", `rr-evidence-row${r.headline ? " rr-headline" : ""}`);
    b.type = "button";
    b.dataset.id = r.id;
    b.dataset.frame = String(r.frameId);
    const main = el("span", "rr-row-main");
    main.append(el("span", "rr-row-title", r.title),
                el("span", "rr-row-sub", `${r.subtitle} · ${r.player}`));
    const chev = el("span", "rr-chev");
    chev.innerHTML = icon("chevron", 16);
    b.append(el("span", "rr-num", String(r.number)), main,
             el("span", `rr-value ${r.positive ? "rr-pos" : "rr-neg"}`, r.valueText),
             el("span", "rr-time", r.clock), chev);
    b.addEventListener("click", () => {
      viewer.jump(r.id);
      markActive();
      dismiss();
    });
    rows.set(r.id, b);
    const li = el("li");
    li.append(b);
    list.append(li);
  }
  evidence.append(hint, list);

  let summaryBox: HTMLElement | null = null;
  const story = summary(bundle);
  if (story) {
    summaryBox = el("section", "rr-summary");
    const h2 = el("h2");
    h2.innerHTML = `${icon("bulb", 18)}<span>Summary</span>`;
    const lead = el("p", "rr-summary-text", story.lead.map((s) => s.text).join(" "));
    const chain = el("ol", "rr-chain");
    chain.hidden = true;
    for (const s of story.all) {
      const link = button("rr-chain-link", "Show this on the pitch", "");
      link.textContent = s.text;
      link.dataset.id = s.contribution_id;
      link.addEventListener("click", () => {
        viewer.jump(s.contribution_id);
        markActive();
      });
      const li = el("li");
      li.append(link);
      chain.append(li);
    }
    const toggle = button("rr-chain-toggle", "View full evidence chain", "View Full Evidence Chain →");
    toggle.addEventListener("click", () => {
      chain.hidden = !chain.hidden;
      toggle.textContent = chain.hidden ? "View Full Evidence Chain →" : "Hide Evidence Chain";
    });
    summaryBox.append(h2, lead, chain, toggle, el("div", "rr-source", story.source));
  }

  function markActive(): void {
    for (const [id, b] of rows) b.classList.toggle("rr-active", id === viewer.active);
  }

  return { header, evidence, summary: summaryBox, markActive, setScore: (t) => (cardScore.textContent = t) };
}

function readFlag(store: Store): boolean {
  try {
    return store?.getItem(HINT_KEY) === "1";
  } catch {
    return false;
  }
}

function writeFlag(store: Store): void {
  try {
    store?.setItem(HINT_KEY, "1");
  } catch {
    // storage unavailable: the hint simply shows again next time
  }
}
