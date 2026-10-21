import raw from "./fixtures/bundle.json";
import { type Bundle, parseBundle } from "../src/bundle";

/** A fresh copy of the fixture bundle (SYN-0007-big_chance_saved-3, exported by python -m replay_room.render). */
export function fixture(): Bundle {
  return parseBundle(structuredClone(raw));
}
