import { useAppDispatch, useAppSelector } from "./hooks";
import { useReduxApi } from "./reduxApi";
import { LIVE_MODE } from "./config";
import { bumpBookingRefresh, closePanel, openBooking, openDeposit, openSale, openWorkstationEditor } from "../features/workspace/uiSlice";
import { refreshWorkspace, selectWorkspace } from "../features/workspace/workspaceSlice";
import { selectUi } from "../features/workspace/uiSlice";
import { BookingEditPanel, BookingPanel } from "../features/bookings/BookingPanels";
import { ClientPanel, NewClientPanel } from "../features/clients/ClientsScreen";
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
  const close = () => dispatch(closePanel());
  const refresh = async () => {
    await dispatch(refreshWorkspace());
    dispatch(bumpBookingRefresh());
    close();
  };
  const openClientDeposit = (client = selectedClient, bonusOnly = false) => dispatch(openDeposit({ clientId: client?.id, bonusOnly }));

  if (!ui.panel) return null;

  return <>
    {ui.panel !== "sale" && <div className="panel-overlay" aria-hidden="true" onClick={close} />}
    {ui.panel !== "sale" && <aside className="right-panel open" role="dialog" aria-modal aria-label="Контекстная панель">
      {ui.panel === "pc" && selectedPc && <PcPanel pc={selectedPc} client={selectedPcClient ?? undefined} workstations={workspace.workstations} tariffs={workspace.tariffs} onClose={close} onEdit={() => dispatch(openWorkstationEditor())} onBook={() => dispatch(openBooking(selectedPc.id))} onDeposit={openClientDeposit} onOpenSale={() => dispatch(openSale({ pcId: selectedPc.id, clientId: selectedPc.clientId }))} onSessionChanged={refresh} api={LIVE_MODE ? api : undefined} />}
      {ui.panel === "client" && selectedClient && <ClientPanel client={selectedClient} clientGroups={workspace.clientGroups} api={LIVE_MODE ? api : undefined} onClose={close} onSaved={refresh} onDeposit={() => openClientDeposit()} onBonusDeposit={() => openClientDeposit(selectedClient, true)} />}
      {ui.panel === "new-client" && LIVE_MODE && <NewClientPanel api={api} clientGroups={workspace.clientGroups} onClose={close} onSaved={refresh} />}
      {ui.panel === "deposit" && <DepositPanel initialClient={selectedClient ?? undefined} bonusOnly={ui.depositBonusOnly} onClose={close} onCompleted={refresh} clients={workspace.clients} api={LIVE_MODE ? api : undefined} />}
      {ui.panel === "booking" && <BookingPanel initialWorkstationId={ui.bookingWorkstationId} onClose={close} pcs={workspace.workstations} api={LIVE_MODE ? api : undefined} onCreated={refresh} />}
      {ui.panel === "booking-edit" && ui.selectedBooking && <BookingEditPanel reservation={ui.selectedBooking} clients={workspace.clients} onClose={close} pcs={workspace.workstations} api={LIVE_MODE ? api : undefined} onSaved={refresh} />}
      {ui.panel === "tariff" && LIVE_MODE && <TariffPanel api={api} groups={workspace.groups} onClose={close} onSaved={refresh} />}
      {ui.panel === "product" && LIVE_MODE && <ProductPanel api={api} product={ui.selectedProduct ?? undefined} categories={workspace.productCategories} onClose={close} onSaved={refresh} />}
      {ui.panel === "discount" && LIVE_MODE && <DiscountPanel api={api} onClose={close} onSaved={refresh} />}
      {ui.panel === "workstation" && LIVE_MODE && <WorkstationEditor api={api} workstation={selectedPc ?? undefined} groups={workspace.groups} onClose={close} onSaved={refresh} />}
      {ui.panel === "group" && LIVE_MODE && <GroupSettingsPanel api={api} group={ui.selectedGroup ?? undefined} onClose={close} onSaved={refresh} />}
      {ui.panel === "payment-method" && LIVE_MODE && <PaymentMethodPanel api={api} method={ui.selectedPaymentMethod ?? undefined} onClose={close} onSaved={refresh} />}
      {ui.panel === "cash-open" && LIVE_MODE && <CashOpenPanel api={api} onClose={close} onSaved={refresh} />}
      {ui.panel === "cash-movement" && LIVE_MODE && ui.selectedCashShift && <CashMovementPanel api={api} shift={ui.selectedCashShift} onClose={close} onSaved={refresh} />}
      {ui.panel === "cash-close" && LIVE_MODE && ui.selectedCashShift && <CashClosePanel api={api} shift={ui.selectedCashShift} onClose={close} onSaved={refresh} />}
    </aside>}
    {ui.panel === "sale" && <SaleWorkspace api={LIVE_MODE ? api : undefined} pc={selectedPc} initialClient={selectedClient} initialProduct={ui.saleInitialProduct} clients={workspace.clients} cashShifts={workspace.cashShifts} tariffs={workspace.tariffs} products={workspace.products} categories={workspace.productCategories} onClose={close} onSaved={refresh} />}
  </>;
}
