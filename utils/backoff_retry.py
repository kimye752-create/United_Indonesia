"""
backoff_retry.py — HTTP 요청용 지수 백오프 + 지터 + 429 Retry-After 존중

Saudi Pharma Crawler(backoff_retry.py) 기반 포팅 — Anti-bot 연동 포함.

핵심 원칙:
1. 429면 서버의 Retry-After 헤더를 최우선으로 따른다 (초 + HTTP-date 둘 다)
2. 5xx는 지터 포함 지수 백오프
3. 4xx (401/403/404)는 재시도 안 함 — Anti-bot 탐지에서 별도 처리
4. CAPTCHA/IP차단 탐지 시 즉시 전파 (Circuit Break 권고)

⚠️ IDEMPOTENCY: GET 및 idempotent 메서드에만 적용하라.

사용 예:
    @with_backoff(max_attempts=3, base=3.0, max_wait=60.0)
    def fetch(url: str) -> httpx.Response:
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        return resp
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
import time
from typing import Any, Callable, TypeVar

import httpx

from utils.id_antibot import AntiBotType, detect as detect_antibot, get_countermeasure

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class RetryExhausted(Exception):
    """최대 재시도 횟수 초과"""


def _compute_wait(attempt: int, *, base: float, max_wait: float, jitter: float) -> float:
    """지수 백오프 + 지터."""
    exponential = base * (2 ** attempt)
    jittered = exponential + random.uniform(0, jitter)
    return min(jittered, max_wait)


def _parse_retry_after(header_value: str | None) -> float | None:
    """Retry-After 헤더 파싱 (RFC 7231). delta-seconds 또는 HTTP-date."""
    if not header_value:
        return None
    header_value = header_value.strip()
    try:
        return max(0.0, float(header_value))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(header_value)
        if dt is None:
            return None
        delta = dt.timestamp() - time.time()
        return max(0.0, delta)
    except (TypeError, ValueError):
        return None


def with_backoff(
    *,
    max_attempts: int = 3,
    base: float = 3.0,
    max_wait: float = 60.0,
    jitter: float = 2.0,
    retry_on_status: tuple[int, ...] = (429, 500, 502, 503, 504),
) -> Callable[[F], F]:
    """동기 HTTP 호출 함수를 감싸는 재시도 데코레이터."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except httpx.HTTPStatusError as e:
                    status = e.response.status_code
                    last_exc = e

                    resp_body = ""
                    try:
                        resp_body = e.response.text[:2000]
                    except Exception:
                        pass
                    resp_headers = dict(e.response.headers) if e.response else {}
                    ab_type = detect_antibot(status, resp_body, resp_headers)
                    cm = get_countermeasure(ab_type)

                    if cm.should_circuit_break:
                        logger.warning("Anti-bot 탐지: %s → 즉시 전파", ab_type.value)
                        raise

                    if status not in retry_on_status:
                        raise

                    if attempt == max_attempts - 1:
                        break

                    wait: float
                    if status == 429:
                        retry_after = _parse_retry_after(e.response.headers.get("Retry-After"))
                        if retry_after is not None:
                            wait = min(retry_after * cm.delay_multiplier, max_wait)
                        else:
                            wait = min(
                                _compute_wait(attempt, base=base, max_wait=max_wait, jitter=jitter) * cm.delay_multiplier,
                                max_wait,
                            )
                    else:
                        wait = min(
                            _compute_wait(attempt, base=base, max_wait=max_wait, jitter=jitter) * cm.delay_multiplier,
                            max_wait,
                        )
                    logger.warning("%d 받음 [%s] (시도 %d/%d). %.1fs 대기", status, ab_type.value, attempt + 1, max_attempts, wait)
                    time.sleep(wait)

                except (httpx.TimeoutException, httpx.NetworkError) as e:
                    last_exc = e
                    if attempt == max_attempts - 1:
                        break
                    wait = _compute_wait(attempt, base=base, max_wait=max_wait, jitter=jitter)
                    logger.warning("네트워크 오류: %s. %.1fs 대기 후 재시도", e, wait)
                    time.sleep(wait)

            raise RetryExhausted(f"{func.__name__} 최대 재시도 초과 (attempts={max_attempts})") from last_exc

        return wrapper  # type: ignore[return-value]

    return decorator


# ─── 비동기 버전 (기존 코드 호환) ───────────────────────
async def fetch_with_retry(
    url: str,
    *,
    attempts: int = 3,
    timeout: float = 20.0,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[int, str]:
    """httpx 비동기 GET + Anti-bot 재시도.

    Returns:
        (status_code, response_text)
    """
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(
                http2=True,
                timeout=timeout,
                follow_redirects=True,
                headers=headers or {},
            ) as client:
                r = await client.get(url, params=params)
                r.raise_for_status()
                return r.status_code, r.text
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            last_exc = e
            resp_body = ""
            try:
                resp_body = e.response.text[:2000]
            except Exception:
                pass
            resp_headers = dict(e.response.headers) if e.response else {}
            ab_type = detect_antibot(status, resp_body, resp_headers)
            cm = get_countermeasure(ab_type)

            if cm.should_circuit_break:
                raise

            if status not in (429, 500, 502, 503, 504):
                raise

            if attempt == attempts - 1:
                break

            wait: float
            if status == 429:
                retry_after = _parse_retry_after(e.response.headers.get("Retry-After"))
                wait = min(
                    (retry_after * cm.delay_multiplier) if retry_after is not None
                    else _compute_wait(attempt, base=3.0, max_wait=60.0, jitter=2.0) * cm.delay_multiplier,
                    60.0,
                )
            else:
                wait = min(
                    _compute_wait(attempt, base=3.0, max_wait=60.0, jitter=2.0) * cm.delay_multiplier,
                    60.0,
                )
            await asyncio.sleep(wait)

        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_exc = e
            if attempt == attempts - 1:
                break
            await asyncio.sleep(_compute_wait(attempt, base=3.0, max_wait=60.0, jitter=2.0))

    raise RetryExhausted(f"fetch_with_retry 최대 재시도 초과 (url={url})") from last_exc


# 기존 코드 호환: default_retry (tenacity 제거, 새 구현으로 대체)
def make_retry(*, attempts: int = 3, min_wait: float = 2.0, max_wait: float = 30.0) -> Callable:
    return with_backoff(max_attempts=attempts, base=min_wait, max_wait=max_wait)


default_retry = with_backoff(max_attempts=3, base=2.0, max_wait=30.0)
