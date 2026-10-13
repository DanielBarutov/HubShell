import { useAppDispatch, useAppSelector } from "./hooks";
import { useReduxApi } from "./reduxApi";
import { LIVE_MODE } from "./config";
import { bumpBookingRefresh, closePanel, openBooking, openDeposit, openSale, openWorkstationEditor, type DepositTarget } from "../features/workspace/uiSlice";
import { refreshWorkspace, selectWorkspace } from "../features/workspace/workspaceSlice";
import { selectUi } from "../features/workspace/uiSlice";
import { BookingEditPanel, BookingPanel } from "../features/bookings/BookingPanels";
import { ClientPanel, NewClientPanel } from "../features/clients/ClientsScreen";
import { findActiveDepositTarget } from "../features/clients/depositTarget";
import { DepositPanel } from "../features/clients/DepositPanel";
import { DiscountPanel, ProductPanel, TariffPanel } from "../features/catalog/CatalogScreen";
import { SaleWorkspace } from "../features/catalog/SaleWorkspace";
import { CashClosePanel, CashMovementPanel, CashOpenPanel } from "../features/cash/CashScreen";
import { GroupSettingsPanel, PaymentMethodPanel } from "../features/settings/SettingsScreen";
import { PcPanel } from "../features/workstations/PcPanel";
import { WorkstationPanel as WorkstationEditor } from "../features/workstations/WorkstationPanel";

export function PanelHost() {
  const dispatch = useAppDispatch();
  const ui = useAppSelector(selectUi);
  const workspace = useAppSelector(selectWorkspace);
  const api = useReduxApi();
  const selectedPc = ui.selectedPcId ? workspace.workstations.find((pc) => pc.id === ui.selectedPcId) ?? null : null;
  const selectedClient = ui.selectedClientId ? workspace.clients.find((client) => client.id === ui.selectedClientId) ?? null : null;
  const selectedPcClient = selectedPc?.clientId
    ? workspace.clients.find((client) => client.id === selectedPc.clientId) ?? null
    : null;
  const openCashShifts = workspace.cashShifts.filter((shift) => shift.status === "open");
  const cashShiftId = openCashShifts.length === 1 ? openCashShifts[0].id : undefined;
  const close = () => dispatch(closePanel());
  const refresh = async (closePanel = true) => {
    await dispatch(refreshWorkspace());
    dispatch(bumpBookingRefresh());
    if (closePanel) close();
  };
  const openClientDeposit = (client = selectedClient, bonusOnly = false, selectedTarget?: DepositTarget) => {
    const target = selectedTarget
      ?? (client && !bonusOnly
        ? findActiveDepositTarget(client.id, workspace.workstations)
        : undefined);
    dispatch(openDeposit({ clientId: client?.id, bonusOnly, target: target }));
  };

  if (!ui.panel) return null;

  return <>
    {ui.panel !== "sale" && <div className="panel-overlay fixed inset-0 z-40 bg-black/50" aria-hidden="true" onClick={close} />}
    {ui.panel !== "sale" && <aside className="right-panel open fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-y-auto border-l border-primary/30! bg-base-100/95! text-base-content! shadow-[0_0_32px_rgba(49,217,120,0.12),-14px_0_38px_rgba(0,0,0,0.25)] backdrop-blur-xl" role="dialog" aria-modal aria-label="Контекстная панель">
      <div className="[&_.booking-form>label]:flex [&_.booking-form>label]:flex-col [&_.booking-form>label]:gap-1 [&_.booking-form>label]:text-sm [&_.form-grid-two>label]:flex [&_.form-grid-two>label]:flex-col [&_.form-grid-two>label]:gap-1 [&_.form-grid-two>label]:text-sm [&_.schedule-fields>label]:flex [&_.schedule-fields>label]:flex-col [&_.schedule-fields>label]:gap-1 [&_.schedule-fields>label]:text-sm [&_.schedule-toggle>label]:flex [&_.schedule-toggle>label]:flex-col [&_.schedule-toggle>label]:gap-0.5 [&_.schedule-toggle>label]:text-sm [&_.amount-field]:flex [&_.amount-field]:flex-col [&_.amount-field]:gap-1 [&_.amount-field]:text-sm [&_.client-result]:border-primary/20! [&_.client-result]:bg-base-200/70! [&_.detail-row]:border [&_.detail-row]:border-primary/15! [&_.detail-row]:bg-base-200/70! [&_.guest-mode-card]:border-primary/20! [&_.guest-mode-card]:bg-base-200/70! [&_.search-hint]:border-primary/20! [&_.search-hint]:bg-base-200/70!">
      {ui.panel === "pc" && selectedPc && <PcPanel pc={selectedPc} client={selectedPcClient ?? undefined} onClose={close} onEdit={() => dispatch(openWorkstationEditor())} onBook={() => dispatch(openBooking(selectedPc.id))} onDeposit={openClientDeposit} onOpenSale={() => dispatch(openSale({ pcId: selectedPc.id, clientId: selectedPc.clientId }))} onSessionChanged={refresh} api={LIVE_MODE ? api : undefined} />}
      {ui.panel === "client" && selectedClient && <ClientPanel client={selectedClient} clientGroups={workspace.clientGroups} api={LIVE_MODE ? api : undefined} onClose={close} onSaved={refresh} onDeposit={() => openClientDeposit()} onBonusDeposit={() => openClientDeposit(selectedClient, true)} />}
      {ui.panel === "new-client" && LIVE_MODE && <NewClientPanel api={api} clientGroups={workspace.clientGroups} onClose={close} onSaved={refresh} />}
      {ui.panel === "deposit" && <DepositPanel initialClient={selectedClient ?? undefined} bonusOnly={ui.depositBonusOnly} target={ui.depositTarget ?? undefined} cashShiftId={cashShiftId} workstations={workspace.workstations} onClose={close} onCompleted={refresh} clients={workspace.clients} api={LIVE_MODE ? api : undefined} />}
      {ui.panel === "booking" && <BookingPanel initialWorkstationId={ui.bookingWorkstationId} onClose={close} pcs={workspace.workstations.filter((place) => place.equipmentType !== "xbox")} clients={workspace.clients} api={LIVE_MODE ? api : undefined} onCreated={refresh} />}
      {ui.panel === "booking-edit" && ui.selectedBooking && <BookingEditPanel reservation={ui.selectedBooking} clients={workspace.clients} onClose={close} pcs={workspace.workstations.filter((place) => place.equipmentType !== "xbox")} api={LIVE_MODE ? api : undefined} onSaved={refresh} />}
      {ui.panel === "tariff" && LIVE_MODE && <TariffPanel api={api} groups={workspace.groups} onClose={close} onSaved={refresh} />}
      {ui.panel === "product" && LIVE_MODE && <ProductPanel api={api} product={ui.selectedProduct ?? undefined} categories={workspace.productCategories} onClose={close} onSaved={refresh} />}
      {ui.panel === "discount" && LIVE_MODE && <DiscountPanel api={api} onClose={close} onSaved={refresh} />}
      {ui.panel === "workstation" && LIVE_MODE && <WorkstationEditor api={api} workstation={selectedPc ?? undefined} groups={workspace.groups} onClose={close} onSaved={refresh} />}
      {ui.panel === "group" && LIVE_MODE && <GroupSettingsPanel api={api} group={ui.selectedGroup ?? undefined} onClose={close} onSaved={refresh} />}
      {ui.panel === "payment-method" && LIVE_MODE && <PaymentMethodPanel api={api} method={ui.selectedPaymentMethod ?? undefined} onClose={close} onSaved={refresh} />}
      {ui.panel === "cash-open" && LIVE_MODE && <CashOpenPanel api={api} onClose={close} onSaved={refresh} />}
      {ui.panel === "cash-movement" && LIVE_MODE && ui.selectedCashShift && <CashMovementPanel api={api} shift={ui.selectedCashShift} onClose={close} onSaved={refresh} />}
      {ui.panel === "cash-close" && LIVE_MODE && ui.selectedCashShift && <CashClosePanel api={api} shift={ui.selectedCashShift} onClose={close} onSaved={refresh} />}
      </div>
    </aside>}
    {ui.panel === "sale" && <SaleWorkspace api={LIVE_MODE ? api : undefined} pc={selectedPc} initialClient={selectedClient} initialProduct={ui.saleInitialProduct} initialTab={ui.saleInitialTab} clients={workspace.clients} cashShifts={workspace.cashShifts} tariffs={workspace.tariffs} products={workspace.products} categories={workspace.productCategories} onClose={close} onSaved={refresh} />}
  </>;
}
