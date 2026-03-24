import React from "react";
import { useCurrentFrame, interpolate } from "remotion";

interface Props {
  durationInFrames: number;
  children: React.ReactNode;
}

const FADE_FRAMES = 10;

export const SceneTransition: React.FC<Props> = ({ durationInFrames, children }) => {
  const frame = useCurrentFrame();

  const fadeIn = interpolate(frame, [0, FADE_FRAMES], [0, 1], {
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(
    frame,
    [durationInFrames - FADE_FRAMES, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <div style={{ opacity: fadeIn * fadeOut, width: "100%", height: "100%" }}>
      {children}
    </div>
  );
};
