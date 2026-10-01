import type { Workstation } from "../../types";
import type { V2DepositTarget } from "../workspace/uiSlice";

export function findActiveV2DepositTarget(
  clientId: string,
  workstations: readonly Workstation[],
): V2DepositTarget | undefined {
  const workstation = workstations.find((item) =>
    item.clientId === clientId
      && item.status === "busy"
      && item.sessionMode === "v2_local_ledger"
      && Boolean(item.sessionId)
      && Boolean(item.deviceId));
  if (!workstation?.sessionId || !workstation.deviceId) {
    return undefined;
  }

  return {
    sessionId: workstation.sessionId,
    deviceId: workstation.deviceId,
    workstationName: workstation.name,
  };
}
