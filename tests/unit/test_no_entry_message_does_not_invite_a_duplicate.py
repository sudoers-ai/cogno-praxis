"""A frase de reescrita afirmava a ausência e convidava a re-ditar — e isso duplica o livro.

A guarda sabe **uma coisa só**: nenhuma escrita correu NESTE turno. Daí não se segue que o
lançamento não exista. A frase anterior afirmava-o — *"esse lançamento ainda não foi registrado
no sistema"* — e pedia a descrição e o valor *"que eu registro agora"*.

**As duas metades erradas, e a segunda é a que custa.** Um contacto que acredite na primeira
re-dita a despesa, o agente regista, **e o tenant fica com o mesmo lançamento duas vezes** — o
livro é corrompido pela mão do contacto, que fica a achar que fez bem. E acontece **mesmo nos
turnos em que a reescrita está certa**, porque a frase é enlatada.

**A forma segura já existia no mesmo ficheiro:** a `CHECK_TOTALS_MSG` não nega os números,
propõe consultá-los. Esta passa a fazer o mesmo — **o próximo passo é uma LEITURA.**

**A metade virada à MÁQUINA era a mais perigosa.** O `_NO_ENTRY_CRITIQUE` alimenta o laço de
reparo e mandava *"Record the entry for real"*: numa reescrita indevida, isso é a duplicata
escrita por NÓS, sem o contacto sequer participar.

Este ficheiro NÃO reabre a decisão de reescrever — essa é preço aceite, medido e com razão
escrita. Só muda o que a reescrita DIZ e o que MANDA fazer.
"""

from __future__ import annotations

import re

import pytest

from cogno_praxis.bookkeeper.grounding import (CHECK_TOTALS_MSG, NO_ENTRY_MSG,
                                               _EN_BUNDLE as BOOK_EN,
                                               _ES_BUNDLE as BOOK_ES,
                                               _NO_ENTRY_CRITIQUE)

# Afirmações de ausência: o que a guarda NÃO pode saber.
_NEGA_EXISTENCIA = {
    "pt": re.compile(r"n[ãa]o foi registrad|ainda n[ãa]o (?:foi|est[áa])|n[ãa]o consta", re.I),
    "en": re.compile(r"hasn'?t been recorded|has not been recorded|is not recorded", re.I),
    "es": re.compile(r"no fue guardad|todav[íi]a no|no est[áa] registrad", re.I),
}
# Convites a DITAR de novo para escrever (≠ convidar a identificar para procurar).
_CONVIDA_A_ESCREVER = {
    "pt": re.compile(r"registro agora|lan[çc]o agora|eu registro|registro e te", re.I),
    "en": re.compile(r"I'?ll record it|record it now", re.I),
    "es": re.compile(r"lo registro ahora|lo registro y", re.I),
}


@pytest.mark.parametrize("locale,msg", [
    ("pt", NO_ENTRY_MSG), ("en", BOOK_EN.no_entry), ("es", BOOK_ES.no_entry)])
def test_the_message_does_not_ASSERT_the_entry_is_missing(locale, msg):
    """SABOTAGEM: repor *"esse lançamento ainda não foi registrado no sistema"* -> morre.

    A guarda não sabe se o lançamento existe; sabe que não foi escrito neste turno.
    """
    assert not _NEGA_EXISTENCIA[locale].search(msg), (
        f"[{locale}] a frase afirma uma ausência que a guarda não pode conhecer")


@pytest.mark.parametrize("locale,msg", [
    ("pt", NO_ENTRY_MSG), ("en", BOOK_EN.no_entry), ("es", BOOK_ES.no_entry)])
def test_the_message_does_not_INVITE_a_second_write(locale, msg):
    """A metade que produz a duplicata: pedir a descrição *para registar agora*.

    Pedir a descrição para PROCURAR é outra coisa e continua permitido — é o que a frase nova
    faz, e é o que a `CHECK_TOTALS_MSG` ao lado sempre fez.
    """
    assert not _CONVIDA_A_ESCREVER[locale].search(msg), (
        f"[{locale}] a frase convida a re-ditar para escrever — é o caminho da duplicata")


def test_the_message_proposes_a_LOOKUP_like_its_neighbour():
    """CONTROLO POSITIVO. Sem ele, uma frase vazia — ou um `""` — passaria os dois testes de
    ausência acima com louvor. A frase tem de continuar a fazer alguma coisa útil.
    """
    assert re.search(r"consultar|procuro", NO_ENTRY_MSG, re.I)
    assert re.search(r"check|look it up", BOOK_EN.no_entry, re.I)
    assert re.search(r"consultar|busco", BOOK_ES.no_entry, re.I)
    # E a vizinha, que é o molde, continua a ser o molde.
    assert re.search(r"consultar", CHECK_TOTALS_MSG, re.I)


def test_the_CRITIQUE_tells_the_loop_to_read_before_writing():
    """A metade virada à máquina — a mais perigosa, porque não passa por ninguém.

    SABOTAGEM: repor *"Record the entry for real (confirm description and amount)"* -> morre.
    """
    assert re.search(r"do not record it blindly", _NO_ENTRY_CRITIQUE, re.I)
    assert re.search(r"would duplicate", _NO_ENTRY_CRITIQUE, re.I)
    assert re.search(r"call search|get_summary", _NO_ENTRY_CRITIQUE, re.I)
    assert re.search(r"only if the lookup shows it is missing", _NO_ENTRY_CRITIQUE, re.I)


def test_the_message_is_still_the_one_the_rule_returns():
    """A ligação, para o conserto não nascer inerte: a regra continua a devolver ESTA frase.

    SABOTAGEM: apontar o bundle `pt` para outra mensagem -> morre.
    """
    from cogno_praxis.bookkeeper.grounding import ground_reply
    v = ground_reply("Registrado! R$ 150,00 da Maria.", tools=[], had_executor=True, locale="pt")
    assert v is not None and v.rule == "fabricated_entry"
    assert v.message == NO_ENTRY_MSG
    assert v.critique == _NO_ENTRY_CRITIQUE
