# 🛒 Bot de Facebook Marketplace con IA

Bot para vender mercadería (remates, liquidaciones, productos usados) en **Facebook Marketplace** de forma casi automática:

- 📤 **Publica** tus productos (título, precio, fotos, descripción) desde un panel web local.
- 🔄 **Renueva** los anuncios solo y **recrea** con otro título los que no reciben clics.
- 💬 **Responde a los compradores** con IA, imitando tu forma de escribir, sin bajar del precio mínimo.
- 📱 **Te avisa por Telegram** cuando alguien deja su número, y desde Telegram lo controlas (también con notas de voz).
- 🟢 **Ícono junto al reloj** que mantiene todo funcionando (verde = bien, amarillo = atención, rojo = sin sesión de Facebook).

La IA usa **[Groq](https://console.groq.com)**, que tiene modelos **gratis** (`openai/gpt-oss-120b`, `whisper-large-v3-turbo`).
No hace falta pagar ninguna API ni tener una PC potente.

> ⚠️ **Aviso:** automatizar Facebook va contra sus términos de uso. Úsalo con moderación y bajo tu propia responsabilidad.
> El bot va despacio a propósito (pausas aleatorias y límites por día) para comportarse como una persona.

---

## ¿Cómo funciona?

```
 bandeja.py  (ícono junto al reloj, arranca solo al prender la PC)
   ├─ panel.py ──── http://127.0.0.1:8765 ──── panel.html   ← tú usas esto
   │     ├─ publicar.py   publica los productos de productos.json
   │     └─ revisar.py    gestor IA: renueva / recrea anuncios
   ├─ telegram_bot.py     comandos y charla contigo por Telegram
   └─ mensajes.py         cada 4–8 min lee la bandeja de Marketplace y responde

 systemd (opcional): revisar.py 2 veces al día (10:00 y 17:00)
```

Todo lo que toca Facebook usa **un Brave propio del bot** (carpeta `perfil-brave/`), controlado con
[Playwright](https://playwright.dev/python/) por el puerto de depuración 9222. Tú inicias sesión en Facebook **una vez**
en ese Brave y el bot reutiliza la sesión. Tu Brave normal no se toca.

| Archivo | Qué hace |
|---|---|
| `publicar.py` | Llena el formulario de Marketplace y publica. Comprueba la sesión, reintenta y nunca publica dos veces lo mismo |
| `revisar.py` | Lee «Tus publicaciones»: renueva los anuncios viejos y recrea los que tienen pocos clics (la IA escribe un título nuevo, publica el nuevo y **después** borra el viejo). `--simular` muestra qué haría sin tocar nada |
| `mensajes.py` | Respondedor de compradores. Negocia hasta el precio mínimo, pide el teléfono del comprador y te lo manda a Telegram. `--simular` no escribe nada |
| `telegram_bot.py` | Bot de Telegram: `/estado`, `/revisar`, `/simular`, `/pausa`, `/activar`, `/registro`, botones ✅/❌, notas de voz y charla libre con un asistente IA |
| `panel.py` + `panel.html` | Panel web: ver productos, publicar, estado de la sesión de Facebook, activar el gestor IA |
| `bandeja.py` | Ícono en la barra del sistema que mantiene vivos el panel, Telegram y el respondedor |
| `ia.py` | Llamadas a Groq (respuestas en JSON y datos del negocio) |
| `catalogo.py`, `preparar.py` | Extras: catálogo en PDF y preparación/redimensionado de fotos |

Solo toca **los anuncios y chats de los productos del bot**. Si tienes otros anuncios propios en Facebook, los deja en paz.

---

## Instalación (Linux)

Requisitos: **Linux** con escritorio (probado en Linux Mint / Ubuntu), **Python 3.10+**, **[Brave](https://brave.com/linux/)** y `git`.

```bash
git clone https://github.com/greusdorian-pixel/marketplace-bot.git ~/marketplace-bot
cd ~/marketplace-bot
./instalar.sh
```

`instalar.sh` crea el entorno de Python (`.venv`), instala las dependencias y copia los archivos de `ejemplos/` a la carpeta principal.

> Para el ícono junto al reloj, en Ubuntu/Mint puede hacer falta: `sudo apt install gir1.2-ayatanaappindicator3-0.1`

## Configuración

Edita estos archivos (ninguno se sube a GitHub, están en `.gitignore`):

### 1. `config_ia.json`: clave de Groq y reglas del gestor
Crea una clave gratis en <https://console.groq.com/keys> y pégala en `"groq_api_key"`
(o usa la variable de entorno `GROQ_API_KEY`).

| Ajuste | Qué significa |
|---|---|
| `dias_renovar` | Renovar un anuncio cada tantos días |
| `recrear`, `dias_recrear`, `clics_max_recrear` | Recrear anuncios con más de X días y menos de Y clics |
| `dias_sin_clics` | Si tiene **0 clics**, recrearlo desde este día |
| `max_recrear_por_dia`, `max_renovar_por_vez` | Límites para no exagerar |
| `chat.modo` | `auto` = responde solo · `aprobar` = te pide OK por Telegram · `pausa` |
| `chat.rebaja_max` | Máximo que puede rebajar en dólares (en productos de menos de $30 manda `rebaja_max_pct_baratos` %) |
| `chat.horario` | Horas en que responde mensajes |

### 2. `negocio.json`: datos de tu negocio
Ciudad, país, cómo entregas, puntos de encuentro, forma de pago y (opcional) tu teléfono.
La IA usa esto para responder a los compradores.

### 3. `productos.json`: tu catálogo
```json
{
  "id": "01",
  "titulo": "Taladro percutor 600W con maletín",
  "precio": 35,
  "categoria": "Herramientas",
  "estado": "Nuevo",
  "descripcion": "…",
  "fotos": ["fotos/01/foto1.jpg"],
  "precio_minimo": 28
}
```
Las fotos van en `fotos/<id>/`. `precio_minimo` es opcional; si no lo pones, el mínimo es el precio menos `rebaja_max`.

### 4. `estilo_dueno.json` y `estilo_conversaciones.json`: cómo hablas tú
Frases tuyas y pares reales «comprador → tú». La IA los copia para sonar como tú y no como un robot.
Cuantos más ejemplos reales pongas, mejor.

### 5. `telegram.json` (opcional, recomendado)
1. En Telegram habla con **@BotFather**, escribe `/newbot` y copia el token en `"token"`.
2. Abre el panel una vez: se crea `clave_panel.txt` con una clave.
3. Mándale a tu bot: `/start <la clave>`. Desde ahí solo te obedece a ti.

## Uso

```bash
./abrir_panel.sh        # abre el panel en http://127.0.0.1:8765
./iniciar_bot.sh        # arranca el ícono + Telegram + respondedor
./apagar_panel.sh       # apaga el panel
```

La **primera vez**, publica desde el panel: se abre el Brave del bot, inicias sesión en Facebook y listo.

Probar sin tocar nada:
```bash
.venv/bin/python revisar.py --simular     # qué renovaría / recrearía
.venv/bin/python mensajes.py --simular    # qué respondería a los compradores
```

### Que arranque solo

**Al prender la PC** (ícono, Telegram y respondedor), crea `~/.config/autostart/bot-marketplace.desktop`:
```ini
[Desktop Entry]
Type=Application
Name=Bot Marketplace
Exec=/home/TU_USUARIO/marketplace-bot/iniciar_bot.sh
X-GNOME-Autostart-enabled=true
```

**Gestor IA 2 veces al día:**
```bash
mkdir -p ~/.config/systemd/user
cp systemd/marketplace-ia.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now marketplace-ia.timer
```

Los registros están en `logs/` (`ia.log`, `mensajes.log`, `panel.log`, `bandeja.log`).

## Pasárselo a otra persona

Cada persona clona el repositorio en su PC, ejecuta `./instalar.sh` y pone **sus propios** datos
(clave de Groq, bot de Telegram, `negocio.json`, productos). Así nadie comparte claves ni sesiones de Facebook.

## Notas

- Facebook cambia su página a veces. Los selectores están pensados para Facebook **en español** (`Renovar publicación`,
  `Más opciones de …`, etc.). Si algo deja de funcionar, mira las capturas `logs/error_*.png`.
- El Brave del bot usa una sola pestaña y se reinicia solo si gasta mucha memoria (pensado para PCs modestas).
- Groq gratis tiene límite por minuto. Si se satura, el bot espera y usa un modelo más liviano.

## Licencia

MIT. Úsalo, cámbialo y compártelo.
