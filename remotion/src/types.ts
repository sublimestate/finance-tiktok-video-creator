export interface TextOverlayData {
  content: string;
  style: "title" | "subtitle" | "lower_third" | "typewriter";
  position: "center" | "top" | "bottom";
}

export interface HookData {
  text: string;
  durationInFrames: number;
  style: "bold" | "glitch" | "zoom";
}

export interface SceneData {
  index: number;
  durationInFrames: number;
  startFrame: number;
  narration: string;
  textOverlay: TextOverlayData | null;
  icon: string | null;
}

export interface VideoProps {
  hook: HookData | null;
  scenes: SceneData[];
  totalDurationInFrames: number;
  fps: number;
  width: number;
  height: number;
  showCharacter: boolean;
}
