import { Composition, Folder } from "remotion";
import { ChatSpike } from "./scenes/ChatSpike";
import { Intro } from "./scenes/Intro";
import { Layouts } from "./scenes/Layouts";
import { Outro } from "./scenes/Outro";
import { Process } from "./scenes/Process";
import { Shorts } from "./scenes/Shorts";
import { Subtitles } from "./scenes/Subtitles";
import { Tour } from "./Tour";

export const RemotionRoot = () => (
  <>
    <Composition id="Tour" component={Tour} width={1280} height={720} fps={30} durationInFrames={1368} />
    <Folder name="Scenes">
      <Composition id="Intro" component={Intro} width={1280} height={720} fps={30} durationInFrames={150} defaultProps={{ style: { backgroundColor: "#0C1B1F" } }} />
      <Composition id="ChatSpike" component={ChatSpike} width={1280} height={720} fps={30} durationInFrames={240} defaultProps={{ style: { backgroundColor: "#0C1B1F" } }} />
      <Composition id="Process" component={Process} width={1280} height={720} fps={30} durationInFrames={210} defaultProps={{ style: { backgroundColor: "#0C1B1F" } }} />
      <Composition id="Shorts" component={Shorts} width={1280} height={720} fps={30} durationInFrames={270} defaultProps={{ style: { backgroundColor: "#0C1B1F" } }} />
      <Composition id="Layouts" component={Layouts} width={1280} height={720} fps={30} durationInFrames={240} defaultProps={{ style: { backgroundColor: "#0C1B1F" } }} />
      <Composition id="Subtitles" component={Subtitles} width={1280} height={720} fps={30} durationInFrames={180} defaultProps={{ style: { backgroundColor: "#0C1B1F" } }} />
      <Composition id="Outro" component={Outro} width={1280} height={720} fps={30} durationInFrames={150} defaultProps={{ style: { backgroundColor: "#0C1B1F" } }} />
    </Folder>
  </>
);
