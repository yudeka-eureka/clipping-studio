import { describe, expect, it } from "vitest";

import { formatTimecode } from "@/lib/timecode";

describe("formatTimecode", () => {
  it("shows the default in point as 14:10.20", () => {
    expect(formatTimecode((14 * 60 + 10) * 1000 + 200)).toBe("14:10.20");
  });

  it("moves by 50 ms per nudge", () => {
    expect(formatTimecode((14 * 60 + 52) * 1000 + 650 + 50)).toBe("14:52.70");
  });

  it("never goes below zero", () => {
    expect(formatTimecode(-50)).toBe("00:00.00");
  });
});
