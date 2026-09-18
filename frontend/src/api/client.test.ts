import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GameClubApi } from "./index";

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

describe("GameClubApi", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("отправляет idempotency key и сериализует запрос переноса", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: "offer-1",
        session_id: "session-1",
        target_workstation_id: "pc-2",
      }),
    );

    const result = await new GameClubApi("http://backend/api/v1").createTransferOffer(
      "session-1",
      "pc-2",
      "transfer-key-1",
    );

    expect(result.id).toBe("offer-1");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://backend/api/v1/session-transfers/offers",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ session_id: "session-1", target_workstation_id: "pc-2" }),
      }),
    );
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get("Idempotency-Key")).toBe(
      "transfer-key-1",
    );
  });

  it("повторяет защищённый запрос после успешного refresh токена", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ access_token: "access-1", refresh_token: "refresh-1" }))
      .mockResolvedValueOnce(jsonResponse({ detail: "expired" }, 401))
      .mockResolvedValueOnce(jsonResponse({ access_token: "access-2", refresh_token: "refresh-2" }))
      .mockResolvedValueOnce(jsonResponse([{ id: "pc-1" }]));

    const api = new GameClubApi("http://backend/api/v1");
    await api.login("operator", "secret");
    const workstations = await api.listWorkstations();

    expect(workstations).toEqual([{ id: "pc-1" }]);
    expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get("Authorization")).toBe(
      "Bearer access-1",
    );
    expect(fetchMock.mock.calls[2]?.[0]).toBe("http://backend/api/v1/auth/refresh");
    expect(new Headers(fetchMock.mock.calls[3]?.[1]?.headers).get("Authorization")).toBe(
      "Bearer access-2",
    );
  });

  it("преобразует публичную ошибку API в ApiError с кодом сервера", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ message: "Недостаточно прав", code: "permission_denied" }, 403),
    );

    const request = new GameClubApi("http://backend/api/v1").listWorkstations();

    await expect(request).rejects.toMatchObject({
      name: "ApiError",
      status: 403,
      code: "permission_denied",
      message: "Недостаточно прав",
    });
  });

  it("передаёт группу клиента при создании и изменении профиля", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ id: "client-1" }, 201))
      .mockResolvedValueOnce(jsonResponse({ id: "client-1" }));
    const api = new GameClubApi("http://backend/api/v1");

    await api.createClient({ nickname: "NewFox", client_group_id: "vip" });
    await api.updateClient("client-1", { nickname: "NewFox", client_group_id: "regular" });

    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://backend/api/v1/clients");
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ body: JSON.stringify({ nickname: "NewFox", client_group_id: "vip" }) });
    expect(fetchMock.mock.calls[1]?.[0]).toBe("http://backend/api/v1/clients/client-1");
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({ body: JSON.stringify({ nickname: "NewFox", client_group_id: "regular" }) });
  });
});
