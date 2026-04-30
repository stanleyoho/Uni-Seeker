"use client";

import { useEffect, useRef } from "react";
import Hls from "hls.js";

// ── Video Sources ──────────────────────────────────────────────

const HLS_BG =
  "https://stream.mux.com/tLkHO1qZoaaQOUeVWo8hEBeGQfySP02EPS02BmnNFyXys.m3u8";

const VIDEO_HUMAN =
  "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260424_090051_64ea5059-da6b-492b-a171-aa7ecc767dc3.mp4";

const VIDEO_AI =
  "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260424_093237_ff0ddc63-c068-4e29-96da-fdd0e40af133.mp4";

// ── VideoIcon ──────────────────────────────────────────────────

function VideoIcon({ src, size = 72 }: { src: string; size?: number }) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    videoRef.current?.play().catch(() => {});
  }, []);

  return (
    <span
      className="inline-block align-middle rounded-full overflow-hidden"
      style={{
        width: `clamp(48px, 10vw, ${size}px)`,
        height: `clamp(48px, 10vw, ${size}px)`,
        flexShrink: 0,
      }}
    >
      <video
        ref={videoRef}
        autoPlay
        loop
        muted
        playsInline
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          display: "block",
        }}
      >
        <source src={src} type="video/mp4" />
      </video>
    </span>
  );
}

// ── GradientLine ───────────────────────────────────────────────

const gradientStyle: React.CSSProperties = {
  background:
    "linear-gradient(90deg, #666666 0%, #d0d0d0 50%, #666666 100%)",
  WebkitBackgroundClip: "text",
  WebkitTextFillColor: "transparent",
  backgroundClip: "text",
  display: "block",
  lineHeight: 1.1,
  marginBottom: "-0.22em",
};

// ── HeroSection ────────────────────────────────────────────────

export function HeroSection() {
  const bgVideoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = bgVideoRef.current;
    if (!video) return;

    let hls: Hls | null = null;

    if (Hls.isSupported()) {
      hls = new Hls({ autoStartLoad: true });
      hls.loadSource(HLS_BG);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        video.play().catch(() => {});
      });
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = HLS_BG;
      video.addEventListener("loadedmetadata", () => {
        video.play().catch(() => {});
      });
    }

    return () => {
      if (hls) {
        hls.destroy();
      }
    };
  }, []);

  return (
    <section
      className="relative overflow-hidden flex flex-col items-center justify-center"
      style={{ height: "100vh", background: "#000" }}
    >
      {/* ── Fullscreen HLS video background ── */}
      <video
        ref={bgVideoRef}
        autoPlay
        loop
        muted
        playsInline
        className="absolute inset-0 w-full h-full object-cover"
        style={{ zIndex: 0 }}
      />

      {/* ── Content ── */}
      <div
        className="relative z-10 flex flex-col items-center text-center px-4 max-w-5xl mx-auto"
        style={{ marginTop: 380 }}
      >
        {/* Headline */}
        <h1
          className="leading-tight"
          style={{
            fontFamily: "'YDYoonche L', 'YDYoonche M', sans-serif",
            fontSize: "clamp(2.2rem, 7vw, 6.5rem)",
            color: "#fff",
            fontWeight: 300,
            letterSpacing: "-0.01em",
            lineHeight: 1.1,
          }}
        >
          <span style={gradientStyle}>The vision</span>
          <span style={gradientStyle}>of engineering</span>

          <span className="flex items-center justify-center gap-3 flex-wrap">
            <span style={{ color: "#999" }}>is</span>
            <VideoIcon src={VIDEO_HUMAN} size={110} />
            <span>human</span>
            <span
              style={{
                color: "#999",
                position: "relative",
                top: "0.15em",
                marginLeft: "0.25em",
              }}
            >
              +
            </span>
            <VideoIcon src={VIDEO_AI} size={110} />
            <span>AI</span>
          </span>
        </h1>

        {/* Subheading */}
        <p
          className="mt-4 max-w-xl text-center px-2"
          style={{
            fontSize: "clamp(0.95rem, 2.2vw, 1.2rem)",
            color: "#ccc",
            lineHeight: 1.4,
            fontWeight: 400,
          }}
        >
          We help you map the talent you need, track the talent you have, and
          close your gaps to thrive in a GenAI world.
        </p>

        {/* CTA Button */}
        <button
          className="mt-6 transition-all duration-300 hover:scale-[1.03] hover:shadow-[0px_6px_32px_8px_rgba(39,243,169,0.22)] active:scale-[0.98]"
          style={{
            padding: "12px 28px",
            background: "#000",
            boxShadow: "0px 6px 24px 6px rgba(39, 243, 169, 0.15)",
            borderRadius: 8,
            outline: "1px solid #30463C",
            outlineOffset: -1,
            border: "none",
            cursor: "pointer",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 10,
          }}
        >
          <span style={{ color: "#fff", fontSize: 14, fontWeight: 400 }}>
            Join The Movement!
          </span>
        </button>
      </div>
    </section>
  );
}
