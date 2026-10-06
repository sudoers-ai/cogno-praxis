# Changelog

## Unreleased

### Added

- **Templated e-mail fields (`cogno_praxis.email_fields`) and `CoordinatorService.email_context`
  (E1).** The closed list of markers a tenant's e-mail template may use (`EMAIL_FIELDS`:
  `[nome]`, `[email]`, `[empresa]`, `[mes]`, `[disciplinas]`, `[aulas]`, `[valor_por_aula]`,
  `[valores_por_bonus]`, `[total]`, `[conteudo]`), the save-time validator (`validate_template`:
  an unknown marker, a bare `[`, `[conteudo]` twice, a multi-line marker in the subject,
  `[contrato]` before E3, `[cpf_cnpj]`, empty or oversized parts), the pure fill
  (`fill_email_fields` → `(values, missing)`, never raises; the recipient's address always
  required) and a one-pass render (`render_email`) with its digest (`email_digest`).
  - Why: the owner's order of 2026-10-06 — e-mails sent on request from per-persona templates,
    every value filled in code, the model writing only `[conteudo]`, a missing field stopping the
    send with a question; the value given per bonus level, always per month; no CPF/CNPJ.
  - `email_context` reads the schedule ONCE and returns the month's payable classes and the
    `PayEstimate` of the same rows, so `[aulas]` and the pay figures cannot disagree (the listing
    hides the month's past days; the estimate counts them). `estimate_professor_pay` now reads
    through the same two helpers (`_named_pay_rows`, `_own_pay_rows`) — the same calls in the same
    order; its tests are unchanged.
  - `[valores_por_bonus]` lists «Sem bônus» and every DECLARED band (`est.tiers`), not the
    hypotheses (empty once a result was read); a band is marked « ← apurado (IBOPE N%)» only when
    the bonus is determined. `[total]` is stated only when it is determined, or when the rules
    declare no band (then the base IS the total, as `FacultyPayEstimate.total_with_bonus` reads it).
  - `[mes]` renders in Portuguese («outubro/2026»), not through `month_label`, which is English.
  - Tests: `tests/unit/test_email_fields.py` (each refusal with its corrected twin; each `Missing`
    with the complete control; the one-read pair M1, `len × hours × rate == base` with the
    listing's shorter read beside it; the four bonus worlds; the owner's two template shapes
    byte for byte, twice, one digest). Docs: README «Templated e-mail fields»,
    `docs/COORDINATOR.md` «The e-mail context».

### Changed

- **The BOOKKEEPER's factory text sends AI COST to `token_cost_analytics`, by cut, not to
  `get_usage`.** `bookkeeper/prompts/system.txt` maps «AI cost / token spend, by message, day,
  conversation, persona, user or month» to `token_cost_analytics(granularity?, period?)` when it
  is among the turn's tools, and to `get_usage()` otherwise; the read-only list and the scope
  line name it too. `bookkeeper/prompts/limits.txt` lists it among the tools a financial value
  may come from and says a figure it returned is grounded; `get_usage` «only says where AI usage
  is metered and returns no figures».
  - Why: on a live rehearsal turn (invented data in the tests) a supervisor asked for the AI cost
    per day; the executor read the host's cost tool, the total matched the ledger, and the judge
    rejected the execution citing «AI token/usage → get_usage()». The persona had both tools and
    the text knew only the one that returns no number.
  - What does not change: `get_usage` stays (a deployment without the host's cost tool still has
    it), and every other prompt of every vertical is byte for byte `main` 45d2ed6 (19 digests).
    `test_coordinator_deadline_rules_read_the_documents.py` regenerates the two BOOKKEEPER
    digests it pins, with the reason.
  - Tests: `tests/unit/test_bookkeeper_ai_cost_comes_from_the_cost_tool.py` — the twin, the
    reconstruction to main's bytes, the JUDGE prompt `SuperegoStage.evaluate` renders over the
    old text (the claim is there) and the new one (it is gone, the cost tool is a source), and
    the neighbour control.
- **The `NO SUCH DISCIPLINE` line OPENS the listing, as the answer, instead of closing it.**
  `server._fmt_head` writes it above the classes; `_fmt_report(…, discipline=False)` leaves it out
  of the footers so it is said once (any other caller of `_fmt_report` still gets it there). The
  line now says the miss as a sentence of its own, asks for it as the reply's first sentence
  (`footers.SAY_THE_MISS_FIRST`) and no longer points "above" or "below".
  - Why: on a real read of this shape (a discipline nobody's schedule holds, invented names in the
    tests), the line was the last paragraph after the whole listing, worded as a note to the
    executor. The reply listed the classes and left the negative out 3 times in 5, so the contact
    never learned that the name matched nothing.
  - What does not change: every read without a miss renders byte for byte as on `main` 6d46f598
    (7 digests pinned, with a control that sees the one read that moved). The window notes stay
    under the list. The asked value and the list keep their bytes, and
    `parse_unmatched_discipline` reads both the new line and the old footer.
  - Tests: `tests/unit/test_the_miss_opens_the_listing.py` (5 tests red on `main`, including the
    position through the real anima voice prompt; 4 mutations killed).
- **The `NO SUCH DISCIPLINE` footer lists each discipline once, by its base name.**
  `_known_disciplines` cuts a status note from the end of a subject before it dedups. The notes
  are a closed list: the tenant's `POSTPONED_LABELS`, read the way `_is_postponed` reads them, plus
  «Reposição» / «reposição do dia DD/MM» and «Cancelada» / «Aula cancelada».
  - Why: in a real trace, one discipline had three rows (the class, «… - Aula Adiada», «… -
    reposição do dia 22/09»). The footer listed three names, and the host's «Você quis dizer:
    A / B / C?» offered the same discipline three times.
  - What does not change: a dash that is part of a name stays («Laboratório - Redes»). The list
    is still sorted under the fold. The asked value and the rest of the line are unchanged, and
    `parse_unmatched_discipline` reads the new list. Pay and free slots are unchanged
    (`_is_postponed` was split, not changed).
  - Tests: `tests/unit/test_known_disciplines_base_name.py` (twins red on `main` ad8df30, controls
    green in both).
- **The `NO SUCH DISCIPLINE` footer lists each discipline as a JSON string literal, and has a
  reader (VQD-2(a)).** `coordinator/footers.py` writes the line (`unmatched_discipline_line`) and
  reads it back (`parse_unmatched_discipline`), both exported from `cogno_praxis.coordinator`.
  - Why: the host asks the contact «Não encontrei X. Você quis dizer: A / B?» with names COPIED
    from this list, so the list is a closed alphabet. Joined with `", "`, a name with a comma of
    its own («Ética, Política e Sociedade») came back as three names, two of them on no sheet.
  - What changes for the executor and the judge: the names gain quotes. The asked value keeps its
    bytes for a plain name. `tests/unit/test_footers.py` pins the round trip (commas, quotes,
    backslashes, an empty list) and the old line, which the reader refuses.
- **A message to the team, composed, rewritten or corrected, is IN SCOPE wherever `notify_user` is
  offered.** One line, word for word as measured, goes into the IN SCOPE part of three `scope.txt`:
  «Messages to the team: composing, rewriting or sending a message/notification to a staff member
  — including the user's corrections to a message just proposed or declined.»
  - Where it goes: `scheduler` (a bullet at the end of `IN SCOPE (ALLOW):`), and `bookkeeper` and
    `interviewer` (the same bullet under an `Also allow:` lead, right before the BLOCK paragraph).
  - How they were chosen: the host's production surface puts `notify_user` on the table of the
    SECRETARY, BOOKKEEPER, COORDINATOR and INTERVIEWER for staff.
  - Why not the `coordinator`: it is a MEASURED prompt that already answers this request ALLOW
    5/5, and a measured file is not changed for consistency without a measurement that asks for
    it (Director). Its `scope.txt` is byte for byte `main`.
  - The `closer` (no tools, guard skipped) and the `companies` contribution do not take the line
    either.
  - Why: on a SECRETARY turn, a staff member declined a proposed message to a colleague and asked
    for a better one. The guard BLOCKED it 5/5, crude wording or clean, with the specific pending
    request in the prompt (host #1145). The clean sentence on a COORDINATOR turn: ALLOW 5/5. The
    cause was the SCOPE, not the tone. The "abusive" definition on the scheduler (#158) was
    closed without landing because it had no effect.
  - The table's own clause («a request that another capability offered on this turn serves is IN
    SCOPE») did not carry «faça uma mensagem melhor» with `notify_user` on the table. The lever is
    the DEFINITION, as in C3 (#153).
  - Tests (`tests/unit/test_messages_to_the_team_are_in_scope.py`, prompt-only):
    - the twin: the line is in the part that ALLOWS of each of the three;
    - the control: without the insertion, each file is `main` 5c57490 byte for byte (digests
      pinned, old and new);
    - `coordinator`, `closer` and `companies` are unchanged, and the six are every scope on disk.
  - The scope digests pinned by #153, #154 and #156's tests are regenerated or stripped before
    measuring.
- **`find_replacement_slot`: uma vaga escrita como FRASE que traz o rótulo conta como livre.**
  A planilha de um professor marca as vagas como «Espaço Reservado para Reposição (se
  necessário)», e o `_is_free` comparava a célula INTEIRA com `FREE_SLOT_LABELS`; a ferramenta
  respondia «No open slots in the next 21 days» (incidente do dono, persona COORDINATOR). Regra do
  dono, sem nada novo na configuração (`_is_free_by_word`): a célula é livre quando (a) traz um
  rótulo como PALAVRA INTEIRA, dobrada, e (b) a linha não é aula — sem professor, sem nenhuma
  disciplina conhecida da leitura inteira (`_known_class_names`) e sem nenhuma turma. O rótulo na
  célula inteira continua livre como antes. O guarda do turno 105 fica pelos controlos: «Redes -
  Reposição» continua aula, «… - Aula adiada» continua adiada, uma disciplina cujo nome contém
  «reposição» continua aula, e «Livreto» não traz «livre». O mesmo predicado alimenta o
  `confirm_swap` e a estimativa de pagamento. `ReadReport.free_by_word` conta as vagas DEVOLVIDAS
  lidas assim e o rodapé di-lo. `docs/COORDINATOR.md`;
  `tests/unit/test_coordinator_free_slot_by_word.py` (nomes inventados).
- **The five `scope.txt` that block "abusive" messages now say what the word means — the same
  sentence in all five** (`bookkeeper`, `closer`, `companies`, `coordinator`, `interviewer`; the
  `scheduler` never uses the word and is unchanged). Undefined, the relevance guard read the word
  as TONE. In the shape measured on a rehearsal tenant, a contact rejected a message the
  assistant had proposed, with a swear word, and asked for a better one: BLOCK 5/5, even with the
  specific pending request in the prompt (host #1145). The same sentence without the swear word:
  ALLOW 5/5.
  - The sentence, appended as each file's last paragraph: «"Abusive" means an insult or a threat
    aimed at a PERSON (anyone in the conversation, the assistant included). Criticism of what the
    assistant wrote, even crude or profane, is NOT abuse: treat it as a request to change that
    text.» It is English in the two Portuguese files too (one string, kept equal by a test).
  - The INTERVIEWER's scope also says «ofensivas», so its copy opens with
    «"Abusive"/"offensive" means …», derived from the same sentence by one substitution. The
    variant is in that file alone, so the other four (the measured coordinator included) do not
    move.
  - No shared include exists (the host reads each file raw), so the sameness is a test.
  - Tests (`tests/unit/test_abusive_is_defined_in_every_scope.py`, prompt-only): the files that
    say "abusiv…" are derived from disk and must be exactly the five; the twin (the sentence is
    each file's last paragraph); the sameness (read out of each file); the control (without the
    paragraph, each file is `main`'s byte for byte, old and new digests pinned); the scheduler
    unchanged. The scope digests pinned by `test_bookkeeper_scope_names_assets_and_investments.py`
    and `test_coordinator_deadline_rules_read_the_documents.py` are regenerated here, and the
    first one's control strips the later paragraph before measuring its own sentence.
  - Whether the guard obeys is measured outside this repo, against the served guard.
- **`get_professor_schedule`: uma `discipline` que não casa com nada deixa de dar «No classes
  found» (M6-c).** Na forma do traço 2056, o executor punha em `discipline` o nome do PROGRAMA
  («MBA em …») e a ferramenta dizia que o professor não tinha aulas. Segue o precedente do
  `unmatched_turma`: `ReadReport.unmatched_discipline` + `known_disciplines` (as disciplinas da
  leitura do chamador), e a lista passa a ser as próximas aulas SEM o filtro, com a janela por
  omissão. O rodapé diz `NO SUCH DISCIPLINE` e nomeia as disciplinas. Julgado antes do mês (uma
  disciplina que existe noutro mês não é um falhanço); sem `report`, a lista vazia de antes.
  `docs/COORDINATOR.md`; `tests/unit/test_coordinator_unmatched_discipline.py` (nomes inventados:
  gémeo, controlo da disciplina que casa, do outro mês e do chamador sem `report`).
- **A regra 6 (`unread_schedule_claim`) deixa de admitir a `consult_material`:
  `MATERIAL_READ_TOOLS` = `{"consult_documents"}`.** O conjunto tinha dois nomes enquanto um host
  ainda servisse a ferramenta antiga, e dizia que o velho só sairia depois de o host a retirar.
  Retirou: o host tirou a `consult_material` na F2.4 P5c e fez o corte final do `# MATERIAL`
  (cogno-host #1085). Nenhum host a oferece já. Uma leitura com o nome antigo passa a fundamentar
  tanto como qualquer leitura que não seja material registado, ou seja, NADA. A regra não muda:
  admite-se pelo NOME e depois pelo VALOR.
- **Testes** (`tests/unit/test_unread_schedule_claim_material_read.py`, conteúdo inventado):
  - o gémeo: as duas respostas medidas e os MESMOS payloads, devolvidos por uma leitura
    `consult_material`, passam a ser reparados (antes: `None`);
  - os gémeos dos casos medidos, e o da leitura que NÃO contém o valor, correm agora pela
    `consult_documents` sobre os mesmos payloads;
  - o conjunto preso a `{"consult_documents"}`.
- **Quem lê o conjunto fora daqui:** nenhum código. No `origin/main` das irmãs, o nome aparece só
  em prosa no host (o `CHANGELOG.md` e o docstring de `test_rule6_admits_consult_documents.py`).
  Esse teste exercita só a `consult_documents`, por isso o próximo pino da praxis no host não o
  parte.

### Fixed

- **`coordinator/prompts/system.txt`: the COORDINATOR's tool mapping tells the deadlines OPEN now
  from the deadline RULES.** The mapping had one line, «Grade/attendance deadlines →
  check_deadlines(professor?)». Asked «what deadlines does the teacher have to meet?», the
  executor called `check_deadlines` 5/5 and `consult_documents` 0/5 on a rehearsal tenant,
  although `consult_documents` was on the table and the host's generic documents duty was in the
  prompt. The mapping line won.
  - The fix splits that line in two: the deadlines currently OPEN (which disciplines are due now)
    stay with `check_deadlines`; the deadline RULES a teacher must follow (what is due, by when,
    after each class) go to `consult_documents`, «when it is among this turn's tools». The bytes
    are the replay's, and they are not padded to the arrow column the other lines use.
  - The condition closes the RULES line, after the arrow. `consult_documents` is the host's tool,
    offered only on a turn whose reader has a published document to read, so without the
    condition the mapping would send the question to a tool that is not on that turn's table. A version with
    the condition BEFORE the arrow scored 4/5 in the same replay and was discarded.
  - Measurement (offline A/B, calibrated, the served host's real executor prompt, n=5): the
    question went from `check_deadlines` 5/5 to `consult_documents` 5/5, and a records control
    («which disciplines have a grade deadline expiring this week?») stayed on `check_deadlines`
    5/5. A generic documents duty, tried on the same calibration, stayed on `check_deadlines` 5/5,
    so the lever is the persona's own mapping. The final line, with its condition, measured the
    same: the question 5/5 on `consult_documents`, the control 5/5 on `check_deadlines`.
  - The judge, measured with `coordinator/prompts/limits.txt` unchanged (it lists the tools a
    schedule fact may come from, and `consult_documents` is not among them): it APPROVED the
    correct reply 5/5 and REJECTED 5/5 a control reply that invents a deadline. So `limits.txt`
    does not change.
  - The question is ambiguous (rules, or deadlines open now). This change sends it to the rules;
    reading both was not measured and is not done.
  - This is the first prompt in this repo that names `consult_documents`. The measured turns had
    it on the table; a turn without it is what the condition is for (`docs/COORDINATOR.md`).
  - Tests (`tests/unit/test_coordinator_deadline_rules_read_the_documents.py`, prompt-only):
    - the twin: the two lines are in the mapping, in the old line's place, and the old line is
      gone; the RULES line ends with its condition;
    - the control: with the old line put back, the file is `main`'s byte for byte (sha256
      pinned, and the new digest too);
    - every other prompt of every vertical is unchanged (20 digests).
  - Who reads the file outside this repo: the host, which loads it as the COORDINATOR's executor
    prompt. Of this repo's `prompts/*.txt`, this is the only file that changes.
- **`bookkeeper/prompts/scope.txt`: the BOOKKEEPER's scope now names the business's own ASSETS
  and INVESTMENTS, not only its ledger.** The ALLOW paragraph said «any message about the
  business's finances» but listed ledger operations only. The relevance guard BLOCKED a question
  about what one of the business's properties cost to build and renovate, with the owner's
  document outline (its «Investimento» section included) already in the guard's prompt. So the
  cause was the definition, not the prompt's structure.
  - The fix is one sentence, spliced right after «…listing clients, and AI-usage questions.» on
    the same line, byte for byte as measured.
  - Measurement (production guard, n=5): the question went from BLOCK 5/5 to ALLOW 5/5, and an
    out-of-scope control stayed BLOCK 5/5 either way.
  - The other definitions that list only their tools' operations were NOT widened, because none
    of them was measured.
  - Tests (`tests/unit/test_bookkeeper_scope_names_assets_and_investments.py`, prompt-only):
    - the twin: the sentence is in the ALLOW paragraph of the file the host loads;
    - the control: without the sentence, the file is `main`'s byte for byte (sha256 pinned, and
      the new digest too);
    - every neighbouring `scope.txt` is unchanged.
  - Who reads the file outside this repo: the host's scope guard, through its
    `_bookkeeper_prompts_dir()`. Of this repo's `prompts/*.txt`, this is the only file that
    changes.
- **`bookkeeper/grounding.py::ground_reply` — a read of the business's DOCUMENT, declared by the
  host, is a source (`source_reads=`, optional, default `()` = the verdicts of before, byte for
  byte).** Measured 10 of 10 on a rehearsal tenant (2026-09-29): the executor read the document,
  the draft quoted the three figures of the section asked about, the judge approved — and this net
  replaced every reply with «Deixa eu consultar…»: 8 by `fabricated_entry` (the document's
  attributive participle, copied by the draft and always POST-nominal — «… mensal registrada» 4×,
  «… meses registrados» 4× — on a turn with no LEDGER read) and 2 by `conjured_totals` (money
  beside «líquido» in one, «total» in the other). **4 of the 8 carry «líquido» too**, so rules (1)
  and (3) are excused together or the reply only moves from one to the other. `is_read_query` was
  true in all ten; it is not a gate here.
  - The host passes the names of ITS source-read tools; **no tool name is written in this repo**,
    and an undeclared read of the same document grounds nothing.
  - By VALUE: EVERY money value in the reply must be written in the WHOLE result of a successful
    call to a declared tool (the one grammar of `declared_values`: «R$ 4.500» = «R$ 4.500,00»).
  - It excuses only the ATTRIBUTIVE participle of rule (1) — with no ledger write called this turn —
    and rule (3). Never: the RECEIPT shape (the participle opening its clause, «Registrado!
    R$ 150,00», even when the document holds R$ 150,00), the EXPLICIT claim («Registrei», «foi
    registrada»), a value computed from the document (a sum of its rows, a year from a month), ONE
    value the document does not hold, a failed read.
  - The measured contradiction with the briefing, written down: «Registrado! R$ X» was described
    as the explicit branch; in the code it is the attributive one (`_RECORDED_RE` only reads first
    person, «acabei de» and copula + participle). Exempting the attributive branch whole would have
    let a receipt of a document's own price through, hence the receipt shape.
  - The scheduler's `ground_reply` accepts the keyword and reads nothing from it (the host hands
    every vertical the same keywords); its rule 6 keeps `MATERIAL_READ_TOOLS`.
- **Declared limits** (pinned): a receipt with a word or its value's comma before the participle
  («Tudo registrado: R$ 150,00», «Vistoria registrada: R$ 150,00», «R$ 150,00 registrado!») reads as
  the listing when a declared read holds every value and no write was called — the exposure a
  LEDGER read already has for any value, narrowed to the document's; a presentational ESTAR («Aqui
  estão os valores registrados») is the explicit branch and is never excused; English
  «Recorded income: …» at a clause start reads as the receipt (strict side, only pt measured).
- **Tests** (`tests/unit/test_a_source_read_grounds_the_listing_never_the_receipt.py`, invented
  document and figures, the figures past char 4000): the ten twins in their form (8 + 2, each in
  both worlds), the old corpus shape unchanged, the receipt and explicit controls with the value IN
  the document, computed totals, one-of-three, undeclared / failed / cut reads, a write called,
  en/es, the scheduler keyword, and the no-declaration digest over 896 verdicts taken on `main`
  d81d3ca. Docs: `docs/BOOKKEEPER.md` § «A document the host DECLARES a source read is a source».

- **`cogno_praxis.declared_values` — a gramática ÚNICA lê três formas que lia mal (F2.1 PR-1).**
  Os desacordos da proveniência por valor classificaram-se em três leituras ERRADAS do
  extractor (não em fontes que faltassem). A gramática é partilhada com o M3c, com as redes e com
  a proveniência do host, e cada correcção vale para todos eles:
  - **(i) o sinal.** `R$ -45,00`, `R$-45,00`, `-R$ 45,00`, `R$ −45,00` (U+2212), um `-45.00`
    nu e `-45 reais` são MENOS quarenta e cinco; antes eram lidos `45,00`, e um valor de sinal
    trocado passava pelo mesmo valor. O sinal só conta encostado ao número ou ao símbolo: `R$
    45,00 - R$ 10,00` continua a ser dois positivos, `10-20` um intervalo, `2026-09-25` uma data e
    `91234-5678` nada. Só dinheiro.
  - **(ii) o negrito partido pela voz.** `**R$**\n**1.440**` passa a ser UM valor: entre o
    símbolo e o número a gramática aceita brancos, ênfase markdown e no máximo UMA quebra de
    linha (uma linha em branco é outro parágrafo, e nada se cola ao símbolo). O literal volta sem
    a ênfase, `R$ 1.440`. Antes, um valor sem centavos nessa forma não era lido de todo.
    (A forma `**R$\n1.234,56**` citada no briefing já era lida, medido; a cegueira era sem
    centavos ou com a ênfase pelo meio.)
  - **(iii) a unidade debaixo de uma chave de máquina.** `"window_days": 7` passa a ser 7 DIAS:
    um número cuja chave tem uma palavra de unidade como UMA das suas partes lê-se nessa unidade.
    Contam só plurais e as abreviaturas (`days/dias/d`, `hours/horas/hrs/h`,
    `minutes/minutos/mins/min`, `weeks/semanas`, `months/meses`, `years/anos`). Uma parte no
    singular (`day`, `month`, `hour`) é muito mais vezes um componente de data ou uma taxa do que
    uma duração: `{"year": 2026, "month": 7, "day": 7}`, `day_of_week: 7` e `price_per_hour: 7`
    não lêem unidade nenhuma. A chave tem de PARECER de máquina (entre aspas, snake_case ou
    `chave=`), por isso a prosa («Dias: 7») nunca é lida assim. A unidade é exigida DENTRO do
    padrão, por isso uma chave que não a nomeia (`"amount": 45.00`) nunca é consumida aqui, e o
    número dela lê-se como antes.
- **O que isto NÃO fecha, dito:** a proveniência do host lê ainda os números nus de uma fonte de
  máquina com a SUA própria regex (`value_provenance._BARE_NUMBER_RE`), que não leva o sinal.
  Com o pino novo, uma fonte `-45.00` fonteia `R$ -45,00` (pela gramática) mas continua a
  fontear também `R$ 45,00` (pela regex do host). O sentido inverso já fica fechado aqui (uma
  fonte `45.00` não fonteia `R$ -45,00`). O resto é uma linha no host.
- **Testes** (`tests/unit/test_declared_values_three_readings.py`, valores inventados): em cada
  forma, o gémeo com o controlo —
  - o negativo fonteado pelo mesmo negativo, e NÃO pelo positivo, nos dois sentidos da troca;
  - os traços que não são sinal;
  - o valor na linha seguinte ao símbolo, e o símbolo sem número (ou com o número no parágrafo
    seguinte), que não dá nada;
  - a chave que nomeia a unidade, e as dez que não a nomeiam;
  - a chave sem unidade que devolve o número à gramática;
  - todo o literal que a extracção entrega relê-se como a mesma chave.

### Fixed

- **A regra 6 (`unread_schedule_claim`) passa a admitir a `consult_documents`.** A excepção que
  deixa uma leitura de MATERIAL registado fundamentar uma resposta de horário — quando a saída da
  leitura CONTÉM um valor de horário que a resposta afirma — estava presa a um nome só,
  `MATERIAL_READ_TOOL = "consult_material"`. A `consult_documents` (a pesquisa do host sobre os
  documentos que o negócio PUBLICOU), que já está servida e substitui a `consult_material`, não
  estava admitida: uma resposta de horário tirada dos documentos disparava o reparo e uma
  resposta reescrita, a mesma forma medida 2/2 no ensaio de 22/09 antes de a `consult_material`
  ser admitida. A constante passa a um conjunto, **`MATERIAL_READ_TOOLS`** =
  `{"consult_material", "consult_documents"}`. A `consult_material` fica enquanto o host a
  servir, e só sai do conjunto depois de o host a retirar. A regra não muda: a admissão continua
  a ser pelo NOME e depois pelo VALOR, nunca pela forma da saída. O nome singular desaparece (não
  tinha nenhum leitor fora deste módulo em nenhum repo do ecossistema).
- **Testes** (`tests/unit/test_unread_schedule_claim_material_read.py`, conteúdo inventado na
  forma do payload da `consult_documents`):
  - o gémeo dos dois casos medidos — «60 horas» sobre «(60h)» e «19h00 às 22h30» sobre a grade —
    agora lidos pela `consult_documents`, que não dão reparo;
  - o CONTROLO: a MESMA saída devolvida por uma ferramenta que não é de material continua a não
    fundamentar;
  - uma leitura dos documentos que não contém o valor continua a dar reparo, e uma leitura
    falhada não fundamenta nada;
  - o conjunto preso aos dois nomes.

### Added

- **A decisão do estativo passa a API PÚBLICA de `cogno_praxis.bookkeeper.grounding`**
  (`__all__`): `write_attempted(tools)`, `mask_possessive_stative(reply, locale)` e
  `mask_declared_stative(reply, *, tools, declared_values, locale)` — a última é a decisão inteira
  (mascara as orações estativas quando todos os valores estão declarados e nenhuma escrita do
  livro foi chamada) e o próprio `ground_reply` passa a lê-la. Existe porque a rede genérica de um
  host lê o mesmo particípio e, com uma cópia desta regra, reescrevia o que ela deixava passar; um
  host chama estas funções em vez de importar nomes privados. `_write_attempted` fica como alias.
  Comportamento de `ground_reply` inalterado; `test_the_public_stative_api.py` prende o contrato.

- **`cogno_praxis.declared_values` — os valores que o negócio escreveu na configuração da persona
  são FONTE, por valor.** Uma gramática só para valores escritos literalmente num texto (dinheiro,
  percentagens, datas, números com unidade de tempo — nunca nomes nem frases): `declared_values`
  extrai (o host chama-a sobre as regras resolvidas para o papel do contacto), `values_declared`
  compara. Os dois lados passam pelo mesmo parser: `R$ 120,00` = `R$ 120`, e `R$ 1.440` nunca é
  1,44. `bookkeeper.ground_reply(..., declared_values=())`: a `fabricated_entry` deixa de ler o
  particípio atributivo/estativo («tenho registrado», «a receita registrada») como lançamento
  quando TODOS os valores da resposta estão declarados — o ESTATIVO possessivo («tenho/temos
  registrado», «tengo registrado») por um FACTO do registo (nenhuma escrita chamada neste turno,
  nem falhada), o particípio NU («Registrado!») só quando o contacto estava a perguntar
  (`is_read_query`), porque no recibo inventado também não se chamou escrita nenhuma. Limite
  declarado: «Tenho registrado: R$ 10,00» depois de um pedido de escrita passa (8 estativos na
  caixa inteira, nenhum recibo); a
  `conjured_totals` aceita um total que É um valor declarado. Continuam a disparar: a alegação
  explícita («registrei», «acabei de lançar», «já está lançado») mesmo com o preço declarado, o
  recibo numa PETIÇÃO de escrita, um valor não declarado, e um valor DERIVADO (soma, total mensal a
  partir de um preço por hora). Sem valores declarados, tudo como antes. O `scheduler.ground_reply`
  aceita a palavra-chave e não a lê.

### Changed

- **en/es: o particípio atributivo passa a ter a mesma regra do pt.** Até aqui os bundles en e es
  liam o particípio nu («the recorded income», «los ingresos registrados») como alegação
  explícita, portanto uma listagem verdadeira era reescrita mesmo com uma leitura do livro na mão.
  Cópula + particípio continua explícita nas três línguas. Controlo: sobre um corpus determinístico
  (todas as strings com dígitos dos testes e benches da praxis e do host, 73 044 células), 0
  fabricações perdidas sem leitura; as 172 células que mudam são todas en/es COM leitura do livro.
- **`bookkeeper/prompts/limits.txt`**: um valor financeiro vem de uma ferramenta OU dos valores
  que o negócio declarou na configuração da persona; valores calculados não são declarados, e um
  lançamento só é confirmado pela ferramenta que o fez. A frase «invents
  amounts/summaries/confirmations without a tool call» fica intacta.

### Fixed

- **A dobra passa de `lower` a `casefold`, como no host: «Straße» e «Strasse» são o mesmo nome
  (#145).** A dobra única do ecossistema (`cogno_host.textfold.fold`) é NFKD → marcas
  combinantes removidas → `casefold`, por esta ordem, e continua idempotente sobre todo o Unicode.
  As três cópias da praxis que SEGUEM o host acompanham-no: `scheduler.service._fold`,
  `bookkeeper.engine._fold` (a pesquisa `matches_query`) e `coordinator.service._norm`. **Ficam
  como estão, de propósito** (só os comentários ao lado mudam, com a distância nova ao host):
  `companies.identifiers.fold` (chave do `company_id`, congelada; alinhar pede migração; 817 code
  points, o `ß` incluído), `coordinator.ics._norm` (chave do UID dos eventos que os calendários
  guardam; 190 code points) e `coordinator.rsvp._norm` (decisão do Director; 867 code points).
  Medido contra `4dc5043`: das 100 000 cadeias do scheduler, 7 280 dobram de outra maneira, todas
  pelo conjunto do `casefold`. Das 170 consultas de agenda sobre 14 marcáveis inventados, 167 ficam
  iguais, 3 ganham um match («Strasse», «STRASSE», «GRAÇA STRASSE» → «Graça Straße») e 0 perdem.
  As 15 expressões do `resolve_date` dão o mesmo. Na pesquisa do bookkeeper, 3 de 20 000 veredictos
  mudam, todos False→True. `tests/unit/test_the_fold_keeps_the_letters.py` fixa a definição (o
  sigma final testado como cadeia, «ΟΔΟΣ», porque o `lower` o decide por contexto) e a paridade do
  `ß`. O PR irmão do host troca o `textfold` junto com o pino da praxis, porque o teste de
  sincronia do host fica vermelho enquanto só uma das pontas tiver o `casefold`.

- **`coordinator` — três seguimentos do #142: a resposta parcial diz que é parcial; a escrita
  ambígua fica provada intacta; o resultado IBOPE deixa de ir para outra pessoa.** (F1) Com o
  rótulo «Ana Lopes» numa folha com uma linha «Ana Lopes» e duas «Prof. Ana Lopes», a agenda e a
  remuneração própria davam 4 h · R$ 400,00 **sem nota nenhuma** (antes do #142 eram 12 h). O
  filtro tinha razão em recusar as duas linhas; a resposta é que não podia parecer inteira. Agora
  `ReadReport.unconfirmed_similar` (um BIT) põe no rodapé «há linhas com um nome parecido com o
  seu que não foi possível confirmar como suas», sem nomear ninguém e sem contagem. Vale para a
  agenda, as leituras do dia, a ficha e a remuneração, incluindo o ramo «No classes found». (F2)
  `confirm_swap` e `record_class_response` com um rótulo ambíguo recusam, e a folha é comparada
  antes e depois, com uma âncora que prova que a mesma escrita, por um rótulo resolvido, a muda.
  (F3) O `_ibope_result` era par a par: «Ana Lopes», com um separador IBOPE que só tinha «Ana
  Maria Lopes» (92 %) e uma «Ana Beatriz Lopes» na agenda, recebia os 92 % da Ana Maria e a faixa
  de R$ 40,00/h. Passa a usar o mesmo `_own_spellings` com a guarda, sobre o separador E a agenda.

- **`coordinator` — um professor (papel não-oversight) vê as linhas com o SEU nome, não as de
  todo nome que o contém.** O ramo não-oversight de `_visible` e de `get_professor_info` fixava a
  leitura ao rótulo da identidade por SUBSTRING dobrada, e «ana» está dentro de «mariana». Medido
  na base com um EMPLOYEE «Ana» (1 aula sua, 3 de «Mariana Lopes»): o horário devolvia 4 linhas;
  a remuneração PRÓPRIA dava 16 h · R$ 1.600,00 em vez de 4 h · R$ 400,00; `professor_email`
  devolvia o endereço da outra professora (para onde iria o calendário); e as duas ESCRITAS atrás
  do mesmo filtro — `record_class_response` e `confirm_swap` — recusaram e moveram a aula DELA.
  Agora é `_own_spellings`: igualdade por tokens dobrados com a regra que o IBOPE próprio já usava
  (`_same_professor` — igual, ou a forma mais completa com o primeiro E o último nome iguais), e
  uma grafia que OUTRO nome da folha também reclama é largada. Fecha as 9 formas de fuga medidas
  (incluindo o apelido partilhado, «Ana Lopes» vs «Mariana Lopes»); aceita a forma curta («Ana
  Lopes» → «Ana Maria Lopes», que a substring RECUSAVA), acentos, caixa, espaços e a partícula.
  **Recusa, contadas, 4 formas que podem ser do próprio**: rótulo sem o apelido, rótulo só com o
  primeiro nome, título na folha e inicial (as três primeiras a substring ACEITAVA). As duas
  primeiras são, token a token, a forma de uma pessoa DIFERENTE, e num filtro de privacidade o
  erro desqualificante é a fuga. A supervisão por nome não mexe. **E a recusa diz o PORQUÊ**:
  quando o rótulo não resolve nenhuma linha mas se PARECE com um nome da folha (`_near_spellings`),
  a porta deixa de responder «No classes found.» — falso nesse mundo, as aulas podem existir — e
  devolve `_LABEL_UNRESOLVED`: a identificação falhou, peça ao administrador o nome completo, sem
  nomear ninguém. Um rótulo resolvido sem aulas no período, ou que não se parece com nada, continua
  a receber «sem aulas», que aí é verdade.

- **`coordinator` — a listagem dá a grafia CANÓNICA do professor, para que quem lê a seguir o
  encontre.** O dono pediu para avisar «o professor» sem nomear ninguém; `get_weekly_briefing`
  devolveu a grafia da PLANILHA, o modelo passou-a a `notify_user`, que procura no directório de
  identidades — onde o professor está escrito de outra maneira — e o sistema **pediu ao dono o
  nome completo de um nome que ele acabara de dizer**. Corrido contra o directório real: a grafia
  completa da agenda não acha nada, nem sugestão; o primeiro nome sozinho acha. Agora toda a
  listagem (`get_weekly_briefing`, `get_professor_schedule`, `check_deadlines`,
  `check_ibope_status`, `find_replacement_slot`, `daily_checks`) renderiza a grafia que a ficha
  DECLARA, e nenhum consumidor a jusante precisa de aprender a resolver. Uma grafia que a ficha
  não alcança fica exactamente como a planilha a escreve. A resolução de uma grafia ÓRFÃ é a
  INTERSECÇÃO de dois sinais declarados — quem a ficha diz leccionar aquela DISCIPLINA, cruzado
  com quem partilha um TOKEN do nome — e só quando sobra **exactamente um**: dois é uma pergunta,
  não um empate, e o sistema não escolhe. **A intersecção decide o RÓTULO e nunca a soma**
  (`ProfessorGroup.shown_as`): ligada à junção, engole na remuneração de um professor declarado
  uma pessoa que o inquilino nunca declarou — medido contra o controlo do `#138`, que falhou na
  âncora. As aulas ficam onde estavam e o bloco continua a dizer que as duas grafias **não** foram
  somadas.

- **`coordinator` — a remuneração declarada em PROSA é NOMEADA na recusa, e as horas passam a
  ser as de CADA AULA (`HOURS_PER_CLASS`), nunca a carga da disciplina vezes as aulas.** Medido
  22/09/2026 em turnos reais (`turns.id` 1963–1968): `estimate_professor_pay` foi escolhida e
  correu, `ok=true`, e devolveu `NOT CONFIGURED: PAY_RATE_PER_HOUR, COLUMN_HOURS are missing` —
  sobre regras que TÊM os valores, em português corrido («Aula - R$ 120,00 por hora, sendo o
  mínimo 4 horas por aula», «Ibope > 80% e <89%: Adicional de R$ 30,00 por hora», «respondido por
  pelo menos 30% da turma»). `_find` lê só `CHAVE: valor` e devolve o default em silêncio, por
  isso a mesma verdade em duas gramáticas contava numa e nada avisava. Agora `CoordinatorConfig`
  RECONHECE essas formas (regex conservadora, por linha, ancorada numa figura — nunca lê a frase
  como número), avisa UMA vez por configuração por processo, e a recusa diz «found "R$ 120,00 por
  hora" in the rules, but PAY_RATE_PER_HOUR is not declared» para cada chave em prosa. Uma chave
  OPCIONAL em prosa (`IBOPE_BONUS`, `IBOPE_MIN_RESPONSE_PCT`) recusa também, pela razão da banda
  ilegível: «este tenant não declara bónus» sobre regras que o descrevem paga menos com a frase
  que um tenant sem bónus recebe legitimamente.

  A semântica das horas, fixada pelo dono («na planilha tem a carga horária completa da
  disciplina, cada linha na planilha equivale a 4 horas»): **remuneração do mês = aulas do mês ×
  `HOURS_PER_CLASS` × `PAY_RATE_PER_HOUR` (+ bónus IBOPE por hora)**. `HOURS_PER_CLASS` é chave
  NOVA e obrigatória — sem ela `NOT CONFIGURED` nomeia-a; nunca se infere 4 nem se divide a carga
  pelo número de aulas. `COLUMN_HOURS` passa a OPCIONAL e a CONTEXTO: a carga TOTAL da disciplina,
  numa secção própria no fim do bloco («Carga horária total das disciplinas»), com o valor da
  disciplina inteira (carga × valor/hora, sem bónus) — nunca mais multiplicada por aulas. Até
  aqui havia três declarações em desacordo dentro do código (`config.py` «per-discipline hour
  total»; `pay.py` `hours_each × classes`; o teste 16 h × 2 aulas → 32 h · R$ 3.840,00) e a que
  decidia o salário era a errada: a regra do dono paga 2 × 4 h × R$ 120,00 = **R$ 960,00**. Os
  testes fixam os números dele (960; IBOPE 85 % → 1.200; 92 % → 1.280) e o gémeo do erro antigo
  (carga 16 h e 2 aulas → 3.840 AUSENTE, a carga só como contexto). Bloco: nova linha «Horas por
  aula declaradas nas regras: 4 h»; a linha «Fora desta soma, por não terem carga horária
  declarada» desaparece (nada fica fora da soma por causa da planilha). `PayLine.hours_each` →
  `hours_per_class` + `workload`; `PayEstimate.hours_missing` → `workload_missing`, mais
  `hours_per_class` e `workload_read`.

  Duas fronteiras a mais, do mesmo dia: **`COLUMN_HOURS` declarada nas regras mas AUSENTE na
  aba é inerte** — `_workload_by_subject` devolve `None` (coluna não existe) em vez de `{}`
  (coluna existe, disciplina sem linha), a secção de contexto só se renderiza quando a coluna foi
  LIDA em pelo menos uma planilha (`PayEstimate.workload_read`), e declarada-mas-ausente rende
  byte a byte o mesmo bloco de quem não declarou: sem `NOT CONFIGURED`, sem `PARTIAL RESULT`,
  estimativa e bónus intactos (a ordem do dono é «não vamos mexer nas planilhas, se quiser mexer
  que seja no prompt»). E **a estimativa lê SEMPRE o mês inteiro** (`include_past=True`, período
  nomeado; período vazio = mês corrente completo + o que vem): medido no turno real 104, «quanto
  recebo pelas aulas de setembro» a meio do mês devolveu «1 aula» porque a leitura de lista
  esconde as passadas — para remuneração o mês é o mês, dadas e por dar (2 passadas + 1 futura
  → 3 × 4 h × R$ 120 = R$ 1.440). A LISTA (`get_professor_schedule`) não muda.

- **`scheduler/grounding` — a regra `unread_schedule_claim` passa a conhecer a leitura de material
  do host, e admite-a pelo VALOR, nunca pelo nome.** A regra 6 só aceitava como leitura as do próprio
  scheduler (`list_appointments`, `check_availability`); uma resposta fundamentada num
  `consult_material` com `ok=True` — a grade horária e a ementa REGISTADAS do inquilino — era
  reescrita como «respondeu de memória». Medido no tenant de ensaio (host `ad3b3920`, 22/09, n=2,
  espécimes `P1_P11_S2-horas-derivacao` e `P1_P12_S2p-carga-horaria-total`): 2/2 disparos, o
  gatilho nas duas foi a cauda de cortesia «ajuda com agendamentos» (`agendament` no padrão de
  ocupação), cada um pagou um re-passo da voz e num deles o executor chamou um `list_appointments`
  que ninguém pediu. Agora um `consult_material` bem-sucedido suprime a regra **quando o seu
  `output` contém uma figura de horário/duração que a resposta afirma** — «60 horas» sobre uma
  ementa que diz «(60h)», «19h00 às 22h30» sobre a grade que diz exactamente isso — comparadas
  por `schedule_figures`, que normaliza a H:MM para que a mesma grandeza escrita de outra maneira
  seja igual e um mero «30» dentro de «22h30» nunca valha por «30 minutos». Pelo nome sozinho a
  leitura lavaria qualquer figura inventada sobre uma consulta sem relação (gémeo 3); a listagem
  do scheduler continua a fundamentar por ESPÉCIE, como sempre (gémeo 4). É QUALQUER figura em
  comum e não todas: o espécime afirma uma duração DERIVADA da leitura (22h30 − 19h00 = 3h30) ao
  lado dos horários que repete tal e qual, e exigir todas repararia o próprio turno que isto
  existe para deixar em paz — qual figura a resposta reproduz bem é pergunta do juiz e do
  backstop de termos preservados, não desta rede. Limite nomeado, não decidido aqui: uma resposta
  que afirme SÓ a duração derivada, com os horários largados, não tem figura em comum com a
  leitura e continua a ser reparada como hoje.

- **`coordinator` — a caixa de correio é do INQUILINO, e é escolhida no momento do envio.** O
  remetente do calendário resolvia-se em `sender_from_env()` pela cadeia da herald (declaração do
  tenant → `SMTP_*` do ambiente → `None`) e ficava preso em `mcp = build_server()`, **no import**
  do subprocesso MCP. Medido na caixa que corre isto: o `.env` do deploy declara
  `SMTP_HOST`/`SMTP_USER`/`SMTP_PASSWORD`/`SMTP_FROM_EMAIL` e **não** declara
  `COGNO_COORDINATOR_SMTP`; `cogno_host.modules` entrega ao filho `{**os.environ, **env_extra}` e
  o seu próprio comentário diz que essa variável «is genuinely the box's and nothing per-turn
  re-injects it». Isso é uma frase só: **todo o inquilino, tivesse declarado ou não, enviava pela
  conta real do deploy** — um inquilino de ensaio incluído, cujo correio aterraria em caixas de
  entrada de estranhos vindo do endereço da casa. E a única configuração que o travava — apontar
  a variável partilhada para um sink — redireccionava **também** a COORDINATOR do dono, porque as
  duas pontas lêem a mesma variável do processo. Não era saída: era troca.

  Agora `mailer.sender_for_tenant(tenant_config)` é uma função **pura** do que aquele inquilino
  DECLAROU: sem declaração, `None`, e o `None` é a recusa honesta que o vertical já sabia dar
  (levanta, portanto `ok=False`/`side_effect=False`, e nada a jusante conta o turno como
  escrita). A forma da declaração **verifica-se a cada nível** em vez de se confiar — quem a
  passa é o host, e um `AttributeError` a sair de dentro do mailer mataria um turno que só
  estava a LER um horário; uma forma ilegível significa **nada declarado**, logo nada enviado,
  nunca um recurso a outra caixa. **Não há recurso ao `SMTP_*` do deploy** — e a assimetria com o convite de marcação
  (`cogno_host.api.pg_app`, que continua a usar a cadeia completa) é deliberada: uma confirmação
  de marcação é o produto a funcionar e a caixa da casa é o default certo; um calendário de aulas
  é uma instituição a escrever ao seu corpo docente, e um inquilino que não declarou caixa não
  pediu para escrever a ninguém. A `resolve_smtp_config` da herald continua a ser quem
  **normaliza** a declaração (porta, `from_email`, `use_tls`) — só se lhe chama com uma
  declaração na mão, o que torna o ramo do ambiente inalcançável por construção e não por ordem
  de chamadas.

  E `build_server` ganha `sender_for=` — um chamável perguntado **em cada chamada** das duas
  ferramentas de calendário —, a mesma forma que `cogno_host.api.pg_app._build_invite_sender` já
  usa para o convite (`_smtp_of(tenant_id)`, resolvido no envio). `sender=` mantém-se para quem já
  resolveu o inquilino; dar os dois levanta `ValueError`, porque um servidor com duas respostas a
  «que caixa» não consegue dizer por qual saiu a mensagem. Sem nenhum dos dois, o default é o
  mesmo `sender_from_env()` — mas perguntado por chamada, não congelado no arranque.

  Os gémeos estão em `tests/unit/test_the_mailer_belongs_to_one_tenant.py`, e o terceiro é o que
  impede o conserto de nascer inerte: **um servidor, construído uma vez, dois inquilinos, duas
  contas**. Um teste do `test_coordinator_mailer.py` afirmava exactamente o contrário
  (`the_environment_half_of_heralds_chain_is_what_builds_it`) — está virado, com o controlo da
  presença dentro do próprio teste.

### Added

- **`coordinator` — a resposta ao convite de aula passa a ficar gravada, pela metade CHAT.** O
  convite já pedia resposta desde #120 (`RSVP=TRUE` no `.ics`), e o que faltava era a volta:
  o professor dizia «aceito» e nada em lado nenhum ficava a saber. `record_class_response`
  (MCP, `readOnlyHint=False`, `destructiveHint=True`) grava **ACEITE / RECUSADA** na coluna
  `COLUMN_STATUS` da própria folha do tenant — a mesma célula que `server._entry_status` já lê
  para TODA a listagem, portanto a resposta aparece na agenda semanal, no `daily_checks` e no
  horário sem um leitor novo. **PENDENTE nunca se escreve**: é a célula vazia (ou o estado
  ordinário do tenant), o que o torna impossível de fabricar.

  **O que liga a resposta ao convite é a DATA que a resposta nomeia, e nada mais — dito assim
  porque o canal não dá outra coisa.** O convite sai por e-mail e a resposta chega por chat; o
  vertical é um subprocesso NOVO em cada turno, logo não pode lembrar-se do que perguntou; o
  adaptador Evolution nunca preenche `reply_to` e o host nunca o lê; e o `selection.id` de um
  botão é convertido em texto antes de chegar ao pipeline. Não há, hoje, referência à mensagem
  citada nem carga útil de botão a que agarrar uma resposta. Portanto a ligação é a mesma que o
  `confirm_swap` sempre usou para escrever nestes dados — `(professor, data)` resolvido contra a
  folha, com `_ambiguous_year` incluído — e chega como **argumento tipado**, não como frase
  interpretada.

  **Todas as recusas deixam a aula PENDENTE, que é uma resposta.** Sem data, com uma data que
  não bate, que bate em dois anos, ou que bate em duas turmas no mesmo dia → levanta erro e não
  escreve nada; a mensagem nomeia as turmas para que a segunda tentativa funcione (`turma`
  desempata). `answer` é um alfabeto FECHADO (`ACCEPTED`/`DECLINED`): «sim» não entra, e o
  detector de língua nunca vota — esta casa já mediu `"sim"` lido como finlandês.

  **Duas respostas iguais são UM estado**: a segunda não escreve e diz «was ALREADY recorded —
  no change was made», a frase que a cláusula NOTHING TO DO do juiz já sabe ler. **Mudar uma
  resposta anterior é permitido e fica gravado** — quem aceitou e depois não pode tem de o poder
  dizer —, mas **um valor que este sistema não escreveu nunca é sobrescrito**: uma nota que a
  secretaria deixou na folha dela não é deste feature para destruir.

  O porto ganhou **um** método, `SpreadsheetStore.write_cell`, nas mesmas coordenadas do
  `swap_rows` — que o adaptador Google já construía a partir exactamente desta operação, duas
  vezes por coluna. Config: `STATUS_ACCEPTED_LABEL` (`"Aceita"`) e `STATUS_DECLINED_LABEL`
  (`"Recusada"`), porque a palavra na célula é lida por uma pessoa na folha da instituição.

  **O e-mail continua fora**: nenhum `METHOD:REPLY`, nenhum leitor de `PARTSTAT`, nenhuma caixa
  de correio consultada. O botão «aceitar» de um cliente de calendário continua a não chegar a
  ninguém, e as prosas do `ics.py` que o diziam foram corrigidas para dizer QUAL das duas voltas
  ficou aberta em vez de negarem as duas.

- **`coordinator` — um professor passa a poder perguntar quanto ELE ganha, e o escopo abre só
  para isso.** Medido em dois turnos vivos do tenant do dono a 2026-09-06: às 22:35:30Z
  «como funciona a parte financeira. minhas aulas por exemplo, qto eu receberia por mes?» foi
  respondido com «informações sobre remuneração e pagamentos estão fora do meu escopo»; às
  22:39:07Z «baseado nesse calculos, qual seria o q tenho a receber…» com «Desculpe, mas não
  posso ajudar com questões financeiras.»

  **As duas recusas vieram de CAMADAS DIFERENTES**, e é por isso que esta mudança toca quatro
  prompts e não um. O traço do turno 67 traz `superego.blocked=true` com `judge_attempts=0` — o
  guarda de entrada parou-o antes de qualquer ferramenta correr. O turno 65 **não foi bloqueado**
  (`judge_rejected_all`, `last_draft_voiced`): o executor leu a agenda, escreveu um rascunho
  honesto, e o «You do NOT ... handle finances» da própria persona mais a cláusula de fora-de-
  escopo do juiz transformaram-no numa recusa. Abrir só a entrada consertava um dos dois.

  O rascunho do turno 65 é também a especificação da conta. Deixado a si mesmo, o executor
  escreveu «the schedule read did not return those hour totals» e «I can't calculate a reliable
  monthly total from the number of classes alone» — está certo, e é essa a falha que se fecha: as
  horas existem na folha da própria instituição e nada as estava a ler.

  **`estimate_professor_pay(period?, turma?)`**, SÓ LEITURA e **só do próprio**, para todos os
  papéis. Conta: `aulas no período × horas da disciplina × valor/hora` + bónus IBOPE. Saída
  agrupada por turma e mês, em bloco renderizado (cabeçalho `*negrito*`, linhas sem rótulos
  repetidos).

  **Nada aqui inventa um número**, e cada forma existe porque a alternativa é uma mentira:

  - **as horas vêm de uma coluna que o inquilino NOMEIA** (`COLUMN_HOURS`, na `TAB_HOURS` que
    por omissão é a `TAB_PROFESSORS` que ele já declarou). Não há default e não há farejar
    cabeçalhos: um header que «parece» horas é como um número de sala vira carga horária.
  - **o valor/hora e as faixas de bónus vêm das `custom_rules`** (`PAY_RATE_PER_HOUR`,
    `IBOPE_BONUS`, `IBOPE_MIN_RESPONSE_PCT`). Sem eles não há estimativa nenhuma — a recusa
    NOMEIA a chave que falta, e chega ao modelo como `NOT CONFIGURED:`, não como `ERROR:`, porque
    um inquilino que não declarou não é um sistema que avariou. As bandas separam-se por **`;`** e
    nunca por vírgula, que é o separador **decimal** de quem escreve as regras: com a vírgula,
    `80-89 = 1.234,56` partia-se ao meio e valia **R$ 1,23**. Uma banda ilegível **recusa a
    estimativa inteira** e nomeia a entrada — engoli-la paga menos ao professor com a mesma frase
    que um inquilino sem esquema de bónus recebe legitimamente.
  - **limites e buracos são coisas diferentes:** um resultado **abaixo** da banda mais baixa vale
    **zero**, e o bloco diz que é um valor apurado, não uma falta de informação; um resultado
    **num buraco** entre bandas declaradas (89,5 contra 80-89 e 90+) é **INDETERMINADO e nunca
    zero** — pagar zero ali é um número sobre o dinheiro de alguém que as regras não autorizam, e
    promovê-lo à banda de cima também. Mostra as duas vizinhas e não escolhe.
  - **IBOPE não encontrado ⇒ as hipóteses, todas, nenhuma escolhida**, com a frase «RESULTADO
    NÃO ENCONTRADO» à cabeça. A contagem segue a declaração do inquilino (as duas faixas dele
    dão três hipóteses com a linha «Sem bónus»), não um 3 escrito no código. **Dois resultados
    que discordam contam como não encontrado**: escolher um é um bónus inventado a vestir um
    número verdadeiro.
  - **uma disciplina sem horas na folha é NOMEADA e fica fora da soma**, nunca zero — «R$ 0,00»
    lê-se como uma aula que não paga, que é uma afirmação diferente e falsa.

  **O escopo é um guarda e abrir um guarda tem sempre uma vítima possível.** Passou a ser
  possível: o próprio professor perguntar o que recebe pelas próprias aulas. Continua fechado, e
  há gémeo para cada metade: a remuneração de OUTRO professor (recusada a **todos** os papéis,
  supervisão incluída — este é o único read do vertical que não alarga para oversight), as
  contas da instituição, notas fiscais a processar, orçamentos, mensalidades. E a abertura da
  entrada é um *prompt*; o «só do próprio» é *código*.

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

- **`coordinator` — a listagem para de ser desfeita, e a janela por omissão deixa de trazer o
  ano inteiro.** Duas metades de um mesmo resultado: o que o professor lê, e quanto lhe é lido.

  **A FORMA.** A listagem passa a vir agrupada sob um cabeçalho de mês a negrito
  (`**Setembro de 2026**`) com uma linha por aula e **três campos escolhidos**, na ordem em que
  o olho precisa deles: DIA, TURMA, DISCIPLINA — `08/09 · DE_09 · Bancos NoSQL` —, mais o
  estado quando não é o ordinário. O bloco anterior era `Turma: X | Data: Y | Disciplina: Z`
  com todas as colunas não vazias anexadas: um rótulo em cada campo de cada linha, a repetir em
  todas as 33 as palavras que o leitor aprendeu na primeira, e o ano a repetir sob um cabeçalho
  que acabara de o dizer. **A forma não foi inventada aqui — foi devolvida.** Medido nos turnos
  da caixa a 2026-09-06: entregue o bloco liso, o rascunho do executor voltou já agrupado por
  mês; o locutor deitou-o fora e reproduziu o bloco liso, porque o `limits.txt` lhe dizia que a
  saída CRUA da ferramenta É o formato esperado. O modelo estava certo e o prompt venceu-o.
  Renderizar a forma aqui é o que faz a instrução e o resultado serem a mesma coisa. Uma linha
  cuja data não se conseguiu ler mantém a forma rotulada e vai para o fim, sem cabeçalho: a
  leitura nunca esconde o que não consegue datar.

  **A JANELA.** Sem período pedido, a leitura passa a devolver `[HOJE, HOJE + 30 dias]`
  (`DEFAULT_HORIZON_DAYS`, injectável por `CoordinatorService(horizon_days=...)`). A ponta de
  trás já existia; esta é a da frente, e nasce da mesma medição: «traga minhas aulas» respondia
  com 33 aulas a entrar por Junho de 2027. **A ponta da frente cede a qualquer período
  NOMEADO** — um `month`, mesmo distante, e um `discipline`, que é uma consulta por uma coisa
  nomeada («quando é o workshop de abertura?» não pode responder «nada» porque a resposta está
  a dois meses). Um `turma` **não** a larga: estreita DE QUEM, não QUANDO. O **export de
  calendário não a aplica de todo** (`apply_horizon=False`): uma janela que existe para poupar
  rolagem não decide o que entra no calendário de alguém — a ponta de trás, essa, continua a
  valer lá. Cada ponta tem a sua frase de rodapé e **só aparece quando cortou mesmo**: «today
  onward» para a de trás, «the next 30 days» para a da frente, e nenhuma delas conta quantas
  aulas ficaram fora.

- **`coordinator` — uma troca deixa de largar as células que nenhum cabeçalho nomeia.**
  Medido no corpus vivo a 2026-09-07: a aba de agenda do inquilino tem colunas DEPOIS da última
  nomeada, com a célula de cabeçalho **em branco**. Chegam a ser lidas porque o `read_range`
  honra o A1 como *deslocamento de linha* e devolve todas as colunas — mas o `confirm_swap` não
  as conseguia escrever, porque o `_resolve_columns` limitava as colunas de conteúdo ao último
  cabeçalho **não vazio**. A troca trocava disciplina e professor e deixava para trás tudo o que
  passava do cabeçalho: a aula mudava de data, a carga horária e o estado ficavam com a data
  velha. **As duas linhas continuam cheias** — cada uma passa a descrever a aula da outra — por
  isso ninguém vê acontecer.

  **A correcção não nomeia as colunas, de propósito.** Para guardar uma célula é preciso
  transportá-la, não percebê-la; e uma coluna que ninguém nomeou também não pode ser exempta
  (`FIXED_COLUMNS` casa por NOME), portanto o default honesto para uma célula sem nome é o que
  todas as colunas de conteúdo já têm — pertence à aula e viaja com ela. Há gémeo que mede que
  nomear uma coluna e pô-la em `FIXED_COLUMNS` continua a ser o modo de a fixar, e outro que
  mede que uma folha sem colunas extra se comporta exactamente como antes. O `width` só é
  passado pelo caminho de **escrita**: das três chamadas a `_resolve_columns`, uma o faz.

- **`coordinator` — um destino que não serve passa a dizer PORQUÊ, e uma recusa não escreve
  nada.** «No free slot found on 18/07 in the same schedule.» cobria três mundos com uma frase:
  a data não existe na agenda, a data é feriado, a data já tem aula. Agora distingue-os e nomeia
  os rótulos que o inquilino aceita (`FREE_SLOT_LABELS`), que são vocabulário dele e o leitor não
  adivinha. Nomeia o obstáculo, **nunca a pessoa por trás dele** — de quem é a aula que ocupa a
  data é a agenda de outra pessoa, e a regra de acesso não deixa de valer dentro de uma mensagem
  de erro. Toda a validação corre antes do único `store.swap_rows`, e há gémeo que compara a
  **grelha inteira** depois de uma recusa. A diagnose é uma leitura que não pode rebentar: um
  diagnóstico que levanta troca uma frase accionável por um stack trace que ninguém vê.

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
  3. **A janela por omissão ganha a ponta de TRÁS: `[HOJE, ...)`.** As planilhas guardam o ano
     lectivo inteiro e devolvê-lo deixava a escolha ao modelo — foi assim que abril foi lido de
     volta. O passado pede-se: `include_past=True`, ou nomeando um mês **já terminado**, que é o
     mesmo pedido dito de outra maneira. Um mês **em curso** mostra de hoje ao fim do mês. O
     corte é à granularidade do **DIA** (uma aula das 08h ainda é de hoje às 15h) e **nunca
     esconde uma linha sem data**. A frase «a partir de hoje» só aparece quando **houve mesmo
     corte**. *(A ponta da FRENTE — os 30 dias — chegou depois, e tem entrada própria em
     `### Fixed`. Esta linha dizia `[HOJE, ∞)` e deixou de ser verdade nesse dia.)*
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
