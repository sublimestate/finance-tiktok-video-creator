import React from "react";
import {
  useCurrentFrame,
  interpolate,
  spring,
  useVideoConfig,
} from "remotion";

interface Props {
  isTalking: boolean;
  durationInFrames: number;
}

export const AvatarCharacter: React.FC<Props> = ({ isTalking, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Entrance: slide up
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

  // Mouth — natural multi-frequency
  const mouthBase = isTalking
    ? (
        Math.abs(Math.sin(frame * 0.55)) * 0.35 +
        Math.abs(Math.sin(frame * 0.9)) * 0.35 +
        Math.abs(Math.cos(frame * 0.35)) * 0.3
      )
    : 0.05;
  const mouthOpen = Math.min(mouthBase, 1.0);

  // Head tilt
  const headTilt = isTalking
    ? Math.sin(frame * 0.12) * 3
    : Math.sin(frame * 0.04) * 1;

  // Body bob
  const bodyBob = isTalking
    ? Math.sin(frame * 0.22) * 4
    : Math.sin(frame * 0.06) * 1;

  // Hand gesture
  const handY = isTalking
    ? interpolate(Math.sin(frame * 0.18), [-1, 1], [0, -30])
    : 0;
  const handRotate = isTalking
    ? Math.sin(frame * 0.22) * 8
    : 0;

  // Blink
  const blinkPeriod = 85 + Math.floor(Math.sin(frame * 0.01) * 25);
  const blinkCycle = frame % blinkPeriod;
  const isBlinking = blinkCycle >= 0 && blinkCycle <= 4;
  const eyeScaleY = isBlinking
    ? interpolate(blinkCycle, [0, 2, 4], [1, 0.05, 1])
    : 1;

  // Eyebrow raise
  const browRaise = isTalking
    ? Math.max(0, Math.sin(frame * 0.16)) * 6
    : 0;

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
      {/* Panel background — gradient */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: 640,
          background: "linear-gradient(to top, rgba(10,15,30,0.95) 0%, rgba(10,15,30,0.85) 60%, rgba(10,15,30,0) 100%)",
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

      {/* Character SVG — centered in panel */}
      <div
        style={{
          position: "absolute",
          bottom: 20,
          left: "50%",
          transform: `translateX(-50%) translateY(${bodyBob}px)`,
          width: 500,
          height: 550,
        }}
      >
        <svg
          width="500"
          height="550"
          viewBox="0 0 500 550"
          xmlns="http://www.w3.org/2000/svg"
        >
          {/* === BODY === */}
          {/* Torso */}
          <path
            d="M 130,420 Q 130,380 170,360 L 250,340 L 330,360 Q 370,380 370,420 L 370,550 L 130,550 Z"
            fill="#1e40af"
          />
          {/* Shirt */}
          <path
            d="M 210,340 L 250,380 L 290,340"
            fill="none"
            stroke="white"
            strokeWidth="3"
          />
          {/* Tie */}
          <polygon points="250,345 238,395 262,395" fill="#f59e0b" />
          <polygon points="250,395 240,420 260,420" fill="#d97706" />
          {/* Lapels */}
          <path d="M 210,340 L 180,420" fill="none" stroke="#1e3a8a" strokeWidth="3" />
          <path d="M 290,340 L 320,420" fill="none" stroke="#1e3a8a" strokeWidth="3" />

          {/* === LEFT ARM === */}
          <g transform={`translate(0, ${handY}) rotate(${handRotate}, 120, 400)`}>
            <path
              d="M 130,400 Q 95,370 85,330"
              fill="none"
              stroke="#1e40af"
              strokeWidth="26"
              strokeLinecap="round"
            />
            {/* Hand */}
            <ellipse cx="82" cy="325" rx="18" ry="14" fill="#f5a623"
              transform={`rotate(${-15 + handRotate * 0.5}, 82, 325)`} />
            {/* Fingers */}
            <path d="M 70,318 L 65,308" stroke="#f5a623" strokeWidth="7" strokeLinecap="round" />
            <path d="M 78,314 L 75,302" stroke="#f5a623" strokeWidth="7" strokeLinecap="round" />
            <path d="M 88,314 L 88,302" stroke="#f5a623" strokeWidth="7" strokeLinecap="round" />
          </g>

          {/* === RIGHT ARM === */}
          <path
            d="M 370,400 Q 395,420 400,460"
            fill="none"
            stroke="#1e40af"
            strokeWidth="26"
            strokeLinecap="round"
          />

          {/* === NECK === */}
          <rect x="232" y="305" width="36" height="45" rx="8" fill="#f5a623" />

          {/* === HEAD GROUP === */}
          <g transform={`rotate(${headTilt}, 250, 200)`}>
            {/* Head */}
            <ellipse cx="250" cy="190" rx="105" ry="115" fill="#fbbf24" />

            {/* Ears */}
            <ellipse cx="143" cy="200" rx="18" ry="28" fill="#f5a623" />
            <ellipse cx="143" cy="200" rx="10" ry="18" fill="#e8961d" />
            <ellipse cx="357" cy="200" rx="18" ry="28" fill="#f5a623" />
            <ellipse cx="357" cy="200" rx="10" ry="18" fill="#e8961d" />

            {/* Hair */}
            <ellipse cx="250" cy="100" rx="98" ry="52" fill="#1e293b" />
            <path d="M 152,105 Q 148,150 155,175" fill="none" stroke="#1e293b" strokeWidth="24" strokeLinecap="round" />
            <path d="M 348,105 Q 352,150 345,175" fill="none" stroke="#1e293b" strokeWidth="24" strokeLinecap="round" />
            {/* Hair detail */}
            <path d="M 190,75 Q 250,60 310,75" fill="none" stroke="#334155" strokeWidth="4" opacity="0.3" />
            <path d="M 200,85 Q 250,72 300,85" fill="none" stroke="#334155" strokeWidth="3" opacity="0.2" />

            {/* === GLASSES === */}
            <rect x="170" y="160" width="62" height="56" rx="12" fill="rgba(200,230,255,0.12)" stroke="#475569" strokeWidth="4" />
            <rect x="268" y="160" width="62" height="56" rx="12" fill="rgba(200,230,255,0.12)" stroke="#475569" strokeWidth="4" />
            <line x1="232" y1="186" x2="268" y2="186" stroke="#475569" strokeWidth="4" />
            {/* Temple arms */}
            <line x1="170" y1="178" x2="148" y2="185" stroke="#475569" strokeWidth="3" />
            <line x1="330" y1="178" x2="352" y2="185" stroke="#475569" strokeWidth="3" />
            {/* Lens glare */}
            <path d="M 180,168 L 195,175" stroke="rgba(255,255,255,0.3)" strokeWidth="2.5" strokeLinecap="round" />
            <path d="M 278,168 L 293,175" stroke="rgba(255,255,255,0.3)" strokeWidth="2.5" strokeLinecap="round" />

            {/* === EYEBROWS === */}
            <path
              d={`M 175,${158 - browRaise} Q 201,${145 - browRaise} 227,${152 - browRaise}`}
              fill="none" stroke="#1e293b" strokeWidth="6" strokeLinecap="round"
            />
            <path
              d={`M 273,${152 - browRaise} Q 299,${145 - browRaise} 325,${158 - browRaise}`}
              fill="none" stroke="#1e293b" strokeWidth="6" strokeLinecap="round"
            />

            {/* === EYES === */}
            <g transform={`translate(201, 185) scale(1, ${eyeScaleY})`}>
              <ellipse cx="0" cy="0" rx="15" ry="16" fill="white" />
              <ellipse cx="2" cy="1" rx="10" ry="11" fill="#1e293b" />
              <circle cx="5" cy="-4" r="4" fill="white" />
              <circle cx="-2" cy="4" r="2" fill="white" opacity="0.4" />
            </g>
            <g transform={`translate(299, 185) scale(1, ${eyeScaleY})`}>
              <ellipse cx="0" cy="0" rx="15" ry="16" fill="white" />
              <ellipse cx="2" cy="1" rx="10" ry="11" fill="#1e293b" />
              <circle cx="5" cy="-4" r="4" fill="white" />
              <circle cx="-2" cy="4" r="2" fill="white" opacity="0.4" />
            </g>

            {/* === NOSE === */}
            <ellipse cx="250" cy="225" rx="10" ry="8" fill="#e8961d" />
            <circle cx="243" cy="229" r="4" fill="#d4880e" opacity="0.3" />
            <circle cx="257" cy="229" r="4" fill="#d4880e" opacity="0.3" />

            {/* === CHEEKS === */}
            <ellipse cx="170" cy="235" rx="22" ry="14" fill="rgba(255,140,140,0.2)" />
            <ellipse cx="330" cy="235" rx="22" ry="14" fill="rgba(255,140,140,0.2)" />

            {/* === MOUTH === */}
            {mouthOpen < 0.12 ? (
              <path
                d="M 220,255 Q 250,268 280,255"
                fill="none" stroke="#b91c1c" strokeWidth="4" strokeLinecap="round"
              />
            ) : (
              <g>
                <ellipse
                  cx="250"
                  cy={255 + mouthOpen * 5}
                  rx={18 + mouthOpen * 16}
                  ry={4 + mouthOpen * 20}
                  fill="#991b1b"
                />
                {/* Inner mouth */}
                <ellipse
                  cx="250"
                  cy={258 + mouthOpen * 6}
                  rx={14 + mouthOpen * 12}
                  ry={2 + mouthOpen * 14}
                  fill="#7f1d1d"
                />
                {/* Tongue */}
                {mouthOpen > 0.4 && (
                  <ellipse
                    cx="250"
                    cy={262 + mouthOpen * 8}
                    rx={10 + mouthOpen * 5}
                    ry={mouthOpen * 8}
                    fill="#dc2626"
                  />
                )}
                {/* Upper teeth */}
                <rect
                  x={238 - mouthOpen * 6}
                  y={252 + mouthOpen * 2}
                  width={24 + mouthOpen * 12}
                  height={Math.min(mouthOpen * 10, 10)}
                  rx="3"
                  fill="white"
                />
                {/* Lower teeth */}
                {mouthOpen > 0.5 && (
                  <rect
                    x={242 - mouthOpen * 3}
                    y={260 + mouthOpen * 14}
                    width={16 + mouthOpen * 6}
                    height={Math.min(mouthOpen * 6, 6)}
                    rx="2"
                    fill="white"
                    opacity="0.85"
                  />
                )}
              </g>
            )}
          </g>
        </svg>
      </div>
    </div>
  );
};
