import { Interactive, interpolate, useCurrentFrame } from "remotion";
import { Enter, Headline } from "../parts";
import { c, clamp, display, mono, out } from "../theme";

// The weights are what clipper/chatscore.py returns for these messages.
const CHAT: [string, number][] = [
  ["W W W", 0], ["nice drive", 1], ["hello", 0], ["no sound", 0], ["left side dekho", 1], ["giveaway please", 0],
  ["OMG", 2], ["hahaha", 2], ["clip it", 2], ["lmao", 2], ["kya tha ye", 2],
];
const BARS = [5, 7, 6, 4, 7, 5, 6, 8, 5, 6, 27];
const THRESHOLD = 18; // three times the normal rate
const UNIT = 7.4;
const SPIKE_AT = 118;

const Chat = () => {
  const frame = useCurrentFrame();
  return (
    <div style={{ position: "absolute", left: 72, top: 158, width: 400, height: 490, overflow: "hidden", background: c.panel, borderRadius: 14 }}>
      <div style={{ position: "absolute", left: 24, right: 24, bottom: 18 }}>
        {CHAT.map(([text, weight], i) => {
          const at = 14 + (i < 6 ? i * 14 : 84 + (i - 6) * 7);
          const grow = interpolate(frame, [at, at + 8], [0, 1], { ...clamp, easing: out });
          const color = weight === 2 ? c.coral : weight === 1 ? c.text : c.mute;
          return (
            <div key={text} style={{ height: 58 * grow, opacity: grow, display: "flex", alignItems: "center", justifyContent: "space-between", fontFamily: display, fontWeight: 500, fontSize: 30, color, whiteSpace: "nowrap" }}>
              <span style={{ textDecoration: weight === 0 ? "line-through" : "none" }}>{text}</span>
              <span style={{ fontFamily: mono, fontWeight: 700, fontSize: 28 }}>×{weight}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const Graph = () => {
  const frame = useCurrentFrame();
  return (
    <div style={{ position: "absolute", left: 520, top: 158, width: 688, height: 300 }}>
      {BARS.map((v, i) => {
        const last = i === BARS.length - 1;
        const at = last ? SPIKE_AT - 14 : 10 + i * 9;
        return (
          <div key={i} style={{ position: "absolute", left: i * 62, bottom: 0, width: 46, borderRadius: "6px 6px 0 0", background: last ? c.coral : c.sky, height: interpolate(frame, [at, at + 16], [0, v * UNIT], { ...clamp, easing: out }) }} />
        );
      })}
      <div style={{ position: "absolute", left: 0, width: 666, bottom: 0, height: 3, background: c.line }} />
      <Enter at={24} y={0} style={{ position: "absolute", left: 0, width: 666, bottom: THRESHOLD * UNIT, borderTop: `3px dashed ${c.yellow}` }}>
        <div style={{ position: "absolute", left: 0, bottom: 8, fontFamily: display, fontWeight: 500, fontSize: 28, color: c.yellow, whiteSpace: "nowrap" }}>spike threshold</div>
      </Enter>
      <Enter at={SPIKE_AT} y={14} style={{ position: "absolute", right: 92, top: 88 }}>
        <div style={{ fontFamily: display, fontWeight: 800, fontSize: 60, color: c.coral, letterSpacing: -1 }}>×4.6</div>
      </Enter>
    </div>
  );
};

/** 4-second segments are 30.5 px apart; the clip is 20 s before the spike and 15 s after it. */
const Recording = () => {
  const frame = useCurrentFrame();
  const open = interpolate(frame, [SPIKE_AT + 24, SPIKE_AT + 54], [0, 1], { ...clamp, easing: out });
  return (
    <div style={{ position: "absolute", left: 520, top: 510, width: 666, height: 140 }}>
      <div style={{ display: "flex", gap: 5 }}>
        {Array.from({ length: 22 }, (_, i) => (
          <div key={i} style={{ width: 25.5, height: 52, borderRadius: 4, background: "#23454E", opacity: interpolate(frame, [6 + i * 7, 14 + i * 7], [0, 1], clamp) }} />
        ))}
      </div>
      <div style={{ position: "absolute", left: 445 - 152 * open, width: 266 * open, top: -6, height: 64, borderRadius: 8, boxSizing: "border-box", border: `4px solid ${c.mint}`, background: "rgba(79,224,168,0.25)", opacity: open }} />
      <div style={{ position: "absolute", left: 443, top: -16, width: 4, height: 84, background: c.coral, opacity: interpolate(frame, [SPIKE_AT, SPIKE_AT + 6], [0, 1], clamp) }} />
      <div style={{ position: "absolute", left: 0, top: 78, fontFamily: display, fontWeight: 500, fontSize: 28, color: c.mute }}>recording</div>
      <div style={{ position: "absolute", left: 0, top: 78, width: 666, fontFamily: display, fontWeight: 500, fontSize: 28, color: c.mint, opacity: interpolate(frame, [SPIKE_AT + 40, SPIKE_AT + 54], [0, 1], clamp) }}>
        <span style={{ position: "absolute", right: 231, whiteSpace: "nowrap" }}>20 s before</span>
        <span style={{ position: "absolute", left: 455, whiteSpace: "nowrap" }}>15 s after</span>
      </div>
    </div>
  );
};

const ChatSpikeInner = () => (
  <>
    <Headline>Chat jumps, so a clip is cut.</Headline>
    <Chat />
    <Graph />
    <Recording />
  </>
);

export const ChatSpike = Interactive.create({ Component: ChatSpikeInner, layout: "absolute-fill" });
