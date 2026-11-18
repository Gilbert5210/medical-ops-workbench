#!/bin/zsh
cd -- "${0:A:h}"
.venv/bin/python scripts/manage.py stop
