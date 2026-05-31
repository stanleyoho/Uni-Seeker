"use client";

import { SegmentError } from "@/components/stratos/segment-error";

export default function RootError({
  error,
  reset,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  reset?: () => void;
  unstable_retry?: () => void;
}) {
  return (
    <SegmentError
      scope="UNI-SEEKER"
      error={error}
      reset={reset}
      unstable_retry={unstable_retry}
    />
  );
}
