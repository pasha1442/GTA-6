import { Interactive, interpolate, useCurrentFrame } from "remotion";
import { Enter, Gameplay, Person } from "../parts";
import { c, clamp, display, inOut } from "../theme";

/** The 16:9 stream turns into a 9:16 Short, and the webcam grows into the top panel. */
const Screen = () => {
  const frame = useCurrentFrame();
  const p = interpolate(frame, [52, 88], [0, 1], { ...clamp, easing: inOut });
  const mix = (a: number, b: number) => a + (b - a) * p;
  const w = mix(500, 298);
  const h = mix(281, 530);
  const cam = { left: mix(16, 0), top: mix(16, 0), width: mix(132, 298), height: mix(99, 212) };
  return (
    <div style={{ position: "absolute", left: 944 - w / 2, top: 360 - h / 2, width: w, height: h, borderRadius: mix(14, 24), overflow: "hidden", boxShadow: `0 0 0 5px ${c.text}`, background: "#3B2F4A" }}>
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, top: mix(0, 212) }}><Gameplay /></div>
      <div style={{ position: "absolute", ...cam, borderRadius: mix(8, 0), overflow: "hidden", boxShadow: `0 0 0 ${mix(3, 0)}px ${c.text}` }}><Person /></div>
      <div style={{ position: "absolute", right: 16, top: 16, opacity: 1 - p * 2, background: c.coral, color: "#fff", fontFamily: display, fontWeight: 800, fontSize: 24, padding: "4px 14px", borderRadius: 6 }}>LIVE</div>
      <div style={{ position: "absolute", left: 0, right: 0, top: 14, textAlign: "center", opacity: interpolate(frame, [92, 100], [0, 1], clamp), scale: interpolate(frame, [92, 99, 104], [0.7, 1.08, 1], clamp) }}>
        <span style={{ background: c.yellow, color: "#000", fontFamily: display, fontWeight: 800, fontSize: 26, padding: "4px 12px" }}>WAIT FOR IT</span>
      </div>
    </div>
  );
};

const IntroInner = () => (
  <>
    <Enter at={4} style={{ position: "absolute", left: 72, top: 176 }}>
      <div style={{ fontFamily: display, fontWeight: 800, fontSize: 100, lineHeight: 0.95, letterSpacing: -3, color: c.text }}>Long<br />streams in.</div>
    </Enter>
    <Enter at={70} style={{ position: "absolute", left: 72, top: 378 }}>
      <div style={{ fontFamily: display, fontWeight: 800, fontSize: 100, lineHeight: 0.95, letterSpacing: -3, color: c.yellow }}>Shorts out.</div>
    </Enter>
    <Enter at={92} style={{ position: "absolute", left: 72, top: 500, width: 560 }}>
      <div style={{ fontFamily: display, fontWeight: 500, fontSize: 32, lineHeight: 1.25, color: c.mute }}>Find the moment, frame it 9:16 and caption it.</div>
    </Enter>
    <Screen />
  </>
);

export const Intro = Interactive.create({ Component: IntroInner, layout: "absolute-fill" });
