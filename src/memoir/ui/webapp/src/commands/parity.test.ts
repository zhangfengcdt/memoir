import { describe, expect, it } from "vitest";
import { listCommands } from "./registry";

/**
 * Frozen parity inventory of the original command set the React webapp
 * shipped against. Each entry is ``[name]`` (no aliases) or
 * ``[name, ...aliases]``. The test asserts every entry resolves to some
 * registered command — placeholder or real — so accidental removals are
 * caught.
 *
 * The legacy single-file UI that originally seeded this list has been
 * removed; this remains the locked baseline of public commands.
 */
const V1_COMMANDS: string[][] = [
  ["connect", "con", "conn"],
  ["new", "create"],
  ["import"],
  ["remember", "rem"],
  ["forget", "del"],
  ["refresh", "ref"],
  ["demo"],
  ["repo"],
  ["code"],
  ["proof"],
  ["verify"],
  ["time-travel", "tt"],
  ["branch", "br"],
  ["checkout", "co"],
  ["merge"],
  ["commits", "log"],
  ["branches"],
  ["blame"],
  ["help", "h"],
  ["summarize", "sum"],
  ["recall", "search"],
  ["timeline", "tl"],
  ["location", "loc"],
  ["eval"],
  ["organize"],
  ["inspect"],
  ["diff", "d"],
  ["benchmark"],
  ["export"],
  ["compare-stores"],
  ["replay"],
  ["template"],
];

function buildResolver() {
  const all = listCommands();
  const byName = new Map<string, string>();
  for (const def of all) {
    byName.set(def.name, def.name);
    for (const alias of def.aliases) byName.set(alias, def.name);
  }
  return byName;
}

describe("v1 → v2 command parity", () => {
  it("every v1 canonical name is present in v2", () => {
    const resolver = buildResolver();
    const missing: string[] = [];
    for (const [canonical] of V1_COMMANDS) {
      if (!resolver.has(canonical)) missing.push(canonical);
    }
    expect(missing).toEqual([]);
  });

  it("every v1 alias resolves (to the same canonical or a parity equivalent)", () => {
    const resolver = buildResolver();
    const broken: string[] = [];
    for (const entry of V1_COMMANDS) {
      const aliases = entry.slice(1);
      for (const alias of aliases) {
        if (!resolver.has(alias)) broken.push(alias);
      }
    }
    expect(broken).toEqual([]);
  });

  it("inventory size sanity check", () => {
    // If this number changes, update V1_COMMANDS to match the legacy
    // availableCommands list. Failing here forces us to keep parity
    // honest as the legacy UI evolves.
    expect(V1_COMMANDS.length).toBe(32);
  });
});
