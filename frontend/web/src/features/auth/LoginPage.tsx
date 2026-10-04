import { FormEvent, useState } from "react";
import { LogIn } from "lucide-react";
import { useAuth } from "../../app/auth";

export function LoginPage() {
  const auth = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      await auth.login(username, password);
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "Login failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <form className="login-panel" onSubmit={submit} autoComplete="off">
        <div>
          <p className="eyebrow">GraphWorld</p>
          <h1>Sign in</h1>
        </div>
        <label>
          <span>Username</span>
          <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="off" />
        </label>
        <label>
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="off"
          />
        </label>
        {error && <div className="error-panel compact">{error}</div>}
        <button className="button primary submit-button" type="submit" disabled={isSubmitting || !username || !password}>
          <LogIn size={16} aria-hidden />
          Sign in
        </button>
      </form>
    </main>
  );
}
