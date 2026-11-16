# Documento Consolidado da Startup Fase 7

## Resumo executivo

A Cloud Distribuída P2P conecta dois lados de um mercado: clientes que precisam
de processamento sob demanda com menor custo e baixa latência no Brasil, e
operadores que desejam transformar capacidade computacional ociosa em receita.

O MVP demonstra o plano de controle dessa rede. O Oracle Database mantém o
catálogo, as regras de elegibilidade, os leases, a liquidação demonstrativa e a
trilha de auditoria. Workers locais representam os computadores ofertantes.
Essa separação deixa claro o que já foi demonstrado e o que ainda pertence à
evolução para produção.

## Problema e público prioritário

Na Fase 5, o problema central foi refinado como a dificuldade de usar
capacidade computacional distribuída sem perder controle sobre território,
operador, efemeridade dos dados e evidência de conformidade. O problema é mais
urgente para organizações reguladas, mas o primeiro recorte comercial deve ser
mais simples de vender.

### Demanda prioritária

- startups, equipes de dados, laboratórios e PMEs brasileiras com cargas
  batch, renderização, inferência ou processamento de arquivos;
- clientes que precisam de capacidade barata e baixa latência, mas não precisam
  colocar dados sensíveis no primeiro piloto;
- em uma segunda etapa, saúde, fintech, jurídico e setor público, com controles
  adicionais de conformidade.

### Oferta prioritária

- pequenas empresas, datacenters regionais e profissionais com máquinas
  subutilizadas;
- operadores que querem gerar renda extra com CPU disponível, mantendo regras
  de capacidade, preço e disponibilidade.

## MVP demonstrado

O MVP implementa:

1. catálogo Oracle com nós, capacidade, preço e atributos declarados;
2. política de elegibilidade por classificação, TEE declarado, território e
   persistência local;
3. seleção e reserva de um lease no Oracle;
4. execução de lote sintético em worker local;
5. grupo computacional nomeado, dividido em dois nós ou concentrado em um;
6. hospedagem de HTML puro por 180 segundos, com gateway e failover local;
7. grafo visual da jornada e controle de ativação/desativação dos workers;
8. hashes, auditoria encadeada e liquidação demonstrativa.

O MVP não afirma executar workloads confidenciais em hardware TEE real. Essa é
uma etapa futura; hoje os atributos TEE, território e homologação são dados
declarados no catálogo para demonstrar a política.

## Business Model Canvas atualizado

| Bloco | Decisão atual |
|---|---|
| **Segmentos de clientes** | Startups, PMEs, laboratórios e equipes de dados que precisam de compute barato e com baixa latência; depois setores regulados. |
| **Proposta de valor** | Capacidade computacional sob demanda, próxima do cliente brasileiro, com preço transparente, escolha de requisitos e evidência de execução. |
| **Canais** | Comunidade open source, GitHub, eventos técnicos, universidades, parceiros Oracle/OCI, indicação entre operadores e clientes-piloto. |
| **Relacionamento** | Self-service para cargas simples; onboarding assistido e relatório de conformidade para clientes corporativos. |
| **Fontes de receita** | Taxa de plataforma sobre o consumo de compute; no MVP a referência é 10% sobre o valor bruto do lease. Plano corporativo de conformidade é uma expansão futura. |
| **Recursos-chave** | Plano de controle Oracle, software de gateway, política de elegibilidade, rede de operadores, reputação e trilha de auditoria. |
| **Atividades-chave** | Homologar operadores, manter scheduler e auditoria, operar a comunidade, garantir disponibilidade e desenvolver conectores/API. |
| **Parcerias-chave** | Oracle/OCI, universidades, laboratórios, integradores, operadores regionais e comunidades de desenvolvedores. |
| **Estrutura de custos** | Oracle/OCI e observabilidade, desenvolvimento, suporte, segurança, aquisição de operadores, jurídico/compliance e pagamentos. |

## Monetização

O modelo inicial é marketplace B2B2C:

- o cliente paga pelo uso de CPU reservado e executado;
- o operador recebe a maior parte do valor do lease;
- a plataforma retém 10% como taxa de coordenação, auditoria, matching e
  liquidação;
- não há cobrança real no MVP, apenas ledger demonstrativo no Oracle;
- no futuro, um plano corporativo pode cobrar mensalidade por políticas,
  relatórios, SLA, suporte e integração via API.

A regra de preço deve continuar transparente: preço por vCPU-hora, capacidade
reservada, duração, região e requisitos de conformidade. O cliente escolhe o
teto; a plataforma nunca deve esconder uma cobrança posterior.

## Estrutura de custos

### Custos variáveis

- repasse aos operadores por vCPU-hora;
- processamento e tráfego na OCI/Oracle;
- taxas de pagamento e emissão fiscal;
- suporte proporcional ao volume de clientes.

### Custos fixos e semifixos

- engenharia e manutenção do scheduler;
- segurança, observabilidade, logs e resposta a incidentes;
- homologação de operadores e auditoria;
- jurídico, LGPD e contratos;
- comunidade, conteúdo técnico e aquisição dos primeiros clientes.

No MVP acadêmico, Oracle e os workers locais são usados para simulação; por
isso o custo financeiro observado não representa o custo de uma operação
comercial.

## Projeção financeira simplificada

Premissas acadêmicas: a plataforma retém 10% do GMV, o restante é repassado
aos operadores, e os números abaixo são cenários de planejamento, não promessa
de receita.

| Ano | Clientes pagantes médios | GMV anual | Receita da plataforma | Custos operacionais | Resultado antes de impostos |
|---:|---:|---:|---:|---:|---:|
| 1 | 25 a 50 em rampa | R$ 198.750 | R$ 19.875 | R$ 36.000 | -R$ 16.125 |
| 2 | 100 | R$ 1.080.000 | R$ 108.000 | R$ 72.000 | R$ 36.000 |
| 3 | 250 | R$ 3.600.000 | R$ 360.000 | R$ 180.000 | R$ 180.000 |

O ponto de atenção é o efeito de rede: a receita cresce somente quando existe
liquidez nos dois lados. Por isso o investimento inicial deve priorizar uma
região e um caso de uso, em vez de tentar cobrir todo o país de uma vez.

## KPIs

### Demanda

- clientes ativos mensais;
- taxa de ativação: cadastro até primeiro job concluído;
- jobs concluídos por cliente e taxa de recompra;
- GMV mensal e receita líquida da plataforma;
- CAC, payback e LTV/CAC.

### Oferta

- número de nós ativos e homologados;
- vCPU disponível e taxa de utilização;
- tempo médio até o primeiro job do operador;
- receita média por operador;
- churn de operadores e taxa de ocupação por região.

### Confiança e operação

- taxa de jobs concluídos;
- p95 de latência de alocação e início de execução;
- percentual de leases com trilha íntegra;
- disponibilidade do plano de controle;
- incidentes de dados: meta zero.

## Estratégia de aquisição

A estratégia segue uma lógica inspirada no início do Bitcoin: protocolo aberto,
comunidade antes de mídia paga, incentivos para os primeiros participantes e
crescimento por confiança verificável. Isso não envolve prometer token,
rendimento financeiro ou valorização especulativa.

### Lançamento em ciclos

1. publicar o código e o modelo de operação de forma transparente;
2. formar uma comunidade inicial em GitHub, Discord, eventos técnicos e
   universidades;
3. recrutar os primeiros operadores por convite e recompensa por capacidade
   realmente disponível;
4. recrutar clientes-piloto em um único caso de uso de batch não sensível;
5. publicar métricas agregadas de jobs, disponibilidade e repasse;
6. usar indicação entre operadores e clientes para criar o loop de crescimento;
7. converter os primeiros casos em estudos de caso e parceiros de canal.

O primeiro objetivo não é volume nacional. É provar liquidez local: poucos
clientes com uso recorrente e operadores suficientes para responder rápido.

## Posicionamento competitivo

Para o primeiro cliente, a Cloud Distribuída P2P não se posiciona como uma
substituta universal de AWS, Azure ou OCI. Ela entra como uma camada de compute
complementar para cargas distribuíveis, em que custo, proximidade regional e
evidência de execução importam mais do que elasticidade infinita.

O diferencial é combinar marketplace de capacidade ociosa, regras de
elegibilidade no Oracle e uma trilha verificável por execução. A comparação
deve ser feita contra três alternativas: nuvem hyperscale com maior custo para
cargas pequenas, hardware próprio com baixa flexibilidade e marketplaces de
compute sem política de território e auditoria. A promessa inicial é simples:
reservar capacidade adequada, executar a carga e mostrar como a decisão foi
tomada.

## Roadmap de escala

### Agora - MVP acadêmico

- Oracle como plano de controle;
- dois workers locais;
- lote sintético e HTML temporário;
- grupos computacionais, auditoria e grafo.

### 0 a 3 meses - piloto técnico

- deploy do control plane na OCI;
- autenticação, API e cadastro real de operadores;
- imagens de workload e isolamento por execução;
- telemetria, health checks e medição de latência;
- piloto com clientes de dados públicos ou internos de baixo risco.

### 3 a 6 meses - confiança comercial

- atestação de hardware e execução confidencial;
- criptografia ponta a ponta e microVM efêmera;
- políticas geográficas e por classificação;
- faturamento, repasse e SLA;
- primeiros contratos corporativos.

### 6 a 12 meses - escala

- múltiplas regiões e autoscaling;
- SDK e integração CI/CD;
- reputação de operadores e matching por histórico;
- Data Guard/RAC ou serviço gerenciado equivalente para o plano de controle;
- expansão para setores regulados.

## Validação com usuários

Três pessoas reais avaliaram o MVP e responderam a cinco perguntas padronizadas.
O resultado completo, registrado com primeiro nome e perfil, está em
`VALIDACAO_USABILIDADE_FASE7.md`.

O feedback confirmou a compreensão da proposta de cloud mais barata, menor
latência no Brasil e uso de capacidade ociosa. Os três participantes disseram
entender grupo computacional, nós e Oracle. A principal dificuldade foi a
interface: dois relatos pediram uma UI mais amigável e um participante ficou
perdido logo no início.

Como resposta, o MVP consolidou três rotas principais, passou a destacar apenas
a página ativa, explicou o grupo antes da hospedagem, adicionou o botão de
Hello World e tornou os controles dos nós explícitos. A conclusão é que o MVP
resolve a demonstração do fluxo técnico, mas precisa de design visual e
onboarding mais guiado antes de um piloto comercial.

## Conclusão

O MVP já prova a viabilidade do plano de controle e da experiência principal.
O próximo marco é transformar essa prova técnica em um piloto comercial,
começando por workloads simples, comunidade de operadores e métricas públicas
de confiança.
