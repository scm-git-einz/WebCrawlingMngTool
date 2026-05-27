"""크롤링 관리 대시보드 — 원클릭 실행 스크립트

사용법:
  python web/start_web.py

FastAPI 백엔드 (8000) + Vite 프론트엔드 (5173) 동시 실행
"""
import os
import subprocess
import sys
import time
import webbrowser

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(ROOT_DIR, "web", "frontend")
VENV_PYTHON = os.path.join(ROOT_DIR, ".venv", "Scripts", "python.exe")
NPM = "npm"

os.chdir(ROOT_DIR)


def check_npm_installed():
    """node_modules 존재 여부 확인, 없으면 npm install"""
    node_modules = os.path.join(FRONTEND_DIR, "node_modules")
    if not os.path.exists(node_modules):
        print("[web] npm install 실행 중...")
        subprocess.run(
            [NPM, "install"],
            cwd=FRONTEND_DIR,
            check=True,
        )
        print("[web] npm install 완료")


def main():
    print("=" * 60)
    print("  크롤링 관리 대시보드")
    print("=" * 60)
    print()

    # 1) npm 패키지 확인
    check_npm_installed()

    # 2) FastAPI 백엔드 시작
    print("[web] FastAPI 백엔드 시작 (port 8000)...")
    backend = subprocess.Popen(
        [
            VENV_PYTHON, "-m", "uvicorn",
            "web.backend.app:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload",
        ],
        cwd=ROOT_DIR,
    )

    # 3) Vite 프론트엔드 시작
    print("[web] Vite 프론트엔드 시작 (port 5173)...")
    frontend = subprocess.Popen(
        [NPM, "run", "dev"],
        cwd=FRONTEND_DIR,
        shell=True,
    )

    time.sleep(3)
    url = "http://localhost:5173"
    print(f"\n[web] 브라우저에서 접속하세요: {url}")
    print("[web] 종료하려면 Ctrl+C를 누르세요.\n")
    webbrowser.open(url)

    try:
        backend.wait()
    except KeyboardInterrupt:
        print("\n[web] 종료 중...")
        backend.terminate()
        frontend.terminate()
        backend.wait()
        frontend.wait()
        print("[web] 종료 완료")


if __name__ == "__main__":
    main()
