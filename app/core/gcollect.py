"""
GA4 g/collect hit sender with Decodo country-targeted proxy routing.
"""

import requests
import time
import random
import os
import logging

log = logging.getLogger(__name__)

PROXY_USER = os.getenv("PROXY_USER", "spunb2abdt")
PROXY_PASS = os.getenv("PROXY_PASS", "")
PROXY_HOST = os.getenv("PROXY_HOST", "gate.decodo.com")
PROXY_PORT = os.getenv("PROXY_PORT", "7000")

LANG_MAP = {
    "DE": "de-DE,de;q=0.9", "PL": "pl-PL,pl;q=0.9", "FR": "fr-FR,fr;q=0.9",
    "IT": "it-IT,it;q=0.9", "ES": "es-ES,es;q=0.9", "CZ": "cs-CZ,cs;q=0.9",
    "SK": "sk-SK,sk;q=0.9", "HU": "hu-HU,hu;q=0.9", "RO": "ro-RO,ro;q=0.9",
    "UA": "uk-UA,uk;q=0.9", "GB": "en-GB,en;q=0.9", "NL": "nl-NL,nl;q=0.9",
    "BE": "nl-BE,nl;q=0.9", "AT": "de-AT,de;q=0.9", "CH": "de-CH,de;q=0.9",
    "SE": "sv-SE,sv;q=0.9", "NO": "nb-NO,nb;q=0.9", "DK": "da-DK,da;q=0.9",
    "FI": "fi-FI,fi;q=0.9", "PT": "pt-PT,pt;q=0.9", "GR": "el-GR,el;q=0.9",
    "US": "en-US,en;q=0.9", "TR": "tr-TR,tr;q=0.9", "BG": "bg-BG,bg;q=0.9",
    "HR": "hr-HR,hr;q=0.9", "RS": "sr-RS,sr;q=0.9",
}

SOURCE_REFERRERS = {
    "google":    "https://www.google.com/",
    "instagram": "https://www.instagram.com/",
    "facebook":  "https://www.facebook.com/",
    "twitter":   "https://twitter.com/",
    "youtube":   "https://www.youtube.com/",
}

SOURCE_MEDIUMS = {
    "organic":  ("google",    "organic"),
    "social":   ("instagram", "social"),
    "direct":   (None,        None),
    "referral": (None,        "referral"),
    "cpc":      ("google",    "cpc"),
    "email":    ("newsletter","email"),
}


def get_proxy(country_code: str) -> dict:
    if not PROXY_PASS:
        return None
    from urllib.parse import quote
    cc = country_code.lower()
    user = quote("user-" + PROXY_USER + "-country-" + cc, safe="")
    password = quote(PROXY_PASS, safe="")
    url = "http://" + user + ":" + password + "@" + PROXY_HOST + ":" + PROXY_PORT
    return {"http": url, "https": url}


def send_hit(
    tid: str,
    site_url: str,
    country_code: str,
    traffic_source: str = "organic",
    campaign: str = None,
    gtm_id: str = None,
) -> dict:
    source, medium = SOURCE_MEDIUMS.get(traffic_source, ("google", "organic"))
    lang = LANG_MAP.get(country_code.upper(), "en-US,en;q=0.9")
    ul = lang.split(",")[0].lower()
    cid = str(random.randint(100000000, 999999999)) + "." + str(int(time.time()))
    ts = str(int(time.time() * 1000))

    dl = site_url
    if source and medium:
        sep = "&" if "?" in site_url else "?"
        dl = site_url + sep + "utm_source=" + source + "&utm_medium=" + medium
        if campaign:
            dl += "&utm_campaign=" + campaign

    dr = SOURCE_REFERRERS.get(source, "https://www.google.com/") if source else ""

    gtm_param = gtm_id if gtm_id else "45je6630v9232360688za200zd9232360688"

    params = {
        "v": "2", "tid": tid,
        "gtm": gtm_param,
        "_p": ts, "gcd": "13l3l3l3l1l1", "npa": "0", "dma": "0",
        "cid": cid, "frm": "0", "pscdl": "noapi",
        "sr": "1280x720", "uaa": "x86", "uab": "64",
        "uap": "Windows", "uapv": "10.0", "ul": ul,
        "_s": "1", "sid": str(int(time.time())), "sct": "1", "seg": "0",
        "dl": dl, "en": "page_view", "_ss": "1", "_fv": "1",
    }
    if dr:
        params["dr"] = dr

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept-Language": lang,
        "Referer": dr or site_url,
    }

    proxies = get_proxy(country_code)

    try:
        r = requests.get(
            "https://www.google-analytics.com/g/collect",
            params=params, headers=headers,
            proxies=proxies, timeout=15,
        )
        return {"status": r.status_code, "cid": cid, "country": country_code, "source": traffic_source}
    except Exception as e:
        log.error("Hit failed: %s", e)
        return {"status": 0, "error": str(e), "country": country_code, "source": traffic_source}


def pick_weighted(options: dict) -> str:
    """Pick a key from {key: weight%} dict randomly."""
    keys = list(options.keys())
    weights = [options[k] for k in keys]
    return random.choices(keys, weights=weights, k=1)[0]
