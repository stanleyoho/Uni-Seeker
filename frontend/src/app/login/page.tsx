"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/i18n/context";
import { useAuth } from "@/contexts/auth-context";
import { login, register } from "@/lib/api-client";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";

export default function LoginPage() {
  const { t } = useI18n();
  const { setToken } = useAuth();
  const router = useRouter();

  const [tab, setTab] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [username, setUsername] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      let token: string;
      if (tab === "login") {
        token = await login(email, password);
      } else {
        token = await register(email, password, username);
      }
      setToken(token);
      router.push("/");
    } catch (err) {
      setError(
        tab === "login"
          ? t.auth.loginFailed + (err instanceof Error ? `: ${err.message}` : "")
          : t.auth.registerFailed + (err instanceof Error ? `: ${err.message}` : ""),
      );
    } finally {
      setLoading(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "12px 16px",
    background: "var(--bg-secondary)",
    border: "1px solid var(--border-color)",
    color: "var(--foreground)",
    fontSize: 14,
    outline: "none",
    transition: "outline 150ms",
  };

  const labelClass =
    "block text-[11px] uppercase tracking-[0.05em] font-bold mb-1.5";

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4"
      style={{ background: "var(--background)" }}
    >
      <GlassPanel className="w-full max-w-md">
        {/* Logo */}
        <div className="flex flex-col items-center gap-2 mb-8">
          <svg
            width="40"
            height="40"
            viewBox="0 0 28 28"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M14 3L25 23H3L14 3Z"
              fill="var(--foreground)"
              opacity="0.9"
            />
            <path
              d="M14 8L20 20H8L14 8Z"
              fill="var(--accent-primary, #ef4444)"
              opacity="0.8"
            />
          </svg>
          <span
            className="font-bold text-[22px] uppercase"
            style={{
              color: "var(--foreground)",
              letterSpacing: "-0.04em",
            }}
          >
            STRATOS
          </span>
        </div>

        {/* Tab toggle */}
        <div className="flex mb-6 gap-0">
          <button
            type="button"
            onClick={() => { setTab("login"); setError(""); }}
            className="flex-1 py-2.5 text-sm font-semibold uppercase tracking-[0.05em] transition-colors duration-200"
            style={{
              background: tab === "login" ? "var(--accent-primary)" : "transparent",
              color: tab === "login" ? "#fff" : "var(--text-secondary)",
              border: tab === "login" ? "none" : "1px solid var(--border-color)",
              cursor: "pointer",
            }}
          >
            {t.auth.login}
          </button>
          <button
            type="button"
            onClick={() => { setTab("register"); setError(""); }}
            className="flex-1 py-2.5 text-sm font-semibold uppercase tracking-[0.05em] transition-colors duration-200"
            style={{
              background: tab === "register" ? "var(--accent-primary)" : "transparent",
              color: tab === "register" ? "#fff" : "var(--text-secondary)",
              border: tab === "register" ? "none" : "1px solid var(--border-color)",
              cursor: "pointer",
            }}
          >
            {t.auth.register}
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              className={labelClass}
              style={{ color: "var(--text-secondary)" }}
            >
              {t.auth.email}
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={inputStyle}
              onFocus={(e) => {
                e.currentTarget.style.outline = "2px solid var(--accent-cyan)";
                e.currentTarget.style.outlineOffset = "2px";
              }}
              onBlur={(e) => {
                e.currentTarget.style.outline = "none";
                e.currentTarget.style.outlineOffset = "0px";
              }}
            />
          </div>

          {tab === "register" && (
            <div>
              <label
                className={labelClass}
                style={{ color: "var(--text-secondary)" }}
              >
                {t.auth.username}
              </label>
              <input
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                style={inputStyle}
                onFocus={(e) => {
                  e.currentTarget.style.outline = "2px solid var(--accent-cyan)";
                  e.currentTarget.style.outlineOffset = "2px";
                }}
                onBlur={(e) => {
                  e.currentTarget.style.outline = "none";
                  e.currentTarget.style.outlineOffset = "0px";
                }}
              />
            </div>
          )}

          <div>
            <label
              className={labelClass}
              style={{ color: "var(--text-secondary)" }}
            >
              {t.auth.password}
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={inputStyle}
              onFocus={(e) => {
                e.currentTarget.style.outline = "2px solid var(--accent-cyan)";
                e.currentTarget.style.outlineOffset = "2px";
              }}
              onBlur={(e) => {
                e.currentTarget.style.outline = "none";
                e.currentTarget.style.outlineOffset = "0px";
              }}
            />
          </div>

          {error && (
            <p className="text-sm" style={{ color: "var(--accent-primary)" }}>
              {error}
            </p>
          )}

          <div className="pt-2">
            <ClippedButton
              type="submit"
              variant={tab === "login" ? "red-solid" : "white-solid"}
              size="lg"
              disabled={loading}
              className="w-full"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span
                    className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"
                  />
                  ...
                </span>
              ) : tab === "login" ? (
                t.auth.loginButton
              ) : (
                t.auth.registerButton
              )}
            </ClippedButton>
          </div>
        </form>
      </GlassPanel>
    </div>
  );
}
