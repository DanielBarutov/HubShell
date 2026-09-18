import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { GameClubApi } from "../../api";
import type { BackendClientGroup } from "../../api";
import type { Client } from "../../types";
import { ClientPanel, NewClientPanel } from "./ClientsScreen";

const groups: BackendClientGroup[] = [
  { id: "regular", name: "Обычные клиенты", allow_negative_balance: false, negative_balance_limit_cents: 0, active: true, is_default: true, updated_at: null },
  { id: "vip", name: "VIP-клиенты", allow_negative_balance: true, negative_balance_limit_cents: 5_000, active: true, is_default: false, updated_at: null },
];

const client: Client = {
  id: "client-1",
  nickname: "NightFox",
  phone: "+79990000000",
  balance: 500,
  bonus: 0,
  category: "Без категории",
  clientGroupId: "regular",
};

function clientApi(updateClient = vi.fn().mockResolvedValue({})): GameClubApi {
  return {
    updateClient,
    listClientOperations: vi.fn().mockResolvedValue([]),
    listDiscountRules: vi.fn().mockResolvedValue([]),
    getClientAnalytics: vi.fn().mockResolvedValue(null),
  } as unknown as GameClubApi;
}

describe("Группа клиента в карточке", () => {
  it("сохраняет выбранную активную группу для существующего клиента", async () => {
    const updateClient = vi.fn().mockResolvedValue({});
    const api = clientApi(updateClient);

    render(<ClientPanel client={client} clientGroups={groups} api={api} onClose={vi.fn()} onSaved={vi.fn()} onDeposit={vi.fn()} onBonusDeposit={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /Редактировать/ }));
    const groupSelector = screen.getByRole("combobox", { name: "Группа клиента" });
    expect(groupSelector).toHaveValue("regular");

    fireEvent.change(groupSelector, { target: { value: "vip" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить клиента" }));

    await waitFor(() => expect(updateClient).toHaveBeenCalledWith("client-1", expect.objectContaining({ client_group_id: "vip" })));
  });

  it("передаёт выбранную группу при создании клиента", async () => {
    const createClient = vi.fn().mockResolvedValue({});
    const api = { createClient } as unknown as GameClubApi;

    render(<NewClientPanel api={api} clientGroups={groups} onClose={vi.fn()} onSaved={vi.fn()} />);

    fireEvent.change(screen.getByRole("textbox", { name: "Ник" }), { target: { value: "NewFox" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Группа клиента" }), { target: { value: "vip" } });
    fireEvent.click(screen.getByRole("button", { name: "Создать клиента" }));

    await waitFor(() => expect(createClient).toHaveBeenCalledWith(expect.objectContaining({ client_group_id: "vip" })));
  });
});
