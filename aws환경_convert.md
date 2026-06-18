# 로컬 → AWS 환경 전환 가이드

> 로컬(10.149.67.179) 환경에서 AWS EC2/RDS로 이전할 때 수정해야 하는 항목을 정리한 문서.
> `{AWS_PUBLIC_IP}` = EC2 공인 IP, `{DB_HOST}` = RDS 엔드포인트 또는 EC2 내부 IP로 치환.

---

## 0. 환경변수 설정 (로컬 / AWS 공통)

DB 비밀번호는 코드에 하드코딩하지 않고 **환경변수로 주입**한다.
`core/db.py`는 `os.getenv("DB_PASSWORD", "")`로 읽으므로, 환경변수 미설정 시 접속 실패한다.

### Windows (로컬)
```powershell
# 영구 설정 (사용자 환경변수)
[System.Environment]::SetEnvironmentVariable("DB_PASSWORD", "einz00!", "User")

# 현재 세션에도 즉시 적용
$env:DB_PASSWORD = "einz00!"
```

### Linux (AWS EC2)
```bash
# ~/.bashrc 또는 /etc/environment에 추가
export DB_PASSWORD="einz00!"

# 즉시 적용
source ~/.bashrc
```

### 전체 환경변수 목록

| 변수명 | 기본값 | 설명 |
|--------|--------|------|
| `DB_HOST` | `10.149.67.179` | PostgreSQL 호스트 (AWS에서 변경) |
| `DB_PORT` | `5432` | PostgreSQL 포트 |
| `DB_NAME` | `aops` | 데이터베이스명 |
| `DB_USER` | `postgres` | 접속 사용자 |
| `DB_PASSWORD` | (없음, 필수) | DB 비밀번호 — 반드시 환경변수로 설정 |

---

## 1. 코드 변경 (2개 파일)

### 1-1. DB 접속 호스트 — `core/db.py` (23행)

```python
# 현재 (로컬)
"host": os.getenv("DB_HOST", "10.149.67.179"),

# 변경 (AWS) — 환경변수 또는 기본값 변경
"host": os.getenv("DB_HOST", "localhost"),           # 같은 EC2에 DB 동거 시
"host": os.getenv("DB_HOST", "{RDS_ENDPOINT}"),      # RDS 분리 시
```

> 비밀번호는 이미 환경변수 전용: `os.getenv("DB_PASSWORD", "")` — 코드 변경 불필요.

### 1-2. Vite 프록시 대상 — `web/frontend/vite.config.js` (11행)

```js
// 현재 (로컬)
target: 'http://10.149.67.179:8000',

// 변경 (AWS)
// - 웹+백엔드 같은 서버: 'http://localhost:8000'
// - 백엔드 분리 서버:    'http://{백엔드_IP}:8000'
target: 'http://localhost:8000',
```

### 1-3. 시작 스크립트 URL — `web/start_web.py` (67행)

```python
# 현재 (로컬)
url = "http://10.149.67.179:5173"

# 변경 (AWS)
url = "http://{AWS_PUBLIC_IP}:5173"
```

---

## 2. PostgreSQL 설정 (DB가 같은 EC2에 있을 경우)

### 2-1. `pg_hba.conf` — 접속 허용 IP

```conf
# 현재 (로컬)
host    all    all    127.0.0.1/32        scram-sha-256
host    all    all    10.149.67.179/32    scram-sha-256

# 변경 (AWS) — 로컬 접속만 허용 (같은 서버)
host    all    all    127.0.0.1/32        scram-sha-256
# 10.149.67.179 행 삭제

# 변경 (AWS) — 다른 서버에서 접속 허용 시
host    all    all    {EC2_PRIVATE_IP}/32  scram-sha-256
# 또는 VPC 대역 허용
host    all    all    10.0.0.0/16          scram-sha-256
```

### 2-2. `postgresql.conf` — 수신 주소

```conf
# 현재 (이미 설정됨, 유지)
listen_addresses = '*'

# 보안 강화 시
listen_addresses = 'localhost'          # 같은 서버만
listen_addresses = 'localhost,10.0.0.5' # 특정 내부 IP만
```

변경 후 반드시 리로드:
```bash
pg_ctl reload -D /var/lib/postgresql/18/data
# 또는
sudo systemctl reload postgresql
```

---

## 3. AWS 인프라 설정

### 3-1. Security Group (보안 그룹) 인바운드 규칙

| 포트 | 프로토콜 | 소스 | 용도 |
|------|----------|------|------|
| **5173** | TCP | `0.0.0.0/0` (또는 사무실 IP) | 프론트엔드 (Vite) |
| **8000** | TCP | `0.0.0.0/0` (또는 사무실 IP) | 백엔드 API (FastAPI) |
| **5432** | TCP | EC2 자체 SG (또는 비허용) | PostgreSQL (외부 차단 권장) |
| **22** | TCP | 사무실 IP만 | SSH 접속 |

### 3-2. RDS 사용 시 (DB 분리)

| 항목 | 설정 |
|------|------|
| `DB_HOST` 환경변수 | RDS 엔드포인트 (예: `aops-db.xxxx.ap-northeast-2.rds.amazonaws.com`) |
| `DB_PASSWORD` 환경변수 | RDS 마스터 비밀번호 |
| `pg_hba.conf` | RDS가 관리하므로 수정 불필요 |
| Security Group | RDS SG에 EC2 SG를 소스로 허용 |
| 테이블 생성 | `create_table.sql` 실행 |
| 데이터 이관 | `insert_mig_data.sql` 실행 |

---

## 4. 변경 불필요 (이미 AWS 호환)

| 항목 | 파일 | 이유 |
|------|------|------|
| DB 비밀번호 | `core/db.py:27` | 이미 `os.getenv("DB_PASSWORD", "")` — 환경변수 전용 |
| uvicorn 바인딩 | `web/start_web.py:51` | 이미 `--host 0.0.0.0` |
| Vite 서버 호스트 | `vite.config.js:7` | 이미 `host: '0.0.0.0'` |
| CORS 설정 | `web/backend/app.py:17` | `allow_origins=["*"]` |
| 프론트엔드 API 호출 | `src/pages/*.jsx` | 모두 상대경로 `/api/...` |
| CLI 크롤링 실행 | `main.py` | DB 접속만 바뀌면 동작 |
| 로그/출력 경로 | `logs/`, `output/` | 상대경로 사용 |

---

## 5. 환경별 설정 요약

| 항목 | 로컬 (현재) | AWS (같은 EC2) | AWS (EC2 + RDS) |
|------|------------|---------------|-----------------|
| `DB_HOST` | `10.149.67.179` | `localhost` | RDS 엔드포인트 |
| `DB_PASSWORD` | 환경변수 `einz00!` | 환경변수 | 환경변수 |
| Vite proxy target | `10.149.67.179:8000` | `localhost:8000` | `localhost:8000` |
| start_web.py URL | `10.149.67.179:5173` | `{공인IP}:5173` | `{공인IP}:5173` |
| pg_hba.conf | `10.149.67.179/32` 허용 | `127.0.0.1/32` | RDS 관리 |
| Security Group | 없음 | 5173, 8000 오픈 | 5173, 8000 오픈 |

---

## 6. 전환 체크리스트

```
[ ] EC2 인스턴스 생성 + Security Group 설정
[ ] PostgreSQL 설치 (또는 RDS 생성)
[ ] 환경변수 설정: DB_HOST, DB_PASSWORD (+ 필요시 DB_NAME, DB_USER)
[ ] create_table.sql 실행하여 테이블 생성
[ ] insert_mig_data.sql 실행하여 데이터 이관
[ ] core/db.py DB_HOST 기본값 변경
[ ] vite.config.js proxy target 변경
[ ] web/start_web.py 접속 URL 변경
[ ] pg_hba.conf 접속 허용 IP 수정 (EC2 직접 설치 시)
[ ] Python 3.12 + .venv 구성 + pip install
[ ] Node.js + npm install (web/frontend/)
[ ] Playwright 설치: playwright install chromium
[ ] python web/start_web.py 실행 후 외부 접속 확인
```

---

## 7. 참고 파일

| 파일 | 용도 |
|------|------|
| `create_table.sql` | PostgreSQL 테이블 생성 DDL |
| `insert_mig_data.sql` | 기존 데이터 마이그레이션 INSERT (436건) |
| `migrate_sqlite_to_pg.py` | SQLite→PostgreSQL 직접 마이그레이션 스크립트 |
