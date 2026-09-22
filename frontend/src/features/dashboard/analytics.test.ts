import { describe, expect, it } from "vitest";
import { ApiError } from "../../api";
import {
  getAnalyticsDataState,
  getAnalyticsPeriodBounds,
  getComparisonPeriod,
  productCategoryLabel,
} from "./analytics";

describe("analytics period helpers", () => {
  it("builds half-open day bounds in Europe/Moscow instead of UTC midnight", () => {
    expect(getAnalyticsPeriodBounds("2026-09-21", "2026-09-21")).toEqual({
      startAt: "2026-09-20T21:00:00.000Z",
      endAt: "2026-09-21T21:00:00.000Z",
    });
  });

  it("keeps comparison period equal in duration and immediately before the selected period", () => {
    expect(getComparisonPeriod("2026-09-20T21:00:00.000Z", "2026-09-23T21:00:00.000Z", new Date("2026-09-24T00:00:00.000Z"))).toEqual({
      startAt: "2026-09-17T21:00:00.000Z",
      endAt: "2026-09-20T21:00:00.000Z",
      isPartial: false,
    });
  });
});

describe("analytics data states", () => {
  it.each([
    [{ loading: true }, "loading"],
    [{ error: new ApiError(403, "Недостаточно прав", "permission_denied") }, "permission_denied"],
    [{ error: new ApiError(500, "Ошибка") }, "error"],
    [{ overview: null, isEmpty: true }, "empty"],
    [{ metricAvailable: false }, "not_available"],
    [{ metricCalculated: false }, "not_calculated"],
    [{ partial: true }, "partial"],
  ] as const)("classifies %j as %s", (input, expected) => {
    expect(getAnalyticsDataState(input)).toBe(expected);
  });
});

describe("analytics report labels", () => {
  it("replaces technical category keys with readable management labels", () => {
    expect(productCategoryLabel("drinks")).toBe("Напитки");
    expect(productCategoryLabel("unknown")).toBe("Без категории");
    expect(productCategoryLabel("Игровые аксессуары")).toBe("Игровые аксессуары");
  });
});
