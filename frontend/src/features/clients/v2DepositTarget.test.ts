import { describe, expect, it } from "vitest";
import type { Workstation } from "../../types";
import { findActiveV2DepositTarget } from "./v2DepositTarget";

const activeV2Workstation: Workstation = {
  id: "pc-1",
  name: "VIP-01",
  group: "VIP",
  status: "busy",
  clientId: "client-1",
  sessionId: "session-1",
  deviceId: "device-1",
  sessionMode: "v2_local_ledger",
};

describe("findActiveV2DepositTarget", () => {
  it("routes a client-card deposit to the client's active V2 session", () => {
    expect(findActiveV2DepositTarget("client-1", [activeV2Workstation])).toEqual({
      sessionId: "session-1",
      deviceId: "device-1",
      workstationName: "VIP-01",
    });
  });

  it("does not route deposits to another client or to V1 sessions", () => {
    const anotherClient = { ...activeV2Workstation, clientId: "client-2" };
    const v1Workstation = {
      ...activeV2Workstation,
      sessionMode: "v1_server_owned" as const,
    };

    expect(
      findActiveV2DepositTarget("client-1", [anotherClient, v1Workstation]),
    ).toBeUndefined();
  });

  it("does not select incomplete or non-busy sessions", () => {
    const missingDevice = { ...activeV2Workstation, deviceId: undefined };
    const notBusy = { ...activeV2Workstation, status: "online" as const };

    expect(
      findActiveV2DepositTarget("client-1", [missingDevice, notBusy]),
    ).toBeUndefined();
  });
});
