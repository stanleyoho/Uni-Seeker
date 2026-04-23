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
    <div className="flex-1 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-gray-800 rounded-lg p-6 space-y-6">
        {/* Tabs */}
        <div className="flex border-b border-gray-700">
          <button
            className={`flex-1 py-2 text-center text-sm font-medium transition ${
              tab === "login"
                ? "text-blue-400 border-b-2 border-blue-400"
                : "text-gray-400 hover:text-white"
            }`}
            onClick={() => { setTab("login"); setError(""); }}
          >
            {t.auth.login}
          </button>
          <button
            className={`flex-1 py-2 text-center text-sm font-medium transition ${
              tab === "register"
                ? "text-blue-400 border-b-2 border-blue-400"
                : "text-gray-400 hover:text-white"
            }`}
            onClick={() => { setTab("register"); setError(""); }}
          >
            {t.auth.register}
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-300 mb-1">{t.auth.email}</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white text-sm focus:outline-none focus:border-blue-500"
            />
          </div>

          {tab === "register" && (
            <div>
              <label className="block text-sm text-gray-300 mb-1">{t.auth.username}</label>
              <input
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white text-sm focus:outline-none focus:border-blue-500"
              />
            </div>
          )}

          <div>
            <label className="block text-sm text-gray-300 mb-1">{t.auth.password}</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white text-sm focus:outline-none focus:border-blue-500"
            />
          </div>

          {error && (
            <p className="text-red-400 text-sm">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 disabled:opacity-50 text-white text-sm rounded transition"
          >
            {loading
              ? "..."
              : tab === "login"
                ? t.auth.loginButton
                : t.auth.registerButton}
          </button>
        </form>
      </div>
    </div>
  );
}
