"""Gestor autónomo de publicaciones de Marketplace (con IA de Groq, gratis).

Revisa «Tus publicaciones» en Facebook y, solo para los productos del bot (productos.json):
  1. Renueva los que ya pasaron N días (opción oficial de Facebook).
  2. Si un anuncio es viejo y casi nadie lo abre, publica una versión nueva con otro título y
     otra descripción escritos por la IA, y luego borra el viejo (con límite por día).
Los anuncios que no son del bot nunca se tocan.

Uso:
  python revisar.py --simular     Solo mira y dice qué haría (no cambia nada)
  python revisar.py               Revisa y actúa
Ajustes en config_ia.json (se crea solo).
"""
import argparse, json, os, random, re, sys, time, unicodedata, urllib.request
from datetime import date, datetime, timedelta

import ia
import publicar as P
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = P.BASE
CONFIG = os.path.join(BASE, "config_ia.json")
HISTORIAL = os.path.join(BASE, "historial_ia.json")
URL_VENTAS = "https://www.facebook.com/marketplace/you/selling"

AJUSTES_BASE = {
    "modelo": "openai/gpt-oss-120b",
    "groq_api_key": "",            # vacío = usa la variable de entorno GROQ_API_KEY
    "dias_renovar": 7,             # renovar si pasaron estos días desde la última vez
    "recrear": True,               # permitir borrar y volver a publicar con otro título
    "dias_sin_clics": 4,           # con 0 clics, recrear desde estos días
    "dias_recrear": 21,            # con pocos clics, recrear desde estos días...
    "clics_max_recrear": 15,       # ...y con menos de estos clics
    "max_recrear_por_dia": 3,
    "max_renovar_por_vez": 10,
    "pausa_min": [2, 5],           # minutos de espera entre acciones
}


def log(msg):
    P.log(msg)


def cargar(path, default):
    return P.cargar(path, default)


def guardar(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def ajustes():
    a = dict(AJUSTES_BASE)
    a.update(cargar(CONFIG, {}))
    if not os.path.exists(CONFIG):
        guardar(CONFIG, {k: v for k, v in a.items() if k != "groq_api_key"} | {"groq_api_key": ""})
    if not a["groq_api_key"]:
        a["groq_api_key"] = os.environ.get("GROQ_API_KEY", "")
    return a


def norm(t):
    """Título comparable: sin tildes, sin símbolos, minúsculas (FB cambia ½ por 1⁄2, etc.)."""
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "", t)


# ---------------------------------------------------------------- IA (Groq)

def ia_variante(cfg, p, titulos_usados):
    """Pide a la IA un título y una descripción nuevos para el producto, sin inventar datos."""
    if not cfg["groq_api_key"]:
        raise RuntimeError("No hay clave de Groq (pon groq_api_key en config_ia.json)")
    instrucciones = (
        f"Eres experto en ventas por Facebook Marketplace en {ia.negocio()['ciudad']}, {ia.negocio()['pais']}. Reescribe el anuncio para "
        f"que parezca una publicación nueva y atraiga más clics. Reglas: español de {ia.negocio()['pais']}; NO inventes "
        "datos (marca, medidas, potencia, modelo y estado deben ser los mismos); el título debe ser distinto "
        "a todos los usados antes, de 40 a 90 caracteres, con palabras que la gente busca (qué es, para qué "
        "sirve, marca, medida); sin emojis en el título, sin MAYÚSCULAS completas, sin la palabra 'remate' en "
        "el título. En la descripción cambia el orden y la redacción, máximo 2 emojis, y copia EXACTAMENTE "
        "la línea que empieza con 'Precio en tienda' si existe. No escribas el precio de venta en la descripción. "
        "Incluye 'Remate por liquidación. Precio negociable.' y termina con una invitación a escribir. "
        'Responde solo JSON: {"titulo": "...", "descripcion": "..."}')
    datos = {"titulo_actual": p["titulo"], "titulos_usados_antes": titulos_usados,
             "precio_usd": p["precio"], "estado": p["estado"], "descripcion_actual": p["descripcion"]}
    cuerpo = json.dumps({"model": cfg["modelo"], "temperature": 0.9,
                         "response_format": {"type": "json_object"},
                         "messages": [{"role": "system", "content": instrucciones},
                                      {"role": "user", "content": json.dumps(datos, ensure_ascii=False)}]}).encode()
    req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", data=cuerpo, headers={
        "Authorization": f"Bearer {cfg['groq_api_key']}", "Content-Type": "application/json",
        "User-Agent": "marketplace-bot"})
    for intento in range(3):
        try:
            r = json.load(urllib.request.urlopen(req, timeout=60))
            v = json.loads(r["choices"][0]["message"]["content"])
            titulo, desc = v["titulo"].strip().strip('"'), v["descripcion"].strip()
            break
        except Exception as e:
            if intento == 2:
                raise RuntimeError(f"La IA no respondió bien: {e}")
            time.sleep(5)
    # Controles: si la IA se salió de las reglas, se corrige o se usa lo original.
    titulo = titulo[:99]
    if len(titulo) < 15 or norm(titulo) in {norm(t) for t in titulos_usados + [p["titulo"]]}:
        raise RuntimeError(f"la IA dio un título repetido o muy corto: {titulo!r}")
    linea_precio = next((l for l in p["descripcion"].splitlines() if l.startswith("Precio en tienda")), None)
    if linea_precio and linea_precio not in desc:
        desc = desc.rstrip() + "\n\n" + linea_precio
    if len(desc) < 40:
        desc = p["descripcion"]
    return titulo, desc


# ---------------------------------------------------------------- Facebook

RX_TARJETA = re.compile(r"^(?P<titulo>.+?), (?P<precio>[\d.,]+)\s*\$, (?:precio original [\d.,]+\s*\$, )?"
                        r"(?P<estado>[^,]+), Publicado el (?P<dia>\d{1,2})/(?P<mes>\d{1,2}).*?"
                        r"(?P<clics>\d+) clics? en la publicación", re.S)


def leer_publicaciones(page):
    page.goto(URL_VENTAS, wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    if P.sin_sesion(page):
        raise P.SinSesion()
    vistas, quietos = 0, 0
    for _ in range(40):  # baja hasta que no aparezcan más anuncios en 3 intentos seguidos
        page.keyboard.press("End")
        page.mouse.wheel(0, 5000)
        page.wait_for_timeout(2000)
        n = page.locator("[role=button][aria-label*='clic']").count()
        quietos = quietos + 1 if n == vistas else 0
        if quietos >= 3:
            break
        vistas = n
    etiquetas = page.locator("[role=button][aria-label*='clic']").evaluate_all(
        "e => e.map(x => x.getAttribute('aria-label'))")
    hoy, salida = date.today(), []
    for et in etiquetas:
        m = RX_TARJETA.match(et.replace("\xa0", " "))
        if not m:
            continue
        f = date(hoy.year, int(m["mes"]), int(m["dia"]))
        if f > hoy:
            f = f.replace(year=hoy.year - 1)
        salida.append({"titulo": m["titulo"], "precio": int(float(m["precio"].replace(".", "").replace(",", "."))),
                       "estado": m["estado"].strip(), "fecha": f.isoformat(),
                       "dias": (hoy - f).days, "clics": int(m["clics"])})
    return salida


def abrir_menu(page, titulo):
    b = page.locator(f'[aria-label="Más opciones de {titulo}"]').first
    # Tras renovar/borrar, FB recarga la lista y solo trae los primeros: bajar hasta que aparezca.
    for _ in range(25):
        if b.count():
            break
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(1200)
    else:
        page.evaluate("window.scrollTo(0, 0)")
        raise RuntimeError(f"no encontré «{titulo}» en la lista")
    b.scroll_into_view_if_needed(timeout=10000)
    b.click()
    page.wait_for_timeout(1500)
    return [t.strip() for t in page.get_by_role("menuitem").all_inner_texts()]


def renovar(page, titulo):
    opciones = abrir_menu(page, titulo)
    if "Renovar publicación" not in opciones:
        page.keyboard.press("Escape")
        return False
    page.get_by_role("menuitem", name="Renovar publicación").click()
    page.wait_for_timeout(2500)
    dialogo = page.get_by_role("dialog").get_by_role("button", name=re.compile(r"^renovar", re.I))
    if dialogo.count():
        dialogo.first.click()
        page.wait_for_timeout(2500)
    return True


def eliminar(page, titulo):
    opciones = abrir_menu(page, titulo)
    if "Eliminar publicación" not in opciones:
        page.keyboard.press("Escape")
        raise RuntimeError("el menú no ofrece «Eliminar publicación»")
    page.get_by_role("menuitem", name="Eliminar publicación").click()
    page.wait_for_timeout(2000)
    page.get_by_role("dialog").get_by_role("button", name=re.compile(r"^(eliminar|borrar)$", re.I)).first.click()
    page.wait_for_timeout(3000)
    # A veces FB pregunta si se vendió: se responde sin marcarlo como vendido.
    for nombre in (r"prefiero no responder", r"no,? (no )?lo vend", r"omitir|ahora no|cerrar"):
        btn = page.get_by_role("dialog").get_by_role("button", name=re.compile(nombre, re.I))
        if btn.count():
            btn.first.click()
            page.wait_for_timeout(1500)
            break


# ---------------------------------------------------------------- lógica

def plan(cfg, publicaciones, productos, publicados, hist):
    """Decide qué hacer con cada anuncio del bot. No toca nada todavía."""
    por_titulo = {}
    for pid, info in publicados.items():
        prod = productos.get(pid)
        if prod:
            por_titulo[norm(info.get("titulo_fb") or prod["titulo"])] = pid
            por_titulo.setdefault(norm(prod["titulo"]), pid)
    hoy = date.today().isoformat()
    recreados_hoy = sum(1 for h in hist.get("acciones", []) if h["accion"] == "recrear" and h["fecha"].startswith(hoy))
    acciones, candidatos, ajenos, vistos = [], [], [], set()
    for pub in publicaciones:
        pid = por_titulo.get(norm(pub["titulo"]))
        if not pid:
            ajenos.append(pub["titulo"])
            continue
        if pid in vistos or pub["estado"].lower() not in ("disponible", "activo"):
            continue
        vistos.add(pid)
        h = hist.get("productos", {}).get(pid, {})
        dias_desde = (date.today() - date.fromisoformat(h.get("ultima_accion", pub["fecha"])[:10])).days
        edad = (date.today() - date.fromisoformat(h.get("recreado", pub["fecha"])[:10])).days
        # los clics que muestra FB son de los últimos 14 días
        sin_clics = pub["clics"] == 0 and edad >= cfg["dias_sin_clics"]
        pocos = edad >= cfg["dias_recrear"] and pub["clics"] < cfg["clics_max_recrear"]
        if cfg["recrear"] and (sin_clics or pocos):
            candidatos.append({"accion": "recrear", "pid": pid, "pub": pub, "edad": edad,
                               "renovable": dias_desde >= cfg["dias_renovar"]})
        elif dias_desde >= cfg["dias_renovar"]:
            acciones.append({"accion": "renovar", "pid": pid, "pub": pub})
    # Primero los que tienen 0 clics, luego los de menos clics y más viejos.
    candidatos.sort(key=lambda c: (c["pub"]["clics"], -c["edad"]))
    cupo = max(0, cfg["max_recrear_por_dia"] - recreados_hoy)
    recrear, sobran = candidatos[:cupo], candidatos[cupo:]
    # Los que no entran en el cupo de hoy al menos se renuevan.
    acciones += [{"accion": "renovar", "pid": c["pid"], "pub": c["pub"]} for c in sobran if c["renovable"]]
    return recrear + acciones[:cfg["max_renovar_por_vez"]], ajenos


def registrar(hist, pid, accion, detalle):
    ahora = datetime.now().isoformat(timespec="seconds")
    hist.setdefault("acciones", []).append({"fecha": ahora, "pid": pid, "accion": accion, **detalle})
    hist["acciones"] = hist["acciones"][-300:]
    h = hist.setdefault("productos", {}).setdefault(pid, {})
    h.update(ultima_accion=ahora, accion=accion)
    if accion == "recrear":
        h["recreado"] = ahora
    guardar(HISTORIAL, hist)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--simular", action="store_true", help="solo decir qué haría")
    a = ap.parse_args()
    cfg = ajustes()
    productos = {p["id"]: p for p in cargar(os.path.join(BASE, "productos.json"), [])}
    hist = cargar(HISTORIAL, {})
    os.makedirs(P.LOGS, exist_ok=True)

    with P.candado_brave():
        brave = P.abrir_brave(depuracion=True)
        try:
            with sync_playwright() as pw:
                nav = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{P.PUERTO}")
                ctx = nav.contexts[0]
                page = P.una_pestana(ctx)
                page.set_default_timeout(15000)
                try:
                    pubs = leer_publicaciones(page)
                except P.SinSesion:
                    log("✖ No hay sesión de Facebook. Usa «Iniciar sesión FB» en el panel.")
                    raise SystemExit(2)
                publicados = cargar(P.PUBLICADOS, {})
                acciones, ajenos = plan(cfg, pubs, productos, publicados, hist)
                hist["ultima_revision"] = {"fecha": datetime.now().isoformat(timespec="seconds"),
                                           "anuncios": pubs, "ajenos": ajenos}
                guardar(HISTORIAL, hist)
                log(f"Revisé {len(pubs)} anuncios ({len(pubs) - len(ajenos)} del bot; "
                    f"{len(ajenos)} tuyos de otras cosas, esos no se tocan).")
                if not acciones:
                    log("Nada que hacer por ahora: todo está al día.")
                for i, ac in enumerate(acciones):
                    pid, pub = ac["pid"], ac["pub"]
                    prod = dict(productos[pid])
                    desc_ = f"{pid} «{pub['titulo']}» ({pub['dias']} días, {pub['clics']} clics)"
                    if a.simular:
                        log(f"[SIMULACIÓN] {ac['accion'].upper()}: {desc_}")
                        continue
                    try:
                        if ac["accion"] == "renovar":
                            log(f"Renovando {desc_}")
                            if renovar(page, pub["titulo"]):
                                registrar(hist, pid, "renovar", {"titulo": pub["titulo"], "clics": pub["clics"]})
                                log("  Renovado ✔")
                            else:
                                log("  Facebook todavía no deja renovarlo; se intenta otro día.")
                        else:
                            usados = hist.get("productos", {}).get(pid, {}).get("titulos", []) + [prod["titulo"]]
                            titulo, descripcion = ia_variante(cfg, prod | {"titulo": pub["titulo"]}, usados)
                            log(f"Recreando {desc_}\n  Título nuevo (IA): {titulo}")
                            prod.update(titulo=titulo, descripcion=descripcion)
                            P.llenar(page, prod)
                            P.boton(page, r"^(siguiente|next)$")
                            page.wait_for_timeout(3000)
                            P.boton(page, r"^(publicar|publish)$")
                            if not P.confirmar_publicado(page):
                                log("  ⚠ Facebook no confirmó el anuncio nuevo: NO borro el viejo. Revísalo.")
                                registrar(hist, pid, "recrear_dudoso", {"titulo_nuevo": titulo})
                                continue
                            log("  Nuevo publicado ✔. Borrando el anterior...")
                            publicados[pid] = publicados.get(pid, {}) | {"titulo_fb": titulo}
                            guardar(P.PUBLICADOS, publicados)
                            page.goto(URL_VENTAS, wait_until="domcontentloaded")
                            page.wait_for_timeout(6000)
                            eliminar(page, pub["titulo"])
                            h = hist.setdefault("productos", {}).setdefault(pid, {})
                            h["titulos"] = (h.get("titulos", []) + [pub["titulo"]])[-10:]
                            registrar(hist, pid, "recrear", {"titulo_viejo": pub["titulo"], "titulo_nuevo": titulo,
                                                             "clics_viejo": pub["clics"]})
                            log("  Anterior borrado ✔")
                    except P.SinSesion:
                        log("✖ Se perdió la sesión de Facebook. Paro.")
                        raise SystemExit(2)
                    except Exception as e:
                        foto = P.captura(page, pid)
                        log(f"  ERROR: {type(e).__name__}: {str(e).splitlines()[0]}"
                            + (f" -> {os.path.relpath(foto, BASE)}" if foto else ""))
                        page.keyboard.press("Escape")
                    if i < len(acciones) - 1:
                        espera = random.uniform(*cfg["pausa_min"]) * 60
                        log(f"  Espero {espera / 60:.1f} min...")
                        time.sleep(espera)
                        page.goto(URL_VENTAS, wait_until="domcontentloaded")
                        page.wait_for_timeout(6000)
                nav.close()
        finally:
            if brave:
                brave.terminate()
    log("Revisión terminada.")


if __name__ == "__main__":
    main()
