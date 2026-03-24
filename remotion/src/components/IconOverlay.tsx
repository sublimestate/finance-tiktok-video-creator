import React from "react";
import { useCurrentFrame, spring, useVideoConfig, interpolate } from "remotion";

interface Props {
  icon: string;
  durationInFrames: number;
}

const ICON_MAP: Record<string, string> = {
  warning: "⚠️",
  chart: "📈",
  dollar: "💰",
  piggy: "🐷",
  card: "💳",
  book: "📚",
  rocket: "🚀",
  target: "🎯",
  fire: "🔥",
  check: "✅",
  cross: "❌",
  lightbulb: "💡",
  clock: "⏰",
  house: "🏠",
  car: "🚗",
  graduation: "🎓",
};

export const IconOverlay: React.FC<Props> = ({ icon, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({
    frame: frame - 5,
    fps,
    config: { damping: 10, stiffness: 150, mass: 0.5 },
  });
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 15, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const emoji = ICON_MAP[icon] || "💰";

  return (
    <div
      style={{
        position: "absolute",
        top: 140,
        right: 60,
        fontSize: 80,
        opacity: fadeOut,
        transform: `scale(${scale})`,
      }}
    >
      {emoji}
    </div>
  );
};
