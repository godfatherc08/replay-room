import { describe, expect, it } from "vitest";
import { highlightedPlayers, outcomeBanner, panelItems, signed } from "../src/account";
import { parseBundle } from "../src/bundle";
import { fixture } from "./helpers";

describe("panel", () => {
  it("lists every contribution once, headline first, then in the account's rank order", () => {
    const b = fixture();
    const items = panelItems(b);
    expect(items.map((i) => i.id).sort()).toEqual(b.account.contributions.map((c) => c.contribution_id).sort());
    expect(items[0]).toMatchObject({ id: b.account.headline_contribution_id, headline: true });
    const rest = items.slice(1).map((i) => i.rank);
    expect(rest).toEqual([...rest].sort((x, y) => x - y));
  });

  it("shows the account's own labels, values and jump frames", () => {
    const b = fixture();
    const head = panelItems(b)[0];
    expect(head).toMatchObject({ id: "d163", label: "shot_missed", playerId: "EPA-11", effectText: "−0.152" });
    expect(head.frameId).toBe(b.jumps.find((j) => j.contribution_id === "d163")!.frame_id);
    expect(panelItems(b).find((i) => i.id === "a161")!.hasCounterfactual).toBe(true);
    expect(signed(0.0371)).toBe("+0.037");
  });

  it("highlights exactly the players a contribution names", () => {
    const b = fixture();
    const c = b.account.contributions.find((x) => x.track === "off_ball")!;
    const named = new Set([c.player_id, ...c.evidence.flatMap((r) => (r.kind === "frame" ? r.player_ids : []))]);
    expect(new Set(highlightedPlayers(c))).toEqual(named);
  });

  it("labels a prevented outcome as prevented, with what denied it", () => {
    const banner = outcomeBanner(fixture());
    expect(banner.framing).toBe("prevented");
    expect(banner.detail).toContain("no goal");
    expect(banner.detail).toContain("denied: shot_missed");
    expect(banner.detail).not.toContain("scored");
  });

  it("refuses a bundle whose jump leaves the window", () => {
    const b = structuredClone(fixture());
    b.jumps[0].frame_id = 1;
    expect(() => parseBundle(b)).toThrow(/not in the window/);
  });
});
