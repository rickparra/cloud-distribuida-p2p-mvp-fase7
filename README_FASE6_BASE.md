# Fase 6 — PoC de plano de controle com Oracle

Este pacote cobre somente as partes atribuídas a este integrante: **Parte 2 (PoC), Parte 3 (validação técnica) e Parte 4 (evolução da arquitetura)**.

> **Escopo importante:** esta é uma PoC executada localmente, integrada a um Oracle Database real da FIAP. Ela valida o plano de controle (seleção, política, reserva e auditoria); não está implantada na Oracle Cloud Infrastructure (OCI) e não executa cargas em computadores reais de participantes.

## O que a PoC demonstra

Uma aplicação Python servida em `http://127.0.0.1:8000` recebe uma carga fictícia. Ela consulta o catálogo no Oracle, escolhe o nó lógico elegível de menor preço e chama `F6POC_ALLOCATE`. O trigger `TRG_F6POC_LEASE_GUARD` valida a alocação; os triggers de auditoria atualizam estado, reservam/liberam capacidade e registram a trilha. Triggers adicionais impedem transferir um lease autorizado para outro nó ou excluir um lease ativo. Após a autorização, a aplicação envia ao worker simulado, em `127.0.0.1:8001`, o identificador do nó selecionado e um payload fictício. O worker devolve esse identificador e o hash SHA-256 do JSON; isso demonstra a associação lógica entre a reserva e a resposta, mas não comprova execução em outra máquina nem processamento real da carga.

Há quatro **nós lógicos de demonstração** no catálogo Oracle: um brasileiro com TEE elegível, um sem TEE, um estrangeiro e um que mantém persistência local. Eles são registros de teste, não agentes ou VMs em execução. Tentativas recusadas ficam em `F6POC_REJECTIONS` e não criam lease. Para testar a recusa, selecione “Teste negativo” e escolha um nó inadequado. vCPU precisa ser inteira (validado na aplicação e no Oracle); o teto aceita no máximo duas casas decimais. Leases concluídos ou falhos liberam capacidade no Oracle.

## Executar no Windows

1. Tenha Python 3 instalado e acesso à rede Oracle da FIAP.
2. No PowerShell, entre nesta pasta e rode:

   ```powershell
   .\run.ps1
   ```

3. Digite seu usuário/RM Oracle e a senha no prompt oculto. O script cria um ambiente virtual local, instala `oracledb`, cria ou atualiza somente os objetos `F6POC_*`/`TRG_F6POC_*` e inicia a aplicação.
4. Abra `http://127.0.0.1:8000` no navegador. Pressione `Ctrl+C` no PowerShell para parar.

Se o PowerShell bloquear scripts locais, rode `powershell -ExecutionPolicy Bypass -File .\run.ps1` nesta pasta.

O script não grava credenciais no projeto. O host e SID/serviço estão definidos a partir da conexão FIAP usada no teste; podem ser substituídos pelas variáveis `ORACLE_USER` e `ORACLE_DSN`, se necessário. Testado com Python 3.13.5 e `oracledb` 26.0.1, fixado em `requirements.txt`.

> Execute somente contra o schema/conta Oracle de demonstração autorizado para o projeto. Antes de iniciar, confira host, serviço e usuário; não use um banco ou schema de produção. O instalador cria/atualiza objetos com prefixos `F6POC_*`/`TRG_F6POC_*`, e o smoke test faz gravações temporárias de teste antes de limpá-las.

## Testes

Testes locais das regras e validação de entrada:

```powershell
py -m unittest discover -s tests -v
```

Testes locais mais smoke test no Oracle real (solicita usuário e senha; rode em outra janela PowerShell). O smoke test verifica que um lease autorizado não pode ser transferido (`ORA-20019`) nem apagado enquanto ativo (`ORA-20020`):

```powershell
.\verify.ps1
```

O smoke test verifica objetos, autorização, recusa, concorrência, regra proporcional e hashes. As verificações isoladas usam `ROLLBACK`; o teste concorrente confirma em sessões separadas e depois remove seus dados temporários e restaura a capacidade original do nó.

## Arquivos

- `app.py`, `policy.py`: aplicação e explicação de elegibilidade.
- `tests/test_mock_worker.py`: teste da resposta simulada com a identidade lógica do nó.
- `schema.sql`, `seed.sql`: objetos Oracle e nós simulados.
- `run.ps1`: instalação, prompts de credencial (senha oculta), setup e inicialização.
- `smoke_oracle.py`, `tests/`, `verify.ps1`: testes de integração e unitários.
- `relatorio_validacao_tecnica.md`: resposta às Partes 2, 3 e 4.
- `diagrams/arquitetura_fase6.mmd` e `.svg`: vista visual do estado atual da PoC.
- `diagrams/arquitetura_evolucao_fase6.mmd` e `.svg`: arquitetura futura proposta, não implantada.
- `evidencias/oracle_smoke.txt`: saída do smoke test contra Oracle.

## Limites da prova de conceito

O banco e suas regras são reais. A aplicação e o único processo de worker são executados localmente. Os quatro nós, lances e payloads são demonstrações; nenhum dado real é enviado. A resposta do worker repete o identificador lógico recebido e calcula um hash do JSON, sem executar o conteúdo. Não há implantação na OCI, agentes em computadores externos, execução em hardware TEE, autenticação de usuário, teste de carga ou alta disponibilidade implantada. O relatório descreve esses itens como evolução, não como funcionalidades existentes.
