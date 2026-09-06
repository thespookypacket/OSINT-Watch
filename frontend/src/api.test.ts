import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, severityLabel, timeAgo } from "./api";
import { categories } from "./types";
afterEach(() => vi.unstubAllGlobals());
describe("API client and hazard meanings", () => {
  it("keeps the three fire layers distinct", () => {
    expect(
      new Set([
        categories.wildfire_perimeter.label,
        categories.satellite_hotspot.label,
        categories.fire_weather.label,
      ]).size,
    ).toBe(3);
    expect(severityLabel(0)).toBe("Unknown");
    expect(timeAgo(null)).toBe("Never collected");
  });
  it("preserves structured validation errors and credentials", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            fields: [{ field: "geometry", message: "Invalid coordinate" }],
          },
        }),
        { status: 422 },
      ),
    );
    vi.stubGlobal("fetch", fetcher);
    await expect(api("/assets")).rejects.toMatchObject({
      message: "geometry: Invalid coordinate",
      status: 422,
    });
    expect(fetcher.mock.calls[0][1].credentials).toBe("same-origin");
  });
  it("handles a gateway failure without leaking HTML", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response("<html>upstream error</html>", { status: 502 }),
        ),
    );
    await expect(api("/events")).rejects.toBeInstanceOf(ApiError);
  });
});
