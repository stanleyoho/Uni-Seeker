"use client";

import { useWebSocket } from "./use-websocket";

const WS_BASE =
  process.env.NEXT_PUBLIC_WS_URL ||
  "ws://localhost:8000/api/v1/ws/notifications";

interface Notification {
  type: string;
  title: string;
  message: string;
  timestamp: string;
  data?: unknown;
}

export function useNotificationsWS(options?: { enabled?: boolean }) {
  const { isConnected, lastMessage } = useWebSocket({
    url: WS_BASE,
    channel: "notifications",
    enabled: options?.enabled ?? true,
  });

  return {
    isConnected,
    lastNotification: lastMessage as Notification | null,
  };
}
