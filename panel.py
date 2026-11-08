"""Panel web local para elegir y publicar productos en Marketplace.

Uso: python panel.py  -> abre http://127.0.0.1:8765
"""
import hashlib, hmac, json, mimetypes, os, secrets, subprocess, sys, threading, time, webbrowser
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, unquote, urlparse

BASE = os.path.dirname(os.path.abspath(__file__))
PRODUCTOS = os.path.join(BASE, "productos.json")
PUBLICADOS = os.path.join(BASE, "publicados.json")
NUEVOS = os.path.join(BASE, "nuevos")
CLAVE_ARCHIVO = os.path.join(BASE, "clave_panel.txt")
PUERTO_PANEL = 8765


def cargar_clave():
    """Clave para entrar desde fuera (celular vía túnel). Se crea sola la primera vez."""
    if not os.path.exists(CLAVE_ARCHIVO):
        with open(CLAVE_ARCHIVO, "w", encoding="utf-8") as f:
            f.write(secrets.token_urlsafe(6))
    with open(CLAVE_ARCHIVO, encoding="utf-8") as f:
        return f.read().strip()


CLAVE = cargar_clave()
TOKEN = hashlib.sha256(f"panel:{CLAVE}".encode()).hexdigest()  # va en la cookie; sobrevive reinicios

PAGINA_ENTRAR = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Panel Marketplace</title>
<style>body{font-family:system-ui,sans-serif;background:#111;color:#eee;display:grid;place-items:center;
min-height:100vh;margin:0}form{display:grid;gap:12px;padding:24px;width:min(320px,90vw)}
input,button{font-size:18px;padding:12px;border-radius:10px;border:1px solid #444;background:#222;color:#eee}
button{background:#1877f2;border:0;font-weight:600}p{color:#f66;margin:0}</style></head><body>
<form method="post" action="/entrar"><h2>Panel Marketplace</h2>{error}
<input name="clave" type="password" placeholder="Clave" autofocus autocomplete="current-password">
<button>Entrar</button></form></body></html>"""

estado = {"proc": None, "log": [], "tarea": ""}
_sesion = {"t": 0, "ok": None}


def sesion_fb():
    """¿Hay sesión de Facebook en el perfil del bot? Mira si existe la cookie c_user (sin leer su valor)."""
    import sqlite3
    if time.time() - _sesion["t"] < 30:
        return _sesion["ok"]
    db = os.path.join(BASE, "perfil-brave", "Default", "Cookies")
    ok = None
    if os.path.exists(db):
        try:
            con = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
            ok = con.execute("SELECT COUNT(*) FROM cookies WHERE host_key LIKE '%facebook.com' AND name='c_user' "
                             "AND (expires_utc=0 OR expires_utc > (strftime('%s','now')+11644473600)*1000000)"
                             ).fetchone()[0] > 0
            con.close()
        except sqlite3.Error:
            ok = None
    else:
        ok = False
    _sesion.update(t=time.time(), ok=ok)
    return ok
candado = threading.Lock()


def leer(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def escribir_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)  # nunca deja el archivo a medias


def agregar_log(linea):
    with candado:
        estado["log"].append(linea.rstrip())
        estado["log"] = estado["log"][-500:]


def corriendo():
    return estado["proc"] is not None and estado["proc"].poll() is None


IA_LOG = os.path.join(BASE, "logs", "ia.log")


def systemctl(*args):
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)


def estado_ia():
    auto = systemctl("is-enabled", "marketplace-ia.timer").stdout.strip() == "enabled"
    proxima = ""
    if auto:
        us = systemctl("show", "marketplace-ia.timer", "-p", "NextElapseUSecRealtime", "--value").stdout.strip()
        proxima = us
    lineas = []
    if os.path.exists(IA_LOG):
        with open(IA_LOG, encoding="utf-8", errors="replace") as f:
            lineas = f.read().splitlines()[-60:]
    return {"auto": auto, "proxima": proxima, "log": lineas,
            "ocupado": systemctl("is-active", "marketplace-ia.service").stdout.strip() == "activating"}


def lanzar(args, tarea, script="publicar.py"):
    if corriendo():
        return False
    agregar_log(f"[{datetime.now():%H:%M:%S}] ▶ {tarea}")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    proc = subprocess.Popen([sys.executable, os.path.join(BASE, script), *args], cwd=BASE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            text=True, encoding="utf-8", errors="replace", env=env)
    estado["proc"], estado["tarea"] = proc, tarea

    def leer_salida():
        ia = open(IA_LOG, "a", encoding="utf-8") if script == "revisar.py" else None
        if ia:
            ia.write(f"=== {tarea} {datetime.now():%d/%m %H:%M} ===\n")
        for linea in proc.stdout:
            agregar_log(linea)
            if ia:
                ia.write(linea)
                ia.flush()
        if ia:
            ia.close()
        agregar_log(f"[{datetime.now():%H:%M:%S}] ■ Terminó ({tarea})")

    threading.Thread(target=leer_salida, daemon=True).start()
    return True


class Panel(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def responder(self, data, code=200, tipo="application/json"):
        cuerpo = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", tipo + ("; charset=utf-8" if tipo.startswith(("text", "application/json")) else ""))
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def autorizado(self):
        # Lo que llega por el túnel de Cloudflare trae esta cabecera; lo local (la PC) no pide clave.
        if "Cf-Connecting-IP" not in self.headers:
            return True
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return "sesion" in cookie and hmac.compare_digest(cookie["sesion"].value, TOKEN)

    def redirigir(self, destino, cookie=None):
        self.send_response(303)
        self.send_header("Location", destino)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def pagina_entrar(self, error=False):
        html = PAGINA_ENTRAR.replace("{error}", "<p>Clave incorrecta</p>" if error else "")
        self.responder(html.encode("utf-8"), tipo="text/html")

    def archivo(self, rel):
        ruta = os.path.normpath(os.path.join(BASE, rel))
        if not ruta.startswith(BASE) or not os.path.isfile(ruta):
            return self.responder({"error": "no existe"}, 404)
        with open(ruta, "rb") as f:
            self.responder(f.read(), tipo=mimetypes.guess_type(ruta)[0] or "application/octet-stream")

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/entrar":
            return self.pagina_entrar("error" in url.query)
        if not self.autorizado():
            if url.path.startswith("/api/"):
                return self.responder({"error": "Sesión vencida, recarga la página"}, 401)
            return self.redirigir("/entrar")
        if url.path == "/":
            return self.archivo("panel.html")
        if url.path.startswith(("/fotos/", "/logs/")):
            return self.archivo(unquote(url.path.lstrip("/")))
        if url.path == "/api/datos":
            nuevos = [f for f in os.listdir(NUEVOS) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))] \
                if os.path.isdir(NUEVOS) else []
            with candado:
                log = list(estado["log"])
            return self.responder({"productos": leer(PRODUCTOS, []), "publicados": leer(PUBLICADOS, {}),
                                   "corriendo": corriendo(), "tarea": estado["tarea"], "log": log,
                                   "nuevos": len(nuevos), "sesion": sesion_fb(), "ia": estado_ia()})
        self.responder({"error": "no existe"}, 404)

    def do_POST(self):
        largo = int(self.headers.get("Content-Length", 0))
        cuerpo = self.rfile.read(largo)
        ruta = urlparse(self.path).path

        if ruta == "/entrar":
            clave = parse_qs(cuerpo.decode("utf-8", "replace")).get("clave", [""])[0].strip()
            if hmac.compare_digest(clave.encode(), CLAVE.encode()):
                return self.redirigir("/", f"sesion={TOKEN}; Max-Age=2592000; Path=/; HttpOnly; Secure; SameSite=Lax")
            time.sleep(2)  # frena a quien pruebe claves al azar
            return self.redirigir("/entrar?error=1")
        if not self.autorizado():
            return self.responder({"error": "Sesión vencida, recarga la página"}, 401)
        datos = json.loads(cuerpo or b"{}")

        if ruta == "/api/guardar":
            productos = leer(PRODUCTOS, [])
            for p in productos:
                if p["id"] == datos["id"]:
                    for k in ("titulo", "descripcion", "estado", "categoria"):
                        if k in datos:
                            p[k] = datos[k]
                    if "precio" in datos:
                        p["precio"] = int(datos["precio"]) if str(datos["precio"]).strip() else None
            escribir_json(PRODUCTOS, productos)
            return self.responder({"ok": True})

        if ruta == "/api/marcar":
            hechos = leer(PUBLICADOS, {})
            if datos.get("publicado"):
                hechos[datos["id"]] = {"titulo": datos.get("titulo", ""), "fecha": datetime.now().isoformat(timespec="seconds"),
                                       "manual": True}
            else:
                hechos.pop(datos["id"], None)
            escribir_json(PUBLICADOS, hechos)
            return self.responder({"ok": True})

        if ruta == "/api/confirmar":
            hechos = leer(PUBLICADOS, {})
            if datos.get("id") in hechos:
                hechos[datos["id"]].pop("verificar", None)
                escribir_json(PUBLICADOS, hechos)
            return self.responder({"ok": True})

        if ruta == "/api/ejecutar":
            ids = [i for i in datos.get("ids", []) if i]
            if not ids:
                return self.responder({"ok": False, "error": "Selecciona al menos un producto"}, 400)
            if datos.get("modo") == "publicar" and datos.get("ritmo") == "diario":
                por_dia, desde, hasta = int(datos.get("porDia", 3)), datos.get("desde", "09:00"), datos.get("hasta", "21:00")
                if por_dia < 1 or hasta <= desde:
                    return self.responder({"ok": False, "error": "Revisa la cantidad por día y el horario"}, 400)
                args = ["--ui", "--publicar", "--ids", ",".join(ids), "--por-dia", str(por_dia),
                        "--horario", desde, hasta]
                tarea = f"Publicar {len(ids)} producto(s), {por_dia} por día ({desde}–{hasta})"
            elif datos.get("modo") == "publicar":
                pmin, pmax = datos.get("pausa", [3, 6])
                args = ["--ui", "--publicar", "--ids", ",".join(ids), "--max", str(len(ids)),
                        "--pausa", str(pmin), str(pmax)]
                tarea = f"Publicar {len(ids)} producto(s): {', '.join(ids)}"
            else:
                args = ["--ui", "--ids", ids[0], "--max", "1"]
                tarea = f"Prueba (sin publicar): {ids[0]}"
            ok = lanzar(args, tarea)
            return self.responder({"ok": ok, "error": None if ok else "Ya hay una tarea en curso"})

        if ruta == "/api/ia/revisar":
            simular = bool(datos.get("simular"))
            ok = lanzar(["--simular"] if simular else [], "Gestor IA: " + ("simulación" if simular else "revisar y actuar"),
                        script="revisar.py")
            return self.responder({"ok": ok, "error": None if ok else "Ya hay una tarea en curso"})

        if ruta == "/api/ia/auto":
            r = systemctl("enable" if datos.get("activo") else "disable", "--now", "marketplace-ia.timer")
            return self.responder({"ok": r.returncode == 0, "error": r.stderr.strip() or None})

        if ruta == "/api/login":
            _sesion["t"] = 0
            ok = lanzar(["--login"], "Abrir Brave para iniciar sesión")
            return self.responder({"ok": ok})

        if ruta == "/api/detener":
            if corriendo():
                estado["proc"].terminate()
                agregar_log(f"[{datetime.now():%H:%M:%S}] ■ Detenido por el usuario")
            return self.responder({"ok": True})

        if ruta == "/api/abrir_nuevos":
            os.makedirs(NUEVOS, exist_ok=True)
            subprocess.Popen(["xdg-open", NUEVOS], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return self.responder({"ok": True})

        self.responder({"error": "no existe"}, 404)


if __name__ == "__main__":
    os.makedirs(NUEVOS, exist_ok=True)
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO_PANEL), Panel)
    url = f"http://127.0.0.1:{PUERTO_PANEL}"
    print(f"Panel en {url}  (cierra esta ventana para apagarlo)")
    if "--sin-navegador" not in sys.argv:
        threading.Timer(1, lambda: webbrowser.open(url)).start()
    servidor.serve_forever()
