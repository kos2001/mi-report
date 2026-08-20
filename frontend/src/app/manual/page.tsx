import Link from "next/link";
import { Card, PageHeader } from "@/components/ui";

// 사용 안내 — 실제 기능과 화면 흐름을 기준으로 유지하는 정적 운영 매뉴얼.

type GuideFeature = {
  menu: string;
  href: string;
  icon: string;
  color: string;
  what: string;
  steps: string[];
  check: string;
};

const QUICK_START = [
  {
    step: "1",
    title: "소스 연결·수집",
    description: "URL·Confluence·SEC·DART·한경 소스를 설정하고 실제 운영 상태를 확인합니다.",
    href: "/collection",
    color: "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-200",
  },
  {
    step: "2",
    title: "문서 확인·분류",
    description: "수집 본문, 원본 링크, 주제와 소스를 확인하고 필요한 문서를 분류합니다.",
    href: "/collection/documents",
    color: "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200",
  },
  {
    step: "3",
    title: "검색 인프라 확인",
    description: "BM25 색인, 임베딩 벡터, LLM Wiki가 문서를 빠짐없이 반영했는지 확인합니다.",
    href: "/collection/results",
    color: "border-violet-200 bg-violet-50 text-violet-800 dark:border-violet-900 dark:bg-violet-950/40 dark:text-violet-200",
  },
  {
    step: "4",
    title: "분석·Q&A 실행",
    description: "다이제스트·주제·경쟁사 분석을 생성하고 문서 Q&A로 근거를 교차 확인합니다.",
    href: "/ask",
    color: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200",
  },
  {
    step: "5",
    title: "주간 리포트 종합",
    description: "검증된 하위 생성물을 Priority/Risk·Critical Point와 함께 주간 초안으로 묶습니다.",
    href: "/report",
    color: "border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200",
  },
];

const FEATURES: GuideFeature[] = [
  {
    menu: "데이터 수집",
    href: "/collection",
    icon: "↓",
    color: "bg-sky-600",
    what: "연결 설정, 실제 운영 상태, 즉시 수집과 파일 업로드를 한 화면에서 관리합니다.",
    steps: [
      "소스·수집에서 소스 이름과 유형별 필수 설정을 입력합니다.",
      "실제 운영 상태가 ‘활성·정상’인지 확인한 뒤 ‘지금 수집’을 실행합니다.",
      "로컬 자료는 파일 업로드에서 주제 태그와 함께 투입합니다.",
    ],
    check: "‘정상’ 문자열이 아니라 설정·최근 실행·문서 존재를 반영한 운영 판정을 확인합니다.",
  },
  {
    menu: "수집 문서",
    href: "/collection/documents",
    icon: "▤",
    color: "bg-emerald-600",
    what: "수집된 문서를 소스·주제·검색어로 필터링하고 추출 본문과 외부 원본을 확인합니다.",
    steps: [
      "목록에서 문서를 선택해 오른쪽 상세 패널을 엽니다.",
      "수집 소스·주제·발행일·수집 시각과 본문 통계를 확인합니다.",
      "URL 문서는 ‘원본 열기’, 업로드 문서는 추출 본문을 검토합니다.",
    ],
    check: "제목만 같은 문서가 실제 중복인지 판단할 때는 본문과 수집 URL을 함께 비교합니다.",
  },
  {
    menu: "수집 결과",
    href: "/collection/results",
    icon: "⌁",
    color: "bg-violet-600",
    what: "소스·주제 분포와 BM25·Embedding DB·LLM Wiki의 실제 적재 상태를 보여줍니다.",
    steps: [
      "BM25 색인 커버리지가 전체 문서 수와 일치하는지 확인합니다.",
      "Embedding 벡터 수·차원·모델과 커버리지를 확인합니다.",
      "LLM Wiki 누적 주차·개념·최신 지식 주차를 확인합니다.",
    ],
    check: "색인 또는 벡터 커버리지가 100% 미만이면 새 문서가 검색에 반영되지 않았을 수 있습니다.",
  },
  {
    menu: "문서 Q&A",
    href: "/ask",
    icon: "?",
    color: "bg-amber-500",
    what: "에이전트가 수집 문서와 필요한 웹 자료를 검색해 멀티턴으로 답합니다.",
    steps: [
      "질문을 구체적으로 입력하고 도구 진행 상황을 확인합니다.",
      "완료 응답의 수치 검증 상태와 관련 수집 문서를 확인합니다.",
      "‘추출 원문 확인’으로 답변과 실제 근거를 대조합니다.",
    ],
    check: "‘미확인 수치’는 곧 오류라는 뜻이 아니라 수집 코퍼스에서 확인되지 않았다는 뜻입니다.",
  },
  {
    menu: "뉴스 다이제스트",
    href: "/digest",
    icon: "✉",
    color: "bg-blue-600",
    what: "수집 문서를 S.LSI 연관성·수요 영향·리스크·영향도로 구조화합니다.",
    steps: [
      "기간과 문서 범위를 지정해 AI 초안을 생성합니다.",
      "수치·출처 검증 경고와 에이전트 코멘트를 검토합니다.",
      "생성 이력의 ‘내용 보기’를 눌러 과거 주차 결과를 비교합니다.",
    ],
    check: "같은 ISO 주차를 재생성하면 이전 결과를 교체하고 다른 주차는 누적합니다.",
  },
  {
    menu: "주제별 History",
    href: "/topics",
    icon: "≡",
    color: "bg-cyan-600",
    what: "동일 주제의 문서를 누적 요약, 인사이트와 사건 타임라인으로 변환합니다.",
    steps: [
      "문서에 부여된 주제를 선택합니다.",
      "AI 요약 생성을 실행해 Summary·Insight·History를 만듭니다.",
      "이력 항목을 선택해 과거 생성 내용을 직접 확인합니다.",
    ],
    check: "출처 검증 경고가 있는 History 사건은 원문 귀속을 확인합니다.",
  },
  {
    menu: "경쟁사 IR",
    href: "/competitors",
    icon: "▥",
    color: "bg-fuchsia-600",
    what: "IR·공시·증권사 문서에서 재무, 콜 요약, QoQ 변화와 컨센서스를 추출합니다.",
    steps: [
      "수집 데이터에서 경쟁사 후보를 선택하거나 이름·티커를 입력합니다.",
      "AI 분석을 생성하고 미근거 수치·서술 경고를 검토합니다.",
      "생성 이력에서 회사·분기 중복 여부와 실제 내용을 확인합니다.",
    ],
    check: "회사명이 같아도 분기가 다르면 다른 이력입니다. 회사·분기·본문을 함께 비교합니다.",
  },
  {
    menu: "주간 MI 리포트",
    href: "/report",
    icon: "▦",
    color: "bg-rose-600",
    what: "다이제스트·주제 분석을 총평, Priority/Risk와 Critical Point로 종합합니다.",
    steps: [
      "기간·호수·주제 범위를 확인하고 리포트를 생성합니다.",
      "총평과 중요 판단 포인트의 근거 검증 상태를 확인합니다.",
      "생성 이력 또는 Markdown 문서 미리보기로 결과를 검토합니다.",
    ],
    check: "리포트 생성은 여러 분석 agent를 호출하므로 다른 기능보다 오래 걸릴 수 있습니다.",
  },
];

const SOURCE_STATES = [
  ["활성·정상", "설정 확인, 최근 48시간 내 실행, 수집 문서 존재", "bg-emerald-500"],
  ["활성·대기", "설정은 완료됐지만 아직 실행 기록 없음", "bg-blue-500"],
  ["활성·결과 없음", "최근 실행했지만 수집 문서가 없음", "bg-orange-500"],
  ["활성·점검 필요", "마지막 실행이 48시간보다 오래됨", "bg-amber-500"],
  ["설정 필요", "URL·경로·CIK·인증정보 등 필수 설정 누락", "bg-fuchsia-500"],
  ["활성·오류", "마지막 수집 실행 실패", "bg-red-500"],
  ["수동 활성", "파일 업로드 요청 시 동작", "bg-sky-500"],
  ["비활성", "사용자 설정으로 수집 중지", "bg-zinc-400"],
] as const;

export default function ManualPage() {
  return (
    <>
      <PageHeader
        title="사용 안내"
        description="처음 수집부터 근거 확인·생성 이력·주간 리포트까지 실제 화면 기준 사용법"
      />

      <div className="flex flex-col gap-8">
        <Card className="overflow-hidden border-sky-200 bg-gradient-to-br from-sky-50 via-white to-violet-50 dark:border-sky-900 dark:from-sky-950/40 dark:via-zinc-950 dark:to-violet-950/30">
          <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
            <div>
              <span className="rounded-full bg-sky-100 px-2.5 py-1 text-[11px] font-semibold text-sky-700 dark:bg-sky-900 dark:text-sky-300">MI WORKFLOW</span>
              <h2 className="mt-4 text-xl font-semibold text-zinc-950 dark:text-zinc-50">원문에서 의사결정 가능한 MI 초안까지</h2>
              <p className="mt-2 max-w-2xl text-sm leading-7 text-zinc-700 dark:text-zinc-300">
                MI Report Agent는 문서를 먼저 수집·색인한 뒤 검색 근거를 사용해 다이제스트,
                주제 History, 경쟁사 IR과 주간 리포트를 생성합니다. 결과의 수치와 출처는
                완료 카드와 원문 링크에서 직접 확인할 수 있습니다.
              </p>
            </div>
            <div className="rounded-xl border border-white/80 bg-white/80 p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-950/70">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">핵심 원칙</p>
              <ul className="mt-3 space-y-2 text-sm text-zinc-700 dark:text-zinc-300">
                <li>✓ 원문 코퍼스가 사실의 기준</li>
                <li>✓ BM25와 의미 검색을 함께 사용</li>
                <li>✓ 미확인 수치·출처를 경고</li>
                <li>✓ 같은 주차는 교체, 다른 주차는 누적</li>
              </ul>
            </div>
          </div>
        </Card>

        <section>
          <div className="mb-3">
            <h2 className="text-base font-semibold text-zinc-950 dark:text-zinc-50">처음 시작하는 순서</h2>
            <p className="mt-1 text-xs text-zinc-500">각 단계를 눌러 해당 화면으로 이동합니다.</p>
          </div>
          <div className="grid gap-3 md:grid-cols-5">
            {QUICK_START.map((item) => (
              <Link key={item.step} href={item.href} className={`group rounded-xl border p-4 transition hover:-translate-y-0.5 hover:shadow-md ${item.color}`}>
                <span className="font-mono text-[10px] font-bold opacity-70">STEP {item.step}</span>
                <h3 className="mt-2 text-sm font-semibold">{item.title}</h3>
                <p className="mt-1.5 text-[11px] leading-5 opacity-80">{item.description}</p>
                <span className="mt-3 inline-block text-[11px] font-semibold">화면 열기 →</span>
              </Link>
            ))}
          </div>
        </section>

        <section className="grid gap-5 lg:grid-cols-[1fr_1fr]">
          <Card>
            <h2 className="text-base font-semibold text-zinc-950 dark:text-zinc-50">수집 상태 읽는 법</h2>
            <p className="mt-1 text-xs text-zinc-500">저장된 마지막 결과가 아니라 현재 설정·실행 상태를 함께 판정합니다.</p>
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              {SOURCE_STATES.map(([label, description, dot]) => (
                <div key={label} className="rounded-lg border border-zinc-200 px-3 py-2.5 dark:border-zinc-800">
                  <div className="flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${dot}`} />
                    <span className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">{label}</span>
                  </div>
                  <p className="mt-1 text-[11px] leading-4 text-zinc-500">{description}</p>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <h2 className="text-base font-semibold text-zinc-950 dark:text-zinc-50">검색·지식 계층</h2>
            <p className="mt-1 text-xs text-zinc-500">수집결과 화면에서 실제 적재 수와 커버리지를 확인합니다.</p>
            <div className="mt-4 space-y-3">
              <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-3 dark:border-blue-900 dark:bg-blue-950/40">
                <p className="text-xs font-semibold text-blue-900 dark:text-blue-100">BM25 · 키워드 검색</p>
                <p className="mt-1 text-[11px] leading-5 text-blue-700 dark:text-blue-300">제목·주제·본문에서 정확한 용어, 약어와 숫자를 찾습니다.</p>
              </div>
              <div className="rounded-lg border border-violet-200 bg-violet-50 px-3 py-3 dark:border-violet-900 dark:bg-violet-950/40">
                <p className="text-xs font-semibold text-violet-900 dark:text-violet-100">Embedding · 의미 검색</p>
                <p className="mt-1 text-[11px] leading-5 text-violet-700 dark:text-violet-300">표현이 달라도 의미가 가까운 문서를 회수하고 BM25와 RRF로 결합합니다.</p>
              </div>
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-3 dark:border-amber-900 dark:bg-amber-950/40">
                <p className="text-xs font-semibold text-amber-900 dark:text-amber-100">LLM Wiki · 주차별 기억</p>
                <p className="mt-1 text-[11px] leading-5 text-amber-700 dark:text-amber-300">생성된 다이제스트를 주차·개념별로 누적해 다음 생성의 비교 맥락으로 사용합니다.</p>
              </div>
            </div>
            <Link href="/collection/results" className="mt-4 inline-flex rounded-lg bg-zinc-900 px-3 py-2 text-xs font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white">
              검색 인프라 상태 확인 →
            </Link>
          </Card>
        </section>

        <section>
          <h2 className="mb-3 text-base font-semibold text-zinc-950 dark:text-zinc-50">화면별 사용법</h2>
          <div className="grid gap-4 lg:grid-cols-2">
            {FEATURES.map((feature) => (
              <Card key={feature.menu} className="overflow-hidden p-0">
                <div className={`h-1.5 ${feature.color}`} />
                <div className="p-5">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2.5">
                      <span className={`flex h-8 w-8 items-center justify-center rounded-lg text-sm font-bold text-white ${feature.color}`}>{feature.icon}</span>
                      <h3 className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{feature.menu}</h3>
                    </div>
                    <Link href={feature.href} className="text-xs font-medium text-sky-600 hover:underline dark:text-sky-400">화면 열기 →</Link>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-zinc-700 dark:text-zinc-300">{feature.what}</p>
                  <ol className="mt-3 space-y-1.5">
                    {feature.steps.map((step, index) => (
                      <li key={step} className="flex gap-2 text-xs leading-5 text-zinc-600 dark:text-zinc-400">
                        <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-zinc-200 font-mono text-[9px] text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">{index + 1}</span>
                        {step}
                      </li>
                    ))}
                  </ol>
                  <p className="mt-3 rounded-lg bg-zinc-100 px-3 py-2 text-[11px] leading-5 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400">
                    <strong className="text-zinc-800 dark:text-zinc-200">확인 포인트 · </strong>{feature.check}
                  </p>
                </div>
              </Card>
            ))}
          </div>
        </section>

        <section className="grid gap-5 lg:grid-cols-2">
          <Card>
            <h2 className="text-base font-semibold text-zinc-950 dark:text-zinc-50">생성 이력 사용법</h2>
            <ol className="mt-3 space-y-3 text-sm text-zinc-700 dark:text-zinc-300">
              <li className="flex gap-3"><span className="font-mono text-sky-600">01</span><span>각 생성 페이지의 <strong>생성 이력</strong>에서 날짜와 제목을 확인합니다.</span></li>
              <li className="flex gap-3"><span className="font-mono text-sky-600">02</span><span><strong>내용 보기 →</strong>를 누르면 저장된 payload가 실제 결과 카드에 표시됩니다.</span></li>
              <li className="flex gap-3"><span className="font-mono text-sky-600">03</span><span>화면이 결과 영역으로 이동하며 선택된 이력이 파란색으로 강조됩니다.</span></li>
              <li className="flex gap-3"><span className="font-mono text-sky-600">04</span><span>같은 ISO 주차 재생성은 이전 결과를 교체하고 다른 주차는 유지합니다.</span></li>
            </ol>
          </Card>

          <Card className="border-amber-200 bg-amber-50/40 dark:border-amber-900 dark:bg-amber-950/20">
            <h2 className="text-base font-semibold text-amber-900 dark:text-amber-100">결과를 신뢰하기 전에</h2>
            <ul className="mt-3 space-y-2 text-sm leading-6 text-zinc-700 dark:text-zinc-300">
              <li>• <strong>수치 검증 완료</strong>는 수집 코퍼스에서 동일 수치를 찾았다는 뜻입니다.</li>
              <li>• <strong>미확인 수치</strong>는 웹 출처 수치이거나 오류일 수 있으므로 원문을 확인합니다.</li>
              <li>• <strong>단일 출처</strong> 항목은 독립된 두 번째 출처로 교차 검증합니다.</li>
              <li>• 출처 카드의 <strong>추출 원문 확인</strong>과 외부 원본 링크를 우선 사용합니다.</li>
              <li>• LLM Wiki는 비교 맥락이며 최종 사실 원장은 수집 원문입니다.</li>
            </ul>
          </Card>
        </section>

        <Card>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-base font-semibold text-zinc-950 dark:text-zinc-50">연결·설정 문제 확인</h2>
              <p className="mt-1 text-xs text-zinc-500">API, 모델, 인증과 스케줄 설정은 설정 화면과 백엔드 OpenAPI에서 확인합니다.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link href="/settings" className="rounded-lg border border-zinc-300 px-3 py-2 text-xs font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900">설정 열기 →</Link>
              <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer" className="rounded-lg bg-sky-600 px-3 py-2 text-xs font-medium text-white hover:bg-sky-500">Backend API Docs ↗</a>
            </div>
          </div>
        </Card>
      </div>
    </>
  );
}
