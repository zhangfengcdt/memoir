import { describe, expect, it } from "vitest";
import { initialConfig } from "./configSlice";
import type { RuntimeConfig } from "../config/runtime";

const LOCAL: RuntimeConfig = {
  apiBase: "",
  store: null,
  ref: null,
  readonly: null,
  profile: "local",
  backUrl: null,
  injected: false,
  features: null,
};

const CLOUD: RuntimeConfig = {
  apiBase: "/feng-zhang/demo/api",
  store: "feng-zhang/demo",
  ref: "main",
  readonly: true,
  profile: "cloud",
  backUrl: "/feng-zhang/demo",
  injected: true,
  features: null,
};

describe("initialConfig", () => {
  it("local: reads readonly/usellm from the URL, writable by default", () => {
    expect(initialConfig(LOCAL, "http://x/?store=/s")).toEqual({
      writable: true,
      useLLM: false,
      profile: "local",
      backUrl: null,
      features: null,
    });
    expect(initialConfig(LOCAL, "http://x/?store=/s&readonly=1&usellm=1")).toEqual({
      writable: false,
      useLLM: true,
      profile: "local",
      backUrl: null,
      features: null,
    });
  });

  it("cloud: the injected readonly wins over the URL and LLM is always off", () => {
    expect(initialConfig(CLOUD, "http://x/h/n/workspace?readonly=0&usellm=1")).toEqual({
      writable: false,
      useLLM: false,
      profile: "cloud",
      backUrl: "/feng-zhang/demo",
      features: null,
    });
  });

  it("an injected readonly=false makes a local session writable regardless of the URL", () => {
    expect(initialConfig({ ...LOCAL, readonly: false, injected: true }, "http://x/?readonly=1").writable).toBe(true);
  });
});
