"""Validate saved map links and derive Google Maps links for text addresses."""

import re
from urllib.parse import unquote, urlencode, urlsplit

MAX_MAP_URL_LENGTH = 2048
MAP_URL_ERROR = "請貼上有效的 Google Maps HTTPS 分享連結。"
GOOGLE_DOMAINS = ("google.com", "google.com.tw", "google.co.jp")
MAP_HOSTS = {f"maps.{domain}" for domain in GOOGLE_DOMAINS}
GOOGLE_HOSTS = set(GOOGLE_DOMAINS) | {f"www.{domain}" for domain in GOOGLE_DOMAINS}
URL_START = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|www\.|maps\.|goo\.gl/|google\.(?:com|co\.jp)/)", re.I)
SHARE_CODE = re.compile(r"[a-zA-Z0-9_-]+")


def looks_like_url(value: str) -> bool:
    return bool(URL_START.match(value.strip()))


def valid_map_url(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if len(value) > MAX_MAP_URL_LENGTH or re.search(r"[\s\x00-\x1f\x7f\\]", value):
        return None
    try:
        url = urlsplit(value)
    except ValueError:
        return None
    if url.scheme != "https":
        return None
    host = url.netloc.lower()
    path = unquote(url.path)
    if any(segment in (".", "..") for segment in path.split("/")):
        return None
    if host == "maps.app.goo.gl":
        allowed = SHARE_CODE.fullmatch(url.path.removeprefix("/").removesuffix("/"))
    elif host == "goo.gl":
        allowed = url.path.startswith("/maps/") and SHARE_CODE.fullmatch(url.path[len("/maps/"):].removesuffix("/"))
    else:
        is_maps_path = url.path == "/maps" or url.path.startswith("/maps/")
        allowed = (host in GOOGLE_HOSTS and is_maps_path) or (
            host in MAP_HOSTS and (is_maps_path or url.path in ("", "/"))
        )
    return value if allowed else None


def parse_location(address: str = "", map_url: str | None = None) -> dict:
    address = address.strip()
    link = valid_map_url(map_url)
    if map_url and map_url.strip() and not link:
        raise ValueError(MAP_URL_ERROR)
    if looks_like_url(address):
        address_link = valid_map_url(address)
        if not address_link:
            raise ValueError(MAP_URL_ERROR)
        if link and link != address_link:
            raise ValueError("請只填寫一個 Google Maps 連結。")
        return {"address": "", "map_url": address_link}
    if address and link:
        raise ValueError("請擇一填寫地址或 Google Maps 連結。")
    if len(address) > 1000:
        raise ValueError("地址不可超過 1000 字元。")
    return {"address": address, "map_url": link}


def stored_location(record: dict) -> dict:
    address = record.get("address") or ""
    link = valid_map_url(record.get("map_url")) or valid_map_url(address)
    return {"address": "" if link else address, "map_url": link}


def maps_destination(record: dict) -> str | None:
    location = stored_location(record)
    address = location["address"].strip()
    if location["map_url"] or not address or looks_like_url(address):
        return location["map_url"]
    city = (record.get("city") or "").strip()
    query = f"{city} {address}" if city and city not in address else address
    url = "https://www.google.com/maps/search/?" + urlencode({"api": 1, "query": query})
    return url if len(url) <= MAX_MAP_URL_LENGTH else None


def location_reference(record: dict) -> dict:
    address = stored_location(record)["address"]
    return {"address": "" if looks_like_url(address) else address, "map_url": maps_destination(record)}
