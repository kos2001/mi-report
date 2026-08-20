import { Card, PageHeader } from "@/components/ui";

// 사용 안내(매뉴얼) — 정적 페이지. 서비스 개요 + 기능별 사용법 + 권장 워크플로우.

type Feature = {
  menu: string;
  icon: string;
  what: string;
  how: string;
  endpoint: string;
  live: boolean;
};

const FEATURES: Feature[] = [
  {
    menu: "데이터 수집",
    icon: "⬇",
    what: "소스(EDM·Confluence·뉴스·증권사·컨센서스) 관리, 수동 업로드, 수집 문서 조회. 모든 AI 기능의 입력이 되는 문서를 여기서 쌓는다.",
    how: "‘업로드’ 탭에서 문서를 올리고(주제 태그 선택), ‘문서’ 탭에서 조회한다. 주제가 비어 있는 문서는 ‘분류’ 또는 ‘미분류 자동 분류’로 AI 태깅.",
    endpoint: "/collection/*",
    live: true,
  },
  {
    menu: "주제별 History",
    icon: "≡",
    what: "한 주제로 누적된 문서를 종합해 누적 요약 · S.LSI 시황 연계 인사이트 · 사건 타임라인을 만든다.",
    how: "주제를 선택하고 ‘AI 요약 생성’. 주제는 문서에 부여된 태그에서 자동 수집된다.",
    endpoint: "POST /topics/summarize",
    live: true,
  },
  {
    menu: "뉴스 다이제스트",
    icon: "✉",
    what: "수집 문서를 요약해 항목별 S.LSI 연관성 · 수요 변동 · 리스크 · 영향도(상/중/하) · 태그를 평가한다.",
    how: "‘AI 초안 생성’ 버튼 한 번. 생성된 초안은 발송 전 검토 대상으로 표시된다.",
    endpoint: "POST /digest/generate",
    live: true,
  },
  {
    menu: "경쟁사 IR",
    icon: "▤",
    what: "경쟁사 IR·실적·콜 문서에서 재무 요약 · 콜 요약 · 전분기 대비 변화 · 컨센서스 추적을 추출한다.",
    how: "경쟁사 이름(·티커·문서 주제)을 입력하고 ‘AI 분석 생성’. 문서에 없는 수치는 비워 두며(환각 방지), 컨센서스가 없으면 빈 상태로 표시된다.",
    endpoint: "POST /competitors/analyze",
    live: true,
  },
  {
    menu: "문서 Q&A",
    icon: "?",
    what: "hermes 에이전트가 수집 문서·웹을 스스로 검색해 답한다(멀티턴). 답변 수치는 코퍼스와 자동 대조해 미확인 수치를 경고한다.",
    how: "질문을 입력하고 ‘보내기’. 이어지는 질문은 같은 세션에서 맥락을 기억한다. 도구 사용 시 수십 초 걸릴 수 있다.",
    endpoint: "POST /agent/chat",
    live: true,
  },
  {
    menu: "주간 리포트",
    icon: "▦",
    what: "다이제스트 + 주제별 요약 + 이를 종합한 총평(executive overview)을 한 편으로 묶는다.",
    how: "‘AI 리포트 생성’ 한 번으로 여러 단계를 오케스트레이션한다(다중 호출이라 시간이 걸릴 수 있음).",
    endpoint: "POST /report/generate",
    live: true,
  },
];

const WORKFLOW = [
  "데이터 수집 → 업로드 탭에서 분석 대상 문서를 올린다(주제 태그를 알면 함께 입력).",
  "데이터 수집 → 문서 탭에서 ‘미분류 자동 분류’로 주제가 없는 문서에 주제를 부여한다.",
  "주제별 History·경쟁사 IR·뉴스 다이제스트에서 해당 화면의 ‘AI … 생성’으로 인사이트를 만든다.",
  "문서 Q&A로 특정 질문을 던져 근거와 함께 확인한다.",
  "주간 리포트에서 한 주 분량을 총평까지 묶어 초안으로 받는다.",
];

export default function ManualPage() {
  return (
    <>
      <PageHeader
        title="사용 안내"
        description="MI Report Agent 개요와 화면별 사용법"
      />

      <div className="flex flex-col gap-6">
        {/* 개요 */}
        <Card>
          <h2 className="text-base font-semibold text-zinc-950 dark:text-zinc-50">서비스 개요</h2>
          <p className="mt-2 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
            <strong className="text-zinc-900 dark:text-zinc-100">MI Report Agent</strong>는 반도체·IT 시장
            인텔리전스(MI) 리포트 작성을 자동화하는 에이전트다. 시장 센싱 · 뉴스
            다이제스트 · 경쟁사 IR 분석을 한 곳에서 다룬다. 핵심 흐름은 다음 한 줄로
            요약된다:
          </p>
          <p className="mt-3 rounded-lg border border-sky-100/40 dark:border-sky-900/40 bg-sky-50/30 dark:bg-sky-950/30 px-4 py-3 text-sm font-medium text-sky-800 dark:text-sky-200">
            문서 수집 → (자동 분류) → AI 생성(다이제스트 · 주제 · 경쟁사 · Q&A) → 주간 리포트 종합
          </p>
          <p className="mt-3 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
            수집된 문서를 입력으로, OpenAI 호환 LLM(agno + OpenRouter)이 구조화된
            인텔리전스를 산출한다. 모든 생성물은 제공된 문서에만 근거하도록 제약하며,
            단일 출처 항목은 교차검증 필요로 표시한다.
          </p>
        </Card>

        {/* 구성 */}
        <Card>
          <h2 className="text-base font-semibold text-zinc-950 dark:text-zinc-50">구성</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg bg-zinc-200/50 dark:bg-zinc-800/50 px-4 py-3">
              <p className="text-xs font-medium text-zinc-600 dark:text-zinc-400">프론트엔드</p>
              <p className="mt-1 text-sm text-zinc-800 dark:text-zinc-200">Next.js 대시보드</p>
              <p className="mt-1 text-xs text-zinc-500">localhost:3000</p>
            </div>
            <div className="rounded-lg bg-zinc-200/50 dark:bg-zinc-800/50 px-4 py-3">
              <p className="text-xs font-medium text-zinc-600 dark:text-zinc-400">백엔드</p>
              <p className="mt-1 text-sm text-zinc-800 dark:text-zinc-200">FastAPI</p>
              <p className="mt-1 text-xs text-zinc-500">localhost:8000 · /docs</p>
            </div>
            <div className="rounded-lg bg-zinc-200/50 dark:bg-zinc-800/50 px-4 py-3">
              <p className="text-xs font-medium text-zinc-600 dark:text-zinc-400">LLM 엔진</p>
              <p className="mt-1 text-sm text-zinc-800 dark:text-zinc-200">agno + OpenRouter</p>
              <p className="mt-1 text-xs text-zinc-500">OpenAI 호환 · 모델 교체 가능</p>
            </div>
          </div>
          <p className="mt-3 text-xs leading-relaxed text-zinc-500">
            수집 문서는 백엔드 SQLite(전문검색 FTS5 포함)에 저장된다. AI 생성 기능은
            OpenRouter API 키가 설정돼 있어야 동작한다.
          </p>
        </Card>

        {/* 기능별 사용법 */}
        <section>
          <h2 className="mb-3 text-base font-semibold text-zinc-950 dark:text-zinc-50">화면별 사용법</h2>
          <div className="flex flex-col gap-3">
            {FEATURES.map((f) => (
              <Card key={f.menu}>
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-2">
                    <span className="w-5 text-center text-zinc-500">{f.icon}</span>
                    <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{f.menu}</h3>
                  </div>
                  <div className="flex items-center gap-2">
                    {f.live && (
                      <span className="rounded-full border border-emerald-100/60 dark:border-emerald-900/60 bg-emerald-50/40 dark:bg-emerald-950/40 px-2.5 py-0.5 text-[11px] text-emerald-600 dark:text-emerald-400">
                        실연동
                      </span>
                    )}
                    <code className="rounded bg-zinc-200 dark:bg-zinc-800 px-2 py-0.5 font-mono text-[11px] text-zinc-600 dark:text-zinc-400">
                      {f.endpoint}
                    </code>
                  </div>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">{f.what}</p>
                <p className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
                  <span className="text-zinc-500">사용법 · </span>
                  {f.how}
                </p>
              </Card>
            ))}
          </div>
        </section>

        {/* 권장 워크플로우 */}
        <Card>
          <h2 className="text-base font-semibold text-zinc-950 dark:text-zinc-50">권장 워크플로우</h2>
          <ol className="mt-3 flex flex-col gap-2.5">
            {WORKFLOW.map((step, i) => (
              <li key={i} className="flex gap-3 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-sky-100/60 dark:bg-sky-900/60 text-[11px] font-medium text-sky-700 dark:text-sky-300">
                  {i + 1}
                </span>
                {step}
              </li>
            ))}
          </ol>
        </Card>

        {/* 주의 사항 */}
        <Card className="border-amber-100/50 dark:border-amber-900/50 bg-amber-50/20 dark:bg-amber-950/20">
          <h2 className="text-base font-semibold text-amber-800 dark:text-amber-200">알아둘 점</h2>
          <ul className="mt-3 flex flex-col gap-2 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
            <li>
              · <strong className="text-zinc-900 dark:text-zinc-100">근거 기반 생성</strong> — 생성물은 제공된
              문서에만 근거한다. 문서가 없으면 빈 상태로 안내하며 사실을 지어내지 않는다.
            </li>
            <li>
              · <strong className="text-zinc-900 dark:text-zinc-100">검토 후 활용</strong> — 단일 출처 항목은
              교차검증 필요로 표시된다. 다이제스트 초안·경쟁사 수치는 발송/인용 전 검토를 권장한다.
            </li>
            <li>
              · <strong className="text-zinc-900 dark:text-zinc-100">LLM 키 의존</strong> — AI 생성 기능은
              OpenRouter API 키가 설정돼 있을 때만 동작한다. 데이터 수집·문서 관리·검색은 키 없이도 동작한다.
            </li>
            <li>
              · <strong className="text-zinc-900 dark:text-zinc-100">현황</strong> — 데이터 수집은 백엔드
              실연동(SQLite). 커넥터(EDM/Confluence/뉴스)의 실제 크롤링은 아직 스텁이며,
              현재는 수동 업로드·COM 인제스트로 문서를 넣는다.
            </li>
          </ul>
        </Card>
      </div>
    </>
  );
}
