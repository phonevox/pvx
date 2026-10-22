# Context Map

## Contexts

- [UOE / Autobackup](./CONTEXT.md): registro de central no Upload-Only Endpoint, tokens e a cron gerenciada que envia backups pro UOE via `pbackup`
- [Backup/restore Issabel](./modules/issabel/CONTEXT.md): captura e restauração de backups do Issabel (componentes oficiais e extras Phonevox), com ou sem o backupengine parcheado

## Relationships

Sem sobreposição hoje -- são dois domínios de backup completamente distintos (um é sobre *pra onde* mandar o arquivo de backup e como autenticar nisso; o outro é sobre *o que* vai dentro do arquivo e como o Issabel entende isso). Nenhum dos dois termos de um contexto é usado no outro.
