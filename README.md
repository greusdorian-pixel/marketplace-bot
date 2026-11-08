<div align="center">

# 🛒 Marketplace Bot

**Tu vendedor automático para Facebook Marketplace, con IA gratis.**

Publica tus productos, renueva los anuncios, responde a los compradores como si fueras tú y te avisa por Telegram cuando alguien quiere comprar.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-Brave-2EAD33?logo=playwright&logoColor=white)
![Groq](https://img.shields.io/badge/IA-Groq%20gratis-F55036)
![Telegram](https://img.shields.io/badge/Telegram-bot-26A5E4?logo=telegram&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-Mint%20%7C%20Ubuntu-FCC624?logo=linux&logoColor=black)
![Claude Code](https://img.shields.io/badge/Hecho%20para-Claude%20Code-D97757?logo=anthropic&logoColor=white)
![Licencia MIT](https://img.shields.io/badge/licencia-MIT-green)

[Qué hace](#-qué-hace) · [Instalar con Claude](#-instalación-con-claude-recomendada) · [Instalar a mano](#-instalación-a-mano) · [Cómo funciona](#-cómo-funciona-por-dentro) · [Configuración](#-configuración)

</div>

---

## ✨ Qué hace

| | Función | Detalle |
|---|---|---|
| 📤 | **Publica** | Sube tus productos (título, precio, fotos, descripción) desde un panel web, sin repetir ninguno |
| 🔄 | **Renueva** | Renueva solo los anuncios viejos para que vuelvan a salir arriba |
| ♻️ | **Recrea** | Si un anuncio no tiene clics, la IA le escribe otro título y otra descripción, lo publica de nuevo y borra el viejo |
| 💬 | **Responde** | Contesta a los compradores **con tu forma de escribir**, negocia sin bajar de tu precio mínimo y les pide el número |
| 📱 | **Te avisa** | Te manda a Telegram cada contacto con su enlace de WhatsApp. Lo controlas desde ahí, incluso con **notas de voz** |
| 🟢 | **Se cuida solo** | Un ícono junto al reloj mantiene todo encendido: verde = bien · amarillo = atención · rojo = se cerró la sesión de Facebook |

> 💸 **Cuesta $0.** La IA usa [Groq](https://console.groq.com), que tiene modelos gratis (`gpt-oss-120b` para escribir y `whisper` para las notas de voz). Funciona en PCs modestas.

---

## 🤖 Instalación con Claude (recomendada)

Este repositorio está pensado para que **[Claude Code](https://claude.com/claude-code) lo lea y lo instale por ti**.
El archivo [`CLAUDE.md`](CLAUDE.md) le explica a Claude todo el proyecto: qué hace cada archivo, cómo se configura y qué cuidados tener.
Tú solo conversas con él.

```bash
git clone https://github.com/greusdorian-pixel/marketplace-bot.git ~/marketplace-bot
cd ~/marketplace-bot
claude
```

Y le escribes, así de simple:

> **«Instálame este bot y ayúdame a configurarlo»**

Claude instala todo, te pide tu clave de Groq, te ayuda a crear el bot de Telegram, llena `negocio.json` con tus datos y prueba que funcione.
Después le puedes seguir pidiendo cosas:

> «Te dejé fotos en la carpeta nuevos, agrégalas como productos»  
> «¿Por qué no se publicó el taladro?»  
> «Cambia el horario de respuestas hasta las 9 de la noche»

### ¿Con Claude o a mano?

| | 🤖 Con Claude | 🛠️ A mano |
|---|---|---|
| **Instalar** | Le dices «instálalo» y listo | Correr comandos y editar 5 archivos JSON |
| **Configurar** | Te pregunta tus datos en una conversación | Leer la guía y llenar cada campo |
| **Agregar productos** | Dejas fotos en `nuevos/`; él identifica el producto, busca precios de tienda, redimensiona las fotos y lo agrega | Escribir cada producto en `productos.json` y preparar las fotos |
| **Si algo falla** | Lee los registros y las capturas de error y lo arregla | Revisar `logs/` por tu cuenta |
| **Cambios al bot** | «Haz que responda más corto» | Editar el código Python |
| **Tiempo** | ⚡ Minutos | ⏳ Una tarde |
| **Necesitas saber programar** | No | Un poco (terminal y JSON) |

Las dos formas dan el mismo bot. La diferencia es quién hace el trabajo.

---

## 🛠️ Instalación a mano

**Requisitos:** Linux con escritorio (probado en Linux Mint y Ubuntu), Python 3.10+, [Brave](https://brave.com/linux/) y `git`.

```bash
git clone https://github.com/greusdorian-pixel/marketplace-bot.git ~/marketplace-bot
cd ~/marketplace-bot
./instalar.sh
```

`instalar.sh` crea el entorno de Python (`.venv`), instala las dependencias y copia los archivos de [`ejemplos/`](ejemplos) a la carpeta principal.
Usa [uv](https://docs.astral.sh/uv/) si lo tienes; si no, necesita `python3-venv` (`sudo apt install python3-venv`).
Para el ícono junto al reloj puede hacer falta `sudo apt install gir1.2-ayatanaappindicator3-0.1`.

Después sigue la sección [Configuración](#-configuración).

---

## 🧠 Cómo funciona por dentro

```
                         ┌──────────────────────────┐
  Al prender la PC  ───► │  bandeja.py  (ícono 🟢)   │  mantiene todo vivo
                         └────────────┬─────────────┘
          ┌───────────────────────────┼────────────────────────────┐
          ▼                           ▼                            ▼
   panel.py :8765              telegram_bot.py               mensajes.py
   (tu panel web)              (tú ⇄ el bot)                 (cada 4–8 min)
     │        │                  │      │                      │
     ▼        ▼                  ▼      ▼                      ▼
 publicar.py  revisar.py      comandos  asistente IA     lee la bandeja de
 (publicar)   (renovar /      /estado   + notas de voz   Marketplace, responde
              recrear)        /pausa…                    y te avisa los contactos
          │         │                                          │
          └─────────┴──────────────┬───────────────────────────┘
                                   ▼
                  🦁 Brave propio del bot (perfil-brave/)
                  controlado con Playwright por el puerto 9222
                                   │
                                   ▼
                        Facebook Marketplace

  systemd (opcional): revisar.py todos los días a las 10:00 y 17:00
  IA: ia.py ──► Groq (gratis)
```

- **Brave propio:** inicias sesión en Facebook **una sola vez** en el Brave del bot y él reutiliza la sesión. Tu Brave normal no se toca.
- **Un candado compartido** evita que dos partes usen Facebook al mismo tiempo.
- **Seguro contra duplicados:** si no se confirma que un anuncio salió, lo marca como «verificar» en vez de publicarlo otra vez.
- **Solo toca lo suyo:** únicamente los anuncios y chats de los productos del bot. Tus otros anuncios quedan intactos.
- **Va despacio a propósito:** usa pausas aleatorias y límites por día para comportarse como una persona.

| Archivo | Qué hace |
|---|---|
| [`publicar.py`](publicar.py) | Llena el formulario de Marketplace y publica. Comprueba la sesión y reintenta |
| [`revisar.py`](revisar.py) | Gestor IA: renueva y recrea anuncios. `--simular` muestra qué haría sin tocar nada |
| [`mensajes.py`](mensajes.py) | Responde a los compradores. `--simular` no escribe nada |
| [`telegram_bot.py`](telegram_bot.py) | Comandos `/estado` `/revisar` `/simular` `/pausa` `/activar` `/registro`, botones ✅/❌, notas de voz y charla libre |
| [`panel.py`](panel.py) + [`panel.html`](panel.html) | Panel web local: productos, publicar, estado de la sesión, gestor IA |
| [`bandeja.py`](bandeja.py) | Ícono en la barra del sistema |
| [`ia.py`](ia.py) | Conexión con Groq y datos del negocio |
| [`catalogo.py`](catalogo.py), [`preparar.py`](preparar.py) | Extras: catálogo en PDF y preparación de fotos |

---

## ⚙️ Configuración

Ninguno de estos archivos se sube a GitHub: están en [`.gitignore`](.gitignore). Tus claves y tus datos se quedan en tu PC.

<details>
<summary><b>1. <code>config_ia.json</code>: clave de Groq y reglas</b></summary>

Crea una clave gratis en <https://console.groq.com/keys> y pégala en `"groq_api_key"` (o usa la variable de entorno `GROQ_API_KEY`).

| Ajuste | Qué significa |
|---|---|
| `dias_renovar` | Renovar un anuncio cada tantos días |
| `recrear`, `dias_recrear`, `clics_max_recrear` | Recrear anuncios con más de X días y menos de Y clics |
| `dias_sin_clics` | Si tiene **0 clics**, recrearlo desde este día |
| `max_recrear_por_dia`, `max_renovar_por_vez` | Límites para no exagerar |
| `chat.modo` | `auto` = responde solo · `aprobar` = te pide el OK por Telegram · `pausa` |
| `chat.rebaja_max` | Máximo de rebaja en dólares (en productos de menos de $30 se usa `rebaja_max_pct_baratos` %) |
| `chat.horario` | Horas en que responde |
</details>

<details>
<summary><b>2. <code>negocio.json</code>: tu negocio</b></summary>

Ciudad, país, cómo entregas, puntos de encuentro, forma de pago y, si quieres, tu teléfono. La IA usa estos datos para responder.
Mira el ejemplo en [`ejemplos/negocio.json`](ejemplos/negocio.json).
</details>

<details>
<summary><b>3. <code>productos.json</code>: tu catálogo</b></summary>

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
</details>

<details>
<summary><b>4. <code>estilo_dueno.json</code> y <code>estilo_conversaciones.json</code>: cómo hablas tú</b></summary>

Frases tuyas y pares reales «comprador → tú». La IA los imita para sonar como tú y no como un robot. Cuantos más ejemplos reales, mejor.
</details>

<details>
<summary><b>5. <code>telegram.json</code>: avisos al celular (recomendado)</b></summary>

1. En Telegram habla con **@BotFather**, escribe `/newbot` y copia el token en `"token"`.
2. Abre el panel una vez: se crea `clave_panel.txt` con una clave.
3. Mándale a tu bot `/start <la clave>`. Desde ese momento solo te obedece a ti.
</details>

---

## 🚀 Uso

```bash
./abrir_panel.sh     # abre el panel → http://127.0.0.1:8765
./iniciar_bot.sh     # ícono + Telegram + respondedor
./apagar_panel.sh    # apaga el panel
```

La **primera vez** publica desde el panel: se abre el Brave del bot, inicias sesión en Facebook y listo.

**Probar sin tocar nada:**
```bash
.venv/bin/python revisar.py --simular     # qué renovaría o recrearía
.venv/bin/python mensajes.py --simular    # qué respondería
```

<details>
<summary><b>Que arranque solo al prender la PC</b></summary>

Crea `~/.config/autostart/bot-marketplace.desktop`:
```ini
[Desktop Entry]
Type=Application
Name=Bot Marketplace
Exec=/home/TU_USUARIO/marketplace-bot/iniciar_bot.sh
X-GNOME-Autostart-enabled=true
```

Y para que el gestor IA revise dos veces al día:
```bash
mkdir -p ~/.config/systemd/user
cp systemd/marketplace-ia.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now marketplace-ia.timer
```
</details>

Los registros están en `logs/`: `ia.log`, `mensajes.log`, `panel.log` y `bandeja.log`.

---

## 🤝 Pasárselo a otra persona

Cada persona clona el repositorio en **su** PC y pone **sus propios** datos: clave de Groq, bot de Telegram, `negocio.json` y productos.
Nadie comparte claves ni sesiones de Facebook. Con Claude Code basta con decirle «instálalo».

## ❓ Preguntas frecuentes

<details>
<summary><b>¿Funciona en Windows o Mac?</b></summary>
Está hecho y probado en Linux. El código de Facebook es Python + Playwright y funcionaría en otros sistemas, pero los scripts <code>.sh</code>, el ícono y el arranque automático son de Linux. Claude puede adaptarlo si se lo pides.
</details>

<details>
<summary><b>¿Facebook lo puede detectar?</b></summary>
Automatizar Facebook va contra sus términos de uso. El bot va lento y con límites para parecer una persona, pero úsalo con moderación y bajo tu responsabilidad.
</details>

<details>
<summary><b>Dejó de funcionar después de un tiempo</b></summary>
Facebook cambia su página a veces. Los selectores están pensados para Facebook <b>en español</b>. Mira las capturas <code>logs/error_*.png</code>, o pídele a Claude que lo revise.
</details>

<details>
<summary><b>Me sale error 429</b></summary>
Es el límite por minuto de Groq gratis. El bot espera solo y, si sigue saturado, usa un modelo más liviano.
</details>

---

<div align="center">

**Licencia [MIT](LICENSE)**: úsalo, cámbialo y compártelo.

Hecho en Ecuador 🇪🇨 con ayuda de [Claude Code](https://claude.com/claude-code)

</div>
