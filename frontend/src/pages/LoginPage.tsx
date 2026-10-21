import { useState } from "react";
import { api, type Me } from "../api";

export default function LoginPage({ onLogin }: { onLogin: (me: Me) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLogin(await api.login(username, password));
    } catch (err) {
      // "401: Wrong username or password." -> "Wrong username or password."
      setError(String(err).replace(/^Error:\s*\d+:\s*/, ""));
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <img src="/icon-192.png" alt="" className="login-icon" width={96} height={96} />
      <h1>Bay Area Yums Map</h1>
      <form className="login-form" onSubmit={submit}>
        <label>
          Username
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            required
            autoFocus
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error && (
          <p className="login-error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="primary" disabled={busy || !username || !password}>
          {busy ? "Logging in…" : "Log in"}
        </button>
      </form>
    </main>
  );
}
