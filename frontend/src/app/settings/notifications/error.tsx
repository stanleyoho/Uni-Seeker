"use client";

import { SegmentError } from "@/components/stratos/segment-error";

export default function SettingsNotificationsError(props: {
  error: Error & { digest?: string };
  reset?: () => void;
  unstable_retry?: () => void;
}) {
  return <SegmentError scope="SETTINGS · NOTIFICATIONS" {...props} />;
}
