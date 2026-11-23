import { Interactive, interpolate, useCurrentFrame } from "remotion";
import { Enter, Phone, Split } from "../parts";
import { black, c, clamp, display, hindi } from "../theme";

// The caption builder puts at most three words on screen at a time.
const CUES = [["bhai", "ye", "kya"], ["ho", "gaya"]];
const WORD = 13;
const START = 44;

const Caption = () => {
  const frame = useCurrentFrame();
  const n = Math.floor(Math.max(0, frame - START) / WORD) % 5;
  const cue = n < 3 ? CUES[0] : CUES[1];
  const active = n < 3 ? n : n - 3;
  return (
    <div style={{ position: "absolute", left: 0, right: 0, top: 221, textAlign: "center", fontFamily: black, fontSize: 34, opacity: frame < START ? 0 : 1 }}>
      {cue.map((w, i) => (
        <span key={w} style={{ color: i === active ? c.yellow : "#fff", WebkitTextStroke: "7px #000", paintOrder: "stroke fill", margin: "0 6px" }}>{w}</span>
      ))}
    </div>
  );
};

const Hook = () => {
  const frame = useCurrentFrame();
  return (
    <div style={{ position: "absolute", left: 0, right: 0, top: 26, textAlign: "center", opacity: interpolate(frame, [22, 26], [0, 1], clamp), scale: interpolate(frame, [22, 29, 33], [0.7, 1.08, 1], clamp) }}>
      <span style={{ background: c.yellow, color: "#000", fontFamily: black, fontSize: 25, padding: "5px 11px", whiteSpace: "nowrap" }}>WAIT FOR THE END</span>
    </div>
  );
};

const SubtitlesInner = () => (
  <>
    <Enter at={2} style={{ position: "absolute", left: 72, top: 84 }}>
      <div style={{ fontFamily: display, fontWeight: 800, fontSize: 76, lineHeight: 0.98, letterSpacing: -2, color: c.text }}>Hindi speech,<br />Hinglish captions.</div>
    </Enter>
    <Enter at={34} style={{ position: "absolute", left: 72, top: 316 }}>
      <div style={{ fontFamily: hindi, fontWeight: 700, fontSize: 54, lineHeight: 1.4, color: c.mute }}>भाई ये क्या हो गया</div>
    </Enter>
    <Enter at={68} y={-40} style={{ position: "absolute", left: 72, top: 404 }}>
      <div style={{ fontFamily: display, fontWeight: 800, fontSize: 58, color: c.yellow }}>bhai ye kya ho gaya</div>
    </Enter>
    <Enter at={92} style={{ position: "absolute", left: 72, top: 540, width: 620 }}>
      <div style={{ fontFamily: display, fontWeight: 500, fontSize: 32, lineHeight: 1.25, color: c.mute }}>Timed word by word, with a headline at the top of the screen.</div>
    </Enter>
    <Enter at={10} y={60} style={{ position: "absolute", left: 840, top: 54 }}>
      <Phone width={344}><Split /><Hook /><Caption /></Phone>
    </Enter>
  </>
);

export const Subtitles = Interactive.create({ Component: SubtitlesInner, layout: "absolute-fill" });
