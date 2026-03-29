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

  const words = hook.text.split(/\s+/);
  const framesPerWord = Math.floor((durationInFrames - 8) / words.length); // leave 8 frames for fadeout

  const renderBold = () => {
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
          top: 0, left: 0, right: 0, bottom: 0,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          flexDirection: "column",
          padding: "0 40px",
          opacity: fadeOut,
        }}
      >
        {/* Dark overlay */}
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
          background: "rgba(0,0,0,0.7)", zIndex: 0,
        }} />

        {/* Per-word flash */}
        {words.map((_, i) => {
          const wordStart = i * framesPerWord;
          const flashOp = interpolate(
            frame, [wordStart, wordStart + 2], [0.9, 0],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
          );
          return flashOp > 0 ? (
            <div key={`flash-${i}`} style={{
              position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
              background: "white", opacity: flashOp, zIndex: 1,
            }} />
          ) : null;
        })}

        {/* Red accent bars */}
        <div style={{
          position: "absolute", left: 25, top: "35%", width: 6, height: 180,
          background: "#ef4444", borderRadius: 3, zIndex: 2,
        }} />
        <div style={{
          position: "absolute", right: 25, top: "35%", width: 6, height: 180,
          background: "#ef4444", borderRadius: 3, zIndex: 2,
        }} />

        {/* Words — each slams in one at a time */}
        <div style={{
          display: "flex", flexWrap: "wrap", justifyContent: "center",
          gap: "8px 16px", zIndex: 3, maxWidth: 900,
        }}>
          {words.map((word, i) => {
            const wordStart = i * framesPerWord;
            const localFrame = frame - wordStart;

            // Don't show words that haven't appeared yet
            if (frame < wordStart) return (
              <span key={i} style={{ fontSize: 110, fontWeight: 900, opacity: 0 }}>{word}</span>
            );

            const slamScale = spring({
              frame: localFrame,
              fps,
              config: { damping: 5, stiffness: 400, mass: 0.25 },
            });
            const scaleVal = interpolate(slamScale, [0, 1], [6, 1]);

            const wordOpacity = interpolate(localFrame, [0, 1], [0, 1], {
              extrapolateRight: "clamp",
            });

            // Shake per word on impact
            const shake = localFrame < 4
              ? Math.sin(localFrame * 15) * interpolate(localFrame, [0, 4], [12, 0], { extrapolateRight: "clamp" })
              : 0;

            // Highlight the current word in red, previous words in white
            const isCurrent = frame >= wordStart && frame < wordStart + framesPerWord;
            const color = isCurrent ? "#ef4444" : "white";

            return (
              <span
                key={i}
                style={{
                  fontSize: 110,
                  fontWeight: 900,
                  color,
                  fontFamily: "sans-serif",
                  textTransform: "uppercase",
                  letterSpacing: -4,
                  lineHeight: 1.0,
                  opacity: wordOpacity,
                  transform: `scale(${scaleVal}) translateX(${shake}px)`,
                  textShadow: isCurrent
                    ? "0 0 40px rgba(239,68,68,0.8), 0 4px 20px rgba(0,0,0,0.9)"
                    : "0 0 30px rgba(0,0,0,1), 0 4px 15px rgba(0,0,0,0.8)",
                  display: "inline-block",
                }}
              >
                {word}
              </span>
            );
          })}
        </div>
      </div>
    );
  };

  const renderGlitch = () => {
    const fadeOut = interpolate(
      frame,
      [durationInFrames - 6, durationInFrames],
      [1, 0],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    // Continuous glitch
    const glitchActive = frame < 15 || (frame % 12 < 2);
    const gx = glitchActive ? Math.sin(frame * 18) * 10 : 0;
    const gy = glitchActive ? Math.cos(frame * 22) * 8 : 0;

    return (
      <div
        style={{
          position: "absolute",
          top: 0, left: 0, right: 0, bottom: 0,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          flexDirection: "column",
          padding: "0 40px",
          opacity: fadeOut,
        }}
      >
        {/* Flash */}
        {frame < 3 && (
          <div style={{
            position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
            background: "white", opacity: interpolate(frame, [0, 3], [1, 0]),
            zIndex: 0,
          }} />
        )}
        {/* Dark bg */}
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
          background: "rgba(0,0,0,0.7)", zIndex: 1,
        }} />

        {/* Glitch layers */}
        {[
          { color: "rgba(255,30,30,0.6)", dx: gx + 6, dy: gy + 4 },
          { color: "rgba(0,255,255,0.6)", dx: -gx - 6, dy: -gy - 4 },
        ].map((layer, li) => (
          <div key={li} style={{
            position: "absolute",
            display: "flex", flexWrap: "wrap", justifyContent: "center",
            gap: "8px 16px", maxWidth: 900, zIndex: 2,
            transform: `translate(${layer.dx}px, ${layer.dy}px)`,
          }}>
            {words.map((word, i) => {
              const wordStart = i * framesPerWord;
              if (frame < wordStart) return null;
              return (
                <span key={i} style={{
                  fontSize: 110, fontWeight: 900, color: layer.color,
                  fontFamily: "sans-serif", textTransform: "uppercase",
                  letterSpacing: -4, lineHeight: 1.0,
                }}>
                  {word}
                </span>
              );
            })}
          </div>
        ))}

        {/* Main text — word by word */}
        <div style={{
          display: "flex", flexWrap: "wrap", justifyContent: "center",
          gap: "8px 16px", zIndex: 3, maxWidth: 900,
        }}>
          {words.map((word, i) => {
            const wordStart = i * framesPerWord;
            if (frame < wordStart) return (
              <span key={i} style={{ fontSize: 110, fontWeight: 900, opacity: 0 }}>{word}</span>
            );

            const localFrame = frame - wordStart;
            const slam = spring({
              frame: localFrame, fps,
              config: { damping: 5, stiffness: 400, mass: 0.25 },
            });
            const scale = interpolate(slam, [0, 1], [5, 1]);
            const isCurrent = frame >= wordStart && frame < wordStart + framesPerWord;

            return (
              <span key={i} style={{
                fontSize: 110, fontWeight: 900,
                color: isCurrent ? "#ef4444" : "white",
                fontFamily: "sans-serif", textTransform: "uppercase",
                letterSpacing: -4, lineHeight: 1.0,
                transform: `scale(${scale})`,
                textShadow: "0 0 40px rgba(0,0,0,1), 0 4px 20px rgba(0,0,0,0.9)",
                display: "inline-block",
              }}>
                {word}
              </span>
            );
          })}
        </div>
      </div>
    );
  };

  const renderZoom = () => {
    const scale = interpolate(frame, [0, durationInFrames], [0.8, 1.15], {
      extrapolateRight: "clamp",
    });
    const opacity = interpolate(frame, [0, 3], [0, 1], { extrapolateRight: "clamp" });
    const fadeOut = interpolate(
      frame, [durationInFrames - 8, durationInFrames], [1, 0],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    return (
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
        display: "flex", justifyContent: "center", alignItems: "center",
        padding: "0 50px", opacity: opacity * fadeOut, transform: `scale(${scale})`,
      }}>
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
          background: "rgba(0,0,0,0.6)", opacity: fadeOut,
        }} />
        <div style={{
          fontSize: 100, fontWeight: 900, color: "white", textAlign: "center",
          textShadow: "0 4px 30px rgba(0,0,0,0.9), 0 0 60px rgba(255,255,255,0.1)",
          lineHeight: 1.1, fontFamily: "sans-serif", textTransform: "uppercase",
          letterSpacing: -3, zIndex: 1,
        }}>
          {hook.text}
        </div>
      </div>
    );
  };

  switch (hook.style) {
    case "glitch": return renderGlitch();
    case "zoom": return renderZoom();
    case "bold":
    default: return renderBold();
  }
};
