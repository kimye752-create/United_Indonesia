"""인도네시아 거시지표 — IDR/KRW 환율 포함.

정적 폴백값: KOTRA·IMF·BPS·WHO 2024/2025 기준.
yfinance로 IDR/KRW 실시간 환율 제공.
"""
from __future__ import annotations

from typing import Any

_STATIC_MACRO: list[dict] = [
    {
        "label": "1인당 GDP",
        "value": "$4,941",
        "sub": "2024 · IMF",
        "source_full": "IMF World Economic Outlook Database, 2024 (현재 달러 기준)",
        "source_url": "https://www.imf.org/en/Publications/WEO",
    },
    {
        "label": "인구",
        "value": "2억 8,100만 명",
        "sub": "2024 · BPS Indonesia",
        "source_full": "Badan Pusat Statistik (BPS) Indonesia, 2024",
        "source_url": "https://www.bps.go.id",
    },
    {
        "label": "의약품 시장 규모",
        "value": "USD 87억",
        "sub": "2024E · IQVIA / GlobalData",
        "source_full": "IQVIA Indonesia Pharma Market Report 2024; GlobalData Pharmaceutical Market Forecast Indonesia 2024",
        "source_url": "https://www.iqvia.com",
    },
    {
        "label": "의약품 수입 의존도",
        "value": "약 90%",
        "sub": "원료의약품(API) 기준 · Kemenkes RI",
        "source_full": "Kementerian Kesehatan Republik Indonesia — Rencana Induk Pengembangan Bahan Baku Obat 2020-2024; BPOM RI 국내 제약산업 현황 보고서 2023",
        "source_url": "https://www.kemkes.go.id",
    },
]

_cache: list[dict] | None = None


def get_id_macro() -> list[dict[str, Any]]:
    """인도네시아 거시지표 반환. 정적 폴백 기반.

    각 항목:
        label       — 지표명
        value       — 표시값
        sub         — 간략 출처 (카드 하단)
        source_full — 전체 출처 문장
        source_url  — 출처 링크
    """
    global _cache
    if _cache is not None:
        return _cache
    _cache = list(_STATIC_MACRO)
    return _cache


# ── IDR/KRW 환율 (yfinance) ──────────────────────────────────────────────────

_exchange_cache: dict[str, Any] = {"data": None, "ts": 0.0}
_EXCHANGE_TTL = 300.0  # 5분 캐시


def get_idr_krw() -> dict[str, Any]:
    """IDR/KRW 실시간 환율 (yfinance IDRKRW=X 티커).

    Returns:
        {"rate": float, "display": str, "source": str, "ts": float}
    """
    import time as _t

    now = _t.time()
    cached = _exchange_cache.get("data")
    if cached and now - _exchange_cache["ts"] < _EXCHANGE_TTL:
        return cached

    try:
        import yfinance as yf  # type: ignore

        ticker = yf.Ticker("IDRKRW=X")
        fast = ticker.fast_info
        rate = float(getattr(fast, "last_price", None) or 0)
        if rate <= 0:
            hist = ticker.history(period="1d", interval="1m")
            if not hist.empty:
                rate = float(hist["Close"].iloc[-1])

        if rate > 0:
            result: dict[str, Any] = {
                "rate": rate,
                "display": f"1 IDR = {rate:.4f} KRW",
                "source": "yfinance (IDRKRW=X)",
                "ts": now,
            }
            _exchange_cache["data"] = result
            _exchange_cache["ts"] = now
            return result
    except Exception:
        pass

    # 정적 폴백 (2025-04 기준 약 0.082)
    fallback: dict[str, Any] = {
        "rate": 0.082,
        "display": "1 IDR ≈ 0.0820 KRW (정적 폴백)",
        "source": "static fallback",
        "ts": now,
    }
    return fallback


# 하위 호환
ID_MACRO = _STATIC_MACRO
