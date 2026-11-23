import { Interactive, interpolate, useCurrentFrame } from "remotion";
import { Enter, Headline, Phone, Split } from "../parts";
import { c, clamp, display, inOut, mono, out } from "../theme";

const LINES: [number, string, string][] = [
  [12, "> shorts.bat \"<youtube link>\"", c.text],
  [40, "source.mp4        downloaded", c.mute],
  [56, "layout.json       gaming_facecam", c.mute],
  [72, "transcript.txt    written", c.mute],
  [100, "NEEDS CLAUDE:     plan.json", c.yellow],
  [146, "plan.json         5 moments", c.mint],
  [176, "short-01 ... 05   rendered", c.mint],
];
const PICKS = [[96, 92], [298, 66], [470, 104], [690, 74], [940, 96]];

const Timeline = () => {
  const frame = useCurrentFrame();
  return (
    <div style={{ position: "absolute", left: 72, top: 448, width: 1136, height: 44, borderRadius: 8, background: c.panel, overflow: "hidden" }}>
      <div style={{ height: "100%", background: "#23454E", width: interpolate(frame, [40, 92], [0, 1136], { ...clamp, easing: inOut }) }} />
      {PICKS.map(([x, w], i) => (
        <div key={x} style={{ position: "absolute", left: x, top: 0, height: 44, background: c.yellow, width: interpolate(frame, [130 + i * 5, 144 + i * 5], [0, w], { ...clamp, easing: out }) }} />
      ))}
    </div>
  );
};

const ShortsInner = () => (
  <>
    <Headline>One link in, five Shorts out.</Headline>
    <div style={{ position: "absolute", left: 72, top: 146, width: 1136, height: 280, borderRadius: 14, background: "#071114", overflow: "hidden" }}>
      <div style={{ position: "absolute", left: 30, top: 20 }}>
        {LINES.map(([at, text, color]) => (
          <Enter key={text} at={at} y={8} style={{ height: 34 }}>
            <div style={{ fontFamily: mono, fontWeight: 700, fontSize: 27, lineHeight: "34px", color, whiteSpace: "pre" }}>{text}</div>
          </Enter>
        ))}
      </div>
      <Enter at={108} style={{ position: "absolute", right: 34, top: 118, width: 400 }}>
        <div style={{ fontFamily: display, fontWeight: 500, fontSize: 30, lineHeight: 1.2, color: c.yellow }}>It stops here, so Claude Code can read the transcript and choose.</div>
      </Enter>
    </div>
    <Timeline />
    {PICKS.map(([x, w], i) => (
      <Enter key={x} at={168 + i * 8} y={-50} style={{ position: "absolute", left: 72 + x + w / 2 - 42, top: 516 }}>
        <Phone width={84}><Split /></Phone>
      </Enter>
    ))}
  </>
);

export const Shorts = Interactive.create({ Component: ShortsInner, layout: "absolute-fill" });
