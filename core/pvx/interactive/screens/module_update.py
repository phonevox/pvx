from pvx import config, update_check
from pvx.cli import discover_installed_modules
from pvx.interactive import widgets
from pvx.interactive.inputs import ask_select
from pvx.modules import installer, listing


def update_modules(names):
    # extraído pra reuso -- pvx.interactive.screens.root usa isso direto pro
    # atalho "pvx > atualizar > tudo" (core + todos os módulos numa ação só).
    try:
        # achado ao vivo: reinstalava e anunciava "atualizado" pra TODO
        # módulo selecionado, mesmo pros que já estavam na última versão.
        outdated = listing.outdated_names(names, discover_installed_modules(), config.registry_index_url())
    except RuntimeError as e:
        widgets.failed(str(e))
        return

    for name in names:
        if name not in outdated:
            widgets.message(f"{name} já está atualizado.")
            continue
        try:
            with widgets.spinner(f"Atualizando {name}..."):
                installer.install(name, config.registry_index_url())
        except (RuntimeError, ValueError) as e:
            widgets.failed(str(e))
        else:
            widgets.success(f"{name} atualizado.")

    # achado ao vivo: o cache de update_check.py (TTL 6h) ficava com a versão
    # de antes da atualização, mostrando "atualização disponível" pra módulo
    # que acabou de ser atualizado -- discover_installed_modules() de novo
    # (não reusa a lista de antes) pra refletir o .pyz já sobrescrito.
    update_check.pending_notices(discover_installed_modules(), force=True)


class ModuleUpdateScreen:
    def render(self):
        modules = discover_installed_modules()
        if not modules:
            widgets.breadcrumb("pvx > módulos > atualizar")
            widgets.message("nenhum módulo instalado.")
            widgets.pause()
            return "BACK"

        selected = ask_select(
            "pvx > módulos > atualizar >", list(modules.keys()) + ["todos", "voltar"]
        )
        if selected is None or selected == "voltar":
            return "BACK"

        names = list(modules) if selected == "todos" else [selected]
        update_modules(names)

        widgets.pause()
        return "BACK"
