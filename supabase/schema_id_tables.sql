-- =============================================================================
-- ID (인도네시아) 전용 보조 테이블
-- Supabase SQL Editor에서 한 번 실행
-- 모든 테이블은 'id_' 접두어 → 다른 팀원(sg_, uy_, mn_ 등)과 물리적 분리
-- =============================================================================

-- 1. 품목별 분석 컨텍스트 (id_export_analyzer 결과 캐시)
create table if not exists id_product_context (
  id                    uuid primary key default gen_random_uuid(),
  product_id            text not null unique,
  -- BPOM 등록 상태
  bpom_registered       boolean default false,
  bpom_reg_no           text default '',
  bpom_holder           text default '',
  bpom_expire_date      text default '',
  -- e-Katalog 조달가
  ekatalog_price_idr    bigint default 0,
  ekatalog_satuan       text default '',
  ekatalog_supplier     text default '',
  ekatalog_year         text default '',
  -- FORNAS/JKN 급여 여부
  fornas_listed         boolean default false,
  fornas_tier           text default '',          -- 'tier_1'~'tier_3' 또는 ''
  -- Halodoc 소매가
  halodoc_price_idr     bigint default 0,
  halodoc_discount_pct  int default 0,
  -- Claude 분석 결과
  verdict               text default '',
  rationale             text default '',
  entry_pathway         text default '',
  confidence_note       text default '',
  pdf_snippets          jsonb default '[]'::jsonb,
  raw_analysis          jsonb default '{}'::jsonb,
  built_at              timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);

-- 2. BPOM Cek 크롤링 결과 캐시
create table if not exists id_bpom_results (
  id                    bigserial primary key,
  keyword               text not null,
  product_name          text not null,
  reg_no                text default '',
  reg_type              text default '',          -- 'ML'(수입) / 'MD'(국내)
  holder                text default '',          -- Pendaftar
  dosage_form           text default '',          -- Bentuk Sediaan
  expire_date           text default '',
  crawled_at            timestamptz not null default now(),
  unique(reg_no)
);

-- 3. e-Katalog LKPP 조달가 캐시
create table if not exists id_ekatalog_prices (
  id                    bigserial primary key,
  keyword               text not null,
  product_name          text not null,
  inn                   text default '',
  price_idr             bigint default 0,
  satuan                text default '',           -- 단위 (정/캡슐/mL 등)
  supplier              text default '',
  contract_year         text default '',
  source_url            text default '',
  crawled_at            timestamptz not null default now()
);

-- 4. Halodoc 소매가 캐시
create table if not exists id_halodoc_prices (
  id                    bigserial primary key,
  keyword               text not null,
  product_name          text not null,
  brand                 text default '',
  price_idr             bigint default 0,
  discount_pct          int default 0,
  unit                  text default '',
  is_rx                 boolean default false,
  crawled_at            timestamptz not null default now()
);

-- 5. FORNAS/JKN 급여 목록 캐시
create table if not exists id_fornas_listing (
  id                    bigserial primary key,
  inn                   text not null unique,
  product_name          text default '',
  tier                  text default '',           -- 'tier_1' / 'tier_2' / 'tier_3'
  fornas_edition        text default '',           -- 예: '2023'
  indication            text default '',
  dosage_form           text default '',
  strength              text default '',
  notes                 text default '',
  raw_payload           jsonb default '{}'::jsonb,
  updated_at            timestamptz not null default now()
);

-- 6. PDF 문서 메타데이터 (Supabase Storage)
create table if not exists id_documents (
  id                    uuid primary key default gen_random_uuid(),
  filename              text not null unique,
  storage_path          text not null,
  bucket                text not null default 'id-documents',
  category              text check (category in
    ('regulation','brochure','paper','report','market','strategy','bpom','ekatalog')),
  product_id            text,
  label                 text,
  file_size_bytes       bigint,
  created_at            timestamptz not null default now()
);

-- 7. 시장조사 희망 대상 (8개 KUP 품목 + 추가 관심 품목)
create table if not exists id_market_targets (
  id                    bigserial primary key,
  product_name          text,
  inn_name              text,
  dosage_form           text,
  target_channel        text check (target_channel in ('public','private','both')),
  notes                 text,
  priority              int default 0,
  raw_payload           jsonb,
  created_at            timestamptz not null default now()
);

-- 8. 마진 스프레드 분석 결과
create table if not exists id_margin_analysis (
  id                    bigserial primary key,
  product_id            text not null,
  inn                   text default '',
  ekatalog_price_idr    bigint default 0,
  halodoc_price_idr     bigint default 0,
  spread_idr            bigint default 0,
  spread_pct            numeric(6,1) default 0,
  estimated_fob_idr     bigint default 0,
  analysis_date         date not null default current_date,
  notes                 text default '',
  created_at            timestamptz not null default now(),
  unique(product_id, analysis_date)
);

-- =============================================================================
-- 인덱스
-- =============================================================================
create index if not exists idx_id_product_context_pid   on id_product_context(product_id);
create index if not exists idx_id_bpom_keyword          on id_bpom_results(keyword);
create index if not exists idx_id_bpom_reg_no           on id_bpom_results(reg_no);
create index if not exists idx_id_ekatalog_keyword      on id_ekatalog_prices(keyword);
create index if not exists idx_id_ekatalog_inn          on id_ekatalog_prices(inn);
create index if not exists idx_id_halodoc_keyword       on id_halodoc_prices(keyword);
create index if not exists idx_id_fornas_inn            on id_fornas_listing(inn);
create index if not exists idx_id_documents_category   on id_documents(category);
create index if not exists idx_id_documents_product    on id_documents(product_id);
create index if not exists idx_id_margin_pid_date      on id_margin_analysis(product_id, analysis_date);

-- =============================================================================
-- products 공유 테이블 보호 — RLS 정책 (Row Level Security)
-- 팀 공유 테이블에서 'ID' 행만 접근 가능하도록 추가 방어선 설정
-- (Supabase Dashboard > Authentication > Policies 에서도 확인 가능)
-- =============================================================================

-- RLS 활성화 (이미 켜져 있으면 무시됨)
alter table if exists products enable row level security;

-- ID 팀 전용 정책: country='ID' 행만 SELECT/INSERT/UPDATE/DELETE 허용
-- 주의: service_role key는 RLS를 우회함. anon/authenticated key 사용 시에만 적용됨.
--       현재 코드는 service_role key 사용 중이므로 아래 정책은 추가 참고용임.
--       실질적 보호는 utils/db.py의 _guard_country() 함수가 담당함.

do $$
begin
  if not exists (
    select 1 from pg_policies
    where tablename = 'products' and policyname = 'id_team_isolation'
  ) then
    execute $pol$
      create policy id_team_isolation on products
        for all
        using (country = 'ID')
        with check (country = 'ID')
    $pol$;
  end if;
end
$$;
