import { useMemo } from "react";
import { createAsyncThunk } from "@reduxjs/toolkit";
import { api } from "./api";
import { useAppDispatch } from "./hooks";
import type { GameClubApi } from "../api";

type AsyncMethodName = {
  [Key in keyof GameClubApi]: GameClubApi[Key] extends (...args: never[]) => Promise<unknown> ? Key : never;
}[keyof GameClubApi];

type ApiCall = {
  [Key in AsyncMethodName]: {
    method: Key;
    args: GameClubApi[Key] extends (...args: infer Arguments) => Promise<unknown> ? Arguments : never;
  };
}[AsyncMethodName];

export const callApi = createAsyncThunk<unknown, ApiCall, { rejectValue: string }>(
  "api/call",
  async (request, { rejectWithValue }) => {
    try {
      const method = api[request.method] as (...args: unknown[]) => Promise<unknown>;
      return await Reflect.apply(method, api, request.args);
    } catch (error) {
      return rejectWithValue(error instanceof Error ? error.message : "Не удалось выполнить операцию");
    }
  },
);

export type ReduxApi = {
  [Key in AsyncMethodName]: GameClubApi[Key] extends (...args: infer Arguments) => Promise<infer Result>
    ? (...args: Arguments) => Promise<Result>
    : never;
};

export function useReduxApi(): GameClubApi {
  const dispatch = useAppDispatch();
  return useMemo(() => new Proxy({}, {
    get: (_, property: string) => (...args: unknown[]) => dispatch(callApi({ method: property as AsyncMethodName, args: args as never } as ApiCall)).unwrap(),
  }) as unknown as GameClubApi, [dispatch]);
}
