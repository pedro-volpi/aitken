# CLAUDE.md — projeto `aitken`

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
  `src/aitken/core/scheduler.py`, que filtra as chaves excluídas **antes**
  do `rng.choices`. Filtrar a chave (não zerar o peso) é obrigatório:
  chave ausente em `weights` recebe peso *máximo*
  (`sampling_weight(None)`), então omiti-la a priorizaria, não a
  suprimiria. Com `exclude` vazio o consumo do `rng` é idêntico ao sorteio
  direto — preserva reprodutibilidade com seed.

Não adicionar flag para desligar a regra sem solicitação explícita.

## Política padrão de drills: SM-2 ponderado por latência

Todo drill amostra pelo scheduler SM-2 de `src/aitken/core/scheduler.py`.
O ciclo:

1. `DrillSession.__init__` carrega `dict[str, Card]` via
   `ScheduleRepo.load(module_id)` se o repo existe; caso contrário começa
   vazio (scheduling só em memória).
2. `__iter__` chama `generator.next(rng, weights=weights_from_cards(...))`;
   geradores usam `rng.choices` ponderado por chave. Chaves inéditas
   recebem o maior peso (`sampling_weight(None) = 4.0`).
3. `record()` atualiza o `Card` **apenas no acerto final** do ciclo de
   retry; se houve qualquer erro no ciclo, a quality é truncada em 2
   (caminho de recall failure → zera streak, EF cai 0.2). Persiste via
   `ScheduleRepo.upsert` se o repo existe.

Contrato do `Generator` (`src/aitken/core/generators/base.py`):

- `next(rng, *, weights=None, exclude=frozenset()) -> Problem`
- `all_keys() -> Sequence[str]`
- `check(problem, user_answer) -> bool`

Qualquer novo módulo precisa satisfazer os três; sem isso, o scheduler
não consegue enumerar o universo nem amostrar ponderado. Não adicionar
flag para desligar SM-2 sem solicitação explícita.

## Feedback nunca revela a resposta correta

`_format_feedback` em `src/aitken/ui/plain.py` emite `x errado (sua: ...)`
sem exibir `expected_answer`. Revelar a resposta certa no erro derrota o
retry — o usuário copiaria e passaria. Qualquer nova UI que implemente o
contrato de `DrillSession` deve respeitar a mesma restrição.

## Ambiente e ferramentas

- Python ≥ 3.14 (sem `from __future__ import annotations` — desnecessário
  em 3.14). Sintaxe PEP 758 (`except A, B:`) é válida e ruff format a
  aplica.
- Toda mudança de código deve passar antes de commit:
  - `pytest` (atualmente 122 testes, todos devem passar)
  - `ruff check src tests`
  - `ruff format --check src tests`
  - `mypy` strict em `src/aitken` + `tests/` (config em `pyproject.toml`).
- Use a venv do projeto: `.venv/bin/{pytest,ruff,mypy,aitken}`.

## Arquitetura (invariante)

Quatro camadas em um sentido: `ui/` → `session/` → `storage/` → `core/`.
Nenhuma importação em sentido contrário. Novo gerador entra como
implementação do `Protocol` em `core/generators/base.py` + novo
subparser em `cli.py` (via `_add_<module>_subparser`) + um
`cmd_drill_<module>` que constrói o gerador e chama `_run_drill(args,
gen)`. Flags comuns (`--count`, `--no-persist`, `--db`) vêm de
`_add_common_drill_args`. Não toca `session/` nem `storage/`. Detalhes
completos em `README.md`, seção "Implementação detalhada".

## Localização do banco

`DEFAULT_DB_PATH = <repo>/data/aitken.db` em `config.py`, calculado via
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
