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
    // Slam in effect — scale from 5x to 1x with aggressive spring
    const scale = spring({
      frame,
      fps,
      config: { damping: 6, stiffness: 300, mass: 0.3 },
    });
    const scaleValue = interpolate(scale, [0, 1], [5, 1]);
    const opacity = interpolate(frame, [0, 1], [0, 1], {
      extrapolateRight: "clamp",
    });
    const fadeOut = interpolate(
      frame,
      [durationInFrames - 6, durationInFrames],
      [1, 0],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    // Aggressive shake on impact
    const shake =
      frame < 8
        ? Math.sin(frame * 12) * interpolate(frame, [0, 8], [15, 0], { extrapolateRight: "clamp" })
        : 0;

    // White flash on frame 0-2
    const flashOpacity = interpolate(frame, [0, 3], [0.8, 0], {
      extrapolateRight: "clamp",
    });

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
          padding: "0 40px",
          opacity: opacity * fadeOut,
          transform: `scale(${scaleValue}) translateX(${shake}px)`,
        }}
      >
        {/* White flash */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "white",
            opacity: flashOpacity,
            zIndex: 0,
          }}
        />
        {/* Dark overlay */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,0.6)",
            opacity: fadeOut,
            zIndex: 1,
          }}
        />
        {/* Red accent bar */}
        <div
          style={{
            position: "absolute",
            top: "42%",
            left: 30,
            width: 6,
            height: 120,
            background: "#ef4444",
            borderRadius: 3,
            opacity: fadeOut,
            zIndex: 2,
          }}
        />
        <div
          style={{
            fontSize: 100,
            fontWeight: 900,
            color: "white",
            textAlign: "center",
            textShadow:
              "0 0 60px rgba(0,0,0,1), 0 6px 30px rgba(0,0,0,0.9), 0 0 100px rgba(239,68,68,0.4)",
            lineHeight: 1.05,
            fontFamily: "sans-serif",
            textTransform: "uppercase",
            letterSpacing: -3,
            zIndex: 3,
          }}
        >
          {hook.text}
        </div>
      </div>
    );
  };

  const renderGlitch = () => {
    const opacity = interpolate(frame, [0, 1], [0, 1], {
      extrapolateRight: "clamp",
    });
    const fadeOut = interpolate(
      frame,
      [durationInFrames - 6, durationInFrames],
      [1, 0],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    // White flash
    const flashOpacity = interpolate(frame, [0, 3], [0.9, 0], {
      extrapolateRight: "clamp",
    });

    // Aggressive glitch offset — keeps glitching throughout
    const glitchActive = frame < 15 || (frame % 20 < 3);
    const glitchX = glitchActive ? Math.sin(frame * 15) * 8 : 0;
    const glitchY = glitchActive ? Math.cos(frame * 18) * 6 : 0;

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
        {/* White flash */}
        <div
          style={{
            position: "absolute",
            top: 0, left: 0, right: 0, bottom: 0,
            background: "white",
            opacity: flashOpacity,
            zIndex: 0,
          }}
        />
        <div
          style={{
            position: "absolute",
            top: 0, left: 0, right: 0, bottom: 0,
            background: "rgba(0,0,0,0.6)",
            opacity: fadeOut,
            zIndex: 1,
          }}
        />
        {/* Red glitch layer */}
        <div
          style={{
            position: "absolute",
            fontSize: 100,
            fontWeight: 900,
            color: "rgba(255,30,30,0.6)",
            textAlign: "center",
            textTransform: "uppercase",
            letterSpacing: -3,
            fontFamily: "sans-serif",
            transform: `translate(${glitchX + 5}px, ${glitchY + 3}px)`,
            zIndex: 2,
          }}
        >
          {hook.text}
        </div>
        {/* Cyan glitch layer */}
        <div
          style={{
            position: "absolute",
            fontSize: 100,
            fontWeight: 900,
            color: "rgba(0,255,255,0.6)",
            textAlign: "center",
            textTransform: "uppercase",
            letterSpacing: -3,
            fontFamily: "sans-serif",
            transform: `translate(${-glitchX - 5}px, ${-glitchY - 3}px)`,
            zIndex: 2,
          }}
        >
          {hook.text}
        </div>
        {/* Main white text */}
        <div
          style={{
            fontSize: 100,
            fontWeight: 900,
            color: "white",
            textAlign: "center",
            textTransform: "uppercase",
            letterSpacing: -3,
            lineHeight: 1.05,
            fontFamily: "sans-serif",
            textShadow: "0 0 60px rgba(0,0,0,1), 0 6px 30px rgba(0,0,0,0.9)",
            zIndex: 3,
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
