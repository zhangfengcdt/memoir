import { describe, expect, it } from "vitest";
import { relativeTime } from "./time";

const now = new Date("2026-04-24T12:00:00Z");
const secondsAgo = (n: number) => Math.floor(now.getTime() / 1000) - n;

describe("relativeTime", () => {
  it('"just now" for very recent', () => {
    expect(relativeTime(secondsAgo(10), now)).toBe("just now");
  });

  it("minutes for < 60m", () => {
    expect(relativeTime(secondsAgo(5 * 60), now)).toBe("5m ago");
  });

  it("hours for 1-23h", () => {
    expect(relativeTime(secondsAgo(2 * 3600), now)).toBe("2h ago");
  });

  it("yesterday for 1d", () => {
    expect(relativeTime(secondsAgo(26 * 3600), now)).toBe("yesterday");
  });

  it("days for 2-6d", () => {
    expect(relativeTime(secondsAgo(3 * 86400), now)).toBe("3d ago");
  });

  it("weeks for 7-29d", () => {
    expect(relativeTime(secondsAgo(10 * 86400), now)).toBe("1w ago");
  });

  it("calendar date for >= 30d, same year", () => {
    const result = relativeTime(secondsAgo(60 * 86400), now);
    expect(result).toMatch(/^\w{3} \d{1,2}$/); // e.g. "Feb 23"
  });

  it("includes year for different calendar year", () => {
    const twoYearsAgo = secondsAgo(730 * 86400);
    const result = relativeTime(twoYearsAgo, now);
    expect(result).toMatch(/\b\d{4}\b/);
  });
});
