"""Llamadas a Groq (modelos gratis) que devuelven JSON."""
import json, os, time, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))


def clave():
    for ruta in (os.path.join(BASE, "config_ia.json"),):
        try:
            with open(ruta, encoding="utf-8") as f:
                k = json.load(f).get("groq_api_key")
            if k:
                return k
        except (OSError, ValueError):
            pass
    return os.environ.get("GROQ_API_KEY", "")


def modelo():
    try:
        with open(os.path.join(BASE, "config_ia.json"), encoding="utf-8") as f:
            return json.load(f).get("modelo") or "openai/gpt-oss-120b"
    except (OSError, ValueError):
        return "openai/gpt-oss-120b"


NEGOCIO_BASE = {
    "ciudad": "Tu ciudad",
    "pais": "Tu país",
    "telefono_dueno": "",
    "entrega": "Entrega en lugar público, punto medio.",
    "puntos_entrega": "",
    "pago": "Pago solo efectivo.",
}


def negocio():
    """Datos del negocio (ciudad, teléfono, puntos de entrega…) desde negocio.json."""
    d = dict(NEGOCIO_BASE)
    try:
        with open(os.path.join(BASE, "negocio.json"), encoding="utf-8") as f:
            d.update(json.load(f))
    except (OSError, ValueError):
        pass
    return d


RESPALDO = "openai/gpt-oss-20b"  # modelo gratis más liviano si el principal está saturado


def json_chat(sistema, usuario, temperatura=0.6, intentos=4):
    import urllib.error
    k = clave()
    if not k:
        raise RuntimeError("No hay clave de Groq")
    ultimo = None
    for i in range(intentos):
        m = modelo() if i < 2 else RESPALDO
        try:
            return _llamar(k, m, sistema, usuario, temperatura)
        except urllib.error.HTTPError as e:
            ultimo = e
            time.sleep(25 if e.code == 429 else 5)  # 429 = límite por minuto del plan gratis
        except Exception as e:  # red, JSON roto: reintenta
            ultimo = e
            time.sleep(5)
    raise RuntimeError(f"La IA no respondió: {ultimo}")


def _llamar(k, m, sistema, usuario, temperatura):
    cuerpo = json.dumps({"model": m, "temperature": temperatura,
                         "response_format": {"type": "json_object"},
                         "messages": [{"role": "system", "content": sistema},
                                      {"role": "user", "content": usuario if isinstance(usuario, str)
                                       else json.dumps(usuario, ensure_ascii=False)}]}).encode()
    req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", data=cuerpo, headers={
        "Authorization": f"Bearer {k}", "Content-Type": "application/json", "User-Agent": "marketplace-bot"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(json.load(r)["choices"][0]["message"]["content"])
