#!/bin/bash
#===============================================================================
# audit.sh - Auditoria de comprometimento para servidores EL7/EL8 e Issabel
#
# Exit codes:
#   0 = SUCCESS      (nada relevante encontrado)
#   1 = COMPROMISED  (evidencia forte de comprometimento)
#   2 = UNSUPPORTED  (SO/ambiente nao suportado)
#   3 = UNKNOWN      (nao foi possivel determinar: sem privilegio, erro interno)
#
# Uso:
#   ./audit.sh                 # JSON (padrao), exit code real
#   ./audit.sh --text          # relatorio legivel
#   ./audit.sh --zabbix        # JSON em 1 linha, SEMPRE exit 0
#   ./audit.sh --force         # ignora checagem de SO suportado
#   ./audit.sh --allow-degraded# nao retorna UNKNOWN quando sem root
#
# Compat: bash 4.2+ (CentOS 7) / bash 4.4+ (Rocky 8). Sem dependencias externas
# alem de coreutils/procps. Tudo que pode faltar e' testado antes de usar.
#===============================================================================

VERSION="1.4.0"

LC_ALL=C
LANG=C
export LC_ALL LANG
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 077

# Nunca deixar o proprio audit atrapalhar a central
if command -v renice >/dev/null 2>&1; then renice -n 19 -p $$ >/dev/null 2>&1; fi
if command -v ionice >/dev/null 2>&1; then ionice -c3 -p $$ >/dev/null 2>&1; fi

#------------------------------------------------------------------------------
# Configuracao (pode ser sobrescrita em /etc/pvx-audit/audit.conf)
#------------------------------------------------------------------------------
CONF_DIR="/etc/pvx-audit"
CONF_FILE="${CONF_DIR}/audit.conf"
WHITELIST_FILE="${CONF_DIR}/whitelist.conf"
KNOWN_KEYS_FILE="${CONF_DIR}/known_keys.conf"

# Janela (em dias) para considerar um arquivo "recente"
RECENT_DAYS=45
# CPU minima (%) para considerar processo suspeito por consumo
CPU_THRESHOLD=70
# Tempo minimo de vida (segundos) para avaliar CPU sustentada
MIN_ETIME=300
# Diretorios web auditados
WEBROOTS="/var/www/html /usr/share/issabel /var/lib/asterisk/static-http"
# Score a partir do qual consideramos COMPROMISED
SCORE_COMPROMISED=50
# Score a partir do qual marcamos nivel "suspect"
SCORE_SUSPECT=20
# Timeout global (segundos) para comandos de varredura pesada
SCAN_TIMEOUT=25

#------------------------------------------------------------------------------
# DEFAULTS DA OPERACAO - edite aqui e distribua so o script
#------------------------------------------------------------------------------
# Chaves SSH confiaveis, por FINGERPRINT do material da chave.
# Levante novos fingerprints com:  audit.sh --list-keys
# O arquivo /etc/pvx-audit/known_keys.conf, se existir, SOMA a esta lista.
BUILTIN_KNOWN_KEYS=(
    "87ee57f5642577cc8b2de9efb8236c7d  MAIN@PHONEVOX - chave principal de operacao"
    "a7f28904aff28f4c798b2e4b1dd8d73e  adrian@adriankubinyete - Adrian"
)

# Achados aceitos como esperados no parque (regex ERE contra a mensagem).
# O /etc/pvx-audit/whitelist.conf, se existir, SOMA a esta lista.
BUILTIN_WHITELIST=(
    "conta com hash de senha vazio em /etc/shadow: 'phonevox'$"
)
#------------------------------------------------------------------------------

MODE="json"
COLOR="auto"
FORCE=0
ZABBIX=0
ALLOW_DEGRADED=0
DEBUG=0

#------------------------------------------------------------------------------
# Estado
#------------------------------------------------------------------------------
declare -a F_SEV=() F_CLASS=() F_MSG=()
SCORE=0
CLASS_MASK=0
DEGRADED=0
SUPPRESSED=0
declare -a NOTES=()
TMPDIR_AUDIT=""
START_TS=$(date +%s 2>/dev/null || echo 0)

# Classes de invasao (bitmask)
C_MINER=1        # mineracao de criptomoeda
C_PERSIST=2      # persistencia (cron, systemd, rc.local, authorized_keys)
C_WEBSHELL=4     # webshell / arquivo malicioso em webroot
C_ACCOUNT=8      # conta maliciosa / escalonamento
C_ROOTKIT=16     # ocultacao (ld.so.preload, processo mascarado, binario deletado)
C_NETWORK=32     # conexao maliciosa / pool de mineracao / backdoor
C_TAMPER=64      # adulteracao de binarios / logs / atributos
C_PBX=128        # abuso especifico de PBX

class_name() {
    case "$1" in
        1)   echo "miner" ;;
        2)   echo "persistence" ;;
        4)   echo "webshell" ;;
        8)   echo "account" ;;
        16)  echo "rootkit" ;;
        32)  echo "network" ;;
        64)  echo "tamper" ;;
        128) echo "pbx_abuse" ;;
        *)   echo "other" ;;
    esac
}

#------------------------------------------------------------------------------
# Utilidades
#------------------------------------------------------------------------------
have() { command -v "$1" >/dev/null 2>&1; }

dbg() { [ "$DEBUG" -eq 1 ] && printf 'DEBUG: %s\n' "$*" >&2; return 0; }

# Executa com timeout se disponivel
run() {
    if have timeout; then
        timeout "$SCAN_TIMEOUT" "$@" 2>/dev/null
    else
        "$@" 2>/dev/null
    fi
}

json_escape() {
    local s="$1"
    s=${s//\\/\\\\}
    s=${s//\"/\\\"}
    s=${s//$'\n'/ }
    s=${s//$'\r'/ }
    s=${s//$'\t'/ }
    printf '%s' "$s" | tr -d '\000-\037'
}

# Trunca string longa para nao estourar o valor no Zabbix
trunc() {
    local s="$1" n="${2:-180}"
    if [ ${#s} -gt "$n" ]; then
        printf '%s...' "${s:0:$n}"
    else
        printf '%s' "$s"
    fi
}

sev_weight() {
    case "$1" in
        CRIT) echo 50 ;;
        HIGH) echo 25 ;;
        MED)  echo 10 ;;
        LOW)  echo 3 ;;
        *)    echo 0 ;;
    esac
}

is_whitelisted() {
    local msg="$1" pat
    for pat in "${BUILTIN_WHITELIST[@]:-}"; do
        [ -z "$pat" ] && continue
        if printf '%s' "$msg" | grep -qE -- "$pat" 2>/dev/null; then
            return 0
        fi
    done
    [ -r "$WHITELIST_FILE" ] || return 1
    while IFS= read -r pat; do
        case "$pat" in ''|'#'*) continue ;; esac
        if printf '%s' "$msg" | grep -qE -- "$pat" 2>/dev/null; then
            return 0
        fi
    done < "$WHITELIST_FILE"
    return 1
}

# add_finding <SEV> <CLASS_BIT> <mensagem>
add_finding() {
    local sev="$1" cls="$2" msg="$3"
    msg=$(trunc "$msg" 200)
    if is_whitelisted "$msg"; then
        SUPPRESSED=$((SUPPRESSED + 1))
        dbg "suprimido: $msg"
        return 0
    fi
    F_SEV+=("$sev")
    F_CLASS+=("$cls")
    F_MSG+=("$msg")
    SCORE=$((SCORE + $(sev_weight "$sev")))
    CLASS_MASK=$((CLASS_MASK | cls))
    dbg "finding [$sev/$(class_name "$cls")] $msg"
}

add_note() { NOTES+=("$1"); }

cleanup() {
    [ -n "$TMPDIR_AUDIT" ] && [ -d "$TMPDIR_AUDIT" ] && rm -rf -- "$TMPDIR_AUDIT" 2>/dev/null
}
trap cleanup EXIT HUP INT TERM

#------------------------------------------------------------------------------
# Argumentos
#------------------------------------------------------------------------------
while [ $# -gt 0 ]; do
    case "$1" in
        --text)           MODE="text" ;;
        --json)           MODE="json" ;;
        --zabbix)         MODE="json"; ZABBIX=1 ;;
        --force)          FORCE=1 ;;
        --allow-degraded) ALLOW_DEGRADED=1 ;;
        --debug)          DEBUG=1 ;;
        --list-keys)      MODE="listkeys" ;;
        --color)          COLOR="always" ;;
        --no-color)       COLOR="never" ;;
        --version)        echo "audit.sh ${VERSION}"; exit 0 ;;
        -h|--help)
            sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "Opcao desconhecida: $1" >&2; exit 3 ;;
    esac
    shift
done

[ -r "$CONF_FILE" ] && . "$CONF_FILE" 2>/dev/null


#------------------------------------------------------------------------------
# Cores (somente em modo texto e apenas quando a saida e' um terminal)
#------------------------------------------------------------------------------
C_RESET=""; C_BOLD=""; C_DIM=""
C_RED=""; C_YEL=""; C_GRN=""; C_BLU=""; C_MAG=""; C_CYA=""; C_WHT=""
C_BGRED=""

setup_colors() {
    local enable=0
    case "$COLOR" in
        always) enable=1 ;;
        never)  enable=0 ;;
        auto)
            # Cor apenas com TTY real, terminal capaz e sem NO_COLOR definido.
            # Redirecionar para arquivo ou pipe (| grep, > log) sai limpo.
            if [ -t 1 ] && [ -z "${NO_COLOR+x}" ]; then
                case "${TERM:-dumb}" in
                    dumb|"") enable=0 ;;
                    *) enable=1 ;;
                esac
            fi
            ;;
    esac
    [ "$enable" -eq 0 ] && return 0

    C_RESET=$'\033[0m'
    C_BOLD=$'\033[1m'
    C_DIM=$'\033[2m'
    C_RED=$'\033[31m'
    C_YEL=$'\033[33m'
    C_GRN=$'\033[32m'
    C_BLU=$'\033[34m'
    C_MAG=$'\033[35m'
    C_CYA=$'\033[36m'
    C_WHT=$'\033[37m'
    C_BGRED=$'\033[41;97;1m'
    return 0
}

sev_color() {
    case "$1" in
        CRIT) printf '%s' "${C_BOLD}${C_RED}" ;;
        HIGH) printf '%s' "${C_RED}" ;;
        MED)  printf '%s' "${C_YEL}" ;;
        LOW)  printf '%s' "${C_CYA}" ;;
        *)    printf '%s' "" ;;
    esac
}

level_color() {
    case "$1" in
        compromised) printf '%s' "${C_BOLD}${C_RED}" ;;
        suspect)     printf '%s' "${C_BOLD}${C_YEL}" ;;
        clean)       printf '%s' "${C_BOLD}${C_GRN}" ;;
        unsupported) printf '%s' "${C_MAG}" ;;
        *)           printf '%s' "${C_DIM}" ;;
    esac
}

# Barra visual do score
score_bar() {
    local sc="$1" filled i out="" col
    filled=$((sc / 5))
    if   [ "$sc" -ge 50 ]; then col="${C_RED}"
    elif [ "$sc" -ge 20 ]; then col="${C_YEL}"
    else col="${C_GRN}"; fi
    out="${col}"
    for ((i=0; i<20; i++)); do
        if [ "$i" -lt "$filled" ]; then out="${out}#"; else out="${out}${C_DIM}.${col}"; fi
    done
    printf '%s' "${out}${C_RESET}"
}

#------------------------------------------------------------------------------
# Saida
#------------------------------------------------------------------------------
emit_and_exit() {
    local status="$1" reason="$2"
    local level end_ts dur i
    end_ts=$(date +%s 2>/dev/null || echo 0)
    dur=$((end_ts - START_TS))
    [ "$SCORE" -gt 100 ] && SCORE=100

    case "$status" in
        0) if   [ "$SCORE" -ge "$SCORE_SUSPECT" ]; then level="suspect"
           else level="clean"; fi ;;
        1) level="compromised" ;;
        2) level="unsupported" ;;
        *) level="unknown" ;;
    esac

    # lista de classes textuais
    local classes="" bit
    for bit in 1 2 4 8 16 32 64 128; do
        if [ $((CLASS_MASK & bit)) -ne 0 ]; then
            [ -n "$classes" ] && classes="${classes},"
            classes="${classes}\"$(class_name "$bit")\""
        fi
    done

    if [ "$MODE" = "text" ]; then
        local lc rule sevc
        lc=$(level_color "$level")
        rule="${C_DIM}---------------------------------------------------------------${C_RESET}"

        printf '%s\n' "${C_DIM}===============================================================${C_RESET}"
        printf ' %saudit %s%s  %s%s%s\n' "${C_BOLD}" "${VERSION}" "${C_RESET}" "${C_CYA}" "$(hostname 2>/dev/null)" "${C_RESET}"
        printf ' %sdata:%s    %s\n' "${C_DIM}" "${C_RESET}" "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)"
        printf ' %ssistema:%s %s%s\n' "${C_DIM}" "${C_RESET}" "${OS_LABEL:-?}" "${PBX_LABEL:+ / ${PBX_LABEL}}"
        printf ' %sstatus:%s  %s%s (%s)%s\n' "${C_DIM}" "${C_RESET}" "$lc" "$status" "$level" "${C_RESET}"
        printf ' %sscore:%s   %s %3d/100\n' "${C_DIM}" "${C_RESET}" "$(score_bar "$SCORE")" "$SCORE"
        if [ -n "$classes" ]; then
            printf ' %sclasses:%s %s%s%s\n' "${C_DIM}" "${C_RESET}" "${C_MAG}" "$(echo "$classes" | tr -d '"' | tr ',' ' ')" "${C_RESET}"
        fi
        if [ "$DEGRADED" -eq 1 ]; then
            printf ' %s AVISO: execucao SEM root - cobertura reduzida %s\n' "${C_BGRED}" "${C_RESET}"
        fi
        [ -n "$reason" ] && printf ' %smotivo:%s  %s\n' "${C_DIM}" "${C_RESET}" "$reason"
        printf '%s\n' "${C_DIM}===============================================================${C_RESET}"

        if [ ${#F_MSG[@]} -eq 0 ]; then
            printf ' %sNenhum achado.%s\n' "${C_GRN}" "${C_RESET}"
        else
            for i in "${!F_MSG[@]}"; do
                sevc=$(sev_color "${F_SEV[$i]}")
                printf ' %s[%-4s]%s %s%-12s%s %s\n' \
                    "$sevc" "${F_SEV[$i]}" "${C_RESET}" \
                    "${C_DIM}" "$(class_name "${F_CLASS[$i]}")" "${C_RESET}" \
                    "${F_MSG[$i]}"
            done
        fi

        if [ ${#NOTES[@]} -gt 0 ]; then
            printf '%s\n' "$rule"
            for i in "${!NOTES[@]}"; do
                printf ' %snota:%s %s\n' "${C_BLU}" "${C_RESET}" "${NOTES[$i]}"
            done
        fi
        if [ "$SUPPRESSED" -gt 0 ]; then
            printf ' %s(%d achado(s) suprimido(s) pela whitelist)%s\n' "${C_DIM}" "$SUPPRESSED" "${C_RESET}"
        fi
        printf '%s\n' "$rule"
        printf ' %sduracao: %ss%s\n' "${C_DIM}" "$dur" "${C_RESET}"
    else
        local findings="" crit_count=0 high_count=0 top=""
        for i in "${!F_MSG[@]}"; do
            [ -n "$findings" ] && findings="${findings},"
            findings="${findings}{\"sev\":\"${F_SEV[$i]}\",\"class\":\"$(class_name "${F_CLASS[$i]}")\",\"msg\":\"$(json_escape "${F_MSG[$i]}")\"}"
            case "${F_SEV[$i]}" in
                CRIT) crit_count=$((crit_count + 1)); [ -z "$top" ] && top="${F_MSG[$i]}" ;;
                HIGH) high_count=$((high_count + 1)) ;;
            esac
        done
        [ -z "$top" ] && [ ${#F_MSG[@]} -gt 0 ] && top="${F_MSG[0]}"

        local notes_json="" n
        for n in "${NOTES[@]:-}"; do
            [ -z "$n" ] && continue
            [ -n "$notes_json" ] && notes_json="${notes_json},"
            notes_json="${notes_json}\"$(json_escape "$n")\""
        done

        printf '{'
        printf '"version":"%s",'        "$VERSION"
        printf '"status":%d,'           "$status"
        printf '"level":"%s",'          "$level"
        printf '"score":%d,'            "$SCORE"
        printf '"class_mask":%d,'       "$CLASS_MASK"
        printf '"classes":[%s],'        "$classes"
        printf '"findings_total":%d,'   "${#F_MSG[@]}"
        printf '"findings_crit":%d,'    "$crit_count"
        printf '"findings_high":%d,'    "$high_count"
        printf '"degraded":%d,'         "$DEGRADED"
        printf '"suppressed":%d,'       "$SUPPRESSED"
        printf '"os":"%s",'             "$(json_escape "${OS_LABEL:-unknown}")"
        printf '"pbx":"%s",'            "$(json_escape "${PBX_LABEL:-none}")"
        printf '"reason":"%s",'         "$(json_escape "$reason")"
        printf '"top":"%s",'            "$(json_escape "$(trunc "$top" 160)")"
        printf '"notes":[%s],'          "$notes_json"
        printf '"duration_s":%d,'       "$dur"
        printf '"ts":%d,'               "$end_ts"
        printf '"findings":[%s]'        "$findings"
        printf '}\n'
    fi

    [ "$ZABBIX" -eq 1 ] && exit 0
    exit "$status"
}

#------------------------------------------------------------------------------
# 0. Ambiente / suporte
#------------------------------------------------------------------------------
OS_LABEL="unknown"
PBX_LABEL="none"
EL_VER=""

detect_env() {
    local id="" ver=""
    if [ -r /etc/os-release ]; then
        id=$(awk -F= '/^ID=/{gsub(/"/,"",$2); print $2; exit}' /etc/os-release 2>/dev/null)
        ver=$(awk -F= '/^VERSION_ID=/{gsub(/"/,"",$2); print $2; exit}' /etc/os-release 2>/dev/null)
    elif [ -r /etc/redhat-release ]; then
        id="centos"
        ver=$(grep -oE '[0-9]+' /etc/redhat-release 2>/dev/null | head -1)
    fi
    EL_VER="${ver%%.*}"
    OS_LABEL="${id:-unknown}-${ver:-unknown}"

    # Issabel
    if [ -f /etc/issabel.conf ] || [ -d /usr/share/issabel ] || [ -f /etc/issabel_version ]; then
        local iv=""
        [ -r /etc/issabel_version ] && iv=$(head -1 /etc/issabel_version 2>/dev/null)
        PBX_LABEL="issabel${iv:+ $iv}"
    elif [ -f /etc/asterisk/asterisk.conf ]; then
        PBX_LABEL="asterisk"
    fi

    case "$id" in
        rocky|centos|rhel|almalinux|ol) : ;;
        *)
            [ "$FORCE" -eq 1 ] && return 0
            add_note "SO nao suportado: ${OS_LABEL} (use --force para ignorar)"
            emit_and_exit 2 "unsupported_os"
            ;;
    esac
    case "$EL_VER" in
        7|8|9) : ;;
        *)
            [ "$FORCE" -eq 1 ] && return 0
            add_note "Versao EL nao suportada: ${OS_LABEL}"
            emit_and_exit 2 "unsupported_release"
            ;;
    esac
    return 0
}

check_privs() {
    if [ "$(id -u 2>/dev/null || echo 1000)" -ne 0 ]; then
        DEGRADED=1
        add_note "executando como $(id -un 2>/dev/null) - checagens de /proc, cron de outros usuarios e webroot podem falhar; configure sudoers NOPASSWD"
    fi
}

#------------------------------------------------------------------------------
# 1. Processos: mineradores, mascaramento, binarios suspeitos
#------------------------------------------------------------------------------
# Nomes exatos de processo (usados SOMENTE com ancora ^...$ contra /proc/pid/comm)
MINER_NAMES='xmrig|minerd|cpuminer|cgminer|bfgminer|ccminer|ethminer|nbminer|phoenixminer|lolminer|t-rex|xmr-stak|xmrigDaemon|xmrigMiner|nanominer|gminer|srbminer|teamredminer|verusminer|kdevtmpfsi|kinsing|sysupdate|networkservice|sustes|watchdogs|dbused|ddgs|qW3xT|ksoftirqds|xm64'

# Tokens inequivocos para busca DENTRO de arquivos (cron, units, scripts).
# Nao inclui palavras genericas ("mine", "stratum", "sysupdate") que colidem
# com texto legitimo do sistema.
MINER_TEXT='(^|[^A-Za-z0-9_.-])(xmrig|minerd|cpuminer|cgminer|bfgminer|ccminer|ethminer|nbminer|phoenixminer|lolminer|xmr-stak|nanominer|srbminer|teamredminer|kdevtmpfsi|kinsing|sustes|moneroocean|supportxmr|minexmr|hashvault|c3pool|nanopool|dwarfpool|stratum\+tcp)([^A-Za-z0-9_.-]|$)'
MINER_ARGS='stratum\+tcp://|stratum2\+tcp://|--donate-level|--cpu-priority|--nicehash|--coin=|xmrpool|supportxmr|minexmr|nanopool|f2pool|hashvault|moneroocean|dwarfpool|pool\.minergate|c3pool|2miners|ethermine'
SUSPECT_DIRS='^/tmp/|^/var/tmp/|^/dev/shm/|^/run/shm/|^/var/spool/|^/var/lock/|^/dev/\.|^/\.\.'

# nomes reais de kernel threads (se aparecer com binario, e' mascaramento)
KTHREAD_NAMES='^(kworker/|ksoftirqd/|migration/|rcu_[a-z]+$|rcuo?[bps][0-9]|watchdog/|kswapd[0-9]+$|kthreadd$|kintegrityd$|kblockd$|md$|md[0-9]+_raid[0-9]*$|jbd2/|ext4-|xfs-|xfsalloc$|scsi_eh_|scsi_tmf_|irq/|kdmflush$|kcompactd[0-9]+$|khugepaged$|kauditd$|oom_reaper$|writeback$|crypto$|devfreq_wq$|edac-poller$|kthrotld$|acpi_thermal_pm$|ipv6_addrconf$|kstrp$|charger_manager$|kmpath_|kpsmoused$|ttm_swap$|nfit$|vballoon$|kvm-irqfd-clean$|cpuhp/|idle_inject/|netns$|kdevtmpfs$)'

check_processes() {
    local pid comm cmdline exe user pcpu etimes deleted
    local perm_denied=0 scanned=0

    # Auto-exclusao: o proprio audit carrega assinaturas de malware na sua
    # linha de comando/ambiente e nao pode se detectar.
    local self_pids=" $$ $PPID "
    local anc="$PPID" depth=0
    while [ -n "$anc" ] && [ "$anc" != "0" ] && [ "$anc" != "1" ] && [ "$depth" -lt 6 ]; do
        anc=$(awk '/^PPid:/{print $2; exit}' "/proc/$anc/status" 2>/dev/null)
        [ -z "$anc" ] && break
        self_pids="${self_pids}${anc} "
        depth=$((depth + 1))
    done

    for pid in /proc/[0-9]*; do
        pid=${pid#/proc/}
        [ -d "/proc/$pid" ] || continue
        case "$self_pids" in *" $pid "*) continue ;; esac
        scanned=$((scanned + 1))

        comm=""
        [ -r "/proc/$pid/comm" ] && read -r comm < "/proc/$pid/comm" 2>/dev/null

        cmdline=""
        if [ -r "/proc/$pid/cmdline" ]; then
            cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
        fi

        exe=$(readlink "/proc/$pid/exe" 2>/dev/null)
        if [ -z "$exe" ] && [ -n "$cmdline" ]; then
            # nao conseguiu ler exe mas tem cmdline => provavelmente permissao
            [ "$DEGRADED" -eq 1 ] && perm_denied=$((perm_denied + 1))
        fi

        # --- kernel thread real: sem cmdline e sem exe
        if [ -z "$cmdline" ] && [ -z "$exe" ]; then
            continue
        fi

        # --- 1.1 nome de minerador conhecido
        if printf '%s' "$comm" | grep -qiE "^($MINER_NAMES)$" 2>/dev/null; then
            add_finding CRIT $C_MINER "processo de mineracao conhecido: pid=$pid comm=$comm exe=${exe:-?}"
            continue
        fi

        # --- 1.2 argumentos de mineracao / pool
        if [ -n "$cmdline" ] && printf '%s' "$cmdline" | grep -qiE "$MINER_ARGS" 2>/dev/null; then
            add_finding CRIT $C_MINER "argumentos de pool/mineracao: pid=$pid cmd=$(trunc "$cmdline" 120)"
            continue
        fi

        # --- 1.3 carteira Monero/ETH na linha de comando
        if [ -n "$cmdline" ] && printf '%s' "$cmdline" | grep -qE '(4[0-9AB][1-9A-HJ-NP-Za-km-z]{93})|(0x[a-fA-F0-9]{40})' 2>/dev/null; then
            add_finding HIGH $C_MINER "possivel carteira cripto na linha de comando: pid=$pid comm=$comm"
        fi

        # --- 1.4 mascaramento de kernel thread
        if printf '%s' "$comm" | grep -qE "$KTHREAD_NAMES" 2>/dev/null; then
            if [ -n "$exe" ] || [ -n "$cmdline" ]; then
                add_finding CRIT $C_ROOTKIT "processo se passando por kernel thread: pid=$pid comm=$comm exe=${exe:-?}"
                continue
            fi
        fi

        # --- 1.5 binario rodando de diretorio suspeito
        if [ -n "$exe" ]; then
            deleted=0
            case "$exe" in *" (deleted)") deleted=1; exe=${exe% (deleted)} ;; esac

            if printf '%s' "$exe" | grep -qE "$SUSPECT_DIRS" 2>/dev/null; then
                add_finding CRIT $C_MINER "binario executando de diretorio temporario: pid=$pid exe=$exe"
                continue
            fi
            # binario oculto (nome iniciando com ponto)
            case "${exe##*/}" in
                .*) add_finding HIGH $C_ROOTKIT "binario oculto em execucao: pid=$pid exe=$exe" ;;
            esac
            # binario deletado: comum apos yum update, entao peso menor
            if [ "$deleted" -eq 1 ]; then
                case "$exe" in
                    /usr/*|/bin/*|/sbin/*|/lib*|/opt/*) : ;;  # atualizacao de pacote
                    *) add_finding HIGH $C_ROOTKIT "binario deletado do disco ainda em execucao: pid=$pid exe=$exe" ;;
                esac
            fi
        fi
    done

    if [ "$DEGRADED" -eq 1 ] && [ "$perm_denied" -gt 5 ]; then
        add_note "sem permissao para inspecionar ${perm_denied} processos de outros usuarios"
    fi
    dbg "processos analisados: $scanned"

    # --- 1.6 CPU sustentada alta em processo nao esperado
    if have ps; then
        local line
        while IFS= read -r line; do
            [ -z "$line" ] && continue
            set -- $line
            pid="$1"; user="$2"; pcpu="$3"; etimes="$4"; comm="$5"
            shift 5
            cmdline="$*"
            pcpu=${pcpu%%.*}
            [ -z "$pcpu" ] && continue
            case "$pcpu" in ''|*[!0-9]*) continue ;; esac
            case "$etimes" in ''|*[!0-9]*) continue ;; esac
            [ "$pcpu" -lt "$CPU_THRESHOLD" ] && continue
            [ "$etimes" -lt "$MIN_ETIME" ] && continue
            # whitelist de processos que legitimamente consomem CPU numa central
            case "$comm" in
                asterisk|mysqld|mariadbd|mysqld_safe|httpd|php-fpm|php|java|node|dnf|yum|rpm|rsync|tar|gzip|xz|bzip2|mongod|postgres|clamd|freshclam|fail2ban-server|zabbix_agentd|zabbix_server|kworker*|monit|logrotate|dockerd|containerd|cp|dd|find|mysqldump|smbd|nmbd|named|dovecot|postfix|opendkim|elastic*|python*|perl|systemd*|firewalld|NetworkManager|sshd|crond|rsyslogd|auditd|tuned)
                    continue ;;
            esac
            add_finding MED $C_MINER "CPU sustentada ${pcpu}% por ${etimes}s: pid=$pid user=$user comm=$comm cmd=$(trunc "$cmdline" 80)"
        done < <(run ps -eo pid=,user=,pcpu=,etimes=,comm=,args= 2>/dev/null)
    fi
}

#------------------------------------------------------------------------------
# 2. Rede: conexoes com pools de mineracao / portas suspeitas
#------------------------------------------------------------------------------
POOL_PORTS=' 3333 3334 3335 4444 4445 5555 5556 6666 7777 8888 9999 14433 14444 45560 45700 3032 3357 20580 '

check_network() {
    local out line peer port proc
    if have ss; then
        out=$(run ss -Hntp 2>/dev/null)
    elif have netstat; then
        out=$(run netstat -antp 2>/dev/null)
    else
        add_note "nem ss nem netstat disponiveis - checagem de rede ignorada"
        return 0
    fi
    [ -z "$out" ] && return 0

    while IFS= read -r line; do
        case "$line" in
            *ESTAB*|*ESTABLISHED*) : ;;
            *) continue ;;
        esac
        # ss:      ESTAB 0 0 local peer users:(("proc",pid=N,fd=M))
        # netstat: tcp 0 0 local peer ESTABLISHED pid/prog
        peer=$(printf '%s' "$line" | awk '{print $5}')
        proc=$(printf '%s' "$line" | awk '{print $NF}')
        port=${peer##*:}
        case "$port" in ''|*[!0-9]*) continue ;; esac

        if printf '%s' "$POOL_PORTS" | grep -q " ${port} " 2>/dev/null; then
            add_finding HIGH $C_NETWORK "conexao estabelecida em porta tipica de pool de mineracao: peer=${peer} proc=${proc}"
        fi
    done <<< "$out"

    # binario em diretorio temporario com socket aberto
    if have ss; then
        while IFS= read -r line; do
            case "$line" in
                *'/tmp/'*|*'/dev/shm/'*|*'/var/tmp/'*)
                    add_finding CRIT $C_NETWORK "socket aberto por binario em diretorio temporario: $(trunc "$line" 140)" ;;
            esac
        done < <(run ss -Hlntup 2>/dev/null)
    fi
}

#------------------------------------------------------------------------------
# 3. Persistencia: cron, systemd, rc.local, profile
#------------------------------------------------------------------------------
BAD_CMD_PATTERN='(curl|wget|fetch)[^|;]*\|[[:space:]]*(ba)?sh|base64[[:space:]]+-d|base64[[:space:]]+--decode|echo[[:space:]]+[A-Za-z0-9+/=]{60,}|/dev/tcp/|nc[[:space:]]+-e|python[[:space:]]+-c[[:space:]]+.import|perl[[:space:]]+-e|chmod[[:space:]]+\+?x[[:space:]]+/(tmp|var/tmp|dev/shm)|(^|[;&|][[:space:]]*|[[:space:]](ba)?sh[[:space:]]+|[[:space:]]source[[:space:]]+)(/tmp|/var/tmp|/dev/shm)/[.a-zA-Z0-9_-]+|pastebin|raw\.githubusercontent|\.onion|transfer\.sh|bitbucket\.org/[^ ]*\.sh'

scan_cron_file() {
    local f="$1" line owned=0
    [ -r "$f" ] || return 0

    # Arquivo pertencente a um pacote (Issabel/FreePBX/EPEL) e' legitimo: rebaixa
    # para LOW. Ex.: /etc/cron.daily/geoip_update.sh do Issabel usa
    # 'curl -s $URL > /tmp/CountryInfo.txt', que e' comportamento normal.
    if have rpm && rpm -qf "$f" >/dev/null 2>&1; then
        owned=1
    fi

    while IFS= read -r line; do
        case "$line" in ''|'#'*|MAILTO=*|PATH=*|SHELL=*|HOME=*) continue ;; esac
        if printf '%s' "$line" | grep -qE "$BAD_CMD_PATTERN" 2>/dev/null; then
            if [ "$owned" -eq 1 ]; then
                add_finding LOW $C_PERSIST "cron de pacote com comando de risco (provavel legitimo) em ${f}: $(trunc "$line" 100)"
            else
                add_finding CRIT $C_PERSIST "cron malicioso em ${f}: $(trunc "$line" 130)"
            fi
            return 0
        fi
        if printf '%s' "$line" | grep -qiE "$MINER_TEXT" 2>/dev/null; then
            add_finding CRIT $C_MINER "cron referenciando minerador em ${f}: $(trunc "$line" 130)"
            return 0
        fi
    done < "$f"
}

check_cron() {
    local f d
    for f in /etc/crontab /etc/anacrontab; do
        scan_cron_file "$f"
    done
    for d in /etc/cron.d /etc/cron.hourly /etc/cron.daily /etc/cron.weekly /etc/cron.monthly /var/spool/cron /var/spool/cron/crontabs; do
        [ -d "$d" ] || continue
        for f in "$d"/*; do
            [ -f "$f" ] || continue
            scan_cron_file "$f"
            # arquivo em /etc/cron.d nao pertencente a pacote e recente
            if [ "$d" = "/etc/cron.d" ] && have rpm; then
                if ! rpm -qf "$f" >/dev/null 2>&1; then
                    if [ -n "$REF_RECENT" ] && [ "$f" -nt "$REF_RECENT" ]; then
                        add_finding MED $C_PERSIST "cron novo sem dono de pacote: ${f}"
                    fi
                fi
            fi
        done
    done

    # crontab do root modificado recentemente
    if [ -f /var/spool/cron/root ] && [ -n "$REF_RECENT" ] && [ /var/spool/cron/root -nt "$REF_RECENT" ]; then
        add_finding LOW $C_PERSIST "crontab do root modificado nos ultimos ${RECENT_DAYS} dias"
    fi
}

check_systemd() {
    local f content
    have systemctl || return 0
    for f in /etc/systemd/system/*.service /usr/lib/systemd/system/*.service /run/systemd/system/*.service; do
        [ -f "$f" ] || continue
        content=$(grep -iE '^(ExecStart|ExecStartPre)' "$f" 2>/dev/null)
        [ -z "$content" ] && continue
        if printf '%s' "$content" | grep -qE '(/tmp/|/var/tmp/|/dev/shm/)' 2>/dev/null; then
            add_finding CRIT $C_PERSIST "unit systemd executa binario de diretorio temporario: ${f}"
        elif printf '%s' "$content" | grep -qE "$BAD_CMD_PATTERN" 2>/dev/null; then
            add_finding CRIT $C_PERSIST "unit systemd com comando suspeito: ${f}"
        elif printf '%s' "$content" | grep -qiE "$MINER_TEXT" 2>/dev/null; then
            add_finding CRIT $C_MINER "unit systemd referenciando minerador: ${f}"
        fi
    done
}

check_startup_files() {
    local f
    for f in /etc/rc.local /etc/rc.d/rc.local /etc/profile /root/.bashrc /root/.bash_profile /etc/bashrc; do
        [ -r "$f" ] || continue
        if grep -qE "$BAD_CMD_PATTERN" "$f" 2>/dev/null; then
            add_finding HIGH $C_PERSIST "comando suspeito em arquivo de inicializacao: ${f}"
        fi
    done
    # ld.so.preload = classico de rootkit userland
    if [ -s /etc/ld.so.preload ]; then
        add_finding CRIT $C_ROOTKIT "/etc/ld.so.preload nao vazio: $(trunc "$(tr '\n' ' ' < /etc/ld.so.preload 2>/dev/null)" 120)"
    fi
}

SUSPECT_KEY_COMMENT='(t3rr0r|terr0r|h4ck|hax0r|hacked|pwn3d|pwned|0wned|r00t@|xploit|expl0it|backdoor|mdrfckr|botnet|anonymous@|@private$|@kali$|@parrot$|nobody@nowhere)'

declare -A KNOWN_KEY=()
KNOWN_KEYS_ACTIVE=0

# Fingerprint do MATERIAL da chave (campo 2), nunca do comentario.
# O comentario e' texto livre e pode ser copiado por um atacante; o blob nao.
key_fp() {
    local blob="$1" out=""
    if have sha256sum; then
        out=$(printf '%s' "$blob" | sha256sum 2>/dev/null | cut -c1-32)
    elif have openssl; then
        out=$(printf '%s' "$blob" | openssl dgst -sha256 2>/dev/null | sed 's/.*= *//' | cut -c1-32)
    elif have md5sum; then
        out=$(printf '%s' "$blob" | md5sum 2>/dev/null | cut -c1-32)
    fi
    printf '%s' "$out"
}

# Aceita tanto "<fingerprint>  rotulo" quanto a linha completa da chave publica
register_known_key() {
    local line="$1" fp label
    case "$line" in ''|'#'*) return 0 ;; esac
    case "$line" in
        ssh-*|ecdsa-*|sk-*)
            fp=$(key_fp "$(printf '%s' "$line" | awk '{print $2}')")
            label=$(printf '%s' "$line" | awk '{ if (NF>=3) { $1=""; $2=""; sub(/^[[:space:]]+/,""); print } else print "sem-rotulo" }')
            ;;
        *)
            fp=$(printf '%s' "$line" | awk '{print $1}' | cut -c1-32)
            label=$(printf '%s' "$line" | awk '{ if (NF>=2) { $1=""; sub(/^[[:space:]]+/,""); sub(/^#[[:space:]]*/,""); print } else print "sem-rotulo" }')
            ;;
    esac
    # Fingerprint valido tem 32 hex; descarta linha malformada em vez de
    # cadastrar lixo que nunca casaria com chave nenhuma.
    case "$fp" in
        [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]*) : ;;
        *) return 0 ;;
    esac
    [ ${#fp} -ne 32 ] && return 0
    KNOWN_KEY["$fp"]="$label"
    KNOWN_KEYS_ACTIVE=1
    return 0
}

load_known_keys() {
    local line n_builtin=0 n_file=0

    # 1) Defaults embutidos no script
    for line in "${BUILTIN_KNOWN_KEYS[@]:-}"; do
        [ -z "$line" ] && continue
        register_known_key "$line" && n_builtin=$((n_builtin + 1))
    done

    # 2) Arquivo local, se existir - SOMA, nao substitui
    if [ -r "$KNOWN_KEYS_FILE" ]; then
        while IFS= read -r line; do
            register_known_key "$line" && n_file=$((n_file + 1))
        done < "$KNOWN_KEYS_FILE"
    fi

    if [ "$KNOWN_KEYS_ACTIVE" -eq 1 ]; then
        add_note "allowlist de chaves ativa: ${#KNOWN_KEY[@]} confiavel(is) (${n_builtin} embutida(s), ${n_file} de arquivo)"
    else
        add_note "allowlist de chaves VAZIA - deteccao de chave nao autorizada desligada"
    fi
    return 0
}

# Modo utilitario: lista todas as chaves da maquina com fingerprint,
# para o operador montar o known_keys.conf.
list_keys_mode() {
    local user home f line blob fp comment
    local seen_files=" " seen_pairs=" "
    printf '# fingerprint                     usuario      comentario\n'
    while IFS=: read -r user _ _ _ _ home _; do
        [ -z "$home" ] && continue
        f="${home}/.ssh/authorized_keys"
        [ -r "$f" ] || continue
        # Contas diferentes podem compartilhar o mesmo home
        case "$seen_files" in *" $f "*) continue ;; esac
        seen_files="${seen_files}${f} "
        while IFS= read -r line; do
            blob=$(printf '%s' "$line" | awk '{print $2}')
            [ -z "$blob" ] && continue
            fp=$(key_fp "$blob")
            comment=$(printf '%s' "$line" | awk '{ if (NF>=3) { $1=""; $2=""; sub(/^[[:space:]]+/,""); print } else print "(sem-comentario)" }')
            # Mesma chave repetida DENTRO do mesmo arquivo e' anomalia de edicao
            case "$seen_pairs" in
                *" ${f}:${fp} "*)
                    printf '%-32s %-12s %s  [DUPLICADA no mesmo arquivo]\n' "$fp" "$user" "$comment"
                    continue ;;
            esac
            seen_pairs="${seen_pairs}${f}:${fp} "
            printf '%-32s %-12s %s\n' "$fp" "$user" "$comment"
        done < <(grep -E '^(ssh-|ecdsa-|sk-)' "$f" 2>/dev/null)
    done < /etc/passwd
}

check_ssh_keys() {
    local home user uid f count comments c blob fp trusted
    local seen_files=" "

    while IFS=: read -r user _ uid _ _ home _; do
        [ -z "$home" ] && continue
        [ -d "$home" ] || continue
        f="${home}/.ssh/authorized_keys"
        [ -f "$f" ] || continue
        [ -r "$f" ] || continue

        # Varias contas podem compartilhar o mesmo home (ex.: contas UID 0
        # maliciosas apontando para /root). Auditar o arquivo uma unica vez.
        case "$seen_files" in *" $f "*) continue ;; esac
        seen_files="${seen_files}${f} "

        count=0
        comments=""

        while IFS= read -r c; do
            [ -z "$c" ] && continue
            blob=$(printf '%s' "$c" | awk '{print $2}')
            [ -z "$blob" ] && continue
            count=$((count + 1))
            fp=$(key_fp "$blob")
            c=$(printf '%s' "$c" | awk '{ if (NF>=3) { $1=""; $2=""; sub(/^[[:space:]]+/,""); print } else print "(sem-comentario)" }')

            trusted=0
            if [ "$KNOWN_KEYS_ACTIVE" -eq 1 ] && [ -n "$fp" ] && [ -n "${KNOWN_KEY[$fp]+x}" ]; then
                trusted=1
            fi
            [ "$trusted" -eq 1 ] && continue

            [ -n "$comments" ] && comments="${comments} | "
            comments="${comments}${c}"

            # Comentario suspeito serve para ACUSAR, nunca para inocentar.
            if printf '%s' "$c" | grep -qiE "$SUSPECT_KEY_COMMENT" 2>/dev/null; then
                add_finding CRIT $C_PERSIST "chave SSH com identificacao suspeita em ${f}: '${c}' fp=${fp}"
            elif [ "$KNOWN_KEYS_ACTIVE" -eq 1 ]; then
                if [ "$uid" = "0" ]; then
                    add_finding CRIT $C_PERSIST "chave SSH NAO autorizada em conta UID 0 '${user}': '${c}' fp=${fp}"
                else
                    add_finding HIGH $C_PERSIST "chave SSH NAO autorizada em ${f}: '${c}' fp=${fp}"
                fi
            fi
        done < <(grep -E '^(ssh-|ecdsa-|sk-)' "$f" 2>/dev/null)

        [ "$count" -eq 0 ] && continue

        # Sem allowlist, cai na heuristica de data (bem mais fraca)
        if [ "$KNOWN_KEYS_ACTIVE" -eq 0 ]; then
            if [ -n "$REF_RECENT" ] && [ "$f" -nt "$REF_RECENT" ]; then
                add_finding MED $C_PERSIST "authorized_keys de '${user}' modificado nos ultimos ${RECENT_DAYS} dias (${count} chave(s)): $(trunc "$comments" 120)"
            elif [ "$uid" = "0" ]; then
                add_finding LOW $C_PERSIST "chaves SSH ativas para conta UID 0 '${user}' (${count}): $(trunc "$comments" 120)"
            fi
        fi

        if grep -qiE '(mdrfckr|hilde@)' "$f" 2>/dev/null; then
            add_finding CRIT $C_PERSIST "chave SSH com assinatura de kit malicioso conhecido em ${f}"
        fi
    done < /etc/passwd
}

#------------------------------------------------------------------------------
# 4. Contas e escalonamento
#------------------------------------------------------------------------------
check_accounts() {
    local user pass uid gid home shell line

    while IFS=: read -r user pass uid gid _ home shell; do
        [ -z "$user" ] && continue

        # UID 0 alem do root
        if [ "$uid" = "0" ] && [ "$user" != "root" ]; then
            add_finding CRIT $C_ACCOUNT "conta com UID 0 alem do root: '${user}' (shell=${shell})"
        fi

        # nomes classicos de backdoor
        if printf '%s' "$user" | grep -qiE '^(r00t|ro0t|r0ot|roott|rooot|toor|admin1|sysadm1n|hacker|backdoor|vnc|ftpuser1|oracle1|test123|mysql1|support1|www-data1|nobody1|system32|defaultuser|guest1|clamav1)$' 2>/dev/null; then
            add_finding HIGH $C_ACCOUNT "nome de usuario tipico de backdoor: '${user}' (uid=${uid} shell=${shell})"
        fi

        # senha vazia em conta com shell valido
        if [ "$pass" = "" ] && [ "$user" != "root" ]; then
            case "$shell" in
                */nologin|*/false|"") : ;;
                *) add_finding HIGH $C_ACCOUNT "conta sem senha e com shell valido: '${user}'" ;;
            esac
        fi
    done < /etc/passwd

    # shadow: hash vazio
    if [ -r /etc/shadow ]; then
        while IFS=: read -r user pass _; do
            [ -z "$user" ] && continue
            if [ -z "$pass" ]; then
                add_finding HIGH $C_ACCOUNT "conta com hash de senha vazio em /etc/shadow: '${user}'"
            fi
        done < /etc/shadow
    else
        [ "$DEGRADED" -eq 1 ] && add_note "/etc/shadow ilegivel (sem root)"
    fi

    # sudoers.d suspeito
    local f
    for f in /etc/sudoers.d/*; do
        [ -f "$f" ] || continue
        if grep -qE 'NOPASSWD:[[:space:]]*ALL' "$f" 2>/dev/null; then
            if have rpm && ! rpm -qf "$f" >/dev/null 2>&1; then
                if [ -n "$REF_RECENT" ] && [ "$f" -nt "$REF_RECENT" ]; then
                    add_finding MED $C_ACCOUNT "regra sudo NOPASSWD:ALL recente e sem dono de pacote: ${f}"
                fi
            fi
        fi
    done

    # binarios SUID fora dos diretorios de sistema
    if [ "$DEGRADED" -eq 0 ]; then
        local sf
        while IFS= read -r sf; do
            [ -z "$sf" ] && continue
            add_finding CRIT $C_ACCOUNT "binario SUID root em diretorio temporario/home: ${sf}"
        done < <(run find /tmp /var/tmp /dev/shm /home -xdev -maxdepth 3 -type f -perm -4000 -uid 0 -print 2>/dev/null | head -5)
    fi
}

#------------------------------------------------------------------------------
# 5. Webroot: webshells e arquivos suspeitos
#------------------------------------------------------------------------------
WEBSHELL_PATTERN='eval[[:space:]]*\([[:space:]]*(base64_decode|gzinflate|str_rot13|gzuncompress|\$_(POST|GET|REQUEST|COOKIE))|preg_replace[[:space:]]*\(.*/e|assert[[:space:]]*\([[:space:]]*\$_|(system|shell_exec|passthru|popen|proc_open)[[:space:]]*\([[:space:]]*\$_(POST|GET|REQUEST|COOKIE)|\$_(POST|GET|REQUEST)\[[^]]*\][[:space:]]*\([[:space:]]*\$_|create_function[[:space:]]*\(|FilesMan|WSO[[:space:]]*[0-9.]*Shell|c99shell|r57shell|b374k|IndoXploit|\$GLOBALS\[.[a-zA-Z0-9_]+.\]\[.[a-zA-Z0-9_]+.\]'

check_webroot() {
    local root f hits n=0
    [ -z "$REF_RECENT" ] && return 0

    for root in $WEBROOTS; do
        [ -d "$root" ] || continue

        # 5.1 scripts recentes com padrao de webshell
        while IFS= read -r f; do
            [ -z "$f" ] && continue
            [ -r "$f" ] || continue
            if grep -qlE "$WEBSHELL_PATTERN" "$f" 2>/dev/null; then
                if have rpm && rpm -qf "$f" >/dev/null 2>&1; then
                    continue   # pertence a pacote (Issabel/FreePBX legitimo)
                fi
                add_finding CRIT $C_WEBSHELL "possivel webshell: ${f}"
                n=$((n + 1))
                [ "$n" -ge 8 ] && break
            fi
        done < <(run find "$root" -xdev -type f \( -name '*.php' -o -name '*.php[0-9]' -o -name '*.phtml' -o -name '*.inc' -o -name '*.phar' \) -newer "$REF_RECENT" -print 2>/dev/null | head -400)

        [ "$n" -ge 8 ] && break

        # 5.2 codigo PHP escondido em arquivo com extensao de imagem/texto
        while IFS= read -r f; do
            [ -z "$f" ] && continue
            [ -r "$f" ] || continue
            if head -c 4096 "$f" 2>/dev/null | grep -qE '<\?php|<\?=' 2>/dev/null; then
                add_finding CRIT $C_WEBSHELL "codigo PHP dentro de arquivo nao-PHP: ${f}"
                n=$((n + 1))
                [ "$n" -ge 8 ] && break
            fi
        done < <(run find "$root" -xdev -type f \( -name '*.jpg' -o -name '*.jpeg' -o -name '*.png' -o -name '*.gif' -o -name '*.ico' -o -name '*.txt' -o -name '*.css' -o -name '*.log' \) -newer "$REF_RECENT" -print 2>/dev/null | head -400)

        [ "$n" -ge 8 ] && break

        # 5.3 arquivo executavel/ELF dentro do webroot
        while IFS= read -r f; do
            [ -z "$f" ] && continue
            add_finding HIGH $C_WEBSHELL "arquivo executavel dentro do webroot: ${f}"
            n=$((n + 1))
            [ "$n" -ge 10 ] && break
        done < <(run find "$root" -xdev -type f -perm -u+x ! -name '*.sh' ! -name '*.cgi' ! -name '*.pl' -newer "$REF_RECENT" -print 2>/dev/null | head -50)
    done
}

#------------------------------------------------------------------------------
# 6. Adulteracao / ocultacao
#------------------------------------------------------------------------------
check_tamper() {
    local f out

    # arquivos imutaveis fora do padrao (miners usam chattr +i)
    if have lsattr; then
        for f in /etc/resolv.conf /etc/crontab /var/spool/cron/root /etc/passwd /etc/hosts; do
            [ -e "$f" ] || continue
            out=$(lsattr -d "$f" 2>/dev/null | awk '{print $1}')
            case "$out" in
                *i*) add_finding HIGH $C_TAMPER "arquivo marcado como imutavel (chattr +i): ${f}" ;;
            esac
        done
        # binario imutavel em diretorio temporario
        while IFS= read -r f; do
            [ -z "$f" ] && continue
            add_finding CRIT $C_TAMPER "arquivo imutavel em diretorio temporario: $(trunc "$f" 120)"
        done < <(run lsattr -R /tmp /dev/shm /var/tmp 2>/dev/null | grep -E '^-{4}i' | head -5)
    fi

    # historico anulado
    for f in /root/.bash_history; do
        if [ -L "$f" ]; then
            out=$(readlink "$f" 2>/dev/null)
            case "$out" in
                /dev/null) add_finding HIGH $C_TAMPER "historico de comandos do root redirecionado para /dev/null" ;;
            esac
        fi
    done
    if [ -n "${HISTFILE+x}" ] && [ "$HISTFILE" = "/dev/null" ]; then
        add_finding MED $C_TAMPER "HISTFILE definido como /dev/null no ambiente"
    fi

    # binarios de sistema alterados (verificacao rpm em um subconjunto critico)
    if have rpm && [ "$DEGRADED" -eq 0 ]; then
        local bin
        for bin in /usr/bin/ps /usr/bin/top /usr/bin/netstat /usr/bin/ss /usr/bin/find /usr/bin/ls /usr/sbin/lsof /bin/ps /bin/ls /bin/netstat; do
            [ -f "$bin" ] || continue
            out=$(run rpm -Vf "$bin" 2>/dev/null | awk -v b="$bin" '$NF==b {print $1}')
            case "$out" in
                *5*) add_finding CRIT $C_ROOTKIT "binario de sistema com checksum alterado: ${bin}" ;;
            esac
        done
    fi

    # arquivos/diretorios classicos de kit
    local known
    for known in /tmp/.X11-unix/.rc /tmp/.X25-unix /dev/shm/.x /var/tmp/.systemd /usr/bin/kswapd0 /usr/bin/bioset /etc/cron.d/root_cron /usr/local/bin/dns /tmp/.ICE-unix/.x /bin/httpdns; do
        [ -e "$known" ] && add_finding CRIT $C_MINER "artefato conhecido de kit de mineracao presente: ${known}"
    done
}

#------------------------------------------------------------------------------
# 7b. Exposicao da PBXAPI / REST API do Issabel
#
# Vetor conhecido: requisicao HTTP sem autenticacao para o endpoint de manager
# da pbxapi permite disparar um Originate via AMI com Application=System, o que
# executa comando de shell como usuario 'asterisk'. Dali o atacante escala.
#
# IMPORTANTE: este modulo NUNCA toca o endpoint vulneravel. Ele sonda apenas o
# caminho base em 127.0.0.1 para descobrir se ha exigencia de credencial.
# Bater no /manager para "testar" dispararia uma chamada de verdade.
#------------------------------------------------------------------------------
PBXAPI_DIRS="/var/www/html/pbxapi /usr/share/issabel/pbxapi /var/www/html/admin/api /var/www/html/rest"

check_pbxapi() {
    local d installed=0 apidir="" code line ips n ip sample

    for d in $PBXAPI_DIRS; do
        if [ -d "$d" ]; then installed=1; apidir="$d"; break; fi
    done
    if [ "$installed" -eq 0 ] && have rpm; then
        rpm -qa 2>/dev/null | grep -qiE 'pbxapi|issabel-api' && installed=1
    fi
    [ "$installed" -eq 0 ] && return 0

    add_note "pbxapi detectada${apidir:+ em ${apidir}}"

    # --- 7b.1 Exige credencial? Sonda apenas o caminho base, em loopback.
    if have curl; then
        code=$(curl -s -o /dev/null -w '%{http_code}' -m 4 \
               --noproxy '*' "http://127.0.0.1/pbxapi/" 2>/dev/null)
        case "$code" in
            401|403)
                add_note "pbxapi exige autenticacao no caminho base (HTTP ${code})" ;;
            200|301|302)
                add_finding HIGH $C_PBX "pbxapi responde SEM credencial em 127.0.0.1 (HTTP ${code}) - confirmar se ha ACL na frente" ;;
            000|"")
                add_note "nao foi possivel sondar a pbxapi localmente (httpd fora do ar ou porta diferente)" ;;
        esac
    fi

    # --- 7b.2 Ha restricao de acesso no Apache para o caminho?
    local hasacl=0 f
    for f in /etc/httpd/conf.d/*.conf /etc/httpd/conf/httpd.conf; do
        [ -r "$f" ] || continue
        if grep -qiE '<(Location|Directory)[^>]*(pbxapi|/rest)' "$f" 2>/dev/null; then
            hasacl=1
            break
        fi
    done
    if [ "$hasacl" -eq 0 ]; then
        add_finding MED $C_PBX "nenhuma diretiva <Location>/<Directory> restringindo pbxapi no Apache"
    fi

    # --- 7b.3 Httpd escutando em interface publica
    if have ss; then
        if run ss -Hlnt 2>/dev/null | awk '{print $4}' | grep -qE '(^0\.0\.0\.0:(80|443)$|^\[::\]:(80|443)$|^\*:(80|443)$)'; then
            add_finding MED $C_PBX "httpd escutando em todas as interfaces com pbxapi instalada - restringir por firewall/VPN"
        fi
    fi

    # --- 7b.4 RASTRO: acessos a pbxapi vindos de IP publico no access_log.
    # Esta e' a evidencia mais direta de tentativa ou sucesso de exploracao.
    for f in /var/log/httpd/access_log /var/log/httpd/ssl_access_log /var/log/httpd/access_log.1; do
        [ -r "$f" ] || continue
        ips=$(run grep -a 'pbxapi' "$f" 2>/dev/null \
              | awk '{print $1}' \
              | grep -vE '^(127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|::1|localhost)' \
              | sort -u | head -20)
        [ -z "$ips" ] && continue
        n=$(printf '%s\n' "$ips" | grep -c . )
        sample=$(printf '%s' "$ips" | tr '\n' ' ')
        add_finding CRIT $C_PBX "acesso a pbxapi a partir de ${n} IP(s) PUBLICO(s) em ${f}: $(trunc "$sample" 110)"
    done
}

#------------------------------------------------------------------------------
# 7c. Rastro de exploracao via Originate/System no Asterisk
#------------------------------------------------------------------------------
check_asterisk_exec() {
    local f hits n

    for f in /var/log/asterisk/full /var/log/asterisk/messages /var/log/asterisk/full.1; do
        [ -r "$f" ] || continue

        # Originate ou AMI executando System()/Shell com comando de rede
        hits=$(run grep -aiE '(System|Shell|AGI)[^\n]{0,80}(curl|wget|/dev/tcp|base64|chmod \+x|/tmp/|python -c|perl -e)' "$f" 2>/dev/null | head -3)
        if [ -n "$hits" ]; then
            n=$(printf '%s\n' "$hits" | grep -c .)
            add_finding CRIT $C_PBX "execucao de comando de shell via dialplan em ${f}: $(trunc "$(printf '%s' "$hits" | head -1)" 130)"
        fi

        # Acao Originate recebida pelo AMI com Application System
        hits=$(run grep -aiE 'Originate.{0,200}Application.{0,20}System' "$f" 2>/dev/null | head -2)
        if [ -n "$hits" ]; then
            add_finding CRIT $C_PBX "AMI Originate com Application=System em ${f}: $(trunc "$(printf '%s' "$hits" | head -1)" 130)"
        fi
    done

    # live_dangerously libera funcoes perigosas para interfaces externas
    if [ -r /etc/asterisk/asterisk.conf ]; then
        if grep -qiE '^[[:space:]]*live_dangerously[[:space:]]*=[[:space:]]*yes' /etc/asterisk/asterisk.conf 2>/dev/null; then
            add_finding HIGH $C_PBX "asterisk.conf com live_dangerously=yes (funcoes perigosas liberadas para AMI/AGI)"
        fi
    fi
}

#------------------------------------------------------------------------------
# 7. Especifico de PBX (Issabel/Asterisk)
#------------------------------------------------------------------------------
check_pbx() {
    [ "$PBX_LABEL" = "none" ] && return 0
    local f

    # scripts AGI/AMI recentes fora de pacote
    if [ -d /var/lib/asterisk/agi-bin ] && [ -n "$REF_RECENT" ]; then
        while IFS= read -r f; do
            [ -z "$f" ] && continue
            if have rpm && rpm -qf "$f" >/dev/null 2>&1; then continue; fi
            if grep -qE "$BAD_CMD_PATTERN" "$f" 2>/dev/null; then
                add_finding CRIT $C_PBX "script AGI com comando suspeito: ${f}"
            fi
        done < <(run find /var/lib/asterisk/agi-bin -xdev -type f -newer "$REF_RECENT" -print 2>/dev/null | head -50)
    fi

    # contexto de discagem permitindo saida a partir do contexto default
    if [ -r /etc/asterisk/extensions_custom.conf ]; then
        if grep -qE '^\[default\]' /etc/asterisk/extensions_custom.conf 2>/dev/null; then
            if grep -A20 '^\[default\]' /etc/asterisk/extensions_custom.conf 2>/dev/null | grep -qE 'Dial\((SIP|PJSIP|IAX2|DAHDI)/' 2>/dev/null; then
                add_finding MED $C_PBX "contexto [default] com Dial() em extensions_custom.conf (risco de toll fraud)"
            fi
        fi
    fi

    # AMI aberto sem restricao
    if [ -r /etc/asterisk/manager.conf ]; then
        if grep -qE '^\s*bindaddr\s*=\s*0\.0\.0\.0' /etc/asterisk/manager.conf 2>/dev/null \
           && grep -qE '^\s*permit\s*=\s*0\.0\.0\.0/0\.0\.0\.0' /etc/asterisk/manager.conf 2>/dev/null; then
            add_finding MED $C_PBX "AMI (manager.conf) escutando em 0.0.0.0 com permit 0.0.0.0/0"
        fi
    fi
}

#------------------------------------------------------------------------------
# Execucao
#------------------------------------------------------------------------------
main() {
    setup_colors

    if [ "$MODE" = "listkeys" ]; then
        list_keys_mode
        exit 0
    fi

    detect_env
    check_privs

    TMPDIR_AUDIT=$(mktemp -d /tmp/.audit.XXXXXX 2>/dev/null)
    REF_RECENT=""
    if [ -n "$TMPDIR_AUDIT" ] && [ -d "$TMPDIR_AUDIT" ]; then
        REF_RECENT="${TMPDIR_AUDIT}/ref"
        if ! touch -d "-${RECENT_DAYS} days" "$REF_RECENT" 2>/dev/null; then
            if ! touch -t "$(date -d "-${RECENT_DAYS} days" '+%Y%m%d%H%M' 2>/dev/null)" "$REF_RECENT" 2>/dev/null; then
                REF_RECENT=""
                add_note "nao foi possivel criar referencia temporal - checagens por data ignoradas"
            fi
        fi
    else
        add_note "nao foi possivel criar diretorio temporario"
    fi

    load_known_keys

    check_processes
    check_network
    check_cron
    check_systemd
    check_startup_files
    check_ssh_keys
    check_accounts
    check_webroot
    check_tamper
    check_pbx
    check_pbxapi
    check_asterisk_exec

    # decisao final
    local has_crit=0 i
    for i in "${F_SEV[@]:-}"; do
        [ "$i" = "CRIT" ] && has_crit=1 && break
    done

    if [ "$has_crit" -eq 1 ] || [ "$SCORE" -ge "$SCORE_COMPROMISED" ]; then
        emit_and_exit 1 "evidence_found"
    fi

    if [ "$DEGRADED" -eq 1 ] && [ "$ALLOW_DEGRADED" -eq 0 ] && [ ${#F_MSG[@]} -eq 0 ]; then
        emit_and_exit 3 "insufficient_privileges"
    fi

    emit_and_exit 0 ""
}

main