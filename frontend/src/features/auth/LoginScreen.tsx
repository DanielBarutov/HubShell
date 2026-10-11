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
    <div className="login-shell grid min-h-screen place-items-center bg-base-100! p-6 text-base-content!">
      <form className="login-card card flex w-full max-w-md flex-col gap-4 border border-primary/25! bg-base-100/85! p-8 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md" onSubmit={submit}>
        <div className="brand login-brand flex items-center gap-2 text-lg font-extrabold"><div className="brand-mark grid h-8 w-8 place-items-center rounded-lg bg-primary! text-primary-content!"><Command size={19} strokeWidth={2.6} /></div><span>HUBSHELL</span><span className="brand-dot text-primary!">·</span></div>
        <p className="mb-1 text-sm text-base-content/65! text-xs uppercase tracking-widest text-primary!">Операторский доступ</p>
        <h1 className="text-2xl font-bold">Вход в клуб</h1>
        <p className="mt-1 text-sm text-base-content/70! text-sm text-base-content/65!">{isRestoring ? "Проверяем вход…" : "Войдите, чтобы работать с клубом."}</p>
        <label className="flex flex-col gap-1 text-sm">Логин<input className="input input-sm" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" /></label>
        <label className="flex flex-col gap-1 text-sm">Пароль<input className="input input-sm" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" /></label>
        {error && <div className="form-error rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!" role="alert">{error}</div>}
        <button className="primary-button btn btn-primary btn-block w-full bg-primary! text-primary-content!" disabled={isSubmitting || isRestoring}>{isSubmitting ? "Проверяем..." : "Войти"}</button>
      </form>
    </div>
  );
}
