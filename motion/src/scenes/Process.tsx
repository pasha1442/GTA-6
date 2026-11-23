import type { ReactNode } from "react";
import { Interactive, interpolate, useCurrentFrame } from "remotion";
import { Enter, Headline, Phone, Split } from "../parts";
import { c, clamp, display, inOut, mono, out } from "../theme";

const Station = ({ at, left, title, note, children }: {
  readonly at: number; readonly left: number; readonly title: string; readonly note: string; readonly children: ReactNode;
}) => (
  <Enter at={at} style={{ position: "absolute", left, top: 160, width: 352 }}>
    <div style={{ height: 260, background: c.panel, borderRadius: 14, position: "relative", overflow: "hidden" }}>{children}</div>
    <div style={{ marginTop: 16, fontFamily: display, fontWeight: 800, fontSize: 38, color: c.text }}>{title}</div>
    <div style={{ fontFamily: display, fontWeight: 500, fontSize: 26, color: c.mute }}>{note}</div>
  </Enter>
);

const Wave = () => {
  const frame = useCurrentFrame();
  return (
    <>
      <div style={{ position: "absolute", left: 24, right: 24, top: 34, height: 100, display: "flex", alignItems: "center", gap: 6 }}>
        {Array.from({ length: 25 }, (_, i) => (
          <div key={i} style={{ flex: 1, borderRadius: 4, background: c.sky, height: 14 + Math.abs(Math.sin(i * 1.7 + frame / 7) * Math.cos(i * 0.6)) * 80 }} />
        ))}
      </div>
      {[270, 304, 190].map((w, i) => (
        <div key={w} style={{ position: "absolute", left: 24, top: 160 + i * 28, height: 14, borderRadius: 7, background: c.text, width: interpolate(frame, [26 + i * 10, 42 + i * 10], [0, w], { ...clamp, easing: out }) }} />
      ))}
    </>
  );
};

const Score = () => {
  const frame = useCurrentFrame();
  const v = interpolate(frame, [62, 96], [0, 82], { ...clamp, easing: inOut });
  const color = v >= 60 ? c.mint : c.coral;
  return (
    <>
      <div style={{ position: "absolute", left: 24, top: 34, fontFamily: display, fontWeight: 800, fontSize: 108, lineHeight: 1, letterSpacing: -3, color }}>{Math.round(v)}</div>
      <div style={{ position: "absolute", left: 24, width: 304, top: 176, height: 20, borderRadius: 10, background: c.bg }}>
        <div style={{ width: `${v}%`, height: "100%", borderRadius: 10, background: color }} />
      </div>
      <div style={{ position: "absolute", left: 204, top: 166, width: 4, height: 40, background: c.yellow }} />
      <div style={{ position: "absolute", left: 144, width: 124, textAlign: "center", top: 208, fontFamily: display, fontWeight: 500, fontSize: 26, color: c.yellow }}>pass: 60</div>
    </>
  );
};

const FOLDERS: [string, string, string][] = [
  ["approved/", "score passes", c.mint],
  ["rejected/", "no reel rendered", c.coral],
  ["unreviewed/", "no API key set", c.yellow],
];

const ProcessInner = () => (
  <>
    <Headline>Each clip goes through three steps.</Headline>
    <Station at={12} left={72} title="Transcribe" note="faster-whisper, on your PC"><Wave /></Station>
    <Station at={50} left={464} title="Review" note="optional, with an API key"><Score /></Station>
    <Station at={96} left={856} title="Render 9:16" note="face on top, game below">
      <div style={{ position: "absolute", left: 111, top: 14 }}><Phone width={130}><Split /></Phone></div>
    </Station>
    {FOLDERS.map(([name, note, color], i) => (
      <Enter key={name} at={126 + i * 10} style={{ position: "absolute", left: 72 + i * 392, top: 570 }}>
        <div style={{ fontFamily: mono, fontWeight: 700, fontSize: 34, color }}>{name}</div>
        <div style={{ fontFamily: display, fontWeight: 500, fontSize: 26, color: c.mute }}>{note}</div>
      </Enter>
    ))}
  </>
);

export const Process = Interactive.create({ Component: ProcessInner, layout: "absolute-fill" });
