# Marketplace Bot: guía para Claude

Bot que vende productos en **Facebook Marketplace** con IA gratis (Groq). Corre en una PC Linux con escritorio (X11).
El usuario normalmente habla **español** y puede no saber programar: responde en español, claro y corto, y haz tú el trabajo técnico.

## Si te piden «instálalo» / «configúralo»

Hazlo de principio a fin, preguntando solo lo que no puedes averiguar:

1. Revisa los requisitos: `python3 --version` (≥3.10), Brave (`brave-browser`) y `git`. Si falta algo que necesita `sudo`,
   dale al usuario el comando exacto para que lo ejecute él (en Claude Code: `! sudo apt install …`).
2. Ejecuta `./instalar.sh` (crea `.venv`, instala `requirements.txt` y copia `ejemplos/*.json` a la raíz sin pisar los que ya existen).
3. **Clave de Groq:** pídele que cree una gratis en https://console.groq.com/keys y guárdala en `config_ia.json` → `groq_api_key`.
   Nunca la muestres completa ni la subas a git.
4. **`negocio.json`:** pregúntale ciudad, país, cómo entrega, puntos de encuentro, forma de pago y si quiere dar su teléfono (es opcional).
5. **Telegram (recomendado):** guíalo con @BotFather (`/newbot`), guarda el token en `telegram.json` (permisos 600), arranca el panel
   para que se cree `clave_panel.txt` y dile que le mande `/start <clave>` a su bot.
6. **Estilo:** pídele 5–15 mensajes reales suyos a compradores para `estilo_dueno.json` y pares comprador→dueño para
   `estilo_conversaciones.json`. Mejoran mucho las respuestas.
7. **Productos:** si tiene fotos, que las deje en `nuevos/` y sigue «Agregar mercadería nueva».
8. Prueba con `./abrir_panel.sh`. Dile que la **primera vez** inicie sesión en Facebook en el Brave que abre el bot.
9. Si lo quiere automático, configura el autostart y el timer de systemd (ver README).
10. Simula con `.venv/bin/python revisar.py --simular` y `mensajes.py --simular` antes de dejarlo en real.

## Mapa

```
bandeja.py (ícono; proceso principal, arranca con iniciar_bot.sh)
 ├─ panel.py → http://127.0.0.1:8765 (panel.html) ─ lanza publicar.py y revisar.py
 ├─ hilo telegram_bot.escuchar     comandos y asistente() del dueño
 ├─ hilo telegram_bot.vigilar_registro   resume logs/ia.log → Telegram
 └─ hilo mensajes.py cada 4–8 min dentro de chat.horario
systemd --user marketplace-ia.timer → revisar.py >> logs/ia.log
Todo lo que toca Facebook: publicar.abrir_brave() → Brave --user-data-dir=perfil-brave --remote-debugging-port=9222,
Playwright por CDP. Candado compartido: publicar.candado_brave() (logs/.brave.lock).
```

| Archivo | Contenido |
|---|---|
| `productos.json` | `id` "NN", `titulo`, `precio` int, `categoria`, `estado`, `descripcion`, `fotos[]` (`fotos/NN/…`), opcional `precio_minimo` |
| `publicados.json` | `{id: {titulo, fecha, manual?, verificar?, titulo_fb?}}` |
| `negocio.json` | Datos del negocio que usa la IA (`ia.negocio()`) |
| `config_ia.json` | Gestor (días, clics, límites), `groq_api_key`, `chat` (modo `auto/aprobar/pausa`, rebajas, horario) |
| `chats.json`, `historial_ia.json`, `tg_*.json` | Estado de ejecución (privado) |
| `telegram.json`, `clave_panel.txt` | **Secretos**: no mostrarlos ni subirlos |

## Agregar mercadería nueva (fotos en `nuevos/`)

Mira las fotos, identifica cada producto (marca, modelo, medidas), busca precios en tiendas y ponlos como «Precio en tienda: $X - $Y».
Precio de remate ~10–15 % menos (el dueño negocia). Pon primero la mejor foto, redimensiona a ≤1400 px en `fotos/NN/` y agrega
el producto a `productos.json` con el siguiente id. Descripción: nombre - marca, viñetas «- », «Precio en tienda», «Remate por
liquidación. Precio negociable.», «Pregunta por disponibilidad.». No borres ni muevas las fotos originales sin preguntar.

## Selectores de Facebook (en español)

- Ventas: `https://www.facebook.com/marketplace/you/selling`. Tarjetas `[role=button][aria-label*='clic']` con
  «Título, 120 $, Disponible, Publicado el 22/10, …, 6 clics en la publicación». Carga perezosa: hay que hacer scroll.
- Menú `[aria-label="Más opciones de {título}"]` → `Renovar publicación`, `Editar publicación`, `Eliminar publicación`.
- Bandeja `https://www.facebook.com/marketplace/inbox/`: filas `div[role=main] div[role=button]`. El chat es un popup
  `[role=log][aria-label="Mensajes de la conversación llamada {Nombre} · {Producto}"]` y la caja de texto es «Escribe en …».
- Si Facebook cambia algo, revisa `logs/error_*.png` y ajusta los selectores en `publicar.py`, `revisar.py` o `mensajes.py`.

## Reglas importantes

- La IA es **Groq gratis**. Ante un 429, `ia.json_chat` espera y cae a `openai/gpt-oss-20b`. No cambies a APIs de pago sin que lo pidan.
- Precio mínimo = precio − `rebaja_max` (en productos de menos de $30, máximo `rebaja_max_pct_baratos` %) o `precio_minimo`.
  El código bloquea respuestas por debajo del mínimo: no quites esa protección.
- Solo tocar anuncios y chats de productos del bot. El usuario puede tener otros anuncios propios.
- No publiques, renueves ni borres en Facebook por tu cuenta: eso lo hace el bot cuando el usuario lo pide desde el panel,
  el timer o Telegram. Leer páginas para revisar sí está bien.
- Escrituras JSON atómicas (`.tmp` + `os.replace`). No guardes capturas de la página de login (pueden mostrar la contraseña).
- No uses `pkill -f` con un patrón que también aparezca en tu propio comando de bash: mata tu propia shell.

## Probar

```bash
.venv/bin/python revisar.py --simular
.venv/bin/python mensajes.py --simular      # abre chats → quedan como «vistos»
./iniciar_bot.sh
systemctl --user list-timers marketplace-ia.timer
tail -f logs/mensajes.log logs/ia.log
```
