import { describe, expect, it } from "vitest";
import { listCommands, unavailableReason } from "./registry";

const byName = (name: string) => {
  const def = listCommands().find((d) => d.name === name);
  if (!def) throw new Error(`no command ${name}`);
  return def;
};

const WRITABLE_LOCAL = { writable: true, useLLM: true, profile: "local" as const };
const READONLY_LOCAL = { writable: false, useLLM: false, profile: "local" as const };
const CLOUD = { writable: false, useLLM: false, profile: "cloud" as const };

describe("command availability", () => {
  it("a writable local session with LLM can run everything", () => {
    for (const def of listCommands()) {
      expect(unavailableReason(def, WRITABLE_LOCAL)).toBeNull();
    }
  });

  it("read-only hides every mutating command, in any profile", () => {
    const mutating = listCommands().filter((d) => d.tags.includes("mutating"));
    expect(mutating.map((d) => d.name).sort()).toEqual(
      ["checkout", "forget", "merge", "remember", "time-travel"].sort(),
    );
    for (const def of mutating) {
      expect(unavailableReason(def, READONLY_LOCAL)).toMatch(/read-only/);
    }
    // On the cloud, /checkout is a read (it pins `ref`); the rest stay blocked.
    for (const def of mutating) {
      if (def.name === "checkout") expect(unavailableReason(def, CLOUD)).toBeNull();
      else expect(unavailableReason(def, CLOUD)).toMatch(/read-only/);
    }
  });

  it("LLM commands need useLLM", () => {
    expect(unavailableReason(byName("recall"), { ...WRITABLE_LOCAL, useLLM: false })).toMatch(
      /LLM/,
    );
    expect(unavailableReason(byName("recall"), WRITABLE_LOCAL)).toBeNull();
  });

  it("the cloud profile hides commands whose endpoints it does not serve", () => {
    for (const name of ["stats", "timeline", "places", "location", "proof", "verify", "blame"]) {
      expect(unavailableReason(byName(name), CLOUD)).toMatch(/memoir-cloud/);
      // ...but they are fine on a read-only local server.
      expect(unavailableReason(byName(name), READONLY_LOCAL)).toBeNull();
    }
  });

  it("the cloud profile keeps the read commands it can serve", () => {
    for (const name of ["connect", "refresh", "status", "commits", "outline", "map", "diff", "branches", "help"]) {
      expect(unavailableReason(byName(name), CLOUD)).toBeNull();
    }
  });
});
