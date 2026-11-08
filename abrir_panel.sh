#!/bin/bash
# Abre el panel de Marketplace (http://127.0.0.1:8765) sin ventana de consola.
# Si ya está corriendo, solo abre el navegador.
cd "$(dirname "$(readlink -f "$0")")" || exit 1
URL=http://127.0.0.1:8765
abrir() {
    for b in brave-browser brave; do command -v "$b" >/dev/null && { "$b" "$URL" >/dev/null 2>&1 & return; }; done
    xdg-open "$URL" >/dev/null 2>&1 &
}
if curl -s -o /dev/null --max-time 1 "$URL/entrar"; then
    abrir
else
    mkdir -p logs
    PYTHONIOENCODING=utf-8 nohup .venv/bin/python panel.py --sin-navegador >> logs/panel.log 2>&1 &
    for _ in $(seq 20); do curl -s -o /dev/null --max-time 1 "$URL/entrar" && break; sleep 0.3; done
    abrir
fi
