#!/bin/bash
# Apaga el panel de Marketplace.
pkill -f "python panel.py --sin-navegador"
notify-send "Marketplace" "Panel apagado" 2>/dev/null
