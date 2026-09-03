# modules/ — CONTEXT.md

Guia prático pra criar um módulo novo do zero. Filosofia geral (TDD, aprovação
humana, convenções de código) já está em `/CLAUDE.md` — não repete aqui. Isto
aqui é o "playbook": estrutura de arquivos, o que cada peça faz, e os
gotchas já pisados em módulos anteriores (zabbix, uoe, netinstall, firewall,
qint, ssh-hardening, dummy — são a referência viva, olha um deles sempre que
em dúvida).

**Se o usuário pedir algo que quebra uma convenção daqui, avisa explicitamente
e pergunta se é pra atualizar este arquivo** — senão o próximo módulo (feito
por outro agente, sem o contexto desta conversa) volta a fazer do jeito
antigo.

## Layout de um módulo

```
modules/<nome>/
├── manifest.json
├── build.sh
├── pyproject.toml
├── src/
│   ├── main.py          # obrigatório — PvxModule + comandos Click
│   ├── <unidade>.py      # um arquivo por responsabilidade (ver "Divisão de arquivos")
│   └── ...
└── tests/
    ├── conftest.py         # isolamento de PVX_HOME -- ver "Testes"
    ├── test_main.py
    ├── test_<unidade>.py
    └── test_build.py      # opcional, mas recomendado (ver "Teste de packaging")
```

`<nome>` é o nome do módulo, do diretório, do `manifest.json.name` e do grupo
Click raiz (`pvx <nome> ...`) — sempre os quatro iguais.

## manifest.json

```json
{
  "name": "<nome>",
  "version": "0.1.0",
  "entrypoint": "main:cli",
  "description": "...",
  "author": "pvx",
  "min_pvx_version": "0.1.0",
  "checksum_sha256": "",
  "dependencies": []
}
```

- `entrypoint` no manifest **fonte** é sempre `"main:cli"` (aponta pro layout
  `src/main.py`). O `build.sh` gera um `dist/manifest.json` separado com
  `entrypoint: "module:cli"` — não edita o `entrypoint` do fonte manualmente.
- `checksum_sha256` no fonte fica sempre `""` — só o `dist/manifest.json`
  (gerado pelo build) tem o hash real, calculado em cima do `.pyz` publicado.
- **Version bump**: qualquer mudança no módulo (feature, fix, mesmo trivial)
  bump de `patch` no `manifest.json` **e** em `MagnusModule.version`/
  `<X>Module.version` dentro de `main.py` — os dois têm que bater.

## build.sh

Copia **todo** `src/*.py` (não só o entrypoint) pra um dir temporário, renomeia
`main.py` → `module.py`, empacota com `zipapp`. Motivo: os arquivos do módulo
se importam entre si por nome de topo (`import backup_scripts`, não
`from src import backup_scripts`) — todos precisam estar juntos na raiz do
`.pyz`, senão o import quebra em runtime.

Copia o `build.sh` de um módulo existente com mais de um arquivo (ex.:
`modules/zabbix/build.sh`) e ajusta só o nome — o script é idêntico em todos
os módulos, isso não é acidente, é convenção: **nunca escreve um `build.sh` do
zero**. (`modules/dummy/build.sh` é a exceção — só tem `main.py`, um único
`cp` em vez de `cp src/*.py`; não copia esse.)

## pyproject.toml

```toml
[tool.pytest.ini_options]
pythonpath = [".", "src", "../../core"]
```

Padrão de todo módulo com mais de um arquivo em `src/` (todos exceto
`dummy`, que é o único de arquivo único). Com isso, os testes importam os
módulos pelo nome bare (`import backup_scripts`, `from main import cli`),
igual ao jeito que o código dentro de `src/` já se importa — e igual ao
layout achatado que o `.pyz` final vai ter. **Nunca** `pythonpath = [".",
"../../core"]` sem `"src"` a não ser que o módulo seja de arquivo único.

## src/main.py

```python
import click
from pvx.interactive import widgets
from pvx.interactive.inputs import ask_confirm, ask_select, ask_text, ask_password
from pvx.modules.base import PvxModule

import <outras_unidades_do_modulo>


def _is_interactive():
    return sys.stdin.isatty()


class <Nome>Module(PvxModule):
    name = "<nome>"
    version = "0.1.0"

    def cli_group(self):
        @click.group(name="<nome>")
        def group():
            pass

        @group.command(name="...")
        @click.option(...)
        def algo_cmd(...):
            ...

        return group


cli = <Nome>Module()
```

- `interactive_entry()` **não é implementado** a não ser que o módulo precise
  de um wizard/fluxo de tela custom de verdade. Sem implementar, o core cai
  no auto-menu (`auto_menu.build_choices()` + `ask_select`, introspecção do
  `cli_group()`) — é o caminho de todos os módulos hoje (zabbix, uoe,
  netinstall, firewall, qint, ssh-hardening). Não implementa "só por
  garantia" — é o erro que já pegou o M12/M7 (ver `/CLAUDE.md` → Lições
  aprendidas).
- **Limitação atual do auto-menu**: `build_choices()` devolve só os *nomes*
  dos comandos — não existe subtítulo/descrição no menu interativo hoje. Se
  um comando precisa de aviso antes de rodar (ex.: "isso executa um script
  de terceiro"), isso vai no `ask_confirm()` do próprio comando, não em
  metadado de menu que não existe. Adicionar descrição ao core é uma
  melhoria própria, fora do escopo de criar um módulo — se o usuário pedir
  isso, é conversa separada.

## Divisão de arquivos ("Responsabilidade única por parte", aplicado)

`main.py` **orquestra**: le flags/prompts, decide o que chamar, formata
saída. Nunca faz `subprocess`/IO direto — isso vive em módulo(s) de
"ops" (`install_steps.py`, `pbackup_ops.py`, `os_ops.py`, `crontab.py`,
`state.py`, ...). Motivo prático, não só estético: código em `main.py` é
testado via `CliRunner` mockando essas funções (`patch("main.algo_ops.foo")`)
— se a lógica real estivesse dentro do comando Click, teria que mockar
`subprocess.run` em vez de uma função com nome que diz o que ela faz, e o
teste fica ilegível.

Um arquivo por responsabilidade, não um `utils.py` genérico. Exemplos reais:
`crontab.py` (só cron), `state.py` (só persistência local), `sudoers.py` (só
regra sudoers), `system_info.py` (só detecção de SO/provider). Se está em
dúvida se algo é uma responsabilidade nova ou cabe em um arquivo existente,
pergunta: "esse arquivo continua fazendo *uma coisa só* se eu adicionar
isso?".

## Interativo vs headless

Todo comando que precisa de um valor tem que funcionar dos dois jeitos, sem
duplicar a validação:

```python
if valor is None:
    if not interactive:
        raise click.ClickException("informe --valor.")
    valor = ask_text("Valor:")
    if valor is None:
        return  # usuário deu Esc — não é erro, só "voltar"
```

- `interactive = _is_interactive()` (checa `sys.stdin.isatty()`) — calculado
  uma vez no começo do comando, passado adiante.
- `ask_*` devolvendo `None` = usuário apertou Esc/Ctrl-Q — trata como "aborta
  essa operação sem erro", nunca deixa `None` vazar pra frente sem checar.
- Senha **nunca** por parâmetro de CLI direto (fica em `~/.bash_history`,
  `ps aux`) — sempre `--xxx-password-file <path>` (lido e stripado) na CLI
  direta, `ask_password()` (sem default, nunca ecoa) no modo interativo.
- `widgets.pause()` só é chamado quando `interactive` é `True`, e só uma vez
  por comando, no final (sucesso ou "nada foi alterado") — nunca em erro
  (`click.ClickException` já para a execução sozinho, sem precisar de pause).
- Toda ação destrutiva exige confirmação: `--yes` pula o `ask_confirm()` na
  CLI direta, mas **uma flag `--yes` nunca implica automaticamente uma
  segunda ação mais destrutiva** (ex.: `uoe remove --yes` apaga a cron local,
  mas só apaga o usuário remoto com `--delete-remote-user` explícito, ou
  confirmação própria no modo interativo).
- Widgets sempre de `pvx.interactive.widgets` (`success`, `failed`, `state`,
  `spinner`, `step`, `message`, `pause`) e inputs sempre de
  `pvx.interactive.inputs` — nunca `questionary`/`rich` importado direto num
  módulo, nunca cor hardcoded (sempre a paleta do `theme.py` via os
  wrappers). Já mordemos isso uma vez (ver `/CLAUDE.md`).

## Segredos e estado local

- Token/senha salvos em disco (`state.py`-like): JSON com `os.chmod(0o600)`
  antes de mover pro lugar final (`tmp + os.replace`, nunca escreve o
  arquivo final direto — evita ficar com conteúdo pela metade se cair no
  meio da escrita).
- Nunca imprime um token/senha inteiro em tela, log ou mensagem de
  confirmação — se precisar mostrar que "existe", redige (primeiros ~8
  chars + `...`, ver `_redact()` em `uoe/src/main.py`).
- Caminho de estado do módulo: `pvx_config.modules_dir() / "<nome>" / "state"`,
  criado com `mkdir(parents=True, exist_ok=True)` antes de usar.

## Logging

`self.get_logger()` (vem de `PvxModule`, usa `get_module_logger(self.name)`)
— nunca configura `logging` manualmente dentro do módulo. Loga eventos que
importam pra debug pós-fato (`logger.info(...)` no fim de uma operação bem
sucedida, `logger.error(...)` antes de levantar um `ClickException` vindo de
uma chamada externa) — não loga todo passo intermediário.

Construir `cli_group()` sozinho **nunca** deve tocar o logger (só o comando
sendo de fato executado toca) — vira teste de regressão padrão
(`test_building_the_cli_group_alone_does_not_touch_the_logger`).

## Testes

- **`tests/conftest.py` é obrigatório, copiado verbatim de outro módulo**
  (idêntico em todos, mesma lógica de `build.sh`/`pyproject.toml`): um
  fixture `autouse` que aponta `PVX_HOME` pra um tmpdir descartável antes de
  cada teste. Sem isso, qualquer teste que toque `self.get_logger()` (ou
  qualquer outro caminho que passe por `config.pvx_home()` sem mock
  profundo) tenta escrever de verdade em `/etc/pvx` — funciona sem querer
  numa máquina de dev rodando como root, mas quebra com `PermissionError`
  em qualquer outra (CI, container não-root). Um `conftest.py` na raiz do
  repo **não pega** aqui — cada módulo tem seu próprio `pyproject.toml`
  (vira rootdir do pytest), então a descoberta de conftest não sobe até lá;
  precisa estar dentro de `tests/` do próprio módulo.
- `unittest` + `click.testing.CliRunner` pra comandos, `unittest.mock.patch`
  pra tudo que é I/O externo (subprocess, filesystem fora de tempdir, rede,
  `main._is_interactive`). Nunca um teste chama um binário/serviço de
  verdade (systemctl, mysql, crontab, curl) — sempre mockado.
- Padrão de nome: `Test<Algo>` vira `class <Algo>Test(unittest.TestCase)`,
  um método `test_descreve_o_comportamento_em_ingles_ou_pt_consistente_com_
  o_resto_do_arquivo` por caso.
- Toda função que só faz sentido headless E interativo ganha teste dos dois
  lados (`is_tty=True`/`False`) — inclusive o "pausa quando interativo / não
  pausa quando não é".
- Mensagem de erro nunca deixa vazar traceback pra CLI (`assertNotIn
  ("Traceback", result.output)`) — `click.ClickException` cuida disso
  sozinho, só cuidado pra sempre levantar `ClickException` (não uma
  exception genérica) nos caminhos de erro esperado.

### Teste de packaging (`test_build.py`)

Roda `sh build.sh` de verdade e confere que o `checksum_sha256` do
`dist/manifest.json` bate com o hash real do `dist/module.pyz` gerado — pega
regressão de "build.sh quebrado" ou "manifest desatualizado" antes de virar
problema em produção. Copia o de `modules/dummy/tests/test_build.py` ou
`modules/ssh-hardening/tests/test_build.py` — é idêntico entre módulos.

## Deploy / registry

Módulo novo/alterado vai direto pro VPS por padrão (não sobe pro registry
sozinho) — publicação no registry é `scripts/publish.sh`, rodado pelo Adrian
com credenciais próprias, não automático. Ver memória de projeto (`[Module
deploy workflow]`) se precisar dos detalhes de deploy manual num host.

## TDD (lembrete, processo completo em `/CLAUDE.md`)

Testes propostos e aprovados **antes** da implementação, um "corte" por vez
(não precisa ser um teste isolado por vez — um arquivo de testes inteiro pra
uma unidade coesa, ex.: todos os testes de `backup_ops.py`, é um corte
razoável). Red confirmado antes de implementar. Teste aprovado é baseline —
não se edita pra conveniência da implementação.
