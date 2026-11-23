import { loadFont as loadBlack } from "@remotion/google-fonts/ArchivoBlack";
import { loadFont as loadDisplay } from "@remotion/google-fonts/BricolageGrotesque";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";
import { loadFont as loadHindi } from "@remotion/google-fonts/NotoSansDevanagari";
import { Easing } from "remotion";

export const display = loadDisplay("normal", { weights: ["500", "800"], subsets: ["latin"] }).fontFamily;
export const mono = loadMono("normal", { weights: ["700"], subsets: ["latin"] }).fontFamily;
export const black = loadBlack("normal", { weights: ["400"], subsets: ["latin"] }).fontFamily;
export const hindi = loadHindi("normal", { weights: ["700"], subsets: ["devanagari"] }).fontFamily;

export const c = {
  bg: "#0C1B1F",
  panel: "#13292F",
  line: "#2A4A52",
  text: "#F4F1E8",
  mute: "#93AEB1",
  yellow: "#FFE500", // the tool's own headline and subtitle highlight colour
  coral: "#FF5D4D",
  mint: "#4FE0A8",
  sky: "#5FB4D9",
};

export const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
export const out = Easing.bezier(0.16, 1, 0.3, 1);
export const inOut = Easing.bezier(0.65, 0, 0.35, 1);
