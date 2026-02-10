import os
import time
import traceback
import multiprocessing as mp

LOG_PATH = os.path.expanduser("~/mosaic_runtime.log")

def log(msg: str):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
        f.flush()

def main():
    log("=== Mosaic boot ===")
    log(f"pid={os.getpid()}")
    log(f"cwd={os.getcwd()}")
    log(f"__file__={__file__}")

    try:
        import threading
        import webbrowser
        import uvicorn
        from artified_backend.serve import app

        log("imports ok (uvicorn + app)")

        def _open():
            time.sleep(1.2)
            try:
                webbrowser.open("http://127.0.0.1:8000")
                log("browser opened")
            except Exception:
                log("browser open failed:\n" + traceback.format_exc())

        threading.Thread(target=_open, daemon=True).start()

        log("starting uvicorn...")
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=8000,
            log_level="info",
            access_log=True,
            # ❌ 不要 reload=True
        )

        log("uvicorn.run returned (unexpected)")
    except Exception:
        log("FATAL:\n" + traceback.format_exc())
        # 防止秒退看不到日志刷新
        time.sleep(2)

if __name__ == "__main__":
    mp.freeze_support()
    main()
