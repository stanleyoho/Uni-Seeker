"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/i18n/context";
import { useAuth } from "@/contexts/auth-context";
import { login, register } from "@/lib/api-client";
import { TabGroup } from "@/components/ui/tab-group";

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

  const inputClass =
    "w-full px-3 py-2.5 bg-[var(--background)] border border-[var(--border-subtle)] rounded-lg text-white text-sm focus:outline-none focus:border-[var(--accent-blue)] focus:ring-1 focus:ring-[var(--accent-blue)]/30 transition-all duration-200 placeholder-[var(--text-muted)]";

  return (
    <div className="flex-1 flex items-center justify-center p-4 relative overflow-hidden">
      {/* Background decoration - enhanced shimmer */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-blue-600/8 rounded-full blur-[100px] animate-pulse-glow" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-purple-600/8 rounded-full blur-[100px]" />
        <div className="absolute inset-0 animate-shimmer" />
      </div>

      <div className="relative w-full max-w-sm glass border border-[var(--border-color)] rounded-xl p-6 shadow-2xl shadow-black/50 animate-fade-in" style={{ backdropFilter: "blur(24px)", WebkitBackdropFilter: "blur(24px)" }}>
        {/* Logo */}
        <div className="text-center mb-5">
          <h1 className="text-xl font-bold gradient-text">Uni-Seeker</h1>
        </div>

        {/* Tabs */}
        <div className="flex justify-center mb-5">
          <TabGroup
            tabs={[
              { key: "login", label: t.auth.login },
              { key: "register", label: t.auth.register },
            ]}
            active={tab}
            onChange={(key) => { setTab(key as "login" | "register"); setError(""); }}
            size="sm"
          />
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-1">
              {t.auth.email}
            </label>
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass} />
          </div>

          {tab === "register" && (
            <div className="animate-fade-in">
              <label className="block text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-1">
                {t.auth.username}
              </label>
              <input type="text" required value={username} onChange={(e) => setUsername(e.target.value)} className={inputClass} />
            </div>
          )}

          <div>
            <label className="block text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-1">
              {t.auth.password}
            </label>
            <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className={inputClass} />
          </div>

          {error && (
            <div className="px-2.5 py-2 bg-[var(--stock-up)]/10 border border-[var(--stock-up)]/20 rounded-lg animate-slide-down">
              <p className="text-red-400 text-xs">{error}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-[var(--accent-blue)] hover:bg-[var(--accent-blue-hover)] disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-all duration-200"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ...
              </span>
            ) : tab === "login" ? (
              t.auth.loginButton
            ) : (
              t.auth.registerButton
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
