import questionary
from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl

from pvx.interactive import theme, widgets

NAV_HINT_TEXT = "↑↓ navega · enter confirma · esc/q volta · ctrl-c fecha o pvx"
CHECKBOX_NAV_HINT_TEXT = "↑↓ navega · espaço marca · enter confirma · esc volta · ctrl-c fecha o pvx"

_BACK = object()


def _ask(question, include_q=False):
    back_binding = KeyBindings()

    @back_binding.add(Keys.Escape, eager=True)
    def _(event):
        event.app.exit(result=_BACK)

    if include_q:
        @back_binding.add("q", eager=True)
        def _(event):
            event.app.exit(result=_BACK)

    question.application.key_bindings = merge_key_bindings(
        [question.application.key_bindings, back_binding]
    )

    # unsafe_ask(): não engole KeyboardInterrupt (Ctrl-C) -- questionary
    # trataria como "cancelado" igual o Esc; aqui precisa propagar pra
    # fechar o pvx inteiro, não só voltar uma tela.
    result = question.unsafe_ask()
    return None if result is _BACK else result


class _ScrollableList:
    # estado + renderização de uma lista com viewport fixo (WINDOW_SIZE
    # linhas visíveis por vez, desliza acompanhando o cursor, com
    # indicadores de quanto mais tem acima/abaixo) -- questionary.select()/
    # checkbox() sempre renderizam a lista inteira de uma vez, sem viewport
    # limitado, e não dá pra configurar isso via parâmetro da lib.
    WINDOW_SIZE = 5
    # flag única controlando os indicadores de scroll: True = "↑ mais N
    # acima"/"↓ mais N abaixo", False = só a seta.
    SHOW_SCROLL_COUNT = True

    def __init__(self, choices, multi=False, default=None, window_size=WINDOW_SIZE):
        self.choices = [questionary.Choice.build(c) for c in choices]
        self.multi = multi
        self.window_size = window_size
        self.window_start = 0
        self.selected = {c.value for c in self.choices if c.checked} if multi else set()
        self.pointed_at = self._initial_pointer(default)

    def _selectable_indexes(self):
        return [i for i, c in enumerate(self.choices) if not c.disabled]

    def _initial_pointer(self, default):
        selectable = self._selectable_indexes()
        if not selectable:
            return 0
        if default is not None:
            for i in selectable:
                if self.choices[i].value == default:
                    return i
        return selectable[0]

    def _move(self, delta):
        selectable = self._selectable_indexes()
        if not selectable:
            return
        pos = selectable.index(self.pointed_at) if self.pointed_at in selectable else 0
        self.pointed_at = selectable[(pos + delta) % len(selectable)]

    def move_down(self):
        self._move(1)

    def move_up(self):
        self._move(-1)

    def toggle(self):
        if not self.multi:
            return
        choice = self.choices[self.pointed_at]
        if choice.disabled:
            return
        self.selected.symmetric_difference_update({choice.value})

    def result(self):
        if self.multi:
            return [c.value for c in self.choices if c.value in self.selected]
        return self.choices[self.pointed_at].value if self.choices else None

    def current_title(self):
        return self.choices[self.pointed_at].title if self.choices else None

    def visible_range(self):
        n = len(self.choices)
        if self.window_size is None:
            return 0, n
        size = min(self.window_size, n)
        if size == 0:
            return 0, 0
        start = self.window_start
        if self.pointed_at < start:
            start = self.pointed_at
        elif self.pointed_at >= start + size:
            start = self.pointed_at - size + 1
        start = max(0, min(start, n - size))
        self.window_start = start
        return start, start + size

    def render_lines(self):
        n = len(self.choices)
        start, end = self.visible_range()
        lines = []

        if start > 0:
            text = f"   ↑ mais {start} acima" if self.SHOW_SCROLL_COUNT else "   ↑"
            lines.append([("class:separator", text)])

        for i in range(start, end):
            choice = self.choices[i]
            current = i == self.pointed_at
            line = []
            if isinstance(choice, questionary.Separator):
                line.append(("class:separator", f"   {choice.title}"))
            else:
                line.append(("class:pointer" if current else "class:text", f" {'»' if current else ' '} "))
                if self.multi:
                    checked = choice.value in self.selected
                    line.append(("class:selected" if checked else "class:text", f"{'●' if checked else '○'} "))
                title = choice.title if isinstance(choice.title, str) else str(choice.title)
                line.append(("class:highlighted" if current else "class:text", title))
                if current and choice.description:
                    line.append(("class:separator", f"  — {choice.description}"))
            lines.append(line)

        if end < n:
            text = f"   ↓ mais {n - end} abaixo" if self.SHOW_SCROLL_COUNT else "   ↓"
            lines.append([("class:separator", text)])

        return lines

    def tokens(self):
        tokens = []
        for line in self.render_lines():
            tokens.extend(line)
            tokens.append(("", "\n"))
        if tokens:
            tokens.pop()
        return tokens


def _build_bindings(state, qmark_binding_for_back=True):
    # separado da montagem do Application/Layout (_run_scrollable) só pra
    # dar pra testar cada handler isolado, sem precisar rodar um terminal
    # de verdade.
    bindings = KeyBindings()

    @bindings.add(Keys.Down, eager=True)
    @bindings.add("j", eager=True)
    def _(event):
        state.move_down()

    @bindings.add(Keys.Up, eager=True)
    @bindings.add("k", eager=True)
    def _(event):
        state.move_up()

    @bindings.add(Keys.ControlM, eager=True)
    def _(event):
        event.app.exit(result=state.result())

    @bindings.add(Keys.Escape, eager=True)
    def _(event):
        event.app.exit(result=None)

    if qmark_binding_for_back:
        @bindings.add("q", eager=True)
        def _(event):
            event.app.exit(result=None)

    if state.multi:
        @bindings.add(" ", eager=True)
        def _(event):
            state.toggle()

    @bindings.add(Keys.ControlC, eager=True)
    @bindings.add(Keys.ControlQ, eager=True)
    def _(event):
        # não engole ctrl-c: precisa fechar o pvx inteiro, mesma convenção
        # de _ask()/unsafe_ask() pros outros prompts.
        event.app.exit(exception=KeyboardInterrupt)

    return bindings


def _run_scrollable(msg, state, nav_hint):
    message_control = FormattedTextControl(
        lambda: [("class:qmark", "?"), ("class:question", f" {msg} ")]
    )
    list_control = FormattedTextControl(state.tokens)
    hint_control = FormattedTextControl([("class:separator", nav_hint)])

    layout = Layout(HSplit([
        Window(message_control, height=1, dont_extend_height=True),
        Window(list_control, dont_extend_height=True),
        Window(hint_control, height=1, dont_extend_height=True),
    ]))

    app = Application(
        layout=layout,
        key_bindings=_build_bindings(state, qmark_binding_for_back=not state.multi),
        style=theme.current_style(),
        full_screen=False,
        erase_when_done=True,
    )
    return app.run()


def ask_select(msg, choices, default=None, window_size=_ScrollableList.WINDOW_SIZE):
    # window_size=None mostra a lista inteira, sem scroll/setas -- o menu
    # raiz usa isso de propósito (lista curta, fixa, navegada toda hora --
    # scroll ali atrapalha mais do que ajuda).
    state = _ScrollableList(choices, default=default, window_size=window_size)
    result = _run_scrollable(msg, state, NAV_HINT_TEXT)
    if result is not None:
        widgets.select_answer(msg, state.current_title())
    return result


def ask_checkbox(msg, choices, defaults=None):
    defaults = defaults or []
    wrapped = [questionary.Choice(title=str(c), value=c, checked=c in defaults) for c in choices]
    state = _ScrollableList(wrapped, multi=True)
    result = _run_scrollable(msg, state, CHECKBOX_NAV_HINT_TEXT)
    if result is not None:
        widgets.checkbox_answer(msg, result)
    return result


def ask_confirm(msg, default=True):
    question = questionary.confirm(msg, default=default, style=theme.current_style())
    return _ask(question, include_q=True)


def ask_text(msg, validator=None, default=None):
    question = questionary.text(
        msg, default=default or "", validate=validator, style=theme.current_style()
    )
    return _ask(question)


def ask_password(msg):
    # sem default -- senha nunca deve vir pré-preenchida nem ecoada na tela.
    question = questionary.password(msg, style=theme.current_style())
    return _ask(question)
