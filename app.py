"""Hamburg Transit Radar als eigenes Fenster (kein Browser, kein fester Port nötig)."""
import os, sys, socket, threading, time, traceback, urllib.request, webbrowser
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
ERR = []

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

PORT = free_port()
URL = f"http://127.0.0.1:{PORT}"

def log(msg):
    with open("log.txt", "a", encoding="utf-8") as f: f.write(msg + "\n")

def serve():
    try:
        import uvicorn
        from backend.main import app
        uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
    except Exception:
        ERR.append(traceback.format_exc()); log(ERR[-1])

def page(title, body):
    return ("<body style='background:#0d1117;color:#e6edf3;font:16px system-ui;padding:40px'>"
            f"<h2>{title}</h2><pre style='white-space:pre-wrap;color:#9fb0c3'>{body}</pre></body>")

def wait_ready(timeout=60):
    t = time.time()
    while time.time() - t < timeout:
        if ERR: return False
        try:
            urllib.request.urlopen(URL + "/api/status", timeout=2); return True
        except Exception: time.sleep(0.5)
    return False

open("log.txt", "w").close()
threading.Thread(target=serve, daemon=True).start()
try:
    import webview
except Exception as e:
    log(f"pywebview fehlt ({e}) – nutze Browser")
    webview = None

if webview:
    win = webview.create_window("Hamburg Transit Radar", html=page("Starte …", "Server wird gestartet."), width=1300, height=820)
    def go():
        if wait_ready(): win.load_url(URL)
        else: win.load_html(page("Start fehlgeschlagen", (ERR[0] if ERR else "Server antwortet nicht.") + "\n\nDetails: log.txt"))
    webview.start(go)
else:
    if wait_ready(): webbrowser.open(URL); print("Läuft:", URL, "– Fenster offen lassen. Beenden mit Strg+C.")
    else: print("Start fehlgeschlagen:\n", ERR[0] if ERR else "Server antwortet nicht."); sys.exit(1)
    while True: time.sleep(1)
