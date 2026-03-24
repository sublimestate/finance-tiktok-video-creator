import React from "react";
import {
  useCurrentFrame,
  interpolate,
  spring,
  useVideoConfig,
} from "remotion";
import { HookData } from "../types";

interface Props {
  hook: HookData;
}

export const HookText: React.FC<Props> = ({ hook }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { durationInFrames } = hook;

  const renderBold = () => {
    // Slam in effect — scale from 3x to 1x with spring
    const scale = spring({
      frame,
      fps,
      config: { damping: 8, stiffness: 200, mass: 0.4 },
    });
    const scaleValue = interpolate(scale, [0, 1], [3, 1]);
    const opacity = interpolate(frame, [0, 3], [0, 1], {
      extrapolateRight: "clamp",
    });
    const fadeOut = interpolate(
      frame,
      [durationInFrames - 8, durationInFrames],
      [1, 0],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    // Subtle shake on impact
    const shake =
      frame < 6
        ? Math.sin(frame * 8) * interpolate(frame, [0, 6], [8, 0], { extrapolateRight: "clamp" })
        : 0;

    return (
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          padding: "0 50px",
          opacity: opacity * fadeOut,
          transform: `scale(${scaleValue}) translateX(${shake}px)`,
        }}
      >
        {/* Dark overlay behind text for contrast */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,0.4)",
            opacity: fadeOut,
          }}
        />
        <div
          style={{
            fontSize: 88,
            fontWeight: 900,
            color: "white",
            textAlign: "center",
            textShadow:
              "0 0 40px rgba(0,0,0,0.9), 0 4px 20px rgba(0,0,0,0.8), 0 0 80px rgba(0,100,255,0.3)",
            lineHeight: 1.1,
            fontFamily: "sans-serif",
            textTransform: "uppercase",
            letterSpacing: -2,
            zIndex: 1,
          }}
        >
          {hook.text}
        </div>
      </div>
    );
  };

  const renderGlitch = () => {
    const opacity = interpolate(frame, [0, 2], [0, 1], {
      extrapolateRight: "clamp",
    });
    const fadeOut = interpolate(
      frame,
      [durationInFrames - 8, durationInFrames],
      [1, 0],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    // Glitch offset
    const glitchX = frame < 10 ? Math.sin(frame * 12) * 4 : 0;
    const glitchY = frame < 10 ? Math.cos(frame * 15) * 3 : 0;

    return (
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          padding: "0 50px",
          opacity: opacity * fadeOut,
        }}
      >
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,0.4)",
            opacity: fadeOut,
          }}
        />
        {/* Red glitch layer */}
        <div
          style={{
            position: "absolute",
            fontSize: 88,
            fontWeight: 900,
            color: "rgba(255,0,0,0.5)",
            textAlign: "center",
            textTransform: "uppercase",
            letterSpacing: -2,
            fontFamily: "sans-serif",
            transform: `translate(${glitchX + 3}px, ${glitchY + 2}px)`,
            zIndex: 1,
          }}
        >
          {hook.text}
        </div>
        {/* Cyan glitch layer */}
        <div
          style={{
            position: "absolute",
            fontSize: 88,
            fontWeight: 900,
            color: "rgba(0,255,255,0.5)",
            textAlign: "center",
            textTransform: "uppercase",
            letterSpacing: -2,
            fontFamily: "sans-serif",
            transform: `translate(${-glitchX - 3}px, ${-glitchY - 2}px)`,
            zIndex: 1,
          }}
        >
          {hook.text}
        </div>
        {/* Main white text */}
        <div
          style={{
            fontSize: 88,
            fontWeight: 900,
            color: "white",
            textAlign: "center",
            textTransform: "uppercase",
            letterSpacing: -2,
            lineHeight: 1.1,
            fontFamily: "sans-serif",
            textShadow: "0 4px 20px rgba(0,0,0,0.8)",
            zIndex: 2,
          }}
        >
          {hook.text}
        </div>
      </div>
    );
  };

  const renderZoom = () => {
    // Continuous slow zoom from 0.8 to 1.1
    const scale = interpolate(frame, [0, durationInFrames], [0.8, 1.1], {
      extrapolateRight: "clamp",
    });
    const opacity = interpolate(frame, [0, 5], [0, 1], {
      extrapolateRight: "clamp",
    });
    const fadeOut = interpolate(
      frame,
      [durationInFrames - 8, durationInFrames],
      [1, 0],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    return (
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          padding: "0 50px",
          opacity: opacity * fadeOut,
          transform: `scale(${scale})`,
        }}
      >
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,0.4)",
            opacity: fadeOut,
          }}
        />
        <div
          style={{
            fontSize: 88,
            fontWeight: 900,
            color: "white",
            textAlign: "center",
            textShadow: "0 4px 30px rgba(0,0,0,0.9), 0 0 60px rgba(255,255,255,0.1)",
            lineHeight: 1.1,
            fontFamily: "sans-serif",
            textTransform: "uppercase",
            letterSpacing: -2,
            zIndex: 1,
          }}
        >
          {hook.text}
        </div>
      </div>
    );
  };

  switch (hook.style) {
    case "glitch":
      return renderGlitch();
    case "zoom":
      return renderZoom();
    case "bold":
    default:
      return renderBold();
  }
};
