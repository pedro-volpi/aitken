# CLAUDE.md — projeto `aitken`

Instruções de escopo local ao projeto. A `CLAUDE.md` do vault (um nível
acima) trata apenas das notas Obsidian — não se aplica ao código aqui.

## Política padrão de drills: retry-on-wrong

Toda sessão de drill (hoje `drill tables`; planejados `squares`,
`multidigit`, `tricks`) **reapresenta o mesmo problema até que a resposta
seja correta**. `--count N` conta *problemas distintos a dominar*, nunca
tentativas — erros não consomem o orçamento. Mudanças nesse contrato
precisam ser discutidas com o usuário antes de serem implementadas.

Implementação em `DrillSession`: campo `_pending_retry: Problem | None` é
atribuído em `record()` (None se correto, o próprio `problem` se errado) e
consultado em `__iter__`. A posição 1-indexada exposta via
`current_position` **não** avança em retry.

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
  - `pytest` (atualmente 63 testes, todos devem passar)
  - `ruff check src tests`
  - `ruff format --check src tests`
  - `mypy` strict em `src/aitken` + `tests/` (config em `pyproject.toml`).
- Use a venv do projeto: `.venv/bin/{pytest,ruff,mypy,aitken}`.

## Arquitetura (invariante)

Quatro camadas em um sentido: `ui/` → `session/` → `storage/` → `core/`.
Nenhuma importação em sentido contrário. Novo gerador entra como
implementação do `Protocol` em `core/generators/base.py` + novo subparser
em `cli.py`; não toca `session/` nem `storage/`. Detalhes completos em
`README.md`, seção "Implementação detalhada".

## Proibições

- Não adicionar flag para desligar retry-on-wrong sem solicitação explícita.
- Não revelar `expected_answer` em qualquer UI quando `attempt.correct` for
  `False`.
- Não importar `sqlite3`, `argparse`, `print`, `input` ou `time` dentro de
  `core/` ou `session/` — apenas `ui/` e `storage/` têm licença para isso.
