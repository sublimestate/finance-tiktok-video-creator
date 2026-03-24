import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";

interface WordTiming {
  word: string;
  startFrame: number;  // global frame numbers
  endFrame: number;
}

interface Props {
  words: WordTiming[];
  durationInFrames: number;
  commentaryMode?: boolean;
}

const WORDS_PER_GROUP = 4;

export const Captions: React.FC<Props> = ({ words, durationInFrames, commentaryMode = false }) => {
  const frame = useCurrentFrame();  // local frame within the Sequence

  if (!words || words.length === 0) return null;

  // Convert global frames to local (relative to scene start)
  const sceneStartFrame = words.length > 0 ? Math.min(...words.map(w => w.startFrame)) : 0;
  // Offset needed to map scene start to 0
  const offset = sceneStartFrame;

  const localWords = words.map(w => ({
    ...w,
    startFrame: w.startFrame - offset,
    endFrame: w.endFrame - offset,
  }));

  // Group words into chunks for display
  const groups: typeof localWords[] = [];
  for (let i = 0; i < localWords.length; i += WORDS_PER_GROUP) {
    groups.push(localWords.slice(i, i + WORDS_PER_GROUP));
  }

  // Find which group is currently active
  let activeGroupIndex = 0;
  for (let i = 0; i < groups.length; i++) {
    const group = groups[i];
    const groupStart = group[0].startFrame;
    const groupEnd = group[group.length - 1].endFrame;
    if (frame >= groupStart && frame <= groupEnd + 5) {
      activeGroupIndex = i;
    }
  }

  const activeGroup = groups[activeGroupIndex];
  if (!activeGroup) return null;

  const groupStart = activeGroup[0].startFrame;
  const groupEnd = activeGroup[activeGroup.length - 1].endFrame;

  // Fade in/out for group
  const groupOpacity = interpolate(
    frame,
    [groupStart - 3, groupStart, groupEnd, groupEnd + 5],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // Position — in commentary mode, above the character panel
  const yPosition = commentaryMode ? 480 : 1100;

  return (
    <div
      style={{
        position: "absolute",
        top: yPosition,
        left: 40,
        right: 40,
        display: "flex",
        justifyContent: "center",
        flexWrap: "wrap",
        gap: 8,
        opacity: groupOpacity,
      }}
    >
      {/* Background pill */}
      <div
        style={{
          position: "absolute",
          top: -12,
          left: "50%",
          transform: "translateX(-50%)",
          background: "rgba(0, 0, 0, 0.75)",
          borderRadius: 16,
          padding: "14px 28px",
          backdropFilter: "blur(8px)",
          display: "flex",
          gap: 10,
          justifyContent: "center",
          flexWrap: "wrap",
        }}
      >
        {activeGroup.map((wordData, i) => {
          const isActive = frame >= wordData.startFrame && frame <= wordData.endFrame;
          const wasSpoken = frame > wordData.endFrame;

          // Scale pop on the active word
          const wordScale = isActive
            ? interpolate(
                frame,
                [wordData.startFrame, wordData.startFrame + 3],
                [0.9, 1.1],
                { extrapolateRight: "clamp" }
              )
            : 1;

          return (
            <span
              key={`${activeGroupIndex}-${i}`}
              style={{
                fontSize: 52,
                fontWeight: 800,
                fontFamily: "sans-serif",
                color: isActive ? "#facc15" : wasSpoken ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0.5)",
                transform: `scale(${wordScale})`,
                transition: "color 0.1s",
                textShadow: isActive ? "0 0 20px rgba(250,204,21,0.5)" : "none",
                lineHeight: 1.3,
              }}
            >
              {wordData.word}
            </span>
          );
        })}
      </div>
    </div>
  );
};
