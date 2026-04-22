"""
id_antibot.py — 인도네시아 크롤러용 Anti-bot 탐지 + 규칙 기반 대응

Saudi Pharma Crawler(antibot.py) 기반 포팅 — 인도네시아 사이트에 맞게 조정.
(Cloudflare, WAF 패턴은 동일, 인니어 CAPTCHA 패턴 추가)
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AntiBotType(Enum):
    CLOUDFLARE = "cloudflare"
    RECAPTCHA  = "recaptcha"
    RATE_LIMIT = "rate_limit"
    IP_BLOCK   = "ip_block"
    WAF_GENERIC = "waf_generic"
    NONE       = "none"


@dataclass(frozen=True)
class Countermeasure:
    action: str
    delay_multiplier: float
    extra_headers: dict | None
    should_circuit_break: bool


COUNTERMEASURES: dict[AntiBotType, Countermeasure] = {
    AntiBotType.CLOUDFLARE: Countermeasure(
        action="add_delay_and_headers",
        delay_multiplier=3.0,
        extra_headers={"Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8", "Accept-Encoding": "gzip, deflate, br"},
        should_circuit_break=False,
    ),
    AntiBotType.RATE_LIMIT: Countermeasure(
        action="respect_retry_after",
        delay_multiplier=2.0,
        extra_headers=None,
        should_circuit_break=False,
    ),
    AntiBotType.IP_BLOCK: Countermeasure(
        action="circuit_break",
        delay_multiplier=0,
        extra_headers=None,
        should_circuit_break=True,
    ),
    AntiBotType.RECAPTCHA: Countermeasure(
        action="circuit_break",
        delay_multiplier=0,
        extra_headers=None,
        should_circuit_break=True,
    ),
    AntiBotType.WAF_GENERIC: Countermeasure(
        action="exponential_backoff",
        delay_multiplier=5.0,
        extra_headers=None,
        should_circuit_break=False,
    ),
    AntiBotType.NONE: Countermeasure(
        action="none",
        delay_multiplier=1.0,
        extra_headers=None,
        should_circuit_break=False,
    ),
}

# ─── User-Agent 풀 (2025 최신 브라우저) ─────────────────
UA_POOL: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    # 모바일 UA (Halodoc 등 모바일 최적화 사이트용)
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
]

# Cloudflare 시그니처
_CF_BODY_PATTERNS = (
    "cloudflare", "cf-challenge", "cf-browser-verification",
    "checking your browser", "ray id:",
    "performance & security by cloudflare",
)
_CF_HEADER_PATTERNS = ("cloudflare", "cf-ray")

# CAPTCHA 패턴 (영어 + 인니어)
_CAPTCHA_PATTERNS = (
    "recaptcha", "g-recaptcha", "hcaptcha",
    "captcha-container", "captcha_challenge",
    "verifikasi", "tidak robot",  # 인니어 패턴
)

_WAF_STATUS_CODES = frozenset({520, 521, 522, 523, 524, 525, 526})


def pick_ua() -> str:
    return random.choice(UA_POOL)


def detect(
    status_code: int,
    body: str = "",
    headers: Optional[dict[str, str]] = None,
) -> AntiBotType:
    headers = headers or {}
    body_lower = body.lower()
    headers_lower = {k.lower(): v.lower() for k, v in headers.items()}

    cf_in_body = any(p in body_lower for p in _CF_BODY_PATTERNS)
    cf_in_headers = any(
        any(p in v for p in _CF_HEADER_PATTERNS)
        for v in headers_lower.values()
    )
    if cf_in_body or cf_in_headers:
        return AntiBotType.CLOUDFLARE

    if status_code == 429:
        return AntiBotType.RATE_LIMIT

    if status_code == 403:
        if any(p in body_lower for p in _CAPTCHA_PATTERNS):
            return AntiBotType.RECAPTCHA
        return AntiBotType.IP_BLOCK

    if status_code in _WAF_STATUS_CODES:
        return AntiBotType.WAF_GENERIC

    return AntiBotType.NONE


def get_countermeasure(antibot_type: AntiBotType) -> Countermeasure:
    return COUNTERMEASURES.get(antibot_type, COUNTERMEASURES[AntiBotType.NONE])
