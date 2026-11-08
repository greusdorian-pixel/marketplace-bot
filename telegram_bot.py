"""Control del bot de Marketplace por Telegram.

Configuración en telegram.json: {"token": "...", "chat_id": null}
El primer chat que mande  /start <clave del panel>  queda como dueño; los demás se ignoran.
"""
import json, os, re, subprocess, threading, time, urllib.parse, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(BASE, "telegram.json")
IA_LOG = os.path.join(BASE, "logs", "ia.log")
PANEL = "http://127.0.0.1:8765"
AYUDA = ("🤖 *Bot de Marketplace*\n"
         "/estado – cómo va todo\n"
         "/revisar – revisar anuncios ahora (renueva/recrea)\n"
         "/simular – decir qué haría, sin tocar nada\n"
         "/pausa – apagar el gestor automático\n"
         "/activar – encender el gestor automático\n"
         "/registro – últimas líneas del registro\n"
         "/chats – conversaciones con compradores\n"
         "/auto · /aprobar · /pausachat – cómo responde los mensajes\n\n"
         "También puedes escribirme normal (ej. «¿quién quiere la bomba?», «el mínimo del 12 es 1700»). "
         "Si respondes a un aviso de un comprador, tu texto se lo mando a él.")


def conf():
    try:
        with open(CONF, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def guardar_conf(c):
    tmp = CONF + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONF)
    os.chmod(CONF, 0o600)


def api_tg(metodo, **params):
    token = conf().get("token")
    if not token:
        return None
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{metodo}", data=data)
    with urllib.request.urlopen(req, timeout=70) as r:
        return json.load(r)


REFS = os.path.join(BASE, "tg_refs.json")
CHATS = os.path.join(BASE, "chats.json")
MEMORIA = os.path.join(BASE, "tg_memoria.json")


def leer_json(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def escribir_json(ruta, data):
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ruta)


def enviar(texto, markdown=False, chat_ref=None, botones=None):
    """Manda un mensaje al dueño. Nunca lanza error (si no hay internet, se pierde el aviso).
    chat_ref: conversación de Marketplace a la que pertenece (para que el dueño pueda responderle)."""
    c = conf()
    if not c.get("token") or not c.get("chat_id"):
        return False
    try:
        extra = {"parse_mode": "Markdown"} if markdown else {}
        if botones:
            extra["reply_markup"] = json.dumps({"inline_keyboard": [[{"text": t, "callback_data": d[:64]}
                                                                     for t, d in botones]]})
        r = api_tg("sendMessage", chat_id=c["chat_id"], text=texto[:4000], disable_web_page_preview="true", **extra)
        if chat_ref and r and r.get("ok"):
            refs = leer_json(REFS, {})
            refs[str(r["result"]["message_id"])] = chat_ref
            escribir_json(REFS, dict(list(refs.items())[-400:]))
        return True
    except Exception as e:
        print(f"[telegram] no se pudo enviar: {e}", flush=True)
        return False


def encolar_para_comprador(clave, texto):
    chats = leer_json(CHATS, {})
    if clave not in chats:
        return False
    chats[clave].setdefault("salida", []).append(texto)
    escribir_json(CHATS, chats)
    return True


def ajustes_chat():
    return leer_json(os.path.join(BASE, "config_ia.json"), {}).get("chat", {})


def cambiar_chat(**cambios):
    ruta = os.path.join(BASE, "config_ia.json")
    c = leer_json(ruta, {})
    c.setdefault("chat", {}).update(cambios)
    escribir_json(ruta, c)


def texto_chats(n=10):
    chats = sorted(leer_json(CHATS, {}).items(), key=lambda kv: kv[1].get("actualizado", ""), reverse=True)[:n]
    if not chats:
        return "Todavía no hay conversaciones atendidas."
    iconos = {"cerrado": "🤝", "interesado": "🔥", "negociando": "💬", "perdido": "🧊"}
    return "\n".join(f"{iconos.get(c.get('etapa'), '❔')} {c['nombre']} · {c['producto'][:30]}"
                     + (f" · ☎️ {c['telefono']}" if c.get("telefono") else "")
                     + (f" · ${c['precio_acordado']}" if c.get("precio_acordado") else "")
                     + (f"\n   {c.get('resumen')}" if c.get("resumen") else "") for _, c in chats)


def asistente(texto):
    """El dueño habla en lenguaje normal; la IA responde y puede hacer algunas acciones."""
    import ia
    productos = leer_json(os.path.join(BASE, "productos.json"), [])
    chats = leer_json(CHATS, {})
    memoria = leer_json(MEMORIA, [])[-10:]
    fb = anuncios_fb()
    contexto = {
        "estado": texto_estado(),
        "modo_respuestas": ajustes_chat().get("modo", "auto"),
        "gestor_automatico": ("Ya renueva solo y recrea con otro título los anuncios del bot con 0 clics tras "
                              "4 días (máx. 3 por día), a las 10:00 y 17:00. 'revisar' lo corre ya."),
        "productos": [{"id": p["id"], "titulo": p["titulo"], **fb.get(p["id"], {}),
                       "precio_minimo_manual": p.get("precio_minimo")} for p in productos],
        "nota_precios": "precio_fb es el precio real en Facebook; úsalo siempre para calcular rebajas o mínimos.",
        "pendiente_de_confirmar": leer_json(PENDIENTE, {}).get("descripcion"),
        "conversaciones": [{"clave": k, "nombre": c["nombre"], "producto": c["producto"], "etapa": c.get("etapa"),
                            "telefono": c.get("telefono"), "precio_acordado": c.get("precio_acordado"),
                            "resumen": c.get("resumen")}
                           for k, c in sorted(chats.items(), key=lambda kv: kv[1].get("actualizado", ""))[-20:]],
        "charla_anterior": memoria,
        "mensaje_del_dueno": texto,
    }
    sistema = (
        "Eres el asistente por Telegram del dueño de un bot que vende mercadería de remate en Facebook Marketplace "
        f"({ia.negocio()['ciudad']}). Le hablas como un amigo de confianza: relajado, directo, frases cortas, "
        "nada de lenguaje de robot ni de oficina («procesar», «registrado», «etapa de consulta»). Nombra los productos "
        "por su nombre corto (la bomba, el disco Carioca), nunca por ID. Da el dato útil y propone el siguiente paso "
        "(«¿le escribo a César?»). Sí entiendes notas de voz: el sistema las transcribe y te llegan como texto. Revisa bien los números antes de decirlos. Usas solo los datos "
        "del contexto; si no sabes algo, dilo. Nunca le pidas IDs: búscalos tú en 'productos' (clics, precio_fb). "
        "Si pide algo que tú no puedes hacer (p. ej. cambiar el precio publicado en Facebook), dilo claro. "
        "Si pide cambiar varios productos a la vez, devuelve igual las acciones: el sistema le mostrará la lista "
        "y le pedirá confirmar antes de aplicar (tú NO repitas la lista, solo di qué regla usaste). "
        "Borrar y resubir con otro título lo hace el gestor (acción 'revisar'): solo recrea los que llevan "
        "≥4 días sin clics; si tienen 0 días (recién subidos) explícale que hay que darles tiempo. Puedes hacer acciones cuando el dueño lo pida claramente:\n"
        '- {"tipo":"responder_comprador","clave":"<clave de la conversación>","texto":"..."}\n'
        '- {"tipo":"precio_minimo","id":"NN","valor":entero}\n'
        '- {"tipo":"modo","valor":"auto|aprobar|pausa"}  (auto = responde solo, aprobar = pide OK, pausa = no responde)\n'
        '- {"tipo":"revisar"} o {"tipo":"simular"}  (revisión de anuncios)\n'
        'Responde SOLO JSON: {"respuesta":"texto para el dueño","acciones":[...]}')
    r = ia.json_chat(sistema, contexto, temperatura=0.4)
    acciones = [a for a in (r.get("acciones") or []) if isinstance(a, dict)]
    if sum(a.get("tipo") == "precio_minimo" for a in acciones) > 1:
        # cambios en varios productos: primero mostrar y esperar el OK del dueño
        nombres = {p["id"]: p["titulo"][:32] for p in productos}
        lineas = [f"• {nombres.get(str(a.get('id')).zfill(2), a.get('id'))}: mínimo ${a.get('valor')}"
                  for a in acciones if a.get("tipo") == "precio_minimo"]
        desc = "Poner precio mínimo:\n" + "\n".join(lineas)
        escribir_json(PENDIENTE, {"acciones": acciones, "descripcion": desc})
        respuesta = (r.get("respuesta") or "") + "\n\n📝 Esto haría (aún NO lo aplico):\n" + desc
        memoria.append({"dueno": texto, "asistente": respuesta})
        escribir_json(MEMORIA, memoria[-10:])
        enviar(respuesta[:3900], botones=[("✅ Aplicar", "pend|ok"), ("❌ Cancelar", "pend|no")])
        return None
    respuesta = aplicar(acciones, chats, r.get("respuesta") or "Listo.")
    memoria.append({"dueno": texto, "asistente": respuesta})
    escribir_json(MEMORIA, memoria[-10:])
    return respuesta


PENDIENTE = os.path.join(BASE, "tg_pendiente.json")


def _norm(t):
    import unicodedata
    return " ".join(unicodedata.normalize("NFKC", t).lower().split())


def anuncios_fb():
    """{id: {precio_fb, clics, dias}} desde la última revisión de Facebook."""
    pub = leer_json(os.path.join(BASE, "publicados.json"), {})
    titulos = {}
    for pid, d in pub.items():
        for t in (d.get("titulo_fb"), d.get("titulo")):
            if t:
                titulos[_norm(t)] = pid
    ult = leer_json(os.path.join(BASE, "historial_ia.json"), {}).get("ultima_revision", {})
    out = {}
    for a in ult.get("anuncios", []):
        pid = titulos.get(_norm(a.get("titulo", "")))
        if pid:
            out[pid] = {"precio_fb": a.get("precio"), "clics": a.get("clics"), "dias_publicado": a.get("dias")}
    return out


def aplicar(acciones, chats, respuesta):
    hechas = []
    for a in acciones:
        t = a.get("tipo")
        if t == "responder_comprador" and a.get("texto") and encolar_para_comprador(a.get("clave", ""), a["texto"]):
            hechas.append(f"📨 Se lo envío a {chats[a['clave']]['nombre']} en la próxima vuelta")
        elif t == "precio_minimo" and str(a.get("valor", "")).isdigit():
            ruta = os.path.join(BASE, "productos.json")
            ps = leer_json(ruta, [])
            for p in ps:
                if p["id"] == str(a.get("id")).zfill(2):
                    p["precio_minimo"] = int(a["valor"])
                    hechas.append(f"💲 Mínimo de {p['titulo'][:30]}: ${a['valor']}")
            escribir_json(ruta, ps)
        elif t == "modo" and a.get("valor") in ("auto", "aprobar", "pausa"):
            cambiar_chat(modo=a["valor"])
            hechas.append(f"⚙️ Respuestas en modo {a['valor']}")
        elif t in ("revisar", "simular"):
            try:
                panel("/api/ia/revisar", {"simular": t == "simular"})
                hechas.append("🔎 Revisión de anuncios iniciada")
            except OSError:
                hechas.append("⚠️ El panel no responde")
    return respuesta + ("\n\n" + "\n".join(hechas) if hechas else "")


def panel(ruta, datos=None):
    req = urllib.request.Request(PANEL + ruta, data=json.dumps(datos).encode() if datos is not None else None)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def texto_estado():
    try:
        d = panel("/api/datos")
    except OSError:
        return "⚠️ El panel no responde."
    prods, pubs = d["productos"], d["publicados"]
    n_pub = sum(1 for p in prods if p["id"] in pubs)
    ia = d.get("ia", {})
    lineas = [
        f"📦 Productos: {len(prods)} · publicados {n_pub} · pendientes {len(prods) - n_pub}",
        "✅ Facebook conectado" if d.get("sesion") else "❌ Sin sesión de Facebook (inicia sesión en el panel)",
        f"🤖 Gestor automático: {'encendido' if ia.get('auto') else 'apagado'}"
        + (f" · próxima {ia['proxima'][4:20]}" if ia.get("auto") and ia.get("proxima") else ""),
    ]
    if d.get("corriendo"):
        lineas.append(f"⏳ Ahora: {d.get('tarea')}")
    try:
        with open(os.path.join(BASE, "historial_ia.json"), encoding="utf-8") as f:
            h = json.load(f)
        r = h.get("ultima_revision", {})
        if r:
            ajenos = set(r.get("ajenos", []))
            anuncios = [a for a in r.get("anuncios", []) if a["titulo"] not in ajenos]
            ceros = [a["titulo"] for a in anuncios if a["clics"] == 0]
            top = sorted(anuncios, key=lambda a: -a["clics"])[:3]
            lineas.append(f"🔎 Última revisión: {r['fecha'][8:10]}/{r['fecha'][5:7]} {r['fecha'][11:16]}")
            lineas.append("🔥 Más clics: " + "; ".join(f"{a['titulo'][:28]} ({a['clics']})" for a in top))
            if ceros:
                lineas.append(f"🧊 Sin clics: {len(ceros)}")
    except (OSError, ValueError, KeyError):
        pass
    return "\n".join(lineas)


def cola_log(n=20):
    if not os.path.exists(IA_LOG):
        return "Sin registro todavía."
    with open(IA_LOG, encoding="utf-8", errors="replace") as f:
        return "\n".join(f.read().splitlines()[-n:])


def systemctl(*a):
    return subprocess.run(["systemctl", "--user", *a], capture_output=True, text=True)


def atender(texto, chat_id):
    c = conf()
    cmd = texto.strip().split()[0].split("@")[0].lower() if texto.strip() else ""
    if not c.get("chat_id"):
        clave = open(os.path.join(BASE, "clave_panel.txt"), encoding="utf-8").read().strip()
        palabras = texto.strip().split()
        dada = palabras[1] if cmd == "/start" and len(palabras) > 1 else (palabras[0] if len(palabras) == 1 else "")
        print(f"[telegram] mensaje de {chat_id} sin vincular", flush=True)
        if dada == clave:
            c["chat_id"] = chat_id
            guardar_conf(c)
            enviar("✅ Listo, este chat quedó vinculado al bot.\n\n" + AYUDA, markdown=True)
        else:
            try:
                time.sleep(2)
                api_tg("sendMessage", chat_id=chat_id,
                       text="🔒 Para vincularte mándame la clave del panel (la misma que usas en el celular).")
            except Exception:
                pass
        return
    if chat_id != c["chat_id"]:
        return  # desconocidos: silencio
    if cmd in ("/start", "/ayuda", "/help"):
        enviar(AYUDA, markdown=True)
    elif cmd == "/estado":
        enviar(texto_estado())
    elif cmd in ("/revisar", "/simular"):
        try:
            r = panel("/api/ia/revisar", {"simular": cmd == "/simular"})
            enviar("⏳ " + ("Simulando…" if cmd == "/simular" else "Revisando anuncios…") + " Te aviso al terminar."
                   if r.get("ok") else f"⚠️ {r.get('error')}")
        except OSError:
            enviar("⚠️ El panel no responde.")
    elif cmd in ("/pausa", "/activar"):
        r = systemctl("enable" if cmd == "/activar" else "disable", "--now", "marketplace-ia.timer")
        enviar(("▶️ Gestor automático encendido" if cmd == "/activar" else "⏸ Gestor automático apagado")
               if r.returncode == 0 else f"⚠️ {r.stderr.strip()}")
    elif cmd == "/registro":
        enviar(cola_log(25))
    elif cmd == "/chats":
        enviar(texto_chats())
    elif cmd in ("/auto", "/aprobar", "/pausachat"):
        modo = {"/auto": "auto", "/aprobar": "aprobar", "/pausachat": "pausa"}[cmd]
        cambiar_chat(modo=modo)
        enviar({"auto": "🤖 Respondo solo a los compradores (te mando copia).",
                "aprobar": "✍️ Te mando cada respuesta para que la apruebes.",
                "pausa": "⏸ No respondo a nadie hasta que digas /auto o /aprobar."}[modo])
    elif cmd.startswith("/"):
        enviar("No conozco ese comando. " + AYUDA, markdown=True)
    else:
        try:
            r = asistente(texto)
            if r:
                enviar(r)
        except Exception as e:
            enviar(f"⚠️ No pude pensar la respuesta: {e}")


def botón(q):
    if q.get("message", {}).get("chat", {}).get("id") != conf().get("chat_id"):
        return
    accion, _, clave = q.get("data", "").partition("|")
    if accion == "pend":
        p = leer_json(PENDIENTE, {})
        if clave == "ok" and p.get("acciones"):
            enviar("✅ Aplicado:" + aplicar(p["acciones"], leer_json(CHATS, {}), ""))
        else:
            enviar("❌ Cancelado, no cambié nada.")
        escribir_json(PENDIENTE, {})
        try:
            api_tg("answerCallbackQuery", callback_query_id=q["id"])
        except Exception:
            pass
        return
    chats = leer_json(CHATS, {})
    c = chats.get(clave, {})
    if accion == "ok" and c.get("borrador"):
        c.setdefault("salida", []).append(c.pop("borrador"))
        aviso = "✅ Se envía en la próxima vuelta"
    else:
        c.pop("borrador", None)
        aviso = "❌ Descartado"
    escribir_json(CHATS, chats)
    try:
        api_tg("answerCallbackQuery", callback_query_id=q["id"], text=aviso)
    except Exception:
        pass


def transcribir(file_id):
    """Nota de voz de Telegram → texto con Whisper de Groq (gratis)."""
    import ia, uuid
    info = api_tg("getFile", file_id=file_id)["result"]
    url = f"https://api.telegram.org/file/bot{conf()['token']}/{info['file_path']}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return whisper(r.read())


def whisper(datos, nombre="audio.ogg"):
    import ia, uuid
    b = uuid.uuid4().hex
    partes = []
    for k, v in (("model", "whisper-large-v3-turbo"), ("language", "es"), ("response_format", "json")):
        partes.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    partes.append(f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{nombre}"\r\n'
                  f'Content-Type: application/octet-stream\r\n\r\n'.encode() + datos + b"\r\n")
    cuerpo = b"".join(partes) + f"--{b}--\r\n".encode()
    req = urllib.request.Request("https://api.groq.com/openai/v1/audio/transcriptions", data=cuerpo, headers={
        "Authorization": f"Bearer {ia.clave()}", "Content-Type": f"multipart/form-data; boundary={b}",
        "User-Agent": "marketplace-bot"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r).get("text", "").strip()


def escuchar(parar):
    """Bucle de mensajes entrantes (long polling). Corre en un hilo."""
    offset = None
    while not parar.is_set():
        if not conf().get("token"):
            time.sleep(15)
            continue
        try:
            r = api_tg("getUpdates", timeout=50, **({"offset": offset} if offset else {}))
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                if "callback_query" in u:
                    botón(u["callback_query"])
                    continue
                m = u.get("message") or {}
                audio = m.get("voice") or m.get("audio")
                if audio and m.get("chat", {}).get("id") == conf().get("chat_id"):
                    try:
                        m["text"] = transcribir(audio["file_id"])
                    except Exception as e:
                        print(f"[telegram] audio: {e}", flush=True)
                        enviar(f"⚠️ No pude entender el audio: {e}")
                        continue
                    if not m["text"]:
                        enviar("🎤 No escuché nada en el audio.")
                        continue
                    enviar(f"🎤 Entendí: «{m['text']}»")
                if "text" not in m:
                    continue
                ref = leer_json(REFS, {}).get(str((m.get("reply_to_message") or {}).get("message_id")))
                if ref and m["chat"]["id"] == conf().get("chat_id") and not m["text"].startswith("/"):
                    ok = encolar_para_comprador(ref, m["text"])
                    enviar("📨 Se lo envío en la próxima vuelta (unos minutos)." if ok else "⚠️ No encontré ese chat.")
                    continue
                atender(m["text"], m["chat"]["id"])
        except Exception as e:
            print(f"[telegram] {e}", flush=True)
            time.sleep(10)


RESUMEN = re.compile(r"Renovado ✔|Recreando|Título nuevo|Nuevo publicado|Anterior borrado|Publicado ✔|ERROR|✖|⚠|"
                     r"Revisé \d+|SIMULACIÓN|Nada que hacer")


def vigilar_registro(parar):
    """Cuando termina una revisión en ia.log, manda un resumen por Telegram."""
    pos = os.path.getsize(IA_LOG) if os.path.exists(IA_LOG) else 0
    bloque = []
    while not parar.is_set():
        time.sleep(5)
        if not os.path.exists(IA_LOG):
            continue
        tam = os.path.getsize(IA_LOG)
        if tam < pos:
            pos = 0
        if tam == pos:
            continue
        with open(IA_LOG, encoding="utf-8", errors="replace") as f:
            f.seek(pos)
            nuevas = f.read().splitlines()
            pos = f.tell()
        for l in nuevas:
            if RESUMEN.search(l):
                bloque.append(re.sub(r"^\[\d\d:\d\d:\d\d\] ", "", l).strip())
            if "Revisión terminada" in l or "No hay sesión" in l or "Traceback" in l:
                if "Traceback" in l:
                    bloque.append("❌ El gestor falló (mira logs/ia.log)")
                enviar("🤖 Revisión de anuncios\n" + "\n".join(bloque[-30:] or ["(sin cambios)"]))
                bloque = []
