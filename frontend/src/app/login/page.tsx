"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/i18n/context";
import { useAuth } from "@/contexts/auth-context";
import { login, register } from "@/lib/api-client";

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

  return (
    <div className="flex-1 flex items-center justify-center p-4 relative overflow-hidden">
      {/* Background decoration */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/3 left-1/3 w-80 h-80 bg-blue-600/5 rounded-full blur-3xl" />
        <div className="absolute bottom-1/3 right-1/3 w-80 h-80 bg-purple-600/5 rounded-full blur-3xl" />
      </div>

      <div className="relative w-full max-w-md glass border border-[#1e293b] rounded-2xl p-8 shadow-2xl shadow-black/40 animate-fade-in">
        {/* Logo */}
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold gradient-text">Uni-Seeker</h1>
        </div>

        {/* Tabs */}
        <div className="flex mb-6 bg-[#111827] p-1 rounded-xl">
          <button
            className={`flex-1 py-2.5 text-center text-sm font-medium rounded-lg transition-all duration-200 ${
              tab === "login"
                ? "bg-blue-600 text-white shadow-lg shadow-blue-600/20"
                : "text-[#94a3b8] hover:text-white"
            }`}
            onClick={() => { setTab("login"); setError(""); }}
          >
            {t.auth.login}
          </button>
          <button
            className={`flex-1 py-2.5 text-center text-sm font-medium rounded-lg transition-all duration-200 ${
              tab === "register"
                ? "bg-blue-600 text-white shadow-lg shadow-blue-600/20"
                : "text-[#94a3b8] hover:text-white"
            }`}
            onClick={() => { setTab("register"); setError(""); }}
          >
            {t.auth.register}
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-[#64748b] uppercase tracking-wider font-medium mb-1.5">
              {t.auth.email}
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-4 py-2.5 bg-[#111827] border border-[#1e293b] rounded-xl text-white text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition-all duration-200 placeholder-[#64748b]"
            />
          </div>

          {tab === "register" && (
            <div className="animate-fade-in">
              <label className="block text-xs text-[#64748b] uppercase tracking-wider font-medium mb-1.5">
                {t.auth.username}
              </label>
              <input
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-4 py-2.5 bg-[#111827] border border-[#1e293b] rounded-xl text-white text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition-all duration-200 placeholder-[#64748b]"
              />
            </div>
          )}

          <div>
            <label className="block text-xs text-[#64748b] uppercase tracking-wider font-medium mb-1.5">
              {t.auth.password}
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-2.5 bg-[#111827] border border-[#1e293b] rounded-xl text-white text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition-all duration-200 placeholder-[#64748b]"
            />
          </div>

          {error && (
            <div className="px-3 py-2.5 bg-red-500/10 border border-red-500/20 rounded-xl animate-slide-down">
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium rounded-xl transition-all duration-200 shadow-lg shadow-blue-600/20 hover:shadow-blue-600/30"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
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
