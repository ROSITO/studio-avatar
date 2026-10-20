#!/bin/zsh
# Start the local studio and open it in the default browser.
cd "${0:A:h}"
( sleep 1.5; open "http://localhost:${STUDIO_PORT:-8765}" ) &
exec python3 studio.py
