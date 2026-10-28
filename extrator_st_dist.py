import re
import unicodedata

from datetime import datetime
from decimal import Decimal

import pdfplumber


# ============================================================
# FUNÇÕES INTERNAS
# ============================================================

def _normalizar_texto(texto):

    texto = str(texto or "").strip()

    texto = unicodedata.normalize(
        "NFKD",
        texto
    )

    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    ).strip()

    return texto


def _normalizar_chave(texto):

    return re.sub(
        r"[^A-Z0-9]",
        "",
        _normalizar_texto(
            texto
        ).upper()
    )


def _filtrar_campos_configurados(
    registro,
    campos_configurados
):

    if not campos_configurados:
        return registro

    campos = {
        _normalizar_chave(campo)
        for campo in campos_configurados
    }

    return {
        chave: valor
        for chave, valor in registro.items()
        if _normalizar_chave(chave) in campos
    }


def _converter_valor(texto):

    texto = str(texto or "").strip()

    if not texto:
        return None

    negativo = False

    if re.search(
        r"(^|\s)-\s*R?\$?",
        texto
    ):
        negativo = True

    texto = (
        texto
        .replace("R$", "")
        .replace(" ", "")
        .replace("–", "-")
        .replace("—", "-")
    )

    texto = re.sub(
        r"[^0-9,.\-]",
        "",
        texto
    )

    if not texto:
        return None

    if not re.fullmatch(
        r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}",
        texto
    ):
        return None

    valor = Decimal(
        texto
        .replace(".", "")
        .replace(",", ".")
    )

    if negativo:
        valor = -abs(valor)

    return valor


def _extrair_conta_texto(texto):

    resultado = re.search(
        r"CONTA\s*:\s*([0-9.\-]+)",
        texto,
        flags=re.IGNORECASE
    )

    if not resultado:
        return None

    conta = resultado.group(1).strip()

    conta = re.sub(
        r"[^0-9A-Za-z\-]",
        "",
        conta
    )

    return conta or None


def _extrair_conta_posicional(pdf):
    """
    Fallback para PDFs Santander em que o número da conta
    aparece visualmente no cabeçalho, mas o extract_text()
    retorna apenas:

        Agência: Conta:

    Procura a palavra Conta na página e lê os dígitos
    posicionados imediatamente à direita dela.
    """

    for pagina in pdf.pages[:2]:

        palavras = pagina.extract_words(
            x_tolerance=1,
            y_tolerance=2,
            keep_blank_chars=False
        ) or []

        for indice, palavra in enumerate(palavras):

            chave = _normalizar_texto(
                palavra.get(
                    "text",
                    ""
                )
            ).upper()

            if not (
                chave == "CONTA"
                or chave == "CONTA:"
                or chave.startswith("CONTA:")
            ):
                continue

            # Primeiro tenta o próprio token:
            # Conta:130059673
            resultado_mesmo_token = re.search(
                r"CONTA\s*:\s*([0-9.\-]+)",
                palavra.get(
                    "text",
                    ""
                ),
                flags=re.IGNORECASE
            )

            if resultado_mesmo_token:
                conta = re.sub(
                    r"[^0-9A-Za-z\-]",
                    "",
                    resultado_mesmo_token.group(1)
                )

                if conta:
                    return conta

            top_conta = palavra.get(
                "top",
                0
            )

            x_conta = palavra.get(
                "x1",
                palavra.get(
                    "x0",
                    0
                )
            )

            candidatos = []

            for proxima in palavras:

                if proxima is palavra:
                    continue

                if abs(
                    proxima.get(
                        "top",
                        0
                    )
                    - top_conta
                ) > 5:
                    continue

                if proxima.get(
                    "x0",
                    0
                ) < x_conta - 2:
                    continue

                texto_proximo = str(
                    proxima.get(
                        "text",
                        ""
                    )
                ).strip()

                if not re.fullmatch(
                    r"[0-9.\-]{4,}",
                    texto_proximo
                ):
                    continue

                candidatos.append(
                    (
                        proxima.get(
                            "x0",
                            0
                        ),
                        texto_proximo
                    )
                )

            if candidatos:

                candidatos.sort(
                    key=lambda item: item[0]
                )

                conta = re.sub(
                    r"[^0-9A-Za-z\-]",
                    "",
                    candidatos[0][1]
                )

                if conta:
                    return conta

    return None


def _eh_linha_saldo(historico):

    chave = _normalizar_texto(
        historico
    ).upper()

    return (
        chave.startswith(
            "SALDO DO DIA"
        )
        or chave.startswith(
            "SALDO ANTERIOR"
        )
        or chave.startswith(
            "SALDO TOTAL"
        )
    )


def _eh_rodape_ou_cabecalho(linha):

    chave = _normalizar_texto(
        linha
    ).upper()

    termos = (
        "INTERNET BANKING EMPRESARIAL",
        "CENTRAL DE ATENDIMENTO",
        "SANTANDER EMPRESARIAL",
        "PESSOAS COM DEFICIENCIA",
        "ATENDIMENTO 24H",
        "REGIOES METROPOLITANAS",
        "DEMAIS LOCALIDADES",
        "OUVIDORIA",
        "SAC -",
        "DATA HISTORICO VALOR",
    )

    return any(
        termo in chave
        for termo in termos
    )


def _extrair_movimento_linha(
    linha,
    conta
):

    linha = re.sub(
        r"\s+",
        " ",
        str(linha or "")
    ).strip()

    if (
        not linha
        or _eh_rodape_ou_cabecalho(
            linha
        )
    ):
        return None

    resultado = re.match(
        r"^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+"
        r"(-\s*)?R\$\s*"
        r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})\s*$",
        linha,
        flags=re.IGNORECASE
    )

    if not resultado:
        return None

    data_movimento = resultado.group(1)
    historico = resultado.group(2).strip()
    sinal_negativo = resultado.group(3)
    valor_texto = resultado.group(4)

    if _eh_linha_saldo(
        historico
    ):
        return None

    valor = _converter_valor(
        (
            "- R$ "
            if sinal_negativo
            else "R$ "
        )
        + valor_texto
    )

    if valor is None:
        return None

    return {
        "DATA": data_movimento,
        "HISTORICO": historico,
        "VALOR": valor,
        "CONTA": conta
    }


def _extrair_texto_paginas(pdf):

    textos = []

    for pagina in pdf.pages:

        texto = pagina.extract_text(
            x_tolerance=2,
            y_tolerance=2
        ) or ""

        textos.append(
            texto
        )

    return textos


def _converter_data(texto):

    try:

        return datetime.strptime(
            str(texto).strip(),
            "%d/%m/%Y"
        ).date()

    except (
        ValueError,
        TypeError
    ):

        return None


def _filtrar_mes_principal(registros):
    """
    Alguns PDFs Santander de fechamento trazem nas primeiras
    linhas movimentos do mês seguinte.

    Exemplo:

        02/03/2026
        27/02/2026
        26/02/2026
        ...
        02/02/2026

    A competência é definida pelo mês com maior quantidade
    de movimentos no arquivo.

    Assim, no exemplo acima, 02/03 é desconsiderado e somente
    fevereiro permanece.
    """

    contagem_meses = {}

    for registro in registros:

        data_registro = _converter_data(
            registro.get(
                "DATA"
            )
        )

        if data_registro is None:
            continue

        chave_mes = (
            data_registro.year,
            data_registro.month
        )

        contagem_meses[
            chave_mes
        ] = (
            contagem_meses.get(
                chave_mes,
                0
            )
            + 1
        )

    if not contagem_meses:
        return registros

    mes_principal = max(
        contagem_meses,
        key=contagem_meses.get
    )

    ano_principal = mes_principal[0]
    numero_mes_principal = mes_principal[1]

    registros_filtrados = []

    for registro in registros:

        data_registro = _converter_data(
            registro.get(
                "DATA"
            )
        )

        if data_registro is None:
            continue

        if (
            data_registro.year
            == ano_principal
            and data_registro.month
            == numero_mes_principal
        ):

            registros_filtrados.append(
                registro
            )

    return registros_filtrados



def _eh_layout_santander_empresas(texto):
    chave = _normalizar_texto(
        texto
    ).upper()

    return (
        "SANTANDER EMPRESAS" in chave
        and "VALOR (R$)" in chave
        and "SALDO (R$)" in chave
    )


def _extrair_movimentos_santander_empresas(
    texto_completo,
    conta
):
    """
    Layout:

        Santander Empresas
        Data Histórico Documento Valor (R$) Saldo (R$)

    Exemplo:

        Transferencia Para Poupanca PARA:
        26/05/2026 16253291 -100,00 0,00
        3706.60.027221-6

        26/05/2026 Ted Recebida 64423614000169 200,00 200,00

    O saldo final da linha não é gravado porque o DE/PARA atual
    do Santander usa Data, Histórico, Valor e Conta.
    """

    registros = []
    historico_pendente = None
    dentro_tabela = False

    linhas = [
        re.sub(
            r"\s+",
            " ",
            str(linha or "")
        ).strip()
        for linha in texto_completo.splitlines()
    ]

    for linha in linhas:

        if not linha:
            continue

        chave = _normalizar_texto(
            linha
        ).upper()

        if (
            "DATA HISTORICO DOCUMENTO VALOR (R$) SALDO (R$)"
            in chave
        ):
            dentro_tabela = True
            historico_pendente = None
            continue

        if not dentro_tabela:
            continue

        # A partir daqui começa a seção informativa de saldo.
        if (
            chave.startswith("SALDO DE CONTAMAX")
            or chave.startswith("SALDO DISPONIVEL")
            or chave == "SALDO"
            or chave.startswith("POSICAO EM:")
            or chave.startswith(
                "ENTENDA A COMPOSICAO"
            )
        ):
            break

        # Continuação visual da conta destino de uma transferência.
        if re.fullmatch(
            r"\d{4}\.\d{2}\.\d{6}-\d",
            linha
        ):
            continue

        if not re.match(
            r"^\d{2}/\d{2}/\d{4}\b",
            linha
        ):
            # Guarda histórico quebrado em uma linha anterior.
            if not _eh_rodape_ou_cabecalho(
                linha
            ):
                historico_pendente = linha

            continue

        data_resultado = re.match(
            r"^(\d{2}/\d{2}/\d{4})\s+(.+)$",
            linha
        )

        if not data_resultado:
            continue

        data_movimento = data_resultado.group(1)
        restante = data_resultado.group(2).strip()

        valores = list(
            re.finditer(
                r"-?\s*\d{1,3}(?:\.\d{3})*,\d{2}|-?\s*\d+,\d{2}",
                restante
            )
        )

        if len(valores) < 2:
            historico_pendente = None
            continue

        # Penúltimo monetário = valor do movimento.
        valor_match = valores[-2]

        valor_texto = valor_match.group(0)
        prefixo = restante[
            :valor_match.start()
        ].strip()

        if historico_pendente:

            historico = historico_pendente.strip()

        else:

            historico = prefixo

            # No layout em uma linha, o último token numérico
            # antes do valor normalmente é o Documento.
            historico = re.sub(
                r"\s+\d{5,}$",
                "",
                historico
            ).strip()

        historico_pendente = None

        if not historico:
            continue

        chave_historico = _normalizar_texto(
            historico
        ).upper()

        # Não é movimento financeiro.
        if (
            chave_historico == "ABERTURA"
            or _eh_linha_saldo(
                historico
            )
        ):
            continue

        valor = _converter_valor(
            valor_texto
        )

        if valor is None:
            continue

        registros.append(
            {
                "DATA": data_movimento,
                "HISTORICO": historico,
                "VALOR": valor,
                "CONTA": conta
            }
        )

    return registros


def _agrupar_linhas_ocr(dados):
    """
    Agrupa tokens do pytesseract pela própria linha reconhecida.
    """

    grupos = {}

    total = len(
        dados.get(
            "text",
            []
        )
    )

    for indice in range(total):

        texto = str(
            dados["text"][indice]
            or ""
        ).strip()

        if not texto:
            continue

        chave = (
            dados["block_num"][indice],
            dados["par_num"][indice],
            dados["line_num"][indice]
        )

        grupos.setdefault(
            chave,
            []
        ).append(
            (
                dados["left"][indice],
                texto
            )
        )

    linhas = []

    for palavras in grupos.values():

        palavras.sort(
            key=lambda item: item[0]
        )

        linha = " ".join(
            texto
            for _, texto in palavras
        )

        linha = re.sub(
            r"\s+",
            " ",
            linha
        ).strip()

        if linha:
            linhas.append(
                linha
            )

    return linhas


def _normalizar_linha_ocr_santander(linha):
    """
    Corrige somente variações pequenas e previsíveis do OCR
    no símbolo monetário, sem alterar o histórico.
    """

    linha = str(
        linha
        or ""
    ).strip()

    linha = re.sub(
        r"\bRS\b",
        "R$",
        linha,
        flags=re.IGNORECASE
    )

    linha = re.sub(
        r"\bR§\b",
        "R$",
        linha,
        flags=re.IGNORECASE
    )

    linha = re.sub(
        r"\s+",
        " ",
        linha
    ).strip()

    return linha


def _extrair_via_ocr(
    pdf
):
    """
    Fallback OCR para PDFs Santander sem camada de texto.

    Usa a própria renderização do pdfplumber e pytesseract.
    Assim não depende de Poppler/pdf2image.
    """

    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)
    except ImportError as erro:
        raise RuntimeError(
            "O PDF Santander não possui camada de texto e "
            "o pacote pytesseract não está instalado."
        ) from erro

    textos_paginas = []
    linhas_ocr = []

    for pagina in pdf.pages:

        imagem = pagina.to_image(
            resolution=220
        ).original

        texto_pagina = pytesseract.image_to_string(
            imagem,
            config="--psm 6"
        ) or ""

        textos_paginas.append(
            texto_pagina
        )

        dados = pytesseract.image_to_data(
            imagem,
            output_type=pytesseract.Output.DICT,
            config="--psm 6"
        )

        linhas_ocr.extend(
            _agrupar_linhas_ocr(
                dados
            )
        )

    return (
        "\n".join(
            textos_paginas
        ),
        linhas_ocr
    )


def _extrair_conta_ocr(
    texto_ocr
):

    texto_normalizado = _normalizar_texto(
        texto_ocr
    )

    resultado = re.search(
        r"CONTA\s*:\s*([0-9.\-]{4,})",
        texto_normalizado,
        flags=re.IGNORECASE
    )

    if not resultado:
        return None

    return re.sub(
        r"[^0-9A-Za-z\-]",
        "",
        resultado.group(1)
    ) or None


def _extrair_movimentos_internet_ocr(
    linhas_ocr,
    conta
):

    registros = []

    for linha in linhas_ocr:

        linha = _normalizar_linha_ocr_santander(
            linha
        )

        if not re.match(
            r"^\d{2}/\d{2}/\d{4}\b",
            linha
        ):
            continue

        # O OCR às vezes lê o sinal como "~" ou "—".
        linha = re.sub(
            r"\s+[~—–]\s+R\$",
            " - R$",
            linha
        )

        registro = _extrair_movimento_linha(
            linha,
            conta
        )

        if registro is None:
            continue

        registros.append(
            registro
        )

    return registros


# ============================================================
# EXTRATOR PÚBLICO
# ============================================================

def extrair_st_dist_pdf(
    caminho,
    campos_configurados=None
):

    """
    Extrator Santander - Distribuidoras.

    Suporta:

        1) Internet Banking Empresarial com camada de texto;
        2) Internet Banking Empresarial em PDF imagem/OCR;
        3) Santander Empresas:
           Data / Histórico / Documento / Valor / Saldo.

    Campos retornados:

        DATA
        HISTORICO
        VALOR
        CONTA

    Regras:

        - linhas de saldo são ignoradas;
        - "Abertura" é ignorada;
        - valor negativo permanece negativo;
        - linhas residuais de outro mês são descartadas,
          mantendo o mês principal do extrato;
        - somente uma função pública inicia com "extrair_".
    """

    registros = []
    conta = None

    with pdfplumber.open(
        str(caminho)
    ) as pdf:

        textos_paginas = _extrair_texto_paginas(
            pdf
        )

        texto_completo = "\n".join(
            textos_paginas
        )

        texto_normalizado = (
            _normalizar_texto(
                texto_completo
            )
            .upper()
        )

        # ====================================================
        # LAYOUT 1 - SANTANDER EMPRESAS
        # ====================================================

        if _eh_layout_santander_empresas(
            texto_completo
        ):

            conta = _extrair_conta_texto(
                texto_completo
            )

            if not conta:

                conta = _extrair_conta_posicional(
                    pdf
                )

            if not conta:

                raise ValueError(
                    "Não foi possível identificar a conta "
                    "no extrato Santander."
                )

            registros = _extrair_movimentos_santander_empresas(
                texto_completo,
                conta
            )

        # ====================================================
        # LAYOUT 2 - INTERNET BANKING COM TEXTO
        # ====================================================

        elif (
            "INTERNET BANKING EMPRESARIAL"
            in texto_normalizado
        ):

            conta = _extrair_conta_texto(
                texto_completo
            )

            if not conta:

                conta = _extrair_conta_posicional(
                    pdf
                )

            if not conta:

                raise ValueError(
                    "Não foi possível identificar a conta "
                    "no extrato Santander."
                )

            for texto_pagina in textos_paginas:

                for linha in texto_pagina.splitlines():

                    registro = _extrair_movimento_linha(
                        linha,
                        conta
                    )

                    if registro is None:
                        continue

                    registros.append(
                        registro
                    )

        # ====================================================
        # LAYOUT 3 - INTERNET BANKING PDF IMAGEM / OCR
        # ====================================================

        else:

            texto_ocr, linhas_ocr = _extrair_via_ocr(
                pdf
            )

            texto_ocr_normalizado = (
                _normalizar_texto(
                    texto_ocr
                )
                .upper()
            )

            if (
                "INTERNET BANKING EMPRESARIAL"
                not in texto_ocr_normalizado
            ):

                raise ValueError(
                    "Layout do Banco Santander não reconhecido."
                )

            conta = _extrair_conta_ocr(
                texto_ocr
            )

            if not conta:

                raise ValueError(
                    "Não foi possível identificar a conta "
                    "no extrato Santander."
                )

            registros = _extrair_movimentos_internet_ocr(
                linhas_ocr,
                conta
            )

    if not registros:

        raise ValueError(
            "Já existem lançamentos na data."
        )

    registros = _filtrar_mes_principal(
        registros
    )

    if not registros:

        raise ValueError(
            "Já existem lançamentos na data."
        )

    return [
        _filtrar_campos_configurados(
            registro,
            campos_configurados
        )
        for registro in registros
    ]
