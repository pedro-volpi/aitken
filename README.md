# mentat

Treinador de aritmética mental com foco em **fluência por latência**, não só acerto. Inspirado nas técnicas de calculadores profissionais (Aitken, Benjamin, Lemaire): cálculo da esquerda para a direita, criss-cross, close-together, diagnóstico de pares lentos da tabuada e repetição espaçada ponderada por tempo de resposta.

## Motivação

Em aritmética mental, saber a resposta não basta — o gargalo real é **latência**. Um par da tabuada respondido em 4 segundos trava toda a cadeia de uma conta de 3 dígitos. Este projeto cronometra cada resposta, identifica os pares lentos (tipicamente 6×7, 7×8, 8×9, pares com 12), agenda revisões com SM-2 ponderado por tempo e libera níveis superiores (2d×2d, 3d×1d, quadrados, atalhos) apenas quando a latência mediana do nível atual cai abaixo de um limiar configurável.

## Requisitos

Python ≥ 3.14.

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso

```bash
mentat drill tables                              # tabuada (default: 30 problemas, faixa 2-99)
mentat drill tables --min 6 --max 9              # quadrante difícil da tabuada
mentat drill squares                             # quadrados (default: 11² a 99²; 2²-10² já saem da tabuada)
mentat drill cubes                               # cubos (default: 3³ a 10³)
mentat drill factorial                           # fatoriais de 0! a 10! (faixa fixa)
mentat drill tables --layout horizontal          # `17 × 86` em vez da conta armada
```

### Parâmetros comuns a todo drill

Todos os subcomandos `mentat drill <módulo>` aceitam as mesmas flags de sessão:

- `--count N` / `-n N` — número de problemas *distintos* a dominar (default 30; `factorial` usa 20 por ter pool menor).
- `--no-persist` — não grava tentativas nem o estado SM-2 desta sessão.
- `--layout vertical|horizontal` — disposição do problema na tela (default `vertical`).

O default é a **conta armada**, com as casas alinhadas (unidade sob unidade, dezena sob dezena) — a mesma disposição em que o algoritmo de multiplicação é treinado no papel, em que cada produto parcial tem uma coluna própria:

```
                                                    [3/30]
  17
× 86
=
```

`--layout horizontal` volta à leitura compacta, com a conta em uma linha só (`17 × 86 = `). A flag afeta apenas operações binárias: `squares`, `cubes` e `factorial` são termos atômicos (`17²`, `5!`) e são sempre apresentados em uma linha, nos dois modos.

O contador `[N/total]` é cromo periférico, não parte da conta: ocupa uma linha só sua nos dois layouts, encostado na borda direita e em cinza apagado. Quando a saída não é um terminal (pipe, redirecionamento, `NO_COLOR=1` no ambiente) ele sai cru e na margem esquerda. Ele conta problemas *distintos*, então congela durante o retry de uma resposta errada.

Logo abaixo dele vem o cronômetro `MM:SS:CC` da sessão, no mesmo alinhamento e com o mesmo tratamento de cor. Em terminal interativo ele corre de verdade: uma thread de fundo (`ui/refresh.py`) repinta só a linha do relógio a cada centésimo de segundo, sem tocar na linha em que a resposta é digitada. Ele mede tempo *ativo* de prática: **Ctrl+P** pausa e retoma no meio da digitação (em terminal interativo a resposta é lida pelo leitor cbreak de `ui/reader.py`; sem terminal, vale o fallback `p` + Enter), e o intervalo pausado não entra nem no relógio nem na latência gravada. A saudação da sessão estampa **MENTAT** em ASCII art (`figlet` + `lolcat`, quando instalados) e lista os atalhos da interface, derivados da fonte única em `ui/hotkeys.py`. Pausado, a conta sai da tela e a linha do cronômetro perde o cinza e ganha `[PAUSADO]` — esconder o problema é o que impede pausar, resolver sem pressão e retomar com uma latência que mentiria para a mediana e para o SM-2.

O layout é puramente visual — não altera a chave SM-2, o `prompt` gravado no banco nem o resumo de fim de sessão.

### Flags específicas dos módulos

Além dos parâmetros comuns, `tables`, `squares` e `cubes` expõem flags próprias para ajustar a faixa amostrada e os filtros. `factorial` não tem flags adicionais — o pool é fixo de `0!` a `10!`.

| Flag | Módulos | Default | Efeito |
| --- | --- | --- | --- |
| `--min N` | `tables`, `squares`, `cubes` | `tables`: 2 · `squares`: 11 · `cubes`: 3 | Menor valor da faixa amostrada — fator na tabuada; base em quadrados e cubos. |
| `--max N` | `tables`, `squares`, `cubes` | `tables`: 99 · `squares`: 99 · `cubes`: 10 | Maior valor da faixa amostrada. |

Os defaults numéricos acima moram todos em `src/mentat/config.py` (`DEFAULT_TABLES_MAX_FACTOR` etc.) — mudar lá reflete na CLI, no `--help` e nos dataclasses de params de uma vez.
| `--include-trivial` | `tables`, `squares`, `cubes` | exclui triviais | Passar a flag mantém os casos triviais no pool: `×0`/`×1` na tabuada, `0²`/`1²` em quadrados, `0³`/`1³` em cubos. Por default ficam fora porque não exercitam cálculo mental — sabê-los ≠ treiná-los. |
| `--no-commutative` | `tables` | agrupa comutativos | Por default, `7×8` e `8×7` compartilham a chave SM-2 canônica `tables:7x8`, o que significa **mesmo `Card`, mesmo estado de aprendizado** — acertar um conta como reforço do outro. Passar a flag separa em duas chaves distintas (`tables:7x8` e `tables:8x7`) e faz o SM-2 tratá-los como itens independentes. Útil apenas se você considera que a ordem de apresentação altera a dificuldade cognitiva e quer medir cada lado em separado. |

Cada flag também aparece em `mentat drill <módulo> --help` com a mesma descrição resumida.

### Onde fica o banco

O histórico é gravado em `data/mentat.db`, dentro do próprio repositório. Como o projeto vive numa pasta sincronizada pelo OneDrive, o banco viaja entre máquinas sem precisar de export, env var ou config file — clonou a pasta, já tem o histórico.

A flag `--db PATH` existe como escape hatch para apontar a sessão para um arquivo alternativo (usada principalmente pelos testes para isolar `tmp_path`).

Outros módulos planejados (multidígito, atalhos) e `mentat diagnostic` estão listados em [Funcionalidades](#funcionalidades).


## Funcionalidades

Linhas marcadas com ✗ são planejadas — o nome exato do comando pode mudar quando forem implementadas.

> **Políticas padrão de todo drill.**
>
> - *Retry-on-wrong*: respostas erradas reapresentam o mesmo problema até serem acertadas. `--count N` conta problemas distintos a dominar; tentativas erradas não consomem desse orçamento. A resposta certa nunca é exibida no erro — revelá-la esvaziaria o retry.
> - *SM-2 ponderado por latência*: a amostragem prioriza pares com `ease_factor` baixo (difíceis, lentos ou recém-errados) sobre pares já dominados. Ao fim de cada ciclo de retry o `Card` da chave é atualizado; erros em qualquer ponto do ciclo rebaixam o item para "re-aprender" (quality ≤ 2 → streak zera, `ease_factor` cai 0.2). Pares nunca vistos têm prioridade máxima, para que a sessão cubra o universo antes de voltar aos conhecidos.

| Funcionalidade | Descrição | Como chamar | Implementado |
| --- | --- | --- | --- |
| Treino de tabuada | Sessão cronometrada de multiplicações na faixa configurada (padrão 2-99, estensível até qualquer inteiro). Amostragem por SM-2 + retry-on-wrong. Aceita `--min`, `--max`, `--include-trivial`, `--no-commutative` além dos [parâmetros comuns](#par%C3%A2metros-comuns-a-todo-drill). | `mentat drill tables` | ✓ |
| Treino de quadrados | Sessão de `N²` para `N` em `[--min, --max]` (default 11–99; `2²` a `10²` já saem da tabuada, daí o corte). Aceita `--min`, `--max`, `--include-trivial`. | `mentat drill squares` | ✓ |
| Treino de cubos | Sessão de `N³` para `N` em `[--min, --max]` (default 3–10; `2³ = 8` é trivial). Aceita `--min`, `--max`, `--include-trivial`. | `mentat drill cubes` | ✓ |
| Treino de fatoriais | Sessão de `N!` com `N` sorteado no pool fixo `{0, 1, ..., 10}` — sem parâmetros de faixa. | `mentat drill factorial` | ✓ |
| Conta armada | Operações binárias são apresentadas empilhadas, com as casas alinhadas (unidade sob unidade). `--layout horizontal` volta à leitura em uma linha. Módulos unários (`N²`, `N³`, `N!`) são sempre de uma linha. | comum a todo `drill`, via `--layout` | ✓ |
| Histórico persistente | Cada tentativa é gravada na tabela `attempts` e o estado SM-2 (`ease_factor`, streak de acertos) por chave em `schedule`. Banco em SQLite dentro do projeto (`data/mentat.db`). Para análise ad-hoc, o banco é consultável direto com `sqlite3` ou qualquer ferramenta SQL. | automático em qualquer `drill` (desabilitável com `--no-persist`) | ✓ |
| Treino multidígito | Multiplicações 2d×1d, 2d×2d, 3d×1d, 3d×2d, 3d×3d. | `mentat drill multidigit` | ✗ |
| Treino de atalhos | Operações com atalhos mentais: ×11, ×25, ×125, (10a+5)². | `mentat drill tricks` | ✗ |
| Diagnóstico de fraquezas | Bateria de 100 pares aleatórios; produz mapa dos pares mais lentos, estatísticas agregadas de latência (mediana, p90) e gráficos semanais de evolução (matplotlib). | `mentat diagnostic` | ✗ |


## Arquitetura

Quatro camadas com dependências em um único sentido:

```
ui/  →  session/  →  storage/
                 ↘            ↘
                   core/  ←───┘
```

- **`core/`** — lógica pura: geradores de problemas, scheduler SM-2 (`ease_factor`, streak, quality mapping), estatísticas. Sem I/O, sem UI, sem SQLite. `core/progression.py` está reservado para regras futuras de desbloqueio de nível.
- **`storage/`** — adaptador SQLite. Depende apenas dos tipos de `core/`.
- **`session/`** — casos de uso (DrillSession, DiagnosticSession). Orquestra `core/` + `storage/`. Hoje devolve resultados de forma síncrona; `session/events.py` fica reservado para uma API baseada em eventos que UIs assíncronas (Textual, GUI) consumirão sem tocar em `core/`.
- **`ui/`** — `ui/plain.py` é o adaptador de terminal síncrono que hoje executa todas as sessões; ele delega o desenho do problema a um `Presenter` (`ui/presenter.py`), a leitura interativa a `ui/reader.py`, a saudação a `ui/welcome.py` e os bindings a `ui/hotkeys.py`. `ui/textual/` e `ui/plot.py` são ganchos para adaptadores futuros que consomem os mesmos contratos de `session/`.


## Implementação detalhada

Esta seção expande o diagrama de quatro camadas seguindo uma sessão real — `mentat drill tables --count 30` — da linha de comando até o `INSERT` no SQLite, e termina com um grafo `dot` das chamadas. O objetivo é que um leitor novo consiga abrir qualquer arquivo do projeto sabendo em que papel ele entra.

### Camadas e responsabilidades

A camada **`core/`** contém apenas lógica pura: geradores, estatísticas, tipos imutáveis. Nenhum módulo importa `sqlite3`, `argparse`, `print` ou `input`. A consequência prática é que todos os testes de `core/` usam um `random.Random` com seed fixo, sem fixtures, sem `tmp_path`, sem `capsys`. Se amanhã trocarmos SQLite por Postgres, `core/` não tem uma linha alterada.

A camada **`storage/`** fala `sqlite3` e nada mais além dos tipos de `core/`. `AttemptRepo` recebe a conexão pronta no construtor em vez de abrir a própria, o que transforma cada teste em um caminho de três linhas: `open_db(tmp_path / "t.db")`, instanciar o repo, rodar. Pragmas, migrações e timestamps ficam isolados em `storage/db.py` e `storage/migrations.py` — quem usa o repo nunca precisa pensar neles.

A camada **`session/`** orquestra mas não decide apresentação. `DrillSession` é um iterável: `__iter__` produz o próximo `Problem` chamando `generator.next(rng)`, `record(problem, answer, elapsed_ms)` avalia via `generator.check`, monta o `Attempt` e, se houver repo, persiste. A sessão nunca cronometra nem lê input — o driver faz isso e devolve o `elapsed_ms`. Esse é o contrato que qualquer UI (terminal, TUI, GUI futura) satisfaz.

A camada **`ui/`** é o único lugar onde existem `input()`, `print()` e `time.monotonic()` — este último encapsulado em `ui/timer.py`, cujo `PracticeTimer` é a fonte única de verdade sobre o cronômetro estar rodando e sobre quanto tempo ativo já passou. `ui/refresh.py` é a única thread do projeto: a `ClockRefresher` mantém a linha do cronômetro viva sob a leitura bloqueada, armada apenas com uma questão na tela e desarmada antes de qualquer outra escrita. `ui/reader.py` é o único lugar que toca termios: em terminal interativo a resposta é lida tecla a tecla em cbreak, o que dá o Ctrl+P de pausa; fora dele vale o `input()` clássico. O contrato de substituição tem dois níveis: uma UI inteira nova (Textual, web) implementa um `run` análogo consumindo a mesma sessão, e uma forma nova de *apresentar* a questão (voz, flash anzan) é só outro `Presenter` (`ui/presenter.py`) escolhido na composição da CLI, com o loop de `plain.py` intacto. `ui/style.py` é o único módulo do projeto que emite ANSI, e só para apagar cromo — nunca para carregar informação, de modo que a saída sem cor não perde nada.

### Tipos de domínio

Seis dataclasses formam o vocabulário compartilhado entre as camadas:

- **`Problem`** (`src/mentat/core/problem.py`) — `module_id`, `key` canônica (ex.: `tables:7x8` agrupa estatisticamente 7×8 e 8×7 quando `commutative_pairs=True`), `expression` estrutural, `expected_answer` em string. `prompt` não é campo: é `@property` derivada de `expression.inline()`, para que a forma canônica de uma linha (a que vai para o banco e para o resumo) nunca possa divergir da estrutura.
- **`Expression`** (`src/mentat/core/expression.py`) — união fechada `Term | BinaryOp`. `Term("17²")` é atômico; `BinaryOp("17", "×", "86")` preserva os operandos e o símbolo em separado. O gerador declara *o que* é a expressão; `ui/layout.py` decide *como* desenhá-la. Sem isso a UI receberia uma string já formatada e não teria como armar a conta.
- **`Attempt`** (`src/mentat/core/problem.py`) — `problem`, `user_answer`, `correct`, `elapsed_ms`. É o que entra na tabela `attempts`.
- **`TablesParams`** (`src/mentat/core/generators/tables.py`) — `frozen=True` com `__post_init__` validando faixas. Frozen porque parâmetros circulam entre threads e módulos; mutação silenciosa nunca é o que o usuário quer.
- **`SessionSummary`** (`src/mentat/core/stats.py`) — `total`, `correct`, `accuracy`, `median_ms`, `p90_ms` (ou `None` se `total < 10`), `slowest`.
- **`Card`** (`src/mentat/core/scheduler.py`) — estado SM-2 por chave: `ease_factor` (partida em 2.5, piso em 1.3) e `consecutive_correct`. Persistido na tabela `schedule`.

### Cadeia de execução de um comando

Considere:

```bash
mentat drill tables --count 30
```

**Parsing (`ui/` entrando em `cli.py`)**

1. O console script `mentat` (registrado em `[project.scripts]` do `pyproject.toml`) chama `mentat.cli:main(argv)`.
2. `main` monta o parser via `build_parser()`: subparser `drill` → sub-subparser `tables` configurado em `_add_tables_subparser`.
3. `parser.parse_args(argv)` retorna um `Namespace` onde `args.func` já aponta para `cmd_drill_tables` (via `p.set_defaults(func=...)`). Esse truque dispensa `if/elif` na `main` — adicionar um novo módulo é só registrar mais um subparser.
4. `main` chama `args.func(args)`. `ValueError` levantado em qualquer camada é capturado aqui e convertido em mensagem no `stderr` com `rc=1`; demais exceções propagam com stack trace.

**Bootstrap (`storage/` e `core/`)**

5. `cmd_drill_tables` instancia `TablesParams(min_factor=2, max_factor=9, commutative_pairs=True, exclude_trivial=True)`. O `__post_init__` rejeita `min_factor < 0`, `min_factor > max_factor` e faixas que ficam vazias após `exclude_trivial`. Com os params válidos, constrói `TablesGenerator(params)` e um `Random()` sem seed — a CLI não expõe `--seed` porque, com o scheduler SM-2 persistido, é o histórico acumulado que dita o que reaparece, não a semente. Quem precisar de reprodutibilidade (ex.: testes) constrói `DrillSession(rng=Random(42))` diretamente.
6. Como `--no-persist` não foi passado, chama `open_db(args.db)`. A função cria o diretório pai se necessário, abre a conexão em autocommit e aplica três pragmas: `journal_mode=WAL` (leituras concorrentes não bloqueiam escritas), `foreign_keys=ON` (SQLite desabilita por padrão), `synchronous=NORMAL` (perdemos só a última transação em crash do SO, não do processo). Em seguida chama `migrate(conn)`, que lê a tabela `schema_version`, aplica só as migrações pendentes e é idempotente — rodar duas vezes é no-op.
7. `AttemptRepo(conn)` e `ScheduleRepo(conn)` embrulham a conexão (stateless além dela). `DrillSession(generator, attempt_repo, schedule_repo, max_problems=30, rng)` valida `max_problems > 0`, guarda as cinco referências injetadas e chama `schedule_repo.load("tables")` para hidratar o dicionário interno de `Card` com o que já existia no banco — assim uma sessão nova retoma exatamente onde a anterior parou.

**Loop de iteração (`ui/` ↔ `session/` ↔ `core/`)**

8. `cmd_drill_tables` delega para `plain.run(session)`.
9. `plain.run` itera `for problem in session:`, lendo a posição atual via `session.current_position`. Isso dispara `DrillSession.__iter__`, que — se `self._pending_retry` estiver setado — reemite o mesmo problema sem decrementar `self._remaining` (retry-on-wrong); caso contrário decrementa, incrementa `_position` e faz `yield self._generator.next(self._rng, weights=weights_from_cards(self._cards), exclude={self._last_key})`. Os pesos vêm do scheduler SM-2: cada chave conhecida produz um peso a partir do seu `Card` (baixo `ease_factor` → peso alto), e chaves inéditas recebem o peso padrão de `sampling_weight(None)` — o maior. O `exclude` carrega a chave do problema anterior (gravada em `_last_key` a cada `yield`) para garantir que dois sorteios frescos seguidos não coincidam — o retry é isento porque não passa pelo gerador. O loop segue enquanto restar problema distinto a dominar **ou** um retry pendente.
10. `TablesGenerator.next(rng, weights=..., exclude=...)` chama `weighted_choice(rng, all_keys, weights, exclude=exclude)` (em `scheduler.py`) para escolher a chave a renderizar — o helper filtra as chaves excluídas **antes** do `rng.choices` (omitir do `weights` não suprime: chave ausente recebe o peso máximo de `sampling_weight(None)`), com fallback best-effort para o universo cheio se a exclusão esvaziaria o pool. Devolve um `Problem` com `prompt = "a × b"` (em pares comutativos, aleatoriza a ordem só na apresentação — a `key` canônica continua `min(a,b), max(a,b)`) e `expected_answer = str(a*b)`. Sem `weights`, recai no caminho uniforme via `_draw` (amostragem por rejeição para descartar pares com fator `< 2` quando `exclude_trivial=True`).

**Loop de captura (`ui/` ↔ `session/`)**

11. De volta ao `plain.run`: `started = timer.elapsed` e a leitura vai para `_ask_active(...)`, que repinta o prompt e chama `ask` (o `input_fn` injetado ou `builtins.input`) até vir uma resposta com o cronômetro rodando — uma linha `p`/`pause` alterna a pausa em vez de valer como resposta, e pausado nenhuma outra entrada é aceita. Fechado o ciclo, `elapsed_ms = int((timer.elapsed - started) * 1000)`. Como os dois extremos saem do **mesmo** `PracticeTimer` (sobre `time.monotonic`, imune a ajustes de relógio), o intervalo pausado desaparece da latência sem que o caminho de gravação precise saber que a pausa existe; e como `elapsed` nunca decresce, o delta nunca é negativo. Um `EOFError`/`KeyboardInterrupt` — inclusive durante a pausa — quebra o loop graciosamente, e o resumo ainda é gerado com os `attempts` que chegaram até ali.
12. `session.record(problem, answer, elapsed_ms)` valida `elapsed_ms >= 0`, chama `generator.check(problem, user_answer)` (`TablesGenerator.check` faz `strip()`, tenta `int()`, compara — nunca levanta), constrói o `Attempt` e apenda. Se `self._attempt_repo is not None`, chama `attempt_repo.record(attempt)` — o `INSERT` inclui `created_at = datetime.now(UTC).isoformat(timespec="milliseconds")`. Em seguida, o fluxo ramifica: **se a resposta estiver errada**, `self._pending_retry = problem` e `self._cycle_had_error = True` — o ciclo segue aberto; **se correta**, fecha o ciclo: computa `quality = quality_from_attempt(correct=True, elapsed_ms=elapsed_ms)` (5 se rápido, 2 se muito lento), reduz a `min(quality, 2)` se houve erro em algum ponto do ciclo, chama `update_card` no `Card` da chave e, se `self._schedule_repo is not None`, persiste via `schedule_repo.upsert(...)`.
13. `plain.run` formata o retorno via `_format_feedback(attempt)` (`ok (Xs)` no acerto, `x errado (sua: 'Z', Xs)` no erro — a resposta certa **não** é revelada, porque o problema volta logo em seguida) e escreve no `output`.

**Encerramento**

14. Esgotados os 30 problemas distintos **com retry exaurido em cada um** (ou após abortar), `plain.run` chama `session.summary()`, que simplesmente delega a `stats.summarize(self._attempts)`. A função é pura: recebe a lista (que pode conter múltiplas entradas por problema devido aos retries), computa `total`, `correct`, `accuracy`, `median_ms`, `p90_ms` (via `statistics.quantiles(..., n=10)[8]`, só se houver ≥ 10 amostras) e o par mais lento. `plain.run` escreve o bloco via `_format_summary` e retorna o `SessionSummary`.
15. De volta a `cmd_drill_tables`, o bloco `finally` fecha a conexão — mesmo se qualquer passo anterior tiver levantado. `main` retorna `int(args.func(args))` e o processo encerra com `rc=0`.

### Grafo de chamadas

Arestas sólidas são chamadas diretas; arestas tracejadas mostram o dado retornado/passado entre camadas. Clusters reproduzem as quatro camadas da arquitetura. GitHub não renderiza DOT — para ver o grafo, cole o bloco em `dot -Tsvg` ou em <https://dreampuf.github.io/GraphvizOnline>.

```dot
digraph mentat_call_chain {
  rankdir=LR;
  node [shape=box, fontname="Helvetica", fontsize=10];
  edge [fontname="Helvetica", fontsize=9];

  entry [label="console_script\n(mentat)", shape=oval];

  subgraph cluster_ui {
    label="ui/"; style=filled; fillcolor="#f0f4ff";
    cli_main        [label="cli.main"];
    cli_build       [label="cli.build_parser"];
    cli_cmd_tables  [label="cli.cmd_drill_tables"];
    plain_run       [label="plain.run"];
    plain_fmt       [label="plain._format_prompt\nplain._format_feedback\nplain._format_summary", style=dashed];
    layout_render   [label="layout.render"];
  }

  subgraph cluster_session {
    label="session/"; style=filled; fillcolor="#f3fff0";
    drill_init   [label="DrillSession.__init__"];
    drill_iter   [label="DrillSession.__iter__"];
    drill_record [label="DrillSession.record"];
    drill_sum    [label="DrillSession.summary"];
  }

  subgraph cluster_core {
    label="core/"; style=filled; fillcolor="#fff7e8";
    gen_next       [label="TablesGenerator.next"];
    gen_draw       [label="TablesGenerator._draw"];
    gen_check      [label="TablesGenerator.check"];
    stats_sum      [label="stats.summarize"];
    params         [label="TablesParams.__post_init__", shape=note];
    sched_weights  [label="scheduler.weights_from_cards"];
    sched_quality  [label="scheduler.quality_from_attempt"];
    sched_update   [label="scheduler.update_card"];
  }

  subgraph cluster_storage {
    label="storage/"; style=filled; fillcolor="#fdf0ff";
    open_db       [label="db.open_db"];
    migrate       [label="migrations.migrate"];
    attempt_rec   [label="AttemptRepo.record"];
    sched_load    [label="ScheduleRepo.load"];
    sched_upsert  [label="ScheduleRepo.upsert"];
  }

  entry          -> cli_main;
  cli_main       -> cli_build;
  cli_main       -> cli_cmd_tables  [label="args.func(args)"];
  cli_cmd_tables -> params;
  cli_cmd_tables -> open_db;
  open_db        -> migrate;
  cli_cmd_tables -> drill_init;
  drill_init     -> sched_load;
  cli_cmd_tables -> plain_run;

  plain_run      -> drill_iter;
  drill_iter     -> sched_weights;
  drill_iter     -> gen_next        [label="weights=..."];
  gen_next       -> gen_draw        [label="caminho uniforme"];

  plain_run      -> drill_record;
  drill_record   -> gen_check;
  drill_record   -> attempt_rec     [label="se attempt_repo"];
  drill_record   -> sched_quality   [label="no acerto final"];
  drill_record   -> sched_update;
  drill_record   -> sched_upsert    [label="se schedule_repo"];

  plain_run      -> drill_sum;
  drill_sum      -> stats_sum;
  plain_run      -> plain_fmt       [style=dotted];
  plain_fmt      -> layout_render   [label="layout=..."];

  gen_next       -> drill_iter      [label="Problem",        style=dashed, constraint=false];
  drill_record   -> attempt_rec     [label="Attempt",        style=dashed, constraint=false];
  stats_sum      -> drill_sum       [label="SessionSummary", style=dashed, constraint=false];
}
```

`DiagnosticSession` (roadmap) seguirá o mesmo formato com uma sessão diferente no lugar de `DrillSession`; `ui/textual/` consumirá os mesmos contratos via eventos definidos em `session/events.py`.

### UI desacoplada

A assinatura é `plain.run(session, *, output: TextIO | None = None, input_fn: Callable[[str], str] | None = None, presenter: Presenter | None = None, clock: Clock | None = None)`. Testes em `tests/ui/test_plain.py` instanciam um `_FakeInput` com uma lista de respostas pré-programadas e passam um `io.StringIO` como `output` — o loop roda até o fim sem tocar em `stdin`/`stdout`. O `clock` existe pelo mesmo motivo que o `rng` de `DrillSession`: com um dublê de relógio, pausa e retomada são testáveis sem `sleep`, e as asserções de prompt exato não ficam à mercê do cronômetro. Uma futura UI Textual ou GUI implementa um `run` análogo consumindo `DrillSession` via iteração + `record()`; `core/`, `session/` e `storage/` ficam intactos.

O bloco do problema (contador, cronômetro, operandos, `= `) é montado por `_format_prompt` e entregue **inteiro** como argumento único de `ask()`: `input()` aceita prompt multilinha, imprime tudo e lê na última linha. Isso mantém a cronometragem em uma leitura de `timer.elapsed` por extremo e preserva o contrato de que `input_fn` recebe exatamente o que o usuário viu — o que também é o que torna os fakes dos testes capazes de derivar a resposta do prompt nos dois layouts.

O arranjo em si mora em `src/mentat/ui/layout.py` (`Layout`, `render`), separado de `plain.py`: `render` é uma função pura `Expression -> list[str]` que não imprime nem lê, e qualquer UI futura reaproveita o mesmo desenho. Entre o driver e o `render` fica a costura de apresentação: `plain.run` pede as linhas a um `Presenter` (`ui/presenter.py`) — o default `VisualPresenter(layout)` embrulha o `render`; um presenter de voz ou de flash anzan devolve lista vazia e apresenta por efeito colateral.

### Persistência opcional

`--no-persist` passa `repo=None` para `DrillSession`. Dentro de `record`, o teste é literal: `if self._repo is not None: self._repo.record(attempt)`. Não há `NullRepo`, nem `MemoryRepo` — um `None` bem checado evita uma hierarquia inteira. E como `migrate(conn)` é idempotente, rodar `mentat` em uma máquina nova cria o banco e o schema sem passos manuais; rodar de novo não faz nada.

### Adicionando um novo gerador

- Implementar o `Protocol` `Generator` em `src/mentat/core/generators/base.py`: atributo `module_id: str`, método `next(rng: Random, *, weights: Mapping[str, float] | None = None, exclude: AbstractSet[str] = frozenset()) -> Problem`, método `all_keys() -> Sequence[str]`, método `check(problem: Problem, user_answer: str) -> bool`. Quando `weights` é passado, o gerador amostra ponderadamente por chave (integração com SM-2); sem pesos, amostragem uniforme. `exclude` carrega as chaves a evitar (política de não-repetição consecutiva) e deve ser honrado via `weighted_choice` — best-effort: ignorado se esvaziaria o pool.
- Ao montar cada `Problem`, declarar a `expression`: `BinaryOp(left, operador, right)` para operações de dois operandos (ganha a conta armada de graça) ou `Term(texto)` para termos atômicos. O gerador não escolhe layout nem sabe que layouts existem — só descreve a estrutura.
- Opcional: um dataclass `frozen=True` de parâmetros com `__post_init__` validador, seguindo `TablesParams`.
- Em `cli.py`, espelhar `_add_tables_subparser` e escrever um `cmd_*` análogo a `cmd_drill_tables`. Os arquivos de outras camadas não mudam — a `DrillSession` já carrega o estado SM-2 correto para o novo módulo via `schedule_repo.load(generator.module_id)`.
- `core/progression.py` hoje é stub — reservado para regras de desbloqueio automático de nível (liberar 2d×2d quando a tabuada ficar rápida).

## Desenvolvimento

```bash
pytest                    # testes
ruff check src tests      # lint
ruff format src tests     # formatação
mypy src/mentat           # tipos
```
