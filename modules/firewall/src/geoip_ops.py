import datetime
import gzip
import ipaddress
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

# DB-IP Country Lite (CC-BY 4.0, https://db-ip.com) -- base de geolocalização,
# não de registro RIR: bloco de cloud registrado nos EUA mas servido do Brasil
# (ex.: AWS sa-east-1) aparece como BR aqui. Um arquivo por mês, mundo inteiro.
DBIP_URL_TEMPLATE = "https://download.db-ip.com/free/dbip-country-lite-{month}.csv.gz"
SOURCE_LABEL = "DB-IP Country Lite, localização"
GEOLOC_URL_TEMPLATE = "https://stat.ripe.net/data/geoloc/data.json?resource={ip}&sourceapp=pvx-firewall"

# abaixo desse percentual do total anterior, a resposta é tratada como
# incompleta -- a fonte devolver "menos da metade do que já confiávamos antes"
# é mais provável ser erro transitório da API do que uma realocação real.
MIN_RATIO_VS_PREVIOUS = 0.5


class GeoIPError(Exception):
    pass


def _download_dbip(timeout):
    # o arquivo do mês corrente só sai uns dias depois da virada -- cai pro anterior.
    this_month = datetime.date.today().replace(day=1)
    last_month = this_month - datetime.timedelta(days=1)
    for month in (this_month, last_month):
        url = DBIP_URL_TEMPLATE.format(month=month.strftime("%Y-%m"))
        try:
            # DB-IP devolve 403 pro User-Agent padrão do urllib (achado ao vivo).
            request = urllib.request.Request(url, headers={"User-Agent": "pvx-firewall"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return gzip.decompress(response.read()).decode()
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise GeoIPError(f"falha ao baixar a base DB-IP ({url}): {e}")
        except (urllib.error.URLError, OSError) as e:
            raise GeoIPError(f"falha ao baixar a base DB-IP ({url}): {e}")
    raise GeoIPError("base DB-IP não encontrada nem pro mês atual nem pro anterior")


def fetch_country_ranges(country_codes, timeout=60):
    wanted = {cc.upper() for cc in country_codes}
    ranges = {cc: [] for cc in wanted}
    for line in _download_dbip(timeout).splitlines():
        if not line.strip():
            continue
        try:
            start, end, cc = line.strip().split(",")
            if cc not in wanted or ":" in start:
                continue
            networks = ipaddress.summarize_address_range(ipaddress.ip_address(start), ipaddress.ip_address(end))
        except ValueError as e:
            raise GeoIPError(f"linha inválida na base DB-IP ({line!r}): {e}")
        ranges[cc].extend(str(net) for net in networks)
    return ranges


def lookup_ip_country(ip, timeout=10):
    # consulta ao vivo (RIPEstat geoloc) -- diferente de fetch_country_ranges,
    # é IP -> país, não país -> ranges. Usado só por `geo test` (diagnóstico
    # manual, sob demanda) -- nunca por apply/sync, que continuam offline.
    url = GEOLOC_URL_TEMPLATE.format(ip=ip)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode())
    except (urllib.error.URLError, OSError) as e:
        raise GeoIPError(f"falha ao consultar a RIPE pra {ip}: {e}")
    except json.JSONDecodeError as e:
        raise GeoIPError(f"resposta inválida da RIPE pra {ip}: {e}")

    try:
        located_resources = payload["data"]["located_resources"]
    except (KeyError, TypeError) as e:
        raise GeoIPError(f"formato inesperado na resposta da RIPE pra {ip}: {e}")

    for entry in located_resources:
        locations = entry.get("locations") or []
        if locations:
            return {"country": locations[0]["country"], "resource": entry.get("resource")}
    return None


def validate_ranges(country_code, new_ranges, previous_count=None):
    if not new_ranges:
        return False, f"{country_code}: resposta vazia da DB-IP, mantendo cache anterior"
    if previous_count and len(new_ranges) < previous_count * MIN_RATIO_VS_PREVIOUS:
        return False, (
            f"{country_code}: resposta com {len(new_ranges)} range(s), menos da metade "
            f"das {previous_count} anteriores -- mantendo cache anterior"
        )
    return True, None


def _ranges_path(state_dir, country_code):
    return Path(state_dir) / "geo_ranges" / f"{country_code.upper()}.txt"


def read_cached_ranges(state_dir, country_code):
    path = _ranges_path(state_dir, country_code)
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def cache_updated_at(state_dir, country_code):
    path = _ranges_path(state_dir, country_code)
    if not path.exists():
        return None
    return datetime.datetime.fromtimestamp(path.stat().st_mtime)


def _write_ranges(state_dir, country_code, ranges):
    path = _ranges_path(state_dir, country_code)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text("\n".join(ranges) + ("\n" if ranges else ""))
    os.replace(tmp_path, path)


def refresh(countries, state_dir):
    results = {}
    try:
        fetched = fetch_country_ranges(countries)
    except GeoIPError as e:
        for country_code in countries:
            previous = read_cached_ranges(state_dir, country_code)
            results[country_code] = {"accepted": False, "count": len(previous), "reason": str(e)}
        return results

    for country_code in countries:
        previous = read_cached_ranges(state_dir, country_code)
        new_ranges = fetched.get(country_code.upper(), [])
        ok, reason = validate_ranges(country_code, new_ranges, previous_count=len(previous))
        if ok:
            _write_ranges(state_dir, country_code, new_ranges)
            results[country_code] = {"accepted": True, "count": len(new_ranges), "reason": None}
        else:
            results[country_code] = {"accepted": False, "count": len(previous), "reason": reason}
    return results
