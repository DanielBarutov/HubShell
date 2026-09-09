import { useState } from "react";
import { Command } from "lucide-react";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { clearAuthError, login, selectAuth } from "./authSlice";

export function LoginScreen() {
  const dispatch = useAppDispatch();
  const { isRestoring, isSubmitting, error } = useAppSelector(selectAuth);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    dispatch(clearAuthError());
    await dispatch(login({ username, password }));
  };

  return (
    <div className="login-shell">
      <form className="login-card" onSubmit={submit}>
        <div className="brand login-brand"><div className="brand-mark"><Command size={19} strokeWidth={2.6} /></div><span>HUBSHELL</span><span className="brand-dot">·</span></div>
        <p className="eyebrow">Операторский доступ</p>
        <h1>Вход в клуб</h1>
        <p className="subheading">{isRestoring ? "Восстанавливаем защищённую сессию…" : "Авторизуйтесь, чтобы открыть dashboard и карту мест."}</p>
        <label>Логин<input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" /></label>
        <label>Пароль<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" /></label>
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="primary-button wide" disabled={isSubmitting || isRestoring}>{isSubmitting ? "Проверяем..." : "Войти"}</button>
      </form>
    </div>
  );
}
