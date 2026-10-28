import re
import unicodedata
from decimal import Decimal

import pdfplumber


def normalizar_chave(texto):
    texto = str(texto or "").strip().upper()
    texto = unicodedata.normalize("NFKD", texto)

    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    return re.sub(r"[^A-Z0-9]", "", texto)


def converter_valor_aden(valor):
    if valor is None:
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    resultado = re.search(
        r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}",
        texto
    )

    if not resultado:
        return None

    numero = (
        resultado.group(0)
        .replace(".", "")
        .replace(",", ".")
    )

    return Decimal(numero)


def localizar_conta_aden(pdf):
    """
    Exemplo:
        Extrato de Agência: 8 | Conta: 72885 | CNPJ: ...
    """

    padrao = r"\bConta\s*:\s*([0-9A-Za-z.-]+)"

    for pagina in pdf.pages[:2]:
        texto = pagina.extract_text() or ""
        texto = re.sub(r"\s+", " ", texto)

        resultado = re.search(
            padrao,
            texto,
            flags=re.IGNORECASE
        )

        if resultado:
            return resultado.group(1).strip()

    return None


def agrupar_palavras_por_linha(
    palavras,
    tolerancia=3
):
    linhas = []

    for palavra in sorted(
        palavras,
        key=lambda item: (
            round(item["top"], 1),
            item["x0"]
        )
    ):
        adicionada = False

        for linha in linhas:
            if abs(
                linha["top"] - palavra["top"]
            ) <= tolerancia:

                linha["palavras"].append(
                    palavra
                )

                linha["top"] = (
                    linha["top"]
                    + palavra["top"]
                ) / 2

                adicionada = True
                break

        if not adicionada:
            linhas.append({
                "top": palavra["top"],
                "palavras": [palavra]
            })

    for linha in linhas:
        linha["palavras"] = sorted(
            linha["palavras"],
            key=lambda item: item["x0"]
        )

    return sorted(
        linhas,
        key=lambda item: item["top"]
    )


def texto_intervalo(
    palavras,
    x_inicio,
    x_fim
):
    return " ".join(
        palavra["text"]
        for palavra in palavras
        if (
            palavra["x0"] >= x_inicio
            and palavra["x0"] < x_fim
        )
    ).strip()


def localizar_data_linha(palavras):
    """
    No layout Aden a data fica na primeira coluna,
    aproximadamente até x=115.
    """

    texto = texto_intervalo(
        palavras,
        0,
        115
    )

    resultado = re.search(
        r"\b\d{2}/\d{2}/\d{4}\b",
        texto
    )

    if resultado:
        return resultado.group(0)

    return None


def filtrar_campos_configurados(
    registro,
    campos_configurados
):
    if not campos_configurados:
        return registro

    campos_normalizados = {
        normalizar_chave(campo)
        for campo in campos_configurados
    }

    return {
        chave: valor
        for chave, valor in registro.items()
        if chave in campos_normalizados
    }


def detectar_colunas_aden(pdf):
    """
    Detecta as posições X do cabeçalho:
        Data | Descrição | Fluxo | Tipo | Valor

    Isso evita depender de posições fixas, pois o Aden
    muda a largura das colunas entre relatórios.
    """

    for pagina in pdf.pages:
        palavras = pagina.extract_words(
            use_text_flow=False,
            keep_blank_chars=False
        )

        posicoes = {}

        for palavra in palavras:
            chave = normalizar_chave(
                palavra["text"]
            )

            if chave == "DATA":
                posicoes["data"] = palavra["x0"]

            elif chave == "DESCRICAO":
                posicoes["descricao"] = palavra["x0"]

            elif chave == "FLUXO":
                posicoes["fluxo"] = palavra["x0"]

            elif chave == "TIPO":
                posicoes["tipo"] = palavra["x0"]

            elif chave == "VALOR":
                posicoes["valor"] = palavra["x0"]

        if all(
            chave in posicoes
            for chave in (
                "data",
                "descricao",
                "fluxo",
                "tipo",
                "valor"
            )
        ):
            return {
                "descricao_inicio": max(
                    105,
                    posicoes["descricao"] - 15
                ),
                "fluxo_inicio": max(
                    posicoes["descricao"] + 20,
                    posicoes["fluxo"] - 15
                ),
                "tipo_inicio": max(
                    posicoes["fluxo"] + 20,
                    posicoes["tipo"] - 15
                ),
                "valor_inicio": max(
                    posicoes["tipo"] + 20,
                    posicoes["valor"] - 15
                ),
                "valor_fim": 570
            }

    # Fallback para o layout original.
    return {
        "descricao_inicio": 110,
        "fluxo_inicio": 405,
        "tipo_inicio": 450,
        "valor_inicio": 488,
        "valor_fim": 560
    }


def montar_registro_aden(
    bloco_palavras,
    data_movimento,
    conta,
    colunas
):
    """
    Colunas visuais do PDF:
        Data        ~ x 64
        Descrição   ~ x 120
        Fluxo       ~ x 411
        Tipo        ~ x 451
        Valor       ~ x 492

    O bloco pode ocupar 2 ou 3 linhas físicas.
    """

    descricao_partes = []
    fluxo_partes = []
    tipo_partes = []
    valor_partes = []

    for palavras_linha in bloco_palavras:

        descricao = texto_intervalo(
            palavras_linha,
            colunas["descricao_inicio"],
            colunas["fluxo_inicio"]
        )

        fluxo = texto_intervalo(
            palavras_linha,
            colunas["fluxo_inicio"],
            colunas["tipo_inicio"]
        )

        tipo = texto_intervalo(
            palavras_linha,
            colunas["tipo_inicio"],
            colunas["valor_inicio"]
        )

        valor = texto_intervalo(
            palavras_linha,
            colunas["valor_inicio"],
            colunas["valor_fim"]
        )

        if descricao:
            descricao_partes.append(descricao)

        if fluxo:
            fluxo_partes.append(fluxo)

        if tipo:
            tipo_partes.append(tipo)

        if valor:
            valor_partes.append(valor)

    descricao = " ".join(descricao_partes).strip()
    fluxo = " ".join(fluxo_partes).strip()
    tipo = " ".join(tipo_partes).strip()
    valor_texto = " ".join(valor_partes).strip()

    chave_descricao = normalizar_chave(descricao)
    chave_fluxo = normalizar_chave(fluxo)
    chave_tipo = normalizar_chave(tipo)

    # Linhas de saldo diário não são movimentações.
    if (
        "SALDODODIA" in chave_descricao
        or "SALDOATUAL" in chave_descricao
        or chave_fluxo.startswith("SALDO")
        or chave_tipo.startswith("SALDO")
    ):
        return None

    valor = converter_valor_aden(valor_texto)

    if valor is None:
        return None

    # O sinal vem da coluna Fluxo.
    if chave_fluxo == "SAIDA":
        valor = -abs(valor)
    elif chave_fluxo == "ENTRADA":
        valor = abs(valor)
    else:
        # Sem Entrada/Saída não consideramos uma movimentação válida.
        return None

    # Remove eventual lixo estrutural que possa ter entrado na descrição.
    descricao = re.sub(
        r"\s+",
        " ",
        descricao
    ).strip()

    return {
        normalizar_chave("Data"): data_movimento,
        normalizar_chave("Descrição"): descricao or None,
        normalizar_chave("Fluxo"): fluxo or None,
        normalizar_chave("Tipo"): tipo or None,
        normalizar_chave("Valor"): valor,
        normalizar_chave("Conta"): conta
    }



def processar_aden_via_ocr(
    caminho,
    campos_configurados=None
):
    """
    Fallback para PDFs Aden sem camada de texto.

    Só é chamado quando o pdfplumber não encontra palavras no PDF.

    Dependências:
        pip install pymupdf pytesseract pillow

    Também é necessário ter o Tesseract OCR instalado no Windows
    e disponível no PATH.
    """

    try:
        import pymupdf
        import pytesseract
        from PIL import Image
        import io
        import os
    except ImportError as erro:
        raise RuntimeError(
            "PDF Aden sem camada de texto. "
            "Instale o fallback OCR com: "
            "pip install pymupdf pytesseract pillow"
        ) from erro

    # Tenta localizar automaticamente o Tesseract no Windows,
    # mesmo quando ele não foi adicionado ao PATH.
    caminhos_tesseract = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(
            r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"
        )
    ]

    for executavel in caminhos_tesseract:
        if os.path.exists(executavel):
            pytesseract.pytesseract.tesseract_cmd = executavel
            break

    documento = pymupdf.open(caminho)

    registros = []
    conta = None

    try:
        for pagina in documento:
            pixmap = pagina.get_pixmap(
                matrix=pymupdf.Matrix(3, 3),
                alpha=False
            )

            imagem = Image.open(
                io.BytesIO(
                    pixmap.tobytes("png")
                )
            )

            try:
                texto_pagina = pytesseract.image_to_string(
                    imagem,
                    lang="por",
                    config="--psm 6"
                )
            except pytesseract.TesseractNotFoundError as erro:
                raise RuntimeError(
                    "Tesseract OCR não encontrado no Windows. "
                    "Instale o Tesseract OCR. O extrator também procura "
                    "automaticamente em C:\\Program Files\\Tesseract-OCR\\tesseract.exe."
                ) from erro

            if conta is None:
                resultado_conta = re.search(
                    r"\bConta\s*:\s*([0-9A-Za-z.-]+)",
                    texto_pagina,
                    flags=re.IGNORECASE
                )

                if resultado_conta:
                    conta = resultado_conta.group(1).strip()

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
                resultado_data = re.match(
                    r"^(\d{2}/\d{2}/\d{4})\s+"
                    r"\d{2}:\d{2}\s+"
                    r"(.+)$",
                    linha
                )

                if not resultado_data:
                    continue

                data_movimento = resultado_data.group(1)
                restante = resultado_data.group(2).strip()

                chave_restante = normalizar_chave(
                    restante
                )

                # Saldo diário / saldo atual não são movimentos.
                if (
                    "SALDODODIA" in chave_restante
                    or "SALDOATUAL" in chave_restante
                ):
                    continue

                resultado_valor = re.search(
                    r"R\$\s*"
                    r"(-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2})"
                    r"\s*$",
                    restante,
                    flags=re.IGNORECASE
                )

                if not resultado_valor:
                    continue

                valor_texto = resultado_valor.group(1)

                antes_valor = restante[
                    :resultado_valor.start()
                ].strip()

                resultado_fluxo = re.search(
                    r"\b(Entrada|Sa[ií]da)\b",
                    antes_valor,
                    flags=re.IGNORECASE
                )

                if not resultado_fluxo:
                    continue

                descricao = antes_valor[
                    :resultado_fluxo.start()
                ].strip()

                fluxo = resultado_fluxo.group(1).strip()

                tipo = antes_valor[
                    resultado_fluxo.end():
                ].strip()

                valor = converter_valor_aden(
                    valor_texto
                )

                if valor is None:
                    continue

                chave_fluxo = normalizar_chave(
                    fluxo
                )

                if chave_fluxo == "SAIDA":
                    valor = -abs(valor)

                elif chave_fluxo == "ENTRADA":
                    valor = abs(valor)

                else:
                    continue

                registro = {
                    normalizar_chave("Data"): data_movimento,
                    normalizar_chave("Descrição"): descricao or None,
                    normalizar_chave("Fluxo"): fluxo or None,
                    normalizar_chave("Tipo"): tipo or None,
                    normalizar_chave("Valor"): valor,
                    normalizar_chave("Conta"): conta
                }

                registro = filtrar_campos_configurados(
                    registro,
                    campos_configurados
                )

                registros.append(
                    registro
                )

    finally:
        documento.close()

    return registros


def extrair_aden_dist_pdf(
    caminho,
    campos_configurados=None
):
    """
    Extrator Aden - Distribuidoras.

    Layout:
        Data | Descrição | Fluxo | Tipo | Valor

    Regras:
        Entrada -> Valor positivo
        Saída   -> Valor negativo
        Saldo Do dia / Fluxo Saldo -> ignorado
        Conta capturada no cabeçalho do PDF
        Suporta descrições quebradas em várias linhas
    """

    registros = []

    with pdfplumber.open(caminho) as pdf:

        total_palavras = 0

        for pagina in pdf.pages:
            total_palavras += len(
                pagina.extract_words(
                    use_text_flow=False,
                    keep_blank_chars=False
                )
            )

        # PDF imagem / digitalizado:
        # mantém a lógica normal intacta e só usa OCR
        # quando não existe nenhuma palavra extraível.
        if total_palavras == 0:
            return processar_aden_via_ocr(
                caminho,
                campos_configurados
            )

        conta = localizar_conta_aden(pdf)
        colunas = detectar_colunas_aden(pdf)

        bloco_data = None
        bloco_linhas = []

        def finalizar_bloco():
            nonlocal bloco_data
            nonlocal bloco_linhas

            if not bloco_data or not bloco_linhas:
                bloco_data = None
                bloco_linhas = []
                return

            registro = montar_registro_aden(
                bloco_linhas,
                bloco_data,
                conta,
                colunas
            )

            bloco_data = None
            bloco_linhas = []

            if registro is None:
                return

            registro = filtrar_campos_configurados(
                registro,
                campos_configurados
            )

            registros.append(registro)

        for pagina in pdf.pages:

            palavras = pagina.extract_words(
                use_text_flow=False,
                keep_blank_chars=False
            )

            if not palavras:
                continue

            linhas = agrupar_palavras_por_linha(
                palavras
            )

            for linha in linhas:

                palavras_linha = linha["palavras"]

                texto_linha = " ".join(
                    palavra["text"]
                    for palavra in palavras_linha
                ).strip()

                chave_linha = normalizar_chave(
                    texto_linha
                )

                # Cabeçalhos e informações fora da tabela.
                if (
                    chave_linha.startswith("DATADESCRICAOFLUXOTIPOVALOR")
                    or chave_linha == "ADEN"
                    or chave_linha.startswith("EXTRATODEAGENCIA")
                    or chave_linha.startswith("NOME")
                    or chave_linha.startswith("DATA11")
                ):
                    continue

                data_movimento = localizar_data_linha(
                    palavras_linha
                )

                if data_movimento is not None:
                    finalizar_bloco()

                    bloco_data = data_movimento
                    bloco_linhas = [
                        list(palavras_linha)
                    ]
                    continue

                if bloco_data is not None:
                    bloco_linhas.append(
                        list(palavras_linha)
                    )

        finalizar_bloco()

    return registros