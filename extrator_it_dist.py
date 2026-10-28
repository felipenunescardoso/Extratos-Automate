import re
import os
import unicodedata
from datetime import date
from decimal import Decimal
from pathlib import Path

import pdfplumber


# ============================================================
# FUNÇÕES INTERNAS
# ============================================================

MESES = {
    "JAN": 1,
    "FEV": 2,
    "MAR": 3,
    "ABR": 4,
    "MAI": 5,
    "JUN": 6,
    "JUL": 7,
    "AGO": 8,
    "SET": 9,
    "OUT": 10,
    "NOV": 11,
    "DEZ": 12,
}


def _normalizar_texto(texto):
    texto = str(texto or "").strip().upper()

    texto = unicodedata.normalize(
        "NFKD",
        texto
    )

    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    texto = texto.replace("#", "")

    texto = re.sub(
        r"\s+",
        " ",
        texto
    ).strip()

    return texto


def _normalizar_chave(texto):
    texto = _normalizar_texto(texto)

    return re.sub(
        r"[^A-Z0-9]",
        "",
        texto
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

    texto = (
        texto
        .replace("R$", "")
        .replace(" ", "")
        .replace("—", "-")
        .replace("–", "-")
    )

    if not re.fullmatch(
        r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}",
        texto
    ):
        return None

    texto = (
        texto
        .replace(".", "")
        .replace(",", ".")
    )

    return Decimal(texto)


def _extrair_periodo(texto):
    """
    Aceita os dois formatos Itaú observados:

        lançamentos período: 01/01/2026 até 31/01/2026
        Lançamentos do período: 01/02/2026 até 28/02/2026
    """
    resultado = re.search(
        r"LAN[ÇC]AMENTOS\s+(?:DO\s+)?PER[IÍ]ODO\s*:\s*"
        r"(\d{2}/\d{2}/\d{4})\s+AT[EÉ]\s+"
        r"(\d{2}/\d{2}/\d{4})",
        texto,
        flags=re.IGNORECASE
    )

    if not resultado:
        return None, None

    def converter(valor):
        dia, mes, ano = map(
            int,
            valor.split("/")
        )

        return date(
            ano,
            mes,
            dia
        )

    return (
        converter(resultado.group(1)),
        converter(resultado.group(2))
    )


def _extrair_conta(texto):
    """
    Trata os layouts recebidos:

        agência conta corrente
        CNPJ 0367 99550-1

    e:

        Agência 0367 Conta 0098202-2
        Agência 0444 Conta 0098519-6
    """
    resultado = re.search(
        r"\bAG[ÊE]NCIA\s+\d+\s+CONTA(?:\s+CORRENTE)?\s+"
        r"(\d{4,}-\d+)\b",
        texto,
        flags=re.IGNORECASE
    )

    if resultado:
        return resultado.group(1).strip()

    linhas = [
        re.sub(
            r"\s+",
            " ",
            linha
        ).strip()
        for linha in texto.splitlines()
        if linha.strip()
    ]

    for indice, linha in enumerate(linhas):
        linha_normalizada = _normalizar_texto(
            linha
        )

        if (
            "AGENCIA" not in linha_normalizada
            or "CONTA CORRENTE" not in linha_normalizada
        ):
            continue

        for linha_teste in linhas[
            indice + 1:indice + 3
        ]:
            candidatos = re.findall(
                r"\b\d{4,}-\d+\b",
                linha_teste
            )

            if candidatos:
                return candidatos[-1]

    return None


def _ano_da_data(
    mes,
    inicio_periodo
):
    if inicio_periodo is None:
        return None

    candidatos = [
        inicio_periodo.year - 1,
        inicio_periodo.year,
        inicio_periodo.year + 1
    ]

    referencia = inicio_periodo

    def distancia(ano):
        try:
            candidato = date(
                ano,
                mes,
                15
            )
        except ValueError:
            return 10**9

        return abs(
            (candidato - referencia).days
        )

    return min(
        candidatos,
        key=distancia
    )


def _eh_linha_ignorada(descricao):
    descricao = _normalizar_texto(descricao)

    if not descricao:
        return True

    prefixos = (
        "SALDO ANTERIOR",
        "SALDO TOTAL DISPONIVEL DIA",
        "SALDO TOTAL DISPONVEL DIA",
        "SALDO DISPONIVEL",
        "SALDO DA CONTA CORRENTE",
    )

    return descricao.startswith(prefixos)


def _separar_valores_descricao(restante):
    valores_encontrados = list(
        re.finditer(
            r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}",
            restante
        )
    )

    if not valores_encontrados:
        return None, None, restante.strip()

    # No Itaú:
    #   1 valor -> valor do movimento
    #   2 valores -> valor do movimento + saldo
    valor = _converter_valor(
        valores_encontrados[-2].group(0)
        if len(valores_encontrados) >= 2
        else valores_encontrados[-1].group(0)
    )

    saldo = (
        _converter_valor(
            valores_encontrados[-1].group(0)
        )
        if len(valores_encontrados) >= 2
        else None
    )

    primeiro_valor = (
        valores_encontrados[-2]
        if len(valores_encontrados) >= 2
        else valores_encontrados[-1]
    )

    descricao = restante[
        :primeiro_valor.start()
    ].strip()

    return valor, saldo, descricao


def _extrair_movimento_linha(
    linha,
    inicio_periodo,
    conta
):
    """
    Trata:

        06 / jan TED ... 319,70
        03 / fev TAR ... -79,00

    e:

        02/04/2026 TAR MANUT CONTA 03/26 -87,00
        15/04/2026 RECEBIMENTOS ... 212.309,90
    """

    # --------------------------------------------------------
    # LAYOUT COM DATA COMPLETA DD/MM/YYYY
    # --------------------------------------------------------
    resultado_data_completa = re.match(
        r"^\s*(\d{2}/\d{2}/\d{4})\s+(.+?)\s*$",
        linha
    )

    if resultado_data_completa:
        data_texto = resultado_data_completa.group(1)
        restante = resultado_data_completa.group(2).strip()

        valor, saldo, descricao = (
            _separar_valores_descricao(
                restante
            )
        )

        if valor is None:
            return None

        if _eh_linha_ignorada(
            descricao
        ):
            return None

        dia, mes, ano = map(
            int,
            data_texto.split("/")
        )

        try:
            data_movimento = date(
                ano,
                mes,
                dia
            )
        except ValueError:
            return None

        return {
            "DATA": data_movimento.strftime(
                "%d/%m/%Y"
            ),
            "LANCAMENTO": descricao,
            "VALOR": valor,
            "SALDO": saldo,
            "CONTA": conta
        }

    # --------------------------------------------------------
    # LAYOUT ANTIGO DD / jan
    # --------------------------------------------------------
    resultado = re.match(
        r"^\s*(\d{1,2})\s*/\s*"
        r"([A-Za-zÀ-ÿ]{3,})\s+"
        r"(.+?)\s*$",
        linha
    )

    if not resultado:
        return None

    dia = int(
        resultado.group(1)
    )

    mes_texto = _normalizar_texto(
        resultado.group(2)
    )[:3]

    mes = MESES.get(
        mes_texto
    )

    if mes is None:
        return None

    restante = resultado.group(3).strip()

    valor, saldo, descricao = (
        _separar_valores_descricao(
            restante
        )
    )

    if valor is None:
        return None

    if _eh_linha_ignorada(
        descricao
    ):
        return None

    ano = _ano_da_data(
        mes,
        inicio_periodo
    )

    if ano is None:
        return None

    try:
        data_movimento = date(
            ano,
            mes,
            dia
        )
    except ValueError:
        return None

    return {
        "DATA": data_movimento.strftime(
            "%d/%m/%Y"
        ),
        "LANCAMENTO": descricao,
        "VALOR": valor,
        "SALDO": saldo,
        "CONTA": conta
    }


def _configurar_tesseract():
    import pytesseract

    caminhos = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        str(
            Path(
                os.getenv(
                    "LOCALAPPDATA",
                    ""
                )
            )
            / "Programs"
            / "Tesseract-OCR"
            / "tesseract.exe"
        )
    ]

    for caminho in caminhos:
        if caminho and Path(caminho).exists():
            pytesseract.pytesseract.tesseract_cmd = (
                caminho
            )
            break

    return pytesseract


def _ocr_pdf(caminho):
    """
    OCR usado somente quando o PDF não possui camada de texto.
    Caso observado: Itaú BBA / MATERA.
    """
    import fitz
    from PIL import Image

    pytesseract = _configurar_tesseract()

    textos = []

    documento = fitz.open(
        str(caminho)
    )

    try:
        for pagina in documento:
            pix = pagina.get_pixmap(
                matrix=fitz.Matrix(
                    2.5,
                    2.5
                ),
                alpha=False
            )

            imagem = Image.frombytes(
                "RGB",
                [pix.width, pix.height],
                pix.samples
            )

            try:
                texto = pytesseract.image_to_string(
                    imagem,
                    lang="por",
                    config="--psm 6"
                )
            except Exception:
                texto = pytesseract.image_to_string(
                    imagem,
                    lang="eng",
                    config="--psm 6"
                )

            textos.append(
                texto or ""
            )
    finally:
        documento.close()

    return textos


def _ler_paginas(caminho):
    with pdfplumber.open(
        caminho
    ) as pdf:

        textos_paginas = [
            pagina.extract_text(
                x_tolerance=2,
                y_tolerance=2
            ) or ""
            for pagina in pdf.pages
        ]

    if any(
        texto.strip()
        for texto in textos_paginas
    ):
        return textos_paginas

    return _ocr_pdf(
        caminho
    )


# ============================================================
# EXTRATOR PÚBLICO
# ============================================================

def extrair_it_dist_pdf(
    caminho,
    campos_configurados=None
):
    """
    Extrator Itaú - Distribuidoras.

    Layouts tratados:
        1) Itaú Empresas antigo:
           DD / jan + lançamento + valor

        2) Itaú Empresas/BBA novo:
           DD/MM/YYYY + lançamento + razão social +
           CNPJ/CPF + valor + saldo

        3) PDF imagem/scaneado:
           OCR automático.

    Campos retornados:
        DATA
        LANCAMENTO
        VALOR
        SALDO
        CONTA
    """

    caminho = str(caminho)

    textos_paginas = _ler_paginas(
        caminho
    )

    texto_completo = "\n".join(
        textos_paginas
    )

    texto_normalizado = _normalizar_texto(
        texto_completo
    )

    if (
        "ITAU" not in texto_normalizado
        and "ITAUEMPRESAS" not in texto_normalizado
        and "ITAU BBA" not in texto_normalizado
    ):
        raise ValueError(
            "Layout do Banco Itaú não reconhecido."
        )

    inicio_periodo, fim_periodo = (
        _extrair_periodo(
            texto_completo
        )
    )

    if inicio_periodo is None:
        raise ValueError(
            "Não foi possível identificar o período "
            "no extrato Itaú."
        )

    conta = _extrair_conta(
        texto_completo
    )

    if not conta:
        raise ValueError(
            "Não foi possível identificar a conta "
            "no extrato Itaú."
        )

    registros = []

    for texto_pagina in textos_paginas:

        linhas = [
            re.sub(
                r"\s+",
                " ",
                linha
            ).strip()
            for linha in texto_pagina.splitlines()
            if linha.strip()
        ]

        for linha in linhas:

            registro = _extrair_movimento_linha(
                linha,
                inicio_periodo,
                conta
            )

            if registro is None:
                continue

            registros.append(
                _filtrar_campos_configurados(
                    registro,
                    campos_configurados
                )
            )

    if not registros:
        raise ValueError(
            "Já existem lançamentos na data."
        )

    return registros