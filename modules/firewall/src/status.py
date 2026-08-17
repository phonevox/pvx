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
        protected = ip is not None and iptables_engine.failsafe_present(ip)
    else:
        rule_count = firewalld_engine.count_rich_rules(defaults.FIREWALLD_ZONE)
        protected = ip is not None and firewalld_engine.failsafe_present(defaults.FIREWALLD_ZONE, ip)

    if ip is None:
        protection = "IP da sessão não detectável"
    elif protected:
        protection = "protegido"
    else:
        protection = "não sincronizado"

    return {
        "engine": engine_name,
        "session_ip": ip,
        "rule_count": rule_count,
        "protection": protection,
    }
