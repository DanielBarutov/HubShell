import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { api } from "../../app/api";
import { LIVE_MODE } from "../../app/config";
import { toUiClient, toUiWorkstation } from "../../adapters";
import { clients as demoClients, workstations as demoWorkstations } from "../../data";
import { ApiError } from "../../api";
import type {
  BackendAuditEvent,
  BackendCashShift,
  BackendProductSale,
  BackendWorkstationGroup,
  Reservation,
} from "../../api";
import type { Client, Workstation } from "../../types";
import type { RootState } from "../../app/store";

export type WorkspaceState = {
  workstations: Workstation[];
  groups: BackendWorkstationGroup[];
  clients: Client[];
  reservations: Reservation[];
  auditEvents: BackendAuditEvent[];
  revenueCents: number | null;
  revenueChargeCount: number;
  cashShifts: BackendCashShift[];
  reviewSales: BackendProductSale[];
  loading: boolean;
  error: string | null;
  lastUpdatedAt: string | null;
};

type WorkspaceSnapshot = Omit<WorkspaceState, "loading" | "error" | "lastUpdatedAt">;

const initialState: WorkspaceState = {
  workstations: LIVE_MODE ? [] : demoWorkstations,
  groups: [],
  clients: LIVE_MODE ? [] : demoClients,
  reservations: [],
  auditEvents: [],
  revenueCents: null,
  revenueChargeCount: 0,
  cashShifts: [],
  reviewSales: [],
  loading: LIVE_MODE,
  error: null,
  lastUpdatedAt: null,
};

export const refreshWorkspace = createAsyncThunk<WorkspaceSnapshot | void, void, { rejectValue: string }>(
  "workspace/refresh",
  async (_, { rejectWithValue }) => {
    if (!LIVE_MODE) {
      return;
    }
    try {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const tomorrow = new Date(today);
      tomorrow.setDate(tomorrow.getDate() + 1);
      const [backendPcs, backendClients, activeSessions, todayReservations, auditEvents, revenue, cashShifts, groups, sales, tariffs] = await Promise.all([
        api.listWorkstations(),
        api.listClients(),
        api.listSessions(true),
        api.listReservations(today.toISOString(), tomorrow.toISOString()),
        api.listAuditEvents(),
        api.getRevenue(today.toISOString(), tomorrow.toISOString()),
        api.listCashShifts(),
        api.listWorkstationGroups(),
        api.listSales({ limit: 100 }),
        api.listTariffs(),
      ]);
      const sessionsByWorkstation = new Map(activeSessions.map((session) => [session.workstation_id, session]));
      const groupNames = new Map(groups.map((group) => [group.id, group.name]));
      const clientNames = new Map(backendClients.map((client) => [client.id, client.nickname]));
      const tariffNames = new Map(tariffs.map((tariff) => [tariff.id, tariff.name]));
      return {
        workstations: backendPcs.map((pc) => {
          const session = sessionsByWorkstation.get(pc.id);
          return toUiWorkstation(
            pc,
            session,
            pc.group_id ? groupNames.get(pc.group_id) : undefined,
            session?.client_id ? clientNames.get(session.client_id) : undefined,
            session?.tariff_id ? tariffNames.get(session.tariff_id) : undefined,
          );
        }),
        groups,
        clients: backendClients.map(toUiClient),
        reservations: todayReservations,
        auditEvents,
        revenueCents: revenue.amount_cents,
        revenueChargeCount: revenue.charge_count,
        cashShifts,
        reviewSales: sales.filter((sale) => sale.status === "needs_review"),
      } satisfies WorkspaceSnapshot;
    } catch (error) {
      return rejectWithValue(error instanceof ApiError ? error.message : "Не удалось обновить рабочие данные");
    }
  },
);

export const persistWorkstationPositions = createAsyncThunk<void, Array<{ workstationId: string; position: number }>, { rejectValue: string }>(
  "workspace/persistWorkstationPositions",
  async (changes, { getState, rejectWithValue }) => {
    const current = (getState() as RootState).workspace.workstations;
    const byId = new Map(current.map((workstation) => [workstation.id, workstation]));
    try {
      await Promise.all(changes.filter((change) => byId.has(change.workstationId) && Number.isInteger(change.position) && change.position > 0).map((change) => {
        const workstation = byId.get(change.workstationId);
        if (!workstation) return Promise.resolve();
        return api.updateWorkstation(workstation.id, {
          name: workstation.name,
          mac_address: workstation.macAddress ?? null,
          group_id: workstation.groupId ?? null,
          position: change.position,
        });
      }));
    } catch (error) {
      return rejectWithValue(error instanceof ApiError ? error.message : "Не удалось сохранить расстановку мест");
    }
  },
);

const workspaceSlice = createSlice({
  name: "workspace",
  initialState,
  reducers: {
    clearWorkspace(state) {
      state.workstations = [];
      state.groups = [];
      state.clients = [];
      state.reservations = [];
      state.auditEvents = [];
      state.cashShifts = [];
      state.reviewSales = [];
      state.revenueCents = null;
      state.revenueChargeCount = 0;
      state.error = null;
      state.loading = true;
    },
    replaceWorkstations(state, action: { payload: Workstation[] }) {
      state.workstations = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(refreshWorkspace.pending, (state) => {
        state.loading = true;
      })
      .addCase(refreshWorkspace.fulfilled, (state, action) => {
        if (action.payload) {
          state.workstations = action.payload.workstations;
          state.groups = action.payload.groups;
          state.clients = action.payload.clients;
          state.reservations = action.payload.reservations;
          state.auditEvents = action.payload.auditEvents;
          state.revenueCents = action.payload.revenueCents;
          state.revenueChargeCount = action.payload.revenueChargeCount;
          state.cashShifts = action.payload.cashShifts;
          state.reviewSales = action.payload.reviewSales;
          state.lastUpdatedAt = new Date().toISOString();
        }
        state.loading = false;
        state.error = null;
      })
      .addCase(refreshWorkspace.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload ?? "Не удалось обновить рабочие данные";
      });
  },
});

export const { clearWorkspace, replaceWorkstations } = workspaceSlice.actions;
export const selectWorkspace = (state: RootState) => state.workspace;
export default workspaceSlice.reducer;
