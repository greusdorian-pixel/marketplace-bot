#!/bin/bash
# Arranca el bot de Marketplace (ícono junto al reloj + panel + Telegram) sin consola.
cd "$(dirname "$(readlink -f "$0")")" || exit 1
export PYTHONIOENCODING=utf-8
nohup .venv/bin/python bandeja.py >/dev/null 2>&1 &
