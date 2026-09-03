import contextlib
import datetime
import fcntl
import glob
import gzip
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

import state

# caminhos absolutos fixos (não baseados em $HOME/pvx_home()) -- o `install`
# roda via sudo (usuário real detectado via SUDO_USER), mas o `run` é
# disparado pelo timer do systemd, sem sudo nenhum por trás (sem SUDO_USER).
# Se o estado morasse em pvx_home(), os dois resolveriam diretórios
# diferentes e o timer nunca acharia a config que o install salvou.
CONFIG_DIR = "/etc/phonevox/automacoes"
STATE_FILE = f"{CONFIG_DIR}/state.json"
LAST_RESPONSE_FILE = f"{CONFIG_DIR}/last_response.json"
LOG_FILE = "/var/log/phonevox-automacoes.log"
LOG_MAX_BYTES = 10 * 1024 * 1024
LOCK_FILE = "/tmp/phonevox-automacoes.lock"

SERVICE_UNIT_PATH = "/etc/systemd/system/pvx-autobloqueador.service"
TIMER_UNIT_PATH = "/etc/systemd/system/pvx-autobloqueador.timer"

TYPES = ("opa", "pabx")

_SERVICE_TEMPLATE = """[Unit]
Description=pvx autobloqueador -- runner
After=network-online.target

[Service]
Type=oneshot
ExecStart={pvx_bin} autobloqueador run
User=root
"""

_TIMER_TEMPLATE = """[Unit]
Description=pvx autobloqueador -- timer
Requires=pvx-autobloqueador.service

[Timer]
OnCalendar=*:0/10
Persistent=true

[Install]
WantedBy=timers.target
"""


class AutobloqueadorError(Exception):
    pass


def _run(args, error, **kwargs):
    # ponto único de subprocess do módulo -- falha previsível (comando
    # ausente, serviço fora do ar) vira AutobloqueadorError com o stderr,
    # nunca um CalledProcessError cru.
    kwargs.setdefault("stderr", subprocess.PIPE)
    kwargs.setdefault("text", True)
    result = subprocess.run(args, **kwargs)
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        raise AutobloqueadorError(f"{error}{': ' + detail if detail else ''}")
    return result


# --- configuração ---

def configs_exist():
    return state.load(STATE_FILE) is not None


def save_config(url_base, type_, code, crypted_key):
    state.save(STATE_FILE, {
        "url_base": url_base, "type": type_, "code": code, "crypted_key": crypted_key,
    })


def load_config():
    return state.load(STATE_FILE)


def normalize_url_base(value):
    value = value.strip()
    if not value:
        raise AutobloqueadorError("URL base vazia.")
    if not value.startswith("http://") and not value.startswith("https://"):
        value = f"https://{value}"
    return value


def validate_code(value):
    return bool(value) and len(value) <= 255


def register_curl_commands(base_url, type_, code):
    # comando gerado pra ser colado e executado numa máquina de rede
    # permitida (VPN/interna) -- nunca disparado daqui (ver main.py).
    url = f"{base_url}/register"
    payload = json.dumps({"type": type_, "code": code})
    linux = f"""curl -L -X POST "{url}" -H "Content-Type: application/json" -d '{payload}'"""
    windows_payload = payload.replace('"', '\\"')
    windows = f'curl -L -X POST "{url}" -H "Content-Type: application/json" -d "{windows_payload}"'
    return linux, windows


# --- checagem de status ---

def find_pm2():
    which = shutil.which("pm2")
    if which:
        return which
    for pattern in (
        "/usr/local/bin/pm2", "/usr/bin/pm2",
        "~/.npm/_npx/*/bin/pm2", "~/.nvm/versions/node/*/bin/pm2",
    ):
        # glob não expande "~" sozinho (diferente do bash, que expande
        # $HOME antes do glob) -- sem isso, os dois últimos caminhos nunca
        # bateriam com nada de verdade.
        matches = glob.glob(os.path.expanduser(pattern))
        if matches:
            return matches[0]
    return None


def _apply_action(type_, action):
    if type_ == "pabx":
        _run(["service", "asterisk", action], f"falha ao executar 'service asterisk {action}'")
        return None

    pm2_bin = find_pm2()
    if pm2_bin is None:
        # não é motivo pra abortar a checagem inteira -- só reporta e segue,
        # igual o original (log de aviso, sem `die`).
        return "pm2 não encontrado em nenhum caminho conhecido -- ação não executada."
    _run([pm2_bin, action, "all"], f"falha ao executar 'pm2 {action} all'")
    return None


def _query_status(base_url, type_, crypted_key, last_status, timeout=30):
    encoded_key = urllib.parse.quote(crypted_key)
    url = f"{base_url}?type={type_}&crypted_key={encoded_key}&last_status={last_status:03d}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as e:
        # 402 (bloqueio) chega aqui -- é a resposta de verdade, não uma
        # falha de rede.
        return e.code
    except urllib.error.URLError:
        # equivalente ao "000" do curl original quando não há resposta.
        return 0


def _read_last_status():
    data = state.load(LAST_RESPONSE_FILE)
    return data["http_code"] if data else 0


def _write_last_response(http_code):
    state.save(LAST_RESPONSE_FILE, {
        "http_code": http_code, "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
    })


def check_and_apply(base_url, type_, crypted_key, dry_run=False):
    last_status = _read_last_status()
    http_code = _query_status(base_url, type_, crypted_key, last_status)

    result = {"http_code": http_code, "last_status": last_status, "action": None, "warning": None}

    if http_code == 200:
        _write_last_response(http_code)
        if last_status != 200:
            result["action"] = "restart"
            if not dry_run:
                result["warning"] = _apply_action(type_, "restart")
    elif http_code == 402:
        _write_last_response(http_code)
        result["action"] = "stop"
        if not dry_run:
            result["warning"] = _apply_action(type_, "stop")
    # qualquer outro código: ignora, mantém o last_status salvo.

    return result


# --- execução exclusiva ---

@contextlib.contextmanager
def lock(path=LOCK_FILE, timeout=30, poll_interval=1):
    # substitui o "touch + espera arquivo sumir" do original (tinha race
    # condition -- dois processos podiam ver o arquivo ausente ao mesmo
    # tempo) por flock, atômico de verdade.
    f = open(path, "w")
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise AutobloqueadorError("timeout esperando outra execução terminar.")
                time.sleep(poll_interval)
        yield
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()


# --- systemd ---

def install_timer(pvx_bin="/usr/local/bin/pvx"):
    with open(SERVICE_UNIT_PATH, "w") as f:
        f.write(_SERVICE_TEMPLATE.format(pvx_bin=pvx_bin))
    with open(TIMER_UNIT_PATH, "w") as f:
        f.write(_TIMER_TEMPLATE)
    _run(["systemctl", "daemon-reload"], "falha ao recarregar o systemd")
    _run(["systemctl", "enable", "--now", "pvx-autobloqueador.timer"], "falha ao habilitar o timer")


def start_timer():
    _run(["systemctl", "enable", "--now", "pvx-autobloqueador.timer"], "falha ao iniciar o timer")


def stop_timer():
    _run(["systemctl", "stop", "pvx-autobloqueador.timer"], "falha ao parar o timer")
    _run(["systemctl", "stop", "pvx-autobloqueador.service"], "falha ao parar o service")
    _run(["systemctl", "disable", "pvx-autobloqueador.timer"], "falha ao desabilitar o timer")


def remove_timer():
    # best-effort (igual o `|| true` do original) -- remove precisa
    # funcionar mesmo se alguma unit já não existir mais.
    for cmd in (
        ["systemctl", "stop", "pvx-autobloqueador.timer"],
        ["systemctl", "stop", "pvx-autobloqueador.service"],
        ["systemctl", "disable", "pvx-autobloqueador.timer"],
    ):
        subprocess.run(cmd, capture_output=True)
    for path in (SERVICE_UNIT_PATH, TIMER_UNIT_PATH):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    subprocess.run(["systemctl", "daemon-reload"], capture_output=True)


def remove_config():
    state.remove(STATE_FILE)
    state.remove(LAST_RESPONSE_FILE)


def last_response():
    return state.load(LAST_RESPONSE_FILE)


def _rotate_log_if_needed():
    if not os.path.isfile(LOG_FILE) or os.path.getsize(LOG_FILE) <= LOG_MAX_BYTES:
        return
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    rotated = f"{LOG_FILE}.{timestamp}"
    os.rename(LOG_FILE, rotated)
    with open(rotated, "rb") as src, gzip.open(f"{rotated}.gz", "wb") as dst:
        shutil.copyfileobj(src, dst)
    os.remove(rotated)


def log(message):
    # log de auditoria de tamanho fixo (status/logs mostram este arquivo) --
    # rotaciona em 10MB, igual o original.
    _rotate_log_if_needed()
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")
    os.chmod(LOG_FILE, 0o600)


def tail_log(lines=100):
    if not os.path.isfile(LOG_FILE):
        return ""
    with open(LOG_FILE) as f:
        return "".join(f.readlines()[-lines:])


def timer_status():
    result = subprocess.run(
        ["systemctl", "list-timers", "pvx-autobloqueador.timer", "--no-pager"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None
