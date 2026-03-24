import React from "react";
import {
  useCurrentFrame,
  interpolate,
  spring,
  useVideoConfig,
} from "remotion";
import { TextOverlayData } from "../types";

interface Props {
  overlay: TextOverlayData;
  durationInFrames: number;
  commentaryMode?: boolean;
}

export const AnimatedText: React.FC<Props> = ({ overlay, durationInFrames, commentaryMode = false }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const getPositionStyle = (): React.CSSProperties => {
    if (commentaryMode) {
      // In commentary mode, text stays in the upper 2/3 above the character panel
      switch (overlay.position) {
        case "top":
          return { top: 80, left: 0, right: 0 };
        case "bottom":
          return { top: 520, left: 0, right: 0 };
        case "center":
        default:
          return { top: 350, left: 0, right: 0, transform: "translateY(-50%)" };
      }
    }
    switch (overlay.position) {
      case "top":
        return { top: 120, left: 0, right: 0 };
      case "bottom":
        return { bottom: 200, left: 0, right: 0 };
      case "center":
      default:
        return { top: "50%", left: 0, right: 0, transform: "translateY(-50%)" };
    }
  };

  const renderTitle = () => {
    const scale = spring({ frame, fps, config: { damping: 12, stiffness: 100 } });
    const opacity = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" });
    const fadeOut = interpolate(
      frame,
      [durationInFrames - 15, durationInFrames],
      [1, 0],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    return (
      <div
        style={{
          position: "absolute",
          ...getPositionStyle(),
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          padding: "0 60px",
          opacity: opacity * fadeOut,
          transform: `${getPositionStyle().transform || ""} scale(${scale})`,
        }}
      >
        <div
          style={{
            fontSize: 72,
            fontWeight: 800,
            color: "white",
            textAlign: "center",
            textShadow: "0 4px 20px rgba(0,0,0,0.8), 0 2px 4px rgba(0,0,0,0.5)",
            lineHeight: 1.2,
            fontFamily: "sans-serif",
          }}
        >
          {overlay.content}
        </div>
      </div>
    );
  };

  const renderSubtitle = () => {
    const slideUp = interpolate(frame, [0, 20], [60, 0], { extrapolateRight: "clamp" });
    const opacity = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: "clamp" });
    const fadeOut = interpolate(
      frame,
      [durationInFrames - 15, durationInFrames],
      [1, 0],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    return (
      <div
        style={{
          position: "absolute",
          ...getPositionStyle(),
          display: "flex",
          justifyContent: "center",
          padding: "0 60px",
          opacity: opacity * fadeOut,
          transform: `translateY(${slideUp}px)`,
        }}
      >
        <div
          style={{
            fontSize: 48,
            fontWeight: 600,
            color: "white",
            textAlign: "center",
            textShadow: "0 3px 15px rgba(0,0,0,0.7)",
            fontFamily: "sans-serif",
          }}
        >
          {overlay.content}
        </div>
      </div>
    );
  };

  const renderLowerThird = () => {
    const barWidth = interpolate(frame, [0, 15], [0, 100], { extrapolateRight: "clamp" });
    const textOpacity = interpolate(frame, [10, 25], [0, 1], { extrapolateRight: "clamp" });
    const fadeOut = interpolate(
      frame,
      [durationInFrames - 15, durationInFrames],
      [1, 0],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    return (
      <div
        style={{
          position: "absolute",
          bottom: 200,
          left: 40,
          right: 40,
          opacity: fadeOut,
        }}
      >
        {/* Accent bar */}
        <div
          style={{
            height: 4,
            background: "linear-gradient(90deg, #00d2ff, #3a7bd5)",
            width: `${barWidth}%`,
            marginBottom: 12,
            borderRadius: 2,
          }}
        />
        {/* Background panel */}
        <div
          style={{
            background: "rgba(0, 0, 0, 0.7)",
            backdropFilter: "blur(10px)",
            borderRadius: 12,
            padding: "20px 30px",
            opacity: textOpacity,
          }}
        >
          <div
            style={{
              fontSize: 42,
              fontWeight: 700,
              color: "white",
              fontFamily: "sans-serif",
            }}
          >
            {overlay.content}
          </div>
        </div>
      </div>
    );
  };

  const renderTypewriter = () => {
    const charsToShow = Math.floor(
      interpolate(frame, [0, durationInFrames * 0.6], [0, overlay.content.length], {
        extrapolateRight: "clamp",
      })
    );
    const fadeOut = interpolate(
      frame,
      [durationInFrames - 15, durationInFrames],
      [1, 0],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );
    const displayText = overlay.content.slice(0, charsToShow);
    const showCursor = frame % 20 < 10 && charsToShow < overlay.content.length;

    return (
      <div
        style={{
          position: "absolute",
          ...getPositionStyle(),
          display: "flex",
          justifyContent: "center",
          padding: "0 60px",
          opacity: fadeOut,
        }}
      >
        <div
          style={{
            fontSize: 52,
            fontWeight: 700,
            color: "white",
            textAlign: "center",
            textShadow: "0 3px 15px rgba(0,0,0,0.7)",
            fontFamily: "monospace",
          }}
        >
          {displayText}
          {showCursor && (
            <span style={{ color: "#00d2ff" }}>|</span>
          )}
        </div>
      </div>
    );
  };

  switch (overlay.style) {
    case "title":
      return renderTitle();
    case "subtitle":
      return renderSubtitle();
    case "lower_third":
      return renderLowerThird();
    case "typewriter":
      return renderTypewriter();
    default:
      return renderTitle();
  }
};
