import React from "react";
import { Sequence, AbsoluteFill } from "remotion";
import { VideoProps } from "./types";
import { AnimatedText } from "./components/AnimatedText";
import { IconOverlay } from "./components/IconOverlay";
import { SceneTransition } from "./components/SceneTransition";
import { HookText } from "./components/HookText";
import { LottieCharacter } from "./components/LottieCharacter";
import { Captions } from "./components/Captions";

export const FinanceOverlay: React.FC<Record<string, unknown>> = (rawProps) => {
  const props = rawProps as unknown as VideoProps;
  const { scenes, hook, showCharacter } = props;

  return (
    <AbsoluteFill style={{ backgroundColor: "transparent" }}>
      {/* Hook overlay */}
      {hook && (
        <Sequence from={0} durationInFrames={hook.durationInFrames}>
          <HookText hook={hook} />
        </Sequence>
      )}

      {/* Scene overlays */}
      {scenes.map((scene) => (
        <Sequence
          key={scene.index}
          from={scene.startFrame}
          durationInFrames={scene.durationInFrames}
        >
          <SceneTransition durationInFrames={scene.durationInFrames}>
            <AbsoluteFill>
              {scene.textOverlay && (
                <AnimatedText
                  overlay={scene.textOverlay}
                  durationInFrames={scene.durationInFrames}
                  commentaryMode={showCharacter}
                />
              )}
              {scene.icon && (
                <IconOverlay
                  icon={scene.icon}
                  durationInFrames={scene.durationInFrames}
                />
              )}
              {showCharacter && (
                <LottieCharacter
                  durationInFrames={scene.durationInFrames}
                />
              )}
              {/* Word-by-word captions */}
              {scene.wordTimings && scene.wordTimings.length > 0 && (
                <Captions
                  words={scene.wordTimings}
                  durationInFrames={scene.durationInFrames}
                  commentaryMode={showCharacter}
                />
              )}
            </AbsoluteFill>
          </SceneTransition>
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
