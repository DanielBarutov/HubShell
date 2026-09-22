import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricCard } from "./MetricCard";

describe("MetricCard info hint", () => {
  it("opens the metric explanation on keyboard focus and closes it on blur", () => {
    render(
      <MetricCard
        title="Общая выручка"
        value="1 000 ₽"
        delta="2 операции"
        icon={<span aria-hidden="true">₽</span>}
        accent="violet"
        info={{
          description: "Деньги, полученные клубом за период.",
          formula: "Подтверждённые платежи − возвраты",
          source: "Payment и Refund",
          emptyState: "При отсутствии фактов показывается «Нет данных». ",
        }}
      />,
    );

    const infoButton = screen.getByRole("button", { name: /Описание метрики: Общая выручка/ });
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();

    fireEvent.focus(infoButton);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Подтверждённые платежи − возвраты");
    expect(screen.getByRole("tooltip")).toHaveTextContent("Payment и Refund");

    fireEvent.blur(infoButton);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("opens the same explanation on pointer hover", () => {
    render(
      <MetricCard
        title="Загрузка мест"
        value="42%"
        delta="8 ПК"
        icon={<span aria-hidden="true">%</span>}
        accent="orange"
        info={{
          description: "Доля занятых минут от доступной ёмкости.",
          formula: "Занятые минуты / доступные минуты × 100%",
          source: "Завершённые сессии и рабочие места",
          emptyState: "Если доступная ёмкость равна нулю, показатель не рассчитывается.",
        }}
      />,
    );

    const infoButton = screen.getByRole("button", { name: /Описание метрики: Загрузка мест/ });
    fireEvent.mouseEnter(infoButton);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Занятые минуты / доступные минуты");

    fireEvent.mouseLeave(infoButton);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});
