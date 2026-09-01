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
