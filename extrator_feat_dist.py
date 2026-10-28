import re
import unicodedata
from pathlib import Path
from decimal import Decimal, InvalidOperation

import pdfplumber


_RE_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_RE_VALOR = re.compile(r"^[\d.]+,\d{2}$")


def _normalizar_chave(texto):
    texto = str(texto or "").strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", texto)


def _filtrar_campos_configurados(registro, campos_configurados):
    if not campos_configurados:
        return registro

    permitidos = {_normalizar_chave(c) for c in campos_configurados}
    return {k: v for k, v in registro.items() if k in permitidos}


def _valor_brasileiro(texto):
    try:
        return Decimal(
            str(texto).replace("R$", "").strip().replace(".", "").replace(",", ".")
        )
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"Valor inválido no extrato Featbank: {texto!r}") from exc


def _registro(data, descricao, valor, conta, campos_configurados):
    registro = {
        _normalizar_chave("Data"): data,
        _normalizar_chave("Descrição"): " ".join(str(descricao).split()).strip(),
        _normalizar_chave("Valor"): valor,
        _normalizar_chave("Conta"): conta,
    }
    return _filtrar_campos_configurados(registro, campos_configurados)


def _texto_pdf(pdf):
    textos = []
    for pagina in pdf.pages:
        texto = pagina.extract_text() or ""
        if texto.strip():
            textos.append(texto)
    return "\n".join(textos)


def _extrair_conta(texto, caminho_pdf):
    match = re.search(r"\bConta:\s*([0-9][0-9.\-]*)", texto, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Segurança para relatórios onde "CONTA CORRENTE:" aparece antes do número.
    match = re.search(
        r"\bCONTA\s+CORRENTE:\s*(?:SITUAÇÃO:\s*\S+\s*)?([0-9][0-9.\-]*)",
        texto,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    raise ValueError(f"Conta não encontrada no conteúdo do PDF Featbank: {caminho_pdf}")


def _internet_banking_sem_movimento(texto):
    normalizado = unicodedata.normalize("NFKD", texto)
    normalizado = "".join(c for c in normalizado if not unicodedata.combining(c))
    normalizado = re.sub(r"\s+", " ", normalizado).lower()
    return bool(
        re.search(
            r"nao\s+existe.*?resultados.*?serem.*?exibidos",
            normalizado,
            re.DOTALL,
        )
    )


def _registro_internet_banking(texto, conta, campos_configurados, caminho_pdf):
    # Usa o fim do período exibido como data do saldo.
    periodo = re.search(
        r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})",
        texto,
    )
    if not periodo:
        raise ValueError(
            f"Período não encontrado no Internet Banking Featbank: {caminho_pdf}"
        )
    data = periodo.group(2)

    # No print do Internet Banking o saldo fica próximo de Agência/Conta.
    # Evita capturar datas/horas e procura valor monetário com R$.
    saldos = re.findall(r"R\$\s*([\d.]+,\d{2})", texto)
    if not saldos:
        raise ValueError(
            f"Saldo não encontrado no Internet Banking Featbank: {caminho_pdf}"
        )

    saldo = _valor_brasileiro(saldos[-1])

    return [
        _registro(
            data=data,
            descricao="INTERNET BANKING",
            valor=saldo,
            conta=conta,
            campos_configurados=campos_configurados,
        )
    ]


def _blocos_por_coordenadas(pdf):
    """
    Reconstrói o layout exportado do Featbank pela posição visual das colunas.

    A Data fica na coluna esquerda. Cada nova data inicia um lançamento.
    O bloco continua até a próxima data, inclusive atravessando páginas.
    Isso cobre tanto ATHENA/EZ PAY (linhas simples) quanto BCAG (quebras).
    """
    blocos = []
    atual = None

    for pagina in pdf.pages:
        palavras = pagina.extract_words(
            x_tolerance=2,
            y_tolerance=2,
            keep_blank_chars=False,
        )

        for palavra in palavras:
            texto = palavra["text"].strip()
            x0 = float(palavra["x0"])

            # Datas de movimento aparecem na primeira coluna da tabela.
            # Datas do cabeçalho ficam bem mais à direita.
            if _RE_DATA.fullmatch(texto) and x0 < 110:
                if atual:
                    blocos.append(atual)
                atual = {"data": texto, "palavras": []}
                continue

            if atual is not None:
                atual["palavras"].append(palavra)

    if atual:
        blocos.append(atual)

    return blocos


def _extrair_layout_exportado(pdf, conta, campos_configurados):
    movimentos = []

    for bloco in _blocos_por_coordenadas(pdf):
        palavras = bloco["palavras"]
        if not palavras:
            continue

        textos = [p["text"].strip() for p in palavras]

        # Fluxo é a referência principal do lançamento.
        indice_fluxo = None
        fluxo = None
        for i, t in enumerate(textos):
            tn = unicodedata.normalize("NFKD", t)
            tn = "".join(c for c in tn if not unicodedata.combining(c)).lower()
            if tn in ("entrada", "saida", "saldo"):
                indice_fluxo = i
                fluxo = tn
                break

        if indice_fluxo is None:
            continue

        # Descrição vem da coluna visual entre Data e Fluxo.
        # Isso mantém descrições quebradas em várias linhas/páginas.
        descricao_partes = []
        for p in palavras:
            x0 = float(p["x0"])
            t = p["text"].strip()
            if 110 <= x0 < 380:
                tn = unicodedata.normalize("NFKD", t)
                tn = "".join(c for c in tn if not unicodedata.combining(c)).lower()
                if (
                    tn not in ("entrada", "saida", "saldo")
                    and not re.fullmatch(r"\d{2}:\d{2}", t)
                ):
                    descricao_partes.append(t)

        descricao = " ".join(descricao_partes).strip()

        # Valor fica na coluna da direita. Usa o último valor monetário
        # encontrado no bloco para tolerar R$ e número em linhas diferentes.
        candidatos_valor = []
        for p in palavras:
            t = p["text"].strip()
            if _RE_VALOR.fullmatch(t) and float(p["x0"]) >= 450:
                candidatos_valor.append(t)

        # Fallback para pequenas variações de coordenada.
        if not candidatos_valor:
            candidatos_valor = [t for t in textos if _RE_VALOR.fullmatch(t)]

        if not candidatos_valor:
            continue

        valor = _valor_brasileiro(candidatos_valor[-1])

        # Saldo do dia não é movimento.
        if fluxo == "saldo":
            continue

        if fluxo == "entrada":
            valor = abs(valor)
        elif fluxo == "saida":
            valor = -abs(valor)
        else:
            continue

        if not descricao:
            continue

        movimentos.append(
            _registro(
                data=bloco["data"],
                descricao=descricao,
                valor=valor,
                conta=conta,
                campos_configurados=campos_configurados,
            )
        )

    return movimentos


def _extrair_layout_periodico(texto, conta, campos_configurados):
    movimentos = []

    padrao = re.compile(
        r"^(?P<data>\d{2}/\d{2}/\d{4})\s+"
        r"(?P<descricao>.+?)\s+"
        r"(?:(?P<doc>\d{6,})\s+)?"
        r"(?P<valor>[\d.]+,\d{2})\s+"
        r"(?P<dc>[DC])\s*$",
        re.IGNORECASE,
    )

    for linha in texto.splitlines():
        linha = " ".join(linha.split()).strip()
        match = padrao.match(linha)
        if not match:
            continue

        descricao = match.group("descricao").strip()

        # Linhas de saldo não são movimentos.
        if descricao.upper().startswith("SALDO "):
            continue

        valor = _valor_brasileiro(match.group("valor"))
        dc = match.group("dc").upper()

        if dc == "C":
            valor = abs(valor)
        elif dc == "D":
            valor = -abs(valor)
        else:
            continue

        movimentos.append(
            _registro(
                data=match.group("data"),
                descricao=descricao,
                valor=valor,
                conta=conta,
                campos_configurados=campos_configurados,
            )
        )

    return movimentos


def extrair_feat_dist(caminho_pdf, campos_configurados=None):
    with pdfplumber.open(caminho_pdf) as pdf:
        texto = _texto_pdf(pdf)

        if not texto.strip():
            raise ValueError(f"PDF Featbank sem texto extraível: {caminho_pdf}")

        conta = _extrair_conta(texto, caminho_pdf)

        # Internet Banking sem movimentos:
        # retorna somente o saldo, com histórico fixo.
        if _internet_banking_sem_movimento(texto):
            return _registro_internet_banking(
                texto,
                conta,
                campos_configurados,
                caminho_pdf,
            )

        texto_normalizado = unicodedata.normalize("NFKD", texto)
        texto_normalizado = "".join(
            c for c in texto_normalizado if not unicodedata.combining(c)
        ).upper()

        if "REL. DE EXTRATO PERIODICO PARA CORRENTISTA" in texto_normalizado:
            movimentos = _extrair_layout_periodico(
                texto,
                conta,
                campos_configurados,
            )
        else:
            movimentos = _extrair_layout_exportado(
                pdf,
                conta,
                campos_configurados,
            )

    if not movimentos:
        # DIRECIONAL.pdf é um arquivo Featbank conhecido que não pertence
        # aos layouts de movimentos suportados. Deve ser ignorado sem
        # interromper a fila. DIRECIONAL TRR.pdf continua sendo processado.
        nome_arquivo = getattr(caminho_pdf, "name", None)
        if nome_arquivo is None:
            nome_arquivo = Path(str(caminho_pdf)).name

        if str(nome_arquivo).strip().upper() == "DIRECIONAL.PDF":
            return []

        raise ValueError(
            f"Nenhum movimento financeiro válido encontrado no PDF Featbank: "
            f"{caminho_pdf}"
        )

    return movimentos