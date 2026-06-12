// MI Report Agent 도메인 모델 + 목업 데이터.
// 백엔드 연동 시 이 파일의 export 함수들을 API 호출로 교체한다.

export type ImpactLevel = "high" | "medium" | "low";
export type Sentiment = "positive" | "neutral" | "negative";

export interface Topic {
  id: string;
  title: string;
  category: "SET" | "반도체 설계" | "반도체 제조" | "수요/시황";
  summary: string;
  insight: string;
  sourceCount: number;
  updatedAt: string;
  history: { date: string; event: string; source: string }[];
}

export interface DigestItem {
  id: string;
  title: string;
  source: string;
  publishedAt: string;
  summary: string;
  slsiRelevance: string; // S.LSI 제품군 연관성
  demandImpact: string; // 수요 변동 영향
  risk: string;
  impact: ImpactLevel;
  tags: string[];
}

export interface Digest {
  id: string;
  issueNo: number;
  period: string;
  mailedAt: string | null; // null이면 발송 전 초안
  items: DigestItem[];
}

export interface Competitor {
  id: string;
  name: string;
  ticker: string;
  fiscalQuarter: string;
  reportedAt: string;
  financials: {
    metric: string;
    value: string;
    qoq: number; // % 변화
    yoy: number;
  }[];
  callSummary: string[];
  qoqChanges: string[];
  consensus: {
    metric: string;
    current: string;
    previous: string;
    revisedAt: string;
    broker: string;
    direction: "up" | "down" | "flat";
  }[];
}

export const topics: Topic[] = [
  {
    id: "hbm-demand",
    title: "HBM 수요 사이클과 AI 가속기 로드맵",
    category: "수요/시황",
    summary:
      "AI 학습/추론 인프라 투자 확대로 HBM 수요 강세가 지속. 주요 가속기 벤더의 차세대 제품 로드맵에 따라 HBM4 전환 시점이 수요의 핵심 변수로 부상.",
    insight:
      "HBM 공급 부족이 일반 DRAM 캐파를 잠식하면서 메모리 전반의 가격 상승 압력으로 전이. 모바일 SoC 원가 구조에 2차 영향 가능성 모니터링 필요.",
    sourceCount: 42,
    updatedAt: "2026-06-10",
    history: [
      { date: "2026-06-09", event: "주요 증권사, HBM 캐파 증설 전망 상향", source: "증권사 리포트" },
      { date: "2026-05-28", event: "가속기 벤더 차세대 로드맵 공개", source: "기술 뉴스" },
      { date: "2026-05-12", event: "조사기관, AI 서버 출하 전망 상향 조정", source: "조사기관" },
    ],
  },
  {
    id: "foundry-2nm",
    title: "2nm 파운드리 경쟁 구도",
    category: "반도체 제조",
    summary:
      "GAA 기반 2nm 공정의 수율 안정화 경쟁이 본격화. 선단 공정 고객 확보 경쟁에서 설계 생태계(IP/EDA) 지원 폭이 변별 요소로 작용.",
    insight:
      "2nm 수주 동향은 자사 SoC의 파운드리 선택지와 원가에 직결. 경쟁사 수율 관련 보도는 검증 신뢰도가 낮아 복수 소스 교차 확인 원칙 적용.",
    sourceCount: 31,
    updatedAt: "2026-06-08",
    history: [
      { date: "2026-06-05", event: "경쟁 파운드리 2nm 위험 생산 개시 보도", source: "기술 뉴스" },
      { date: "2026-05-20", event: "EDA 벤더, 2nm 레퍼런스 플로우 발표", source: "기술 뉴스" },
    ],
  },
  {
    id: "onx-set",
    title: "온디바이스 AI와 SET(스마트폰/PC) 교체 수요",
    category: "SET",
    summary:
      "온디바이스 AI 기능이 프리미엄 스마트폰·AI PC의 교체 주기 단축 동인으로 작용하는지에 대한 조사기관 전망이 엇갈림.",
    insight:
      "NPU TOPS 요구치 상승은 AP/모뎀 통합 SoC의 다이 사이즈·원가 상승 요인. 보급형 라인업으로의 AI 기능 하향 전개 속도가 수요 탄력의 관건.",
    sourceCount: 27,
    updatedAt: "2026-06-11",
    history: [
      { date: "2026-06-11", event: "조사기관, AI 스마트폰 침투율 전망 발표", source: "조사기관" },
      { date: "2026-05-30", event: "주요 OEM, 보급형 AI 기능 탑재 계획 보도", source: "뉴스" },
    ],
  },
];

export const digests: Digest[] = [
  {
    id: "2026-w24-1",
    issueNo: 47,
    period: "2026.06.08 – 06.11",
    mailedAt: null,
    items: [
      {
        id: "d1",
        title: "차세대 AI 가속기, HBM4 12단 채택 공식화",
        source: "기술 뉴스 (해외)",
        publishedAt: "2026-06-10",
        summary:
          "주요 가속기 벤더가 차세대 제품에 HBM4 12단 채택을 공식화. 양산 시점은 2027년 상반기로 제시.",
        slsiRelevance: "HBM 컨트롤러 IP 및 베이스 다이 파운드리 수주 기회와 직결.",
        demandImpact: "HBM4 전환 가속 시 선단 패키징 캐파 경쟁 심화 전망.",
        risk: "양산 일정 지연 시 재고 사이클 왜곡 가능성.",
        impact: "high",
        tags: ["HBM", "AI가속기", "패키징"],
      },
      {
        id: "d2",
        title: "글로벌 스마트폰 2분기 출하 전망 소폭 하향",
        source: "조사기관",
        publishedAt: "2026-06-09",
        summary:
          "조사기관이 환율·관세 불확실성을 이유로 2분기 글로벌 스마트폰 출하 전망을 1%p 하향.",
        slsiRelevance: "보급형 AP·이미지센서 출하 물량에 직접 영향.",
        demandImpact: "하반기 신모델 출시 전 채널 재고 조정 가능성.",
        risk: "관세 정책 변동 시 추가 하향 리스크.",
        impact: "medium",
        tags: ["SET", "스마트폰", "수요"],
      },
      {
        id: "d3",
        title: "RISC-V 기반 차량용 MCU 설계 수주 확대",
        source: "기술 뉴스 (국내)",
        publishedAt: "2026-06-08",
        summary:
          "복수의 팹리스가 RISC-V 기반 차량용 MCU 설계를 수주하며 ARM 대비 라이선스 비용 우위를 강조.",
        slsiRelevance: "차량용 SoC 라인업의 ISA 전략 재검토 참고 사례.",
        demandImpact: "단기 수요 영향 제한적, 중장기 생태계 변화 모니터링.",
        risk: "툴체인 성숙도 미흡으로 양산 전환 지연 가능성.",
        impact: "low",
        tags: ["RISC-V", "차량용", "설계"],
      },
    ],
  },
  {
    id: "2026-w23-2",
    issueNo: 46,
    period: "2026.06.04 – 06.07",
    mailedAt: "2026-06-08 09:00",
    items: [
      {
        id: "d4",
        title: "선단 파운드리 가격 인상설, 고객사 반응 엇갈려",
        source: "기술 뉴스 (대만)",
        publishedAt: "2026-06-06",
        summary:
          "선단 공정 웨이퍼 가격 인상 보도에 대해 대형 고객사들의 수용 여부가 엇갈린다는 후속 보도.",
        slsiRelevance: "자사 SoC 원가 및 파운드리 협상 포지션에 영향.",
        demandImpact: "원가 전가 시 세트 가격 인상 → 수요 둔화 2차 효과.",
        risk: "단일 소스 보도로 신뢰도 검증 필요.",
        impact: "high",
        tags: ["파운드리", "가격", "원가"],
      },
    ],
  },
];

export const competitors: Competitor[] = [
  {
    id: "comp-q",
    name: "경쟁사 Q",
    ticker: "QCOM",
    fiscalQuarter: "FY26 Q2",
    reportedAt: "2026-04-30",
    financials: [
      { metric: "매출", value: "$11.7B", qoq: 3.2, yoy: 12.4 },
      { metric: "영업이익", value: "$3.4B", qoq: 5.1, yoy: 18.0 },
      { metric: "영업이익률", value: "29.1%", qoq: 0.5, yoy: 1.4 },
      { metric: "핸드셋 부문 매출", value: "$7.6B", qoq: -2.1, yoy: 9.8 },
    ],
    callSummary: [
      "온디바이스 AI 수요로 프리미엄 AP ASP 상승 지속을 강조.",
      "차량용(오토모티브) 부문 두 자릿수 성장 가이던스 유지.",
      "주요 고객사 자체 모뎀 전환 리스크에 대해 '점진적 영향'으로 톤 유지.",
    ],
    qoqChanges: [
      "핸드셋 매출 QoQ 감소 전환 — 계절성 요인으로 설명했으나 전분기 가이던스 대비 하단.",
      "차량용 백로그 언급 횟수 증가(전분기 3회 → 7회), 성장 내러티브의 무게중심 이동.",
    ],
    consensus: [
      { metric: "FY26 매출", current: "$45.2B", previous: "$44.8B", revisedAt: "2026-06-05", broker: "해외 IB A", direction: "up" },
      { metric: "FY26 EPS", current: "$11.80", previous: "$11.95", revisedAt: "2026-05-22", broker: "해외 IB B", direction: "down" },
    ],
  },
  {
    id: "comp-m",
    name: "경쟁사 M",
    ticker: "MTK",
    fiscalQuarter: "2026 Q1",
    reportedAt: "2026-04-25",
    financials: [
      { metric: "매출", value: "NT$153B", qoq: -4.5, yoy: 14.2 },
      { metric: "매출총이익률", value: "48.9%", qoq: 0.3, yoy: 1.1 },
      { metric: "영업이익", value: "NT$31B", qoq: -6.2, yoy: 16.5 },
    ],
    callSummary: [
      "플래그십 AP 점유율 확대와 함께 ASP 중심 성장 전략 재확인.",
      "엣지 AI ASIC 수주 파이프라인을 처음으로 정량 언급.",
      "2분기 가이던스는 환율 영향 반영해 보수적으로 제시.",
    ],
    qoqChanges: [
      "ASIC/커스텀 실리콘 관련 언급 신규 등장 — 사업 다각화 신호.",
      "재고일수 전분기 대비 6일 감소, 채널 재고 건전화 진행.",
    ],
    consensus: [
      { metric: "2026 매출", current: "NT$640B", previous: "NT$628B", revisedAt: "2026-06-02", broker: "국내 증권사 C", direction: "up" },
      { metric: "2026 영업이익률", current: "20.1%", previous: "20.1%", revisedAt: "2026-05-15", broker: "해외 IB A", direction: "flat" },
    ],
  },
];

// 수집 파이프라인 상태는 라이브 백엔드(/collection/sources)에서 가져온다.
// → components/pipeline-status.tsx
