import type { CSSProperties, ReactNode } from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { c, clamp, display, out } from "./theme";

/** Fades and slides its children in, `at` frames into the scene. */
export const Enter = ({ at, y = 24, style, children }: {
  readonly at: number; readonly y?: number; readonly style?: CSSProperties; readonly children: ReactNode;
}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        ...style,
        opacity: interpolate(frame, [at, at + 12], [0, 1], clamp),
        translate: interpolate(frame, [at, at + 22], [`0px ${y}px`, "0px 0px"], { ...clamp, easing: out }),
      }}
    >
      {children}
    </div>
  );
};

export const Headline = ({ children }: { readonly children: ReactNode }) => (
  <Enter at={2} style={{ position: "absolute", left: 72, top: 56 }}>
    <div style={{ fontFamily: display, fontWeight: 800, fontSize: 64, lineHeight: 1, letterSpacing: -1.5, color: c.text }}>
      {children}
    </div>
  </Enter>
);

/** A generic driving scene; it stands in for gameplay. */
export const Gameplay = () => {
  const frame = useCurrentFrame();
  const dash = (frame * 0.045) % 1;
  const sway = Math.sin(frame / 22) * 14;
  return (
    <svg viewBox="0 0 320 180" preserveAspectRatio="xMidYMid slice" style={{ display: "block", width: "100%", height: "100%" }}>
      <rect width="320" height="180" fill="#1F5E73" />
      <circle cx="232" cy="52" r="20" fill="#FFD9A0" />
      <path d="M0 92 L40 62 L78 84 L122 50 L170 86 L214 66 L262 88 L320 60 V180 H0Z" fill="#17475A" />
      <rect y="92" width="320" height="88" fill="#2C6A50" />
      <path d="M148 92 H172 L290 180 H30Z" fill="#37474D" />
      {[0, 1, 2, 3].map((i) => {
        const t = ((i + dash) / 4) ** 2;
        const w = 1 + t * 9;
        return <rect key={i} x={160 - w / 2} y={92 + t * 88} width={w} height={2 + t * 18} fill="#E9E2C8" />;
      })}
      <g transform={`translate(${160 + sway} 128)`}>
        <rect x="-21" y="-2" width="42" height="24" rx="5" fill="#E8503F" />
        <path d="M-15 -2 L-10 -14 H10 L15 -2Z" fill="#B73A2D" />
        <rect x="-10" y="-11" width="20" height="8" rx="2" fill="#BFE3EC" />
        <rect x="-19" y="6" width="8" height="5" fill="#FFE08A" />
        <rect x="11" y="6" width="8" height="5" fill="#FFE08A" />
        <rect x="-18" y="20" width="9" height="6" fill="#10191B" />
        <rect x="9" y="20" width="9" height="6" fill="#10191B" />
      </g>
    </svg>
  );
};

/** A drawn person in front of a plain backdrop; it stands in for a webcam or a speaker. */
export const Person = ({ shirt = "#4C5FB8", skin = "#C98F62", bg = "#3B2F4A", shift = 0, seed = 0 }: {
  readonly shirt?: string; readonly skin?: string; readonly bg?: string;
  readonly shift?: number; readonly seed?: number;
}) => {
  const frame = useCurrentFrame();
  const bob = Math.sin((frame + seed * 17) / 9) * 2;
  const open = 2 + Math.abs(Math.sin((frame + seed * 11) / 5)) * 5;
  return (
    <svg viewBox="0 0 160 120" preserveAspectRatio="xMidYMid slice" style={{ display: "block", width: "100%", height: "100%" }}>
      <rect width="160" height="120" fill={bg} />
      <g transform={`translate(${80 + shift} ${58 + bob})`}>
        <path d="M-46 66 C-46 34 -24 30 0 30 C24 30 46 34 46 66Z" fill={shirt} />
        <rect x="-9" y="16" width="18" height="20" fill={skin} />
        <ellipse rx="23" ry="27" fill={skin} />
        <path d="M-24 -4 C-26 -34 26 -34 24 -4 C16 -14 -8 -18 -24 -4Z" fill="#1B1416" />
        <circle cx="-9" cy="0" r="2.6" fill="#1B1416" />
        <circle cx="9" cy="0" r="2.6" fill="#1B1416" />
        <ellipse cy="13" rx="7" ry={open} fill="#5A1F22" />
      </g>
    </svg>
  );
};

/** A 9:16 screen. */
export const Phone = ({ width, children }: { readonly width: number; readonly children: ReactNode }) => (
  <div
    style={{
      position: "relative", width, height: (width * 16) / 9, borderRadius: width * 0.07, overflow: "hidden",
      background: "#05090A", boxShadow: `0 0 0 ${Math.max(3, width * 0.016)}px ${c.text}`,
    }}
  >
    {children}
  </div>
);

/** Webcam on top, gameplay below: the split layout. */
export const Split = () => (
  <>
    <div style={{ position: "absolute", inset: "0 0 60% 0" }}><Person /></div>
    <div style={{ position: "absolute", inset: "40% 0 0 0" }}><Gameplay /></div>
  </>
);
