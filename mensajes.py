"""Responde los mensajes de compradores de Marketplace con IA (Groq) y avisa por Telegram.

Una «vuelta»: abre la bandeja de Marketplace en el Brave del bot, busca chats de productos del bot
donde el último mensaje es del comprador, lee la conversación, pide respuesta a la IA, la escribe
y manda copia/avisos por Telegram. También envía lo que el dueño contestó desde Telegram.

Uso:
  python mensajes.py            una vuelta
  python mensajes.py --simular  lee y muestra qué respondería, sin escribir nada
"""
import argparse, json, os, random, re, time, unicodedata
from datetime import datetime

import ia
import publicar as P
import telegram_bot as TG
from playwright.sync_api import sync_playwright

BASE = P.BASE
CHATS = os.path.join(BASE, "chats.json")
CONFIG = os.path.join(BASE, "config_ia.json")
URL_BANDEJA = "https://www.facebook.com/marketplace/inbox/"
NUMERO_DUENO = ia.negocio()["telefono_dueno"]

AJUSTES_CHAT = {
    "activo": True,
    "modo": "auto",              # auto = responde solo · aprobar = te pide OK por Telegram · pausa
    "copiar_a_telegram": True,   # mandar copia de cada respuesta
    "rebaja_max": 10,            # cuánto puede bajar como máximo (USD)
    "rebaja_max_pct_baratos": 25,  # en productos de menos de $30, máximo este % de rebaja
    "max_por_vuelta": 3,
    "cada_min": [4, 8],
    "horario": ["07:00", "22:30"],
}


def log(m):
    P.log(m)


def cargar(path, d):
    return P.cargar(path, d)


def guardar(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def ajustes():
    c = cargar(CONFIG, {})
    a = dict(AJUSTES_CHAT)
    a.update(c.get("chat", {}))
    if "chat" not in c:
        c["chat"] = a
        guardar(CONFIG, c)
    return a


def norm(t):
    t = unicodedata.normalize("NFKD", t)
    return re.sub(r"[^a-z0-9]+", "", "".join(ch for ch in t if not unicodedata.combining(ch)).lower())


# ------------------------------------------------------------------ productos y precios

def catalogo():
    """{titulo normalizado: producto} con el precio real de Facebook si se conoce."""
    productos = {p["id"]: p for p in cargar(os.path.join(BASE, "productos.json"), [])}
    publicados = cargar(P.PUBLICADOS, {})
    precios_fb = {norm(a["titulo"]): a.get("precio") for a in
                  cargar(os.path.join(BASE, "historial_ia.json"), {}).get("ultima_revision", {}).get("anuncios", [])}
    salida = {}
    for pid, p in productos.items():
        titulos = {p["titulo"], publicados.get(pid, {}).get("titulo_fb") or p["titulo"]}
        for t in titulos:
            q = dict(p)
            q["precio_fb"] = precios_fb.get(norm(t)) or next((precios_fb.get(norm(x)) for x in titulos
                                                              if precios_fb.get(norm(x))), None) or p["precio"]
            salida[norm(t)] = q
    return salida


def precio_minimo(p, cfg):
    if p.get("precio_minimo"):
        return int(p["precio_minimo"])
    precio = int(p.get("precio_fb") or p["precio"])
    rebaja = cfg["rebaja_max"]
    if precio < 30:
        rebaja = min(rebaja, round(precio * cfg["rebaja_max_pct_baratos"] / 100))
    return max(1, precio - rebaja)


# ------------------------------------------------------------------ IA

def ejemplos_reales():
    try:
        with open(os.path.join(BASE, "estilo_conversaciones.json"), encoding="utf-8") as f:
            pares = json.load(f)
        return "\n".join(f"Comprador: {x['comprador']}\nDueño: {x['dueno']}" for x in pares[:15])
    except (OSError, ValueError):
        return ""


def instrucciones(p, minimo, otros):
    n = ia.negocio()
    return f"""Eres el dueño de un negocio de remate en {n['ciudad']} y respondes chats de Facebook Marketplace desde el celular.
Tienes que sonar EXACTAMENTE como él. Estas son conversaciones reales suyas, copia su forma de hablar:

{ejemplos_reales()}

Cómo escribe: mensajes cortitos (2 a 10 palabras), varios mensajes seguidos en vez de uno largo (sepáralos con
salto de línea), trata de usted con confianza y a veces «pana», casi sin tildes, sin «¡» ni «¿» de apertura,
sin emojis, sin punto final, precio como «30$». Nada de frases de atención al cliente.

LO MÁS IMPORTANTE: responde a lo ÚLTIMO que dijo el comprador, como en una conversación de verdad.
- Si preguntó algo, contesta eso primero.
- No repitas preguntas que ya contestó (si ya dijo su sector, no lo vuelvas a preguntar; propón el punto).
- Si ya dio su número: agradece corto y di que le escribe al WhatsApp para cuadrar («Listo pana, ya le escribo»).
  No vuelvas a hablar de precio ni a pedir nada.
- Si se nota interesado (pregunta precio, dónde, cuándo, dice que lo quiere): pide su número para coordinar,
  como hace el dueño: «Deme su número de contacto para concretar».

PRODUCTO DE ESTE CHAT:
{p['titulo']} · precio publicado {p['precio_fb']}$ · estado: {p['estado']}
{p['descripcion']}

NEGOCIO:
- Precio mínimo absoluto {minimo}$ (no lo digas de entrada). La PRIMERA vez que piden rebaja ofrece
  {round((int(p['precio_fb']) + minimo) / 2)}$; solo si insisten otra vez, {minimo}$. Si ofrecen {minimo}$ o
  más, acepta («Ya, en X$»). Si ofrecen menos, di que en ese precio no se puede y da el último precio ({minimo}$).
- {n['entrega']}
  {n['puntos_entrega']}
- {n['pago']} {("Su número propio (" + NUMERO_DUENO + ") solo si el comprador insiste mucho en pedirlo.") if NUMERO_DUENO else "No des ningún número propio."}
- Si piden algo que no sabes (garantía, envío a otra ciudad, factura, más unidades, un dato técnico que no está
  arriba): «Dejeme confirmo y le aviso» y avisar_dueno=true.
- Si preguntan por otras cosas, también tiene: {otros}.
- Spam o groserías: respuesta vacía.

Responde SOLO JSON:
{{"respuesta": "lo que le mandarías (líneas = mensajes separados), o vacío",
  "telefono": "celular del comprador si lo dio, si no null",
  "sector": "sector del comprador si lo dijo, si no null",
  "precio_acordado": número o null,
  "etapa": "consulta|negociando|interesado|cerrado|perdido",
  "avisar_dueno": true/false, "motivo_aviso": "texto o vacío",
  "resumen": "1 frase de cómo va"}}"""


try:
    with open(os.path.join(BASE, "estilo_dueno.json"), encoding="utf-8") as _f:
        ESTILO = " | ".join(json.load(_f)[:25])
except (OSError, ValueError):
    ESTILO = "Si esta disponible | Cuanto desea | Pana, se lo dejo en 30$ | Donde se ubica pana | A ver si estamos cerca"

RX_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")
SIN_TILDE = {"sí": "si", "Sí": "Si", "está": "esta", "Está": "Esta", "cuánto": "cuanto", "Cuánto": "Cuanto",
             "dónde": "donde", "Dónde": "Donde", "qué": "que", "Qué": "Que", "aquí": "aqui", "allá": "alla",
             "número": "numero", "teléfono": "telefono", "también": "tambien", "mañana": "mañana"}


def humanizar(texto):
    """Quita lo que delata a una IA: signos de apertura, emojis, punto final, tildes de chat, frases largas."""
    lineas = []
    for l in texto.replace("¡", "").replace("¿", "").split("\n"):
        l = RX_EMOJI.sub("", l).strip()
        l = re.sub(r"\s+", " ", l)
        l = " ".join(SIN_TILDE.get(w, w) for w in l.split(" "))
        l = re.sub(r"\$\s?(\d+)", r"\1$", l)  # $30 -> 30$
        l = l.rstrip(".").rstrip()
        if l.endswith("!"):
            l = l.rstrip("!")
        if l:
            lineas.append(l)
    return "\n".join(lineas[:3])


RX_TEL = re.compile(r"(?:\+?593[\s-]?|0)9[\d\s-]{8,10}")


def buscar_telefono(textos):
    for t in reversed(textos):
        for m in RX_TEL.finditer(t):
            num = re.sub(r"\D", "", m.group())
            if num.startswith("593"):
                num = "0" + num[3:]
            if len(num) == 10 and num.startswith("09") and num != NUMERO_DUENO:
                return num
    return None


def precio_muy_bajo(texto, minimo, dichos_por_comprador=()):
    """True si la respuesta ofrece un precio menor al mínimo (ej. «20$», «$20», «20 dólares»).
    Los números que dijo el comprador no cuentan (ej. «$30 no alcanza»)."""
    suyos = {float(x.replace(",", ".")) for t in dichos_por_comprador for x in re.findall(r"\d+(?:[.,]\d+)?", t)}
    for m in re.finditer(r"\$\s?(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s?(?:\$|dólares|dolares|usd)", texto, re.I):
        v = float((m.group(1) or m.group(2)).replace(",", "."))
        if v < minimo and v not in suyos:
            return True
    return False


def pensar(p, minimo, otros, mensajes):
    hist = "\n".join(("Dueño: " if m["yo"] else "Comprador: ") + m["texto"] for m in mensajes[-25:])
    ult = max((i for i, m in enumerate(mensajes) if m["yo"]), default=-1)
    ultimos = " / ".join(m["texto"] for m in mensajes[ult + 1:])
    tel = buscar_telefono([m["texto"] for m in mensajes if not m["yo"]])
    usuario = (f"CONVERSACIÓN HASTA AHORA:\n{hist}\n\nÚLTIMO DEL COMPRADOR (responde a esto): {ultimos}\n"
               + (f"OJO: el comprador YA DIO su número ({tel}). Solo agradece y di que le escribe al WhatsApp.\n" if tel else ""))
    r = ia.json_chat(instrucciones(p, minimo, otros), usuario, temperatura=0.5)
    r["respuesta"] = humanizar((r.get("respuesta") or "").strip())
    return r


# ------------------------------------------------------------------ Facebook

def cerrar_popups(page):
    for _ in range(6):
        b = page.locator("[aria-label='Cerrar chat']")
        if not b.count():
            break
        try:
            b.first.click(timeout=3000)
        except Exception:
            break
        page.wait_for_timeout(500)


def leer_bandeja(page):
    page.goto(URL_BANDEJA, wait_until="domcontentloaded")
    page.wait_for_timeout(7000)
    if P.sin_sesion(page):
        raise P.SinSesion()
    cerrar_popups(page)
    filas = []
    for f in page.locator("div[role=main] div[role=button]").filter(has_text=" · ").all():
        partes = [x.strip() for x in f.inner_text().split("\n") if x.strip()]
        try:
            i = next(k for k, x in enumerate(partes) if x.startswith("·"))
        except StopIteration:
            continue
        nombre, producto = partes[0], partes[i].lstrip("· ").strip()
        resto = partes[i + 1:]
        filas.append({"nombre": nombre, "producto": producto, "ultimo": resto[0] if resto else "",
                      "cuando": resto[1] if len(resto) > 1 else ""})
    return filas


def abrir_chat(page, fila):
    page.locator("div[role=main] div[role=button]").filter(has_text=fila["producto"]).filter(
        has_text=fila["nombre"]).first.click()
    page.wait_for_timeout(5000)
    return leer_chat(page, fila)


def leer_chat(page, fila):
    etiqueta = f"{fila['nombre']} · {fila['producto']}"
    log_ = page.locator(f'[role=log][aria-label="Mensajes de la conversación llamada {etiqueta}"]')
    log_.wait_for(timeout=15000)
    page.wait_for_timeout(1500)
    mensajes = []
    for et in log_.locator("[aria-label^='A las']").evaluate_all("e => e.map(x => x.getAttribute('aria-label'))"):
        m = re.match(r"A las (?P<cuando>[^,]+), (?P<quien>[^:]+)(?:: (?P<texto>.*))?$", et, re.S)
        if not m or not m["texto"] or re.search(r"ha iniciado este chat|está esperando tu respuesta|"
                                                r"te ha enviado un mensaje sobre tu publicación", m["texto"]):
            continue
        mensajes.append({"cuando": m["cuando"], "yo": m["quien"].strip() == "Tú", "texto": m["texto"].strip()})
    return mensajes


def escribir(page, fila, texto):
    caja = page.get_by_role("textbox", name=f"Escribe en {fila['nombre']} · {fila['producto']}")
    for parte in [x.strip() for x in texto.split("\n") if x.strip()][:3]:
        caja.click()
        page.wait_for_timeout(random.randint(600, 1400))
        caja.type(parte, delay=random.randint(35, 75))
        page.wait_for_timeout(random.randint(400, 900))
        page.keyboard.press("Enter")
        page.wait_for_timeout(random.randint(1500, 3000))


def minimizar(page):
    try:
        cdp = page.context.new_cdp_session(page)
        wid = cdp.send("Browser.getWindowForTarget")["windowId"]
        cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "minimized"}})
    except Exception:
        pass


# ------------------------------------------------------------------ una vuelta

def guardar_chat(clave, c, enviados_salida=()):
    """Guarda solo esta conversación, releyendo el archivo (Telegram también escribe en él)."""
    todos = cargar(CHATS, {})
    actual = todos.get(clave, {})
    salida = [t for t in actual.get("salida", []) if t not in enviados_salida]
    actual.update({k: v for k, v in c.items() if k not in ("salida", "borrador")})
    if c.get("borrador"):
        actual["borrador"] = c["borrador"]
    actual["salida"] = salida
    todos[clave] = actual
    guardar(CHATS, todos)


def avisar_lead(clave, c, p, tel):
    wa = "593" + tel[1:]
    TG.enviar(f"📞 NUEVO CONTACTO\n👤 {c['nombre']} · {p['titulo']}\n☎️ {tel}  →  https://wa.me/{wa}\n"
              f"💵 Precio hablado: {('$' + str(c['precio_acordado'])) if c.get('precio_acordado') else 'sin acordar'}"
              f" (publicado ${p['precio_fb']}, mínimo ${c.get('minimo')})\n📝 {c.get('resumen', '')}",
              chat_ref=clave)


def vuelta(simular=False):
    cfg = ajustes()
    if not cfg["activo"] or cfg["modo"] == "pausa":
        log("Respondedor en pausa.")
        return
    cat = catalogo()
    otros = ", ".join(sorted({p["titulo"] for p in cat.values()})[:25])
    if P.puerto_abierto() and P.ram_brave_mb() > 2800:
        log(f"Brave del bot usa {P.ram_brave_mb()} MB: lo reinicio para liberar memoria.")
        P.cerrar_brave_del_bot()
    P.abrir_brave(depuracion=True)  # si ya estaba abierto, lo reutiliza y lo deja abierto
    with sync_playwright() as pw:
        nav = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{P.PUERTO}")
        ctx = nav.contexts[0]
        page = P.una_pestana(ctx)
        page.set_default_timeout(15000)
        try:
            filas = leer_bandeja(page)
        except P.SinSesion:
            log("✖ Sin sesión de Facebook.")
            return
        except Exception as e:
            if "ERR_NAME_NOT_RESOLVED" in str(e) or "ERR_INTERNET" in str(e) or "ERR_NETWORK" in str(e):
                log("Sin internet; reviso en la próxima vuelta.")
                return
            raise
        hechos = 0
        for fila in filas:
            if hechos >= cfg["max_por_vuelta"]:
                break
            p = cat.get(norm(fila["producto"]))
            clave = f"{fila['nombre']}|{fila['producto']}"
            previo = cargar(CHATS, {}).get(clave, {})
            c = {"nombre": fila["nombre"], "producto": fila["producto"], "enviados": previo.get("enviados", []),
                 "telefono": previo.get("telefono"), "precio_acordado": previo.get("precio_acordado")}
            pendientes = list(previo.get("salida", []))
            nuevo = not fila["ultimo"].startswith(("Tú:", "Has enviado"))
            # «26 oct.» = más de una semana sin responder: no se revive
            viejo = bool(re.search(r"\d+ (ene|feb|mar|abr|may|jun|jul|ago|sep|sept|oct|nov|dic)\.?$", fila["cuando"]))
            ya_visto = previo.get("preview") == fila["ultimo"]
            if not p or (not pendientes and (not nuevo or viejo or ya_visto)):
                continue
            try:
                mensajes = abrir_chat(page, fila)
            except Exception as e:
                log(f"  No pude abrir el chat de {clave}: {str(e).splitlines()[0]}")
                cerrar_popups(page)
                continue
            # 1) lo que el dueño mandó desde Telegram
            if pendientes and not simular:
                for t in pendientes:
                    escribir(page, fila, t)
                    c["enviados"].append(t)
                    log(f"  Enviado (de Telegram) a {fila['nombre']}: {t}")
                guardar_chat(clave, c, enviados_salida=pendientes)
                mensajes = leer_chat(page, fila)
            if not mensajes or mensajes[-1]["yo"]:
                c["preview"] = fila["ultimo"]  # la última palabra es nuestra: no reabrir hasta que cambie
                guardar_chat(clave, c)
                cerrar_popups(page)
                continue
            # si el dueño está escribiendo a mano en este chat hace poco, no meterse
            manuales = [m for m in mensajes if m["yo"] and m["texto"] not in c["enviados"]]
            if manuales and re.fullmatch(r"\d{1,2}:\d{2}", manuales[-1]["cuando"]):
                h, mi = map(int, manuales[-1]["cuando"].split(":"))
                if (datetime.now() - datetime.now().replace(hour=h, minute=mi)).total_seconds() < 45 * 60:
                    log(f"  {fila['nombre']}: estás respondiendo tú, no me meto.")
                    cerrar_popups(page)
                    continue
            minimo = precio_minimo(p, cfg)
            r = pensar(p, minimo, otros, mensajes)
            del_comprador = [m["texto"] for m in mensajes if not m["yo"]]
            tel = buscar_telefono(del_comprador) or (r.get("telefono") if buscar_telefono([r.get("telefono") or ""]) else None)
            c.update(minimo=minimo, etapa=r.get("etapa"), resumen=r.get("resumen"),
                     precio_acordado=r.get("precio_acordado") or c.get("precio_acordado"),
                     actualizado=datetime.now().isoformat(timespec="seconds"))
            ult_mio = max((i for i, m in enumerate(mensajes) if m["yo"]), default=-1)
            nuevas = [m["texto"] for m in mensajes[ult_mio + 1:]]
            respuesta = r["respuesta"]
            if respuesta and precio_muy_bajo(respuesta, minimo, nuevas):
                log(f"  ⚠ La IA quiso dar un precio menor al mínimo (${minimo}); no lo envío: «{respuesta}»")
                simular or TG.enviar(f"⚠️ {fila['nombre']} · {p['titulo']}\nPide: {' / '.join(nuevas)[-300:]}\n"
                          f"La IA quiso responder con un precio bajo el mínimo (${minimo}):\n«{respuesta}»\n"
                          "Responde a este mensaje con lo que quieras que le diga.", chat_ref=clave)
                respuesta = ""
            log(f"  {fila['nombre']} · {p['titulo'][:40]}: «{' / '.join(nuevas)[-120:]}» → «{respuesta[:150]}»")
            if simular:
                cerrar_popups(page)
                hechos += 1
                continue
            enviado = False
            if respuesta and cfg["modo"] == "auto":
                escribir(page, fila, respuesta)
                c["enviados"] += [x.strip() for x in respuesta.split("\n") if x.strip()]
                c["enviados"] = c["enviados"][-60:]
                enviado = True
            elif respuesta and cfg["modo"] == "aprobar":
                c["borrador"] = respuesta
                TG.enviar(f"✍️ {fila['nombre']} · {p['titulo']}\n👤 {' / '.join(nuevas)[-400:]}\n🤖 Propongo: {respuesta}",
                          chat_ref=clave, botones=[("✅ Enviar", f"ok|{clave}"), ("❌ No", f"no|{clave}")])
            if tel and tel != c.get("telefono"):
                c["telefono"] = tel
                avisar_lead(clave, c, p, tel)
            elif r.get("avisar_dueno") and r.get("motivo_aviso"):
                TG.enviar(f"🙋 {fila['nombre']} · {p['titulo']}\n{r['motivo_aviso']}\n👤 {' / '.join(nuevas)[-300:]}\n"
                          "Responde a este mensaje para contestarle tú.", chat_ref=clave)
            elif enviado and cfg["copiar_a_telegram"]:
                TG.enviar(f"💬 {fila['nombre']} · {p['titulo'][:45]}\n👤 {' / '.join(nuevas)[-300:]}\n🤖 {respuesta}",
                          chat_ref=clave)
            if not respuesta:
                c["preview"] = fila["ultimo"]
            guardar_chat(clave, c)
            cerrar_popups(page)
            hechos += 1
            page.wait_for_timeout(random.randint(8000, 20000))
        if not hechos:
            log("Sin mensajes nuevos.")
        minimizar(page)
    # Brave se deja abierto (minimizado) para la próxima vuelta; el panel y el gestor lo reutilizan.


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--simular", action="store_true")
    a = ap.parse_args()
    try:
        with P.candado_brave(esperar=False):
            vuelta(a.simular)
    except BlockingIOError:
        log("Brave ocupado con otra tarea; reviso los mensajes en la próxima vuelta.")


if __name__ == "__main__":
    main()
