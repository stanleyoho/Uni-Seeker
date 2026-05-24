"use client";

import React from "react";

/* ------------------------------------------------------------------ */
/*  AmbientBackground                                                  */
/* ------------------------------------------------------------------ */

const keyframesId = "stratos-drift";

const driftKeyframes = `
@keyframes ${keyframesId} {
  0%   { transform: translateX(0)   translateY(0);   }
  25%  { transform: translateX(30px)  translateY(-20px); }
  50%  { transform: translateX(-20px) translateY(15px);  }
  75%  { transform: translateX(15px)  translateY(-10px); }
  100% { transform: translateX(0)   translateY(0);   }
}
@media (prefers-reduced-motion: reduce) {
  .stratos-drift-group { animation: none !important; }
}
`;

export function AmbientBackground() {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        pointerEvents: "none",
        zIndex: 0,
        overflow: "hidden",
      }}
      aria-hidden="true"
    >
      {/* inject keyframes */}
      <style dangerouslySetInnerHTML={{ __html: driftKeyframes }} />

      <svg
        width="100%"
        height="100%"
        xmlns="http://www.w3.org/2000/svg"
        style={{ position: "absolute", inset: 0 }}
      >
        <defs>
          {/* grid pattern */}
          <pattern
            id="stratos-grid"
            width="60"
            height="60"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M 60 0 L 0 0 0 60"
              fill="none"
              stroke="rgba(255,255,255,0.04)"
              strokeWidth="1"
            />
          </pattern>

          {/* blur filter for drifting lines */}
          <filter id="stratos-blur">
            <feGaussianBlur stdDeviation="6" />
          </filter>
        </defs>

        {/* grid */}
        <rect width="100%" height="100%" fill="url(#stratos-grid)" />

        {/* slow-drifting blurred chart-line shadows */}
        <g
          className="stratos-drift-group"
          style={{ animation: `${keyframesId} 60s ease-in-out infinite` }}
          filter="url(#stratos-blur)"
          opacity="0.06"
        >
          <path
            d="M0,300 Q200,250 400,320 T800,280 T1200,310 T1600,260 T2000,290"
            fill="none"
            stroke="#EE3F2C"
            strokeWidth="2"
          />
          <path
            d="M0,500 Q300,470 600,520 T1000,480 T1400,510 T1800,460"
            fill="none"
            stroke="#00E5FF"
            strokeWidth="2"
          />
          <path
            d="M0,700 Q250,680 500,720 T900,690 T1300,730 T1700,700 T2000,680"
            fill="none"
            stroke="#10B981"
            strokeWidth="2"
          />
        </g>
      </svg>
    </div>
  );
}
