import { describe, expect, it } from "vitest";
import { listCommands } from "./registry";

/**
 * Parity inventory of v1 (legacy ``core-ui.js``) commands.
 *
 * Sourced verbatim from ``availableCommands`` in
 * ``src/memoir/ui/static/js/core-ui.js`` (~line 7180). Each entry below
 * lists either ``[name]`` for a v1 command without aliases, or
 * ``[name, ...aliases]``. The test asserts that every name and every
 * alias resolves to *some* registered v2 command — placeholder or real.
 *
 * If you remove a command from v1 or add one, update this list and run
 * the test. If you add a *new* v2 command (no v1 counterpart), no
 * change here is needed.
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
