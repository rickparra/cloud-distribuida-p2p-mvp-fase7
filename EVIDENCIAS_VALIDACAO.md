# Evidências técnicas do MVP — 16/11/2026

Ambiente de validação: macOS, Python 3.13.18, `oracledb` 26.0.1 e Oracle
Database FIAP do schema de demonstração. Nenhuma credencial está neste pacote.

## Testes locais

- Compilação dos módulos Python e `python -m unittest discover -s tests -v`:
  **20 testes aprovados**.
- `smoke_http.py`, com a aplicação e dois workers em processos separados:
  lote `12,18,30,40` produziu soma `100` e média `25.00`; uma nova requisição
  encontrou os hashes e o relatório técnico no Oracle. O grafo `/topologia`
  destacou a execução concluída e a tentativa recusada a partir dos registros.
- A página inicial foi reorganizada em três ações principais (hospedar site,
  processar tarefa e ver topologia), com regras avançadas, histórico e catálogo
  recolhidos sob demanda. Cada ação é uma rota própria e só a rota atual recebe
  o destaque azul; o fluxo HTTP completo continuou passando após a alteração de UX/UI.
- O modo automático escolheu `BR-TEE-01` por R$ 2,00; o modo manual enviou o
  mesmo cálculo ao segundo executor `BR-TEE-02` por R$ 2,20.
- Tentativa com classificação sensível no nó `BR-SEM-TEE`: recusada pelo Oracle
  e exibida como `FAILED` no histórico.
- A aplicação foi encerrada e reiniciada; os registros e relatórios anteriores
  continuaram acessíveis. Entrada e resultado brutos não apareceram no Oracle.
- Uma falha de worker marcou o lease como `FAILED`, devolveu capacidade e
  mudou o ledger demonstrativo para `REFUNDED`. Uma execução concluída mudou
  o ledger para `RELEASED`, com bruto = taxa + repasse.
- Um operador de demonstração foi cadastrado como `PENDING`, ficou inelegível
  e só passou a `APPROVED` após decisão manual explícita. Aprovação não prova
  homologação documental ou técnica real.
- Página HTML pura `Hello World` publicada nos dois workers: 4 vCPU totais,
  divididas em dois leases de 2 vCPU em nós de operadores demonstrativos
  distintos. Seis requisições ao endereço único foram atendidas alternadamente:
  três por `BR-TEE-01` e três por `BR-TEE-02`, confirmadas pelo cabeçalho
  `X-Served-By`, pelo identificador do nó no próprio HTML e pela contagem na
  interface. O grafo destacou os dois nós.
- A hospedagem agrupada retornou HTTP 200 durante a janela e HTTP 410 após
  180 segundos. Ambos os leases passaram a `COMPLETED`, liberaram capacidade e
  seus ledgers demonstrativos passaram a `RELEASED`. Os hashes SHA-256 dos
  dois relatórios conferiram com o HTML servido por cada nó.
- Encerramento antecipado de outro grupo: HTTP 410 imediato, dois leases
  `FAILED`, capacidade liberada nos dois nós e ledgers `REFUNDED`.
- O formulário de hospedagem aceita nome do grupo, HTML puro customizado e modo
  dividido ou concentrado. O grafo também permite desativar e reativar
  `BR-TEE-01`/`BR-TEE-02`; o worker responde `DISABLED` enquanto o nó está fora.
- O pacote agora inclui `DOCUMENTO_CONSOLIDADO_FASE7.md`, com Canvas, modelo de
  receita, custos, projeção, KPIs, aquisição e roadmap, além do pitch executivo
  `output/pdf/Pitch_Fase7_Cloud_Distribuida.pdf`.
- O ZIP foi extraído em pasta nova: `bash run.sh` criou o ambiente virtual,
  iniciou aplicação e dois workers; os 20 testes e `smoke_http.py` passaram
  usando somente os arquivos extraídos.

## Smoke test Oracle

`verify_oracle.py` passou no schema atualizado: **14 objetos válidos** e seis
nós no catálogo do ambiente de teste (cinco do seed e um cadastro manual).
Verificou disputa concorrente por capacidade, bloqueios de lease ativo,
liberação de capacidade, cálculo e teto de preço, recusa de nó sem TEE,
cadeia de auditoria SHA-256, ausência de colunas de entrada/resultado bruto
e balanço do ledger. Os estados da hospedagem concordam com os leases. Cada
grupo de hospedagem possui exatamente dois leases em nós distintos. As
transações de regra usam rollback; o nó temporário do teste concorrente foi
removido.

## Escopo da evidência

Os dois workers executaram cálculo real em processos locais separados e
serviram o HTML apenas em `127.0.0.1`. A reserva de vCPU é lógica e não muda
o desempenho do site. O Oracle Database representa os computadores ociosos
ofertantes em registros de catálogo e controla a reserva; a CPU usada para
servir o HTML é a deste computador local. A
evidência não prova execução em máquina de provedor externo, TEE real,
implantação OCI, movimentação financeira ou processamento seguro de dados
pessoais. O catálogo, operadores, garantias e preços são de demonstração.
