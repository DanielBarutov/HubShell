import type { Workstation } from "../../types";
import type { DepositTarget } from "../workspace/uiSlice";

export function findActiveDepositTarget(
  clientId: string,
  workstations: readonly Workstation[],
): DepositTarget | undefined {
  const targets = findActiveDepositTargets(clientId, workstations);
  return targets.length === 1 ? targets[0] : undefined;
}

export function findActiveDepositTargets(
  clientId: string,
  workstations: readonly Workstation[],
): DepositTarget[] {
  return workstations.flatMap((item) => {
    if (
      item.clientId !== clientId
      || item.status !== "busy"
      || !item.sessionId
      || !item.deviceId
    ) {
      return [];
    }

    return [{
      sessionId: item.sessionId,
      deviceId: item.deviceId,
      workstationName: item.name,
    }];
  });
}
