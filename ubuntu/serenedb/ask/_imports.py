"""Shared imports for ask zone modules."""
from __future__ import annotations

import contextvars
import csv
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Шаг «достаточен ли вопрос для ответа» вынесен ОТДЕЛЬНЫМ файлом (05.08): его правила —
# чистые функции от разбора вопроса и от посчитанных чисел, и такие проверяются оффлайн,
# без базы, сети и денег (`test_enough.py`). Здесь остаётся только то, чего в чистой
# функции быть не может: обращение к модели, к базе и к гейту.
# Отсутствие файла (раскладка прежним `deploy.sh`) гасит шаг, а не роняет сервис: отказ
# при живых данных — дефект (п. 21), и он был бы куда хуже отключённой проверки.
try:
    import serene_enough
except ImportError:                                # noqa: F401 — шаг просто выключен
    serene_enough = None
import ask_choice_mem as ACM
import partial_visible as PV
try:
    import serene_axis
except ImportError:
    serene_axis = None
try:
    import entity_rank_v2 as K6R
except ImportError:
    K6R = None
