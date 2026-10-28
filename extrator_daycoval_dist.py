import io
import os
import re
import unicodedata
from decimal import Decimal, InvalidOperation

import pdfplumber


_RE_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_RE_VALOR = re.compile(r"^-?[\d.]+,\d{2}$")


def _normalizar_chave(texto):
    texto = str(texto or "").strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", texto)


def _texto_ascii(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(
        c for c in texto if not unicodedata.combining(c)
    ).upper()


def _filtrar_campos_configurados(registro, campos_configurados):
    if not campos_configurados:
        return registro

    permitidos = {
        _normalizar_chave(campo)
        for campo in campos_configurados
    }

    return {
        chave: valor
        for chave, valor in registro.items()
        if chave in permitidos
    }


def _valor_brasileiro(texto):
    try:
        return Decimal(
            str(texto)
            .replace("R$", "")
            .replace(" ", "")
            .strip()
            .replace(".", "")
            .replace(",", ".")
        )
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(
            f"Valor inválido no extrato Daycoval: {texto!r}"
        ) from exc


def _registro(data, lancamento, valor, conta, campos_configurados):
    registro = {
        _normalizar_chave("Data"): data,
        _normalizar_chave("Lançamento"): re.sub(
            r"\s+",
            " ",
            str(lancamento or "")
        ).strip(),
        _normalizar_chave("Valor"): valor,
        _normalizar_chave("Conta"): conta,
    }

    return _filtrar_campos_configurados(
        registro,
        campos_configurados
    )


def _texto_pdf(pdf):
    return "\n".join(
        texto
        for pagina in pdf.pages
        if (texto := (pagina.extract_text() or "")).strip()
    )


def _extrair_conta_texto(texto):
    padroes = (
        r"\bConta\s*:?\s*[\r\n ]*([0-9][0-9.\-]*)",
        r"\bCONTA\s+CORRENTE\s*:?\s*[\r\n ]*([0-9][0-9.\-]*)",
    )

    for padrao in padroes:
        resultado = re.search(
            padrao,
            texto,
            flags=re.IGNORECASE
        )
        if resultado:
            return resultado.group(1).strip()

    return None


def _linhas_visuais(pagina, tolerancia=3):
    palavras = pagina.extract_words(
        x_tolerance=2,
        y_tolerance=2,
        keep_blank_chars=False
    )

    palavras.sort(
        key=lambda p: (
            float(p["top"]),
            float(p["x0"])
        )
    )

    grupos = []

    for palavra in palavras:
        top = float(palavra["top"])

        if (
            not grupos
            or abs(top - grupos[-1][0]) > tolerancia
        ):
            grupos.append([top, [palavra]])
        else:
            grupos[-1][1].append(palavra)

    return [
        sorted(
            grupo,
            key=lambda p: float(p["x0"])
        )
        for _, grupo in grupos
    ]


def _limites_colunas(pagina):
    for linha in _linhas_visuais(pagina):
        textos = [
            p["text"].strip()
            for p in linha
        ]
        normal = [
            _normalizar_chave(t)
            for t in textos
        ]

        if (
            "DATA" in normal
            and "LANCAMENTO" in normal
            and "DEBITO" in normal
            and "CREDITO" in normal
        ):
            def x(chave):
                indice = normal.index(chave)
                return float(linha[indice]["x0"])

            return {
                "data": x("DATA"),
                "lancamento": x("LANCAMENTO"),
                "debito": x("DEBITO"),
                "credito": x("CREDITO"),
                "saldo": (
                    x("SALDO")
                    if "SALDO" in normal
                    else float(pagina.width)
                ),
            }

    return None


def _extrair_movimentos_texto(
    pdf,
    conta,
    campos_configurados
):
    movimentos = []
    atual = None
    limites = None

    def finalizar():
        nonlocal atual

        if not atual:
            return

        descricao = " ".join(
            atual["descricao"]
        ).strip()

        if (
            descricao
            and atual["valor"] is not None
        ):
            movimentos.append(
                _registro(
                    atual["data"],
                    descricao,
                    atual["valor"],
                    conta,
                    campos_configurados,
                )
            )

        atual = None

    for pagina in pdf.pages:
        limites_pagina = _limites_colunas(pagina)

        if limites_pagina:
            limites = limites_pagina

        if not limites:
            continue

        for linha in _linhas_visuais(pagina):
            if not linha:
                continue

            textos = [
                p["text"].strip()
                for p in linha
                if p["text"].strip()
            ]

            if not textos:
                continue

            texto_linha = " ".join(textos).strip()
            chave_linha = _texto_ascii(texto_linha).strip()
            primeira = textos[0]

            if chave_linha.startswith("SALDO"):
                finalizar()
                continue

            if _RE_DATA.fullmatch(primeira):
                finalizar()

                descricao = []
                debito = None
                credito = None

                for palavra in linha[1:]:
                    texto = palavra["text"].strip()
                    x0 = float(palavra["x0"])

                    if (
                        limites["lancamento"]
                        <= x0
                        < limites["debito"]
                    ):
                        descricao.append(texto)

                    elif (
                        limites["debito"]
                        <= x0
                        < limites["credito"]
                    ):
                        if _RE_VALOR.fullmatch(texto):
                            debito = _valor_brasileiro(texto)

                    elif (
                        limites["credito"]
                        <= x0
                        < limites["saldo"]
                    ):
                        if _RE_VALOR.fullmatch(texto):
                            credito = _valor_brasileiro(texto)

                valor = None

                if debito is not None:
                    valor = -abs(debito)

                elif credito is not None:
                    valor = abs(credito)

                atual = {
                    "data": primeira,
                    "descricao": descricao,
                    "valor": valor,
                }

                continue

            if atual:
                partes = []

                for palavra in linha:
                    texto = palavra["text"].strip()
                    x0 = float(palavra["x0"])

                    if (
                        limites["lancamento"]
                        <= x0
                        < limites["debito"]
                    ):
                        partes.append(texto)

                if partes:
                    atual["descricao"].extend(partes)

    finalizar()

    return movimentos


def _configurar_tesseract():
    try:
        import pytesseract
    except ImportError as erro:
        raise RuntimeError(
            "Fallback OCR do Daycoval requer pytesseract."
        ) from erro

    caminhos = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(
            r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"
        ),
    ]

    for executavel in caminhos:
        if os.path.exists(executavel):
            pytesseract.pytesseract.tesseract_cmd = executavel
            break

    return pytesseract


def _ocr_data(imagem, pytesseract):
    try:
        return pytesseract.image_to_data(
            imagem,
            lang="por",
            config="--psm 6",
            output_type=pytesseract.Output.DICT,
        )
    except Exception:
        return pytesseract.image_to_data(
            imagem,
            lang="eng",
            config="--psm 6",
            output_type=pytesseract.Output.DICT,
        )


def _agrupar_ocr_por_linha(dados):
    linhas = {}

    total = len(dados.get("text", []))

    for i in range(total):
        texto = str(dados["text"][i] or "").strip()

        if not texto:
            continue

        chave = (
            dados["page_num"][i],
            dados["block_num"][i],
            dados["par_num"][i],
            dados["line_num"][i],
        )

        linhas.setdefault(chave, []).append({
            "text": texto,
            "left": int(dados["left"][i]),
            "top": int(dados["top"][i]),
            "width": int(dados["width"][i]),
        })

    resultado = []

    for palavras in linhas.values():
        palavras.sort(
            key=lambda item: item["left"]
        )

        resultado.append({
            "top": min(p["top"] for p in palavras),
            "palavras": palavras,
            "texto": " ".join(
                p["text"]
                for p in palavras
            ),
        })

    resultado.sort(
        key=lambda item: item["top"]
    )

    return resultado


def _valor_ocr(texto):
    texto = str(texto or "").strip()
    texto = texto.replace("R$", "").replace(" ", "")

    texto = (
        texto
        .replace("O", "0")
        .replace("o", "0")
    )

    resultado = re.search(
        r"-?\d{1,3}(?:\.\d{3})*,\d{2}"
        r"|-?\d+,\d{2}",
        texto
    )

    if not resultado:
        return None

    try:
        return _valor_brasileiro(
            resultado.group(0)
        )
    except ValueError:
        return None


def _extrair_conta_ocr(textos):
    texto_total = "\n".join(textos)

    conta = _extrair_conta_texto(
        texto_total
    )

    if conta:
        return conta

    linhas = [
        re.sub(r"\s+", " ", linha).strip()
        for linha in texto_total.splitlines()
        if linha.strip()
    ]

    for indice, linha in enumerate(linhas):
        if _texto_ascii(linha).strip() == "CONTA":
            for proxima in linhas[indice + 1:indice + 4]:
                numero = re.search(
                    r"\b0*\d{6,12}\b",
                    proxima
                )

                if numero:
                    return numero.group(0)

    return None


def _extrair_movimentos_ocr(
    caminho,
    campos_configurados
):
    """
    Fallback exclusivo para PDFs Daycoval sem camada de texto.
    Usa o mesmo Tesseract já adotado no projeto.
    """
    try:
        import pymupdf
        from PIL import Image
    except ImportError as erro:
        raise RuntimeError(
            "Fallback OCR do Daycoval requer "
            "pymupdf e pillow."
        ) from erro

    pytesseract = _configurar_tesseract()

    documento = pymupdf.open(caminho)

    paginas = []
    textos_ocr = []

    try:
        for pagina in documento:
            pixmap = pagina.get_pixmap(
                matrix=pymupdf.Matrix(2.5, 2.5),
                alpha=False
            )

            imagem = Image.open(
                io.BytesIO(
                    pixmap.tobytes("png")
                )
            )

            dados = _ocr_data(
                imagem,
                pytesseract
            )

            linhas = _agrupar_ocr_por_linha(
                dados
            )

            paginas.append({
                "largura": imagem.width,
                "linhas": linhas,
            })

            textos_ocr.append(
                "\n".join(
                    linha["texto"]
                    for linha in linhas
                )
            )

    finally:
        documento.close()

    conta = _extrair_conta_ocr(
        textos_ocr
    )

    if not conta:
        raise ValueError(
            f"Conta não encontrada no OCR do PDF Daycoval: "
            f"{caminho}"
        )

    movimentos = []

    for pagina in paginas:
        largura = float(pagina["largura"])

        # As colunas do Daycoval ocupam posições estáveis
        # proporcionalmente à largura da página.
        #
        # Data | Nº Docto | Lançamento | Débito | Crédito | Saldo
        limite_doc = 0.125 * largura
        limite_lanc = 0.205 * largura
        limite_debito = 0.665 * largura
        limite_credito = 0.775 * largura
        limite_saldo = 0.885 * largura

        atual = None

        def finalizar_ocr():
            nonlocal atual

            if not atual:
                return

            descricao = " ".join(
                atual["descricao"]
            ).strip()

            if (
                descricao
                and atual["valor"] is not None
            ):
                movimentos.append(
                    _registro(
                        atual["data"],
                        descricao,
                        atual["valor"],
                        conta,
                        campos_configurados,
                    )
                )

            atual = None

        for linha in pagina["linhas"]:
            texto_linha = linha["texto"].strip()
            chave = _texto_ascii(texto_linha).strip()

            if not texto_linha:
                continue

            if chave.startswith("SALDO"):
                finalizar_ocr()
                continue

            resultado_data = re.match(
                r"^(\d{2}/\d{2}/\d{4})\b",
                texto_linha
            )

            if resultado_data:
                finalizar_ocr()

                data = resultado_data.group(1)
                descricao = []
                debito = None
                credito = None

                for palavra in linha["palavras"]:
                    texto = palavra["text"].strip()
                    centro = (
                        palavra["left"]
                        + palavra["width"] / 2
                    )

                    if centro < limite_doc:
                        continue

                    if (
                        limite_lanc
                        <= centro
                        < limite_debito
                    ):
                        descricao.append(texto)

                    elif (
                        limite_debito
                        <= centro
                        < limite_credito
                    ):
                        valor = _valor_ocr(texto)

                        if valor is not None:
                            debito = valor

                    elif (
                        limite_credito
                        <= centro
                        < limite_saldo
                    ):
                        valor = _valor_ocr(texto)

                        if valor is not None:
                            credito = valor

                # Remove Data e Nº Docto caso o OCR tenha deslocado
                # algum token para dentro da faixa do histórico.
                descricao = [
                    item
                    for item in descricao
                    if not _RE_DATA.fullmatch(item)
                ]

                valor = None

                if debito is not None:
                    valor = -abs(debito)

                elif credito is not None:
                    valor = abs(credito)

                atual = {
                    "data": data,
                    "descricao": descricao,
                    "valor": valor,
                }

                continue

            # Continuação de histórico em linha seguinte.
            if atual:
                partes = []

                for palavra in linha["palavras"]:
                    centro = (
                        palavra["left"]
                        + palavra["width"] / 2
                    )

                    if (
                        limite_lanc
                        <= centro
                        < limite_debito
                    ):
                        partes.append(
                            palavra["text"].strip()
                        )

                if partes:
                    atual["descricao"].extend(
                        partes
                    )

        finalizar_ocr()

    return movimentos


def extrair_daycoval_dist(
    caminho_pdf,
    campos_configurados=None
):
    # APLIC não pertence ao extrato bancário que estamos importando.
    nome_arquivo = os.path.basename(
        str(caminho_pdf)
    )

    if "APLIC" in _texto_ascii(nome_arquivo):
        return []

    with pdfplumber.open(caminho_pdf) as pdf:
        texto = _texto_pdf(pdf)

        # PDF imagem: usa Tesseract somente como fallback.
        if not texto.strip():
            return _extrair_movimentos_ocr(
                caminho_pdf,
                campos_configurados
            )

        conta = _extrair_conta_texto(
            texto
        )

        if not conta:
            raise ValueError(
                f"Conta não encontrada no conteúdo do PDF Daycoval: "
                f"{caminho_pdf}"
            )

        movimentos = _extrair_movimentos_texto(
            pdf,
            conta,
            campos_configurados
        )

    if not movimentos:
        raise ValueError(
            f"Nenhum movimento financeiro válido encontrado "
            f"no PDF Daycoval: {caminho_pdf}"
        )

    return movimentos