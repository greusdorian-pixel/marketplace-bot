#!/bin/bash
# Instalación inicial: crea el entorno de Python y copia los archivos de ejemplo.
set -e
cd "$(dirname "$(readlink -f "$0")")"
command -v brave-browser >/dev/null || command -v brave >/dev/null || echo "⚠ Instala Brave: https://brave.com/linux/"
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -q -r requirements.txt
for f in productos publicados negocio config_ia telegram estilo_dueno estilo_conversaciones; do
    [ -f "$f.json" ] || cp "ejemplos/$f.json" "$f.json"
done
chmod 600 telegram.json config_ia.json
mkdir -p fotos nuevos logs
chmod +x *.sh
echo "✅ Listo. Ahora edita negocio.json, config_ia.json (clave de Groq) y productos.json."
echo "   Luego abre el panel con ./abrir_panel.sh"
