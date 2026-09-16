import { act, fireEvent, render, screen } from "@testing-library/react";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import { describe, expect, it } from "vitest";
import authReducer, { sessionExpired } from "./authSlice";
import { LoginScreen } from "./LoginScreen";

function renderLogin() {
  const store = configureStore({ reducer: { auth: authReducer } });
  return { store, ...render(<Provider store={store}><LoginScreen /></Provider>) };
}

describe("Экран входа оператора", () => {
  it("показывает доступные поля и блокирует отправку во время восстановления сессии", () => {
    renderLogin();

    expect(screen.getByRole("heading", { name: "Вход в клуб" })).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Логин" })).toBeVisible();
    expect(screen.getByLabelText("Пароль")).toBeVisible();
    expect(screen.getByRole("button", { name: "Войти" })).toBeDisabled();
    expect(screen.getByText("Восстанавливаем защищённую сессию…")).toBeVisible();
  });

  it("показывает ошибку истёкшей сессии как alert и разрешает повторный вход", () => {
    const { store } = renderLogin();
    act(() => {
      store.dispatch(sessionExpired());
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Сессия оператора истекла");
    expect(screen.getByRole("button", { name: "Войти" })).toBeEnabled();
    fireEvent.change(screen.getByRole("textbox", { name: "Логин" }), { target: { value: "operator" } });
    expect(screen.getByRole("textbox", { name: "Логин" })).toHaveValue("operator");
  });
});
