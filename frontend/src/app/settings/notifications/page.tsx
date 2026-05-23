"use client";

/**
 * Notification Preferences — Round 9 Y7 frontend.
 *
 * Two server-state sections + one Phase-5 stub:
 *   1. Telegram transport — bind / clear `users.telegram_chat_id`.
 *   2. Per-filer toggles  — flip `notify_on_new_filing` for each
 *      subscribed F13 filer.
 *   3. Other channels (Email / LINE / Webhook) — preview-only stub
 *      mirroring `/api/v1/notifications/channels?status=coming_soon`.
 *
 * Backend asymmetry note:
 *   The institutional list endpoint returns `F13Filer` (no
 *   `notify_on_new_filing` field) and the PATCH preferences route has no
 *   GET sibling. We therefore track the per-filer toggle state as a
 *   client-side optimistic map, defaulting unknown rows to `true` to match
 *   the DB default. The PATCH response is the single source of truth — we
 *   reconcile it into the local map after every save.
 *
 * STRATOS styling: GlassPanel sections, ClippedButton actions, dark-luxe
 * background via AmbientBackground (mirrors /holdings page layout).
 */

import { useEffect, useMemo, useState } from "react";
import { useI18n } from "@/i18n/context";
import { AmbientBackground } from "@/components/stratos/ambient";
import {
  ClippedButton,
  GlassPanel,
} from "@/components/stratos/primitives";
import { useAuth } from "@/contexts/auth-context";
import { useInstitutionalFilers } from "@/hooks/use-institutional";
import {
  useMeNotifications,
  useUpdateFilerPreferences,
  useUpdateMeNotifications,
} from "@/hooks/use-notification-prefs";
import type { F13Filer } from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type ToastTone = "success" | "error";

interface Toast {
  tone: ToastTone;
  message: string;
}

function inputStyle(): React.CSSProperties {
  return {
    width: "100%",
    background: "var(--bg-secondary)",
    border: "1px solid var(--border-color)",
    color: "var(--foreground)",
    padding: "10px 12px",
    fontSize: 13,
    fontVariantNumeric: "tabular-nums",
    outline: "none",
  };
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function NotificationsSettingsPage() {
  const { tr } = useI18n();
  const { user } = useAuth();

  // Server state
  const meQuery = useMeNotifications();
  const updateMe = useUpdateMeNotifications();
  const filersQuery = useInstitutionalFilers();
  const updateFilerPref = useUpdateFilerPreferences();

  // ----- Telegram form state -----
  const [chatIdInput, setChatIdInput] = useState("");
  const [chatIdHydrated, setChatIdHydrated] = useState(false);
  const [toast, setToast] = useState<Toast | null>(null);

  // Sync the input once the server value lands. We guard with a hydration
  // flag so the user can keep typing after the initial fill without the
  // query refetching wiping their unsaved edits.
  useEffect(() => {
    if (chatIdHydrated) return;
    if (meQuery.data) {
      setChatIdInput(meQuery.data.telegram_chat_id ?? "");
      setChatIdHydrated(true);
    }
  }, [meQuery.data, chatIdHydrated]);

  // Auto-dismiss toasts after 3s.
  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 3000);
    return () => window.clearTimeout(t);
  }, [toast]);

  const currentChatId = meQuery.data?.telegram_chat_id ?? null;

  const handleSaveChatId = () => {
    const trimmed = chatIdInput.trim();
    const next = trimmed.length > 0 ? trimmed : null;
    updateMe.mutate(
      { telegram_chat_id: next },
      {
        onSuccess: (data) => {
          setChatIdInput(data.telegram_chat_id ?? "");
          setToast({
            tone: "success",
            message: tr("settings.notifications.telegram.save_success"),
          });
        },
        onError: () => {
          setToast({
            tone: "error",
            message: tr("settings.notifications.telegram.save_error"),
          });
        },
      },
    );
  };

  const handleClearChatId = () => {
    updateMe.mutate(
      { telegram_chat_id: null },
      {
        onSuccess: () => {
          setChatIdInput("");
          setToast({
            tone: "success",
            message: tr("settings.notifications.telegram.save_success"),
          });
        },
        onError: () => {
          setToast({
            tone: "error",
            message: tr("settings.notifications.telegram.save_error"),
          });
        },
      },
    );
  };

  // ----- Per-filer toggle state -----
  //
  // Local optimistic map: filerId → notify flag. The backend list endpoint
  // does not echo `notify_on_new_filing`, so we initialise unknown rows
  // to `true` (the DB default) and overwrite from PATCH responses.
  const [filerPrefs, setFilerPrefs] = useState<Record<number, boolean>>({});

  const filers: F13Filer[] = useMemo(
    () => filersQuery.data ?? [],
    [filersQuery.data],
  );

  // Seed missing entries on first filer load.
  useEffect(() => {
    if (filers.length === 0) return;
    setFilerPrefs((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const f of filers) {
        if (next[f.id] === undefined) {
          next[f.id] = true;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [filers]);

  const handleToggle = (filerId: number, nextValue: boolean) => {
    // Optimistic flip — revert on error.
    setFilerPrefs((prev) => ({ ...prev, [filerId]: nextValue }));
    updateFilerPref.mutate(
      { filerId, notify_on_new_filing: nextValue },
      {
        onError: () => {
          setFilerPrefs((prev) => ({ ...prev, [filerId]: !nextValue }));
          setToast({
            tone: "error",
            message: tr("settings.notifications.telegram.save_error"),
          });
        },
      },
    );
  };

  const handleBulkToggle = (value: boolean) => {
    for (const f of filers) {
      // Fire-and-forget; per-call invalidation handles cache refresh.
      handleToggle(f.id, value);
    }
  };

  // ----- Auth gate ---------------------------------------------------------
  if (!user) {
    return (
      <main className="relative flex-1 overflow-y-auto">
        <AmbientBackground />
        <div className="relative max-w-[1440px] mx-auto px-6 py-6">
          <GlassPanel>
            <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
              {tr("auth.login")} required.
            </p>
          </GlassPanel>
        </div>
      </main>
    );
  }

  return (
    <main className="relative flex-1 overflow-y-auto">
      <AmbientBackground />

      <div className="relative max-w-[960px] mx-auto px-6 py-6 space-y-6">
        {/* Page title */}
        <div>
          <h1
            className="text-[20px] font-bold uppercase"
            style={{
              color: "var(--foreground)",
              letterSpacing: "-0.04em",
            }}
          >
            {tr("settings.notifications.title")}
          </h1>
          <p
            style={{
              fontSize: 13,
              color: "var(--text-muted)",
              marginTop: 4,
            }}
          >
            {tr("settings.notifications.subtitle")}
          </p>
        </div>

        {/* Inline toast — non-blocking */}
        {toast && (
          <div
            role="status"
            aria-live="polite"
            style={{
              padding: "8px 12px",
              fontSize: 12,
              color:
                toast.tone === "success"
                  ? "var(--accent-cyan)"
                  : "var(--accent-primary)",
              border: `1px solid ${
                toast.tone === "success"
                  ? "var(--accent-cyan)"
                  : "var(--accent-primary)"
              }`,
              background: "var(--card-hover)",
            }}
          >
            {toast.message}
          </div>
        )}

        {/* Section 1: Telegram transport */}
        <GlassPanel title={tr("settings.notifications.telegram.title")}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div
              style={{
                fontSize: 12,
                color: "var(--text-muted)",
              }}
            >
              {tr("settings.notifications.telegram.help")}{" "}
              <a
                href="https://t.me/userinfobot"
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  color: "var(--accent-cyan)",
                  textDecoration: "underline",
                }}
              >
                @userinfobot
              </a>
            </div>

            <div
              style={{
                fontSize: 12,
                color: "var(--text-secondary)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              <span style={{ color: "var(--text-muted)" }}>
                {tr("settings.notifications.telegram.current_label")}:
              </span>{" "}
              <span
                style={{
                  color: currentChatId
                    ? "var(--foreground)"
                    : "var(--text-muted)",
                  fontWeight: 500,
                }}
              >
                {currentChatId ??
                  tr("settings.notifications.telegram.not_set")}
              </span>
            </div>

            <label
              htmlFor="telegram-chat-id"
              style={{
                fontSize: 11,
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                color: "var(--text-muted)",
              }}
            >
              {tr("settings.notifications.telegram.chat_id_label")}
            </label>
            <input
              id="telegram-chat-id"
              type="text"
              value={chatIdInput}
              onChange={(e) => setChatIdInput(e.target.value)}
              placeholder={tr(
                "settings.notifications.telegram.chat_id_placeholder",
              )}
              maxLength={64}
              style={inputStyle()}
              disabled={meQuery.isLoading || updateMe.isPending}
            />

            <div
              style={{
                display: "flex",
                gap: 8,
                flexWrap: "wrap",
              }}
            >
              <ClippedButton
                variant="red-solid"
                size="md"
                onClick={handleSaveChatId}
                disabled={
                  updateMe.isPending ||
                  meQuery.isLoading ||
                  chatIdInput.trim() === (currentChatId ?? "")
                }
              >
                {tr("settings.notifications.telegram.save")}
              </ClippedButton>
              <ClippedButton
                variant="red-ghost"
                size="md"
                onClick={handleClearChatId}
                disabled={
                  updateMe.isPending ||
                  meQuery.isLoading ||
                  currentChatId === null
                }
              >
                {tr("settings.notifications.telegram.clear")}
              </ClippedButton>
              <ClippedButton
                variant="cyan-ghost"
                size="md"
                onClick={() =>
                  setToast({
                    tone: "success",
                    message: tr(
                      "settings.notifications.telegram.test_coming_soon",
                    ),
                  })
                }
                disabled={currentChatId === null}
              >
                {tr("settings.notifications.telegram.test")}
              </ClippedButton>
            </div>
          </div>
        </GlassPanel>

        {/* Section 2: Per-filer 13F toggles */}
        <GlassPanel title={tr("settings.notifications.f13.title")}>
          <p
            style={{
              fontSize: 12,
              color: "var(--text-muted)",
              marginBottom: 16,
            }}
          >
            {tr("settings.notifications.f13.subtitle")}
          </p>

          {filersQuery.isLoading ? (
            <div
              style={{
                fontSize: 12,
                color: "var(--text-muted)",
                padding: "12px 0",
              }}
            >
              ...
            </div>
          ) : filers.length === 0 ? (
            <div
              style={{
                fontSize: 13,
                color: "var(--text-muted)",
                padding: "16px 0",
              }}
            >
              {tr("settings.notifications.f13.no_subscribed")}
            </div>
          ) : (
            <>
              <div
                style={{
                  display: "flex",
                  gap: 8,
                  marginBottom: 12,
                  flexWrap: "wrap",
                }}
              >
                <ClippedButton
                  variant="cyan-ghost"
                  size="sm"
                  onClick={() => handleBulkToggle(true)}
                  disabled={updateFilerPref.isPending}
                >
                  {tr("settings.notifications.f13.enable_all")}
                </ClippedButton>
                <ClippedButton
                  variant="red-ghost"
                  size="sm"
                  onClick={() => handleBulkToggle(false)}
                  disabled={updateFilerPref.isPending}
                >
                  {tr("settings.notifications.f13.disable_all")}
                </ClippedButton>
              </div>

              <div
                role="table"
                aria-label={tr("settings.notifications.f13.title")}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  border: "1px solid var(--border-color)",
                }}
              >
                <div
                  role="row"
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 160px",
                    gap: 12,
                    padding: "10px 14px",
                    fontSize: 11,
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    color: "var(--text-muted)",
                    background: "var(--bg-secondary)",
                    borderBottom: "1px solid var(--border-color)",
                  }}
                >
                  <span role="columnheader">
                    {tr("settings.notifications.f13.column_filer")}
                  </span>
                  <span role="columnheader" style={{ textAlign: "right" }}>
                    {tr("settings.notifications.f13.column_notify")}
                  </span>
                </div>
                {filers.map((f) => {
                  const enabled = filerPrefs[f.id] ?? true;
                  return (
                    <div
                      key={f.id}
                      role="row"
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 160px",
                        gap: 12,
                        padding: "12px 14px",
                        alignItems: "center",
                        borderBottom: "1px solid var(--border-subtle)",
                      }}
                    >
                      <div role="cell">
                        <div
                          style={{
                            fontSize: 13,
                            fontWeight: 500,
                            color: "var(--foreground)",
                          }}
                        >
                          {f.name}
                        </div>
                        <div
                          style={{
                            fontSize: 11,
                            color: "var(--text-muted)",
                            fontVariantNumeric: "tabular-nums",
                          }}
                        >
                          CIK {f.cik}
                        </div>
                      </div>
                      <div
                        role="cell"
                        style={{
                          display: "flex",
                          justifyContent: "flex-end",
                        }}
                      >
                        <ToggleSwitch
                          checked={enabled}
                          onChange={(v) => handleToggle(f.id, v)}
                          ariaLabel={`${tr(
                            "settings.notifications.f13.toggle_aria",
                          )} – ${f.name}`}
                          disabled={updateFilerPref.isPending}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </GlassPanel>

        {/* Section 3: Other channels — Phase-5 stub */}
        <GlassPanel title={tr("settings.notifications.channels.title")}>
          <div
            style={{
              fontSize: 12,
              color: "var(--text-muted)",
              padding: "4px 0",
            }}
          >
            {tr("settings.notifications.channels.coming_soon")}
          </div>
        </GlassPanel>
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// ToggleSwitch — accessible, STRATOS-styled
// ---------------------------------------------------------------------------

interface ToggleSwitchProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  ariaLabel: string;
  disabled?: boolean;
}

function ToggleSwitch({
  checked,
  onChange,
  ariaLabel,
  disabled = false,
}: ToggleSwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      onKeyDown={(e) => {
        if (e.key === " " || e.key === "Enter") {
          e.preventDefault();
          onChange(!checked);
        }
      }}
      style={{
        position: "relative",
        width: 44,
        height: 24,
        borderRadius: 12,
        border: "1px solid var(--border-color)",
        background: checked
          ? "var(--accent-cyan)"
          : "var(--bg-secondary)",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.6 : 1,
        transition: "background 0.18s ease",
        outline: "none",
      }}
      onFocus={(e) => {
        e.currentTarget.style.boxShadow =
          "0 0 0 2px var(--background), 0 0 0 4px var(--accent-cyan)";
      }}
      onBlur={(e) => {
        e.currentTarget.style.boxShadow = "none";
      }}
    >
      <span
        aria-hidden="true"
        style={{
          position: "absolute",
          top: 2,
          left: checked ? 22 : 2,
          width: 18,
          height: 18,
          borderRadius: "50%",
          background: "var(--foreground)",
          transition: "left 0.18s ease",
        }}
      />
    </button>
  );
}
