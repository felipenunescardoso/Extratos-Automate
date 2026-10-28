import os
import re
import shutil
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pdfplumber


_RE_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_RE_DINHEIRO = re.compile(
    r"^\(?-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}\)?$"
)


def _decimal_br(texto):
    if texto is None:
        return None

    texto = str(texto).strip()

    if not texto:
        return None

    texto = (
        texto.replace("R$", "")
        .replace("r$", "")
        .replace(" ", "")
    )

    negativo_parenteses = (
        texto.startswith("(")
        and texto.endswith(")")
    )

    if negativo_parenteses:
        texto = texto[1:-1]

    texto = texto.replace(".", "").replace(",", ".")

    try:
        valor = Decimal(texto)
    except InvalidOperation as erro:
        raise ValueError(
            f"Valor monetário inválido no extrato Ourinvest: {texto}"
        ) from erro

    if negativo_parenteses:
        valor = -abs(valor)

    return valor


def _eh_dinheiro(texto):
    return bool(
        _RE_DINHEIRO.match(
            str(texto or "").strip()
        )
    )


def _agrupar_linhas(pagina, tolerancia=2.0):
    palavras = pagina.extract_words(
        x_tolerance=1,
        y_tolerance=2,
        keep_blank_chars=False,
        use_text_flow=False,
    )

    if not palavras:
        return []

    linhas = []

    for palavra in sorted(
        palavras,
        key=lambda item: (
            float(item["top"]),
            float(item["x0"]),
        ),
    ):
        top = float(palavra["top"])

        linha_encontrada = None

        for linha in linhas:
            if abs(linha["top"] - top) <= tolerancia:
                linha_encontrada = linha
                break

        if linha_encontrada is None:
            linha_encontrada = {
                "top": top,
                "bottom": float(palavra["bottom"]),
                "palavras": [],
            }
            linhas.append(linha_encontrada)

        linha_encontrada["palavras"].append(palavra)
        linha_encontrada["bottom"] = max(
            linha_encontrada["bottom"],
            float(palavra["bottom"]),
        )

    for linha in linhas:
        linha["palavras"].sort(
            key=lambda item: float(item["x0"])
        )

    return linhas


def _texto_linha(linha):
    return " ".join(
        str(palavra["text"]).strip()
        for palavra in linha["palavras"]
        if str(palavra["text"]).strip()
    ).strip()


def _configurar_tesseract():
    try:
        import pytesseract
    except ImportError:
        return None

    caminho = shutil.which("tesseract")

    if not caminho:
        caminho_windows = (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        )

        if os.path.exists(caminho_windows):
            caminho = caminho_windows

    if caminho:
        pytesseract.pytesseract.tesseract_cmd = caminho

    return pytesseract


def _ocr_celula_monetaria(
    pagina,
    x0,
    x1,
    top,
    bottom,
):
    pytesseract = _configurar_tesseract()

    if pytesseract is None:
        return None

    margem_y = 4

    recorte = pagina.crop(
        (
            max(0, x0),
            max(0, top - margem_y),
            min(pagina.width, x1),
            min(pagina.height, bottom + margem_y),
        )
    )

    imagem = recorte.to_image(
        resolution=300
    ).original

    texto = pytesseract.image_to_string(
        imagem,
        config="--psm 7",
    )

    candidatos = re.findall(
        r"\(?-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}\)?",
        texto,
    )

    if not candidatos:
        return None

    return _decimal_br(
        candidatos[-1]
    )


def _replicar_saldo_mes(registros):
    saldo_por_mes = {}

    for registro in registros:
        saldo = registro.get("SALDO")

        if saldo is None:
            continue

        data_registro = datetime.strptime(
            registro["DATA"],
            "%d/%m/%Y",
        ).date()

        chave_mes = (
            data_registro.year,
            data_registro.month,
        )

        if chave_mes not in saldo_por_mes:
            saldo_por_mes[chave_mes] = saldo

    for registro in registros:
        if registro.get("SALDO") is not None:
            continue

        data_registro = datetime.strptime(
            registro["DATA"],
            "%d/%m/%Y",
        ).date()

        chave_mes = (
            data_registro.year,
            data_registro.month,
        )

        if chave_mes in saldo_por_mes:
            registro["SALDO"] = saldo_por_mes[chave_mes]

    return registros


def _extrair_layout_ultimos_lancamentos(pagina):
    registros = []

    for linha in _agrupar_linhas(pagina):
        palavras = linha["palavras"]

        if not palavras:
            continue

        data_texto = str(
            palavras[0]["text"]
        ).strip()

        if not _RE_DATA.match(data_texto):
            continue

        historico_partes = []
        valor = None
        saldo = None

        for palavra in palavras[1:]:
            texto = str(
                palavra["text"]
            ).strip()

            x0 = float(
                palavra["x0"]
            )

            if x0 >= 490 and _eh_dinheiro(texto):
                saldo = _decimal_br(texto)

            elif x0 >= 340 and _eh_dinheiro(texto):
                valor = _decimal_br(texto)

            elif x0 < 340:
                historico_partes.append(texto)

        if valor is None:
            continue

        historico = " ".join(
            historico_partes
        ).strip()

        if not historico:
            continue

        registros.append(
            {
                "DATA": data_texto,
                "HISTORICO": historico,
                "VALOR": valor,
                "SALDO": saldo,
            }
        )

    return registros


def _extrair_layout_internet_banking(pagina):
    registros = []
    ultimo_registro = None
    ultimo_top = None

    for linha in _agrupar_linhas(pagina):
        palavras = linha["palavras"]

        if not palavras:
            continue

        texto_linha = _texto_linha(linha)

        primeiro = str(
            palavras[0]["text"]
        ).strip()

        if _RE_DATA.match(primeiro):
            historico_partes = []
            valor = None
            saldo = None

            for palavra in palavras[1:]:
                texto = str(
                    palavra["text"]
                ).strip()

                x0 = float(
                    palavra["x0"]
                )

                # Neste layout o valor começa aproximadamente
                # na região x >= 445 e o saldo x >= 520.
                if x0 >= 520 and _eh_dinheiro(texto):
                    saldo = _decimal_br(texto)

                elif x0 >= 445 and _eh_dinheiro(texto):
                    valor = _decimal_br(texto)

                elif x0 < 445:
                    historico_partes.append(texto)

            if valor is None:
                continue

            historico = " ".join(
                historico_partes
            ).strip()

            registro = {
                "DATA": primeiro,
                "HISTORICO": historico,
                "VALOR": valor,
                "SALDO": saldo,
            }

            registros.append(registro)
            ultimo_registro = registro
            ultimo_top = linha["top"]
            continue

        # Continuação de histórico quebrado em outra linha.
        if (
            ultimo_registro is not None
            and ultimo_top is not None
            and 0 < (
                linha["top"] - ultimo_top
            ) <= 18
        ):
            partes_continuacao = [
                str(palavra["text"]).strip()
                for palavra in palavras
                if 95 <= float(palavra["x0"]) < 445
            ]

            texto_continuacao = " ".join(
                partes_continuacao
            ).strip()

            bloqueios = (
                "Página Inicial",
                "Política",
                "Telefone",
                "Ouvidoria",
                "Copyright",
                "Mostrando",
                "Anterior",
                "Próxima",
                "Exportar",
            )

            if (
                texto_continuacao
                and not any(
                    item.lower()
                    in texto_linha.lower()
                    for item in bloqueios
                )
                and len(texto_continuacao) <= 120
            ):
                ultimo_registro[
                    "HISTORICO"
                ] = (
                    ultimo_registro["HISTORICO"]
                    + " "
                    + texto_continuacao
                ).strip()

    return registros


def _encontrar_colunas_relatorio(pagina):
    linhas = _agrupar_linhas(pagina)

    for linha in linhas:
        palavras = linha["palavras"]

        textos = [
            str(p["text"]).strip().lower()
            for p in palavras
        ]

        if (
            "crédito" in textos
            and "débito" in textos
            and "saldo" in textos
        ):
            posicoes = {}

            for palavra in palavras:
                chave = (
                    str(palavra["text"])
                    .strip()
                    .lower()
                )

                if chave in (
                    "crédito",
                    "débito",
                    "saldo",
                ):
                    posicoes[chave] = (
                        float(palavra["x0"])
                        + float(palavra["x1"])
                    ) / 2

            if len(posicoes) == 3:
                return posicoes

    return None


def _limites_colunas_relatorio(
    pagina,
    posicoes,
):
    credito = posicoes["crédito"]
    debito = posicoes["débito"]
    saldo = posicoes["saldo"]

    limite_cd = (
        credito + debito
    ) / 2

    limite_ds = (
        debito + saldo
    ) / 2

    largura_primeira = (
        limite_cd - credito
    )

    x_inicio_credito = max(
        0,
        credito - largura_primeira - 30,
    )

    return {
        "credito": (
            x_inicio_credito,
            limite_cd,
        ),
        "debito": (
            limite_cd,
            limite_ds,
        ),
        "saldo": (
            limite_ds,
            pagina.width,
        ),
    }


def _valor_coluna_por_palavras(
    palavras,
    x0_limite,
    x1_limite,
):
    candidatos = []

    for palavra in palavras:
        x_centro = (
            float(palavra["x0"])
            + float(palavra["x1"])
        ) / 2

        texto = str(
            palavra["text"]
        ).strip()

        if (
            x0_limite <= x_centro < x1_limite
            and _eh_dinheiro(texto)
        ):
            candidatos.append(
                _decimal_br(texto)
            )

    if not candidatos:
        return None

    return candidatos[-1]


def _extrair_layout_relatorio(pagina):
    posicoes = _encontrar_colunas_relatorio(
        pagina
    )

    if not posicoes:
        return []

    limites = _limites_colunas_relatorio(
        pagina,
        posicoes,
    )

    registros = []

    for linha in _agrupar_linhas(pagina):
        palavras = linha["palavras"]

        if not palavras:
            continue

        data_texto = str(
            palavras[0]["text"]
        ).strip()

        if not _RE_DATA.match(data_texto):
            continue

        credito = _valor_coluna_por_palavras(
            palavras,
            *limites["credito"],
        )

        debito = _valor_coluna_por_palavras(
            palavras,
            *limites["debito"],
        )

        saldo = _valor_coluna_por_palavras(
            palavras,
            *limites["saldo"],
        )

        # Quando a camada textual vem corrompida em uma célula
        # monetária, usa OCR somente naquela célula/linha.
        if credito is None:
            credito = _ocr_celula_monetaria(
                pagina,
                *limites["credito"],
                linha["top"],
                linha["bottom"],
            )

        if debito is None:
            debito = _ocr_celula_monetaria(
                pagina,
                *limites["debito"],
                linha["top"],
                linha["bottom"],
            )

        if saldo is None:
            saldo = _ocr_celula_monetaria(
                pagina,
                *limites["saldo"],
                linha["top"],
                linha["bottom"],
            )

        # Crédito e débito são as duas colunas que compõem o
        # movimento. Célula vazia é tratada como zero.
        credito = (
            credito
            if credito is not None
            else Decimal("0.00")
        )

        debito = (
            debito
            if debito is not None
            else Decimal("0.00")
        )

        valor = credito - debito

        # Evita linhas informativas que possuam data, mas não
        # representem movimento financeiro.
        if (
            credito == Decimal("0.00")
            and debito == Decimal("0.00")
            and saldo is None
        ):
            continue

        # Histórico = tudo entre a data e o início real das
        # colunas financeiras. Assim "BM", números e R$ dentro
        # do histórico permanecem no histórico.
        inicio_financeiro = limites[
            "credito"
        ][0]

        historico = " ".join(
            str(p["text"]).strip()
            for p in palavras[1:]
            if float(p["x0"]) < inicio_financeiro
        ).strip()

        if not historico:
            continue

        registros.append(
            {
                "DATA": data_texto,
                "HISTORICO": historico,
                "VALOR": valor,
                "SALDO": saldo,
            }
        )

    return registros



def _ocr_pagina(pagina):
    pytesseract = _configurar_tesseract()

    if pytesseract is None:
        return "", []

    imagem = pagina.to_image(
        resolution=220
    ).original

    texto = pytesseract.image_to_string(
        imagem,
        config="--psm 6",
    )

    dados = pytesseract.image_to_data(
        imagem,
        config="--psm 6",
        output_type=pytesseract.Output.DICT,
    )

    linhas = {}

    quantidade = len(
        dados.get("text", [])
    )

    for indice in range(quantidade):
        palavra = str(
            dados["text"][indice] or ""
        ).strip()

        if not palavra:
            continue

        chave = (
            dados["block_num"][indice],
            dados["par_num"][indice],
            dados["line_num"][indice],
        )

        linha = linhas.setdefault(
            chave,
            {
                "palavras": [],
                "top": int(dados["top"][indice]),
            },
        )

        linha["palavras"].append(
            {
                "text": palavra,
                "left": int(dados["left"][indice]),
                "width": int(dados["width"][indice]),
            }
        )

    linhas_ordenadas = []

    for linha in linhas.values():
        linha["palavras"].sort(
            key=lambda item: item["left"]
        )

        linha["texto"] = " ".join(
            item["text"]
            for item in linha["palavras"]
        ).strip()

        linhas_ordenadas.append(linha)

    linhas_ordenadas.sort(
        key=lambda item: item["top"]
    )

    return texto, linhas_ordenadas


def _extrair_layout_internet_banking_ocr(
    pagina,
    linhas_ocr,
):
    registros = []

    if not linhas_ocr:
        return registros

    largura_imagem = int(
        pagina.to_image(
            resolution=220
        ).original.width
    )

    # O layout visual do Internet Banking posiciona:
    # histórico à esquerda, valor na região ~78% e saldo ~90%.
    limite_valor = int(
        largura_imagem * 0.72
    )

    limite_saldo = int(
        largura_imagem * 0.86
    )

    ultimo_registro = None
    ultimo_top = None

    for linha in linhas_ocr:
        palavras = linha["palavras"]
        texto_linha = linha["texto"]

        if not palavras:
            continue

        primeiro = str(
            palavras[0]["text"]
        ).strip()

        if _RE_DATA.match(primeiro):
            historico_partes = []
            valor = None
            saldo = None

            for palavra in palavras[1:]:
                texto = str(
                    palavra["text"]
                ).strip()

                x0 = int(
                    palavra["left"]
                )

                if (
                    x0 >= limite_saldo
                    and _eh_dinheiro(texto)
                ):
                    saldo = _decimal_br(texto)

                elif (
                    x0 >= limite_valor
                    and _eh_dinheiro(texto)
                ):
                    valor = _decimal_br(texto)

                elif x0 < limite_valor:
                    historico_partes.append(texto)

            # Fallback por texto: pega os valores monetários do fim da linha.
            if valor is None:
                valores = re.findall(
                    r"\(?-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}\)?",
                    texto_linha,
                )

                if valores:
                    if len(valores) >= 2:
                        valor = _decimal_br(
                            valores[-2]
                        )

                        if saldo is None:
                            saldo = _decimal_br(
                                valores[-1]
                            )

                    else:
                        valor = _decimal_br(
                            valores[-1]
                        )

            if valor is None:
                continue

            historico = " ".join(
                historico_partes
            ).strip()

            # Remove valor/saldo colados no histórico pelo OCR.
            historico = re.sub(
                r"\s+\(?-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}\)?(?:\s+\(?-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}\)?)?$",
                "",
                historico,
            ).strip()

            if not historico:
                continue

            registro = {
                "DATA": primeiro,
                "HISTORICO": historico,
                "VALOR": valor,
                "SALDO": saldo,
            }

            registros.append(registro)
            ultimo_registro = registro
            ultimo_top = linha["top"]
            continue

        # Continuação curta do histórico quebrado pelo OCR.
        if (
            ultimo_registro is not None
            and ultimo_top is not None
            and 0 < (
                linha["top"] - ultimo_top
            ) <= 35
        ):
            texto_upper = texto_linha.upper()

            bloqueios = (
                "MOSTRANDO",
                "EXPORTAR",
                "PÁGINA INICIAL",
                "PAGINA INICIAL",
                "POLÍTICA",
                "POLITICA",
                "TELEFONE",
                "OUVIDORIA",
                "COPYRIGHT",
                "ANTERIOR",
                "PRÓXIMA",
                "PROXIMA",
            )

            if not any(
                item in texto_upper
                for item in bloqueios
            ):
                somente_historico = " ".join(
                    str(p["text"]).strip()
                    for p in palavras
                    if int(p["left"]) < limite_valor
                ).strip()

                if somente_historico:
                    ultimo_registro[
                        "HISTORICO"
                    ] = (
                        ultimo_registro["HISTORICO"]
                        + " "
                        + somente_historico
                    ).strip()

    return registros

def extrair_our_dist_pdf(
    caminho_pdf,
    campos=None,
):
    """
    OURINVEST - Distribuidoras.

    Layouts suportados:
      1) Extrato - Últimos lançamentos
      2) Internet Banking / Extrato - Movimentação Financeira
         com Filtro por período
      3) Relatório Extrato - Movimentação Financeira
         com Crédito / Débito / Saldo

    Regras:
      - sem movimentação -> ValueError tratado pelo Orquestrador;
      - Conta Garantida -> ignorada;
      - saldo ausente -> replica saldo encontrado no mesmo mês;
      - valor do relatório = Crédito - Débito;
      - saldo contábil entre parênteses é negativo.
    """

    caminho_pdf = str(
        caminho_pdf
    )

    registros = []
    layout_reconhecido = False

    with pdfplumber.open(
        caminho_pdf
    ) as pdf:

        textos_paginas = [
            pagina.extract_text(
                x_tolerance=2,
                y_tolerance=3,
            )
            or ""
            for pagina in pdf.pages
        ]

        texto_total = "\n".join(
            textos_paginas
        )

        paginas_ocr = {}

        # PDFs do Internet Banking podem vir como imagem pura.
        # Quando a camada textual não existe, usa OCR apenas como fallback.
        if not texto_total.strip():
            textos_ocr = []

            for indice, pagina in enumerate(
                pdf.pages
            ):
                texto_ocr, linhas_ocr = (
                    _ocr_pagina(
                        pagina
                    )
                )

                paginas_ocr[
                    indice
                ] = linhas_ocr

                textos_ocr.append(
                    texto_ocr
                )

            texto_total = "\n".join(
                textos_ocr
            )

        texto_total_normalizado = unicodedata.normalize(
            "NFKD",
            texto_total
        )

        texto_total_normalizado = "".join(
            caractere
            for caractere in texto_total_normalizado
            if not unicodedata.combining(
                caractere
            )
        ).upper()

        # Conta Garantida é outro produto bancário.
        if (
            "CONTA GARANTIDA PJ"
            in texto_total.upper()
            or (
                "EXTRATO DE C/C PARA SIMPLES CONFERÊNCIA"
                in texto_total.upper()
                and "CONTA GARANTIDA"
                in texto_total.upper()
            )
        ):
            raise ValueError(
                "Já existem lançamentos na data."
            )

        if (
            "Extrato - Últimos lançamentos"
            in texto_total
        ):
            layout_reconhecido = True

            for pagina in pdf.pages:
                registros.extend(
                    _extrair_layout_ultimos_lancamentos(
                        pagina
                    )
                )

        elif (
            "EXTRATO - MOVIMENTACAO FINANCEIRA"
            in texto_total_normalizado
            and (
                "FILTRO POR PERIODO"
                in texto_total_normalizado
                or "FILTRAR POR PERIODO"
                in texto_total_normalizado
            )
        ):
            layout_reconhecido = True

            for indice, pagina in enumerate(
                pdf.pages
            ):
                if indice in paginas_ocr:
                    registros.extend(
                        _extrair_layout_internet_banking_ocr(
                            pagina,
                            paginas_ocr[indice],
                        )
                    )
                else:
                    registros.extend(
                        _extrair_layout_internet_banking(
                            pagina
                        )
                    )

        elif (
            "EXTRATO - MOVIMENTACAO FINANCEIRA"
            in texto_total_normalizado
            and (
                "VLR. CREDITO"
                in texto_total_normalizado
                or "VALOR CREDITO"
                in texto_total_normalizado
            )
            and (
                "VLR. DEBITO"
                in texto_total_normalizado
                or "VALOR DEBITO"
                in texto_total_normalizado
            )
        ):
            layout_reconhecido = True

            for pagina in pdf.pages:
                registros.extend(
                    _extrair_layout_relatorio(
                        pagina
                    )
                )

    if not layout_reconhecido:
        raise ValueError(
            "Layout do Banco Ourinvest não reconhecido."
        )

    if not registros:
        raise ValueError(
            "Já existem lançamentos na data."
        )

    return _replicar_saldo_mes(
        registros
    )