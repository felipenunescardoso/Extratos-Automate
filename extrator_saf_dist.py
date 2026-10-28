import re
from pathlib import Path
import unicodedata
from decimal import Decimal

import pdfplumber


# ============================================================
# FUNÇÕES INTERNAS
# ============================================================

def _normalizar_chave(texto):
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

    texto = re.sub(
        r"[^A-Z0-9]",
        "",
        texto
    )

    return texto


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
    )

    if not re.fullmatch(
        r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}",
        texto
    ):
        return None

    return Decimal(
        texto
        .replace(".", "")
        .replace(",", ".")
    )


def _agrupar_linhas(words, tolerancia=1.6):
    """
    Agrupa as palavras extraídas pelo pdfplumber
    pela coordenada vertical.
    """

    words = sorted(
        words,
        key=lambda item: (
            item["top"],
            item["x0"]
        )
    )

    linhas = []

    for word in words:

        if (
            not linhas
            or abs(
                linhas[-1]["top"]
                - word["top"]
            ) > tolerancia
        ):
            linhas.append({
                "top": word["top"],
                "words": [word]
            })

        else:
            linhas[-1]["words"].append(
                word
            )

    for linha in linhas:
        linha["words"].sort(
            key=lambda item: item["x0"]
        )

    return linhas


def _texto_linha(words):
    return " ".join(
        word["text"]
        for word in words
    ).strip()


def _localizar_valor(words):
    """
    O valor normalmente fica na coluna Valor,
    mas em algumas páginas pode começar um pouco
    antes da posição visual esperada.

    Por isso a identificação é feita pelo conteúdo
    monetário, usando o último valor monetário da linha.
    """

    indice_valor = None

    for indice, word in enumerate(words):

        if word["x0"] < 400:
            continue

        if _converter_valor(
            word["text"]
        ) is not None:
            indice_valor = indice

    if indice_valor is None:
        return None, None

    return (
        indice_valor,
        _converter_valor(
            words[indice_valor]["text"]
        )
    )


def _montar_descricao(
    words,
    x_inicio=60,
    x_fim=410
):
    partes = [
        word["text"]
        for word in words
        if (
            x_inicio
            <= word["x0"]
            < x_fim
        )
    ]

    return " ".join(
        partes
    ).strip()


def _montar_documento(
    words,
    indice_valor
):
    if indice_valor is None:
        return None

    partes = []

    for indice, word in enumerate(words):

        if indice >= indice_valor:
            break

        if word["x0"] >= 410:
            partes.append(
                word["text"]
            )

    documento = " ".join(
        partes
    ).strip()

    return documento or None


def _finalizar_registro(
    registros,
    registro_atual,
    campos_configurados
):
    if registro_atual is None:
        return None

    registro = {
        "DATA": registro_atual["DATA"],
        "DOCUMENTO": registro_atual["DOCUMENTO"],
        "LANCAMENTO": registro_atual["LANCAMENTO"],
        "VALOR": registro_atual["VALOR"],
        "CONTA": registro_atual["CONTA"]
    }

    registros.append(
        _filtrar_campos_configurados(
            registro,
            campos_configurados
        )
    )

    return None



def _configurar_tesseract():
    import os
    import pytesseract

    candidatos = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(
            r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"
        )
    ]

    for caminho in candidatos:
        if Path(caminho).exists():
            pytesseract.pytesseract.tesseract_cmd = caminho
            return


def _ocr_paginas(caminho):
    """
    OCR usado somente quando o PDF não possui camada de texto.
    """
    import pymupdf
    import pytesseract
    from PIL import Image

    _configurar_tesseract()

    paginas = []

    documento = pymupdf.open(caminho)

    try:
        for pagina in documento:
            matriz = pymupdf.Matrix(2.5, 2.5)
            pix = pagina.get_pixmap(
                matrix=matriz,
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

            paginas.append(texto)

    finally:
        documento.close()

    return paginas



def _converter_valor_ocr(texto):
    """
    Converte valores monetários lidos pelo OCR.

    O Tesseract pode trocar o separador de milhar:
        -4.248,00 -> -4,248,00

    A regra considera os dois últimos dígitos como centavos
    e todos os separadores anteriores como separadores de milhar.
    """
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

    negativo = texto.startswith("-")

    if negativo:
        texto = texto[1:]

    if not re.fullmatch(
        r"\d[\d.,]*[.,]\d{2}",
        texto
    ):
        return None

    parte_inteira = texto[:-3]
    centavos = texto[-2:]

    parte_inteira = re.sub(
        r"[.,]",
        "",
        parte_inteira
    )

    if not parte_inteira:
        parte_inteira = "0"

    numero = Decimal(
        f"{parte_inteira}.{centavos}"
    )

    if negativo:
        numero = -numero

    return numero


def _processar_ocr_safra(
    caminho,
    campos_configurados
):
    paginas = _ocr_paginas(
        caminho
    )

    texto_completo = "\n".join(
        paginas
    )

    texto_upper = texto_completo.upper()

    if "SAFRA" not in texto_upper:
        raise ValueError(
            "Layout do Banco Safra não reconhecido."
        )

    # Conta
    resultado_conta = re.search(
        r"\bCONTA\s*[:\-]?\s*([0-9Xx-]+)",
        texto_completo,
        flags=re.IGNORECASE
    )

    conta = (
        resultado_conta.group(1).strip()
        if resultado_conta
        else None
    )

    # Ano / período
    resultado_periodo = re.search(
        r"PER[IÍ]ODO\s+DE\s+"
        r"\d{2}/\d{2}/(\d{4})\s+A\s+"
        r"\d{2}/\d{2}/\d{4}",
        texto_completo,
        flags=re.IGNORECASE
    )

    if resultado_periodo:
        ano = int(
            resultado_periodo.group(1)
        )
    else:
        # fallback: pega a primeira data completa visível
        resultado_data = re.search(
            r"\b\d{2}/\d{2}/(\d{4})\b",
            texto_completo
        )

        if not resultado_data:
            raise ValueError(
                "Não foi possível identificar o ano "
                "do período no extrato Safra."
            )

        ano = int(
            resultado_data.group(1)
        )

    registros = []

    # O OCR do Safra costuma manter cada movimento em uma linha
    # e colocar o complemento em uma ou mais linhas imediatamente
    # abaixo, antes do documento/valor.
    padrao_inicio = re.compile(
        r"^\s*(\d{2}/\d{2})\s+(.+?)\s*$"
    )

    padrao_doc_valor = re.compile(
        r"^\s*([0-9A-Za-z.\-]+)\s+"
        r"(-?\d[\d.,]*[.,]\d{2})\s*$"
    )

    padrao_valor_final = re.compile(
        r"(-?\d[\d.,]*[.,]\d{2})\s*$"
    )

    ignorar_prefixos = (
        "LANÇAMENTOS REALIZADOS",
        "LANCAMENTOS REALIZADOS",
        "DATA LANÇAMENTO",
        "DATA LANCAMENTO",
        "BANCO SAFRA",
        "CENTRAL DE SUPORTE",
        "SAC E DEFICIENTES",
        "OUVIDORIA",
        "PÁGINA ",
        "PAGINA ",
        "EXTRATO DE MOVIMENTAÇÃO",
        "EXTRATO DE MOVIMENTACAO",
        "SALDO + LIMITE",
        "PERÍODO DE",
        "PERIODO DE",
        "CNPJ:"
    )

    registro_pendente = None

    def finalizar():
        nonlocal registro_pendente

        if not registro_pendente:
            return

        descricao = " ".join(
            registro_pendente["descricao_partes"]
        ).strip()

        # Remove artefatos visuais comuns do OCR no início.
        descricao = re.sub(
            r"^[|—–\-]+\s*",
            "",
            descricao
        ).strip()

        descricao_upper = descricao.upper()

        documento_atual = str(
            registro_pendente.get("documento")
            or ""
        ).strip().upper()

        # Linhas de saldo/posição não são movimentos.
        # No PDF imagem o OCR pode separar:
        #   descrição = CONTA
        #   documento = CORRENTE
        if (
            descricao_upper.startswith(
                "SALDO CONTA CORRENTE"
            )
            or descricao_upper.startswith(
                "CONTA CORRENTE"
            )
            or (
                descricao_upper == "CONTA"
                and documento_atual == "CORRENTE"
            )
        ):
            registro_pendente = None
            return

        valor = registro_pendente.get(
            "valor"
        )

        if valor is None:
            registro_pendente = None
            return

        registro = {
            "DATA": registro_pendente["data"],
            "DOCUMENTO": registro_pendente.get(
                "documento"
            ),
            "LANCAMENTO": descricao,
            "VALOR": valor,
            "CONTA": conta
        }

        registros.append(
            _filtrar_campos_configurados(
                registro,
                campos_configurados
            )
        )

        registro_pendente = None

    for texto_pagina in paginas:

        linhas = [
            re.sub(r"\s+", " ", linha).strip()
            for linha in texto_pagina.splitlines()
            if linha.strip()
        ]

        ignorar_rodape_pagina = False

        for linha in linhas:

            linha_upper = linha.upper()

            if ignorar_rodape_pagina:
                continue

            if (
                linha_upper.startswith(
                    "CENTRAL DE SUPORTE"
                )
                or linha_upper.startswith(
                    "SAC E DEFICIENTES"
                )
                or linha_upper.startswith(
                    "OUVIDORIA"
                )
            ):
                # Se o lançamento já possui valor, ele já está completo.
                # Finaliza antes do rodapé para que o cabeçalho/artefatos
                # da página seguinte não sejam anexados à descrição.
                if (
                    registro_pendente is not None
                    and registro_pendente.get(
                        "valor"
                    ) is not None
                ):
                    finalizar()

                ignorar_rodape_pagina = True
                continue

            if any(
                linha_upper.startswith(prefixo)
                for prefixo in ignorar_prefixos
            ):
                continue

            inicio = padrao_inicio.match(
                linha
            )

            if inicio:
                # fecha movimento anterior
                finalizar()

                data_curta = inicio.group(1)
                restante = inicio.group(2).strip()

                # Linhas de saldo/posição do Safra não são movimentos.
                # Fazemos a exclusão antes de separar documento/valor,
                # evitando que "CORRENTE" seja interpretado como documento.
                restante_limpo = re.sub(
                    r"^[|—–\-]+\s*",
                    "",
                    restante
                ).strip()

                restante_normalizado = re.sub(
                    r"\s+",
                    " ",
                    restante_limpo
                ).upper()

                if (
                    restante_normalizado.startswith(
                        "SALDO CONTA CORRENTE"
                    )
                    or restante_normalizado.startswith(
                        "CONTA CORRENTE"
                    )
                ):
                    registro_pendente = None
                    continue

                # Alguns OCRs já trazem documento e valor na mesma linha.
                valor_match = padrao_valor_final.search(
                    restante
                )

                valor = None
                documento = None

                if valor_match:
                    valor = _converter_valor_ocr(
                        valor_match.group(1)
                    )

                    antes_valor = restante[
                        :valor_match.start()
                    ].strip()

                    partes = antes_valor.split()

                    if partes:
                        ultimo = partes[-1]

                        # Documento pode ser numérico ou alfanumérico.
                        if re.fullmatch(
                            r"[0-9A-Za-z.\-]{4,}",
                            ultimo
                        ):
                            documento = ultimo
                            partes = partes[:-1]

                    descricao = " ".join(
                        partes
                    ).strip()

                else:
                    descricao = restante

                dia, mes = data_curta.split("/")

                registro_pendente = {
                    "data": f"{dia}/{mes}/{ano}",
                    "descricao_partes": (
                        [descricao]
                        if descricao
                        else []
                    ),
                    "documento": documento,
                    "valor": valor
                }

                continue

            if registro_pendente is None:
                continue

            # Linha isolada com Documento + Valor.
            doc_valor = padrao_doc_valor.match(
                linha
            )

            if doc_valor:
                registro_pendente["documento"] = (
                    doc_valor.group(1)
                )
                registro_pendente["valor"] = (
                    _converter_valor_ocr(
                        doc_valor.group(2)
                    )
                )
                continue

            # Linha isolada só com valor, comum em CONTA CORRENTE.
            valor_so = re.fullmatch(
                r"-?\d[\d.,]*[.,]\d{2}",
                linha
            )

            if valor_so:
                registro_pendente["valor"] = (
                    _converter_valor_ocr(
                        linha
                    )
                )
                continue

            # Complemento / CNPJ / nome.
            registro_pendente[
                "descricao_partes"
            ].append(
                linha
            )

    finalizar()

    return registros


# ============================================================
# EXTRATOR PÚBLICO
# ============================================================

def extrair_saf_dist_pdf(
    caminho,
    campos_configurados=None
):
    """
    Extrator do Banco Safra - Distribuidoras.

    Layout tratado:

        Extrato de Movimentação
        Data | Lançamento | Complemento | Nº Documento | Valor (R$)

    Regras:
        - Lançamento + Complemento formam o campo LANCAMENTO;
        - Nº Documento vai para DOCUMENTO;
        - Valor mantém o sinal original do PDF;
        - Conta é lida do cabeçalho;
        - SALDO CONTA CORRENTE é ignorado;
        - continuações de descrição em linhas seguintes
          são anexadas ao lançamento anterior;
        - continuação de uma movimentação entre páginas
          também é preservada;
        - não gera campo de saldo, pois o Safra apresenta
          saldo em linhas separadas de fechamento diário.
    """

    registros = []

    conta = None
    ano = None
    registro_atual = None

    with pdfplumber.open(
        caminho
    ) as pdf:

        # ----------------------------------------------------
        # VALIDAÇÃO / CABEÇALHO
        # ----------------------------------------------------

        texto_inicial = "\n".join(
            pagina.extract_text() or ""
            for pagina in pdf.pages[:2]
        )

        # PDF imagem/scaneado: usa OCR sem alterar a lógica
        # já existente para PDFs com camada de texto.
        if not texto_inicial.strip():
            return _processar_ocr_safra(
                caminho,
                campos_configurados
            )

        if (
            "Banco Safra" not in texto_inicial
            and "BANCO SAFRA" not in texto_inicial.upper()
        ):
            raise ValueError(
                "Layout do Banco Safra não reconhecido."
            )

        resultado_conta = re.search(
            r"\bCONTA:\s*([0-9Xx-]+)",
            texto_inicial,
            flags=re.IGNORECASE
        )

        if resultado_conta:
            conta = (
                resultado_conta
                .group(1)
                .strip()
            )

        resultado_periodo = re.search(
            r"Per[ií]odo\s+de\s+"
            r"\d{2}/\d{2}/(\d{4})\s+a\s+"
            r"\d{2}/\d{2}/\d{4}",
            texto_inicial,
            flags=re.IGNORECASE
        )

        if resultado_periodo:
            ano = int(
                resultado_periodo.group(1)
            )

        if ano is None:
            raise ValueError(
                "Não foi possível identificar o ano "
                "do período no extrato Safra."
            )

        # ----------------------------------------------------
        # PÁGINAS
        # ----------------------------------------------------

        for pagina in pdf.pages:

            words = pagina.extract_words(
                x_tolerance=2,
                y_tolerance=2
            )

            linhas = _agrupar_linhas(
                words
            )

            dentro_tabela = False

            for linha in linhas:

                words_linha = linha["words"]

                texto = _texto_linha(
                    words_linha
                )

                texto_upper = texto.upper()

                # --------------------------------------------
                # INÍCIO/FIM DA ÁREA DE LANÇAMENTOS
                # --------------------------------------------

                if (
                    "LANÇAMENTOS REALIZADOS"
                    in texto_upper
                ):
                    dentro_tabela = True
                    continue

                if (
                    dentro_tabela
                    and texto_upper.startswith("DATA ")
                    and "DOCUMENTO" in texto_upper
                    and "VALOR" in texto_upper
                ):
                    continue

                if (
                    texto_upper.startswith("BANCO SAFRA")
                    or texto_upper.startswith(
                        "CENTRAL DE SUPORTE"
                    )
                ):
                    dentro_tabela = False
                    continue

                if not dentro_tabela:
                    continue

                # --------------------------------------------
                # DATA
                # --------------------------------------------

                partes_data = [
                    word["text"]
                    for word in words_linha
                    if word["x0"] < 60
                ]

                data_curta = " ".join(
                    partes_data
                ).strip()

                eh_nova_movimentacao = bool(
                    re.fullmatch(
                        r"\d{2}/\d{2}",
                        data_curta
                    )
                )

                # --------------------------------------------
                # NOVA MOVIMENTAÇÃO
                # --------------------------------------------

                if eh_nova_movimentacao:

                    registro_atual = (
                        _finalizar_registro(
                            registros,
                            registro_atual,
                            campos_configurados
                        )
                    )

                    descricao = (
                        _montar_descricao(
                            words_linha
                        )
                    )

                    # SALDO é apenas informativo.
                    if descricao.upper().startswith(
                        "SALDO CONTA CORRENTE"
                    ):
                        continue

                    indice_valor, valor = (
                        _localizar_valor(
                            words_linha
                        )
                    )

                    if valor is None:
                        raise ValueError(
                            "Não foi possível identificar "
                            f"o valor do lançamento Safra: "
                            f"{texto}"
                        )

                    documento = (
                        _montar_documento(
                            words_linha,
                            indice_valor
                        )
                    )

                    dia, mes = (
                        data_curta.split("/")
                    )

                    registro_atual = {
                        "DATA": (
                            f"{dia}/{mes}/{ano}"
                        ),
                        "DOCUMENTO": documento,
                        "LANCAMENTO": descricao,
                        "VALOR": valor,
                        "CONTA": conta
                    }

                    continue

                # --------------------------------------------
                # CONTINUAÇÃO DA DESCRIÇÃO
                # --------------------------------------------

                if registro_atual is None:
                    continue

                complemento = (
                    _montar_descricao(
                        words_linha
                    )
                )

                if not complemento:
                    continue

                complemento_upper = (
                    complemento.upper()
                )

                # Segurança contra rodapé.
                if any(
                    trecho in complemento_upper
                    for trecho in (
                        "CENTRAL DE SUPORTE",
                        "OUVIDORIA",
                        "DEMAIS LOCALIDADES",
                        "ATENDIMENTO",
                        "EXCETO FERIADOS"
                    )
                ):
                    continue

                registro_atual["LANCAMENTO"] = (
                    (
                        registro_atual["LANCAMENTO"]
                        + " "
                        + complemento
                    )
                    .strip()
                )

        # Último lançamento do arquivo.
        _finalizar_registro(
            registros,
            registro_atual,
            campos_configurados
        )

    return registros