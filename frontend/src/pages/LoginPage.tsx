import { useEffect, useState } from "react";
import { api, type DemoInfo, type Me } from "../api";

export default function LoginPage({ onLogin, demo }: { onLogin: (me: Me) => void; demo: DemoInfo | null }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Shared single account: just a passcode box. Falls back to username + password if the check fails.
  const [passcode, setPasscode] = useState(false);

  useEffect(() => {
    api.authMode().then((m) => setPasscode(m.passcode)).catch(() => setPasscode(false));
  }, []);

  async function logIn(user: string, pass: string) {
    setBusy(true);
    setError(null);
    try {
      onLogin(await api.login(user, pass));
    } catch (err) {
      // "401: Wrong username or password." -> "Wrong username or password."
      setError(String(err).replace(/^Error:\s*\d+:\s*/, ""));
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    logIn(passcode ? "" : username, password);
  }

  return (
    <main className="login-page">
      <img src="/icon-192.png" alt="" className="login-icon" width={96} height={96} />
      <h1>Bay Area Yums Map</h1>
      {demo && (
        <div className="demo-intro">
          <p>
            A map of restaurants saved from Instagram food reels, with a been-here log for two friends. This demo
            uses made-up places; anything you change is reset later.
          </p>
          <button className="primary" disabled={busy} onClick={() => logIn(demo.username, demo.password)}>
            Try the demo
          </button>
          <p className="muted">Or log in below with:</p>
          <dl className="demo-login">
            <dt>Username</dt>
            <dd>
              <code>{demo.username}</code>
            </dd>
            <dt>Password</dt>
            <dd>
              <code>{demo.password}</code>
            </dd>
          </dl>
          <p className="muted">
            <a href={demo.source_url} target="_blank" rel="noreferrer">
              Source code on GitHub
            </a>
          </p>
        </div>
      )}
      <form className="login-form" onSubmit={submit}>
        {!passcode && (
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
        )}
        <label>
          {passcode ? "Passcode" : "Password"}
          <input
            key={passcode ? "passcode" : "password"}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            autoFocus={passcode}
          />
        </label>
        {error && (
          <p className="login-error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="primary" disabled={busy || (!passcode && !username) || !password}>
          {busy ? "Logging in…" : "Log in"}
        </button>
      </form>
    </main>
  );
}
