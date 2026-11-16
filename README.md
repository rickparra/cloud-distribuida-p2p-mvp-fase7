# Cloud Distribuída P2P — MVP da Fase 7

MVP acadêmico que simula uma cloud distribuída: o Oracle mantém o catálogo,
as regras de elegibilidade, os leases e a trilha de auditoria; dois workers
locais representam os computadores ociosos de operadores que, no produto
final, poderiam alugar capacidade computacional.

## Como funciona

O fluxo principal tem três partes:

1. **Programar tarefa** — o usuário informa um lote sintético, vCPU, classe de
   dados e teto de preço. O Oracle escolhe um nó elegível, cria o lease e o
   worker local calcula soma, média, mínimo e máximo.
2. **Hospedar um site** — o usuário cria um grupo computacional nomeado e
   escolhe como distribuir a capacidade:
   - **Dividir entre 2 nós:** dois leases, um em cada worker, com a vCPU
     repartida;
   - **Concentrar em 1 nó:** um lease com toda a capacidade solicitada.
   O gateway usa o grupo para servir HTML puro por 3 minutos. O botão de
   Hello World preenche um exemplo pronto, mas também é possível informar
   qualquer HTML pequeno sem `<script>`.
3. **Ver a topologia** — o grafo mostra cliente, Oracle, catálogo, executores e
   resultado. Os botões de ativar/desativar simulam a entrada e saída de um
   computador ocioso; eles controlam os workers locais desta demonstração.

### O que o Oracle simula

O Oracle não fornece a CPU do HTML nem cria uma instância OCI para cada visita.
Ele simula o plano de controle do produto: catálogo de ofertantes, política,
reserva de capacidade, preço demonstrativo, estados de lease, liquidação
acadêmica e hashes. Os processos `worker.py` simulam os computadores dos
operadores no próprio computador do aluno.

## Como usar

### Pré-requisitos

- Python 3.13 (3.11+ também funciona para o código);
- acesso à conta Oracle FIAP usada no projeto;
- `git` (opcional, apenas para desenvolvimento).

### Configurar credenciais

As credenciais ficam somente no arquivo local `.env`, que está no `.gitignore`.
Nunca coloque senha em `README.md`, código, commit ou captura de tela.

```bash
cp .env.example .env
# edite .env e preencha ORACLE_USER e ORACLE_PASSWORD
```

`launch.py` carrega o `.env` automaticamente. Se o arquivo não existir, ele
solicita usuário e senha no terminal sem salvar os valores.

### Iniciar

macOS/Linux:

```bash
./run.sh
```

Windows PowerShell:

```powershell
./run.ps1
```

Depois abra <http://127.0.0.1:8000/>.

### Roteiro rápido de demonstração

1. Abra **Hospedar um site**.
2. Informe um nome, mantenha **Dividir entre 2 nós** e escolha 4 vCPU.
3. Clique em **Preencher e hospedar Hello World**.
4. Clique em **Abrir site hospedado**. O HTML mostra o nó que respondeu.
5. Atualize algumas vezes ou use **Simular 6 visitas** para ver a distribuição.
6. Abra **Ver a topologia** e desative um nó; o worker passa a responder
   `DISABLED`. Reative-o ao final.
7. Para testar o fluxo de computação, abra **Processar uma tarefa** e envie o
   lote sintético padrão.

Cada página é uma rota própria (`/hosting`, `/processar`, `/topologia`) e apenas
a rota atual recebe o destaque azul.

### Testes

Com o ambiente virtual criado:

```bash
python -m unittest discover -s tests -v
python smoke_http.py
```

O smoke test exige a aplicação em execução, Oracle acessível e os dois workers
locais ativos. Os dados usados no teste são sintéticos.

## Estrutura do projeto

| Arquivo | Função |
|---|---|
| `app.py` | Interface HTTP, alocação, hospedagem, Oracle e relatórios |
| `launch.py` | Carrega `.env`, prepara o schema e inicia os workers |
| `worker.py` | Executor local de cada nó simulado |
| `hosting.py` | Registro temporário de HTML e expiração de 3 minutos |
| `topology.py` | Grafo visual e controles dos nós |
| `schema.sql` / `seed.sql` | Objetos e catálogo demonstrativo no Oracle |
| `smoke_http.py` | Validação ponta a ponta |
| `tests/` | Testes unitários |
| `evidencias/` | Capturas usadas na validação da Fase 7 |

## Limites do MVP

- O HTML fica em memória nos workers e expira após 180 segundos.
- O endereço é local (`127.0.0.1`); não é publicação na internet.
- Valores financeiros são demonstrativos; nenhum pagamento é movimentado.
- TEE, território e homologação são atributos do catálogo, não atestações
  físicas do hardware.
- Use somente dados sintéticos durante a demonstração.
