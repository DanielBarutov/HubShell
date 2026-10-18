import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { GameClubApi } from "../../api";
import { BonusProgramSettings } from "./BonusProgramSettings";

const policy = { enabled: true, game_rate_bps: 500, product_rate_bps: 200, payment_limit_bps: 2000 };

function setup() {
  const api = new GameClubApi("/api/v1");
  const read = vi.spyOn(api, "getBonusProgram").mockResolvedValue(policy);
  const save = vi.spyOn(api, "updateBonusProgram").mockImplementation(async (body) => body);
  return { api, read, save };
}

describe("Настройка бонусной программы", () => {
  it("загружает проценты с сервера и сохраняет выключатель и лимит 100%", async () => {
    const { api, save } = setup();
    render(<BonusProgramSettings api={api} />);
    expect(screen.getByRole("status")).toHaveTextContent("Загружаем настройки");
    const limit = await screen.findByLabelText("Максимальная оплата бонусами, %");
    expect(limit).toHaveValue("20");
    fireEvent.change(limit, { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("Начисление за товары, %"), { target: { value: "2,55" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Бонусная программа включена" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить бонусную программу" }));
    await screen.findByText("Настройки бонусов сохранены");
    expect(save).toHaveBeenCalledWith({ ...policy, enabled: false, product_rate_bps: 255, payment_limit_bps: 10000 }, expect.any(String));
  });

  it("не округляет недопустимые доли процентов и блокирует сохранение", async () => {
    const { api, save } = setup();
    render(<BonusProgramSettings api={api} />);
    const input = await screen.findByLabelText("Начисление за игру, %");
    fireEvent.change(input, { target: { value: "5,005" } });
    expect(screen.getByRole("alert")).toHaveTextContent("точностью до 0,01%");
    expect(screen.getByRole("button", { name: "Сохранить бонусную программу" })).toBeDisabled();
    expect(save).not.toHaveBeenCalled();
  });

  it("показывает ошибку загрузки и загружает фактические настройки повторно", async () => {
    const { api, read } = setup();
    read.mockRejectedValueOnce(new Error("Сервер недоступен"));
    render(<BonusProgramSettings api={api} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Сервер недоступен");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Загрузить заново" }));
    expect(await screen.findByRole("checkbox")).toBeChecked();
  });

  it("повторяет неудачное сохранение с прежним ключом и не показывает ложный успех", async () => {
    const { api, save } = setup();
    save.mockRejectedValueOnce(new Error("Нет подтверждения сервера"));
    render(<BonusProgramSettings api={api} />);
    fireEvent.change(await screen.findByLabelText("Начисление за игру, %"), { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить бонусную программу" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Нет подтверждения сервера");
    expect(screen.queryByText("Настройки бонусов сохранены")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Сохранить бонусную программу" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    expect(save.mock.calls[0][1]).toBe(save.mock.calls[1][1]);
    await screen.findByText("Настройки бонусов сохранены");
  });
});
