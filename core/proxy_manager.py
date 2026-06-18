"""
무료 프록시 IP 로테이션 관리 모듈

여러 무료 프록시 소스에서 프록시 목록을 수집하고,
유효성 검증 후 라운드로빈 방식으로 로테이션한다.

Playwright 브라우저와 통합하여 사용:
  - BrowserManager.create(proxy=proxy_mgr.get_next()) 형태로 주입
  - 429/차단 시 rotate_on_block()으로 현재 프록시 블랙리스트 + 교체
"""
import json
import os
import re
import time
import random
import threading
import urllib.request
import urllib.error
from datetime import datetime


_PROXY_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "proxies",
)
_PROXY_CACHE_FILE = os.path.join(_PROXY_CACHE_DIR, "proxy_list.json")

_PROXY_SOURCES = [
    {
        "name": "proxyscrape_http",
        "url": "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
        "type": "plain",
    },
    {
        "name": "proxyscrape_socks4",
        "url": "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks4&timeout=10000&country=all",
        "type": "plain",
        "protocol": "socks4",
    },
    {
        "name": "proxyscrape_socks5",
        "url": "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=10000&country=all",
        "type": "plain",
        "protocol": "socks5",
    },
    {
        "name": "thespeedx_http",
        "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "type": "plain",
    },
    {
        "name": "thespeedx_socks5",
        "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "type": "plain",
        "protocol": "socks5",
    },
    {
        "name": "clarketm",
        "url": "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
        "type": "plain",
    },
    {
        "name": "monosans_http",
        "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        "type": "plain",
    },
    {
        "name": "monosans_socks5",
        "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
        "type": "plain",
        "protocol": "socks5",
    },
]

# 프록시 검증 시 테스트 URL
_TEST_URL = "https://httpbin.org/ip"
_TEST_TIMEOUT = 8

# 캐시 유효 시간 (초) — 30분
_CACHE_TTL = 1800

# 최대 검증 프록시 수
_MAX_VALIDATE = 200

# 검증 통과 목표 수
_TARGET_VALID = 15


class ProxyManager:
    """무료 프록시 수집 + 검증 + 로테이션 관리"""

    def __init__(self, auto_fetch: bool = True):
        self._proxies: list[dict] = []
        self._blacklist: set[str] = set()
        self._current_idx: int = 0
        self._lock = threading.Lock()
        self._last_fetch_time: float = 0

        if auto_fetch:
            self._load_or_fetch()

    @property
    def available_count(self) -> int:
        with self._lock:
            return len([p for p in self._proxies if p["server"] not in self._blacklist])

    @property
    def total_count(self) -> int:
        return len(self._proxies)

    def get_next(self) -> dict | None:
        """다음 사용할 프록시를 반환한다 (라운드로빈).

        Returns:
            {"server": "http://ip:port"} 형태 또는 None (프록시 없음)
        """
        with self._lock:
            available = [p for p in self._proxies if p["server"] not in self._blacklist]
            if not available:
                return None

            self._current_idx = self._current_idx % len(available)
            proxy = available[self._current_idx]
            self._current_idx += 1
            return {"server": proxy["server"]}

    def get_random(self) -> dict | None:
        """랜덤 프록시를 반환한다."""
        with self._lock:
            available = [p for p in self._proxies if p["server"] not in self._blacklist]
            if not available:
                return None
            proxy = random.choice(available)
            return {"server": proxy["server"]}

    def rotate_on_block(self, current_server: str | None = None) -> dict | None:
        """현재 프록시를 블랙리스트에 추가하고 다음 프록시를 반환한다."""
        with self._lock:
            if current_server:
                self._blacklist.add(current_server)
                print(f"[proxy] 차단된 프록시 제외: {current_server} (블랙리스트: {len(self._blacklist)}개)")

            available = [p for p in self._proxies if p["server"] not in self._blacklist]
            if not available:
                print("[proxy] 사용 가능한 프록시가 없습니다. 목록을 새로 가져옵니다...")
                self._blacklist.clear()
                self._lock.release()
                try:
                    self.refresh()
                finally:
                    self._lock.acquire()
                available = [p for p in self._proxies if p["server"] not in self._blacklist]
                if not available:
                    return None

            proxy = random.choice(available)
            return {"server": proxy["server"]}

    def refresh(self):
        """프록시 목록을 새로 가져오고 검증한다."""
        print("[proxy] 프록시 목록 갱신 중...")
        raw_proxies = self._fetch_all_sources()
        if not raw_proxies:
            print("[proxy] 프록시를 가져올 수 없습니다")
            return

        print(f"[proxy] {len(raw_proxies)}개 프록시 수집 완료, 검증 시작...")
        validated = self._validate_proxies(raw_proxies)

        with self._lock:
            self._proxies = validated
            self._blacklist.clear()
            self._current_idx = 0
            self._last_fetch_time = time.time()

        self._save_cache(validated)
        print(f"[proxy] 검증 완료: {len(validated)}개 사용 가능")

    def _load_or_fetch(self):
        """캐시에서 로드하거나, 만료/없으면 새로 가져온다."""
        cached = self._load_cache()
        if cached:
            with self._lock:
                self._proxies = cached
            print(f"[proxy] 캐시에서 {len(cached)}개 프록시 로드")
            return

        self.refresh()

    def _load_cache(self) -> list[dict] | None:
        """캐시 파일에서 프록시 목록을 로드한다."""
        if not os.path.exists(_PROXY_CACHE_FILE):
            return None

        try:
            with open(_PROXY_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            fetched_at = data.get("fetched_at", 0)
            if time.time() - fetched_at > _CACHE_TTL:
                print("[proxy] 캐시 만료됨")
                return None

            proxies = data.get("proxies", [])
            if not proxies:
                return None

            return proxies
        except Exception:
            return None

    def _save_cache(self, proxies: list[dict]):
        """프록시 목록을 캐시 파일에 저장한다."""
        try:
            os.makedirs(_PROXY_CACHE_DIR, exist_ok=True)
            data = {
                "fetched_at": time.time(),
                "fetched_at_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "count": len(proxies),
                "proxies": proxies,
            }
            with open(_PROXY_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[proxy] 캐시 저장 실패: {e}")

    def _fetch_all_sources(self) -> list[dict]:
        """모든 소스에서 프록시를 수집한다."""
        all_proxies = {}

        for source in _PROXY_SOURCES:
            try:
                proxies = self._fetch_source(source)
                for p in proxies:
                    key = p["server"]
                    if key not in all_proxies:
                        all_proxies[key] = p
            except Exception as e:
                print(f"[proxy] {source['name']} 수집 실패: {e}")

        return list(all_proxies.values())

    def _fetch_source(self, source: dict) -> list[dict]:
        """단일 소스에서 프록시 목록을 가져온다."""
        req = urllib.request.Request(
            source["url"],
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8", errors="ignore")

        protocol = source.get("protocol", "http")
        proxies = []

        if source["type"] == "plain":
            for line in text.strip().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                match = re.match(r"^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{2,5})$", line)
                if match:
                    ip, port = match.group(1), match.group(2)
                    server = f"{protocol}://{ip}:{port}"
                    proxies.append({
                        "server": server,
                        "source": source["name"],
                        "protocol": protocol,
                    })

        if proxies:
            print(f"[proxy] {source['name']}: {len(proxies)}개 수집")
        return proxies

    def _validate_proxies(self, proxies: list[dict]) -> list[dict]:
        """프록시 유효성을 병렬로 검증한다. HTTP 프록시를 우선 검증."""
        http_proxies = [p for p in proxies if p.get("protocol", "http") == "http"]
        other_proxies = [p for p in proxies if p.get("protocol", "http") != "http"]
        random.shuffle(http_proxies)
        random.shuffle(other_proxies)
        candidates = (http_proxies + other_proxies)[:_MAX_VALIDATE]

        validated = []
        lock = threading.Lock()

        def _test_one(proxy):
            if len(validated) >= _TARGET_VALID:
                return
            server = proxy["server"]
            try:
                proxy_handler = urllib.request.ProxyHandler({
                    "http": server,
                    "https": server,
                })
                opener = urllib.request.build_opener(proxy_handler)
                req = urllib.request.Request(
                    _TEST_URL,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                with opener.open(req, timeout=_TEST_TIMEOUT) as resp:
                    body = resp.read().decode("utf-8", errors="ignore")
                    if "origin" in body:
                        with lock:
                            if len(validated) < _TARGET_VALID:
                                proxy["validated_at"] = time.time()
                                validated.append(proxy)
                                print(f"[proxy] ✓ {server}")
            except Exception:
                pass

        BATCH_SIZE = 30
        for i in range(0, len(candidates), BATCH_SIZE):
            if len(validated) >= _TARGET_VALID:
                break
            batch = candidates[i:i + BATCH_SIZE]
            threads = []
            for proxy in batch:
                if len(validated) >= _TARGET_VALID:
                    break
                t = threading.Thread(target=_test_one, args=(proxy,), daemon=True)
                threads.append(t)
                t.start()
            for t in threads:
                t.join(timeout=_TEST_TIMEOUT + 2)

        return validated


# ─── 모듈 레벨 싱글톤 (lazy init) ──────────────────────────────────

_instance: ProxyManager | None = None
_instance_lock = threading.Lock()


def get_proxy_manager(auto_fetch: bool = True) -> ProxyManager:
    """ProxyManager 싱글톤을 반환한다."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ProxyManager(auto_fetch=auto_fetch)
    return _instance
