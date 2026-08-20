import { ImageResponse } from "next/og";

// 앱 파비콘/탭 아이콘 — 사이드바 브랜드 색(zinc-950 배경 + sky 액센트)과 맞춘
// "MI" 뱃지. 정적 이미지 대신 코드로 생성해 별도 이미지 에셋 없이 유지보수한다.
export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
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
          borderRadius: 7,
          fontFamily: "sans-serif",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            fontSize: 17,
            fontWeight: 700,
            letterSpacing: -0.5,
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
