from pathlib import Path

import defaults
import engine_detect
import fail2ban_ops
import firewalld_engine
import iptables_engine
import lists
import log_ops
import session_ip
import sync
import systemd_unit


def get_status(engine=None, base_dir=None):
    engine_name = sync.resolve_engine(engine)
    ip = session_ip.detect_session_ip()

    # achado ao vivo: o engine escolhido por pvx pode não ser o único de
    # fato competindo pelas mesmas chains -- um segundo serviço de firewall
    # ativo pode estar reescrevendo/interceptando pacotes antes (ou depois)
    # das regras que pvx aplicou, sem nenhum sinal disso em rule_count.
    other_engine = "firewalld" if engine_name == "iptables" else "iptables"
    competing_engine = other_engine if engine_detect.service_is_active(other_engine) else None

    firewalld_zone = None
    configured_rule_count = None
    if engine_name == "iptables":
        rule_count = iptables_engine.count_input_rules()
        configured_rule_count = iptables_engine.count_configured_rules()
        failsafe_ok = ip is not None and iptables_engine.failsafe_present(ip)
        # iptables não tem daemon próprio -- "ativo" é exatamente "tem regra
        # carregada no kernel agora", o mesmo sinal que synced.
        engine_active = rule_count > 0
        dropped_counters = iptables_engine.dropped_counters()
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
        # firewalld ainda não tem o equivalente (milestone futuro).
        dropped_counters = None

    lists_data = None
    fail2ban = None
    expected_rule_count = None
    # sem lista pra comparar, não dá pra saber se o conteúdo bate -- fica
    # neutro (nem confirma nem reprova), igual ao comportamento de antes de
    # existir essa checagem.
    content_matches = True
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
        fail2ban = fail2ban_ops.is_synced([ip_entry for ip_entry, _ in lists_data["ip_accept"]])
        if engine_name == "iptables":
            # log_enabled precisa bater com o que sync() de fato aplicou --
            # senão "configured/expected" (contador) e o content-diff dão
            # falso positivo de divergência só por causa das regras de LOG.
            log_enabled = log_ops.is_enabled(base_dir)
            expected_rule_count = iptables_engine.expected_rule_count(
                lists_data["ip_accept"], lists_data["ip_deny"], lists_data["port_accept"], lists_data["port_deny"],
                log_enabled=log_enabled,
            )
            # achado ao vivo: rule_count>0 não quer dizer que as regras
            # aplicadas são as da config atual -- comparar conteúdo de
            # verdade é o que decide "sincronizado" de fato daqui pra
            # frente. firewalld ainda não tem o equivalente (milestone
            # futuro) -- content_matches fica neutro (True) nesse caso.
            content_matches = iptables_engine.rules_match_expected(
                lists_data["ip_accept"], lists_data["ip_deny"], lists_data["port_accept"], lists_data["port_deny"],
                log_enabled=log_enabled,
            )
        else:
            expected_rule_count = firewalld_engine.expected_rule_count(
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
        "synced": rule_count > 0 and content_matches,
        "failsafe_ok": failsafe_ok,
        "lists": lists_data,
        "firewalld_zone": firewalld_zone,
        "configured_rule_count": configured_rule_count,
        "expected_rule_count": expected_rule_count,
        "competing_engine": competing_engine,
        "dropped_counters": dropped_counters,
        # None = fail2ban não instalado/não respondendo; bool = ignoreip bate com ip_accept.
        "fail2ban": fail2ban,
    }
