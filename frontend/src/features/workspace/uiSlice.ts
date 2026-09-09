import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { BackendCashShift, BackendPaymentMethod, BackendProduct, BackendWorkstationGroup, Reservation } from "../../api";
import type { Section } from "../../types";
import type { RootState } from "../../app/store";

export type Panel = "pc" | "client" | "new-client" | "deposit" | "booking" | "booking-edit" | "tariff" | "product" | "sale" | "discount" | "workstation" | "group" | "payment-method" | "cash-open" | "cash-movement" | "cash-close" | null;

type UiState = {
  section: Section;
  group: string;
  selectedPcId: string | null;
  selectedClientId: string | null;
  selectedGroup: BackendWorkstationGroup | null;
  selectedPaymentMethod: BackendPaymentMethod | null;
  selectedBooking: Reservation | null;
  selectedCashShift: BackendCashShift | null;
  selectedProduct: BackendProduct | null;
  saleInitialProduct: BackendProduct | null;
  panel: Panel;
  bookingWorkstationId: string | undefined;
  depositBonusOnly: boolean;
  search: string;
  catalogRefreshKey: number;
  settingsRefreshKey: number;
  bookingRefreshKey: number;
};

const initialState: UiState = {
  section: "dashboard",
  group: "Все зоны",
  selectedPcId: null,
  selectedClientId: null,
  selectedGroup: null,
  selectedPaymentMethod: null,
  selectedBooking: null,
  selectedCashShift: null,
  selectedProduct: null,
  saleInitialProduct: null,
  panel: null,
  bookingWorkstationId: undefined,
  depositBonusOnly: false,
  search: "",
  catalogRefreshKey: 0,
  settingsRefreshKey: 0,
  bookingRefreshKey: 0,
};

const uiSlice = createSlice({
  name: "ui",
  initialState,
  reducers: {
    setSection(state, action: PayloadAction<Section>) { state.section = action.payload; },
    setGroup(state, action: PayloadAction<string>) { state.group = action.payload; },
    setSearch(state, action: PayloadAction<string>) { state.search = action.payload; },
    openPanel(state, action: PayloadAction<Panel>) { state.panel = action.payload; },
    closePanel(state) { state.panel = null; },
    openPc(state, action: PayloadAction<string>) { state.selectedPcId = action.payload; state.selectedClientId = null; state.panel = "pc"; },
    openClient(state, action: PayloadAction<string>) { state.selectedClientId = action.payload; state.selectedPcId = null; state.selectedBooking = null; state.panel = "client"; },
    openNewClient(state) { state.selectedPcId = null; state.selectedClientId = null; state.selectedBooking = null; state.panel = "new-client"; },
    openDeposit(state, action: PayloadAction<{ clientId?: string | null; bonusOnly?: boolean } | undefined>) { state.panel = "deposit"; state.selectedPcId = null; state.selectedClientId = action.payload?.clientId ?? null; state.depositBonusOnly = Boolean(action.payload?.bonusOnly); },
    openBooking(state, action: PayloadAction<string | undefined>) { state.panel = "booking"; state.selectedPcId = null; state.selectedClientId = null; state.selectedBooking = null; state.bookingWorkstationId = action.payload; },
    openSale(state, action: PayloadAction<{ pcId?: string | null; product?: BackendProduct | null } | undefined>) { state.selectedPcId = action.payload?.pcId ?? null; state.selectedClientId = null; state.saleInitialProduct = action.payload?.product ?? null; state.panel = "sale"; },
    openWorkstationEditor(state) { state.panel = "workstation"; },
    openNewWorkstation(state) { state.selectedPcId = null; state.panel = "workstation"; },
    openBookingEdit(state, action: PayloadAction<Reservation>) { state.panel = "booking-edit"; state.selectedPcId = null; state.selectedClientId = null; state.selectedBooking = action.payload; },
    openCashShift(state) { state.selectedCashShift = null; state.panel = "cash-open"; },
    openCashMovement(state, action: PayloadAction<BackendCashShift>) { state.selectedCashShift = action.payload; state.panel = "cash-movement"; },
    openCashClose(state, action: PayloadAction<BackendCashShift>) { state.selectedCashShift = action.payload; state.panel = "cash-close"; },
    selectGroup(state, action: PayloadAction<BackendWorkstationGroup | null>) { state.selectedGroup = action.payload; state.panel = "group"; },
    selectPaymentMethod(state, action: PayloadAction<BackendPaymentMethod | null>) { state.selectedPaymentMethod = action.payload; state.panel = "payment-method"; },
    selectProduct(state, action: PayloadAction<BackendProduct | null>) { state.selectedProduct = action.payload; state.panel = "product"; },
    bumpBookingRefresh(state) { state.bookingRefreshKey += 1; },
    bumpCatalogRefresh(state) { state.catalogRefreshKey += 1; },
    bumpSettingsRefresh(state) { state.settingsRefreshKey += 1; },
  },
});

export const {
  setSection, setGroup, setSearch, openPanel, closePanel, openPc, openClient, openNewClient,
  openDeposit, openBooking, openSale, openWorkstationEditor, openNewWorkstation, openBookingEdit, openCashShift, openCashMovement,
  openCashClose, selectGroup, selectPaymentMethod, selectProduct, bumpBookingRefresh,
  bumpCatalogRefresh, bumpSettingsRefresh,
} = uiSlice.actions;
export const selectUi = (state: RootState) => state.ui;
export default uiSlice.reducer;
