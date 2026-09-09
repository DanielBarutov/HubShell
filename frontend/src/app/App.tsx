import { useEffect } from "react";
import { useAppDispatch, useAppSelector } from "./hooks";
import { LIVE_MODE } from "./config";
import { restoreSession, selectAuth } from "../features/auth/authSlice";
import { AppShell } from "./AppShell";

export default function App() {
  const dispatch = useAppDispatch();
  const auth = useAppSelector(selectAuth);

  useEffect(() => {
    if (LIVE_MODE && auth.isRestoring) void dispatch(restoreSession());
  }, [auth.isRestoring, dispatch]);

  return <AppShell />;
}
