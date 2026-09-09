import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import type { RootState } from "../../app/store";
import { api } from "../../app/api";

type AuthState = {
  isAuthenticated: boolean;
  isRestoring: boolean;
  isSubmitting: boolean;
  error: string | null;
};

const initialState: AuthState = {
  isAuthenticated: false,
  isRestoring: true,
  isSubmitting: false,
  error: null,
};

export const login = createAsyncThunk<void, { username: string; password: string }, { rejectValue: string }>(
  "auth/login",
  async ({ username, password }, { rejectWithValue }) => {
    try {
      await api.login(username, password);
    } catch (error) {
      return rejectWithValue(error instanceof Error ? error.message : "Не удалось войти");
    }
  },
);

export const restoreSession = createAsyncThunk<boolean, void, { rejectValue: string }>(
  "auth/restoreSession",
  async (_, { rejectWithValue }) => {
    try {
      return await api.restoreSession();
    } catch (error) {
      return rejectWithValue(error instanceof Error ? error.message : "Не удалось восстановить сессию");
    }
  },
);

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    sessionExpired(state) {
      state.isAuthenticated = false;
      state.isRestoring = false;
      state.error = "Сессия оператора истекла. Войдите снова.";
    },
    clearAuthError(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(login.pending, (state) => {
        state.isSubmitting = true;
        state.error = null;
      })
      .addCase(login.fulfilled, (state) => {
        state.isSubmitting = false;
        state.isAuthenticated = true;
        state.isRestoring = false;
      })
      .addCase(login.rejected, (state, action) => {
        state.isSubmitting = false;
        state.isAuthenticated = false;
        state.error = action.payload ?? "Не удалось войти";
      })
      .addCase(restoreSession.pending, (state) => {
        state.isRestoring = true;
        state.error = null;
      })
      .addCase(restoreSession.fulfilled, (state, action) => {
        state.isRestoring = false;
        state.isAuthenticated = action.payload;
      })
      .addCase(restoreSession.rejected, (state, action) => {
        state.isRestoring = false;
        state.isAuthenticated = false;
        state.error = action.payload ?? "Не удалось восстановить сессию";
      });
  },
});

export const { sessionExpired, clearAuthError } = authSlice.actions;
export const selectAuth = (state: RootState) => state.auth;
export default authSlice.reducer;
