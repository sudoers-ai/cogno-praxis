# Changelog

## Unreleased

### Added

- **`companies` — o cadastro de empresas passa a ser um vertical MCP, com política por papel.**
  Estava no host como skill nativa cogno-cortex (`cogno_host/company_registration.py` +
  `company_adapter.py`); vem para cá inteiro, com store port + adaptador Postgres, e liga-se a
  uma persona por `allowed_modules` como o `scheduler`. É **transversal**: não é o domínio de
  nenhuma persona — a SECRETARY carrega-o ao lado da agenda.

  **Cinco ferramentas**, uma por linha da política do dono: `company_registration` (o nome NÃO
  muda — ver abaixo), `company_search`, `list_companies`, `company_update`, `company_delete`.

  Quatro coisas foram **medidas antes de escritas**, e cada uma mudou o desenho:

  1. **O NOME da ferramenta de registo é um contrato, não um rótulo.** O host decide de que
     empresa se está a falar procurando execuções chamadas exactamente `company_registration` e
     lendo `company_id`/`company_name` da resposta. Um rename não parte nada: o foco pára de se
     mover, e o turno seguinte planeia para a empresa errada com um texto que continua
     plausível. O nome e as chaves da resposta ficam byte a byte, e o pino vive **deste lado**
     também, porque a mudança que o parte acontece aqui.
  2. **A resposta é um `repr`, e a tool é `-> str`.** O host lê-a com `ast.literal_eval`. Anotar
     `-> dict` faria o FastMCP serializar em JSON: passa hoje (todos os valores são strings) e
     **falha fechado** no dia em que um valor for `bool` ou `None`, sem um único vermelho.
  3. **Uma recusa de ESCRITA levanta; um limite de LEITURA é dito em palavras.** Medido pela
     cadeia real: uma string devolvida é um retorno normal, logo o cogno-mcp constrói
     `ToolResult(ok=True, side_effect=True)` — que registaria um cadastro recusado como escrita
     comitada. Mas uma recusa de leitura que sai como ERRO chega ao contacto como «não consegui
     acessar»: a voz lê uma avaria e pede desculpa pelo sistema em vez de dizer a fronteira. Por
     isso as leituras respondem normalmente e **dizem o limite**, e só as escritas levantam.
  4. **A CONTAGEM decide a FORMA da resposta da busca.** A regra do dono é «pesquisou por um
     específico, usa ele». Exactamente um resultado responde com um mapping; zero, vários e
     **toda** listagem respondem em prosa, que o parser do host rejeita sozinho. Assim nenhuma
     contagem tem de concordar entre dois repositórios — e uma LEITURA nunca ganha o efeito de
     uma escrita sobre o estado da sessão. Quatro gémeos, um por ramo.

  **Escopo por identidade:** staff (`EMPLOYEE`/`SUPERVISOR`/`ADMIN`/`OWNER`) vê as empresas do
  negócio; qualquer outro papel — incluindo um desconhecido — vê só as que registou
  (`created_by_user_id`). A verificação repete-se à ENTRADA das escritas porque o `company_id`
  é derivado do nome e portanto **adivinhável**.

  `company_delete` é **gate C** (`_meta`, a ponte já provada no bookkeeper), não gate B: o B
  decide pelo NOME antes de correr e nunca poderia dizer QUAL empresa; este lê primeiro e
  pergunta com o que leu. `company_registration` e `company_update` entram em `_UNDOABLE`.

  A tabela é a **mesma** `tenant_companies` do host, com as mesmas colunas e a mesma chave
  primária: o host continua a LER dali para montar o bloco «empresa em foco».

### Fixed

- **COMPANIES: corrigir um campo deixa de apagar outro — e o `segment` ganha quem o escreva.**
  Medido: «corrige o SEGMENTO para padaria artesanal» chegou como
  `company_update(guidelines='artisanal bakery')`. O campo errado, e as diretrizes que estavam
  gravadas foram SUBSTITUÍDAS. Três metades, e só duas são código:

  1. **A perda que não precisa de modelo nenhum.** `company_registration` PROMETE que registar
     uma empresa que já está em ficha ACTUALIZA o registo — e reconstruía a linha a partir dos
     argumentos dados, com o default de cada um dos outros. Medido no commit base: corrigir só
     as diretrizes de uma empresa que tinha CNPJ, segmento e identidade visual **apagou os
     três** (`ON CONFLICT … SET cnpj = EXCLUDED.cnpj`, e o mesmo para os outros dois). Passa a
     valer a mesma regra que o `update` já enunciava: **um campo que não é enviado fica como
     está.** Apagar um campo continua deliberadamente inexprimível.
  2. **O `segment` era coluna sem escritor no caminho do registo.** Existia na tabela, no
     `update` e na busca; uma empresa registada nascia sempre sem segmento até alguém a
     corrigir noutro turno. `company_registration(segment=…)` fecha o par, e a resposta do
     registo passa a dizer o que está EM FICHA em vez de ecoar os argumentos — depois de (1),
     ecoar o argumento diria `visual_identity: ''` sobre uma empresa que tem uma.
  3. **A descrição é a promessa, e não distinguia os três campos.** `segment` (o que a empresa
     FAZ), `visual_identity` (como a marca SE VÊ) e `guidelines` (como a marca FALA) passam a
     ter cada um a sua linha, com as palavras que o contacto usa — «segmento», «ramo»,
     «diretrizes», «tom de voz» — coladas ao campo que significam. E a resposta do `update`
     passa a NOMEAR o que se moveu (`CHANGED segment: 'padaria' → 'padaria artesanal'`): uma
     linha de empresa lida depois da escrita é idêntica quer o campo certo tenha mudado quer
     tenha sido o vizinho.

  Uma chamada que não altera nada passa a RECUSAR em vez de responder — devolver faria
  cogno-mcp construir `ToolResult(ok=True, side_effect=True)`, uma escrita que nunca houve
  contada pelo `committed_this_turn` do host (a propriedade do #104, aplicada a este vertical).

  **A frase honesta:** a metade (3) que decide QUAL argumento o modelo escolhe é do MODELO — a
  descrição é a única alavanca que este repositório tem sobre ela. As metades (1) e (2), e o
  facto de a resposta nomear o campo, são PORTÃO.

- **SCHEDULER: uma lista vazia deixa de apagar o catálogo inteiro de um escopo.**
  `PgAppointmentStore.sync_hosts([])` corria `DELETE FROM schedule_hosts WHERE scope = %s` —
  sem `NOT IN`, todos os profissionais do inquilino numa só instrução. A fronteira ENTRE
  inquilinos já estava fechada (`WHERE scope`); o defeito era dentro do escopo.

  A lista chega de um chamador que não consegue distinguir os seus dois significados:
  `COGNO_SCHEDULER_HOSTS="[]"` é o que um host emite tanto quando o inquilino não tem mesmo
  profissionais agendáveis como quando aquilo a que perguntou não devolveu nada. Um desses
  significados custa um catálogo real e nenhuma resposta o desfaz, portanto a ambiguidade
  resolve-se do único modo que uma primitiva destrutiva a pode resolver: **guarda o que lá
  está e diz que guardou** (`event=sync_hosts_empty_refused`, com `kept=`).

  **Encolher continua a funcionar**, e é essa a metade que importa nomear: uma lista NÃO vazia
  remove quem falta nela, logo um profissional retirado do painel continua a deixar de ser
  agendável. O que deixou de ter porta é «remover o ÚLTIMO» — esvaziar o catálogo faz-se
  apagando a identidade (`purge_identity`). Uma oferta velha é reversível pelo operador a quem
  o aviso chega; um catálogo apagado não é.

  O aviso só sai quando há algo a perder: um inquilino legitimamente sem profissionais não
  perde nada, e um aviso que dispara no caso normal é um aviso que ninguém lê no dia em que
  significa alguma coisa.

- **COORDINATOR: a TURMA passa a viajar em toda a linha — e «outras turmas» deixa de ser lido
  como «outros professores».** Medido em 06/09 nos turnos t56–t57 do dono.

  1. **A turma não estava a faltar nos DADOS, estava a faltar na FORMATAÇÃO.** `sheet_key` —
     o rótulo que o próprio tenant deu à planilha, que neste vertical *é* a turma — carrega-se
     em cada `ClassEntry` desde que o vertical existe e só chegava a um humano dentro de uma
     mensagem de erro. Um professor com quatro turmas recebia quatro listas de datas
     indistinguíveis. Agora toda a linha abre com `Turma: <o nome do tenant>`, em **todas** as
     ferramentas de leitura, porque a formatação é partilhada.
  2. **A mesma data era dita TRÊS vezes.** O layout do tenant gasta três colunas num dia
     (`Mês | Dia | Data`, o mesmo valor nas três, no formato cru da folha) e a linha chegava ao
     modelo como `Mês: 2026-09-08 00:00:00 | Dia: 2026-09-08 00:00:00 | Data: 2026-09-08
     00:00:00 | …`. Agora a data é dita **uma vez**, normalizada `DD/MM/AAAA` como no resto do
     sistema. O critério é a **DATA, não o nome da coluna**: só se dobra uma célula que resolve
     para o MESMO dia — um `Dia` com «Terça» é outro facto e sobrevive.
  3. **Filtro por turma (`turma`), com casamento tolerante.** Um prefixo nu leva a família
     («DSA» → DSA_33 e DSA_34); separador, caixa e espaçamento não decidem nada («DE_09»,
     «de 09», «DE09»; uma das chaves vivas tem **dois espaços**). Um `turma` que não designa
     nada devolve **vazio e diz porquê**, nomeando as turmas configuradas — largar o filtro em
     silêncio responde a uma pergunta que ninguém fez, e adivinhar a turma manda um professor
     para a sala errada.
  4. **«DE» é uma PREPOSIÇÃO, e foi isso que decidiu o normalizador.** Um prefixo de turma pode
     ser a palavra mais comum de uma frase de agenda («as aulas **de** outubro»). Duas regras
     foram **medidas uma contra a outra antes de qualquer uma ser escrita**: esmagar tudo e
     fazer substring transforma a conjunção «e» — a primeira palavra do turno t57 — num filtro
     que devolve as duas turmas `DE`; a regra embarcada (corrida contígua de tokens) não
     responde nada. A sonda de sobre-aperto está **embarcada como teste parametrizado**. O
     normalizador aplica-se **ao ARGUMENTO**, nunca a texto livre: a ferramenta não procura
     turmas na frase.
  5. **«Outras turmas» dito por um professor são AS AULAS DELE nas outras turmas.** O âmbito
     não mudou nada — um EMPLOYEE continua a ver só as próprias aulas — mas a persona lia o
     pedido como sendo sobre *outros professores* e recusava-o por âmbito. O `system.txt` passa
     a distingui-los explicitamente («there is nothing to refuse»), e a dizer que perguntar por
     outra turma **não é** perguntar pelo passado (o modelo tinha ligado `include_past=true`
     sem ninguém pedir passado). Os nomes das turmas **não** são injectados: medido no host,
     o `custom_rules` já é anexado ao prompt do EGO e as quatro chegam lá — o que faltava era o
     significado, não a lista.

- **COORDINATOR: quatro consertos de uma só conversa — o horário que a persona disse não
  conseguir aceder, e o que a fez dizê-lo.** Medido em 06/09 nos turnos t50–t55 do dono.

  1. **O parser de `SPREADSHEETS:` falhava em SILÊNCIO e engolia uma URL como id de planilha.**
     A secção do tenant tem chaves **com espaço** («`Turma SMP_33 = <id>`») e o regex exigia
     `\S+\s*=`: a secção não era reconhecida, caía-se na varredura do TEXTO INTEIRO à procura
     de tokens longos, e o slug de 31 caracteres de uma URL de curso no meio das regras entrava
     como `SHEET_1`. Iterado primeiro, dava 404 no Drive e a excepção levava a chamada inteira —
     3/3 tentativas, o juiz a rejeitar as três, e o professor a ouvir «não consegui acessar»
     com **quatro planilhas boas** legíveis. Agora: chaves com espaço são chaves; **um cabeçalho
     declarado nunca cai na varredura** (sem par utilizável, «não configurado» é a resposta
     verdadeira e um id adivinhado não é); e **uma planilha que falha não mata as outras** — o
     erro fica **por planilha** (`Turma SMP_33: HTTP 404`) e o tool devolve o que leu. A ESCRITA
     não degrada: `confirm_swap` **recusa** sobre um horário meio carregado, porque «essa aula
     não está lá» e «a folha que a tinha não abriu» são indistinguíveis e a segunda, agida, move
     a linha errada. A fixture do teste é **anonimizada** e estruturalmente equivalente (ids
     inventados com a morfologia certa, slug inventado): reproduz o defeito, e nenhum id do
     tenant entra num repositório público.
  2. **O mês em INGLÊS não filtrava, e custava uma volta inteira de juiz.** O executor lê a
     reescrita canónica em inglês do NOUMENO, por isso «aulas de setembro» chegava como
     `month="September"` → `None` → **sem filtro** → o ano inteiro (com um workshop de abril
     numa conversa de setembro) → o juiz rejeitava → a 2.ª tentativa acertava com `2026-09`.
     Os nomes ingleses entram na tabela, ao lado dos portugueses; onde as duas línguas partilham
     prefixo («mar», «jun», «jul», «nov») partilham também o mês.
  3. **A janela por omissão passa a ser `[HOJE, ∞)`.** As planilhas guardam o ano lectivo
     inteiro e devolvê-lo deixava a escolha ao modelo — foi assim que abril foi lido de volta.
     O passado pede-se: `include_past=True`, ou nomeando um mês **já terminado**, que é o mesmo
     pedido dito de outra maneira. Um mês **em curso** mostra de hoje ao fim do mês. O corte é à
     granularidade do **DIA** (uma aula das 08h ainda é de hoje às 15h) e **nunca esconde uma
     linha sem data**. A frase «a partir de hoje» só aparece quando **houve mesmo corte**.
     E o «hoje» vem da **âncora do host** (`COGNO_COORDINATOR_TODAY`, o mesmo dia que ele rende
     como `[HOJE]`), não do relógio do processo: o contentor arranca em UTC de propósito, e sem
     isto, entre as 21h e a meia-noite em São Paulo, uma aula de hoje desaparecia da lista. O
     host carimba essa variável desde que o vertical existe; este servidor era o único dos três
     que não a lia.
  4. **Uma recusa de âmbito chega como LIMITE, não como avaria.** A regra não mudou — um
     EMPLOYEE continua a ver só as suas aulas e um SUPERVISOR/ADMIN continua a ver as dos outros.
     Mudou a PALAVRA: `ERROR: You can only view your own schedule.` ensinava ao modelo que houve
     uma falha, e «não consegui acessar» era o que saía. `CoordinatorAccessError` é agora uma
     classe própria e o wrapper MCP rende-a como `NOT PERMITTED: … not a failure`, com o
     `voice.txt` a nomear a frase a NÃO produzir e o `limits.txt` a dizer ao juiz que um limite
     dito com verdade é uma resposta **completa**.

  O `system.txt` ganha as metades que só o prompt pode dar: o contacto **já está identificado**
  (nada de pedir nome ou matrícula a quem o sistema autenticou — t50), `professor` fica **vazio**
  para «minhas aulas», e o `include_past` liga-se só a pedido explícito.

### Changed

- **INTERVIEWER («Carol»): a persona de entrevista/checklist/formulário entra no pacote —
  sem nome próprio, sem guião de campanha, e com a abertura a fazer a 1.ª pergunta da lista.**
  Criada em 04/09 pelo Gemini do dono **sem commit, só nos checkouts servidos** (praxis:
  `cogno_praxis/interviewer/` + package-data + `tests/unit/test_interviewer_prompts.py`, e um
  `form_collector/` órfão quase igual; host: `PersonaSpec` + itens). O checklist de campanha do
  dono (mes_ano / frequencia_semanal / objetivo_campanha) vive hoje na linha DELA em
  `tenant_personas` — o t86 que motivou o conserto do CLOSER conversa com a Carol. Copiado do
  servido para uma worktree (o servido não foi tocado); o `form_collector/` fica de fora (cópia
  sem `PersonaSpec`, e o Diretor trata do disco). Quatro coisas mudaram no que veio, cada uma
  medida ou grepada antes de escrita:

  1. **`system.txt` não se nomeia** («Seu nome padrão de atendimento é Carol» saiu) — nenhuma
     outra persona do praxis se nomeia (grep vazio); o nome é de `tenant_personas.display_name`,
     rendido pelo host no bloco de identidade. E o executor passa a saber que o checklist chega à
     etapa de voz, não a ele — a lição medida no CLOSER.
  2. **`voice.txt` perde o guião de domínio** — a tabela canónica de cronograma (Tema/Objetivo/
     Formato·CTA, Carrossel, Reel) e a «seção de datas comemorativas» eram roteiro de campanha
     numa persona GENÉRICA, e o MESMO guião já vive nas `custom_rules` do tenant: duas fontes, a
     forma exacta do defeito do CLOSER (#94). O base fica com condução (uma pergunta por vez,
     progresso, correcção, resumo) e ganha a regra do bloco de onboarding do host, com as
     palavras do CLOSER: **com bloco, a abertura cumprimenta, diz de onde fala e FAZ a primeira
     pergunta da lista — sem pedir licença, sem anunciar quantas**; o rascunho do executor não
     manda; sem bloco, as perguntas vêm das regras do tenant; sem nenhuma, pergunta o que a pessoa
     quer registar. A frase «consulte a skill `resolve_date`» **fica, porque é verdadeira**:
     medido no host (`_families_offered`, produção stubada, 4 papéis × notifier on/off), a
     INTERVIEWER recebe as MESMAS famílias que a SECRETARY — `resolve_date` e
     `update_my_details` em todos os papéis, `human_handoff` para contacto, `notify_user` + o
     quarteto de staff para staff — e um superconjunto estrito das do CLOSER (que é
     `conversational` e perde notify/profile/remind). `allowed_modules=()` não é portão de skill
     system. (Uma sonda de turno real no `closer_bench` mostrou só `resolve_date` para AMBAS —
     o harness não liga staff/profile/notifier; deriva de superfície documentada, não gate.)
  3. **`limits.txt` deixa de exigir calendário ao juiz** — «rejeite se apresentar datas com dias
     da semana incorretos» é a classe medida esta semana (juiz sem calendário a rejeitar a
     honestidade 3×): agora só há calendário a julgar contra a âncora `[HOJE]` / `resolve_date`
     presente no contexto, e um dia da semana calculado de cabeça é nomeado como coisa que NÃO
     se rejeita.
  4. **`scope.txt` diz ao guarda que a mensagem típica é uma resposta curta.** A persona não é
     `conversational` (a flag do host também tiraria notify/profile/remind), logo o guarda de
     escopo corre em todo turno — e uma entrevista é feita de respostas curtas. Medido no guarda
     sozinho (gpt-4o-mini, sem bypass do NER, N=6 por entrada): o texto servido bloqueava «umas 3
     por semana» **4/6** e «umas 3» **3/6** («Desculpe, mas não posso ajudar…»); este texto,
     **0/6** nas quatro entradas. Apareceu no A/B do bench 1/4 (t3 recusado).

  **A/B no modelo de produção** (`closer_bench::interviewer_checklist_abre_com_o_item` — o
  corpus t86 do dono na persona que hoje o recebe; grupo `optimized`, n=4 por braço, host
  `feat/interviewer-persona-spec`, controlo = a pasta `interviewer/` do servido byte a byte):

  | verificação | controlo (rascunho do Gemini) | ramo |
  |---|---|---|
  | t1 faz o 1.º item (mês/ano) | 0/4 («Oi! 😊 Como posso ajudar você hoje?») | **4/4** |
  | t2 faz o 2.º item (publicações/semana) | 4/4 | 4/4 |
  | t3 faz o 3.º item (objetivo) | 4/4 | 3/4 → ver abaixo |
  | t1 sem promessa de bateria | 4/4 | 4/4 |
  | sem roteiro do CLOSER / sem guião de campanha (3 turnos) | 4/4 · 4/4 | 4/4 · 4/4 |
  | placar | 26/27 ×4 | 27/27 ×3, 26/27 ×1 |

  O 3/4 do ramo é o guarda de escopo (ponto 4): «umas 3 por semana» recusado com «Desculpe,
  mas não posso ajudar com isso», EGO nunca correu — medido com o `scope.txt` servido nos dois
  braços. Repetido o braço com os bytes finais (`scope.txt` novo, n=4): t1 **4/4**, t2 2/4, t3
  **4/4**, sem promessa 4/4, placar 27/27 ×2 e 26/27 ×2 — o guarda deixou de recusar; o t2 a 2/4
  é ruído a n=4 com o `voice.txt` byte-idêntico (6/8 somando as duas séries do ramo), e o modo
  de falha tem nome: a voz repete o 1.º item como «qual o dia de outubro», levada pelo rascunho
  do executor, enquanto o estado do intake do host ainda lista `mes_ano` pendente no t2. **Contra o enunciado:** a
  descrição servida da persona («…apresentando o resumo consolidado ao final») ROTEAVA «me
  manda o resumo financeiro do mês» para a INTERVIEWER no teste de roteamento com descrições
  reais do host («resumo» é radical do BOOKKEEPER) — a descrição, que é sinal de roteamento,
  passou a falar só o vocabulário desta persona (correcção no host). Gémeos em
  `tests/unit/test_interviewer_prompts.py` (os 3 do Gemini ficam; +7).

- **O checklist declarado manda na ABERTURA do CLOSER: a pergunta da lista, sem pedir licença
  para uma bateria — e o roteiro base fica suspenso enquanto o bloco existir.**
  Turno t86 do dono (2026-09-04 ~03:35, CLOSER, EMPLOYEE): ao «Oi», a resposta colou a
  apresentação, «posso te fazer três perguntas rápidas sobre como funciona o atendimento?» e uma
  pergunta do checklist; dois turnos depois perguntou o «volume diário», que não está na lista do
  tenant. O host já tinha posto uma linha de escopo no próprio bloco (`intake._SCOPE_LINE`,
  cogno-host #705) e mediu-a **inócua no modelo de produção** — a instrução nasce aqui.

  **Onde nasce, medido** (grupo `optimized`: nano/4o-mini/luna, caso
  `closer_bench::checklist_manda_no_escopo`, n=4, controlo = este `voice.txt` na main byte a
  byte, host fixo em `18fa870`): o host roteia TODO turno de uma persona sem tools pelo executor
  (`_route_to_ego`), o `system.txt` diz-lhe na ABERTURA «posso te fazer três perguntas rápidas…»,
  e o rascunho do executor trouxe essa promessa em **4/4** aberturas («May I ask you three quick
  questions…») e uma pergunta do roteiro em **4/4** terceiros turnos — a voz transmitiu-os. O
  executor nunca recebe o bloco (o host anexa-o só ao slot de voz), portanto a voz é o único
  estágio que o pode recusar. A frase nova em `voice.txt`, condicionada ao bloco «Onboarding —
  ainda falta descobrir» do host: com o bloco, a abertura cumprimenta, diz de onde fala e FAZ a
  pergunta do bloco — sem pedir licença nem anunciar quantas perguntas virão; o que o executor
  tiver rascunhado de pedido de licença ou de roteiro NÃO se transmite; o roteiro fica SUSPENSO
  enquanto o bloco existir; sem bloco, tudo como estava.

  | verificação | controlo (main) | ramo (`voice.txt`) |
  |---|---|---|
  | t1 cita um item da lista | 0/4 | **4/4** |
  | t1 não diz «três perguntas rápidas» | 0/4 | **4/4** |
  | t3 não diz o roteiro base (instrumento) | 3/4 | **4/4** |
  | placar do caso | 22–23/25 | **25/25** |

  Três coisas medidas que contrariam o enunciado: (1) a promessa não vem do «peça licença» do
  `voice.txt` — vem do `system.txt:13` pelo rascunho do executor, e a voz é quem a larga (o
  rascunho continua a trazê-la 4/4 no ramo); (2) o «3/4» do controlo no t3 é do instrumento — a
  olho o roteiro fugiu **4/4** («quem costuma responder», «por qual canal», «o que mais costuma
  tomar seu tempo» passam ao lado de `_ROTEIRO_DA_PERSONA`), e no ramo 0/4 a olho também; (3) o
  `system.txt` **não mudou**: uma regra no executor (condicionada ao rasto do checklist no
  histórico, já que ele não vê o bloco) foi medida no mesmo A/B — 4/4 idêntico — e não
  acrescentou nada, porque com a abertura certa o próprio executor segue o questionário que o
  histórico mostra (rascunho do t3 sem roteiro 0/4). Alcance: condicionado ao bloco; sob uma
  trava de delegação segura o host rende o slot de voz do HUB com `onboarding_checklist=""` e o
  bloco não chega a prompt nenhum (defeito do host, fora daqui). Gémeos em
  `tests/unit/test_closer_prompts.py`: sem bloco o roteiro corre (toda frase que suspende nomeia o
  bloco); com bloco a abertura faz o item e continua a desta persona.

- **O portão C consegue perguntar: `remove_by_search` larga o `destructiveHint`.**
  O produtor do portão C entregue no #89 estava **entregue, servido, e não dispararia**. A causa
  não estava nele, estava numa palavra da anotação: o **portão B pre-empte o portão C por
  construção** — `cogno_anima/stages/ego.py` retém e faz `continue` *antes* de
  `dispatcher.execute`, portanto uma tool que ele segura **nunca corre**, e a pergunta
  fundamentada nunca chega a existir. Medido: com a anotação de ontem o traço recebia
  `"[PENDING CONFIRMATION] … is destructive and was NOT executed"` — sem data, sem valor, sem as
  irmãs. Nenhuma dessas três coisas o *nome* de uma ferramenta pode saber.

  **Isto não tira uma protecção, tira uma protecção REDUNDANTE**, e a redundância foi medida e não
  argumentada. O caminho de escrita é **inalcançável** sem `confirm_tx_id`: o `store.remove` vive
  no único ramo que exige o id, e um id que não esteja entre as linhas do próprio chamador volta a
  propor em vez de cair para "a mais recente". Quebrar essa forma (regressão ao apagar de um passo,
  pré-#89) põe **10 testes a vermelho** — a promessa é estrutural e é *medida*, não recordada.
  E o mesmo turno não se pode auto-confirmar: o id só existe depois da primeira resposta, portanto
  não cabe no mesmo passo, e mal a proposta chega o portão C levanta-se e o **laço pára**.

  **As duas metades tinham de aterrar juntas.** Tirar a anotação sem emitir o `_meta` deixa a
  proposta chegar ao EGO como `ok=True, side_effect=True` — o dispatcher calcula
  `side_effect = mutating and not asks` — e o turno passa a **declarar uma escrita que não houve**
  sobre uma chamada cujo próprio texto diz *"NOT REMOVED — nothing was deleted"*. Medido, e é a
  razão de o `_meta` não ser um extra.

  **O que muda no fio:** a proposta volta como um `TextContent` cujo `_meta` leva
  `cogno-mcp/needs_confirmation: true` e `cogno-mcp/confirm_arguments: {"confirm_tx_id": …}` — a
  ponte que o cogno-mcp#12 abriu ontem. O texto continua a ser a **prosa** fundamentada; o
  `outputSchema` desaparece para esta tool (o FastMCP valida o retorno contra ele, e um `-> str`
  faz devolver um `TextContent` rebentar — medido no mcp 1.16.0), o que era `{result: string}` e
  não dizia nada.

  **A varredura `test_tool_annotations.py` passou de binária a ternária:** uma tool mutante é
  *gated* (B), *undoable*, ou **ASKS BY ITSELF** (C) — e, como as vizinhas, a nova lista é
  **executada** e não acreditada. O raio de acção fica pinado num teste próprio: continuam com
  `destructiveHint` exactamente `cancel_appointment`, `confirm_swap` e `reschedule_appointment`,
  que **comitam à primeira chamada** e portanto não têm sobre o que fundamentar pergunta nenhuma.

  Fecha a lacuna que `test_bookkeeper_via_mcp.py` afirmava no verde (`needs_confirmation is False`),
  agora invertida.

- **`remove_by_search` PROPÕE antes de comitar — e a proposta cita a linha que ela leu.**
  O EGO tem três portões de confirmação e o terceiro (`cogno_anima/stages/ego.py`, "Fonte C" —
  *a skill correu, leu, e pergunta sobre ESTA chamada*) nunca tinha tido um produtor. Esta é a
  primeira, e a escolha não é arbitrária: `remove_by_search` **já lia antes de escrever**, e uma
  ferramenta que só escreve não tem sobre o que basear a pergunta — nasceria a adivinhar, que é
  exactamente o que o portão B faz.

  **O que o portão B não pode saber:** ele decide por NOME, antes de correr. Diz *"vai apagar
  alguma coisa"* e nunca *"vai apagar ESTA"*. Qual linha uma busca de substring dobrada em acento
  (`matches_query`) apanhou, de que valor e de que data — só depois de ler.

  **Antes:** `remove_by_search(query)` apagava a mais recente que casasse, à primeira, e devolvia
  `Removed: …`. **Agora:** a primeira chamada não apaga nada — devolve a linha que apagaria (data,
  descrição, valor) e as irmãs que a mesma busca apanhou; a segunda, com `confirm_tx_id=<id>`,
  apaga essa linha. Sem correspondência nenhuma → a frase de hoje, inalterada, e pergunta nenhuma.

  Dois defeitos que isto fecha, e nenhum deles é de fraseado: (1) `"internet"` casa a conta de
  Janeiro, a de Fevereiro e a de Março — a versão de um passo apagava a mais recente **em
  silêncio** e ninguém ficava a saber que existiam outras duas; (2) a confirmação é um **id**, não
  um sim/não, portanto um lançamento novo que entre entre a proposta e o "pode apagar" já não
  desloca o alvo. Um `confirm_tx_id` que já não esteja entre as linhas do chamador não recai em
  "a mais recente": propõe outra vez sobre o que HÁ.

  **O que ficou por fechar, e onde:** o campo `ToolResult.needs_confirmation` não é transportado
  pelo `cogno-mcp` (`grep -rn needs_confirmation` nesse repositório: zero ocorrências), portanto
  sobre a ponte MCP a proposta chega ao EGO como texto de ferramenta e o portão C do núcleo não
  chega a levantar-se. É o texto que protege o livro hoje; o campo é a metade que uma ponte teria
  de carregar.

- **Os testes MCP-sobre-stdio do bookkeeper e do scheduler passaram a medir ESTA árvore.** Ambos
  lançavam o servidor por caminho, e o subprocesso importava `cogno_praxis` do *editable install*
  — noutra worktree, um verde que pertence ao checkout de outra pessoa. O
  `test_coordinator_via_mcp.py` já tinha o `PYTHONPATH` e a razão escrita; os outros dois não.
  Encontrado por este PR ficar vermelho no sítio errado.

- **A base descartável passou a ser o DESTINO por omissão das suítes que fazem `DROP TABLE`.**
  Dono, 2026-08-26: *"Já temos um test só para os testes de integração, isso deveria ser
  padrão."* A guarda de 2026-08-04 transformou o engano numa recusa, mas continuava a deixar a
  pessoa **escrever** um DSN — e a forma que causou o estrago é justamente a que a shell já tem
  à mão (`COGNO_PG_DSN` exportado, um copiar-colar de distância de `COGNO_TEST_PG_DSN`).

  **Antes:** `DSN = os.environ.get("COGNO_TEST_PG_DSN")` nos dois módulos de Postgres; variável
  por pôr → `pytest.skip`. **Agora:** `resolve_test_dsn()` — explícito ganha; sem ele,
  `cogno_praxis_test` no servidor LOCAL que `COGNO_PG_DSN` já nomeia (ou nos defaults do libpq,
  que são o que o serviço do CI serve); nada à escuta → `""` → salta como saltava.

  O que torna isto seguro não é uma verificação, é uma **construção**: o nome da base nunca é
  trazido de lado nenhum, é **escrito** (`_for_test_database`). Dar a esta função o DSN exacto
  que causou a perda devolve o descartável, e `tests/unit/test_integration_db_guard.py` pina
  isso nos dois sentidos, incluindo que TODO default nomeia uma base de teste seja qual for o
  ambiente. Um `COGNO_PG_DSN` REMOTO não é adoptado: `cogno_praxis_test` na instância gerida de
  alguém não é nossa para criar, quanto mais para largar.

- **A guarda passou a inspeccionar o DSN RESOLVIDO, não a variável crua.** Tem de olhar para a
  mesma string que os fixtures vão abrir, ou as duas divergem e só uma é verificada. É também a
  segunda rede sob o parágrafo acima: um erro em `_for_test_database` não destrói nada, porque o
  `pytest_collection_modifyitems` volta a recusar o nome.

- **O teste de convenção deixou de poder passar em vazio.** Ele varre os módulos que leem o DSN;
  como esses deixaram de nomear a variável directamente, o termo de busca é o que pode
  envelhecer em silêncio — agora afirma também que a varredura ainda os encontra.

### Fixed

- **O docstring de `tests/integration/test_bookkeeper_postgres.py` ensinava
  `postgresql://postgres:test@localhost:55432/cogno`** — "test" na SENHA, a base VIVA da caixa
  demo no caminho. É exactamente a forma para a qual existe
  `test_refuses_when_only_the_password_says_test`, e estava a ser ensinada no ficheiro ao lado.
  O módulo faz `DROP TABLE bookkeeper_transactions` e `bookkeeper_clients`.
- **`examples/run_with_db.py`** dizia `postgresql://localhost/cogno` → `…/myapp`. Um exemplo não
  deve deixar o nome da base viva num sítio de onde se copia.
- **`README.md`** passou a dizer para onde vão os testes de Postgres, e que o nome da base é
  escolhido por eles.

- **O prompt do `scheduler` ensinava a sintaxe `<TOOL_CALL>` e dava dois exemplos completos.**
  A mecânica de chamada é do CORE (`cogno_anima.stages.ego`), que a renderiza **só quando o
  turno tem catálogo** — e um prompt que a ensina sozinho derrota essa guarda: uma persona sem
  tools lia na mesma dois exemplos de como emitir a tag, e uma tag emitida sem ter o que chamar
  não é uma chamada falhada, é TEXTO, que chega ao contato.

  A regra já existia — num comentário do `ego.py`, sem verificação nenhuma, violada há tempo
  indeterminado. Agora `tests/unit/test_prompts_own_no_tool_mechanics.py` varre
  `cogno_praxis/*/prompts/*.txt` e falha com a explicação; tem controlo para o caso de o glob
  deixar de casar, porque uma guarda sobre lista vazia passa para sempre.

  **A pedagogia ficou.** Os exemplos ensinavam ORDEM (`resolve_date` antes de `book_appointment`;
  `list_schedulable_hosts` antes de marcar), e isso é valioso — foi reescrito em prosa, sem a
  tag. Medido antes/depois no `hostbench secretary_bench --group cheap` (4 cenários com tools):
  **9/9 dos dois lados, com as MESMAS sequências de chamada** — tirar os exemplos não baixou a
  taxa. As duas corridas leram prompts diferentes, verificado no ficheiro resolvido.

## 0.1.1 — 2026-08-02

Dependency fix. **0.1.0 is broken for a fresh install** — upgrade.

- Cap the `mcp` SDK below 2.0. The SDK published 2.0.0 and moved
  `mcp.server.fastmcp`, which every vertical imports at module load, so an
  unbounded `mcp>=1.0` made any new resolve pick a version that fails to import
  before a single request runs. Existing environments were unaffected only
  because their venv already held a 1.x.

## 0.1.0 — 2026-07-25

First public release on PyPI.

The Cogno business verticals as standalone MCP servers (the product layer). Each vertical is an independent FastMCP server the host orchestrates via cogno-mcp; verticals own their domain logic + data behind their own store ports. Verticals: scheduler (agenda → SECRETARY persona) and bookkeeper (finance → BOOKKEEPER persona).
