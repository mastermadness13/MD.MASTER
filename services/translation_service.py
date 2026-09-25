from __future__ import annotations

import json
import urllib.parse
import urllib.request

_TRANSLATION_URL = 'https://translate.googleapis.com/translate_a/single'


def translate_ar_to_en(text: str) -> str:
    value = str(text or '').strip()
    if not value:
        return ''
    params = urllib.parse.urlencode({
        'client': 'gtx',
        'sl': 'ar',
        'tl': 'en',
        'dt': 't',
        'q': value,
    })
    request = urllib.request.Request(
        _TRANSLATION_URL + '?' + params,
        headers={'User-Agent': 'Mozilla/5.0'},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode('utf-8'))
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        raise ValueError('invalid translation response')
    return ''.join(
        segment[0] for segment in payload[0]
        if isinstance(segment, list) and segment and segment[0]
    ).strip()


def safe_translate_ar_to_en(text: str) -> str:
    try:
        return translate_ar_to_en(text)
    except Exception:
        return ''
