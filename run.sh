#!/usr/bin/env bash
python3 -m venv venv
source venv/bin/activate
pip install flask

set -e
python3 app.py
