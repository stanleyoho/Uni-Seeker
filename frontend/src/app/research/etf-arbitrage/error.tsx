"use client";

import { SegmentError } from "@/components/stratos/segment-error";

export default function ETFArbitrageError(props: {
  error: Error & { digest?: string };
  reset?: () => void;
  unstable_retry?: () => void;
}) {
  return <SegmentError scope="ETF 折溢價監控" {...props} />;
}
