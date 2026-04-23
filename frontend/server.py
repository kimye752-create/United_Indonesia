"""분석 대시보드 서버: SSE 실시간 로그 + 분석/보고서 API."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=True)
except ImportError:
    pass

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frontend.dashboard_sites import DASHBOARD_SITES

STATIC = Path(__file__).resolve().parent / "static"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

_state: dict[str, Any] = {
    "events": [],
    "lock": None,
}


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _state["lock"] = asyncio.Lock()
    yield


app = FastAPI(title="ID Analysis Dashboard", version="4.0.0", lifespan=_lifespan)

import os as _os
_cors_origins = _os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _emit(event: dict[str, Any]) -> None:
    payload = {**event, "ts": time.time()}
    lock = _state["lock"]
    if lock is None:
        return
    async with lock:
        _state["events"].append(payload)
        if len(_state["events"]) > 500:
            _state["events"] = _state["events"][-400:]


# ── API 키 런타임 설정 ────────────────────────────────────────────────────────

class ApiKeysBody(BaseModel):
    perplexity_api_key: str = ""
    anthropic_api_key:  str = ""


@app.post("/api/settings/keys")
async def set_api_keys(body: ApiKeysBody) -> JSONResponse:
    """프론트엔드에서 API 키를 런타임에 설정 (프로세스 환경변수 갱신)."""
    import os
    updated: list[str] = []
    if body.perplexity_api_key.strip():
        os.environ["PERPLEXITY_API_KEY"] = body.perplexity_api_key.strip()
        updated.append("PERPLEXITY_API_KEY")
    if body.anthropic_api_key.strip():
        os.environ["ANTHROPIC_API_KEY"] = body.anthropic_api_key.strip()
        updated.append("ANTHROPIC_API_KEY")
    return JSONResponse({"ok": True, "updated": updated})


@app.get("/api/settings/keys/status")
async def get_keys_status() -> JSONResponse:
    """현재 API 키 설정 여부 확인 (값은 노출하지 않음)."""
    import os
    return JSONResponse({
        "perplexity": bool(os.environ.get("PERPLEXITY_API_KEY", "").strip()),
        "anthropic":  bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()),
    })


# ── 분석 ──────────────────────────────────────────────────────────────────────

_analysis_cache: dict[str, Any] = {"result": None, "running": False}


class AnalyzeBody(BaseModel):
    use_perplexity: bool = True
    force_refresh: bool = False


@app.post("/api/analyze")
async def trigger_analyze(body: AnalyzeBody | None = None) -> JSONResponse:
    """8품목 수출 적합성 분석 실행 (Claude API + Perplexity 보조)."""
    req = body if body is not None else AnalyzeBody()
    if _analysis_cache["running"]:
        raise HTTPException(status_code=409, detail="분석이 이미 실행 중입니다.")
    if _analysis_cache["result"] and not req.force_refresh:
        return JSONResponse({"ok": True, "message": "캐시된 분석 결과 사용. force_refresh=true로 재실행."})

    async def _run() -> None:
        _analysis_cache["running"] = True
        try:
            from analysis.id_export_analyzer import analyze_all
            from analysis.perplexity_references import fetch_all_references

            results = await analyze_all(use_perplexity=req.use_perplexity)
            pids = [r["product_id"] for r in results]
            refs = await fetch_all_references(pids)
            for r in results:
                r["references"] = refs.get(r["product_id"], [])
            _analysis_cache["result"] = results
        finally:
            _analysis_cache["running"] = False

    asyncio.create_task(_run())
    return JSONResponse({"ok": True, "message": "분석을 백그라운드에서 시작했습니다."})


@app.get("/api/analyze/result")
async def analyze_result() -> JSONResponse:
    if _analysis_cache["running"]:
        return JSONResponse({"status": "running"}, status_code=202)
    if not _analysis_cache["result"]:
        raise HTTPException(status_code=404, detail="분석 결과 없음. POST /api/analyze 먼저 실행")
    return JSONResponse({
        "status": "done",
        "count": len(_analysis_cache["result"]),
        "results": _analysis_cache["result"],
    })


@app.get("/api/analyze/status")
async def analyze_status() -> dict[str, Any]:
    return {
        "running": _analysis_cache["running"],
        "has_result": _analysis_cache["result"] is not None,
        "product_count": len(_analysis_cache["result"]) if _analysis_cache["result"] else 0,
    }


# ── 시장 신호 · 뉴스 (Perplexity) ─────────────────────────────────────────────

_news_cache: dict[str, Any] = {"data": None, "ts": 0.0}
_NEWS_TTL = 1800  # 30분 캐시


_NEWS_VALID_CATEGORIES = {"BPOM", "JKN", "e-Katalog", "Kemenkes", "제약사", "수출입", "정책", "기타"}


def _parse_perplexity_news_items(raw_text: str) -> list[dict[str, str]]:
    """Perplexity 텍스트 응답에서 뉴스 배열(JSON) 파싱."""
    import re

    text = (raw_text or "").strip()
    if not text:
        return []

    # JSON 배열 추출 (마크다운 코드블록 → 최상위 배열 순서로 시도)
    candidates: list[str] = []
    for m in re.finditer(r"```(?:json)?\s*(\[.*?\])\s*```", text, flags=re.S):
        candidates.append(m.group(1))
    m2 = re.search(r"\[\s*\{.*\}\s*\]", text, flags=re.S)
    if m2:
        candidates.append(m2.group(0))
    candidates.append(text)

    for cand in candidates:
        try:
            parsed = json.loads(cand)
        except Exception:
            continue
        if not isinstance(parsed, list):
            continue
        items: list[dict[str, str]] = []
        for row in parsed[:8]:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title", "") or "").strip()
            if not title:
                continue
            cat = str(row.get("category", "") or "기타").strip()
            if cat not in _NEWS_VALID_CATEGORIES:
                cat = "기타"
            items.append(
                {
                    "title":    title,
                    "source":   str(row.get("source",   "") or "").strip(),
                    "date":     str(row.get("date",     "") or "").strip(),
                    "link":     str(row.get("link",     "") or "").strip(),
                    "category": cat,
                }
            )
        if items:
            return items
    return []


def _is_korean(text: str) -> bool:
    """문자열에 한글이 충분히 포함되어 있는지 확인."""
    korean_chars = sum(1 for c in text if "\uAC00" <= c <= "\uD7A3")
    return korean_chars >= 2


async def _translate_titles_to_korean(items: list[dict[str, str]]) -> list[dict[str, str]]:
    """영문/인니어 제목을 Claude API로 한국어 번역 (한글이 이미 충분하면 스킵)."""
    import os
    import httpx

    # 번역이 필요한 항목 추출
    to_translate = [
        (i, item["title"])
        for i, item in enumerate(items)
        if not _is_korean(item["title"])
    ]
    if not to_translate:
        return items

    claude_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not claude_key:
        # Claude 키 없으면 원문 그대로 반환
        return items

    titles_text = "\n".join(f"{idx}. {title}" for idx, (_, title) in enumerate(to_translate, 1))

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": claude_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5",
                    "max_tokens": 512,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "다음 의약품/제약 뉴스 제목들을 자연스러운 한국어로 번역해 주세요. "
                                "번호와 번역된 제목만 출력하고, 설명이나 부연은 생략하세요.\n\n"
                                f"{titles_text}"
                            ),
                        }
                    ],
                },
            )
            resp.raise_for_status()
            reply = resp.json()["content"][0]["text"].strip()

        # "1. 번역된 제목" 형식 파싱
        import re
        translated_map: dict[int, str] = {}
        for line in reply.splitlines():
            m = re.match(r"^(\d+)\.\s+(.+)", line.strip())
            if m:
                translated_map[int(m.group(1))] = m.group(2).strip()

        result = [item.copy() for item in items]
        for seq, (orig_idx, _) in enumerate(to_translate, 1):
            if seq in translated_map:
                result[orig_idx]["title"] = translated_map[seq]
        return result
    except Exception:
        # 번역 실패 시 원문 유지
        return items


@app.get("/api/news")
async def api_news() -> JSONResponse:
    """Perplexity 기반 인도네시아 제약 시장 뉴스 (30분 캐시)."""
    import time as _time
    import os
    import httpx

    if _news_cache["data"] and _time.time() - _news_cache["ts"] < _NEWS_TTL:
        return JSONResponse(_news_cache["data"])

    px_key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
    if not px_key:
        return JSONResponse({"ok": False, "error": "PERPLEXITY_API_KEY 미설정", "items": []})

    try:
        payload = {
            "model": "sonar-pro",
            "search_recency_filter": "year",   # 최근 1년 (2025-2026) 기사 우선
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an Indonesia pharmaceutical market intelligence analyst. "
                        "Today is April 2026. Focus EXCLUSIVELY on news and events from 2026 (January–April 2026). "
                        "If 2026 items are fewer than 8, you may add items from late 2025 (Oct–Dec 2025) to fill up. "
                        "Return ONLY a valid JSON array — no markdown fences, no explanation text, no preamble. "
                        "Array must contain 6–8 objects. Each object keys:\n"
                        "  title    — headline in KOREAN (한국어) only, natural fluent translation required\n"
                        "  source   — publisher/outlet name (English or Indonesian OK)\n"
                        "  date     — publish date as 'YYYY-MM-DD' or 'YYYY년 MM월' format\n"
                        "  link     — direct URL to the article (empty string if unavailable)\n"
                        "  category — ONE of: BPOM | JKN | e-Katalog | Kemenkes | 제약사 | 수출입 | 정책 | 기타\n\n"
                        "Topic scope (pick diverse mix):\n"
                        "  · BPOM drug approvals, registration policy, GMP enforcement\n"
                        "  · JKN/FORNAS formulary updates, BPJS Kesehatan coverage changes\n"
                        "  · LKPP e-Katalog HET price revisions, procurement tenders\n"
                        "  · Kemenkes regulations, TKDN local content rules, halal pharma\n"
                        "  · Major Indonesian pharma (Kalbe Farma, Kimia Farma, Sanbe, Dexa Medica) corporate news\n"
                        "  · International pharma companies entering/expanding in Indonesia\n"
                        "  · Indonesia pharma exports/imports, trade policy\n\n"
                        "STRICT OUTPUT RULE: Output ONLY the JSON array. No surrounding text whatsoever."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "2026년 인도네시아 제약 시장 최신 뉴스 8건을 JSON 배열로 반환하세요. "
                        "가능한 한 2026년 기사를 우선하고, 부족하면 2025년 4분기 기사로 보충하세요. "
                        "title은 반드시 자연스러운 한국어 번역. source·date·link·category 모두 포함. "
                        "JSON 배열 외 다른 텍스트 없이 출력."
                    ),
                },
            ],
            "max_tokens": 2000,
            "temperature": 0.1,
        }
        headers = {
            "Authorization": f"Bearer {px_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            raw = resp.json()

        content = str(
            raw.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        items = _parse_perplexity_news_items(content)
        if not items:
            return JSONResponse({"ok": False, "error": "Perplexity 응답 파싱 실패", "items": []})

        # 영문/인니어 제목이 섞여 있으면 Claude로 한국어 번역
        items = await _translate_titles_to_korean(items)

        data = {"ok": True, "items": items}
        _news_cache["data"] = data
        _news_cache["ts"]   = _time.time()
        return JSONResponse(data)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)[:120], "items": []})


# ── 거시지표 ──────────────────────────────────────────────────────────────────

@app.get("/api/macro")
async def api_macro() -> JSONResponse:
    from utils.id_macro import get_id_macro
    return JSONResponse(get_id_macro())


# ── 환율 (yfinance SGD/KRW) ───────────────────────────────────────────────────

_exchange_cache: dict[str, Any] = {"data": None, "ts": 0.0}
_EXCHANGE_TTL_SEC = 0.0


@app.get("/api/exchange")
async def api_exchange() -> JSONResponse:
    """IDR/KRW 실시간 환율 (yfinance). 준실시간 제공."""
    import time as _time

    if _exchange_cache["data"] and _time.time() - _exchange_cache["ts"] < _EXCHANGE_TTL_SEC:
        return JSONResponse(_exchange_cache["data"])

    def _fetch() -> dict[str, Any]:
        from utils.id_macro import get_idr_krw
        idr = get_idr_krw()
        import yfinance as yf  # type: ignore[import]
        usd_krw = float(yf.Ticker("USDKRW=X").fast_info.last_price)
        usd_idr = float(yf.Ticker("USDIDR=X").fast_info.last_price)
        return {
            "idr_krw":  round(idr["rate"], 6),
            "usd_krw":  round(usd_krw, 2),
            "usd_idr":  round(usd_idr, 2),
            "display":  idr["display"],
            "source":   "Yahoo Finance",
            "fetched_at": _time.time(),
            "ok": True,
        }

    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, _fetch)
        _exchange_cache["data"] = data
        _exchange_cache["ts"]   = _time.time()
        return JSONResponse(data)
    except Exception as exc:
        fallback: dict[str, Any] = {
            "idr_krw":  0.082,
            "usd_krw":  1393.0,
            "usd_idr":  15900.0,
            "display":  "1 IDR ≈ 0.0820 KRW (정적 폴백)",
            "source":   "폴백 (Yahoo Finance 연결 실패)",
            "fetched_at": _time.time(),
            "ok":       False,
            "error":    str(exc),
        }
        return JSONResponse(fallback)


# ── 현장 크롤링 API ──────────────────────────────────────────────────────────

_CRAWL_TTL   = 1800  # 30분 캐시
_crawl_cache: dict[str, dict[str, Any]] = {}  # key: "{site}:{keyword}"

_SITE_CRAWLERS = {
    "bpom":      "utils.id_bpom_crawler",
    "ekatalog":  "utils.id_ekatalog_crawler",
    "halodoc":   "utils.id_halodoc_crawler",
    "fornas":    "utils.id_fornas_crawler",
    "k24klik":   "utils.id_k24klik_crawler",
    "swiperx":   "utils.id_swiperx_crawler",
    "mims":      "utils.id_mims_crawler",
}

_SITE_FN_MAP = {
    "bpom":     ("search_bpom",     {}),
    "ekatalog": ("search_ekatalog", {}),
    "halodoc":  ("search_halodoc",  {}),
    "fornas":   ("search_fornas",   {}),
    "k24klik":  ("search_k24klik",  {}),
    "swiperx":  ("search_swiperx",  {}),
    "mims":     ("search_mims",     {}),
}


@app.get("/api/crawl/all/{keyword}")
async def api_crawl_all(keyword: str) -> JSONResponse:
    """7개 사이트 전체에서 동시 크롤링 (병렬).

    Returns: 사이트별 결과 딕셔너리
    """
    import time as _time
    import importlib

    async def _run_one(site: str) -> tuple[str, list]:
        try:
            mod_name = _SITE_CRAWLERS[site]
            fn_name, fn_kwargs = _SITE_FN_MAP[site]
            mod = importlib.import_module(mod_name)
            fn  = getattr(mod, fn_name)
            items = await fn(keyword, max_results=10, **fn_kwargs)
            return site, items
        except Exception as exc:
            return site, [{"error": str(exc)[:120]}]

    tasks   = [_run_one(site) for site in _SITE_CRAWLERS]
    results = await asyncio.gather(*tasks)
    combined: dict[str, Any] = {site: items for site, items in results}
    total = sum(len(v) for v in combined.values() if isinstance(v, list))
    return JSONResponse({"ok": True, "keyword": keyword, "total": total, "by_site": combined})


@app.get("/api/crawl/{site}/{keyword}")
async def api_crawl(site: str, keyword: str) -> JSONResponse:
    """지정 사이트에서 키워드로 크롤링 (30분 캐시).

    site: bpom | ekatalog | halodoc | fornas | k24klik | swiperx | mims
    keyword: INN 성분명 또는 제품명 (URL 인코딩)
    """
    import time as _time
    import importlib

    site = site.lower().strip()
    if site not in _SITE_CRAWLERS:
        return JSONResponse({"ok": False, "error": f"지원하지 않는 사이트: {site}. 가능: {list(_SITE_CRAWLERS)}", "items": []})

    cache_key = f"{site}:{keyword}"
    cached = _crawl_cache.get(cache_key)
    if cached and _time.time() - cached["ts"] < _CRAWL_TTL:
        return JSONResponse(cached["data"])

    try:
        mod_name = _SITE_CRAWLERS[site]
        fn_name, fn_kwargs = _SITE_FN_MAP[site]
        mod = importlib.import_module(mod_name)
        fn  = getattr(mod, fn_name)
        items = await fn(keyword, max_results=20, **fn_kwargs)
        data  = {"ok": True, "site": site, "keyword": keyword, "count": len(items), "items": items}
        _crawl_cache[cache_key] = {"data": data, "ts": _time.time()}
        return JSONResponse(data)
    except Exception as exc:
        return JSONResponse({"ok": False, "site": site, "keyword": keyword, "error": str(exc)[:200], "items": []})


# ── 단일 품목 파이프라인 (분석 + 논문 + PDF) ──────────────────────────────────

_pipeline_tasks: dict[str, dict[str, Any]] = {}


async def _run_pipeline_for_product(product_key: str) -> None:
    task = _pipeline_tasks[product_key]
    try:
        # 0. DB 조회 (Supabase)
        task.update({"step": "db_load", "step_label": "Supabase 데이터 로드 중…"})
        await _emit({"phase": "pipeline", "message": f"{product_key} — DB 조회 중", "level": "info"})

        # DB 조회 생략 (ID 분석기는 내장 메타 사용)
        await _emit({"phase": "pipeline", "message": f"{product_key} — 준비 완료", "level": "info"})

        # 1. Claude 분석
        task.update({"step": "analyze", "step_label": "Claude 분석 중…"})
        await _emit({"phase": "pipeline", "message": f"{product_key} — 분석 시작", "level": "info"})

        from analysis.id_export_analyzer import analyze_product
        result = await analyze_product(product_key)
        task["result"] = result
        verdict = result.get("verdict") or "미분석"
        await _emit({"phase": "pipeline", "message": f"분석 완료 — {verdict}", "level": "success"})

        # 2. Perplexity 논문
        task.update({"step": "refs", "step_label": "논문 검색 중…"})
        from analysis.perplexity_references import fetch_references
        refs = await fetch_references(product_key)
        task["refs"] = refs
        if refs:
            await _emit({"phase": "pipeline", "message": f"논문 {len(refs)}건 검색 완료", "level": "success"})

        # 3. PDF 보고서 (in-process 생성 — subprocess 의존성 제거)
        task.update({"step": "report", "step_label": "PDF 생성 중…"})
        await _emit({"phase": "pipeline", "message": "PDF 보고서 생성 중…", "level": "info"})

        from datetime import datetime, timezone as _tz
        from report_generator import build_report, render_pdf

        _ts = datetime.now(_tz.utc).strftime("%Y%m%d_%H%M%S")
        _reports_dir = ROOT / "reports"
        _reports_dir.mkdir(parents=True, exist_ok=True)

        # ID 파이프라인은 Supabase 불필요 — 빈 리스트 전달 (id_export_analyzer 내장 메타 사용)
        _refs_map = {product_key: refs}
        _report = await asyncio.to_thread(
            lambda: build_report(
                [],
                datetime.now(_tz.utc).isoformat(),
                [result],
                references=_refs_map,
            )
        )
        _pdf_name = f"id_report_{product_key}_{_ts}.pdf"
        _pdf_path = _reports_dir / _pdf_name
        await asyncio.to_thread(render_pdf, _report, _pdf_path)

        task["pdf"] = _pdf_name
        task.update({"status": "done", "step": "done", "step_label": "완료"})
        await _emit({"phase": "pipeline", "message": "파이프라인 완료", "level": "success"})

    except Exception as exc:
        task.update({"status": "error", "step": "error", "step_label": str(exc)})
        await _emit({"phase": "pipeline", "message": f"오류: {exc}", "level": "error"})


# ── 신약(커스텀) 파이프라인 ────────────────────────────────────────────────────
# 주의: 리터럴 경로("/api/pipeline/custom/...")는 반드시 {product_key} 라우트보다 먼저 선언

_custom_task: dict[str, Any] = {}


class CustomDrugBody(BaseModel):
    trade_name: str
    inn: str
    dosage_form: str = ""


async def _run_custom_pipeline(trade_name: str, inn: str, dosage_form: str) -> None:
    global _custom_task
    try:
        # Step 1: Claude 분석
        _custom_task.update({"step": "analyze", "step_label": "Claude 분석 중…"})
        from analysis.id_export_analyzer import analyze_custom_product
        result = await analyze_custom_product(trade_name, inn, dosage_form)
        _custom_task["result"] = result

        # Step 2: Perplexity 논문
        _custom_task.update({"step": "refs", "step_label": "논문 검색 중…"})
        from analysis.perplexity_references import fetch_references_for_custom
        refs = await fetch_references_for_custom(trade_name, inn)
        _custom_task["refs"] = refs

        # Step 3: PDF 보고서 (in-process)
        _custom_task.update({"step": "report", "step_label": "PDF 생성 중…"})
        from datetime import datetime, timezone as _tz2
        from report_generator import build_report, render_pdf
        from utils.db import fetch_kup_products

        _ts2 = datetime.now(_tz2.utc).strftime("%Y%m%d_%H%M%S")
        _reports_dir2 = ROOT / "reports"
        _reports_dir2.mkdir(parents=True, exist_ok=True)

        _products_db2 = await asyncio.to_thread(fetch_kup_products, "ID")
        _refs_map2 = {"custom": refs}
        _report2 = await asyncio.to_thread(
            lambda: build_report(
                _products_db2,
                datetime.now(_tz2.utc).isoformat(),
                [result],
                references=_refs_map2,
            )
        )
        _pdf_name2 = f"id_report_custom_{_ts2}.pdf"
        _pdf_path2 = _reports_dir2 / _pdf_name2
        await asyncio.to_thread(render_pdf, _report2, _pdf_path2)

        _custom_task["pdf"] = _pdf_name2
        _custom_task.update({"status": "done", "step": "done", "step_label": "완료"})

    except Exception as exc:
        _custom_task.update({"status": "error", "step": "error", "step_label": str(exc)})


@app.post("/api/pipeline/custom")
async def trigger_custom_pipeline(body: CustomDrugBody) -> JSONResponse:
    global _custom_task
    if _custom_task.get("status") == "running":
        raise HTTPException(status_code=409, detail="신약 분석이 이미 실행 중입니다.")
    _custom_task = {
        "status": "running", "step": "analyze", "step_label": "시작 중…",
        "result": None, "refs": [], "pdf": None,
    }
    asyncio.create_task(_run_custom_pipeline(body.trade_name, body.inn, body.dosage_form))
    return JSONResponse({"ok": True})


@app.get("/api/pipeline/custom/status")
async def custom_pipeline_status() -> JSONResponse:
    if not _custom_task:
        return JSONResponse({"status": "idle"})
    return JSONResponse({
        "status":     _custom_task.get("status", "idle"),
        "step":       _custom_task.get("step", ""),
        "step_label": _custom_task.get("step_label", ""),
        "has_result": _custom_task.get("result") is not None,
        "has_pdf":    bool(_custom_task.get("pdf")),
    })


@app.get("/api/pipeline/custom/result")
async def custom_pipeline_result() -> JSONResponse:
    if not _custom_task:
        raise HTTPException(404, "신약 분석 미실행")
    return JSONResponse({
        "status": _custom_task.get("status"),
        "result": _custom_task.get("result"),
        "refs":   _custom_task.get("refs", []),
        "pdf":    _custom_task.get("pdf"),
    })


# ── 기존 품목 파이프라인 ──────────────────────────────────────────────────────

@app.post("/api/pipeline/{product_key}")
async def trigger_pipeline(product_key: str) -> JSONResponse:
    if _pipeline_tasks.get(product_key, {}).get("status") == "running":
        raise HTTPException(status_code=409, detail="이미 실행 중입니다.")
    _pipeline_tasks[product_key] = {
        "status": "running", "step": "init", "step_label": "시작 중…",
        "result": None, "refs": [], "pdf": None,
    }
    asyncio.create_task(_run_pipeline_for_product(product_key))
    return JSONResponse({"ok": True, "message": "파이프라인 시작됨"})


@app.get("/api/pipeline/{product_key}/status")
async def pipeline_status(product_key: str) -> JSONResponse:
    task = _pipeline_tasks.get(product_key)
    if not task:
        return JSONResponse({"status": "idle"})
    return JSONResponse({
        "status":     task["status"],
        "step":       task["step"],
        "step_label": task["step_label"],
        "has_result": task["result"] is not None,
        "has_pdf":    bool(task["pdf"]),
        "ref_count":  len(task.get("refs", [])),
    })


@app.get("/api/pipeline/{product_key}/result")
async def pipeline_result(product_key: str) -> JSONResponse:
    task = _pipeline_tasks.get(product_key)
    if not task:
        raise HTTPException(404, "파이프라인 미실행")
    return JSONResponse({
        "status": task["status"],
        "step":   task["step"],
        "result": task.get("result"),
        "refs":   task.get("refs", []),
        "pdf":    task.get("pdf"),
    })


# ── 보고서 ────────────────────────────────────────────────────────────────────

_report_cache: dict[str, Any] = {"path": None, "running": False}

def _latest_report_pdf() -> Path | None:
    reports_dir = ROOT / "reports"
    if not reports_dir.exists():
        return None
    pdfs = [p for p in reports_dir.glob("id_report_*.pdf") if p.is_file()]
    if not pdfs:
        return None
    return max(pdfs, key=lambda p: p.stat().st_mtime)


class ReportBody(BaseModel):
    run_analysis: bool = False
    use_perplexity: bool = False


@app.post("/api/report")
async def trigger_report(body: ReportBody | None = None) -> JSONResponse:
    req = body if body is not None else ReportBody()
    if _report_cache["running"]:
        raise HTTPException(status_code=409, detail="보고서 생성이 이미 실행 중입니다.")

    async def _run_report() -> None:
        _report_cache["running"] = True
        try:
            import subprocess
            cmd = [
                sys.executable, str(ROOT / "report_generator.py"),
                "--out", str(ROOT / "reports"),
            ]
            if req.run_analysis:
                cmd.append("--run-analysis")
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: subprocess.run(cmd, capture_output=True, text=True)
            )
            reports_dir = ROOT / "reports"
            pdfs = sorted(reports_dir.glob("id_report_*.pdf"), reverse=True)
            _report_cache["path"] = str(pdfs[0]) if pdfs else None
        finally:
            _report_cache["running"] = False

    asyncio.create_task(_run_report())
    return JSONResponse({"ok": True, "message": "보고서 생성을 백그라운드에서 시작했습니다."})


@app.get("/api/report/status")
async def report_status() -> dict[str, Any]:
    reports_dir = ROOT / "reports"
    pdfs = [p for p in reports_dir.glob("id_report_*.pdf")] if reports_dir.exists() else []
    latest = _latest_report_pdf()
    return {
        "running": _report_cache["running"],
        "latest_pdf": str(latest) if latest else _report_cache["path"],
        "pdf_count": len(pdfs),
    }


@app.get("/api/report/download")
async def download_report(name: str | None = None, inline: bool = False) -> Any:
    """PDF 반환. inline=true면 브라우저/iframe 미리보기용(Content-Disposition: inline)."""
    reports_dir = ROOT / "reports"
    disp = "inline" if inline else "attachment"
    if name:
        target = reports_dir / Path(name).name
        if target.is_file():
            return FileResponse(
                str(target),
                media_type="application/pdf",
                filename=target.name,
                content_disposition_type=disp,
            )

    latest = _latest_report_pdf()
    if not latest:
        raise HTTPException(status_code=404, detail="생성된 보고서 없음. POST /api/report 먼저 실행")
    return FileResponse(
        str(latest),
        media_type="application/pdf",
        filename=latest.name,
        content_disposition_type=disp,
    )


# ── DOCX 보고서 생성 (gen_id_report.js 연동) ─────────────────────────────────

@app.get("/api/report/docx/generate")
async def generate_docx_report(
    report_type: str = "final",  # p1 | p2 | p3 | final
    product_key: str = "",
) -> Any:
    """gen_id_report.js를 호출해 DOCX 보고서를 생성하고 반환."""
    import subprocess
    import tempfile
    import re as _re_dx
    from datetime import datetime, timezone as _tz_dx

    # ── 데이터 수집 ────────────────────────────────────────────────────────────
    # P1: 최신 시장조사 파이프라인 결과
    p1_result = None
    for key, task in _pipeline_tasks.items():
        if task.get("result"):
            p1_result = task["result"]
            if not product_key:
                product_key = key
            break
    if p1_result is None and _custom_task.get("result"):
        p1_result = _custom_task["result"]

    # P2: AI 가격 분석 결과
    p2_extracted  = _p2_ai_task.get("extracted")  if _p2_ai_task else None
    p2_analysis   = _p2_ai_task.get("analysis")   if _p2_ai_task else None
    p2_rates      = _p2_ai_task.get("exchange_rates") if _p2_ai_task else None

    # P3: 바이어 발굴 결과
    p3_buyers = _buyer_task.get("buyers", []) if _buyer_task else []

    # ── meta ───────────────────────────────────────────────────────────────────
    prod_label = _PROD_LABELS.get(product_key, p1_result.get("trade_name", "미상") if p1_result else "미상")
    inn_label  = (p1_result.get("inn", "") if p1_result else
                  (p2_extracted.get("product_name", "") if p2_extracted else ""))
    today_str  = datetime.now(_tz_dx.utc).strftime("%Y년 %m월 %d일")

    # hs_code: p1_result 또는 _PRODUCT_META에서 가져오기
    _hs_code = ""
    if p1_result:
        _hs_code = p1_result.get("hs_code", "")
    if not _hs_code and product_key:
        from analysis.id_export_analyzer import _get_product_meta as _get_pm
        for _pm in _get_pm():
            if _pm.get("product_id") == product_key:
                _hs_code = _pm.get("hs_code", "")
                break

    data_json: dict[str, Any] = {
        "meta": {
            "country":      "인도네시아",
            "company":      "한국유나이티드제약(주)",
            "date":         today_str,
            "product_name": prod_label,
            "inn":          inn_label,
            "product_key":  product_key,
            "hs_code":      _hs_code,
        },
    }

    # ── P1 ────────────────────────────────────────────────────────────────────
    # 거시지표 폴백 (p1_result에 없을 경우 id_macro에서 주입)
    from utils.id_macro import get_id_macro as _get_macro
    _macro_map = {m["label"]: m["value"] for m in _get_macro()}

    if p1_result:
        # P2에서 추출된 상세 제품 정보도 병합 (ekatalog_price_hint 등)
        _ref_price = (
            p1_result.get("ref_price_text") or
            p1_result.get("price_positioning_pbs") or
            (p2_extracted.get("ref_price_text") if p2_extracted else "") or ""
        )
        _entry = (
            p1_result.get("entry_pathway") or
            p1_result.get("basis_procurement") or ""
        )
        _risks = p1_result.get("risks_conditions", "")

        # sources: 문자열 목록으로 정규화
        _raw_sources = p1_result.get("sources", [])
        _sources_list: list[str] = []
        for s in _raw_sources:
            if isinstance(s, dict):
                _sources_list.append(f"{s.get('name','')}{' — '+s.get('description','') if s.get('description') else ''}")
            elif s:
                _sources_list.append(str(s))

        # papers: references 필드 우선, papers 필드 폴백
        _papers = p1_result.get("references") or p1_result.get("papers", [])

        data_json["p1"] = {
            "product_name":         p1_result.get("trade_name", prod_label),
            "inn":                  p1_result.get("inn", inn_label),
            "dosage_form":          p1_result.get("dosage_form", ""),
            "therapeutic_area":     p1_result.get("therapeutic_area", ""),
            "hs_code":              p1_result.get("hs_code", _hs_code),
            "verdict":              p1_result.get("verdict", "미상"),
            "verdict_label":        {"적합": "수출 적합", "조건부": "조건부 적합", "부적합": "수출 부적합"}.get(
                                        p1_result.get("verdict", ""), p1_result.get("verdict", "미분석")),
            "rationale":            p1_result.get("rationale", ""),
            # 거시지표 (macro DB 우선, 분석 결과 보완)
            "population":           p1_result.get("population") or _macro_map.get("인구", "2억 8,100만 명"),
            "gdp_per_capita":       p1_result.get("gdp_per_capita") or _macro_map.get("1인당 GDP", "USD 4,941"),
            "pharma_market":        p1_result.get("pharma_market") or _macro_map.get("의약품 시장 규모", "USD 87억"),
            "health_spend":         p1_result.get("health_spend", "GDP 대비 약 3.2%  (WHO 2023)"),
            "import_dep":           p1_result.get("import_dep") or _macro_map.get("의약품 수입 의존도", "약 90%"),
            "disease_prevalence":   p1_result.get("disease_prevalence", ""),
            "related_market":       p1_result.get("related_market", ""),
            # 섹션별 분석 텍스트
            "basis_market_medical": p1_result.get("basis_market_medical", ""),
            "bpom_reg":             p1_result.get("bpom_reg", ""),
            "entry_pathway":        _entry,
            "basis_trade":          p1_result.get("basis_trade") or p1_result.get("basis_distribution", ""),
            "basis_clinical":       p1_result.get("basis_clinical", ""),
            "basis_regulatory":     p1_result.get("basis_regulatory", ""),
            # 가격
            "ref_price_text":       p1_result.get("ref_price_text", ""),
            "price_positioning_pbs": p1_result.get("price_positioning_pbs") or _ref_price,
            "ekatalog_price_hint":  p1_result.get("ekatalog_price_hint", ""),
            # 리스크
            "risks_conditions":     _risks,
            # 출처·논문
            "papers":               _papers,
            "sources":              _sources_list,
        }
    else:
        data_json["p1"] = None

    # ── P2 ────────────────────────────────────────────────────────────────────
    if p2_analysis:
        data_json["p2"] = {
            "extracted":      p2_extracted or {},
            "analysis":       p2_analysis,
            "exchange_rates": p2_rates or {"usd_idr": 16200, "idr_krw": 0.082, "usd_krw": 1399},
        }
    else:
        data_json["p2"] = None

    # ── P3 ────────────────────────────────────────────────────────────────────
    if p3_buyers:
        data_json["p3"] = {"buyers": p3_buyers}
    else:
        data_json["p3"] = None

    # ── 타입 검증 ───────────────────────────────────────────────────────────────
    if report_type not in ("p1", "p2", "p3", "final"):
        raise HTTPException(400, f"report_type must be p1|p2|p3|final, got: {report_type}")

    # ── 필수 데이터 체크 ────────────────────────────────────────────────────────
    needed = {"p1": p1_result, "p2": p2_analysis, "p3": p3_buyers or None}
    if report_type == "final":
        missing = [k for k, v in needed.items() if not v]
        if missing:
            raise HTTPException(400, f"최종 보고서 생성에 필요한 데이터가 없습니다: {', '.join(missing).upper()}. 각 분석을 먼저 실행하세요.")
    elif report_type == "p1" and not p1_result:
        raise HTTPException(400, "P1(시장조사) 분석이 완료되지 않았습니다. 분석 실행 후 다시 시도하세요.")
    elif report_type == "p2" and not p2_analysis:
        raise HTTPException(400, "P2(가격전략) 분석이 완료되지 않았습니다. AI 가격 분석 후 다시 시도하세요.")
    elif report_type == "p3" and not p3_buyers:
        raise HTTPException(400, "P3(바이어) 분석이 완료되지 않았습니다. 바이어 발굴 후 다시 시도하세요.")

    # ── 파일 생성 ───────────────────────────────────────────────────────────────
    _ts_dx = datetime.now(_tz_dx.utc).strftime("%Y%m%d_%H%M%S")
    _safe_prod = _re_dx.sub(r"[^\w가-힣]", "_", prod_label)[:20] or "product"
    docx_name   = f"ID_{report_type}_{_safe_prod}_{_ts_dx}.docx"
    docx_path   = ROOT / "reports" / docx_name
    (ROOT / "reports").mkdir(parents=True, exist_ok=True)

    # JSON → temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as tf:
        json.dump(data_json, tf, ensure_ascii=False, indent=2)
        tmp_json = tf.name

    # node 실행
    gen_script = ROOT / "gen_id_report.js"
    try:
        proc = await asyncio.to_thread(
            lambda: subprocess.run(
                ["node", str(gen_script), tmp_json, str(docx_path), "--type", report_type],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
                timeout=60,
            )
        )
        if proc.returncode != 0:
            err_detail = (proc.stderr or proc.stdout or "")[:400]
            raise HTTPException(500, f"DOCX 생성 실패 (node exitcode={proc.returncode}): {err_detail}")
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "DOCX 생성 타임아웃 (60s). Node.js 환경을 확인하세요.")
    finally:
        import os as _os_dx
        try:
            _os_dx.unlink(tmp_json)
        except Exception:
            pass

    if not docx_path.is_file():
        raise HTTPException(500, "DOCX 파일이 생성되지 않았습니다.")

    type_labels = {"p1": "시장조사", "p2": "가격전략", "p3": "바이어발굴", "final": "최종보고서"}
    dl_name = f"인도네시아_{type_labels.get(report_type, report_type)}_{_safe_prod}_{_ts_dx}.docx"

    return FileResponse(
        str(docx_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=dl_name,
        content_disposition_type="attachment",
    )


# ── Indonesia PDF 보고서 생성 ─────────────────────────────────────────────────

@app.get("/api/report/pdf/generate")
async def generate_pdf_report(
    report_type: str = "final",  # p1 | p2 | p3 | final
    product_key: str = "",
) -> Any:
    """analysis/id_report_generator.py를 호출해 인도네시아 PDF 보고서를 생성하고 반환.

    DOCX 엔드포인트(/api/report/docx/generate)와 동일한 데이터 수집 로직 사용.
    원화(KRW) + IDR + USD 3중 통화 표기 포함.
    """
    import re as _re_pdf
    from datetime import datetime, timezone as _tz_pdf

    # ── 데이터 수집 (DOCX 엔드포인트와 동일) ──────────────────────────────────
    p1_result = None
    for key, task in _pipeline_tasks.items():
        if task.get("result"):
            p1_result = task["result"]
            if not product_key:
                product_key = key
            break
    if p1_result is None and _custom_task.get("result"):
        p1_result = _custom_task["result"]

    p2_extracted  = _p2_ai_task.get("extracted")    if _p2_ai_task else None
    p2_analysis   = _p2_ai_task.get("analysis")     if _p2_ai_task else None
    p2_rates      = _p2_ai_task.get("exchange_rates") if _p2_ai_task else None
    p3_buyers     = _buyer_task.get("buyers", [])   if _buyer_task else []

    prod_label = _PROD_LABELS.get(product_key, p1_result.get("trade_name", "미상") if p1_result else "미상")
    inn_label  = (p1_result.get("inn", "") if p1_result else
                  (p2_extracted.get("product_name", "") if p2_extracted else ""))
    today_str  = datetime.now(_tz_pdf.utc).strftime("%Y년 %m월 %d일")

    _hs_code = ""
    if p1_result:
        _hs_code = p1_result.get("hs_code", "")
    if not _hs_code and product_key:
        from analysis.id_export_analyzer import _get_product_meta as _get_pm_pdf
        for _pm in _get_pm_pdf():
            if _pm.get("product_id") == product_key:
                _hs_code = _pm.get("hs_code", "")
                break

    data_json: dict[str, Any] = {
        "meta": {
            "country":      "인도네시아",
            "company":      "한국유나이티드제약(주)",
            "date":         today_str,
            "product_name": prod_label,
            "inn":          inn_label,
            "product_key":  product_key,
            "hs_code":      _hs_code,
        },
    }

    from utils.id_macro import get_id_macro as _get_macro_pdf
    _macro_map_pdf = {m["label"]: m["value"] for m in _get_macro_pdf()}

    if p1_result:
        _ref_price = (
            p1_result.get("ref_price_text") or
            p1_result.get("price_positioning_pbs") or
            (p2_extracted.get("ref_price_text") if p2_extracted else "") or ""
        )
        _entry = p1_result.get("entry_pathway") or p1_result.get("basis_procurement") or ""
        _raw_sources = p1_result.get("sources", [])
        _sources_list: list[str] = []
        for s in _raw_sources:
            if isinstance(s, dict):
                _sources_list.append(f"{s.get('name','')}{' — '+s.get('description','') if s.get('description') else ''}")
            elif s:
                _sources_list.append(str(s))
        _papers = p1_result.get("references") or p1_result.get("papers", [])

        data_json["p1"] = {
            "product_name":         p1_result.get("trade_name", prod_label),
            "inn":                  p1_result.get("inn", inn_label),
            "hs_code":              p1_result.get("hs_code", _hs_code),
            "verdict":              p1_result.get("verdict", "미상"),
            "verdict_label":        {"적합": "수출 적합", "조건부": "조건부 적합", "부적합": "수출 부적합"}.get(
                                        p1_result.get("verdict", ""), p1_result.get("verdict", "미분석")),
            "summary":              p1_result.get("summary") or p1_result.get("rationale", ""),
            "population":           p1_result.get("population") or _macro_map_pdf.get("인구", "2억 8,100만 명"),
            "gdp_per_capita":       p1_result.get("gdp_per_capita") or _macro_map_pdf.get("1인당 GDP", "USD 4,941"),
            "pharma_market":        p1_result.get("pharma_market") or _macro_map_pdf.get("의약품 시장 규모", "USD 87억"),
            "health_spend":         p1_result.get("health_spend", "GDP 대비 약 3.2% (WHO 2023)"),
            "import_dep":           p1_result.get("import_dep") or _macro_map_pdf.get("의약품 수입 의존도", "약 90%"),
            "disease_prevalence":   p1_result.get("disease_prevalence", ""),
            "related_market":       p1_result.get("related_market", ""),
            "basis_market_medical": p1_result.get("basis_market_medical", ""),
            "bpom_reg":             p1_result.get("bpom_reg", "") or p1_result.get("basis_regulatory", ""),
            "entry_pathway":        _entry,
            "basis_trade":          p1_result.get("basis_trade") or p1_result.get("basis_distribution", ""),
            "ref_price_text":       p1_result.get("ref_price_text", ""),
            "price_positioning_pbs": p1_result.get("price_positioning_pbs") or _ref_price,
            "ekatalog_price_hint":  p1_result.get("ekatalog_price_hint", ""),
            "risks_conditions":     p1_result.get("risks_conditions", ""),
            "papers":               _papers,
            "sources":              _sources_list,
        }
    else:
        data_json["p1"] = None

    if p2_analysis:
        data_json["p2"] = {
            "extracted":      p2_extracted or {},
            "analysis":       p2_analysis,
            "exchange_rates": p2_rates or {"usd_idr": 16200, "idr_krw": 0.082, "usd_krw": 1399},
        }
    else:
        data_json["p2"] = None

    if p3_buyers:
        data_json["p3"] = {"buyers": p3_buyers}
    else:
        data_json["p3"] = None

    # ── 타입 검증 ────────────────────────────────────────────────────────────
    if report_type not in ("p1", "p2", "p3", "final"):
        raise HTTPException(400, f"report_type must be p1|p2|p3|final, got: {report_type}")

    needed = {"p1": p1_result, "p2": p2_analysis, "p3": p3_buyers or None}
    if report_type == "final":
        missing = [k for k, v in needed.items() if not v]
        if missing:
            raise HTTPException(400, f"최종 보고서 생성에 필요한 데이터가 없습니다: {', '.join(missing).upper()}. 각 분석을 먼저 실행하세요.")
    elif report_type == "p1" and not p1_result:
        raise HTTPException(400, "P1(시장조사) 분석이 완료되지 않았습니다.")
    elif report_type == "p2" and not p2_analysis:
        raise HTTPException(400, "P2(가격전략) 분석이 완료되지 않았습니다.")
    elif report_type == "p3" and not p3_buyers:
        raise HTTPException(400, "P3(바이어) 분석이 완료되지 않았습니다.")

    # ── PDF 생성 ────────────────────────────────────────────────────────────
    _ts_pdf = datetime.now(_tz_pdf.utc).strftime("%Y%m%d_%H%M%S")
    _safe_prod_pdf = _re_pdf.sub(r"[^\w가-힣]", "_", prod_label)[:20] or "product"
    pdf_name   = f"ID_{report_type}_{_safe_prod_pdf}_{_ts_pdf}.pdf"
    pdf_path   = ROOT / "reports" / pdf_name
    (ROOT / "reports").mkdir(parents=True, exist_ok=True)

    from analysis.id_report_generator import generate as _gen_pdf
    await asyncio.to_thread(_gen_pdf, data_json, pdf_path, report_type)

    if not pdf_path.is_file():
        raise HTTPException(500, "PDF 파일이 생성되지 않았습니다.")

    type_labels_pdf = {"p1": "시장조사", "p2": "가격전략", "p3": "바이어발굴", "final": "최종보고서"}
    dl_name_pdf = f"인도네시아_{type_labels_pdf.get(report_type, report_type)}_{_safe_prod_pdf}_{_ts_pdf}.pdf"

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=dl_name_pdf,
        content_disposition_type="attachment",
    )


# ── 2공정 가격 전략 PDF ───────────────────────────────────────────────────────

class P2ReportBody(BaseModel):
    product_name:  str   = ""
    verdict:       str   = ""
    seg_label:     str   = ""
    base_price:    float | None = None
    formula_str:   str   = ""
    mode_label:    str   = ""
    scenarios:     list  = []
    ai_rationale:  list  = []


@app.post("/api/p2/report")
async def generate_p2_report(body: P2ReportBody) -> JSONResponse:
    """2공정 수출 가격 전략 PDF 생성."""
    import re
    from datetime import datetime, timezone as _tz_p2

    _ts = datetime.now(_tz_p2.utc).strftime("%Y%m%d_%H%M%S")
    _reports_dir = ROOT / "reports"
    _reports_dir.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r"[^\w가-힣]", "_", body.product_name)[:30] or "product"
    pdf_name  = f"sg_p2_{safe_name}_{_ts}.pdf"
    pdf_path  = _reports_dir / pdf_name

    p2_data = {
        "product_name":  body.product_name,
        "verdict":       body.verdict,
        "seg_label":     body.seg_label,
        "base_price":    body.base_price,
        "formula_str":   body.formula_str,
        "mode_label":    body.mode_label,
        "scenarios":     body.scenarios,
        "ai_rationale":  body.ai_rationale,
    }

    from report_generator import render_p2_pdf
    await asyncio.to_thread(render_p2_pdf, p2_data, pdf_path)

    return JSONResponse({"ok": True, "pdf": pdf_name})


# ── 2공정 AI 파이프라인 (PDF → Haiku 가격 추출 → 계산 → Haiku 분석 → PDF) ────────

# ── P2 시스템 프롬프트 ─────────────────────────────────────────────────────────
_ID_P2_SYSTEM_PROMPT = (
    "당신은 한국유나이티드제약(주)의 인도네시아 수출 전략 시니어 애널리스트입니다. "
    "주어진 품목의 (1) P1 시장조사 보고서 추출 데이터, (2) 실시간 환율, "
    "(3) 공공·민간 채널 FOB 역산 구조를 종합해 "
    "'수출가격 전략 보고서'에 들어갈 한국어 보고서체 JSON 블록을 작성합니다.\n\n"

    "【데이터 원칙 — 최우선】\n"
    "- 입력 추출 데이터(extracted)에 없는 수치·업체명·규제 사실은 절대 창작하지 않습니다.\n"
    "- 참조가·FOB 역산값·환율은 입력 JSON에 있는 값만 사용합니다.\n"
    "- 인도네시아는 루피아(IDR)를 공용 통화로 사용합니다. "
    "모든 현지 가격은 IDR 기준으로 서술하고 USD·KRW 환산은 입력 환율로 계산해 병기합니다.\n"
    "- 데이터가 없으면 '미확보(e-Katalog/BPOM 현지 추가 조사 필요)'로 명시합니다.\n\n"

    "【인도네시아 특화 약어 — 최초 노출 시 괄호 풀어쓰기】\n"
    "- BPOM (Badan Pengawas Obat dan Makanan · 인도네시아 식약처)\n"
    "- JKN (Jaminan Kesehatan Nasional · 국가건강보험), "
    "BPJS-Kesehatan (JKN 운영 기관)\n"
    "- FORNAS (Formularium Nasional · 국가처방집): 등재 = JKN 급여 자동 인정\n"
    "- e-Katalog/LKPP: 공공병원 의약품 조달 플랫폼, HET(최고 소매가) 설정\n"
    "- PBF (Pedagang Besar Farmasi · 의약품 도매업체): 현지 유통 필수 경유\n"
    "- PPN (Pajak Pertambahan Nilai · 부가가치세): 의약품 11% 고정\n\n"

    "【FOB 역산 구조 참고】\n"
    "공공(e-Katalog·BPJS): FOB = 조달가 × (1-관세) × (1-PBF마진) × (1-병원마진) × (1-에이전트) × (1-운임)\n"
    "민간(약국·병원·Halodoc/K24): FOB = HET ÷ (1+PPN) ÷ (1+소매마진) ÷ (1+유통마진) ÷ (1+관세) × (1-운임)\n\n"

    "【출력 JSON 스키마 — 모든 필드 필수】\n"
    "{\n"
    '  "rationale": "이 제품 가격 전략 수립 근거 2~3문장 — 시장가 수준·경쟁 강도 요약",\n'
    '  "recommendation": "공공/민간/혼합 채널 최적 전략 권고 2~3문장",\n'
    '  "public_market_strategy": "공공 채널 전략 — FORNAS 등재·e-Katalog 입찰가 포지셔닝·PBF 선정 방향 2~3문장",\n'
    '  "private_market_strategy": "민간 채널 전략 — 디지털 약국(Halodoc·K24)·민간병원 납품·브랜드 포지셔닝 2~3문장",\n'
    '  "scenarios": [공공 채널 3개 시나리오 — PDF 생성기 호환용 최상위 복사본],\n'
    '  "public": {\n'
    '    "market_note": "공공 조달 특이사항 1문장 (HET 제한·FORNAS 등재 여부 등)",\n'
    '    "market_strategy": "public_market_strategy와 동일",\n'
    '    "scenarios": [\n'
    '      {\n'
    '        "name": "저가 진입",\n'
    '        "price_idr": 숫자,\n'
    '        "fob_result_idr": 숫자,\n'
    '        "reason": "PBF 마진 언급 포함 포지셔닝 근거 1~2문장",\n'
    '        "fob_factors": [\n'
    '          {"name": "수입관세",    "type": "pct_deduct", "value": 숫자, "rationale": "인도네시아 의약품 관세"},\n'
    '          {"name": "PBF 유통마진","type": "pct_deduct", "value": 숫자, "rationale": "공공 입찰 PBF 마진"},\n'
    '          {"name": "병원·BPJS마진","type":"pct_deduct","value": 숫자, "rationale": "공공병원 마진"},\n'
    '          {"name": "에이전트",    "type": "pct_deduct", "value": 숫자, "rationale": "현지 에이전트 수수료"},\n'
    '          {"name": "운임·보험",   "type": "pct_deduct", "value": 숫자, "rationale": "CIF→FOB 운임 차감"}\n'
    '        ]\n'
    '      },\n'
    '      {"name": "기준",    "price_idr": 숫자, "fob_result_idr": 숫자, "reason": "...", "fob_factors": [...]},\n'
    '      {"name": "프리미엄","price_idr": 숫자, "fob_result_idr": 숫자, "reason": "...", "fob_factors": [...]}\n'
    '    ]\n'
    '  },\n'
    '  "private": {\n'
    '    "market_note": "민간 채널 특이사항 1문장 (PPN·Halodoc/K24 특성 등)",\n'
    '    "market_strategy": "private_market_strategy와 동일",\n'
    '    "scenarios": [\n'
    '      {\n'
    '        "name": "저가 진입",\n'
    '        "price_idr": 숫자,\n'
    '        "fob_result_idr": 숫자,\n'
    '        "reason": "PBF 마진 언급 포함 포지셔닝 근거 1~2문장",\n'
    '        "fob_factors": [\n'
    '          {"name": "수입관세",   "type": "pct_deduct", "value": 숫자, "rationale": "인도네시아 의약품 관세"},\n'
    '          {"name": "유통사마진", "type": "pct_deduct", "value": 숫자, "rationale": "민간 도매 PBF 마진"},\n'
    '          {"name": "소매마진",   "type": "pct_deduct", "value": 숫자, "rationale": "약국·병원 소매 마진"},\n'
    '          {"name": "PPN 부가세", "type": "pct_deduct", "value": 11,   "rationale": "인도네시아 부가세 고정 11%"},\n'
    '          {"name": "에이전트",   "type": "pct_deduct", "value": 숫자, "rationale": "현지 에이전트 수수료"},\n'
    '          {"name": "운임·보험",  "type": "pct_deduct", "value": 숫자, "rationale": "CIF→FOB 운임 차감"}\n'
    '        ]\n'
    '      },\n'
    '      {"name": "기준",    "price_idr": 숫자, "fob_result_idr": 숫자, "reason": "...", "fob_factors": [...]},\n'
    '      {"name": "프리미엄","price_idr": 숫자, "fob_result_idr": 숫자, "reason": "...", "fob_factors": [...]}\n'
    '    ]\n'
    '  }\n'
    "}\n\n"

    "【어투 및 품질 규칙 — 절대 준수】\n"
    "- 한국어 존댓말('-합니다', '-습니다')로 작성합니다.\n"
    "- 마크다운 금지: **, #, -, 백틱, [링크]() 전부 금지.\n"
    "- 이모지·특수 기호 장식 금지.\n"
    "- 각 시나리오 reason 문장에 PBF(유통사) 마진이 FOB 산정에 미친 영향을 1회 이상 포함합니다.\n"
    "- 추상적 권고 문구 단독 금지 — price_idr·fob_result_idr 수치를 반드시 인용합니다.\n"
    "- JSON 객체 하나만 출력합니다. {{ 로 시작, }} 로 끝, 코드블록·서두 없이 출력합니다."
)


def _p2_extract_json(raw: str) -> dict:
    """P2 AI 응답에서 JSON 객체를 강건하게 추출합니다."""
    import json as _json, re as _re

    # 전략 1: ```json 코드블록
    m = _re.search(r"```json\s*(\{.*?\})\s*```", raw, _re.S)
    if m:
        try:
            return _json.loads(m.group(1))
        except Exception:
            pass

    # 전략 2: 중첩 대응 중괄호 범위
    start = raw.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(raw[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return _json.loads(raw[start: i + 1])
                    except Exception:
                        break

    # 전략 3: raw 전체
    import json as _j
    return _j.loads(raw.strip())


_p2_ai_task: dict[str, Any] = {}


async def _run_p2_ai_pipeline(report_path: str, market: str) -> None:
    global _p2_ai_task
    try:
        import json
        import os
        import re

        import anthropic

        api_key = (
            os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY", "")
        ).strip()
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY 미설정 — 환경변수를 확인하세요.")

        # ── Step 1: PDF 텍스트 추출 ────────────────────────────────────────────
        _p2_ai_task.update({"step": "extract", "step_label": "PDF 텍스트 추출 중…"})
        await _emit({"phase": "p2_pipeline", "message": "PDF 텍스트 추출 시작", "level": "info"})

        pdf_text = ""
        try:
            from pypdf import PdfReader  # type: ignore[import]
            reader = PdfReader(report_path)
            for page in reader.pages:
                pdf_text += (page.extract_text() or "") + "\n"
        except Exception as exc_pdf:
            await _emit({"phase": "p2_pipeline", "message": f"PDF 추출 경고: {exc_pdf}", "level": "warn"})

        if not pdf_text.strip():
            raise ValueError("PDF에서 텍스트를 추출할 수 없습니다. 스캔 이미지 PDF이거나 암호화된 파일일 수 있습니다.")

        await _emit({"phase": "p2_pipeline", "message": f"텍스트 {len(pdf_text)}자 추출 완료", "level": "success"})

        # ── Step 2: Claude Haiku — 가격 정보 추출 ──────────────────────────────
        _p2_ai_task.update({"step": "ai_extract", "step_label": "AI 가격 정보 추출 중…"})
        await _emit({"phase": "p2_pipeline", "message": "Claude Haiku — 가격 정보 추출", "level": "info"})

        client = anthropic.Anthropic(api_key=api_key)

        extract_prompt = f"""다음 의약품 수출 분석 보고서에서 가격 관련 정보를 추출하세요.

보고서 내용:
{pdf_text[:7000]}

아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{{
  "product_name": "제품명 (없으면 '미상')",
  "inn": "성분명·규격 (없으면 빈 문자열)",
  "dosage_form": "제형 (없으면 빈 문자열)",
  "pack_size": 숫자 또는 null,
  "ref_price_idr": 숫자 또는 null,
  "ref_price_usd": 숫자 또는 null,
  "ref_price_text": "원문 가격 텍스트 (없으면 빈 문자열)",
  "het_idr": 숫자 또는 null,
  "ekatalog_price_idr": 숫자 또는 null,
  "competitor_prices": [
    {{"name": "경쟁사·제품명", "price_idr": 숫자 또는 null, "price_usd": 숫자 또는 null, "channel": "public|private|unknown"}}
  ],
  "market_context": "시장 맥락 요약 (1~2문장, 없으면 빈 문자열)",
  "hs_code": "HS 코드 (없으면 빈 문자열)",
  "verdict": "수출 적합성 판정 (적합/조건부/부적합/미상)",
  "fornas_registered": true 또는 false 또는 null,
  "bpom_status": "등록완료|등록필요|심사중|미상"
}}

가격 추출 규칙 (반드시 준수):
- 'IDR X,XXX', 'Rp X,XXX', 'IDR X.XXX' 형식의 루피아 금액을 ref_price_idr에 넣으세요.
- 'e-Katalog 조달가', 'LKPP 조달가' 관련 IDR 숫자는 ekatalog_price_idr에 넣으세요.
- 'HET', '최고 판매가', 'HNA' 관련 IDR 숫자는 het_idr에 넣으세요.
- 'USD', '$' 금액이 있으면 ref_price_usd에 넣고, ref_price_idr는 null로 유지하세요.
- 경쟁사 가격의 channel은 'public'(e-Katalog/BPJS) 또는 'private'(약국/병원)으로 구분하세요.
- FORNAS 등재 여부가 '등재', '포함', 'FORNAS' 키워드와 함께 나오면 fornas_registered를 true로 설정하세요.
- '미등재', 'FORNAS 없음' 등이 나오면 fornas_registered를 false로 설정하세요.
- SGD, AUD 등 다른 통화는 ref_price_text에 원문을 기록하고 ref_price_idr와 ref_price_usd는 null로 두세요."""

        extract_resp = await asyncio.to_thread(
            lambda: client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                messages=[{"role": "user", "content": extract_prompt}],
            )
        )

        extracted: dict[str, Any] = {}
        try:
            raw_extract = extract_resp.content[0].text
            m_json = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw_extract, re.S)
            if m_json:
                extracted = json.loads(m_json.group(0))
        except Exception:
            extracted = {
                "product_name": "미상",
                "ref_price_sgd": None,
                "ref_price_text": "",
                "market_context": "",
                "verdict": "미상",
            }

        _p2_ai_task["extracted"] = extracted
        _ref_disp = (
            f"IDR {int(extracted['ref_price_idr']):,}" if extracted.get("ref_price_idr")
            else f"USD {extracted['ref_price_usd']}" if extracted.get("ref_price_usd")
            else extracted.get("ref_price_text") or "미확인"
        )
        await _emit({
            "phase": "p2_pipeline",
            "message": f"가격 추출 완료 — 참조가: {_ref_disp}",
            "level": "success",
        })

        # ── Step 3: 실시간 환율 (yfinance) ────────────────────────────────────
        _p2_ai_task.update({"step": "exchange", "step_label": "실시간 환율 조회 중…"})
        await _emit({"phase": "p2_pipeline", "message": "yfinance 환율 조회", "level": "info"})

        exchange_rates: dict[str, Any] = {
            "usd_idr": 16200.0,
            "idr_krw": 0.0864,
            "usd_krw": 1399.0,
            "source": "폴백값 (Yahoo Finance 연결 실패)",
        }
        try:
            import yfinance as yf  # type: ignore[import]

            def _fetch_rates() -> dict[str, Any]:
                usd_idr = round(float(yf.Ticker("USDIDR=X").fast_info.last_price), 2)
                usd_krw = round(float(yf.Ticker("USDKRW=X").fast_info.last_price), 2)
                idr_krw = round(usd_krw / usd_idr, 6) if usd_idr else 0.0864
                return {
                    "usd_idr": usd_idr,
                    "idr_krw": idr_krw,
                    "usd_krw": usd_krw,
                    "source": "Yahoo Finance (실시간)",
                }

            exchange_rates = await asyncio.to_thread(_fetch_rates)
        except Exception as exc_fx:
            await _emit({"phase": "p2_pipeline", "message": f"환율 폴백: {exc_fx}", "level": "warn"})

        _p2_ai_task["exchange_rates"] = exchange_rates
        await _emit({
            "phase": "p2_pipeline",
            "message": f"환율 — 1 USD = {exchange_rates['usd_idr']:,.0f} IDR / 1 IDR = {exchange_rates['idr_krw']:.5f} KRW",
            "level": "success",
        })

        # ── Step 4: Claude — 공공·민간 이중 시장 FOB 가격 전략 분석 ─────────────
        _p2_ai_task.update({"step": "ai_analysis", "step_label": "AI 공공·민간 분석 중…"})
        await _emit({"phase": "p2_pipeline", "message": "Claude — 공공·민간 이중 시장 분석", "level": "info"})

        # ── 참조가 결정 (IDR 우선, USD·환산 순) ────────────────────────────────
        usd_idr      = exchange_rates["usd_idr"]
        idr_krw      = exchange_rates["idr_krw"]
        verdict_src  = extracted.get("verdict", "미상")
        competitor_json = json.dumps(extracted.get("competitor_prices", []), ensure_ascii=False)

        _ref_idr = extracted.get("ref_price_idr")
        _ref_usd = extracted.get("ref_price_usd")
        if _ref_idr:
            ref_price_idr = int(_ref_idr)
            ref_display   = f"IDR {ref_price_idr:,} (≈ USD {ref_price_idr / usd_idr:.2f})"
        elif _ref_usd:
            ref_price_idr = int(float(_ref_usd) * usd_idr)
            ref_display   = f"USD {_ref_usd} → 환산 IDR {ref_price_idr:,}"
        else:
            ref_price_idr = 0
            ref_display   = extracted.get("ref_price_text") or "미확인"

        _het_idr     = extracted.get("het_idr")
        _ek_idr      = extracted.get("ekatalog_price_idr")
        _fornas_txt  = (
            "FORNAS 등재" if extracted.get("fornas_registered") is True
            else "FORNAS 미등재" if extracted.get("fornas_registered") is False
            else "FORNAS 등재 여부 미확인"
        )
        _bpom_txt    = extracted.get("bpom_status", "미상")

        analysis_prompt = f"""인도네시아 수출 가격 전략(FOB 역산)을 공공·민간 이중 시장으로 수립해주세요.

## 추출된 보고서 정보
- 제품명: {extracted.get('product_name', '미상')}
- INN·성분: {extracted.get('inn', '미상')}
- 제형: {extracted.get('dosage_form', '미상')}
- 수출 적합성 판정: {verdict_src}
- 참조가: {ref_display}
- e-Katalog 조달가: {f"IDR {int(_ek_idr):,}" if _ek_idr else "미확인"}
- HET(최고 판매가): {f"IDR {int(_het_idr):,}" if _het_idr else "미확인"}
- FORNAS 상태: {_fornas_txt}
- BPOM 등록: {_bpom_txt}
- HS 코드: {extracted.get('hs_code', '미상')}
- 현재 환율: 1 USD = {usd_idr:,.0f} IDR / 1 IDR ≈ {idr_krw:.5f} KRW
- 경쟁사 가격: {competitor_json}
- 시장 맥락: {extracted.get('market_context', '정보 없음')}

## 인도네시아 FOB 역산 구조 (참고)
공공(e-Katalog·BPJS): FOB = 조달가 × (1-관세) × (1-PBF마진) × (1-병원마진) × (1-에이전트) × (1-운임)
민간(약국·병원·Halodoc/K24): FOB = HET ÷ (1+PPN) ÷ (1+소매마진) ÷ (1+유통마진) ÷ (1+관세) × (1-운임)

공공 시장 적정 비율 범위:
- 수입관세: 의약품 5~10%  · PBF 유통마진: 15~22%  · 병원·BPJS마진: 10~18%
- 에이전트: 3~5%  · 운임·보험: 3~6%

민간 시장 적정 비율 범위:
- 수입관세: 5~10%  · PBF 유통마진: 20~28%  · 소매마진: 30~40%
- PPN: 11%(고정)  · 에이전트: 3~8%  · 운임·보험: 3~6%

## 작성 지시
시스템 프롬프트의 JSON 스키마를 정확히 따라 공공·민간 각 3개 시나리오를 산정하세요.
- 참조가가 IDR {ref_price_idr:,}이므로 이를 기준으로 시나리오를 설계하세요.
- 참조가가 0이면 경쟁사 가격·제품 특성·HS코드 기반으로 합리적 IDR 추정가를 산정하세요.
- fob_factors 각 항목에 이 제품·시장에 최적화된 실제 비율을 제시하세요.
- scenarios 최상위 키에 public.scenarios를 복사해 PDF 생성기와 호환되게 해주세요.
- public_market_strategy / private_market_strategy 도 최상위에 포함하세요.
- recommendation 필드로 최종 채널 전략 권고를 추가하세요.
- JSON 하나만 반환, {{ 로 시작 }} 로 끝, 코드블록 없이 출력합니다."""

        analysis_resp = await asyncio.to_thread(
            lambda: client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=5000,
                system=_ID_P2_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": analysis_prompt}],
            )
        )

        analysis: dict[str, Any] = {}
        try:
            raw_analysis = analysis_resp.content[0].text
            analysis = _p2_extract_json(raw_analysis)
        except Exception:
            # ── 폴백: 인도네시아 표준 FOB 구조로 두 시장 공통 생성 ─────────────
            base_pub  = ref_price_idr if ref_price_idr else 50_000
            base_priv = int(base_pub * 1.4)   # 민간은 HET 기준 — 공공 조달가보다 높음

            def _factors_pub(rel: float) -> list:
                return [
                    {"name": "수입관세",     "type": "pct_deduct", "value": 7.5,          "rationale": "인도네시아 의약품 평균 관세 (HS 3004.90)"},
                    {"name": "PBF 유통마진", "type": "pct_deduct", "value": round(18 * rel, 1), "rationale": "공공 입찰 PBF 유통 마진"},
                    {"name": "병원·BPJS마진","type": "pct_deduct", "value": 15.0,          "rationale": "공공병원 약품 마진"},
                    {"name": "에이전트",     "type": "pct_deduct", "value": round(3  * rel, 1), "rationale": "현지 에이전트 수수료"},
                    {"name": "운임·보험",    "type": "pct_deduct", "value": 4.0,           "rationale": "CIF→FOB 운임·보험 차감"},
                ]

            def _factors_pri(rel: float) -> list:
                return [
                    {"name": "수입관세",    "type": "pct_deduct", "value": 7.5,           "rationale": "인도네시아 의약품 평균 관세"},
                    {"name": "유통사마진",  "type": "pct_deduct", "value": round(23 * rel, 1), "rationale": "민간 도매 PBF 유통 마진"},
                    {"name": "소매마진",    "type": "pct_deduct", "value": 35.0,           "rationale": "약국·민간병원 소매 마진"},
                    {"name": "PPN 부가세",  "type": "pct_deduct", "value": 11.0,           "rationale": "인도네시아 부가세 고정 11%"},
                    {"name": "에이전트",    "type": "pct_deduct", "value": round(4  * rel, 1), "rationale": "현지 에이전트 수수료"},
                    {"name": "운임·보험",   "type": "pct_deduct", "value": 4.0,            "rationale": "CIF→FOB 운임·보험 차감"},
                ]

            def _calc_fob(price: int, factors: list) -> int:
                p = float(price)
                for f in factors:
                    p *= (1.0 - f["value"] / 100.0)
                return max(1, int(p))

            def _mk_sc(base: int, fn, mults=(0.88, 1.0, 1.20)) -> list:
                names   = ["저가 진입", "기준", "프리미엄"]
                reasons = [
                    "e-Katalog 최저가 공략 — PBF 유통 마진 조정으로 FOB 확보",
                    "FORNAS 기준가 대비 경쟁력 있는 포지셔닝 — PBF 마진 표준 적용",
                    "개량신약 특허 프리미엄 — PBF 마진 최소화로 FOB 극대화",
                ]
                return [
                    {
                        "name":          names[i],
                        "price_idr":     int(base * mults[i]),
                        "fob_result_idr": _calc_fob(int(base * mults[i]), fn(mults[i])),
                        "reason":        reasons[i],
                        "fob_factors":   fn(mults[i]),
                    }
                    for i in range(3)
                ]

            pub_sc  = _mk_sc(base_pub,  _factors_pub)
            priv_sc = _mk_sc(base_priv, _factors_pri)

            analysis = {
                "rationale": (
                    "AI 응답 파싱 오류로 인도네시아 표준 FOB 역산 구조 폴백 적용. "
                    f"참조가 IDR {base_pub:,} 기준 공공·민간 이중 시장 시나리오를 산정합니다."
                ),
                "recommendation": (
                    "공공 채널(e-Katalog·BPJS-Kesehatan) 우선 진입 후 민간 채널 확장을 권장합니다. "
                    "FORNAS 등재 선행이 공공 조달 접근의 핵심 조건입니다."
                ),
                "public_market_strategy": (
                    "FORNAS 등재 후 e-Katalog 기준 시나리오(IDR "
                    f"{pub_sc[1]['price_idr']:,})로 입찰 참여를 권장합니다. "
                    "현지 PBF 파트너 선정 시 공공 조달 이력 보유 여부를 필수 확인합니다."
                ),
                "private_market_strategy": (
                    "Halodoc·K24Klik 디지털 약국 채널과 민간병원 납품을 병행합니다. "
                    f"민간 기준가 IDR {priv_sc[1]['price_idr']:,} 수준에서 브랜드 포지셔닝을 권장합니다."
                ),
                "scenarios": pub_sc,   # PDF 생성기 호환 최상위 복사본
                "public": {
                    "market_note": "e-Katalog/BPJS-Kesehatan 공공 조달 채널 기준 (폴백 산정)",
                    "market_strategy": (
                        "FORNAS 등재 후 e-Katalog 입찰가로 공공병원 납품을 진행합니다."
                    ),
                    "scenarios": pub_sc,
                },
                "private": {
                    "market_note": "Halodoc·K24·민간병원 채널 기준 — PPN 11% 포함 (폴백 산정)",
                    "market_strategy": (
                        "디지털 약국 채널과 민간병원 대상 브랜드 마케팅을 병행합니다."
                    ),
                    "scenarios": priv_sc,
                },
            }

        # ── PDF 생성기 호환: 최상위 scenarios / market_strategy 누락 시 자동 보완 ──
        if not analysis.get("scenarios") and analysis.get("public", {}).get("scenarios"):
            analysis["scenarios"] = analysis["public"]["scenarios"]
        if not analysis.get("public_market_strategy") and analysis.get("public", {}).get("market_strategy"):
            analysis["public_market_strategy"] = analysis["public"]["market_strategy"]
        if not analysis.get("private_market_strategy") and analysis.get("private", {}).get("market_strategy"):
            analysis["private_market_strategy"] = analysis["private"]["market_strategy"]

        _p2_ai_task["analysis"] = analysis
        await _emit({
            "phase": "p2_pipeline",
            "message": "공공·민간 이중 시장 분석 완료",
            "level": "success",
        })

        # ── Step 5: PDF 보고서 생성 ───────────────────────────────────────────
        _p2_ai_task.update({"step": "report", "step_label": "PDF 생성 중…"})
        await _emit({"phase": "p2_pipeline", "message": "2공정 PDF 보고서 생성", "level": "info"})

        from datetime import datetime, timezone as _tz_p2ai
        import re as _re2

        _ts_p2 = datetime.now(_tz_p2ai.utc).strftime("%Y%m%d_%H%M%S")
        _reports_dir_p2 = ROOT / "reports"
        _reports_dir_p2.mkdir(parents=True, exist_ok=True)

        _safe = _re2.sub(r"[^\w가-힣]", "_", extracted.get("product_name", "product"))[:30] or "product"
        _pdf_name_p2 = f"sg_p2_{_safe}_{_ts_p2}.pdf"
        _pdf_path_p2 = _reports_dir_p2 / _pdf_name_p2

        # AI 시나리오 필드명 정규화 (PDF generator는 label/price 사용)
        # 공공 시장 시나리오를 대표로 사용 (PDF 호환)
        pub_scenarios = (analysis.get("public") or {}).get("scenarios", [])
        norm_scenarios = []
        for sc in pub_scenarios:
            norm_scenarios.append({
                "label":   sc.get("name", ""),
                "price":   sc.get("fob_result_idr", sc.get("price_idr", 0)),
                "reason":  sc.get("reason", ""),
                "formula": f"IDR {sc.get('price_idr', 0):,} → FOB IDR {sc.get('fob_result_idr', 0):,}",
            })

        # 대표 최종 권고가: 공공 기준 시나리오(index 1) FOB값
        final_idr = pub_scenarios[1].get("fob_result_idr", 0) if len(pub_scenarios) > 1 else 0

        p2_data = {
            "product_name": extracted.get("product_name", "미상"),
            "verdict":      verdict_src,
            "seg_label":    "공공·민간 이중 시장 (인도네시아)",
            "base_price":   final_idr,
            "formula_str":  "",
            "mode_label":   "AI 분석 — 공공·민간 FOB 역산",
            "scenarios":    norm_scenarios,
            "ai_rationale": [analysis.get("rationale", "")],
        }

        from report_generator import render_p2_pdf
        await asyncio.to_thread(render_p2_pdf, p2_data, _pdf_path_p2)

        _p2_ai_task["pdf"] = _pdf_name_p2
        _p2_ai_task.update({"status": "done", "step": "done", "step_label": "완료"})
        await _emit({"phase": "p2_pipeline", "message": "P2 파이프라인 완료", "level": "success"})

    except Exception as exc:
        _p2_ai_task.update({"status": "error", "step": "error", "step_label": str(exc)[:300]})
        await _emit({"phase": "p2_pipeline", "message": f"P2 오류: {exc}", "level": "error"})


class UploadBody(BaseModel):
    filename: str
    content_b64: str  # base64 인코딩된 PDF 바이너리


@app.post("/api/p2/upload")
async def upload_p2_pdf(body: UploadBody) -> JSONResponse:
    """P2 파이프라인용 PDF 업로드 (base64 JSON — python-multipart 불필요)."""
    import base64
    import re as _re_up

    fname = body.filename or "upload.pdf"
    if not fname.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF 파일(.pdf)만 업로드 가능합니다.")

    try:
        content = base64.b64decode(body.content_b64)
    except Exception:
        raise HTTPException(400, "base64 디코딩 실패 — 올바른 PDF 파일인지 확인하세요.")

    safe_fname = _re_up.sub(r"[^\w가-힣\-\.]", "_", fname)[:80]
    _reports_dir = ROOT / "reports"
    _reports_dir.mkdir(parents=True, exist_ok=True)
    dest = _reports_dir / f"upload_{safe_fname}"
    dest.write_bytes(content)

    return JSONResponse({"ok": True, "filename": dest.name})


class P2PipelineBody(BaseModel):
    report_filename: str = ""  # reports/ 내 파일명 (비어 있으면 최신 1공정 PDF 사용)
    market: str = "public"     # "public" | "private"


@app.post("/api/p2/pipeline")
async def trigger_p2_pipeline(body: P2PipelineBody) -> JSONResponse:
    """2공정 AI 파이프라인 실행."""
    global _p2_ai_task
    if _p2_ai_task.get("status") == "running":
        raise HTTPException(409, "P2 파이프라인이 이미 실행 중입니다.")

    if body.report_filename:
        report_path = ROOT / "reports" / Path(body.report_filename).name
    else:
        report_path = _latest_report_pdf()

    if not report_path or not Path(report_path).is_file():
        raise HTTPException(404, f"보고서 파일을 찾을 수 없습니다: {body.report_filename or '(최신 PDF 없음)'}")

    _p2_ai_task = {
        "status":   "running",
        "step":     "extract",
        "step_label": "시작 중…",
        "extracted": None,
        "exchange_rates": None,
        "analysis": None,
        "pdf":      None,
    }
    asyncio.create_task(_run_p2_ai_pipeline(str(report_path), body.market))
    return JSONResponse({"ok": True})


@app.get("/api/p2/pipeline/status")
async def p2_pipeline_status_ai() -> JSONResponse:
    if not _p2_ai_task:
        return JSONResponse({"status": "idle"})
    return JSONResponse({
        "status":     _p2_ai_task.get("status", "idle"),
        "step":       _p2_ai_task.get("step", ""),
        "step_label": _p2_ai_task.get("step_label", ""),
        "has_result": _p2_ai_task.get("analysis") is not None,
        "has_pdf":    bool(_p2_ai_task.get("pdf")),
    })


@app.get("/api/p2/pipeline/result")
async def p2_pipeline_result_ai() -> JSONResponse:
    if not _p2_ai_task:
        raise HTTPException(404, "P2 파이프라인 미실행")
    return JSONResponse({
        "status":         _p2_ai_task.get("status"),
        "extracted":      _p2_ai_task.get("extracted"),
        "exchange_rates": _p2_ai_task.get("exchange_rates"),
        "analysis":       _p2_ai_task.get("analysis"),
        "pdf":            _p2_ai_task.get("pdf"),
    })


# ── products 조회 ─────────────────────────────────────────────────────────────

@app.get("/api/products")
async def products() -> list[dict[str, Any]]:
    from utils.db import fetch_kup_products
    return fetch_kup_products("ID")


# ── API 키 상태 (U1) ──────────────────────────────────────────────────────────

@app.get("/api/keys/status")
async def keys_status() -> dict[str, Any]:
    """Claude·Perplexity API 키 설정 여부 반환 (실제 키 값은 노출하지 않음)."""
    import os
    claude_key     = os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
    perplexity_key = os.environ.get("PERPLEXITY_API_KEY", "")
    return {
        "claude":     bool(claude_key.strip()),
        "perplexity": bool(perplexity_key.strip()),
    }


# ── 데이터 소스 상태 (U5·B1) ──────────────────────────────────────────────────

@app.get("/api/datasource/status")
async def datasource_status() -> JSONResponse:
    """Supabase 연결 상태, KUP 품목 수, HSA 컨텍스트 출처 반환."""
    try:
        from utils.db import get_client, fetch_kup_products
        kup_rows = fetch_kup_products("ID")
        kup_count = len(kup_rows)

        # HSA 컨텍스트 테이블 점검
        sb = get_client()
        ctx_count = 0
        context_source = "없음"
        try:
            ctx_rows = (
                sb.table("sg_product_context")
                .select("product_id", count="exact")
                .execute()
            )
            ctx_count = ctx_rows.count or 0
            context_source = f"sg_product_context {ctx_count}건" if ctx_count else "products 테이블 폴백"
        except Exception:
            context_source = "조회 실패"

        return JSONResponse({
            "supabase":       "ok",
            "kup_count":      kup_count,
            "context_ok":     ctx_count > 0,
            "context_source": context_source,
            "message":        f"KUP {kup_count}건 로드",
        })
    except Exception as exc:
        return JSONResponse({
            "supabase":       "error",
            "kup_count":      0,
            "context_ok":     False,
            "context_source": "연결 실패",
            "message":        str(exc)[:120],
        })


# ── 상태 / SSE 스트림 ─────────────────────────────────────────────────────────

@app.get("/api/status")
async def status() -> dict[str, Any]:
    lock = _state["lock"]
    assert lock is not None
    async with lock:
        n = len(_state["events"])
    return {"event_count": n}


@app.get("/api/health")
async def health() -> dict[str, Any]:
    """Render 헬스체크용 경량 엔드포인트."""
    return {"ok": True, "service": "id-analysis-dashboard"}


# ── 인도네시아 크롤러 API ──────────────────────────────────────────────────────

class CrawlBody(BaseModel):
    keyword: str
    sources: list[str] = ["bpom", "ekatalog", "halodoc"]
    max_results: int = 10


@app.post("/api/id/crawl")
async def id_crawl(body: CrawlBody) -> JSONResponse:
    """BPOM · e-Katalog · Halodoc 크롤러를 병렬 실행해 결과를 반환한다."""
    import sys
    sys.path.insert(0, str(ROOT))

    tasks: dict[str, Any] = {}

    async def _run_bpom():
        from utils.id_bpom_crawler import search_bpom
        return await search_bpom(body.keyword, max_results=body.max_results)

    async def _run_ekatalog():
        from utils.id_ekatalog_crawler import search_ekatalog
        return await search_ekatalog(body.keyword, max_results=body.max_results)

    async def _run_halodoc():
        from utils.id_halodoc_crawler import search_halodoc
        return await search_halodoc(body.keyword, max_results=body.max_results)

    src_map = {
        "bpom":     _run_bpom,
        "ekatalog": _run_ekatalog,
        "halodoc":  _run_halodoc,
    }
    coros = {s: src_map[s]() for s in body.sources if s in src_map}
    results = await asyncio.gather(*coros.values(), return_exceptions=True)

    output: dict[str, Any] = {}
    for key, res in zip(coros.keys(), results):
        if isinstance(res, Exception):
            output[key] = {"error": str(res)[:200]}
        else:
            output[key] = res

    return JSONResponse({"keyword": body.keyword, "results": output})


@app.get("/api/stream")
async def stream() -> StreamingResponse:
    last = 0

    async def gen() -> Any:
        nonlocal last
        while True:
            await asyncio.sleep(0.12)
            chunk: list[dict[str, Any]] = []
            lock = _state["lock"]
            assert lock is not None
            async with lock:
                while last < len(_state["events"]):
                    chunk.append(_state["events"][last])
                    last += 1
            for ev in chunk:
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ── 3공정: 바이어 발굴 파이프라인 ─────────────────────────────────────────────

_buyer_task: dict[str, Any] = {}

_PROD_LABELS: dict[str, str] = {
    "ID_sereterol_activair":      "Sereterol Activair (Fluticasone+Salmeterol)",
    "ID_omethyl_omega3_2g":       "Omethyl Cutielet (Omega-3 에틸에스테르 2g)",
    "ID_hydrine_hydroxyurea_500": "Hydrine (Hydroxyurea 500mg)",
    "ID_gadvoa_gadobutrol_604":   "Gadvoa Inj. (Gadobutrol)",
    "ID_rosumeg_combigel":        "Rosumeg Combigel (Rosuvastatin+Omega-3)",
    "ID_atmeg_combigel":          "Atmeg Combigel (Atorvastatin+Omega-3)",
    "ID_ciloduo_cilosta_rosuva":  "Ciloduo (Cilostazol+Rosuvastatin)",
    "ID_gastiin_cr_mosapride":    "Gastiin CR (Mosapride citrate 15mg)",
}


class BuyerRunBody(BaseModel):
    product_key:     str = "ID_sereterol_activair"
    active_criteria: list[str] | None = None
    target_country:  str = "Indonesia"
    target_region:   str = "Asia"


async def _run_buyer_pipeline(
    product_key: str,
    active_criteria: list[str] | None = None,
    target_country: str = "Indonesia",
    target_region: str = "Asia",
) -> None:
    global _buyer_task

    async def _log(msg: str, level: str = "info") -> None:
        await _emit({"phase": "buyer", "message": msg, "level": level})

    try:
        product_label = _PROD_LABELS.get(product_key, product_key)

        # ── Step 1: 1차 수집 (CPHI 크롤링 — 후보 최대 20개) ─────────────
        _buyer_task.update({"step": "crawl", "step_label": "CPHI 크롤링 중…"})
        await _log(f"바이어 발굴 시작 — 품목: {product_label} / 타깃: {target_country} ({target_region})")

        from utils.cphi_crawler import crawl as cphi_crawl
        companies = await cphi_crawl(
            product_key=product_key,
            candidate_pool=20,
            emit=_log,
        )
        _buyer_task["crawl_count"] = len(companies)
        await _log(f"1차 수집 완료 — {len(companies)}개 후보", "success")

        # ── Step 2: 심층조사 (CPHI 전체 텍스트 → Claude Haiku) ───────────
        _buyer_task.update({"step": "enrich", "step_label": "심층조사 중…"})
        await _log("심층조사 시작 (CPHI 페이지 텍스트 → Claude Haiku 파싱)")

        from utils.buyer_enricher import enrich_all
        enriched = await enrich_all(
            companies,
            product_label=product_label,
            target_country=target_country,
            target_region=target_region,
            emit=_log,
        )
        # 전체 후보 풀 저장 — 기준 변경 시 재선택에 사용
        _buyer_task["all_candidates"] = enriched
        await _log(f"심층조사 완료 — {len(enriched)}개", "success")

        # ── Step 3: 상위 10개 선택 ────────────────────────────────────────
        _buyer_task.update({"step": "rank", "step_label": "Top 10 선정 중…"})
        await _log("평가 기준 적용 → Top 10 선정")

        from analysis.buyer_scorer import rank_companies
        ranked = rank_companies(enriched, active_criteria=active_criteria, top_n=10)
        _buyer_task["buyers"] = ranked
        await _log(f"Top {len(ranked)}개 바이어 선정 완료", "success")

        # ── Step 4: PDF 보고서 생성 ───────────────────────────────────────
        _buyer_task.update({"step": "report", "step_label": "PDF 생성 중…"})
        await _log("바이어 보고서 PDF 생성 중…")

        from datetime import datetime, timezone as _tz_b
        from analysis.buyer_report_generator import build_buyer_pdf
        import re as _re_b

        _ts = datetime.now(_tz_b.utc).strftime("%Y%m%d_%H%M%S")
        _reports_dir = ROOT / "reports"
        _reports_dir.mkdir(parents=True, exist_ok=True)

        safe = _re_b.sub(r"[^\w가-힣]", "_", product_key)[:30]
        pdf_name = f"id_buyers_{safe}_{_ts}.pdf"
        pdf_path = _reports_dir / pdf_name

        await asyncio.to_thread(build_buyer_pdf, ranked, product_label, pdf_path)
        _buyer_task["pdf"] = pdf_name
        _buyer_task.update({"status": "done", "step": "done", "step_label": "완료"})
        await _log("바이어 발굴 파이프라인 완료", "success")

    except Exception as exc:
        _buyer_task.update({"status": "error", "step": "error", "step_label": str(exc)})
        await _emit({"phase": "buyer", "message": f"오류: {exc}", "level": "error"})


@app.post("/api/buyers/run")
async def trigger_buyers(body: BuyerRunBody | None = None) -> JSONResponse:
    global _buyer_task
    req = body if body is not None else BuyerRunBody()
    if _buyer_task.get("status") == "running":
        raise HTTPException(409, "바이어 발굴이 이미 실행 중입니다.")
    _buyer_task = {
        "status": "running", "step": "crawl", "step_label": "시작 중…",
        "crawl_count": 0, "all_candidates": [], "buyers": [], "pdf": None,
    }
    asyncio.create_task(_run_buyer_pipeline(
        req.product_key,
        req.active_criteria,
        req.target_country,
        req.target_region,
    ))
    return JSONResponse({"ok": True})


@app.get("/api/buyers/status")
async def buyer_status() -> JSONResponse:
    if not _buyer_task:
        return JSONResponse({"status": "idle"})
    return JSONResponse({
        "status":          _buyer_task.get("status", "idle"),
        "step":            _buyer_task.get("step", ""),
        "step_label":      _buyer_task.get("step_label", ""),
        "crawl_count":     _buyer_task.get("crawl_count", 0),
        "buyer_count":     len(_buyer_task.get("buyers", [])),
        "candidate_count": len(_buyer_task.get("all_candidates", [])),
        "has_pdf":         bool(_buyer_task.get("pdf")),
    })


@app.get("/api/buyers/result")
async def buyer_result() -> JSONResponse:
    if not _buyer_task:
        raise HTTPException(404, "바이어 발굴 미실행")
    return JSONResponse({
        "status":  _buyer_task.get("status"),
        "buyers":  _buyer_task.get("buyers", []),
        "pdf":     _buyer_task.get("pdf"),
    })


@app.post("/api/buyers/rerank")
async def buyer_rerank(body: dict = None) -> JSONResponse:
    """기준 변경 시 전체 후보 풀(20개)에서 재선택."""
    all_candidates = _buyer_task.get("all_candidates", [])
    if not all_candidates:
        raise HTTPException(404, "후보 풀 없음. 파이프라인을 먼저 실행하세요.")
    criteria = (body or {}).get("criteria")
    from analysis.buyer_scorer import rank_companies
    ranked = rank_companies(all_candidates, active_criteria=criteria, top_n=10)
    _buyer_task["buyers"] = ranked
    return JSONResponse({"buyers": ranked})


@app.get("/api/buyers/report/download")
async def buyer_report_download(name: str | None = None) -> Any:
    reports_dir = ROOT / "reports"
    if name:
        target = reports_dir / Path(name).name
        if target.is_file():
            return FileResponse(
                str(target), media_type="application/pdf",
                filename=target.name, content_disposition_type="attachment",
            )
    # 최신 buyers PDF
    pdfs = sorted(reports_dir.glob("id_buyers_*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not pdfs:
        raise HTTPException(404, "바이어 보고서 없음")
    return FileResponse(
        str(pdfs[0]), media_type="application/pdf",
        filename=pdfs[0].name, content_disposition_type="attachment",
    )


# ── 우루과이 거시지표 ──────────────────────────────────────────────────────────

@app.get("/api/uy/macro")
async def api_uy_macro() -> JSONResponse:
    from utils.uy_macro import get_uy_macro
    return JSONResponse(get_uy_macro())


# ── UYU/USD 환율 ──────────────────────────────────────────────────────────────

_uyu_exchange_cache: dict[str, Any] = {"data": None, "ts": 0.0}
_UYU_EXCHANGE_TTL = 300.0


@app.get("/api/exchange/uyu")
async def api_exchange_uyu() -> JSONResponse:
    import time as _time

    if _uyu_exchange_cache["data"] and _time.time() - _uyu_exchange_cache["ts"] < _UYU_EXCHANGE_TTL:
        return JSONResponse(_uyu_exchange_cache["data"])

    def _fetch_uyu() -> dict[str, Any]:
        import yfinance as yf  # type: ignore[import]
        uyu_usd = float(yf.Ticker("UYUUSD=X").fast_info.last_price)
        usd_krw = float(yf.Ticker("USDKRW=X").fast_info.last_price)
        return {
            "uyu_usd": round(uyu_usd, 6),
            "usd_krw": round(usd_krw, 2),
            "uyu_krw": round(uyu_usd * usd_krw, 4),
            "source": "Yahoo Finance",
            "fetched_at": _time.time(),
            "ok": True,
        }

    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, _fetch_uyu)
        _uyu_exchange_cache["data"] = data
        _uyu_exchange_cache["ts"] = _time.time()
        return JSONResponse(data)
    except Exception as exc:
        fallback: dict[str, Any] = {
            "uyu_usd": 0.02481,
            "usd_krw": 1393.0,
            "uyu_krw": 34.57,
            "source": "폴백 (Yahoo Finance 연결 실패)",
            "fetched_at": time.time(),
            "ok": False,
            "error": str(exc),
        }
        return JSONResponse(fallback)


# ── 우루과이 크롤링 파이프라인 ────────────────────────────────────────────────────

_uy_crawl_cache: dict[str, Any] = {"result": None, "running": False}


class UyCrawlBody(BaseModel):
    inn_names: list[str] = ["Cilostazol"]
    save_db: bool = True


@app.post("/api/uy/crawl")
async def trigger_uy_crawl(body: UyCrawlBody | None = None) -> JSONResponse:
    req = body if body is not None else UyCrawlBody()
    if _uy_crawl_cache["running"]:
        raise HTTPException(status_code=409, detail="UY 크롤링이 이미 실행 중입니다.")

    async def _run() -> None:
        _uy_crawl_cache["running"] = True
        try:
            from analysis.uy_export_analyzer import analyze_uy_market
            result = await analyze_uy_market(
                inn_names=req.inn_names,
                save_db=req.save_db,
                emit=_emit,
            )
            _uy_crawl_cache["result"] = result
        finally:
            _uy_crawl_cache["running"] = False

    asyncio.create_task(_run())
    return JSONResponse({"ok": True, "message": f"{req.inn_names} UY 크롤링 시작"})


@app.get("/api/uy/crawl/status")
async def uy_crawl_status() -> JSONResponse:
    return JSONResponse({
        "running": _uy_crawl_cache["running"],
        "has_result": _uy_crawl_cache["result"] is not None,
        "result": _uy_crawl_cache["result"],
    })


@app.get("/api/uy/pricing")
async def api_uy_pricing(inn_name: str | None = None, limit: int = 100) -> JSONResponse:
    try:
        from utils.db import get_supabase_client
        sb = get_supabase_client()
        query = sb.table("uy_pricing").select("*").order("crawled_at", desc=True).limit(limit)
        if inn_name:
            query = query.ilike("inn_name", f"%{inn_name}%")
        result = query.execute()
        return JSONResponse({"ok": True, "count": len(result.data), "rows": result.data})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)[:200], "rows": []})


# ── FOB 역산기 ────────────────────────────────────────────────────────────────

class FobBody(BaseModel):
    price_usd: float
    market_segment: str = "private"
    inn_name: str = ""
    import_duty_pct: float | None = None


@app.post("/api/fob/calculate")
async def api_fob_calculate(body: FobBody) -> JSONResponse:
    from analysis.fob_calculator import (
        calc_logic_a, calc_logic_b, fob_result_to_dict, msp_copayment_check
    )
    from decimal import Decimal

    price = Decimal(str(body.price_usd))
    if body.market_segment == "public":
        duty = Decimal(str(body.import_duty_pct / 100)) if body.import_duty_pct else None
        result = calc_logic_a(price, import_duty_rate=duty, inn_name=body.inn_name)
    else:
        result = calc_logic_b(price, inn_name=body.inn_name)

    d = fob_result_to_dict(result)
    d["msp_check"] = msp_copayment_check(result.base.fob_usd)
    return JSONResponse({"ok": True, **d})


# ── 인도네시아 AHP 파트너 매칭 ────────────────────────────────────────────────────

@app.get("/api/ahp/partners")
async def api_ahp_partners() -> JSONResponse:
    from analysis.ahp_matcher import score_all_candidates, ahp_results_to_dicts
    results = score_all_candidates()
    return JSONResponse({"ok": True, "count": len(results), "partners": ahp_results_to_dicts(results)})


# ── 우루과이 시장 뉴스 (Perplexity) ────────────────────────────────────────────

_uy_news_cache: dict[str, Any] = {"data": None, "ts": 0.0}
_UY_NEWS_TTL = 1800


@app.get("/api/uy/news")
async def api_uy_news() -> JSONResponse:
    import time as _time
    import os
    import httpx

    if _uy_news_cache["data"] and _time.time() - _uy_news_cache["ts"] < _UY_NEWS_TTL:
        return JSONResponse(_uy_news_cache["data"])

    px_key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
    if not px_key:
        return JSONResponse({"ok": False, "error": "PERPLEXITY_API_KEY 미설정", "items": []})

    try:
        payload = {
            "model": "sonar-pro",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a Uruguay pharmaceutical market analyst. "
                        "Return ONLY a JSON array with up to 6 recent news items. "
                        "All 'title' values MUST be written in Korean (한국어)."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Find the latest Uruguay pharmaceutical market, regulatory news, "
                        "and drug pricing policy (ASSE, MSP, ARCE). "
                        "Return strict JSON array. Each item: title (Korean), source, date, link."
                    ),
                },
            ],
            "max_tokens": 900,
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {px_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            raw = resp.json()

        content = str(raw.get("choices", [{}])[0].get("message", {}).get("content", ""))
        items = _parse_perplexity_news_items(content)
        data = {"ok": bool(items), "items": items}
        _uy_news_cache["data"] = data
        _uy_news_cache["ts"] = _time.time()
        return JSONResponse(data)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)[:120], "items": []})


@app.get("/")
async def index() -> FileResponse:
    index_path = STATIC / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="index.html 없음")
    return FileResponse(index_path)


@app.get("/frontend3")
async def frontend3() -> FileResponse:
    path = STATIC / "frontend3.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="frontend3.html 없음")
    return FileResponse(path)


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="SG 분석 대시보드")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()

    if args.open:
        def _open_later() -> None:
            time.sleep(1.0)
            webbrowser.open(f"http://127.0.0.1:{args.port}/")
        threading.Thread(target=_open_later, daemon=True).start()

    print(f"\n  ▶ 대시보드: http://127.0.0.1:{args.port}/\n")
    uvicorn.run(app, host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
