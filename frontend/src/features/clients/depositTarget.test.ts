import { describe, expect, it } from "vitest";
import type { Workstation } from "../../types";
import {
  findActiveDepositTarget,
  findActiveDepositTargets,
} from "./depositTarget";

const activeWorkstation: Workstation = {
  id: "pc-1",
  name: "VIP-01",
  group: "VIP",
  status: "busy",
  clientId: "client-1",
  sessionId: "session-1",
  deviceId: "device-1",
};

describe("findActiveDepositTarget", () => {
  it("routes a client-card deposit to the client's active session", () => {
    expect(findActiveDepositTarget("client-1", [activeWorkstation])).toEqual({
      sessionId: "session-1",
      deviceId: "device-1",
      workstationName: "VIP-01",
    });
  });

  it("does not route deposits to another client", () => {
    const anotherClient = { ...activeWorkstation, clientId: "client-2" };

    expect(
      findActiveDepositTarget("client-1", [anotherClient]),
    ).toBeUndefined();
  });

  it("does not select incomplete or non-busy sessions", () => {
    const missingDevice = { ...activeWorkstation, deviceId: undefined };
    const notBusy = { ...activeWorkstation, status: "online" as const };

    expect(
      findActiveDepositTarget("client-1", [missingDevice, notBusy]),
    ).toBeUndefined();
  });

  it("refuses to choose an arbitrary target when the client has multiple active sessions", () => {
    const secondSession = {
      ...activeWorkstation,
      id: "pc-2",
      name: "VIP-02",
      sessionId: "session-2",
      deviceId: "device-2",
    };

    expect(
      findActiveDepositTarget("client-1", [activeWorkstation, secondSession]),
    ).toBeUndefined();
    expect(findActiveDepositTargets("client-1", [activeWorkstation, secondSession])).toHaveLength(2);
  });
});
