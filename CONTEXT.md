# pvx

Vocabulário de domínio do projeto -- glossário, não spec de implementação.

## Language

**UOE (Upload-Only Endpoint)**:
Serviço HTTP interno da Phonevox (`uoe.interno.falevox.com.br`) que guarda os backups enviados pelo `pbackup`. Acessível direto da central do cliente (confirmado -- não é só rede interna da Phonevox).
_Avoid_: upload-only-api, UOA

**Superadmin**:
A conta `root` embutida do UOE, usada uma vez por central pra registrar o client user daquela central. Credencial nunca persiste em lugar nenhum -- o técnico fornece a senha na hora, sempre.
_Avoid_: admin, root user

**Client user**:
Conta do UOE criada pra uma central específica (`register`), escopada ao próprio `root_path`. Username e senha nunca persistem na central -- só o token atual dele.
_Avoid_: cliente, tenant

**Token**:
JWT emitido pelo UOE no login, amarrado a um client user. Logar de novo (por qualquer um) invalida o token anterior na hora -- o UOE guarda exatamente um token ativo por usuário.
_Avoid_: JWT, access token

**Relogin**:
Ação que reautentica um client user (senha fornecida na hora, nunca guardada) pra obter um token novo e atualizá-lo onde ele é usado (a linha de cron).
_Avoid_: amend-token, token refresh

**root_path**:
Escopo de armazenamento do client user dentro do UOE -- string livre, definida no registro. `clientes/<idcliente>-<idcontrato>-<empresa>` é a convenção usual pra cliente externo, não uma regra do UOE (ex.: instalação numa máquina interna da Phonevox usa outra coisa).

**pbackup**:
CLI da Phonevox (abstração sobre rclone) instalado em cada central -- o processo que de fato envia arquivos pra um remote (remote do rclone, ou via `--token`, um endpoint HTTP do UOE).

**Backup script**:
Script que o pbackup roda a partir da cron -- um dos dois presets mantidos pela Phonevox (`issabel.sh` pra config/gravações do Issabel, `magnus.sh` pro MagnusBilling) ou um comando totalmente customizado fornecido pelo técnico. No comando customizado, o técnico escreve `{TOKEN}` literal onde o token deve entrar -- é isso que o `relogin` substitui depois.

**Managed cron entry**:
A linha de cron que o próprio pvx criou e mantém pra uma central, identificada por um comentário-marcador fixo (não por conteúdo/fuzzy match) -- é o que permite `install`/`relogin` acharem e atualizarem a linha certa de forma determinística.
_Avoid_: entrada de cron do pvx

**Legacy backup routine**:
Qualquer linha de cron relacionada a backup que existia antes da migração pra UOE (ou que não tem o marcador de managed cron entry). Nunca é removida automaticamente -- só listada como candidata pro técnico escolher o que apagar.
_Avoid_: cron antiga, rotina obsoleta

## Handover (sessão de 2026-09-09)

Seção de transição pra próxima sessão -- não é glossário, é estado. Pode ser
substituída/arquivada por quem retomar, não é permanente feito o resto deste
arquivo.

**Estado do repo**: `main` e `dev` idênticos (PR #21 mergeado). Core em
`0.2.26`, release `v0.2.26` cortada no GitHub **corretamente** (ver achado
crítico abaixo). Módulos tocados nesta sessão: `firewall` 0.2.11, `autobackup`
0.1.15, `ssl` 0.1.2, `qint` 0.1.16, `motd` 0.1.11, `netinstall` 0.1.22,
`magnus` 0.1.8 -- todos deployados na VPS compartilhada de teste
(`167.114.97.2`, user `rocky`), exceto `qint`/`ssl` (não instalados lá; só
build local + handoff de `dist/`).

**Achado crítico desta sessão -- releases anteriores saíam mislabeled como
"nightly"**: `core/build.sh` só omite o stamp de branch/commit
(`pvx._build_stamp`) se rodar com `PVX_RELEASE_BUILD=1` (documentado em
`docs/plano.md`, nunca seguido nas releases cortadas até aqui). Toda
`gh release create` anterior a `v0.2.26` (v0.2.2 até v0.2.18, pelo menos) foi
buildada sem essa env var -- qualquer host que instalou/atualizou por elas
mostra `pvx --version` como `X.Y.Z (nightly, <commit>)`, mesmo sendo a release
oficial (confirmado ao vivo: servidor de produção do usuário, `pvx self-update`
recusando "atualizar" por achar que já tava numa build não-oficial --
confirmado em pelo menos DOIS servidores de produção diferentes do usuário,
ambos travados em "0.2.18 (nightly, ee51393)" mesmo depois de rodar
`self-update` várias vezes, porque `releases/latest` continuava apontando
pra essa mesma build mal-formada). **v0.2.26 foi cortada certo**
(`PVX_RELEASE_BUILD=1 sh build.sh` + confirmado via zipimport que não tem
`_build_stamp`, e via `curl releases/latest/download/core-manifest.json` que
já é `v0.2.26` como "Latest" no GitHub). Releases antigas (v0.2.2--v0.2.18)
não foram re-cortadas nem deletadas -- daqui pra frente `pvx self-update`
nesses hosts deve puxar `0.2.26` sem o aviso de nightly; se algum host ainda
reportar o sintoma depois de rodar `self-update` de novo, investigar mais
(pode ser cache de CDN do GitHub, ou o host mirando uma URL antiga).

**Daqui pra frente, toda release de core é**:
```sh
PVX_RELEASE_BUILD=1 sh build.sh   # nunca "sh build.sh" cru pra release
python3 -c "..." # gera dist/core-manifest.json (hash do .pyz + versão)
gh release create vX.Y.Z dist/core.pyz dist/core-manifest.json --repo phonevox/pvx --target main --title vX.Y.Z --notes "..."
```
Nunca cortar release sem perguntar antes (é ação pública/irreversível) --
exceto quando o próprio usuário já pediu explicitamente na mesma
conversa ("corta aê").

**Gotcha de git pego nesta sessão**: `git checkout <branch> -- .` resolve
`<branch>` pelo ref **local**, não `origin/<branch>` -- se o branch local
estiver desatualizado (aconteceu com `main` local, 31 commits atrás do
remoto), isso sobrescreve a working tree com conteúdo velho silenciosamente
(sem aviso, sem conflito). Pra conferir/copiar conteúdo de um branch remoto,
sempre `origin/<branch>` explícito, ou `git fetch` + `git branch -f <branch>
origin/<branch>` antes.

**Trabalho desta sessão, por tema** (commits em `dev`, já em `main`):
- Auditoria sistemática do qint (sgp vs ixcsoft) contra os installers bash
  originais (`phonevox/qint`) -- achou e corrigiu aspas indevidas na linha de
  `#include`/`#tryinclude` do dialplan (os bugs maiores de destino de
  áudio/macro já tinham sido corrigidos numa sessão anterior).
- Sistema de telas temáveis no core: `widgets.title/section/description/item/
  warning`, unificados com `success/failed` num só pipeline (`_print_outcome`
  + `_LINE_BUILDERS`). Tema ganhou 4 eixos independentes em `pvx > tema >`:
  cor (já existia), símbolos (glifos de aviso/seção/item), moldura (caractere
  do título), formato (layout de sucesso/erro/aviso -- 8 presets, default
  `modern-full-color`). `pvx > tema > render-test` mostra tudo de uma vez.
- Vocabulário de categoria unificado em **sucesso/erro/aviso** em todo o pvx
  (antes: `success`="sucesso", `failed`="falha", `check_result`="ok"/"erro").
  `check_result()` (usado em preflights, ex. netinstall) passou a usar o
  mesmo pipeline/formato temável -- antes era layout fixo, sem cor
  configurável.
- `autobackup check` e `ssl check` corrigidos: "ainda não configurado"/"sem
  certificado emitido" saíam como ERRO (vermelho) sem ter quebrado nada --
  agora são AVISO. `ssl check` reaproveita `_RENEW_WARNING_DAYS` (15 dias)
  como limiar sucesso/aviso; expirado é erro de verdade.
- Menu interativo raiz ganhou `versão` e `atualizar` (self-update).
- `pvx/update_check.py` (novo): aviso automático de atualização pendente
  (core via `core-manifest.json` do GitHub, módulos via `listing.list_modules`
  já existente) no `pvx >`, cache de 6h em `~/.pvx/update_check.json`,
  best-effort/silencioso, **só no modo interativo** (nunca na CLI direta).

**Pendências/perguntas em aberto que não foram resolvidas**:
- Releases antigas (v0.2.2--v0.2.18) continuam no ar com o bug de
  mislabeling -- não foram re-cortadas.
- `qint`/`ssl`: `dist/module.pyz` + `dist/manifest.json` prontos localmente,
  usuário ainda não confirmou ter aplicado na central de produção real.
- Trabalho de UI/UX pausado numa sessão anterior (mockups em
  `scripts/_mockup_*.py`) foi retomado e virou o sistema de temas acima --
  os arquivos de mockup em `scripts/` ainda existem no disco (gitignored),
  podem ser removidos se não forem mais úteis.
