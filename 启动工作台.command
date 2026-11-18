#!/bin/zsh
cd -- "${0:A:h}"
.venv/bin/python scripts/manage.py start
open 'http://127.0.0.1:18765'
