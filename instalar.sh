#!/bin/bash
# Instalación inicial: crea el entorno de Python y copia los archivos de ejemplo.
set -e
cd "$(dirname "$(readlink -f "$0")")"
command -v brave-browser >/dev/null || command -v brave >/dev/null || echo "⚠ Instala Brave: https://brave.com/linux/"
UV=$(command -v uv || echo "$HOME/.local/bin/uv")
if [ -x "$UV" ]; then
    "$UV" venv -q --system-site-packages .venv
    "$UV" pip install -q --python .venv/bin/python -r requirements.txt
elif python3 -m venv --system-site-packages .venv 2>/dev/null; then
    .venv/bin/pip install -q -r requirements.txt
else
    rm -rf .venv
    echo "❌ Falta el módulo venv. Instálalo con:  sudo apt install python3-venv"
    echo "   (o instala uv:  curl -LsSf https://astral.sh/uv/install.sh | sh ) y vuelve a correr ./instalar.sh"
    exit 1
fi
for f in productos publicados negocio config_ia telegram estilo_dueno estilo_conversaciones; do
    [ -f "$f.json" ] || cp "ejemplos/$f.json" "$f.json"
done
chmod 600 telegram.json config_ia.json
mkdir -p fotos nuevos logs
chmod +x *.sh
echo "✅ Listo. Ahora edita negocio.json, config_ia.json (clave de Groq) y productos.json."
echo "   Luego abre el panel con ./abrir_panel.sh"
