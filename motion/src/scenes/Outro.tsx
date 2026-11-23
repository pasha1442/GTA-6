import { Interactive } from "remotion";
import { Enter } from "../parts";
import { c, display, mono } from "../theme";

const WAYS: [string, string, string][] = [
  ["run.bat", "a channel that is live now", c.coral],
  ["vod.bat", "a stream that has ended", c.sky],
  ["shorts.bat", "a video that is already uploaded", c.yellow],
];

const OutroInner = () => (
  <>
    <Enter at={2} style={{ position: "absolute", left: 72, top: 100 }}>
      <div style={{ fontFamily: display, fontWeight: 800, fontSize: 92, lineHeight: 0.95, letterSpacing: -3, color: c.text }}>Three ways to start.</div>
    </Enter>
    {WAYS.map(([cmd, what, color], i) => (
      <Enter key={cmd} at={20 + i * 14} style={{ position: "absolute", left: 72, top: 264 + i * 112 }}>
        <div style={{ display: "flex", alignItems: "baseline" }}>
          <div style={{ width: 400, fontFamily: mono, fontWeight: 700, fontSize: 56, color }}>{cmd}</div>
          <div style={{ fontFamily: display, fontWeight: 500, fontSize: 40, color: c.text }}>{what}</div>
        </div>
      </Enter>
    ))}
    <Enter at={70} style={{ position: "absolute", left: 72, top: 612 }}>
      <div style={{ fontFamily: display, fontWeight: 500, fontSize: 34, color: c.mute }}>All of them can give you 1080 × 1920 video.</div>
    </Enter>
  </>
);

export const Outro = Interactive.create({ Component: OutroInner, layout: "absolute-fill" });
