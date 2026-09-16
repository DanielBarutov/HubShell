import { describe, expect, it } from "vitest";
import { normalizePhoneQuery } from "./normalizers";

describe("normalizePhoneQuery", () => {
  it.each([
    ["+7 (999) 123-45-67", "79991234567"],
    ["8 999 123 45 67", "79991234567"],
    ["9991234567", "79991234567"],
    ["79991234567", "79991234567"],
    ["", ""],
  ])("приводит телефон %s к серверному поисковому формату %s", (input, expected) => {
    expect(normalizePhoneQuery(input)).toBe(expected);
  });
});
