import type { ReactNode } from "react";
import { Interactive, interpolate, useCurrentFrame } from "remotion";
import { Enter, Gameplay, Headline, Person, Phone, Split } from "../parts";
import { c, display, inOut, mono } from "../theme";

const Group = () => (
  <div style={{ display: "flex", width: "100%", height: "100%" }}>
    <div style={{ flex: 1, minWidth: 0 }}><Person bg="#473A2B" shirt="#C9583E" seed={1} /></div>
    <div style={{ flex: 1, minWidth: 0 }}><Person bg="#473A2B" shirt="#3F8C75" skin="#8E5F3E" seed={2} /></div>
    <div style={{ flex: 1, minWidth: 0 }}><Person bg="#473A2B" shirt="#D0A63A" skin="#E0B28A" seed={3} /></div>
  </div>
);

const Facecam = () => (
  <>
    <Gameplay />
    <div style={{ position: "absolute", left: "4%", top: "6%", width: "27%", height: "36%", boxShadow: `0 0 0 3px ${c.coral}` }}><Person /></div>
  </>
);

const Fit = ({ children }: { readonly children: ReactNode }) => (
  <>
    <div style={{ position: "absolute", inset: 0, filter: "blur(9px) brightness(0.55)", scale: 1.2 }}>{children}</div>
    <div style={{ position: "absolute", left: 0, right: 0, top: "50%", aspectRatio: "16 / 9", translate: "0 -50%", overflow: "hidden" }}>{children}</div>
  </>
);

// The speaker moves across the frame, and the 9:16 crop stays on the face.
const useSpeaker = () => interpolate(useCurrentFrame() % 120, [0, 60, 120], [-34, 34, -34], { easing: inOut });

const Talking = () => {
  const x = useSpeaker();
  return (
    <>
      <Person bg="#28424F" shirt="#B8893A" shift={x} />
      <div style={{ position: "absolute", top: 0, bottom: 0, width: "31.6%", left: `${34.2 + (x / 160) * 100}%`, boxSizing: "border-box", border: `3px solid ${c.yellow}` }} />
    </>
  );
};

const Follow = () => {
  const x = useSpeaker();
  return (
    <div style={{ position: "absolute", top: 0, height: "100%", width: "316%", left: `${50 - (0.5 + x / 160) * 316}%` }}>
      <Person bg="#28424F" shirt="#B8893A" shift={x} />
    </div>
  );
};

const Column = ({ i, type, mode, source, children }: {
  readonly i: number; readonly type: string; readonly mode: string; readonly source: ReactNode; readonly children: ReactNode;
}) => {
  const at = 14 + i * 26;
  return (
    <div style={{ position: "absolute", left: 72 + i * 292, top: 146, width: 260 }}>
      <Enter at={at}>
        <div style={{ fontFamily: mono, fontWeight: 700, fontSize: 27, color: c.mute, whiteSpace: "nowrap", height: 44 }}>{type}</div>
        <div style={{ position: "relative", width: 260, height: 146, borderRadius: 10, overflow: "hidden" }}>{source}</div>
      </Enter>
      <Enter at={at + 26} y={-30} style={{ position: "absolute", left: 56, top: 212 }}>
        <Phone width={148}>{children}</Phone>
      </Enter>
      <Enter at={at + 34} style={{ position: "absolute", left: 56, top: 486 }}>
        <div style={{ fontFamily: display, fontWeight: 800, fontSize: 40, color: c.yellow }}>{mode}</div>
      </Enter>
    </div>
  );
};

const LayoutsInner = () => (
  <>
    <Headline>Faces decide the layout.</Headline>
    <Column i={0} type="gaming_facecam" mode="split" source={<Facecam />}><Split /></Column>
    <Column i={1} type="gameplay" mode="fit" source={<Gameplay />}><Fit><Gameplay /></Fit></Column>
    <Column i={2} type="talking_head" mode="crop" source={<Talking />}><Follow /></Column>
    <Column i={3} type="group" mode="fit" source={<Group />}><Fit><Group /></Fit></Column>
  </>
);

export const Layouts = Interactive.create({ Component: LayoutsInner, layout: "absolute-fill" });
