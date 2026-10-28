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


def converter_valor_rendimento(valor):
    if valor is None:
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    padrao = re.compile(
        r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$|^-?\d+,\d{2}$"
    )

    if not padrao.fullmatch(texto):
        return None

    return Decimal(
        texto
        .replace(".", "")
        .replace(",", ".")
    )


def localizar_conta_corrente_rendimento(pdf):
    padroes = (
        r"\bC/c\s*:?\s*([0-9]+(?:-[0-9X])?)",
        r"\bC/C\s*:?\s*([0-9]+(?:-[0-9X])?)",
    )

    for pagina in pdf.pages[:2]:
        texto = pagina.extract_text() or ""

        for padrao in padroes:
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
    tolerancia=2.5
):
    linhas = []

    for palavra in sorted(
        palavras,
        key=lambda item: (
            item["top"],
            item["x0"]
        )
    ):
        if (
            linhas
            and abs(
                linhas[-1]["top"]
                - palavra["top"]
            ) <= tolerancia
        ):
            linhas[-1]["palavras"].append(
                palavra
            )

            linhas[-1]["top"] = (
                linhas[-1]["top"]
                + palavra["top"]
            ) / 2
        else:
            linhas.append({
                "top": palavra["top"],
                "palavras": [palavra]
            })

    for linha in linhas:
        linha["palavras"] = sorted(
            linha["palavras"],
            key=lambda item: item["x0"]
        )

    return linhas


def texto_ascii(texto):
    texto = unicodedata.normalize(
        "NFKD",
        str(texto or "")
    )

    return "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    ).upper()


def linha_deve_ser_ignorada(texto):
    chave = texto_ascii(texto).strip()

    prefixos = (
        "DOCUMENTO LANCAMENTO",
        "SALDO INICIAL",
        "SALDO FINAL",
        "SALDO DISPONIVEL",
        "SALDO ATUAL",
        "LIMITE CHEQUE",
        "INFORMACOES REFERENTES",
        "JUROS ACUMULADOS",
        "TAXA DE JUROS",
        "BANCO RENDIMENTO",
        "OUVIDORIA",
        "EXTRATO",
        "CNPJ:",
        "( + )",
        "( - )",
        "(-)",
        "UTILIZADOS",
    )

    return chave.startswith(prefixos)


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
        for chave, valor
        in registro.items()
        if chave in campos_normalizados
    }


def processar_layout_extrato(
    pdf,
    campos_configurados
):
    registros_base = []
    linhas_descricao = []

    conta_corrente = (
        localizar_conta_corrente_rendimento(
            pdf
        )
    )

    data_atual = None

    padrao_data = re.compile(
        r"^\d{2}/\d{2}/\d{4}$"
    )

    padrao_valor = re.compile(
        r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$"
        r"|^-?\d+,\d{2}$"
    )

    for numero_pagina, pagina in enumerate(
        pdf.pages
    ):
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

            if not texto_linha:
                continue

            if padrao_data.fullmatch(
                texto_linha
            ):
                data_atual = texto_linha
                continue

            if linha_deve_ser_ignorada(
                texto_linha
            ):
                continue

            if data_atual is None:
                continue

            palavras_valor = [
                palavra
                for palavra in palavras_linha
                if (
                    palavra["x0"] > 400
                    and padrao_valor.fullmatch(
                        palavra["text"]
                    )
                )
            ]

            palavras_documento = [
                palavra
                for palavra in palavras_linha
                if (
                    50 <= palavra["x0"] < 115
                    and not padrao_data.fullmatch(
                        palavra["text"]
                    )
                )
            ]

            # Uma movimentação real do layout possui:
            # Documento + Valor + Saldo.
            if (
                len(palavras_valor) >= 2
                and palavras_documento
            ):
                palavras_valor = sorted(
                    palavras_valor,
                    key=lambda item: item["x0"]
                )

                palavra_valor = (
                    palavras_valor[-2]
                )

                palavra_saldo = (
                    palavras_valor[-1]
                )

                documento = " ".join(
                    palavra["text"]
                    for palavra
                    in palavras_documento
                ).strip()

                descricao = " ".join(
                    palavra["text"]
                    for palavra in palavras_linha
                    if (
                        palavra["x0"] >= 115
                        and palavra["x0"]
                        < palavra_valor["x0"]
                    )
                ).strip()

                valor = (
                    converter_valor_rendimento(
                        palavra_valor["text"]
                    )
                )

                saldo = (
                    converter_valor_rendimento(
                        palavra_saldo["text"]
                    )
                )

                registros_base.append({
                    "pagina": numero_pagina,
                    "top": linha["top"],
                    "data": data_atual,
                    "documento": documento,
                    "descricao": descricao,
                    "valor": valor,
                    "saldo": saldo,
                    "conta": conta_corrente
                })

                continue

            # O Rendimento quebra algumas descrições em
            # linhas acima ou abaixo do lançamento.
            descricao_auxiliar = " ".join(
                palavra["text"]
                for palavra in palavras_linha
                if (
                    115 <= palavra["x0"] < 400
                )
            ).strip()

            if descricao_auxiliar:
                chave_auxiliar = texto_ascii(
                    descricao_auxiliar
                )

                if not (
                    "DOCUMENTO LANCAMENTO"
                    in chave_auxiliar
                    or "SALDO INICIAL"
                    in chave_auxiliar
                    or "SALDO FINAL"
                    in chave_auxiliar
                ):
                    linhas_descricao.append({
                        "pagina": numero_pagina,
                        "top": linha["top"],
                        "data": data_atual,
                        "texto": descricao_auxiliar
                    })

    # Liga linhas quebradas à movimentação visualmente
    # mais próxima do mesmo dia e da mesma página.
    for auxiliar in linhas_descricao:
        candidatos = [
            registro
            for registro in registros_base
            if (
                registro["pagina"]
                == auxiliar["pagina"]
                and registro["data"]
                == auxiliar["data"]
                and abs(
                    registro["top"]
                    - auxiliar["top"]
                ) <= 10
            )
        ]

        if not candidatos:
            continue

        registro = min(
            candidatos,
            key=lambda item: abs(
                item["top"]
                - auxiliar["top"]
            )
        )

        if auxiliar["texto"] not in (
            registro["descricao"] or ""
        ):
            registro.setdefault(
                "_descricao_extra",
                []
            ).append(
                (
                    auxiliar["top"],
                    auxiliar["texto"]
                )
            )

    registros = []

    for registro in registros_base:
        partes_descricao = []

        if registro["descricao"]:
            partes_descricao.append(
                (
                    registro["top"],
                    registro["descricao"]
                )
            )

        partes_descricao.extend(
            registro.get(
                "_descricao_extra",
                []
            )
        )

        partes_descricao = sorted(
            partes_descricao,
            key=lambda item: item[0]
        )

        descricao = " ".join(
            texto
            for _, texto
            in partes_descricao
            if texto
        )

        descricao = re.sub(
            r"\s+",
            " ",
            descricao
        ).strip()

        resultado = {
            normalizar_chave(
                "Data"
            ): registro["data"],

            normalizar_chave(
                "Documento"
            ): registro["documento"] or None,

            normalizar_chave(
                "Lançamento"
            ): descricao or None,

            normalizar_chave(
                "Valor"
            ): registro["valor"],

            normalizar_chave(
                "Saldo"
            ): registro["saldo"],

            normalizar_chave(
                "Conta"
            ): registro["conta"]
        }

        resultado = (
            filtrar_campos_configurados(
                resultado,
                campos_configurados
            )
        )

        registros.append(
            resultado
        )

    return registros



def processar_layout_simples_conferencia(pdf, campos_configurados):
    texto_total = "\n".join(
        pagina.extract_text() or ""
        for pagina in pdf.pages
    )

    conta = None

    resultado_conta = re.search(
        r"Conta\s+Corrente:\s*([0-9]+(?:-[0-9X])?)",
        texto_total,
        flags=re.IGNORECASE
    )

    if resultado_conta:
        conta = resultado_conta.group(1).strip()
    else:
        linhas_texto = [
            linha.strip()
            for linha in texto_total.splitlines()
            if linha.strip()
        ]

        for indice, linha in enumerate(linhas_texto):
            if texto_ascii(linha).startswith("CONTA CORRENTE"):
                for proxima in linhas_texto[indice + 1:indice + 6]:
                    if re.fullmatch(r"[0-9]+(?:-[0-9X])?", proxima):
                        conta = proxima
                        break
                if conta:
                    break

    registros = []
    data_atual = None
    ultimo_registro = None

    padrao_data = re.compile(r"^\d{2}/\d{2}/\d{4}$")
    padrao_valor = re.compile(
        r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$|^-?\d+,\d{2}$"
    )

    for pagina in pdf.pages:
        palavras = pagina.extract_words(
            use_text_flow=False,
            keep_blank_chars=False,
            x_tolerance=2,
            y_tolerance=2
        )

        if not palavras:
            continue

        linhas = agrupar_palavras_por_linha(
            palavras,
            tolerancia=3
        )

        for linha in linhas:
            palavras_linha = linha["palavras"]
            textos = [palavra["text"] for palavra in palavras_linha]
            texto_linha = " ".join(textos).strip()
            chave_linha = texto_ascii(texto_linha).strip()

            if not texto_linha:
                continue

            # Depois que entra na área de resumo do extrato,
            # não existem mais lançamentos bancários.
            if (
                chave_linha.startswith("SALDO ATUAL")
                or chave_linha.startswith("POSICAO EM:")
                or chave_linha.startswith("DETALHES DOS VALORES BLOQUEADOS")
                or chave_linha.startswith("SALDO LIQUIDO")
                or chave_linha.startswith("SALDO PROVISIONADO")
                or chave_linha.startswith("SALDO A TRANSPORTAR")
                or chave_linha.startswith("*** FIM DE RELATORIO")
            ):
                break

            # Data pode vir apenas na primeira movimentação do dia.
            inicio_tokens = 0

            if textos and padrao_data.fullmatch(textos[0]):
                data_atual = textos[0]
                inicio_tokens = 1

            if data_atual is None:
                continue

            # Complemento do histórico da movimentação anterior.
            if (
                ultimo_registro is not None
                and chave_linha.startswith("CP :")
            ):
                complemento = re.sub(r"\s+", " ", texto_linha).strip()

                if complemento:
                    descricao_atual = ultimo_registro["descricao"] or ""
                    if complemento not in descricao_atual:
                        ultimo_registro["descricao"] = (
                            f"{descricao_atual} {complemento}"
                        ).strip()
                continue

            # SALDO fecha o bloco do dia. Aplicamos ao último lançamento.
            if chave_linha.startswith("SALDO"):
                valores = [
                    token
                    for token in textos
                    if padrao_valor.fullmatch(token)
                ]

                if ultimo_registro is not None and valores:
                    ultimo_registro["saldo"] = (
                        converter_valor_rendimento(valores[-1])
                    )
                continue

            # Ignora cabeçalhos/resumos.
            ignorar = (
                "DATA DE LANCTO",
                "SALDO ANTERIOR",
                "SALDO ATUAL",
                "LIMITE:",
                "BLOQUEADO:",
                "C.P.M.F.",
                "DISPONIVEL:",
                "VALOR BLOQUEADO",
                "DETALHES DOS VALORES BLOQUEADOS",
                "SALDO LIQUIDO",
                "SALDO PROVISIONADO",
                "SALDO A TRANSPORTAR",
                "*** FIM DE RELATORIO",
                "*** SUJEITO A ALTERACOES",
                "EXTRATO DE C/C PARA SIMPLES CONFERENCIA",
                "BANCO RENDIMENTO",
                "AGENCIA:",
                "CONTA CORRENTE:",
                "PERIODO DE:",
                "EMITIDO EM",
                "PAGINA:",
                "POSICAO EM:"
            )

            if chave_linha.startswith(ignorar):
                continue

            tokens = textos[inicio_tokens:]

            if len(tokens) < 3:
                continue

            documento = tokens[0]

            if not re.fullmatch(r"[A-Za-z0-9.\-]+", documento):
                continue

            # Localiza os valores monetários preservando a geometria.
            palavras_uteis = palavras_linha[inicio_tokens:]

            candidatos_valor = [
                palavra
                for palavra in palavras_uteis
                if padrao_valor.fullmatch(palavra["text"])
            ]

            if not candidatos_valor:
                continue

            palavra_valor = candidatos_valor[0]
            valor = converter_valor_rendimento(
                palavra_valor["text"]
            )

            if valor is None:
                continue

            largura = float(pagina.width)
            x_centro = (
                palavra_valor["x0"]
                + palavra_valor["x1"]
            ) / 2

            # Débito e Crédito são colunas físicas distintas.
            if x_centro < 0.79 * largura:
                valor = -abs(valor)
            else:
                valor = abs(valor)

            # Histórico fica entre documento e valor.
            descricao_palavras = [
                palavra["text"]
                for palavra in palavras_uteis[1:]
                if palavra["x0"] < palavra_valor["x0"]
            ]

            descricao = re.sub(
                r"\s+",
                " ",
                " ".join(descricao_palavras)
            ).strip()

            registro = {
                "data": data_atual,
                "documento": documento,
                "descricao": descricao or None,
                "valor": valor,
                "saldo": None,
                "conta": conta
            }

            registros.append(registro)
            ultimo_registro = registro

    saida_registros = []

    for registro in registros:
        resultado = {
            normalizar_chave("Data"): registro["data"],
            normalizar_chave("Documento"): registro["documento"],
            normalizar_chave("Lançamento"): registro["descricao"],
            normalizar_chave("Valor"): registro["valor"],
            normalizar_chave("Saldo"): registro["saldo"],
            normalizar_chave("Conta"): registro["conta"]
        }

        saida_registros.append(
            filtrar_campos_configurados(
                resultado,
                campos_configurados
            )
        )

    return saida_registros


def processar_layout_ocr(
    caminho,
    campos_configurados=None
):
    """
    Fallback OCR para PDFs Rendimento sem camada de texto.

    Este caminho só é usado quando pdfplumber não consegue
    extrair texto do PDF. Assim, não interfere nos layouts
    que já funcionam por texto nativo.
    """

    try:
        import io
        import os

        import pymupdf
        import pytesseract
        from PIL import Image

    except ImportError as erro:
        raise RuntimeError(
            "PDF Rendimento sem camada de texto. "
            "Instale o fallback OCR com: "
            "pip install pymupdf pytesseract pillow"
        ) from erro

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

    def converter_valor_ocr(texto):
        texto = str(texto or "").strip()

        if not texto:
            return None

        texto = (
            texto
            .replace("R$", "")
            .replace(" ", "")
        )

        # Caso normal brasileiro.
        if re.fullmatch(
            r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}",
            texto
        ):
            return Decimal(
                texto
                .replace(".", "")
                .replace(",", ".")
            )

        # OCR pode perder a vírgula em saldos pequenos:
        # 1414 -> 14,14
        if re.fullmatch(r"-?\d{3,8}", texto):
            negativo = texto.startswith("-")
            digitos = texto.lstrip("-")

            if len(digitos) >= 3:
                numero = Decimal(digitos) / Decimal("100")
                return -numero if negativo else numero

        return None

    documento_pdf = pymupdf.open(caminho)

    registros = []
    conta = None
    data_atual = None
    buffer_descricao = []

    padrao_data = re.compile(
        r"^\d{2}/\d{2}/\d{4}$"
    )

    padrao_movimento = re.compile(
        r"^([A-Za-z0-9.]+)\s+"
        r"(.+?)\s+"
        r"(-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}|-?\d{3,8})\s+"
        r"(-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}|-?\d{3,8})$"
    )

    try:
        for pagina in documento_pdf:
            pixmap = pagina.get_pixmap(
                matrix=pymupdf.Matrix(2.5, 2.5),
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

            except Exception:
                texto_pagina = pytesseract.image_to_string(
                    imagem,
                    lang="eng",
                    config="--psm 6"
                )

            if conta is None:
                resultado_conta = re.search(
                    r"\bC\s*/\s*C\s*:?\s*([0-9]+(?:-[0-9X])?)",
                    texto_pagina,
                    flags=re.IGNORECASE
                )

                if resultado_conta:
                    conta = resultado_conta.group(1).strip()

            linhas = [
                re.sub(r"\s+", " ", linha).strip()
                for linha in texto_pagina.splitlines()
                if linha.strip()
            ]

            for linha in linhas:
                linha_ascii = texto_ascii(linha).strip()

                # Data sozinha inicia o bloco.
                if padrao_data.fullmatch(linha):
                    data_atual = linha
                    buffer_descricao = []
                    continue

                # Alguns OCRs podem trazer a data no começo da linha.
                resultado_data_inicio = re.match(
                    r"^(\d{2}/\d{2}/\d{4})\s+(.+)$",
                    linha
                )

                if resultado_data_inicio:
                    data_atual = resultado_data_inicio.group(1)
                    linha = resultado_data_inicio.group(2).strip()
                    linha_ascii = texto_ascii(linha).strip()
                    buffer_descricao = []

                if data_atual is None:
                    continue

                # Ignora cabeçalhos, saldos finais e resumos.
                ignorar = (
                    "DOCUMENTO",
                    "SALDO FINAL",
                    "SALDO DISPONIVEL",
                    "SALDO ATUAL",
                    "LIMITE",
                    "INFORMACOES REFERENTES",
                    "JUROS ACUMULADOS",
                    "TAXA DE JUROS",
                    "BANCO RENDIMENTO",
                    "OUVIDORIA",
                    "EXTRATO",
                    "DE ",
                    "HTTPS://",
                )

                if linha_ascii.startswith(ignorar):
                    continue

                resultado_movimento = padrao_movimento.match(
                    linha
                )

                if resultado_movimento:
                    documento = resultado_movimento.group(1).strip()
                    descricao = resultado_movimento.group(2).strip()
                    valor_texto = resultado_movimento.group(3).strip()
                    saldo_texto = resultado_movimento.group(4).strip()

                    # Se a descrição foi quebrada para a linha anterior,
                    # incorpora antes da descrição encontrada na linha.
                    if buffer_descricao:
                        descricao = " ".join(
                            buffer_descricao + [descricao]
                        ).strip()
                        buffer_descricao = []

                    valor = converter_valor_ocr(
                        valor_texto
                    )

                    saldo = converter_valor_ocr(
                        saldo_texto
                    )

                    if valor is None:
                        continue

                    registro = {
                        normalizar_chave("Data"): data_atual,
                        normalizar_chave("Documento"): documento,
                        normalizar_chave("Lançamento"): descricao or None,
                        normalizar_chave("Valor"): valor,
                        normalizar_chave("Saldo"): saldo,
                        normalizar_chave("Conta"): conta
                    }

                    registros.append(
                        filtrar_campos_configurados(
                            registro,
                            campos_configurados
                        )
                    )

                    continue

                # Linhas textuais entre a data e o movimento podem ser
                # continuação do histórico que vem antes do documento.
                possui_valor_final = bool(
                    re.search(
                        r"-?\d{1,3}(?:\.\d{3})*,\d{2}\s+"
                        r"-?\d{1,3}(?:\.\d{3})*,\d{2}$",
                        linha
                    )
                )

                if not possui_valor_final:
                    # Evita carregar ruído conhecido para o próximo movimento.
                    if not (
                        "R$" in linha_ascii
                        or "CNPJ" in linha_ascii
                        or "AG." in linha_ascii
                        or "C/C" in linha_ascii
                    ):
                        buffer_descricao.append(
                            linha
                        )

                        # Limita o buffer para não acumular cabeçalho.
                        buffer_descricao = buffer_descricao[-2:]

    finally:
        documento_pdf.close()

    return registros

def processar_layout_internet_banking(
    pdf,
    campos_configurados
):
    texto = "\n".join(
        pagina.extract_text() or ""
        for pagina in pdf.pages
    )

    if re.search(
        r"Conta\s+sem\s+movimento\s+no\s+per[ií]odo",
        texto,
        flags=re.IGNORECASE
    ):
        return []

    # O único exemplo recebido deste segundo layout
    # não possui movimentações. Evita interpretar
    # saldos/limites como lançamentos.
    raise ValueError(
        "Layout Internet Banking do Rendimento "
        "com movimentações ainda não mapeado."
    )


def extrair_rend_dist_pdf(
    caminho,
    campos_configurados=None
):
    """
    Extrator Rendimento - Distribuidoras.

    Layout 1:
        Extrato tradicional:
        Documento | Lançamento | Valor (R$) | Saldo (R$)

    Layout 2:
        Tela Saldo e Extrato / Internet Banking.
        O exemplo atualmente conhecido informa conta
        sem movimento e retorna lista vazia.

    Saída:
        Data
        Documento
        Lançamento
        Valor
        Saldo
        Conta
    """

    with pdfplumber.open(caminho) as pdf:
        texto_inicial = "\n".join(
            pagina.extract_text() or ""
            for pagina in pdf.pages[:2]
        )

        # Terceira lógica: PDF sem camada de texto.
        # É fallback puro, então não interfere nos layouts já funcionais.
        if not texto_inicial.strip():
            return processar_layout_ocr(
                caminho,
                campos_configurados
            )

        # Normaliza acentos, caixa e espaços para não depender
        # da forma exata como cada PDF foi gerado.
        texto_layout = texto_ascii(texto_inicial)
        texto_layout = re.sub(
            r"\s+",
            " ",
            texto_layout
        ).strip()

        # Layout de tela / Internet Banking.
        # Deve ser identificado antes do extrato formal.
        if (
            "SALDO E EXTRATO" in texto_layout
            or "EXTRATO DETALHADO" in texto_layout
        ):
            return (
                processar_layout_internet_banking(
                    pdf,
                    campos_configurados
                )
            )

        # Layout antigo:
        # Extrato de C/C para Simples Conferência.
        if (
            "EXTRATO DE C/C PARA SIMPLES CONFERENCIA"
            in texto_layout
            or (
                "DATA DE LANCTO" in texto_layout
                and "HISTORICO" in texto_layout
                and "DEBITO" in texto_layout
                and "CREDITO" in texto_layout
            )
        ):
            return processar_layout_simples_conferencia(
                pdf,
                campos_configurados
            )

        # Extrato formal do Rendimento.
        #
        # Não depende mais da presença literal e exata dos
        # quatro nomes de coluna no texto extraído.
        possui_conta = bool(
            re.search(
                r"\bC\s*/\s*C\b",
                texto_layout
            )
        )

        possui_periodo = bool(
            re.search(
                r"\bDE\s+\d{2}/\d{2}/\d{4}"
                r"\s+A\s+\d{2}/\d{2}/\d{4}\b",
                texto_layout
            )
        )

        possui_tabela = (
            "DOCUMENTO" in texto_layout
            and "LANCAMENTO" in texto_layout
            and "VALOR" in texto_layout
            and "SALDO" in texto_layout
        )

        possui_saldos_periodo = (
            "SALDO INICIAL" in texto_layout
            or "SALDO FINAL" in texto_layout
        )

        possui_extrato = (
            "EXTRATO" in texto_layout
        )

        pontos_layout_formal = sum(
            (
                possui_conta,
                possui_periodo,
                possui_tabela,
                possui_saldos_periodo,
                possui_extrato
            )
        )

        if (
            pontos_layout_formal >= 3
            and (
                possui_tabela
                or possui_saldos_periodo
            )
        ):
            return processar_layout_extrato(
                pdf,
                campos_configurados
            )

        raise ValueError(
            "Layout do Banco Rendimento "
            "não reconhecido."
        )