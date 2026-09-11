from pathlib import Path

import defaults
import engine_detect
import firewalld_engine
import iptables_engine
import lists
import session_ip
import sync
import systemd_unit


def get_status(engine=None, base_dir=None):
    engine_name = sync.resolve_engine(engine)
    ip = session_ip.detect_session_ip()

    firewalld_zone = None
    configured_rule_count = None
    if engine_name == "iptables":
        rule_count = iptables_engine.count_input_rules()
        configured_rule_count = iptables_engine.count_configured_rules()
        failsafe_ok = ip is not None and iptables_engine.failsafe_present(ip)
        # iptables não tem daemon próprio -- "ativo" é exatamente "tem regra
        # carregada no kernel agora", o mesmo sinal que synced.
        engine_active = rule_count > 0
    else:
        # mesma zona que sync.run() de fato usaria -- sem isso, `check` lia sempre a
        # zona própria (pvxfw) mesmo numa central onde ela é inerte (ver
        # resolve_firewalld_zone/MagnusBilling), reportando "sincronizado" à toa.
        firewalld_zone, _ = sync.resolve_firewalld_zone()
        rule_count = firewalld_engine.count_rich_rules(firewalld_zone)
        # count_rich_rules() já conta só as regras da zona (equivalente ao
        # "configured" do iptables) -- pode incluir +1 do failsafe quando
        # presente, imprecisão conhecida, não vale a pena caçar mais que isso.
        configured_rule_count = rule_count
        failsafe_ok = ip is not None and firewalld_engine.failsafe_present(firewalld_zone, ip)
        # sinal independente de synced: o daemon pode estar parado mesmo com
        # regras configuradas (nada sendo de fato aplicado nesse caso).
        engine_active = engine_detect.service_is_active("firewalld")

    lists_data = None
    expected_rule_count = None
    if base_dir is not None:
        # sem seed= aqui de propósito -- check não exige root (não é uma
        # ação mutante), e read_list com seed grava as listas padrão em
        # disco se o arquivo ainda não existe. Seed continua sendo
        # responsabilidade só de sync.run() (chamado por `apply`).
        base_dir = Path(base_dir)
        lists_data = {
            key: lists.read_list(base_dir / filename)
            for key, filename in defaults.CONFIG_FILENAMES.items()
        }
        engine_module = iptables_engine if engine_name == "iptables" else firewalld_engine
        expected_rule_count = engine_module.expected_rule_count(
            lists_data["ip_accept"], lists_data["ip_deny"], lists_data["port_accept"], lists_data["port_deny"],
        )

    return {
        "engine": engine_name,
        "engine_active": engine_active,
        # pvx-firewall.service (instalado por `start-on-boot`) reaplica as
        # listas no próximo boot -- sem isso, um reboot derruba as regras do
        # iptables (firewalld persiste sozinho, mas o unit não faz mal nele).
        "boot_persistent": systemd_unit.is_enabled(),
        "session_ip": ip,
        "rule_count": rule_count,
        # sincronizado e failsafe-da-sessão-atual são sinais independentes
        # (ex.: IP da sessão mudou desde o último sync) -- nunca inferir um
        # a partir do outro.
        "synced": rule_count > 0,
        "failsafe_ok": failsafe_ok,
        "lists": lists_data,
        "firewalld_zone": firewalld_zone,
        "configured_rule_count": configured_rule_count,
        "expected_rule_count": expected_rule_count,
    }
