// Renders every animation the README uses into docs/media.
//   npm run render              all of them
//   npm run render ChatSpike    just one
// Needs ffmpeg on PATH (it turns the videos into GIFs).
import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";

const OUT = process.env.MEDIA_DIR ?? "../docs/media";
const GIFS = {
  Intro: "intro",
  ChatSpike: "chat-spike",
  Process: "process",
  Shorts: "shorts",
  Layouts: "layouts",
  Subtitles: "subtitles",
};
const only = process.argv.slice(2);
const run = (file, args) => execFileSync(file, args, { stdio: "inherit" });
const remotion = (...args) =>
  run(process.execPath, ["node_modules/@remotion/cli/remotion-cli.js", ...args]);

mkdirSync("out", { recursive: true });
mkdirSync(OUT, { recursive: true });
for (const [id, name] of Object.entries(GIFS)) {
  if (only.length && !only.includes(id)) continue;
  remotion("render", id, `out/${name}.mp4`, "--crf=12", "--muted");
  run("ffmpeg", [
    "-v", "error", "-y", "-i", `out/${name}.mp4`, "-vf",
    "fps=15,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];" +
      "[b][p]paletteuse=dither=none:diff_mode=rectangle",
    "-loop", "0", `${OUT}/${name}.gif`,
  ]);
}
if (!only.length || only.includes("Tour")) {
  remotion("render", "Tour", `${OUT}/tour.mp4`, "--crf=20", "--scale=1.5", "--muted");
}
