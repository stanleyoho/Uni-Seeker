"use client";

import { SegmentError } from "@/components/stratos/segment-error";

export default function LowBaseError(props: {
  error: Error & { digest?: string };
  reset?: () => void;
  unstable_retry?: () => void;
}) {
  return <SegmentError scope="LOW-BASE SCAN" {...props} />;
}
