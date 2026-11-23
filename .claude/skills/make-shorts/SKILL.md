---
name: make-shorts
description: Cut YouTube Shorts / Instagram Reels with burned-in subtitles from a video already on YouTube (or a video file). Claude Code picks the moments and writes the Hinglish subtitles for Hindi videos. Use when the user gives a YouTube link or video and asks for shorts, reels, clips or subtitles.
argument-hint: <youtube link or video file> [--count N] [--min S] [--max S] [--lang hi|en] [--layout auto|split|track|crop|fit]
---

# Make Shorts / Reels from a YouTube video

The tool is `clipper/shorts.py`. It does the mechanical work (download, transcription,
cutting, 9:16 rendering, face tracking, subtitles). **You** do the judgement steps: checking
the video type, choosing the moments and writing Hinglish. There is no API key; never ask the
user for one.

Run it from the project root with the project's Python:

```bash
"$USERPROFILE/.clipcreator/venv/Scripts/python.exe" -m clipper.shorts "<link or file>" [options]
```

Pass on any options the user gave (`--count`, `--min`, `--max`, `--lang`, `--layout`,
`--upper`, `--no-subs`). Defaults: 5 shorts, 20–60 seconds each, layout `auto`.

Each run does the next possible step and stops with **exit code 2** and a line starting
`NEEDS CLAUDE:` when it needs a file from you. Write that file, then run the same command
again (or pass the folder `clips/shorts-<id>` instead of the link, which skips the YouTube lookup).
Exit code 0 means the shorts are finished.

## Step 1: download, video type, transcribe (slow)

The first run downloads the video, then **decides the video type before anything else**
(about 15 s), then transcribes all of it. Transcription takes about 1/4 of the video's length
on the GPU and 2–3× on CPU, so **run it in the background** (`run_in_background: true`)
and tell the user it is transcribing. Everything lands in `clips/shorts-<video id>/`.

The video type comes from the faces in sampled frames and decides the layout:

| type | what it is | default layout |
|---|---|---|
| `gaming_facecam` | gameplay with the streamer's webcam in a corner | **split**: webcam on top (face tracked inside it), gameplay below, subtitles on the seam |
| `gameplay` | gameplay or screen recording, no face | **fit**: whole frame on a blurred background |
| `talking_head` | one person fills the frame (vlog, solo podcast, just chatting) | **crop**: 9:16 crop that follows the face |
| `group` | several people (podcast, show, stage) | **fit** |

It writes `layout.json` (type plus layout) and `scene.jpg` (12 sampled frames, faces in
green, the webcam box in red). In a `gaming_facecam` video, a short where the streamer goes
full-screen on camera switches to a tracked crop by itself.

## Step 2: check the video type, write `plan.json` (you pick the moments)

First look at `clips/shorts-<id>/scene.jpg` (Read it; it is an image). `transcript.txt` starts
with the detected type and the reason. If the type is wrong (e.g. a stage show taken for
a facecam stream, or a red webcam box that misses the webcam), put the right one in
`plan.json` as `"video_type"`; the layout follows it. If the webcam box is wrong, tell the
user and offer the frame selector (below) after the render.

Then read `clips/shorts-<id>/transcript.txt`: the title, description, chapters, YouTube's
"most replayed" parts (when available), then every transcript line as
`[start-end] text` (seconds). For a long video, read it in parts with offset/limit.

Choose the moments. A good short:
- makes sense to someone who never saw the full video (no "as I said earlier");
- grabs attention in the first 3 seconds (bold claim, question, reaction, set-up of a joke);
- holds one complete idea, story, joke or reveal and ends right after the payoff;
- is within the requested length (default 20–60 s).

Rules: start at a line's start time and end at a line's end time (the tool snaps edges to
the nearest sentence anyway); no overlaps; best first; return fewer than asked rather
than weak ones. Prefer "most replayed" parts when their content also works alone.
Speech recognition makes mistakes, especially in Hindi; judge by meaning.

Write `clips/shorts-<id>/plan.json`:

```json
{
  "language": "hi",
  "video_type": "gaming_facecam",
  "shorts": [
    {
      "start": 312.4,
      "end": 356.9,
      "score": 82,
      "hook": "What grabs the viewer in the first 3 seconds",
      "hook_text": "Shown on screen at the top",
      "why": "Why this works on its own",
      "title": "Under 60 characters",
      "caption": "One-line caption for the post",
      "hashtags": ["#shorts", "#gta6"]
    }
  ]
}
```

`hook_text` is the headline burned in at the top of the short for its whole length, so
viewers know at once what it is about and stay to the end. Make it 3-8 words, under 40
characters, no emoji (the font has none); it is shown in CAPITALS on a yellow box. Tease the
payoff without giving it away: "How to escape the cops in GTA 6", "Look what's hiding in this
shot". Without `hook_text` the title is used; `--no-hook` turns the headline off.

Write `title`, `caption`, `hook_text` and `hashtags` in the audience's style: Hinglish for a Hindi
video, English for an English one. Then run the command again.

## Step 3 (Hindi videos only): write the Hinglish lines

The tool writes `work/short-NN.captions.txt` for each short: the spoken captions, one per
line, usually in Devanagari. For each one, write `work/short-NN.hinglish.txt` with
**exactly the same number of lines**, line for line:

- Transliterate, don't translate. Keep every word in the same order.
- Hinglish = Hindi in Roman letters as people type it on YouTube/WhatsApp:
  `bhai ye kya ho gaya`, `main nahi jaunga`, `accha hai`, `kar raha hai`.
- English words written in Devanagari become normal English: गेम → game, मिशन → mission.
- Words already in Roman letters stay as they are. Lowercase, except names.
- Keep the word count of each line the same as the input where you can, because the
  highlighted word is timed word by word. (If counts differ, that line just shows without
  the highlight. It still works.)
- Fix an obvious speech-recognition slip only when you are sure what was said.

Then run the command again. It renders the shorts.

## Step 4: report

The finished files are `clips/shorts-<id>/short-NN-<title>.mp4` (1080×1920, subtitles
burned in), each with a `.json` holding title, caption, hashtags and the subtitle text.
Tell the user each short's file, time range in the source, title and caption, the video type
and the layout each short got (in its `.json`: `layout`, `face_tracking`, `layout_source`).
Pull one frame with ffmpeg (`ffmpeg -ss 3 -i <short> -frames:v 1 -vf scale=360:-1 <scratchpad>/x.png`)
and look at it to check the layout (webcam fully in the top panel, no gameplay in it, face
not cut off) and the subtitles before reporting.

## Frame selector (the user chooses the frame)

A local page where the user picks the video type and drags the boxes: the webcam/face box
(top panel) and the gameplay box (bottom panel) for **split**, one 9:16 box for **crop**,
nothing for **fit**. It has face tracking on/off, the webcam panel height, "Find face in this
frame", a live phone preview with the headline and subtitle positions, and per-short layouts
("All shorts" or one short). **Save** writes `layout.json`; **Save & render** re-renders
(all shorts, or just the selected one) and plays the result in the page.

Open it for the user in the built-in browser pane with `preview_start` and the name
`frame-selector` (from `.claude/launch.json`), then navigate to
`http://localhost:8765/?p=shorts-<id>`. Outside Claude Code: `frames.bat` or
`python -m clipper.frames clips/shorts-<id>`. Offer it when the user wants to change what a
short shows, when the webcam box looks wrong, or for any `gaming_facecam` video.

Once the user has saved in the selector, `layout.json` has `"edited": true`: the tool then
never replaces their layout (not by `video_type` in plan.json, not by the full-screen
switch). Don't edit an edited `layout.json` yourself unless the user asks.

## Changing things afterwards

- Different moments: edit `plan.json` (or delete it and run again), then run again.
- Better Hinglish for one short: edit its `work/short-NN.hinglish.txt`, run again.
- Layout: use the frame selector, or `--layout split` (webcam on top, gameplay below,
  face tracked), `track` (9:16 crop following the face), `crop` (still centre crop), `fit`
  (whole frame on blur), `auto` (from the video type and `layout.json`, the default).
- Re-render some shorts only: `--only 2` or `--only 1,3`.
- `--auto` skips both judgement steps (picks by loudness / most replayed, rule-based Hinglish).
