import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { ChatSpike } from "./scenes/ChatSpike";
import { Intro } from "./scenes/Intro";
import { Layouts } from "./scenes/Layouts";
import { Outro } from "./scenes/Outro";
import { Process } from "./scenes/Process";
import { Shorts } from "./scenes/Shorts";
import { Subtitles } from "./scenes/Subtitles";
import { c } from "./theme";

const bg = { backgroundColor: c.bg };
const timing = linearTiming({ durationInFrames: 12 });

// 1440 frames of scenes, less six 12-frame cross-fades = 1368.
export const Tour = () => (
  <TransitionSeries>
    <TransitionSeries.Sequence name="Intro" durationInFrames={150}><Intro style={bg} /></TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={timing} />
    <TransitionSeries.Sequence name="Chat spike" durationInFrames={240}><ChatSpike style={bg} /></TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={timing} />
    <TransitionSeries.Sequence name="Process" durationInFrames={210}><Process style={bg} /></TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={timing} />
    <TransitionSeries.Sequence name="Shorts" durationInFrames={270}><Shorts style={bg} /></TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={timing} />
    <TransitionSeries.Sequence name="Layouts" durationInFrames={240}><Layouts style={bg} /></TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={timing} />
    <TransitionSeries.Sequence name="Subtitles" durationInFrames={180}><Subtitles style={bg} /></TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={timing} />
    <TransitionSeries.Sequence name="Outro" durationInFrames={150}><Outro style={bg} /></TransitionSeries.Sequence>
  </TransitionSeries>
);
