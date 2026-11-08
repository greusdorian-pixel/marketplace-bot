"""Publica productos de productos.json en Facebook Marketplace usando Brave.

Uso:
  python publicar.py --login              Abre Brave para iniciar sesión en Facebook (solo la primera vez)
  python publicar.py                      Modo prueba: llena el formulario y espera antes de publicar
  python publicar.py --publicar --max 3   Publica de verdad hasta 3 productos pendientes
  python publicar.py --solo 07            Solo el producto 07
  python publicar.py --publicar --por-dia 4 --horario 09:00 21:00
                                          Publica 4 por día repartidos en ese horario, hasta acabar la cola
"""
import argparse, json, os, random, re, shutil, subprocess, time, urllib.request
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = os.path.dirname(os.path.abspath(__file__))


def buscar_brave():
    for nombre in ("brave-browser", "brave-browser-stable", "brave"):
        if ruta := shutil.which(nombre):
            return ruta
    if shutil.which("flatpak") and subprocess.run(["flatpak", "info", "com.brave.Browser"],
                                                  capture_output=True).returncode == 0:
        return "flatpak run com.brave.Browser"
    raise SystemExit("No encontré Brave. Instálalo (corre: bash ~/INSTALAR_LINUX.sh) y reintenta.")
PERFIL = os.path.join(BASE, "perfil-brave")
PUBLICADOS = os.path.join(BASE, "publicados.json")
LOGS = os.path.join(BASE, "logs")
URL_CREAR = "https://www.facebook.com/marketplace/create/item"
PUERTO = 9222


from contextlib import contextmanager


@contextmanager
def candado_brave(esperar=True):
    """Evita que el publicador, el gestor IA y el respondedor usen el Brave del bot a la vez.
    Con esperar=False lanza BlockingIOError si está ocupado."""
    import fcntl
    os.makedirs(LOGS, exist_ok=True)
    f = open(os.path.join(LOGS, ".brave.lock"), "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        if not esperar:
            f.close()
            raise
        print(f"[{datetime.now():%H:%M:%S}] Otra tarea del bot está usando Brave; espero a que termine...", flush=True)
        fcntl.flock(f, fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def puerto_abierto():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PUERTO}/json/version", timeout=1)
        return True
    except OSError:
        return False


def cerrar_brave_del_bot():
    """Cierra solo las ventanas de Brave que usan el perfil del bot (no toca el Brave normal)."""
    if subprocess.run(["pkill", "-f", f"--user-data-dir={PERFIL}"], capture_output=True).returncode == 0:
        time.sleep(2)


def abrir_brave(depuracion):
    """Abre Brave normal con el perfil del bot; con depuracion=True el bot puede conectarse."""
    if depuracion and puerto_abierto():
        return None
    cerrar_brave_del_bot()
    args = [*buscar_brave().split(), f"--user-data-dir={PERFIL}", "--no-first-run",
            "--renderer-process-limit=2", "--disable-background-networking", "--disk-cache-size=104857600"]
    if depuracion:
        args.append(f"--remote-debugging-port={PUERTO}")
    proc = subprocess.Popen(args + ["https://www.facebook.com/"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if depuracion:
        for _ in range(30):
            if puerto_abierto():
                break
            time.sleep(1)
        else:
            raise SystemExit("No se pudo conectar con Brave. Cierra todas las ventanas de Brave del bot y reintenta.")
    return proc


def ram_brave_mb():
    """Memoria aproximada del Brave del bot (suma de procesos)."""
    r = subprocess.run(["ps", "-eo", "rss,args"], capture_output=True, text=True).stdout.splitlines()
    return sum(int(l.split(None, 1)[0]) for l in r[1:] if f"--user-data-dir={PERFIL}" in l) // 1024


def una_pestana(ctx):
    """Deja una sola pestaña abierta en el Brave del bot (las demás gastan memoria)."""
    paginas = list(ctx.pages)
    for p in paginas[1:]:
        try:
            p.close()
        except Exception:
            pass
    return paginas[0] if paginas else ctx.new_page()


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def cargar(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def guardar_publicado(pid, titulo, verificar=False):
    hechos = cargar(PUBLICADOS, {})
    hechos[pid] = {"titulo": titulo, "fecha": datetime.now().isoformat(timespec="seconds")}
    if verificar:
        hechos[pid]["verificar"] = True
    tmp = PUBLICADOS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(hechos, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PUBLICADOS)  # nunca deja el archivo a medias


class SinSesion(Exception):
    """Facebook pide iniciar sesión: no tiene sentido seguir con la cola."""


def sin_sesion(page):
    if re.search(r"/login|/checkpoint|login\.php", page.url):
        return True
    return page.locator("input[name=pass], input[type=password]").count() > 0


def captura(page, pid):
    """Guarda captura de la pantalla visible (no la página entera) y deja solo las 15 más nuevas."""
    if sin_sesion(page):
        return None  # la pantalla de login puede mostrar la contraseña: no se guarda
    foto = os.path.join(LOGS, f"error_{pid}_{datetime.now():%m%d_%H%M%S}.png")
    try:
        page.screenshot(path=foto)
    except Exception:
        return None
    viejas = sorted((f for f in os.listdir(LOGS) if f.startswith("error_") and f.endswith(".png")),
                    key=lambda f: os.path.getmtime(os.path.join(LOGS, f)))
    for f in viejas[:-15]:
        os.remove(os.path.join(LOGS, f))
    return foto


def campo(page, etiqueta):
    """Busca un campo de texto por su etiqueta visible (español o inglés)."""
    rx = re.compile(etiqueta, re.I)
    loc = page.get_by_label(rx)
    if loc.count() == 0:
        loc = page.get_by_role("textbox", name=rx)
    return loc.first


def escribir(page, etiqueta, texto):
    c = campo(page, etiqueta)
    c.click()
    c.fill("")
    if len(str(texto)) > 60:  # textos largos se pegan de una vez
        c.fill(str(texto))
    else:
        c.type(str(texto), delay=random.randint(30, 80))
    page.wait_for_timeout(random.randint(400, 900))


def elegir(page, etiqueta, opcion):
    """Abre un desplegable por su etiqueta y elige la opción con ese texto."""
    page.get_by_label(re.compile(etiqueta, re.I)).first.click()
    page.wait_for_timeout(800)
    page.get_by_role("option", name=re.compile(re.escape(opcion), re.I)).or_(
        page.get_by_text(opcion, exact=True)).first.click()
    page.wait_for_timeout(random.randint(400, 900))


def boton(page, nombres):
    page.get_by_role("button", name=re.compile(nombres, re.I)).first.click()


def abrir_formulario(page):
    """Abre el formulario de crear artículo. A veces FB manda a la portada de Marketplace: reintenta."""
    subir = page.locator("input[type=file][accept*=image]").first
    for intento in range(3):
        page.goto(URL_CREAR)
        page.wait_for_load_state("domcontentloaded")
        try:
            subir.wait_for(state="attached", timeout=20000)
            page.wait_for_timeout(2000)
            return subir
        except PWTimeout:
            if sin_sesion(page):
                raise SinSesion()
            log(f"  Facebook no mostró el formulario (intento {intento + 1}/3), reintento...")
            page.wait_for_timeout(5000)
    raise RuntimeError("Facebook no abrió el formulario de publicación")


def llenar(page, p):
    subir = abrir_formulario(page)
    fotos = [os.path.join(BASE, f.replace("\\", "/")) for f in p["fotos"]][:10]
    faltan = [f for f in fotos if not os.path.isfile(f)]
    if faltan:
        raise RuntimeError(f"faltan fotos: {', '.join(os.path.relpath(f, BASE) for f in faltan)}")
    subir.set_input_files(fotos)
    log(f"  {len(fotos)} fotos cargadas")
    page.wait_for_timeout(3000)

    escribir(page, r"^(título|title)$", p["titulo"])
    escribir(page, r"^(precio|price)$", p["precio"])
    elegir(page, r"^(categoría|category)$", p["categoria"])
    elegir(page, r"^(estado|condition)$", p["estado"])

    # La descripción a veces está dentro de "Más detalles"
    if campo(page, r"^(descripción|description)$").count() == 0:
        try:
            boton(page, r"más detalles|more details")
            page.wait_for_timeout(800)
        except PWTimeout:
            pass
    escribir(page, r"^(descripción|description)$", p["descripcion"])


def confirmar_publicado(page):
    """Tras pulsar Publicar, espera a que FB salga del formulario. Devuelve False si no lo confirmó."""
    try:
        page.wait_for_url(lambda u: "/marketplace/create" not in u, timeout=45000)
        page.wait_for_timeout(3000)
        return True
    except PWTimeout:
        return False


def correr(a, lote, pausar=True):
    """Abre Brave, publica (o prueba) los productos del lote y lo cierra al terminar."""
    with candado_brave():
        _correr(a, lote, pausar)


def _correr(a, lote, pausar=True):
    brave = abrir_brave(depuracion=True)
    with sync_playwright() as pw:
        navegador = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PUERTO}")
        ctx = navegador.contexts[0]
        page = una_pestana(ctx)
        page.set_default_timeout(15000)
        page.goto("https://www.facebook.com/marketplace/")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3000)
        if sin_sesion(page):
            log("✖ No has iniciado sesión en Facebook. Usa «Iniciar sesión FB» en el panel y vuelve a publicar.")
            navegador.close()
            if brave:
                brave.terminate()
            raise SystemExit(2)

        for i, p in enumerate(lote):
            log(f"Producto {p['id']}: {p['titulo']} (${p['precio']})")
            seguir = True
            for intento in (1, 2):
                pulsado = False
                try:
                    llenar(page, p)
                    if a.publicar:
                        boton(page, r"^(siguiente|next)$")
                        page.wait_for_timeout(3000)
                        boton(page, r"^(publicar|publish)$")
                        pulsado = True
                        if confirmar_publicado(page):
                            guardar_publicado(p["id"], p["titulo"])
                            log("  Publicado ✔")
                        else:
                            # Se marca igual para no duplicarlo; el panel lo muestra como «verificar».
                            guardar_publicado(p["id"], p["titulo"], verificar=True)
                            foto = captura(page, p["id"])
                            log("  ⚠ Se pulsó Publicar pero Facebook no lo confirmó. Revisa en Marketplace > "
                                "Tu cuenta si salió; si no, desmárcalo en el panel." + (f" Captura: {os.path.relpath(foto, BASE)}" if foto else ""))
                    elif a.ui:
                        log("  MODO PRUEBA: formulario listo en Brave (no se publicó). Revísalo y cierra Brave.")
                        return  # deja Brave abierto con el formulario
                    else:
                        input("  MODO PRUEBA: revisa el formulario en Brave. Enter para seguir (no se publica)...")
                    break
                except SinSesion:
                    log("  ✖ Facebook pide iniciar sesión. Usa el botón «Iniciar sesión FB» del panel y vuelve a publicar.")
                    navegador.close()
                    if brave:
                        brave.terminate()
                    raise SystemExit(2)
                except Exception as e:
                    foto = captura(page, p["id"])
                    log(f"  ERROR (intento {intento}/2): {type(e).__name__}: {str(e).splitlines()[0]}"
                        + (f"  -> captura en {os.path.relpath(foto, BASE)}" if foto else ""))
                    if pulsado:
                        guardar_publicado(p["id"], p["titulo"], verificar=True)
                        log("  ⚠ El error fue después de pulsar Publicar: no reintento para no duplicar. Revisa si salió.")
                        break
                    if intento == 1:
                        log("  Reintentando este producto en 20 s...")
                        page.wait_for_timeout(20000)
                        continue
                    if not a.ui and input("  ¿Seguir con el siguiente? (s/n): ").strip().lower() != "s":
                        seguir = False
            if not seguir:
                break

            if pausar and a.publicar and i < len(lote) - 1:
                espera = random.uniform(*a.pausa) * 60
                log(f"  Esperando {espera/60:.1f} min antes del siguiente...")
                time.sleep(espera)

        navegador.close()
    if brave:
        brave.terminate()


def a_hora(texto, dia):
    h, m = map(int, texto.split(":"))
    return dia.replace(hour=h, minute=m, second=0, microsecond=0)


def publicados_hoy():
    """Cuenta lo que el bot publicó hoy (también en corridas anteriores); los marcados a mano no cuentan."""
    hoy = datetime.now().date().isoformat()
    return sum(1 for v in cargar(PUBLICADOS, {}).values()
               if v.get("fecha", "").startswith(hoy) and not v.get("manual"))


def esperar_hasta(cuando, motivo):
    log(f"  {motivo}. Próxima publicación: {cuando:%d/%m %H:%M}")
    while (falta := (cuando - datetime.now()).total_seconds()) > 0:
        time.sleep(min(falta, 30))


def programado(a, cola):
    """Publica a.por_dia productos por día, repartidos dentro del horario, hasta vaciar la cola."""
    desde, hasta = a.horario
    if a_hora(hasta, datetime.now()) <= a_hora(desde, datetime.now()):
        raise SystemExit("El horario debe terminar después de empezar (ej. 09:00 21:00).")
    cola = list(cola)
    dias = -(-len(cola) // a.por_dia)
    log(f"Modo diario: {a.por_dia} por día entre {desde} y {hasta}. {len(cola)} en cola (~{dias} día(s)).")
    while cola:
        ahora = datetime.now()
        inicio, fin = a_hora(desde, ahora), a_hora(hasta, ahora)
        azar = timedelta(minutes=random.uniform(0, 20))  # no arrancar siempre a la hora exacta
        if ahora < inicio:
            esperar_hasta(inicio + azar, "Fuera de horario")
            continue
        if ahora >= fin or publicados_hoy() >= a.por_dia:
            motivo = "Cupo del día completo" if publicados_hoy() >= a.por_dia else "Fuera de horario"
            esperar_hasta(inicio + timedelta(days=1) + azar, motivo)
            continue

        correr(a, [cola.pop(0)], pausar=False)
        if not cola:
            break
        quedan, ahora = a.por_dia - publicados_hoy(), datetime.now()
        if quedan <= 0 or ahora >= fin:
            continue  # la vuelta siguiente espera hasta mañana
        hueco = (fin - ahora) / quedan * random.uniform(0.6, 1.0)
        esperar_hasta(ahora + hueco, f"Quedan {quedan} hoy")
    log("Cola terminada.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true", help="solo abrir Brave para iniciar sesión")
    ap.add_argument("--publicar", action="store_true", help="publicar de verdad (sin esto es modo prueba)")
    ap.add_argument("--max", type=int, default=3, help="máximo de productos por corrida")
    ap.add_argument("--solo", help="id de un producto (ej. 07)")
    ap.add_argument("--ids", help="varios ids separados por coma (ej. 01,03,09)")
    ap.add_argument("--ui", action="store_true", help="lanzado desde el panel: sin preguntas por consola")
    ap.add_argument("--pausa", type=float, nargs=2, default=[3, 6], metavar=("MIN", "MAX"),
                    help="minutos de espera entre publicaciones")
    ap.add_argument("--por-dia", type=int, default=0, help="modo diario: cuántos publicar por día")
    ap.add_argument("--horario", nargs=2, default=["09:00", "21:00"], metavar=("DESDE", "HASTA"),
                    help="modo diario: franja horaria en la que publicar")
    a = ap.parse_args()

    productos = cargar(os.path.join(BASE, "productos.json"), [])
    hechos = cargar(PUBLICADOS, {})
    elegidos = set(a.ids.split(",")) if a.ids else {a.solo} if a.solo else None
    pendientes = [p for p in productos
                  if p["id"] not in hechos and p["precio"] is not None and (not elegidos or p["id"] in elegidos)]
    if not pendientes:
        log("No hay productos pendientes para esa selección.")
        return
    sin_precio = [p["id"] for p in productos if p["precio"] is None]
    if sin_precio:
        log(f"Sin precio (se saltan): {', '.join(sin_precio)}")
    os.makedirs(LOGS, exist_ok=True)

    if a.login:
        abrir_brave(depuracion=False)
        log("Inicia sesión en Facebook en la ventana de Brave. Cuando cargue tu inicio, cierra Brave.")
        return

    if a.publicar and a.por_dia:
        programado(a, pendientes)
    else:
        correr(a, pendientes[:a.max])
    log("Listo.")


if __name__ == "__main__":
    main()
