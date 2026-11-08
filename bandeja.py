"""Ícono junto al reloj para el bot de Marketplace. Arranca solo al entrar a la PC.

Mantiene encendido el panel, avisa por Telegram y muestra el estado:
  verde = todo bien · amarillo = trabajando · rojo = sin sesión de Facebook o panel caído
"""
import fcntl, json, os, subprocess, sys, threading, time, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
os.makedirs("logs", exist_ok=True)
_log = open(os.path.join(BASE, "logs", "bandeja.log"), "a", buffering=1, encoding="utf-8")
sys.stdout = sys.stderr = _log
print(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====")

_unico = open(os.path.join(BASE, "logs", ".bandeja.lock"), "w")
try:
    fcntl.flock(_unico, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print("Ya hay un ícono corriendo; salgo.")
    sys.exit()

import pystray  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
import telegram_bot as TG  # noqa: E402

PANEL = "http://127.0.0.1:8765"
COLORES = {"ok": "#5fb37a", "trabajando": "#f2b84b", "mal": "#e5604f"}
parar = threading.Event()
panel_proc = None


def hacer_icono(estado):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 62, 62), radius=16, fill="#1877f2")
    # bolsa de compras
    d.rounded_rectangle((16, 24, 48, 52), radius=5, fill="white")
    d.arc((22, 12, 42, 34), start=180, end=360, fill="white", width=4)
    d.ellipse((42, 42, 62, 62), fill=COLORES[estado], outline="#141413", width=3)
    return img


ICONOS = {k: hacer_icono(k) for k in COLORES}


def datos():
    try:
        with urllib.request.urlopen(PANEL + "/api/datos", timeout=5) as r:
            return json.load(r)
    except OSError:
        return None


def asegurar_panel():
    """Si el panel no responde, lo arranca (en segundo plano, sin ventana)."""
    global panel_proc
    if datos() is not None:
        return
    if panel_proc and panel_proc.poll() is None:
        return  # todavía arrancando
    print("Arrancando panel...")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    panel_proc = subprocess.Popen([sys.executable, "panel.py", "--sin-navegador"], cwd=BASE, env=env,
                                  stdout=open(os.path.join(BASE, "logs", "panel.log"), "a"),
                                  stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)


def estado_actual():
    d = datos()
    if d is None:
        return "mal", "Panel apagado (arrancando…)", None
    ia = d.get("ia", {})
    if d.get("corriendo") or ia.get("ocupado"):
        return "trabajando", "Trabajando: " + (d.get("tarea") or "revisión automática"), d
    if d.get("sesion") is False:
        return "mal", "Sin sesión de Facebook: inicia sesión en el panel", d
    auto = "gestor automático ON" if ia.get("auto") else "gestor automático APAGADO"
    return "ok", f"Encendido · {auto}", d


def vigilar(icono):
    ultimo, avisado_sesion = None, False
    while not parar.is_set():
        asegurar_panel()
        estado, texto, d = estado_actual()
        icono.icon = ICONOS[estado]
        icono.title = "Bot Marketplace\n" + texto
        if d is not None:
            sin_sesion = d.get("sesion") is False
            if sin_sesion and not avisado_sesion:
                TG.enviar("❌ Se cerró la sesión de Facebook del bot. Entra al panel y pulsa «Iniciar sesión FB».")
            avisado_sesion = sin_sesion
            # aviso cuando termina una publicación lanzada desde el panel
            if ultimo and ultimo.get("corriendo") and not d.get("corriendo") and "Gestor IA" not in (ultimo.get("tarea") or ""):
                hechos = [l for l in d.get("log", [])[-40:] if "Publicado ✔" in l or "ERROR" in l or "✖" in l or "⚠" in l]
                TG.enviar(f"📤 Terminó: {ultimo.get('tarea')}\n" + "\n".join(hechos[-15:] or ["(sin novedades)"]))
            ultimo = d
        parar.wait(5)


def ciclo_mensajes():
    """Cada pocos minutos (en horario) corre una vuelta del respondedor de mensajes."""
    import random
    from datetime import datetime
    parar.wait(60)
    while not parar.is_set():
        try:
            cfg = TG.ajustes_chat()
            desde, hasta = cfg.get("horario", ["07:00", "22:30"])
            ahora = datetime.now().strftime("%H:%M")
            listo = TG.conf().get("chat_id") and cfg.get("activo", True) and cfg.get("modo", "auto") != "pausa"
            if listo and desde <= ahora <= hasta:
                with open(os.path.join(BASE, "logs", "mensajes.log"), "a", encoding="utf-8") as out:
                    subprocess.run([sys.executable, "mensajes.py"], cwd=BASE, stdout=out, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, timeout=20 * 60,
                                   env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1"))
            espera = random.uniform(*cfg.get("cada_min", [4, 8])) * 60
        except Exception as e:
            print(f"[mensajes] {e}")
            espera = 300
        parar.wait(espera)


def abrir_panel(icono=None, item=None):
    subprocess.Popen(["bash", os.path.join(BASE, "abrir_panel.sh")])


def accion(ruta, cuerpo, aviso):
    def f(icono, item):
        try:
            req = urllib.request.Request(PANEL + ruta, data=json.dumps(cuerpo).encode())
            r = json.load(urllib.request.urlopen(req, timeout=10))
            icono.notify(aviso if r.get("ok") else (r.get("error") or "No se pudo"), "Bot Marketplace")
        except OSError:
            icono.notify("El panel no responde", "Bot Marketplace")
    return f


def es_auto(item):
    return subprocess.run(["systemctl", "--user", "is-enabled", "marketplace-ia.timer"],
                          capture_output=True, text=True).stdout.strip() == "enabled"


def cambiar_auto(icono, item):
    activo = not es_auto(item)
    subprocess.run(["systemctl", "--user", "enable" if activo else "disable", "--now", "marketplace-ia.timer"])
    icono.notify("Gestor automático " + ("encendido" if activo else "apagado"), "Bot Marketplace")


def salir(icono, item):
    parar.set()
    icono.stop()
    os._exit(0)  # el panel sigue vivo; se apaga con apagar_panel.sh


menu = pystray.Menu(
    pystray.MenuItem("Abrir panel", abrir_panel, default=True),
    pystray.Menu.SEPARATOR,
    pystray.MenuItem("Revisar anuncios ahora", accion("/api/ia/revisar", {"simular": False}, "Revisando anuncios…")),
    pystray.MenuItem("Simular revisión", accion("/api/ia/revisar", {"simular": True}, "Simulando…")),
    pystray.MenuItem("Gestor automático", cambiar_auto, checked=es_auto),
    pystray.Menu.SEPARATOR,
    pystray.MenuItem("Abrir carpeta", lambda i, it: subprocess.Popen(["xdg-open", BASE])),
    pystray.MenuItem("Quitar ícono", salir),
)

icono = pystray.Icon("marketplace-bot", ICONOS["trabajando"], "Bot Marketplace\nIniciando…", menu)
threading.Thread(target=vigilar, args=(icono,), daemon=True).start()
threading.Thread(target=TG.escuchar, args=(parar,), daemon=True).start()
threading.Thread(target=TG.vigilar_registro, args=(parar,), daemon=True).start()
threading.Thread(target=ciclo_mensajes, daemon=True).start()
TG.enviar("🟢 Bot de Marketplace encendido.")
icono.run()
