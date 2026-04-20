import { NextRequest, NextResponse } from "next/server";
import OpenAI from "openai";

/** API 요청 본문: taskType + 해당 작업용 data (클라이언트는 lib/analyzeApi.ts 타입 사용) */
type AnalyzeTaskType =
  | "buyer-email"
  | "sales-analyzer"
  | "spec-localizer"
  | "price-matrix"
  | "exhibition-report";

interface AnalyzeRequestBody {
  taskType: AnalyzeTaskType;
  /** 작업별 페이로드 (CSV 문자열, JSON 객체 등) */
  data: string | Record<string, unknown> | unknown[];
}

const SYSTEM_PROMPTS: Record<AnalyzeTaskType, string> = {
  "buyer-email":
    "You are an expert B2B sales copywriter. Based on the provided CSV data (Buyer, Country, Product), write highly personalized, professional cold emails. Output in clean Markdown.",
  "sales-analyzer": `You are a Senior Strategic Analyst. Analyze the provided monthly export CSV data and produce a highly visual, structured Korean report for C-level executives.

VISUAL DESIGN RULES (MANDATORY):
1. Main Headers (Level 3: ###): Use large, bold headers with primary emojis to define major sections.
2. Horizontal Rules: Add '---' between major sections to provide visual breathing room.
3. Sub-headers (Level 4: ####): Use specific status-indicative emojis (📈, 📉, 🎯) to categorize insights.
4. Bold Key Numbers: All percentages (%) and currency figures MUST be **bolded** in the output.
5. Tables: Use Markdown tables for the Top 3 items with proper column alignment.

STRICT MARKDOWN TEMPLATE — Follow this structure EXACTLY. Output ONLY the formatted Korean Markdown report. Maintain a formal, authoritative, yet concise "C-level Executive" tone. Ensure the contrast between Growth and Decline is visually immediate.

### 📊 [REPORT] 월별 수출 실적 및 시장 분석

---

### 🏆 1. 품목별 실적 변동 현황 (Top 3)
| 순위 | 품목명 | 전월 대비 증감률 | 분석 의견 |
| :--- | :--- | :--- | :--- |
| 1위 | {item_name} | **+{percent}%** or **-{percent}%** | {brief_analysis} |
| 2위 | ... | ... | ... |
| 3위 | ... | ... | ... |

> *전문가 한 줄 평: [데이터 기반의 핵심 요약 문구 작성]*

---

### 🗺️ 2. 국가별 시장 트렌드 분석

#### 📈 성장세 뚜렷한 국가 (Growth)
- **{국가명}**: 전월 대비 **{X}%** 상승. [상세 이유 설명]
- (추가 국가가 있으면 동일 형식으로 나열)

#### 📉 하락세 경계 국가 (Decline)
- **{국가명}**: 전월 대비 **{X}%** 하락. [리스크 요인 설명]
- (추가 국가가 있으면 동일 형식으로 나열)

---

### 🚀 3. 하반기(H2) 전략적 집중 시장 추천

#### 🎯 핵심 타깃 시장: {국가명}
- **추천 이유 1**: [데이터 근거]
- **추천 이유 2**: [성장 잠재력 분석]

#### 🎯 전략적 공략 시장: {국가명}
- **추천 이유 1**: [포지셔닝 전략]
- (필요 시 추천 이유 2)

---

Do not add any introductory or closing paragraphs. Fill the template with real numbers and insights derived from the provided CSV data.`,
  "spec-localizer": "", // 동적 생성 (buildSpecLocalizerSystemPrompt)
  "price-matrix":
    "You are a pricing strategy consultant. Analyze the provided competitor price data. Output Markdown with: 1. Price positioning (Low/Mid/Premium), 2. Key differentiation points to emphasize, 3. 3 logical arguments for price negotiation.",
  "exhibition-report":
    "You are a C-level executive assistant. Based on the provided exhibition consultation data, write a formal 2-page executive summary report in Korean. Use professional corporate language and include a Markdown table for key metrics.",
};

/** spec-localizer: 언어 코드 → 프롬프트용 표시명 (프론트엔드 목록과 동기화) */
const SPEC_LANGUAGE_LABELS: Record<string, string> = {
  auto: "Auto Detect",
  ko: "Korean",
  en: "English",
  ja: "Japanese",
  "zh-CN": "Chinese-Simplified",
  "zh-TW": "Chinese-Traditional",
  es: "Spanish",
  fr: "French",
  de: "German",
  ru: "Russian",
  pt: "Portuguese",
  it: "Italian",
  vi: "Vietnamese",
  th: "Thai",
  id: "Indonesian",
  ar: "Arabic",
};

/** spec-localizer 전용 시스템 프롬프트 (source/target 동적 치환) */
function buildSpecLocalizerSystemPrompt(
  sourceLanguage: string,
  targetLanguage: string
): string {
  const sourceLabel = SPEC_LANGUAGE_LABELS[sourceLanguage] ?? sourceLanguage;
  const targetLabel = SPEC_LANGUAGE_LABELS[targetLanguage] ?? targetLanguage;
  return `You are an elite Native B2B Translator, Localization Expert, and Quality Assurance Editor.
Your task is to translate the provided business text from ${sourceLabel} (if "Auto Detect", identify it first) to ${targetLabel}.

CRITICAL TRANSLATION PROTOCOL:
1. DO NOT do a simple, literal word-for-word translation.
2. Localize the text perfectly into the business culture and formal B2B tone of the target language. Use industry-standard terminology.
3. RIGOROUS REVIEW: Act as your own proofreader. Ensure there are absolutely no grammatical errors, awkward phrasing, or loss of the original business intent.
4. If translating product specs, ensure technical terms remain accurate and professional.

Output Format:
Provide ONLY the final, polished translated text. Do not include introductory filler words like "Here is the translation."`;
}

/** taskType + data 로 사용자 메시지 본문 생성 */
function buildUserMessage(
  taskType: AnalyzeTaskType,
  data: string | Record<string, unknown> | unknown[]
): string {
  if (typeof data === "string") {
    return data.trim() || "No input provided.";
  }
  if (taskType === "spec-localizer" && data && typeof data === "object" && !Array.isArray(data)) {
    const obj = data as Record<string, unknown>;
    const text = String(obj.text ?? "").trim();
    return text || "No text provided.";
  }
  return JSON.stringify(data, null, 2);
}

export async function POST(request: NextRequest) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: "OPENAI_API_KEY is not configured. Set it in environment variables." },
      { status: 503 }
    );
  }

  let body: AnalyzeRequestBody;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON body." },
      { status: 400 }
    );
  }

  const { taskType, data } = body;
  const validTypes: AnalyzeTaskType[] = [
    "buyer-email",
    "sales-analyzer",
    "spec-localizer",
    "price-matrix",
    "exhibition-report",
  ];
  if (!taskType || !validTypes.includes(taskType as AnalyzeTaskType)) {
    return NextResponse.json(
      { error: "Missing or invalid taskType. Must be one of: " + validTypes.join(", ") },
      { status: 400 }
    );
  }

  if (data === undefined || data === null) {
    return NextResponse.json(
      { error: "Missing data in request body." },
      { status: 400 }
    );
  }

  const openai = new OpenAI({ apiKey });
  const task = taskType as AnalyzeTaskType;
  let systemPrompt = SYSTEM_PROMPTS[task];
  if (task === "spec-localizer" && data && typeof data === "object" && !Array.isArray(data)) {
    const obj = data as Record<string, unknown>;
    const source = String(obj.sourceLanguage ?? "auto");
    const target = String(obj.targetLanguage ?? "en");
    systemPrompt = buildSpecLocalizerSystemPrompt(source, target);
  }
  const userContent = buildUserMessage(task, data);

  try {
    const completion = await openai.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userContent },
      ],
      temperature: 0.6,
    });

    const content =
      completion.choices[0]?.message?.content?.trim() ??
      "No response generated. Please try again.";
    return NextResponse.json({ content });
  } catch (err) {
    const message = err instanceof Error ? err.message : "OpenAI API request failed.";
    const status = message.includes("API key") ? 503 : 502;
    return NextResponse.json(
      { error: message },
      { status }
    );
  }
}
