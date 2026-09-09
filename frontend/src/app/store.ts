import { configureStore } from "@reduxjs/toolkit";
import { api } from "./api";
import authReducer, { sessionExpired } from "../features/auth/authSlice";
import workspaceReducer, { clearWorkspace } from "../features/workspace/workspaceSlice";
import uiReducer from "../features/workspace/uiSlice";

export const store = configureStore({
  reducer: {
    auth: authReducer,
    workspace: workspaceReducer,
    ui: uiReducer,
  },
});

api.onSessionExpired(() => {
  store.dispatch(sessionExpired());
  store.dispatch(clearWorkspace());
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
