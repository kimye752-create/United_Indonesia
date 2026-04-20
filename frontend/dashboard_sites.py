"""인도네시아(ID) 시장조사 크롤링 소스 라벨 (한국어)."""

from __future__ import annotations

from typing import Any, TypedDict


class SiteDef(TypedDict):
    id: str
    name: str
    hint: str
    domain: str


DASHBOARD_SITES: tuple[SiteDef, ...] = (
    {
        "id": "bpom_cek",
        "name": "Cek BPOM · 의약품 등록 검색",
        "hint": "인도네시아 식약청 제품 DB — ML(수입)/MD(국내) 등록번호, 제조사(Pendaftar), 제형, 허가 만료일 수집 (정적 HTML)",
        "domain": "cekbpom.pom.go.id",
    },
    {
        "id": "ekatalog",
        "name": "e-Katalog LKPP · 공공 조달 가격",
        "hint": "정부 납품 Harga Satuan — 성분별 최저가·최고가·중간값 수집. JKN 시장 가격 협상 기준점 (정적 HTML)",
        "domain": "e-katalog.lkpp.go.id",
    },
    {
        "id": "fornas",
        "name": "FORNAS · 국가 처방집",
        "hint": "JKN 급여 등재 의약품 목록 — 2년 주기 전면 검토 + 수시 Addendum. 복합제 등재 여부 핵심 확인 (정적 HTML)",
        "domain": "e-fornas.kemkes.go.id",
    },
    {
        "id": "halodoc",
        "name": "Halodoc · B2C 원격의료",
        "hint": "인도네시아 최대 헬스테크 — 소매 정가·할인율·경쟁 제네릭 노출 빈도. Elasticsearch 동적 렌더링 (Playwright)",
        "domain": "halodoc.com",
    },
    {
        "id": "k24klik",
        "name": "K24Klik · 온라인 약국",
        "hint": "Apotek K-24 공식몰 — sitemap.xml 기반 전수 가격 조사 가능. 24시간 배송 재고 상태 포함 (정적 HTML)",
        "domain": "k24klik.com",
    },
    {
        "id": "swiperx",
        "name": "SwipeRx · B2B 약국 네트워크",
        "hint": "동남아 최대 B2B 약국 플랫폼 — 인도네시아 12,000+ 약국 가입. 도매가·번들 할인·CPD 커뮤니티 데이터 (정적 HTML)",
        "domain": "swiperx.com",
    },
    {
        "id": "mims_id",
        "name": "MIMS Indonesia · 임상 약품 DB",
        "hint": "MIMS Class 기반 경쟁 제품 현황 — 처방 적응증·용법·부작용·경쟁사 포지셔닝 수집 (정적 HTML)",
        "domain": "mims.com/indonesia",
    },
)


def initial_site_states() -> dict[str, dict[str, Any]]:
    return {
        s["id"]: {
            "status": "pending",
            "message": "아직 시작 전이에요",
            "ts": 0.0,
        }
        for s in DASHBOARD_SITES
    }
