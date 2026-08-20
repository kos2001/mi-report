import { ImageResponse } from "next/og";

// iOS 홈 화면 아이콘 — icon.tsx 와 같은 디자인을 더 큰 캔버스·여백으로.
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#09090b",
          fontFamily: "sans-serif",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            fontSize: 92,
            fontWeight: 700,
            letterSpacing: -3,
            color: "#38bdf8",
          }}
        >
          MI
        </div>
      </div>
    ),
    { ...size },
  );
}
