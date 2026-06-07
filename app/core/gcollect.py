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

# source_key -> (utm_source, utm_medium, referrer)
# Organic sources: NO utm params (source=None, medium=None), only referrer.
# Real organic traffic never has utm_* in the URL — GA4 attributes it via
# the Referer header alone. Adding UTMs to organic hits creates a conflict
# that GA4 cannot resolve → "Unassigned".
SOURCES = {
    # Organic Search — referrer only, no UTMs
    "google_organic":     (None,                    None,       "https://www.google.com/"),
    "bing_organic":       (None,                    None,       "https://www.bing.com/"),
    "duckduckgo_organic": (None,                    None,       "https://duckduckgo.com/"),
    "yahoo_organic":      (None,                    None,       "https://search.yahoo.com/"),
    "youtube_organic":    (None,                    None,       "https://www.youtube.com/"),
    # Paid — UTMs are correct here (real CPC traffic IS utm-tagged)
    "google_cpc":         ("google",                "cpc",      "https://www.google.com/"),
    # Social
    "instagram":          ("instagram",             "social",   "https://www.instagram.com/"),
    "facebook":           ("facebook",              "social",   "https://www.facebook.com/"),
    "linkedin":           ("linkedin",              "social",   "https://www.linkedin.com/"),
    "twitter":            ("twitter",               "social",   "https://twitter.com/"),
    "pinterest":          ("pinterest",             "social",   "https://www.pinterest.com/"),
    "tiktok":             ("tiktok",                "social",   "https://www.tiktok.com/"),
    # AI Chatbots (GA4 channel: Referral / AI)
    "chatgpt":            ("chatgpt.com",           "referral", "https://chatgpt.com/"),
    "perplexity":         ("perplexity.ai",         "referral", "https://www.perplexity.ai/"),
    "gemini":             ("gemini.google.com",     "referral", "https://gemini.google.com/"),
    "copilot":            ("copilot.microsoft.com", "referral", "https://copilot.microsoft.com/"),
    "grok":               ("grok.com",              "referral", "https://grok.com/"),
    # Messengers
    "whatsapp":           ("whatsapp",              "social",   None),
    "telegram":           ("telegram",              "social",   None),
    # Other
    "email":              ("newsletter",            "email",    None),
    "direct":             (None,                    None,       None),
    "referral":           ("referral",              "referral", "https://example.com/"),
}

# Legacy aliases
SOURCE_MEDIUMS = {k: (v[0], v[1]) for k, v in SOURCES.items()}
SOURCE_REFERRERS = {k: v[2] for k, v in SOURCES.items() if v[2]}


def get_proxy(country_code: str) -> dict:
    if not PROXY_PASS:
        log.warning("PROXY_PASS is empty — no proxy used")
        return None
    from urllib.parse import quote
    cc = country_code.lower()
    user = "user-" + PROXY_USER + "-country-" + cc   # dashes are safe, no encoding needed
    password = quote(PROXY_PASS, safe="")             # encode special chars like +
    url = "http://" + user + ":" + password + "@" + PROXY_HOST + ":" + PROXY_PORT
    log.info("Using proxy: http://%s:***@%s:%s", user, PROXY_HOST, PROXY_PORT)
    return {"http": url, "https": url}


DEVICE_PROFILES = {
    "desktop": {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "sr": "1280x720", "uaa": "x86", "uab": "64", "uap": "Windows", "uapv": "10.0", "uamb": "0",
    },
    "mobile": {
        "ua": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.60 Mobile Safari/537.36",
        "sr": "390x844", "uaa": "arm", "uab": "64", "uap": "Android", "uapv": "14.0", "uamb": "1",
    },
    "tablet": {
        "ua": "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "sr": "820x1180", "uaa": "arm", "uab": "64", "uap": "iOS", "uapv": "17.0", "uamb": "1",
    },
}


def send_hit(
    tid: str,
    site_url: str,
    country_code: str,
    traffic_source: str = "google_organic",
    campaign: str = None,
    gtm_id: str = None,
    device: str = "desktop",
) -> dict:
    src_data = SOURCES.get(traffic_source, SOURCES["google_organic"])
    source, medium, referrer = src_data
    lang = LANG_MAP.get(country_code.upper(), "en-US,en;q=0.9")
    ul = lang.split(",")[0].lower()
    cid = str(random.randint(100000000, 999999999)) + "." + str(int(time.time()))
    ts = str(int(time.time() * 1000))
    dev = DEVICE_PROFILES.get(device, DEVICE_PROFILES["desktop"])

    dl = site_url
    if source and medium:
        sep = "&" if "?" in site_url else "?"
        dl = site_url + sep + "utm_source=" + source + "&utm_medium=" + medium
        if campaign:
            dl += "&utm_campaign=" + campaign

    dr = referrer or ""
    gtm_param = gtm_id if gtm_id else "45je6630v9232360688za200zd9232360688"

    params = {
        "v": "2", "tid": tid,
        "gtm": gtm_param,
        "_p": ts, "gcd": "13l3l3l3l1l1", "npa": "0", "dma": "0",
        "cid": cid, "frm": "0", "pscdl": "noapi",
        "sr": dev["sr"], "uaa": dev["uaa"], "uab": dev["uab"],
        "uap": dev["uap"], "uapv": dev["uapv"], "uamb": dev["uamb"],
        "ul": ul,
        "_s": "1", "sid": str(int(time.time())), "sct": "1", "seg": "0",
        "dl": dl, "en": "page_view", "_ss": "1", "_fv": "1",
    }
    if dr:
        params["dr"] = dr

    headers = {
        "User-Agent": dev["ua"],
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
