# 배포 가이드 (Deployment Guide)

> 본 문서는 공정에너지 MVP를 로컬·시연·베타 환경에 배포하는 절차를 정리한다.
> 정책 07(출시 통제)·06(KPI 측정)과 함께 읽는다.

---

## 1. 환경 분류

| 환경 | 목적 | DEMO_MODE | 외부 LLM | 비고 |
|---|---|---|---|---|
| **로컬 개발** | 개발자 검증 | true | DemoLLMClient | API 키 불필요 |
| **시연 (데모데이)** | 심사위원·관계자 시연 | true | DemoLLMClient | 데모 데이터 사전 주입 |
| **베타 (PoC)** | 사용자 100명 실증 | false | AnthropicLLMClient | 출시 게이트 G1~G6 충족 필수 |

베타 환경은 정책 07의 게이트가 미충족 상태에서 시작하지 않는다.

---

## 2. 로컬 개발 환경

### 사전 요구
- Python 3.11+
- Git (선택)
- 시스템 한국어 폰트 (Windows: 기본 포함, macOS: 기본 포함, Linux: NanumGothic 또는 Noto CJK 설치)

### 설치
```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경변수 설정
cp .env.example .env
# .env 편집:
#   APP_ENV=development
#   DEMO_MODE=true
#   APP_SECRET_KEY=<Fernet.generate_key()로 발급한 32바이트 키>

# 3. Fernet 키 발급 (Python 한 줄)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 4. 앱 실행
streamlit run app.py
```

기본 포트 8501. `--server.port 8765` 등으로 변경 가능.

### 검증
```bash
# 전체 테스트 (335개 통과 기대)
python -m pytest

# 데모 데이터 생성 후 KPI 확인
python scripts/create_demo_data.py --users 30 --reset --db demo.db
python scripts/export_metrics.py --db demo.db --out reports/demo.csv
```

---

## 3. 시연 (데모데이) 환경

### 사전 준비
```bash
# 1. 데모 데이터 주입
python scripts/create_demo_data.py --users 50 --reset --seed 42

# 2. 관리자 모드 활성화 (.env)
ENABLE_ADMIN=true

# 3. Streamlit 실행
streamlit run app.py --server.headless true --server.port 8501
```

### 시연 시나리오
정책 06 §2-A의 KPI 계층을 보여주는 시연 흐름:

1. **사용자 흐름** (페이지 1 → 8)
   - 시작하기 (cohort=NGO 선택)
   - 동의 + 안전체크 (모두 「아니오」 → LOW 등급)
   - 문서 업로드 (5종 슬롯)
   - OR 수동 입력 모드 (3b — 외부 LLM 우회)
   - 추출값 확인 (필드 모두 확인)
   - 자료 완결성 점수 (저장 → passport_created 이벤트)
   - 검산 결과 (분류 + 정액 override 데모)
   - 자료 확인 메시지 예시 (4단계 안전 차단 시연)
   - 자료 요약본 PDF 다운로드

2. **관리자 흐름** (페이지 10)
   - KPI 대시보드에서 데모 사용자 50명의 1차/보조 KPI 표시
   - 분류 분포가 정책 06 §6 기대값과 정렬

3. **안전 시연** (선택)
   - 별도 사용자로 다시 시작 → 안전체크 3·6번 「예」 → VERY_HIGH
   - 페이지 7에서 메시지 본문 자체가 숨겨지는 것 확인

---

## 4. 베타 (PoC) 환경

### 출시 차단 조건 (정책 07 §2)

다음 모두 충족 전까지 베타 시작 금지:

- **G3** 마스킹 정확도 ≥95% — 라벨링 데이터 200건 비교 완료
- **G4** 법률 판단 금지어 필터 통과 — **충족** (24개 패턴 + 회귀)
- **G5** 화우 ESG센터 사전 검토 의견서 확보
- **G6** 룰 엔진 합성 100건 완전일치율 ≥99% — Phase 7b 차단 중

G1·G2는 RAG 미사용으로 N/A.

### 환경변수 (.env)

```env
APP_ENV=production
DEMO_MODE=false                # 실 사용자 → false
ANTHROPIC_API_KEY=sk-ant-...   # 화우 자문 + DPA 검토 후 활성화
APP_SECRET_KEY=<32바이트 키>   # KMS·Secret Manager에서 주입 권장
DATABASE_URL=sqlite:///fair_energy.db  # 또는 PostgreSQL URL
STORAGE_DIR=/var/lib/fair_energy/storage
DEFAULT_RETENTION_MONTHS=6
ENABLE_LLM_OCR=true            # AI OCR 처리 동의 확보 후 활성화
ENABLE_PDF_EXPORT=true         # G3 마스킹 정확도 검증 후 활성화
ENABLE_ADMIN=false             # 관리자 페이지는 별도 인증 환경에서만
```

### 베타 출시 직전 체크

[`docs/BETA_CHECKLIST.md`](BETA_CHECKLIST.md) 참조.

### 운영 점검 명령

```bash
# 매일: 만료된 원본 파기 (cron)
python -c "
from core import config, storage, db
from cryptography.fernet import Fernet
cfg = config.load_config()
key = storage.load_or_generate_key(cfg.app_secret_key, allow_generate=False)
store = storage.DocumentStorage(
    key=key, originals_dir=cfg.originals_dir, masked_dir=cfg.masked_dir,
)
conn = db.init_db(cfg.db_path)
print(f'Purged: {store.purge_expired(conn)} originals')
"

# 매주: KPI export
python scripts/export_metrics.py --out reports/$(date +%Y%m%d).csv

# 분기별: 정책·tariff YAML 검수 (수동)
```

---

## 5. 보안 점검 (베타 직전 필수)

### 키 관리
- `APP_SECRET_KEY`는 평문 파일에 두지 않는다.
- 베타 환경에서는 KMS, AWS Secrets Manager, Azure Key Vault 등에서 주입.
- 키 분실 시 모든 원본 복호화 불가 — 백업 절차 필수.

### 권한
- 관리자 페이지(`pages/10_KPI_대시보드.py`)는 `ENABLE_ADMIN=true`로만 접근 가능.
- 운영 환경에서는 IP 화이트리스트 또는 OAuth 추가 권장.

### 백업
- DB 파일: 매일 백업, 30일 보관.
- 암호화 원본: `storage/originals/` 별도 백업, 키와 분리 보관.
- 마스킹본: 백업 우선순위 낮음(재생성 가능).

### 인시던트 대응
- 원본 유출 의심 시: 정책 04 §10 audit_logs 조회 → 영향 사용자 통지 → 키 회전.
- 가드레일 통과 후 부적절한 출력 보고 시: 정책 01 §2 패턴 보강 + 회귀 테스트 추가.

---

## 6. 후속 환경

### PostgreSQL 전환 (베타 100명 초과 시)
- `DATABASE_URL=postgresql://user:pass@host/db`
- `core/db.py`의 SQLite 의존 코드 점검 필요 (현재 sqlite3 직접 사용 — 추후 SQLAlchemy 도입 검토).

### 클라우드 배포 (선택)
- Streamlit Community Cloud — 가장 빠른 옵션. 단, secret 관리 한계.
- Render / Railway — 컨테이너 배포 + KMS 연동.
- AWS ECS + RDS — 본격 운영 단계.

PoC 단계에서는 Streamlit Community Cloud + 외부 KMS 조합이 가장 가벼움.
