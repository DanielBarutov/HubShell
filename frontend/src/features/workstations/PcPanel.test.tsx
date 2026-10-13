import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PcPanel } from "./PcPanel";
import type { GameClubApi } from "../../api";
import type { Workstation } from "../../types";

const interruptSession = vi.fn();
const api = { interruptSession } as unknown as GameClubApi;
const activePc: Workstation = {
  id: "pc-01",
  name: "Avalonia Linux smoke",
  group: "Обычный зал",
  status: "busy",
  client: "DanielBarutov",
  clientId: "client-01",
  session: "18 мин",
  sessionId: "session-01",
  deviceId: "device-01",
};

function renderPcPanel(pc = activePc) {
  return render(
    <PcPanel
      pc={pc}
      client={{
        id: "client-01",
        nickname: "DanielBarutov",
        phone: "—",
        balance: 0,
        bonus: 0,
        category: "Без категории",
      }}
      onClose={vi.fn()}
      onEdit={vi.fn()}
      onBook={vi.fn()}
      onDeposit={vi.fn()}
      onOpenSale={vi.fn()}
      onSessionChanged={vi.fn()}
      api={api}
    />,
  );
}

describe("панель игрового ПК", () => {
  it("показывает действия новой локальной сессии", () => {
    const view = renderPcPanel();

    expect(screen.getAllByText("Оформить продажу")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Заблокировать клиент" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Прервать сессию" })).toBeInTheDocument();

    view.rerender(
      <PcPanel
        pc={{ ...activePc }}
        onClose={vi.fn()}
        onEdit={vi.fn()}
        onBook={vi.fn()}
        onDeposit={vi.fn()}
        onOpenSale={vi.fn()}
        onSessionChanged={vi.fn()}
        api={api}
      />,
    );

    expect(screen.queryByRole("button", { name: "Заблокировать клиент" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Прервать сессию" })).toBeInTheDocument();
  });

  it("прерывает активную сессию через сервер", async () => {
    interruptSession.mockResolvedValueOnce({});
    const onSessionChanged = vi.fn();
    vi.stubGlobal("confirm", vi.fn(() => true));
    render(
      <PcPanel
        pc={activePc}
        client={{ id: "client-01", nickname: "DanielBarutov", phone: "—", balance: 0, bonus: 0, category: "Без категории" }}
        onClose={vi.fn()}
        onEdit={vi.fn()}
        onBook={vi.fn()}
        onDeposit={vi.fn()}
        onOpenSale={vi.fn()}
        onSessionChanged={onSessionChanged}
        api={api}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Прервать сессию" }));

    await waitFor(() => expect(interruptSession).toHaveBeenCalledWith(
      "session-01",
      "Оператор прервал сессию из панели ПК",
      expect.any(String),
    ));
    expect(onSessionChanged).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });

});
