/**
 * /api/analyze 호출 클라이언트 - 서버에서 OpenAI 호출로 API 키 보호
 */
export type AnalyzeTaskType =
  | "buyer-email"
  | "sales-analyzer"
  | "spec-localizer"
  | "price-matrix"
  | "exhibition-report";

export interface AnalyzeApiResponse {
  content: string;
}

export interface AnalyzeApiError {
  error: string;
}

/** API에 보낼 데이터 타입 (JSON 직렬화 가능) */
export type AnalyzePayload = string | Record<string, unknown> | unknown[] | object;

/** POST /api/analyze 호출 후 마크다운 content 반환. 실패 시 에러 메시지 throw */
export async function callAnalyzeApi(
  taskType: AnalyzeTaskType,
  data: AnalyzePayload
): Promise<string> {
  const res = await fetch("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ taskType, data }),
  });

  const json = await res.json().catch(() => ({}));

  if (!res.ok) {
    const message =
      (json as AnalyzeApiError).error ??
      `Request failed (${res.status}). Check API key and try again.`;
    throw new Error(message);
  }

  const content = (json as AnalyzeApiResponse).content;
  if (typeof content !== "string") {
    throw new Error("Invalid response: missing content.");
  }
  return content;
}
