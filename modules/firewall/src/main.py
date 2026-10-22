import ipaddress
import json
import os
import sys

import click

from pvx import config as pvx_config
from pvx.interactive import widgets
from pvx.interactive.inputs import ask_confirm, ask_text
from pvx.modules.base import PvxModule

import asterisk_ips
import defaults
import geoip_ops
import ipset_ops
import lists
import log_ops
import session_ip
import status as status_module
import sync as sync_module
import systemd_unit
import validators
import webhook_ops

ENGINE_CHOICE = click.Choice(["iptables", "firewalld"])


def _state_dir():
    return pvx_config.modules_dir() / "firewall" / "state"


def _list_path(key):
    return _state_dir() / defaults.CONFIG_FILENAMES[key]


def _read(key):
    return lists.read_list(_list_path(key), seed=defaults.DEFAULT_LISTS[key])


def _is_interactive():
    return sys.stdin.isatty()


def _require_root():
    if os.geteuid() != 0:
        raise click.ClickException("firewall precisa rodar como root (sudo).")


def _resolve_arg(value, prompt, usage):
    if value is not None:
        return value
    if not _is_interactive():
        raise click.ClickException(usage)
    return ask_text(prompt)


def _humanize_bytes(n):
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.2f}{unit}"
        value /= 1024
    return f"{value:.2f}TB"


def _check_row(item_label, description_text, value, level):
    # item | descrição (o que esse item significa) | valor dinâmico -- o
    # "ok ou não" vem do símbolo/cor de check_result (nunca texto cru
    # "ok"/"falha", vocabulário do projeto é sempre sucesso/erro/aviso).
    widgets.check_result(f"{item_label:<20}{description_text:<68}{value}", level)


def _echo_list(label, entries):
    widgets.section(label)
    if not entries:
        widgets.description("(vazio)")
        return
    for entry, comment in entries:
        widgets.item(entry, comment)


class FirewallModule(PvxModule):
    name = "firewall"
    version = "0.2.31"

    def cli_group(self):
        @click.group(name="firewall")
        def group():
            pass

        @group.group(name="port", help="libera/bloqueia portas.")
        def port_group():
            pass

        @port_group.command(name="accept", help="libera uma porta/faixa.")
        @click.argument("spec", required=False, default=None)
        @click.option("--comment", default="")
        def port_accept_cmd(spec, comment):
            _require_root()
            spec = _resolve_arg(
                spec, "Porta/faixa (ex.: 5060/udp, 10000-20000/tcp):",
                "informe a porta: `pvx firewall port accept <spec> [--comment]`.",
            )
            if spec is None:
                return
            try:
                validators.parse_port_spec(spec)
            except ValueError as e:
                raise click.ClickException(str(e))
            lists.add_entry(_list_path("port_accept"), spec, comment, seed=defaults.DEFAULT_LISTS["port_accept"])
            click.echo(f"porta {spec} liberada.")
            if _is_interactive():
                widgets.pause()

        @port_group.command(name="deny", help="bloqueia uma porta/faixa.")
        @click.argument("spec", required=False, default=None)
        @click.option("--comment", default="")
        def port_deny_cmd(spec, comment):
            _require_root()
            spec = _resolve_arg(
                spec, "Porta/faixa (ex.: 5060/udp, 10000-20000/tcp):",
                "informe a porta: `pvx firewall port deny <spec> [--comment]`.",
            )
            if spec is None:
                return
            try:
                validators.parse_port_spec(spec)
            except ValueError as e:
                raise click.ClickException(str(e))
            lists.add_entry(_list_path("port_deny"), spec, comment, seed=defaults.DEFAULT_LISTS["port_deny"])
            click.echo(f"porta {spec} bloqueada.")
            if _is_interactive():
                widgets.pause()

        @port_group.command(name="remove", help="remove uma porta das listas de liberação/bloqueio.")
        @click.argument("spec", required=False, default=None)
        def port_remove_cmd(spec):
            _require_root()
            spec = _resolve_arg(
                spec, "Porta/faixa a remover:", "informe a porta: `pvx firewall port remove <spec>`.",
            )
            if spec is None:
                return
            removed = lists.remove_entry(_list_path("port_accept"), spec, seed=defaults.DEFAULT_LISTS["port_accept"])
            removed = lists.remove_entry(
                _list_path("port_deny"), spec, seed=defaults.DEFAULT_LISTS["port_deny"],
            ) or removed
            if not removed:
                raise click.ClickException(f"{spec} não está em nenhuma lista de portas.")
            click.echo(f"{spec} removido.")
            if _is_interactive():
                widgets.pause()

        @port_group.command(name="list", help="lista as portas liberadas e bloqueadas.")
        def port_list_cmd():
            _echo_list("Portas liberadas", _read("port_accept"))
            _echo_list("Portas bloqueadas", _read("port_deny"))
            if _is_interactive():
                widgets.pause()

        @group.group(name="ip", help="libera/bloqueia IPs e faixas (CIDR).")
        def ip_group():
            pass

        @ip_group.command(
            name="accept", help="adiciona um ou mais IP/CIDR (separados por vírgula) à lista de confiáveis.",
        )
        @click.argument("cidr", required=False, default=None)
        @click.option("--comment", default="")
        def ip_accept_cmd(cidr, comment):
            _require_root()
            cidr = _resolve_arg(
                cidr, "IP/CIDR (ex.: 203.0.113.9, 10.0.0.0/8 -- vários separados por vírgula):",
                "informe o CIDR: `pvx firewall ip accept <cidr>[,<cidr>...] [--comment]`.",
            )
            if cidr is None:
                return
            try:
                entries = validators.parse_cidr_list(cidr)
            except ValueError as e:
                raise click.ClickException(str(e))
            for entry in entries:
                added = lists.add_entry(_list_path("ip_accept"), entry, comment, seed=defaults.DEFAULT_LISTS["ip_accept"])
                verb = "adicionado à" if added else "já estava na"
                click.echo(f"{entry} {verb} lista de confiáveis.")
            if _is_interactive():
                widgets.pause()

        @ip_group.command(
            name="deny", help="adiciona um ou mais IP/CIDR (separados por vírgula) à lista de bloqueio.",
        )
        @click.argument("cidr", required=False, default=None)
        @click.option("--comment", default="")
        @click.option("--force", is_flag=True, help="ignora a checagem de auto-bloqueio")
        def ip_deny_cmd(cidr, comment, force):
            _require_root()
            cidr = _resolve_arg(
                cidr, "IP/CIDR (ex.: 203.0.113.9, 10.0.0.0/8 -- vários separados por vírgula):",
                "informe o CIDR: `pvx firewall ip deny <cidr>[,<cidr>...] [--comment] [--force]`.",
            )
            if cidr is None:
                return
            try:
                entries = validators.parse_cidr_list(cidr)
            except ValueError as e:
                raise click.ClickException(str(e))
            if not force:
                session = session_ip.detect_session_ip()
                if session:
                    session_addr = ipaddress.ip_address(session)
                    self_banning = [
                        entry for entry in entries
                        if session_addr in ipaddress.ip_network(entry, strict=False)
                    ]
                    if self_banning:
                        raise click.ClickException(
                            f"{', '.join(self_banning)} inclui o IP da sua sessão atual ({session}) -- "
                            "use --force se tiver certeza."
                        )
            for entry in entries:
                added = lists.add_entry(_list_path("ip_deny"), entry, comment, seed=defaults.DEFAULT_LISTS["ip_deny"])
                verb = "adicionado à" if added else "já estava na"
                click.echo(f"{entry} {verb} lista de bloqueio.")
            # best-effort, nunca falha o comando por causa do webhook.
            webhook_ops.notify(_state_dir(), "ip_deny", f"{', '.join(entries)} adicionado(s) à lista de bloqueio")
            if _is_interactive():
                widgets.pause()

        @ip_group.command(name="remove", help="remove um IP das listas de confiáveis/bloqueio.")
        @click.argument("cidr", required=False, default=None)
        def ip_remove_cmd(cidr):
            _require_root()
            cidr = _resolve_arg(
                cidr, "IP/CIDR a remover:", "informe o CIDR: `pvx firewall ip remove <cidr>`.",
            )
            if cidr is None:
                return
            removed = lists.remove_entry(_list_path("ip_accept"), cidr, seed=defaults.DEFAULT_LISTS["ip_accept"])
            removed = lists.remove_entry(
                _list_path("ip_deny"), cidr, seed=defaults.DEFAULT_LISTS["ip_deny"],
            ) or removed
            if not removed:
                raise click.ClickException(f"{cidr} não está em nenhuma lista de IPs.")
            click.echo(f"{cidr} removido.")
            if _is_interactive():
                widgets.pause()

        @ip_group.command(
            name="trust-phonevox",
            help="garante os IPs base da Phonevox na lista de confiáveis (upsert, nunca duplica).",
        )
        def ip_trust_phonevox_cmd():
            _require_root()
            added = []
            for ip, comment in defaults.DEFAULT_LISTS["ip_accept"]:
                if lists.add_entry(_list_path("ip_accept"), ip, comment, seed=defaults.DEFAULT_LISTS["ip_accept"]):
                    added.append(ip)

            if added:
                click.echo(f"{len(added)} IP(s) adicionado(s) à lista de confiáveis: {', '.join(added)}")
            else:
                click.echo("nenhum IP novo -- todos já estavam na lista de confiáveis.")
            if _is_interactive():
                widgets.pause()

        @ip_group.command(
            name="trust-asterisk",
            help="adiciona os IPs conectados no Asterisk à lista de confiáveis.",
        )
        def ip_trust_asterisk_cmd():
            _require_root()
            found = asterisk_ips.discover_asterisk_ips()
            if not found:
                click.echo("nenhum IP encontrado no Asterisk.")
                if _is_interactive():
                    widgets.pause()
                return

            added = []
            for ip, source in sorted(found.items()):
                if lists.add_entry(_list_path("ip_accept"), ip, source, seed=defaults.DEFAULT_LISTS["ip_accept"]):
                    added.append(ip)

            if added:
                click.echo(f"{len(added)} IP(s) adicionado(s) à lista de confiáveis: {', '.join(added)}")
            else:
                click.echo("nenhum IP novo -- todos já estavam na lista de confiáveis.")
            if _is_interactive():
                widgets.pause()

        @ip_group.command(name="list", help="lista os IPs confiáveis e bloqueados.")
        def ip_list_cmd():
            _echo_list("IPs confiáveis", _read("ip_accept"))
            _echo_list("IPs bloqueados", _read("ip_deny"))
            if _is_interactive():
                widgets.pause()

        def _refresh_geo(countries):
            logger = self.get_logger()
            with widgets.spinner("Baixando ranges da DB-IP..."):
                results = geoip_ops.refresh(countries, _state_dir())
            for cc, result in results.items():
                if result["accepted"]:
                    widgets.success(f"{cc}: {result['count']} range(s)")
                    logger.info(f"geo refresh {cc}: {result['count']} range(s)")
                else:
                    widgets.warning(result["reason"] or f"{cc}: falha ao atualizar")
                    logger.error(f"geo refresh {cc}: {result['reason']}")

        @group.group(name="geo", help="bloqueio geográfico (geoban) -- opt-in, só iptables por enquanto.")
        def geo_group():
            pass

        @geo_group.command(name="enable", help="liga o geoban com o padrão (só Brasil) -- idempotente.")
        @click.option("--yes", is_flag=True)
        def geo_enable_cmd(yes):
            _require_root()
            if not yes and not ask_confirm(
                "Isso vai bloquear todo acesso de fora do(s) país(es) configurado(s), em qualquer porta "
                "(exceto IPs já confiáveis), assim que `geo refresh` e `apply` rodarem. Confirma?",
                default=False,
            ):
                click.echo("Operação cancelada.")
                if _is_interactive():
                    widgets.pause()
                return

            added = []
            for cc, comment in defaults.DEFAULT_GEO_ACCEPT:
                if lists.add_entry(_list_path("geo_accept"), cc, comment, seed=defaults.DEFAULT_LISTS["geo_accept"]):
                    added.append(cc)
            if added:
                click.echo(f"geoban habilitado com: {', '.join(added)}.")
            else:
                click.echo("geoban já estava habilitado (nenhum país novo).")
            _refresh_geo([cc for cc, _ in _read("geo_accept")])
            click.echo("rode `pvx firewall apply` pra ter efeito.")
            if _is_interactive():
                widgets.pause()

        @geo_group.command(
            name="accept", help="adiciona um ou mais países (ISO 3166-1 alpha-2, separados por vírgula) à allowlist.",
        )
        @click.argument("countries", required=False, default=None)
        @click.option("--comment", default="")
        def geo_accept_cmd(countries, comment):
            _require_root()
            countries = _resolve_arg(
                countries, "País(es) ISO 3166-1 alpha-2 (ex.: BR, CA -- vários separados por vírgula):",
                "informe o país: `pvx firewall geo accept <CC>[,<CC>...] [--comment]`.",
            )
            if countries is None:
                return
            try:
                entries = validators.parse_country_list(countries)
            except ValueError as e:
                raise click.ClickException(str(e))
            for entry in entries:
                added = lists.add_entry(
                    _list_path("geo_accept"), entry, comment, seed=defaults.DEFAULT_LISTS["geo_accept"],
                )
                verb = "adicionado à" if added else "já estava na"
                click.echo(f"{entry} {verb} allowlist geográfica.")
            _refresh_geo(entries)
            click.echo("rode `pvx firewall apply` pra ter efeito.")
            if _is_interactive():
                widgets.pause()

        @geo_group.command(name="remove", help="remove um país da allowlist geográfica.")
        @click.argument("country", required=False, default=None)
        def geo_remove_cmd(country):
            _require_root()
            country = _resolve_arg(
                country, "País a remover:", "informe o país: `pvx firewall geo remove <CC>`.",
            )
            if country is None:
                return
            country = country.strip().upper()
            removed = lists.remove_entry(_list_path("geo_accept"), country, seed=defaults.DEFAULT_LISTS["geo_accept"])
            if not removed:
                raise click.ClickException(f"{country} não está na allowlist geográfica.")
            click.echo(f"{country} removido da allowlist geográfica.")
            if _is_interactive():
                widgets.pause()

        @geo_group.command(name="list", help="lista os países configurados e o estado do cache de ranges.")
        def geo_list_cmd():
            countries = _read("geo_accept")
            widgets.section(f"Geoban (fonte: {geoip_ops.SOURCE_LABEL})")
            if not countries:
                widgets.description("desligado -- nenhum país configurado (`geo enable` ou `geo accept <CC>`).")
            else:
                applied = ipset_ops.members(defaults.GEO_IPSET_NAME) if ipset_ops.available() else []
                if applied:
                    widgets.item("estado: ligado, aplicado", f"ipset {defaults.GEO_IPSET_NAME} com {len(applied)} entradas")
                else:
                    widgets.warning("estado: ligado, NÃO aplicado -- rode `pvx firewall apply`")
                for cc, comment in countries:
                    cached = geoip_ops.read_cached_ranges(_state_dir(), cc)
                    if not cached:
                        widgets.item(f"{cc}: sem cache", "rode `geo refresh`")
                        continue
                    total_ips = sum(ipaddress.ip_network(c, strict=False).num_addresses for c in cached)
                    updated = geoip_ops.cache_updated_at(_state_dir(), cc)
                    when = f"cache de {updated:%Y-%m-%d %H:%M}" if updated else "cache sem data"
                    widgets.item(
                        f"{cc}: {len(cached)} range(s), ~{total_ips / 1e6:.1f}M IPs",
                        f"{comment + ' -- ' if comment else ''}{when}",
                    )
            if _is_interactive():
                widgets.pause()

        @geo_group.command(name="refresh", help="baixa as ranges de IP dos países configurados (DB-IP) agora.")
        def geo_refresh_cmd():
            _require_root()
            countries = [cc for cc, _ in _read("geo_accept")]
            if not countries:
                click.echo("nenhum país configurado -- rode `geo enable` ou `geo accept <CC>` primeiro.")
                if _is_interactive():
                    widgets.pause()
                return
            _refresh_geo(countries)
            if _is_interactive():
                widgets.pause()

        @geo_group.command(
            name="test",
            help="diz de onde um IP é (consulta a RIPE ao vivo) e se passaria pelo geoban configurado.",
        )
        @click.argument("ip", required=False, default=None)
        def geo_test_cmd(ip):
            ip = _resolve_arg(ip, "IP a testar:", "informe o IP: `pvx firewall geo test <ip>`.")
            if ip is None:
                return
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                raise click.ClickException(f"IP inválido: {ip}")

            # consulta ao vivo -- sempre roda, mesmo com geoban desligado, pra
            # servir de diagnóstico ("de onde é esse IP?") independente de
            # qualquer bloqueio estar em vigor.
            try:
                lookup = geoip_ops.lookup_ip_country(ip)
            except geoip_ops.GeoIPError as e:
                widgets.warning(f"não consegui consultar a RIPE agora: {e}")
                lookup = None

            widgets.item(
                f"localização: {lookup['country']} ({lookup['resource']})" if lookup else "localização: não encontrada",
                comment="consulta ao vivo (RIPE geoloc)",
            )

            countries = [cc for cc, _ in _read("geo_accept")]
            if not countries:
                widgets.warning("geoban está desligado -- nenhum bloqueio em vigor agora (isso é só um teste).")
                if _is_interactive():
                    widgets.pause()
                return

            for cc in countries:
                for cidr in geoip_ops.read_cached_ranges(_state_dir(), cc):
                    if addr in ipaddress.ip_network(cidr, strict=False):
                        widgets.success(f"geoban: passaria -- está em {cc} ({cidr}), permitido.")
                        if _is_interactive():
                            widgets.pause()
                        return
            widgets.failed("geoban: seria bloqueado -- fora de todos os países permitidos.")
            if _is_interactive():
                widgets.pause()

        @group.group(name="logs", help="log detalhado de pacotes bloqueados (iptables).")
        def logs_group():
            pass

        @logs_group.command(name="enable", help="liga o log de pacotes bloqueados (rate-limited).")
        def logs_enable_cmd():
            _require_root()
            log_ops.enable(_state_dir())
            click.echo("log de pacotes bloqueados habilitado -- rode `pvx firewall apply` pra aplicar.")
            if _is_interactive():
                widgets.pause()

        @logs_group.command(name="disable", help="desliga o log de pacotes bloqueados.")
        def logs_disable_cmd():
            _require_root()
            log_ops.disable(_state_dir())
            click.echo("log de pacotes bloqueados desabilitado -- rode `pvx firewall apply` pra aplicar.")
            if _is_interactive():
                widgets.pause()

        @logs_group.command(name="show", help="mostra as últimas linhas de pacotes bloqueados.")
        @click.option("--tail", default=50, help="quantas linhas do journal do kernel considerar.")
        @click.option("--follow", is_flag=True, help="acompanha em tempo real (Ctrl+C pra sair).")
        def logs_show_cmd(tail, follow):
            if follow:
                log_ops.follow()
                return
            lines = log_ops.read_lines(tail=tail)
            if not lines:
                click.echo("nenhum pacote bloqueado registrado -- confira se `logs enable` + `apply` já rodaram.")
                if _is_interactive():
                    widgets.pause()
                return
            for line in lines:
                click.echo(line)
            if _is_interactive():
                widgets.pause()

        @group.group(name="webhook", help="notificação opcional (fire-and-forget) de eventos do firewall.")
        def webhook_group():
            pass

        @webhook_group.command(name="set", help="configura a URL do webhook.")
        @click.argument("url", required=False, default=None)
        def webhook_set_cmd(url):
            _require_root()
            url = _resolve_arg(url, "URL do webhook:", "informe a URL: `pvx firewall webhook set <url>`.")
            if url is None:
                return
            webhook_ops.set_url(_state_dir(), url)
            click.echo("webhook configurado.")
            if _is_interactive():
                widgets.pause()

        @webhook_group.command(name="clear", help="remove a URL do webhook configurada.")
        def webhook_clear_cmd():
            _require_root()
            webhook_ops.clear(_state_dir())
            click.echo("webhook removido.")
            if _is_interactive():
                widgets.pause()

        @webhook_group.command(name="test", help="envia uma notificação de teste pro webhook configurado.")
        def webhook_test_cmd():
            ok, reason = webhook_ops.notify(_state_dir(), "test", "teste manual via `pvx firewall webhook test`")
            if ok:
                widgets.success("notificação de teste enviada.")
            else:
                widgets.failed(reason)
            if _is_interactive():
                widgets.pause()

        @group.command(name="check", help="mostra engine, IPs, portas e se o firewall está ativo agora.")
        @click.option("--engine", default=None, type=ENGINE_CHOICE)
        @click.option("--json", "as_json", is_flag=True, help="saída em JSON (consumo por outros módulos/scripts).")
        def check_cmd(engine, as_json):
            result = status_module.get_status(engine=engine, base_dir=_state_dir())

            if as_json:
                # contrato estável pra outros módulos (ex.: utilidades'
                # checks-phonevox) -- nunca faz sentido scraping de texto
                # formatado/colorido, que muda de tema pra tema.
                click.echo(json.dumps(result, default=str))
                return

            # pedido ao vivo: linhas antigas misturavam descrição e valor no
            # mesmo texto, difícil saber o que cada item significa -- agora
            # cada linha é item + descrição fixa (o que é) + valor dinâmico,
            # com o veredito ok/aviso/erro vindo do símbolo/cor de
            # check_result (nunca "ok"/"falha" cru).
            up = result["engine_active"] and result["synced"]
            counter = ""
            if result["expected_rule_count"] is not None:
                counter = f" ({result['configured_rule_count']}/{result['expected_rule_count']} regra(s))"

            widgets.title("pvx > firewall > check")
            widgets.section("Status")

            _check_row(
                "status", "firewall aplicado e com as regras batendo com a config atual",
                f"{'ATIVO' if up else 'INATIVO'}{counter}", "ok" if up else "error",
            )
            _check_row(
                "engine", "motor usado pra aplicar as regras (iptables/firewalld)",
                f"{result['engine']} ({'ativo' if result['engine_active'] else 'inativo'})",
                "ok" if result["engine_active"] else "warn",
            )
            if result.get("firewalld_zone"):
                _check_row(
                    "zona firewalld", "zona do firewalld onde as regras são aplicadas",
                    result["firewalld_zone"], "ok",
                )
            _check_row(
                "boot", "reaplica as regras sozinho depois de reiniciar (systemd)",
                "habilitado" if result["boot_persistent"] else "desabilitado",
                "ok" if result["boot_persistent"] else "warn",
            )

            if not result["session_ip"]:
                session_value, session_level = "não detectado", "warn"
            elif not result["failsafe_ok"]:
                session_value, session_level = f"{result['session_ip']} (sem failsafe -- rode `apply`)", "warn"
            else:
                session_value, session_level = result["session_ip"], "ok"
            _check_row(
                "sessão", "IP desta sessão -- failsafe garante que você não se tranca de fora",
                session_value, session_level,
            )

            if result.get("dropped_counters") is not None:
                counters = result["dropped_counters"]
                _check_row(
                    "pacotes bloqueados", "dropados desde o último apply (contador zera a cada apply)",
                    f"{counters['packets']} ({_humanize_bytes(counters['bytes'])})", "ok",
                )
                log_state = "habilitado" if log_ops.is_enabled(_state_dir()) else "desabilitado"
                _check_row(
                    "log detalhado", "LOG rate-limited nas chains de drop (ver `logs show`)", log_state, "ok",
                )

            geo_countries = lists.read_list(_list_path("geo_accept"))
            if not geo_countries:
                _check_row(
                    "geoban", "bloqueio geográfico em toda porta, exceto IPs confiáveis", "desligado", "ok",
                )
            else:
                names = ", ".join(cc for cc, _ in geo_countries)
                missing = [cc for cc, _ in geo_countries if not geoip_ops.read_cached_ranges(_state_dir(), cc)]
                if missing:
                    _check_row(
                        "geoban", "bloqueio geográfico em toda porta, exceto IPs confiáveis",
                        f"{names} (sem cache: {', '.join(missing)} -- rode `geo refresh`)", "warn",
                    )
                else:
                    _check_row(
                        "geoban", "bloqueio geográfico em toda porta, exceto IPs confiáveis", names, "ok",
                    )

            competing = result.get("competing_engine")
            _check_row(
                "engine concorrente", "outro firewall rodando junto que pode competir pelas mesmas regras",
                competing or "nenhum", "warn" if competing else "ok",
            )
            if competing:
                webhook_ops.notify(_state_dir(), "competing_engine", f"{competing} também ativo")

            # achado ao vivo: rule_count>0 mas synced=False é exatamente o
            # cenário que enganou o `check` antigo (regras presentes, mas
            # divergentes do esperado) -- vale notificar sozinho, sem
            # depender de alguém rodar `check` e reparar por acaso.
            if result["rule_count"] > 0 and not result["synced"]:
                webhook_ops.notify(
                    _state_dir(), "check_drift", "regras aplicadas divergem da configuração atual",
                )

            click.echo()
            if result["lists"]:
                _echo_list("IPs confiáveis", result["lists"]["ip_accept"])
                _echo_list("IPs bloqueados", result["lists"]["ip_deny"])
                _echo_list("Portas liberadas", result["lists"]["port_accept"])
                _echo_list("Portas bloqueadas", result["lists"]["port_deny"])

            if _is_interactive():
                widgets.pause()

        @group.command(name="apply", help="aplica as listas no firewall de verdade (iptables/firewalld).")
        @click.option("--engine", default=None, type=ENGINE_CHOICE)
        @click.option("--force", is_flag=True, help="prossegue mesmo sem detectar o IP da sessão atual")
        @click.option("--yes", is_flag=True)
        def apply_cmd(engine, force, yes):
            _require_root()
            logger = self.get_logger()
            if not yes and not ask_confirm(
                "Isso vai reescrever as regras de firewall deste host. Confirma?", default=False
            ):
                click.echo("Operação cancelada.")
                if _is_interactive():
                    widgets.pause()
                return

            try:
                with widgets.spinner("Sincronizando firewall..."):
                    result = sync_module.run(str(_state_dir()), engine=engine, force=force)
            except Exception as e:
                logger.error(f"apply falhou: {e}")
                widgets.failed(str(e))
                if _is_interactive():
                    widgets.pause()
                return

            logger.info(f"firewall sincronizado (engine: {result['engine']}).")
            widgets.success(f"firewall sincronizado (engine: {result['engine']}).")
            if result["session_ip"] is None:
                click.echo("aviso: IP da sessão não detectado -- nenhum failsafe foi inserido (rodou com --force).")
            if _is_interactive():
                widgets.pause()

        @group.command(name="start-on-boot", help="instala um serviço systemd que reaplica o firewall no boot.")
        @click.option("--dry-run", is_flag=True)
        @click.option("--pvx-bin", default="/usr/local/bin/pvx")
        def start_on_boot_cmd(dry_run, pvx_bin):
            _require_root()
            content = systemd_unit.install(pvx_bin=pvx_bin, dry_run=dry_run)
            if dry_run:
                click.echo(content)
            else:
                self.get_logger().info("serviço pvx-firewall habilitado no boot.")
                widgets.success("serviço pvx-firewall habilitado no boot.")
            if _is_interactive():
                widgets.pause()

        return group


cli = FirewallModule()
