"use client";

import { SegmentError } from "@/components/stratos/segment-error";

export default function JournalAccountDetailError(props: {
  error: Error & { digest?: string };
  reset?: () => void;
  unstable_retry?: () => void;
}) {
  return <SegmentError scope="JOURNAL · ACCOUNT" {...props} />;
}
