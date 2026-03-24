import { registerRoot, Composition } from "remotion";
import React from "react";
import { FinanceOverlay } from "./Video";

const Root: React.FC = () => {
  return (
    <>
      <Composition
        id="FinanceOverlay"
        component={FinanceOverlay}
        durationInFrames={300}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{
          scenes: [],
          hook: null,
          totalDurationInFrames: 300,
          fps: 30,
          width: 1080,
          height: 1920,
          showCharacter: false,
        }}
        calculateMetadata={async ({ props }) => {
          return {
            durationInFrames: (props as any).totalDurationInFrames || 300,
            fps: (props as any).fps || 30,
            width: (props as any).width || 1080,
            height: (props as any).height || 1920,
          };
        }}
      />
    </>
  );
};

registerRoot(Root);
