import defaults
import firewalld_engine
import iptables_engine
import session_ip
import sync


def get_status(engine=None):
    engine_name = sync.resolve_engine(engine)
    ip = session_ip.detect_session_ip()

    if engine_name == "iptables":
        rule_count = iptables_engine.count_input_rules()
        failsafe_ok = ip is not None and iptables_engine.failsafe_present(ip)
    else:
        rule_count = firewalld_engine.count_rich_rules(defaults.FIREWALLD_ZONE)
        failsafe_ok = ip is not None and firewalld_engine.failsafe_present(defaults.FIREWALLD_ZONE, ip)

    return {
        "engine": engine_name,
        "session_ip": ip,
        "rule_count": rule_count,
        # sincronizado e failsafe-da-sessão-atual são sinais independentes
        # (ex.: IP da sessão mudou desde o último sync) -- nunca inferir um
        # a partir do outro.
        "synced": rule_count > 0,
        "failsafe_ok": failsafe_ok,
    }
