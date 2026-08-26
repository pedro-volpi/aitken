# CLAUDE.md — projeto `mentat`

Instruções de escopo local ao projeto. A `CLAUDE.md` do vault (um nível
acima) trata apenas das notas Obsidian — não se aplica ao código aqui.

## Política padrão de drills: retry-on-wrong

Toda sessão de drill (hoje: `tables`, `squares`, `cubes`, `factorial`;
planejados: `multidigit`, `tricks`) **reapresenta o mesmo problema até
que a resposta seja correta**. `--count N` conta *problemas distintos a
dominar*, nunca tentativas — erros não consomem o orçamento. Mudanças
nesse contrato precisam ser discutidas com o usuário antes de serem
implementadas.

Implementação em `DrillSession`: campo `_pending_retry: Problem | None` é
atribuído em `record()` (None se correto, o próprio `problem` se errado) e
consultado em `__iter__`. A posição 1-indexada exposta via
`current_position` **não** avança em retry.

## Política padrão de drills: sem repetição consecutiva

Dois sorteios *frescos* seguidos nunca produzem a mesma chave — depois de
um problema ser dominado, o próximo problema distinto é necessariamente
outro. O **retry-on-wrong é estruturalmente isento**: reapresentar a
questão errada não passa pelo gerador (`_pending_retry`), então continua
mostrando a mesma chave até o acerto.

A restrição é **best-effort**: se o universo tem uma única chave (ex.:
`squares` com `min_base == max_base`), a repetição é permitida — nunca
falha por pool vazio.

Implementação (separação política/mecanismo, espelhando o retry):

- *Política* em `DrillSession`: campo `_last_key: str | None`, gravado em
  `__iter__` a cada `yield` e passado como `exclude={_last_key}` no
  próximo sorteio fresco.
- *Mecanismo* em `core`: `Generator.next` recebe
  `exclude: AbstractSet[str] = frozenset()` e amostra via
  `weighted_choice(rng, keys, weights, *, exclude)` em
  `src/mentat/core/scheduler.py`, que filtra as chaves excluídas **antes**
  do `rng.choices`. Filtrar a chave (não zerar o peso) é obrigatório:
  chave ausente em `weights` recebe peso *máximo*
  (`sampling_weight(None)`), então omiti-la a priorizaria, não a
  suprimiria. Com `exclude` vazio o consumo do `rng` é idêntico ao sorteio
  direto — preserva reprodutibilidade com seed.

Não adicionar flag para desligar a regra sem solicitação explícita.

## Política padrão de drills: SM-2 ponderado por latência

Todo drill amostra pelo scheduler SM-2 de `src/mentat/core/scheduler.py`.
O ciclo:

1. `DrillSession.__init__` carrega `dict[str, Card]` via
   `ScheduleRepo.load_for(generator.all_keys())` se o repo existe; caso
   contrário começa vazio (scheduling só em memória). A carga é pelo
   **universo do gerador**, não por módulo — a sessão nunca pergunta de
   que módulo o gerador é.
2. `__iter__` chama `generator.next(rng, weights=weights_from_cards(...))`;
   geradores usam `rng.choices` ponderado por chave. Chaves inéditas
   recebem o maior peso (`sampling_weight(None) = 4.0`).
3. `record()` atualiza o `Card` **apenas no acerto final** do ciclo de
   retry; se houve qualquer erro no ciclo, a quality é truncada em 2
   (caminho de recall failure → zera streak, EF cai 0.2). Persiste via
   `ScheduleRepo.upsert` se o repo existe.

Contrato do `Generator` (`src/mentat/core/generators/base.py`):

- `next(rng, *, weights=None, exclude=frozenset()) -> Problem`
- `all_keys() -> Sequence[str]`
- `check(problem, user_answer) -> bool`

Qualquer novo módulo precisa satisfazer os três; sem isso, o scheduler
não consegue enumerar o universo nem amostrar ponderado. O contrato **não
tem `module_id`** e é **fechado sob composição**: um drill misto futuro é
um gerador *composto* que embrulha outros geradores e satisfaz o mesmo
`Protocol` (`all_keys` = união dos filhos, `next` delega, `check`
despacha por `problem.module_id`) — entra pela mesma receita de qualquer
módulo (gerador + subparser + `cmd_*`), sem tocar `session/`/`storage/`.
Duas invariantes sustentam isso: toda `key` começa com `"<module_id>:"`
(verificada em `Problem.__post_init__` — é o que impede `squares:13` e
`cubes:13` de colidirem em pesos, exclusão e Cards) e cada
tentativa/Card é persistido sob o `module_id` do próprio `Problem`, então
treino misto e drills individuais alimentam o mesmo histórico. Não
adicionar flag para desligar SM-2 sem solicitação explícita.

## Estrutura é `core/`, arranjo é `ui/`

`Problem` carrega uma `expression: Expression` (união fechada
`Term | BinaryOp` em `src/mentat/core/expression.py`), não uma string já
formatada. O gerador declara *o que* é o problema; `src/mentat/ui/layout.py`
(`Layout`, `render`) decide *como* desenhá-lo. `render` é puro
(`Expression -> list[str]`) — não imprime, não lê, não conhece `DrillSession`.

`Problem.prompt` é `@property`, nunca campo: devolve `expression.inline()`,
a forma canônica de uma linha. É ela que vai para a coluna `attempts.prompt`
e para o resumo de fim de sessão. **O layout escolhido na UI não altera
`prompt`** — mudar isso quebraria a continuidade do histórico no banco.

Default é `Layout.VERTICAL` (conta armada, casas alinhadas); `--layout
horizontal` é o escape. Módulos unários (`N²`, `N³`, `N!`) são `Term` e
degradam para uma linha nos dois modos — não têm forma armada.

Novo gerador declara `BinaryOp(left, operador, right)` ou `Term(texto)` e
ganha os dois layouts de graça. Não formatar prompt em gerador nenhum.

## Apresentação é plugável (`Presenter`)

O driver de terminal não desenha o problema: pede a um `Presenter` (`src/mentat/ui/presenter.py`) via `present(problem)` — uma vez por apresentação, retry incluído; toggle de pausa reusa as linhas sem re-apresentar — e compõe no prompt o que vier. O retorno é o **resíduo visual** da apresentação (pode ser vazio), o que admite presenters por efeito colateral: um futuro `--voice` fala os números e devolve `[]`, um flash anzan anima a tela e idem. `VisualPresenter` embrulha `layout.render`; quem escolhe o presenter concreto é o ponto de composição (`_run_drill` em `cli.py`). Feature nova de apresentação = novo presenter + escolha na CLI, sem tocar no loop de `plain.py` nem em `session/`/`core/`.

## O contador `[N/total]` é cromo periférico

O contador nunca compete com a conta. `_format_hud` em `src/mentat/ui/plain.py` o coloca em uma linha só dele nos dois layouts, alinhado à direita da largura do terminal (menos uma coluna de folga, para não armar o wrap adiado dos terminais com auto-margin) e apagado com SGR *faint*.

Ficar fora da linha do cursor não é só estética: o bloco inteiro vai como argumento único de `ask()`, e tanto o fallback `input()`/readline quanto o eco manual do leitor cbreak assumem que a última linha do prompt não tem escape ANSI — escape ali descontaria colunas e bagunçaria o backspace. Qualquer estilo novo no prompt fica nas linhas anteriores.

Logo abaixo do contador vem o cronômetro `MM:SS:CC`, no mesmo `rjust` e sob as mesmas regras. A fonte única de verdade é o `PracticeTimer` de `src/mentat/ui/timer.py` — `running` é derivada de `_started_at`, não há flag paralela, e `elapsed` é o **único** cálculo de tempo decorrido do projeto. `plain.run` deriva o `elapsed_ms` de cada tentativa de um par de leituras desse mesmo cronômetro, então pausa não contamina latência, mediana/p90 nem a *quality* do SM-2, e nenhuma condicional de pausa entra no caminho de gravação. Formatação é função livre (`format_elapsed`), separada da contagem, e converte em inteiro a partir de um único `round` — truncar deixaria vazar artefato binário (`int(0.29 * 100) == 28`).

O binding de pausa é **Ctrl+P**, capturado pelo leitor cbreak de `src/mentat/ui/reader.py` (pedido explícito do usuário, 2026-08-26 — antes disso valia a proibição de sair do cooked mode). Em terminal interativo a resposta não passa mais pelo `input()`/readline: `read_line` lê tecla a tecla com `tty.setcbreak` (ECHO/ICANON desligados, **ISIG ligado** — Ctrl+C segue virando `KeyboardInterrupt` sozinho), ecoa manualmente, trata backspace, engole escape sequences e levanta `PauseRequested` no `\x10`; o estado termios é restaurado em `finally`. O motivo de abandonar o readline: o Python do projeto usa libedit, cujas macros `bind -s` inserem texto mas não disparam accept-line — não há chord de pausa possível por ali. Fora de terminal (testes, pipe), o `ask` continua `input_fn`/`input()` e a pausa cai no fallback de linha-sentinela `p`/`pause` + Enter. Os dois caminhos saem do mesmo registro: `src/mentat/ui/hotkeys.py` é a **fonte única** dos atalhos (`Hotkey` com `keys` exibido, `char` capturado, `aliases` de fallback); leitor e saudação só consomem — nunca duplicar um binding em literal. O cronômetro, porém, **corre continuamente** (pedido explícito do usuário, 2026-08-25): a `ClockRefresher` de `src/mentat/ui/refresh.py` é uma thread de fundo que a cada centésimo sobrescreve só a linha do relógio via DECSC/sobe-N/DECRC em uma única `write()`, sem tocar na linha de edição da resposta. Ela só é criada em terminal interativo (`styled`) e só pinta armada — `_ask_active` arma imediatamente antes do `ask` (apenas com o cronômetro correndo) e desarma em `finally`, então nada concorre com feedback, resumo ou o contrato `input_fn` dos testes. A saudação é o módulo autocontido `src/mentat/ui/welcome.py`: estampa **MENTAT** em ASCII art (`figlet` + `lolcat -f`, mesma cadeia de degradação do `mac-awake` dos dotfiles; puro cromo, falha em silêncio) e embaixo a lista de atalhos formatada a partir de `HOTKEYS` — a lista em texto puro sai sempre e é a fonte canônica (e testada) da interface. Pausado, a conta **sai da tela** e a linha do cronômetro perde o *faint* e ganha `[PAUSADO]`; deixar o problema visível permitiria pausar, resolver sem pressão e retomar com uma latência falsa — é a mesma família de proteção do feedback que nunca revela a resposta.

`src/mentat/ui/style.py` é o único módulo que emite ANSI, e só para *tirar* ênfase — nenhuma informação é codificada em cor, então a saída sem cor não perde nada. `supports_ansi(stream)` decide: só terminal interativo e sem `NO_COLOR` no ambiente. Sem flag de CLI para isso — `NO_COLOR` é a convenção de fato e o projeto evita knobs. Padear antes de colorir é obrigatório: escapes não ocupam coluna na tela mas contam em `len()`, então `rjust` sobre texto já colorido erra o alinhamento.

## Feedback nunca revela a resposta correta

`_format_feedback` em `src/mentat/ui/plain.py` emite `x errado (sua: ...)`
sem exibir `expected_answer`. Revelar a resposta certa no erro derrota o
retry — o usuário copiaria e passaria. Qualquer nova UI que implemente o
contrato de `DrillSession` deve respeitar a mesma restrição.

## Ambiente e ferramentas

- Python ≥ 3.14 (sem `from __future__ import annotations` — desnecessário
  em 3.14). Sintaxe PEP 758 (`except A, B:`) é válida e ruff format a
  aplica.
- Toda mudança de código deve passar antes de commit:
  - `pytest` (atualmente 229 testes, todos devem passar)
  - `ruff check src tests`
  - `ruff format --check src tests`
  - `mypy` strict em `src/mentat` + `tests/` (config em `pyproject.toml`).
- Use a venv do projeto: `.venv/bin/{pytest,ruff,mypy,mentat}`.

## Arquitetura (invariante)

Quatro camadas em um sentido: `ui/` → `session/` → `storage/` → `core/`.
Nenhuma importação em sentido contrário. `config.py` é módulo-folha fora
das camadas (só stdlib): **todo default visível ao usuário mora lá**
(`DEFAULT_TABLES_MAX_FACTOR`, `DEFAULT_DRILL_COUNT`, ...), e qualquer
camada pode importá-lo — argparse, help e dataclasses de params
referenciam a mesma constante, nunca literais duplicados. Novo gerador entra como
implementação do `Protocol` em `core/generators/base.py` + novo
subparser em `cli.py` (via `_add_<module>_subparser`) + um
`cmd_drill_<module>` que constrói o gerador e chama `_run_drill(args,
gen)`. Flags comuns (`--count`, `--no-persist`, `--db`) vêm de
`_add_common_drill_args`. Não toca `session/` nem `storage/`. Detalhes
completos em `README.md`, seção "Implementação detalhada".

## Localização do banco

`DEFAULT_DB_PATH = <repo>/data/mentat.db` em `config.py`, calculado via
`Path(__file__).resolve().parents[2]`. Decisão: projeto single-user, repo
vive em pasta sincronizada pelo OneDrive — DB dentro do repo é o caminho
portátil sem env var, config file ou XDG. `data/.gitignore` preserva a
pasta no git e ignora os arquivos `.db*`. `--db` permanece na CLI como
escape hatch, usado sobretudo pelos testes (que apontam para `tmp_path`
do pytest para não poluir o banco real).

## Proibições

- Não adicionar flag para desligar retry-on-wrong ou SM-2 sem solicitação
  explícita — ambos são política do projeto, não knobs do usuário.
- Não revelar `expected_answer` em qualquer UI quando `attempt.correct` for
  `False`.
- Não importar `sqlite3`, `argparse`, `print`, `input` ou `time` dentro de
  `core/` ou `session/` — apenas `ui/` e `storage/` têm licença para isso.
- Não atualizar `Card` no meio de um ciclo de retry. O contrato SM-2 só
  fecha quando o problema é finalmente acertado; erros intermediários são
  absorvidos como penalidade na quality do acerto final.
