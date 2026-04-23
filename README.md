# aitken

Treinador de aritmética mental com foco em **fluência por latência**, não só acerto. Inspirado nas técnicas de calculadores profissionais (Aitken, Benjamin, Lemaire): cálculo da esquerda para a direita, criss-cross, close-together, diagnóstico de pares lentos da tabuada e repetição espaçada ponderada por tempo de resposta.

## Motivação

Em aritmética mental, saber a resposta não basta — o gargalo real é **latência**. Um par da tabuada respondido em 4 segundos trava toda a cadeia de uma conta de 3 dígitos. Este projeto cronometra cada resposta, identifica os pares lentos (tipicamente 6×7, 7×8, 8×9, pares com 12), agenda revisões com SM-2 ponderado por tempo e libera níveis superiores (2d×2d, 3d×1d, quadrados, atalhos) apenas quando a latência mediana do nível atual cai abaixo de um limiar configurável.

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso

```bash
aitken drill              # sessão de treino no nível ativo
aitken diagnostic         # 100 pares aleatórios, mapa de fraquezas
aitken stats              # latência mediana, p90 por nível
aitken plot               # gráficos de evolução semanal (matplotlib)
```

## Arquitetura

Quatro camadas com dependências em um único sentido:

```
ui/  →  session/  →  storage/
                 ↘            ↘
                   core/  ←───┘
```

- **`core/`** — lógica pura: geradores de problemas, scheduler SM-2, regras de progressão, estatísticas. Sem I/O, sem UI, sem SQLite.
- **`storage/`** — adaptador SQLite. Depende apenas dos tipos de `core/`.
- **`session/`** — casos de uso (DrillSession, DiagnosticSession). Orquestra `core/` + `storage/` e emite eventos tipados. Não conhece a UI.
- **`ui/`** — adaptador Textual consome eventos de `session/`. Uma GUI futura (Qt, web) é outro adaptador do mesmo contrato, sem tocar nas camadas inferiores.

## Desenvolvimento

```bash
pytest                    # testes
ruff check src tests      # lint
ruff format src tests     # formatação
mypy src/aitken           # tipos
```

## Roadmap

- Níveis: tabuada 2-9, 2-19, 2d×1d, 2d×2d, quadrados até 25², 3d×1d, 3d×2d, 3d×3d, atalhos (×11, ×25, ×125, (10a+5)²).
- Major System para memória de trabalho em 3d×3d e 4d×4d.
- Export CSV/JSON do histórico.
- Modo Textual com painel de stats ao vivo (heatmap de latência por par da tabuada).
