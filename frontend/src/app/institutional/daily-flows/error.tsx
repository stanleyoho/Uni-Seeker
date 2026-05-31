"use client";

import { SegmentError } from "@/components/stratos/segment-error";

export default function DailyFlowsError(props: {
  error: Error & { digest?: string };
  reset?: () => void;
  unstable_retry?: () => void;
}) {
  return <SegmentError scope="DAILY-FLOWS" {...props} />;
}
