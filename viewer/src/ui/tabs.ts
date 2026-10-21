// The other panel tabs, each a direct read of the account: Tactics (counterfactuals), Metrics (the numbers
// behind each fact), Players (who the account names), and the match's Moments for the rail.

import { playerLabel, signed, teamName } from "../account";
import type { Viewer } from "../controller";
import { button, el } from "./dom";

export function buildTactics(viewer: Viewer, onJump: () => void): HTMLElement {
  const { bundle } = viewer;
  const box = el("section", "rr-tab-body rr-tactics");
  box.append(el("h2", undefined, "Decisions"));
  if (bundle.account.counterfactuals.length === 0) {
    box.append(el("p", "rr-muted", "This account has no counterfactual: no available option beat the one chosen by the margin."));
    return box;
  }
  for (const cf of bundle.account.counterfactuals) {
    const card = el("div", "rr-cf");
    const c = bundle.account.contributions.find((x) => x.contribution_id === cf.contribution_id);
    card.append(el("div", "rr-cf-who", c ? `${playerLabel(bundle, c.player_id)} · ${teamName(bundle, c.team_id)}` : cf.contribution_id));
    card.append(el("div", "rr-cf-row rr-cf-chosen", `Chosen: ${cf.chosen} — ${cf.chosen_value.toFixed(3)}`));
    for (const a of cf.alternatives) {
      const comp = a.completion_prob !== null ? ` (completion ${a.completion_prob.toFixed(2)})` : "";
      card.append(el("div", "rr-cf-row rr-cf-better", `Better: ${a.description} — ${a.value.toFixed(3)}${comp}`));
    }
    const show = button("rr-cf-show", "Show the options on the pitch", "Show on pitch →");
    show.addEventListener("click", () => {
      viewer.jump(cf.contribution_id);
      onJump();
    });
    card.append(show);
    box.append(card);
  }
  return box;
}

export function buildMetrics(viewer: Viewer): HTMLElement {
  const { bundle } = viewer;
  const { outcome } = bundle.account;
  const box = el("section", "rr-tab-body rr-metrics");
  box.append(el("h2", undefined, "Outcome"));
  const dl = el("dl", "rr-kv");
  const kv = (k: string, v: string) => dl.append(el("dt", undefined, k), el("dd", undefined, v));
  kv("Value", `${outcome.value_source === "xg" ? "xG" : "xT"} ${outcome.value.toFixed(3)}`);
  kv("Result", outcome.scored ? "scored" : "no goal");
  kv("Framing", outcome.realized ? "realized" : "prevented");
  kv("Attacking", teamName(bundle, outcome.beneficiary_team_id));
  box.append(dl, el("h2", undefined, "Facts by effect"));
  const table = el("table", "rr-table");
  const head = el("tr");
  for (const h of ["#", "Fact", "Effect", "Numbers"]) head.append(el("th", undefined, h));
  table.append(head);
  const units = new Map(bundle.display.map((d) => [d.contribution_id, d.unit]));
  for (const c of bundle.account.contributions) {
    const tr = el("tr");
    const numbers = Object.entries(c.metrics).map(([k, v]) => `${k} ${v.toFixed(3)}`).join(", ");
    tr.append(el("td", undefined, String(c.rank)), el("td", undefined, `${(c.action ?? c.signal ?? "").replace(/_/g, " ")} · ${playerLabel(bundle, c.player_id)}`),
              el("td", c.effect >= 0 ? "rr-pos" : "rr-neg", `${signed(c.effect)} ${units.get(c.contribution_id) ?? ""}`),
              el("td", "rr-muted", numbers));
    table.append(tr);
  }
  box.append(table);
  return box;
}

export function buildPlayers(viewer: Viewer, onJump: () => void): HTMLElement {
  const { bundle } = viewer;
  const box = el("section", "rr-tab-body rr-players");
  const counts = new Map<string, number>();
  for (const c of bundle.account.contributions) counts.set(c.player_id, (counts.get(c.player_id) ?? 0) + 1);
  for (const team of bundle.account.teams) {
    box.append(el("h2", undefined, team.name));
    const list = el("ul", "rr-player-list");
    for (const p of bundle.account.participants.filter((x) => x.team_id === team.team_id)) {
      const n = counts.get(p.player_id) ?? 0;
      const b = button("rr-player", `Show ${p.name}`, "");
      b.append(el("span", "rr-shirt", p.shirt_number !== null ? String(p.shirt_number) : "-"), el("span", undefined, p.name),
               el("span", "rr-muted", n ? `${n} fact${n > 1 ? "s" : ""}` : "named in evidence"));
      b.disabled = n === 0;
      b.addEventListener("click", () => {
        viewer.selectPlayer(p.player_id);
        onJump();
      });
      const li = el("li");
      li.append(b);
      list.append(li);
    }
    box.append(list);
  }
  return box;
}

export function buildMoments(viewer: Viewer, onPick: ((id: string) => void) | undefined): HTMLElement {
  const { bundle } = viewer;
  const box = el("section", "rr-tab-body rr-moments");
  box.append(el("h2", undefined, `Moments in ${bundle.match.home.short_name} v ${bundle.match.away.short_name}`));
  const list = el("ol", "rr-moment-list");
  for (const m of bundle.match_moments) {
    const current = m.moment_id === bundle.account.moment.moment_id;
    const b = button(`rr-moment-item${current ? " rr-on" : ""}`, `Open ${m.moment_id}`, "");
    b.append(el("span", "rr-time", m.match_clock), el("span", undefined, m.type.replace(/_/g, " ")),
             el("span", `rr-chip rr-${m.realized ? "realized" : "prevented"}`, m.realized ? "REALIZED" : "PREVENTED"));
    b.disabled = current;
    b.addEventListener("click", () => onPick?.(m.moment_id));
    const li = el("li");
    li.append(b);
    list.append(li);
  }
  box.append(list);
  return box;
}
