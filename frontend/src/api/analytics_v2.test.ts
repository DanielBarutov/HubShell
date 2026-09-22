import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GameClubApi } from "./index";

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("analytics v2 read API", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn()));
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("requests the expanded dashboard with all confirmed filters", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ api_version: "v2" }));

    await new GameClubApi("http://backend/api/v1").getAnalyticsDashboard({
      startAt: "2026-09-20T21:00:00.000Z",
      endAt: "2026-09-21T21:00:00.000Z",
      categoryKey: "drinks",
      productKey: "product-1",
      operatorKey: "operator-1",
      comparison: true,
    });

    expect(fetchMock.mock.calls[0]?.[0]).toContain("http://backend/api/v2/analytics/dashboard?");
    expect(fetchMock.mock.calls[0]?.[0]).toContain("category_key=drinks");
    expect(fetchMock.mock.calls[0]?.[0]).toContain("product_key=product-1");
    expect(fetchMock.mock.calls[0]?.[0]).toContain("operator_key=operator-1");
    expect(fetchMock.mock.calls[0]?.[0]).toContain("comparison=previous_equal_period");
  });

  it("keeps drill-down on the v2 endpoint", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ state: "empty", items: [] }));

    await new GameClubApi("http://backend/api/v1").getAnalyticsDrillDown({
      startAt: "2026-09-20T21:00:00.000Z",
      endAt: "2026-09-21T21:00:00.000Z",
      operationType: "return",
    });

    expect(fetchMock.mock.calls[0]?.[0]).toContain("/api/v2/analytics/drill-down?");
    expect(fetchMock.mock.calls[0]?.[0]).toContain("operation_type=return");
  });
});
