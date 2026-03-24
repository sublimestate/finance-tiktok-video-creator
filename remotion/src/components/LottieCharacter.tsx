import React, { useEffect, useState } from "react";
import { Lottie, LottieAnimationData } from "@remotion/lottie";
import {
  useCurrentFrame,
  interpolate,
  spring,
  useVideoConfig,
  cancelRender,
  continueRender,
  delayRender,
  staticFile,
} from "remotion";

interface Props {
  durationInFrames: number;
}

export const LottieCharacter: React.FC<Props> = ({ durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const [handle] = useState(() => delayRender("Loading Lottie character"));
  const [animationData, setAnimationData] = useState<LottieAnimationData | null>(null);

  useEffect(() => {
    fetch(staticFile("character.json"))
      .then((res) => res.json())
      .then((json) => {
        setAnimationData(json);
        continueRender(handle);
      })
      .catch((err) => {
        // If Lottie file not found, just continue without it
        console.error("Failed to load Lottie character:", err);
        continueRender(handle);
      });
  }, [handle]);

  // Entrance slide up
  const enterProgress = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 80 },
  });
  const enterY = interpolate(enterProgress, [0, 1], [200, 0]);

  // Exit
  const exitOpacity = interpolate(
    frame,
    [durationInFrames - 12, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  if (!animationData) return null;

  return (
    <div
      style={{
        position: "absolute",
        bottom: 0,
        left: 0,
        right: 0,
        height: 640,
        opacity: exitOpacity,
        transform: `translateY(${enterY}px)`,
      }}
    >
      {/* Panel background */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: 640,
          background:
            "linear-gradient(to top, rgba(10,15,30,0.95) 0%, rgba(10,15,30,0.85) 60%, rgba(10,15,30,0) 100%)",
        }}
      />

      {/* Accent line */}
      <div
        style={{
          position: "absolute",
          bottom: 580,
          left: 40,
          right: 40,
          height: 3,
          background: "linear-gradient(90deg, #3b82f6, #f59e0b, #3b82f6)",
          borderRadius: 2,
          opacity: 0.8,
        }}
      />

      {/* Lottie character — centered in panel */}
      <div
        style={{
          position: "absolute",
          bottom: 20,
          left: "50%",
          transform: "translateX(-50%)",
          width: 400,
          height: 500,
        }}
      >
        <Lottie
          animationData={animationData}
          loop
          style={{ width: "100%", height: "100%" }}
        />
      </div>
    </div>
  );
};
