import os
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


def converter_valor_bb(valor):
    if valor is None:
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    resultado_sinal = re.search(
        r"\b([CD])\b\s*$",
        texto,
        flags=re.IGNORECASE
    )

    sinal = (
        resultado_sinal.group(1).upper()
        if resultado_sinal
        else None
    )

    resultado_numero = re.search(
        r"(-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2})",
        texto
    )

    if not resultado_numero:
        return None

    numero = (
        resultado_numero.group(1)
        .replace(".", "")
        .replace(",", ".")
    )

    valor_decimal = Decimal(numero)

    if sinal == "D":
        return -abs(valor_decimal)

    if sinal == "C":
        return abs(valor_decimal)

    return valor_decimal


def localizar_conta_corrente_bb_dist(pdf):
    """
    Localiza a conta corrente fora da tabela.

    Exemplos suportados:
        Conta corrente 105435-X 76 OIL COMBUSTIVEIS
        Conta corrente 105435-X76 OIL COMBUSTIVEIS
        Conta corrente: 105435-X
        Conta corrente 000000112577

    Captura somente o número da conta, sem carregar
    o nome da empresa que pode vir colado no texto.
    """

    padroes = (
        # Formato BB com dígito após hífen, inclusive X.
        r"Conta\s+corrente\s*:?\s*0*([0-9]{1,12}-[0-9X])",

        # Alguns PDFs podem trazer a conta sem hífen.
        r"Conta\s+corrente\s*:?\s*0*([0-9]{4,12})",
    )

    for pagina in pdf.pages[:3]:
        texto = pagina.extract_text() or ""

        # Normaliza apenas espaços para evitar quebra de linha
        # entre "Conta" e "corrente".
        texto = re.sub(
            r"\s+",
            " ",
            texto
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
    selecionadas = [
        palavra["text"]
        for palavra in palavras
        if (
            palavra["x0"] >= x_inicio
            and palavra["x0"] < x_fim
        )
    ]

    return " ".join(
        selecionadas
    ).strip()


def obter_limites_colunas(pagina):
    largura = float(pagina.width)
    return {
        "dt_balancete": (0.000 * largura, 0.190 * largura),
        "dt_movimento": (0.190 * largura, 0.300 * largura),
        "ag_origem": (0.300 * largura, 0.370 * largura),
        "lote": (0.370 * largura, 0.415 * largura),
        "historico": (0.415 * largura, 0.610 * largura),
        "documento": (0.610 * largura, 0.790 * largura),
        "valor": (0.790 * largura, 0.910 * largura),
        "saldo": (0.910 * largura, 1.010 * largura)
    }


def localizar_data_na_linha(
    palavras,
    limites
):
    data_balancete_txt = texto_intervalo(
        palavras,
        *limites["dt_balancete"]
    )

    data_movimento_txt = texto_intervalo(
        palavras,
        *limites["dt_movimento"]
    )

    padrao_data = re.compile(
        r"\b\d{2}/\d{2}/\d{4}\b"
    )

    resultado_balancete = (
        padrao_data.search(
            data_balancete_txt
        )
    )

    resultado_movimento = (
        padrao_data.search(
            data_movimento_txt
        )
    )

    dt_balancete = (
        resultado_balancete.group(0)
        if resultado_balancete
        else None
    )

    dt_movimento = (
        resultado_movimento.group(0)
        if resultado_movimento
        else None
    )

    if (
        dt_movimento is None
        and dt_balancete is not None
    ):
        dt_movimento = (
            dt_balancete
        )

    return (
        dt_balancete,
        dt_movimento
    )


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



_PADRAO_DATA_BB = re.compile(
    r"^\d{2}/\d{2}/\d{4}$"
)

_PADRAO_DINHEIRO_BB = re.compile(
    r"^-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}$"
)

_PADRAO_DOCUMENTO_BB = re.compile(
    r"^[0-9][0-9.]*$"
)


def _centro_vertical(palavra):
    return (
        float(palavra["top"])
        + float(palavra["bottom"])
    ) / 2


def _pares_monetarios_bb(palavras):
    """
    Retorna pares (valor, C/D) encontrados geometricamente
    da esquerda para a direita.

    O primeiro par é o Valor R$ do movimento.
    O segundo, quando existe, é o Saldo.
    """

    palavras_ordenadas = sorted(
        palavras,
        key=lambda item: float(item["x0"])
    )

    pares = []

    for indice, palavra in enumerate(
        palavras_ordenadas
    ):
        texto = str(
            palavra["text"]
        ).strip()

        if not _PADRAO_DINHEIRO_BB.match(
            texto
        ):
            continue

        sinal = None

        for seguinte in palavras_ordenadas[
            indice + 1:
            indice + 4
        ]:
            texto_seguinte = str(
                seguinte["text"]
            ).strip().upper()

            if texto_seguinte in (
                "C",
                "D"
            ):
                sinal = texto_seguinte
                break

        if sinal is not None:
            pares.append(
                (
                    palavra,
                    sinal
                )
            )

    return pares


def _juntar_palavras_sem_duplicar(
    base,
    extras
):
    vistos = {
        (
            str(item["text"]),
            round(float(item["x0"]), 2),
            round(float(item["top"]), 2),
        )
        for item in base
    }

    resultado = list(base)

    for item in extras:
        chave = (
            str(item["text"]),
            round(float(item["x0"]), 2),
            round(float(item["top"]), 2),
        )

        if chave in vistos:
            continue

        resultado.append(item)
        vistos.add(chave)

    return resultado


def _completar_linha_movimento_bb(
    linhas,
    indice
):
    """
    O BB às vezes desloca o valor/sinal alguns pixels para cima
    ou quebra Histórico/Documento/Valor na linha imediatamente
    seguinte.

    Em vez de depender de faixas fixas de coluna, recompõe apenas
    o bloco visual do próprio lançamento.
    """

    linha = linhas[indice]

    palavras = list(
        linha["palavras"]
    )

    top_referencia = float(
        linha["top"]
    )

    # Caso raro: valor monetário é renderizado alguns pixels acima
    # da data, embora visualmente pertença à mesma linha.
    if indice > 0:
        anterior = linhas[
            indice - 1
        ]

        distancia = (
            top_referencia
            - float(anterior["top"])
        )

        if 0 < distancia <= 7:
            palavras_anterior = anterior[
                "palavras"
            ]

            tem_dinheiro = any(
                _PADRAO_DINHEIRO_BB.match(
                    str(p["text"]).strip()
                )
                for p in palavras_anterior
            )

            somente_regiao_financeira = all(
                float(p["x0"]) > 400
                for p in palavras_anterior
            )

            if (
                tem_dinheiro
                and somente_regiao_financeira
            ):
                palavras = (
                    _juntar_palavras_sem_duplicar(
                        palavras,
                        palavras_anterior
                    )
                )

    pares = _pares_monetarios_bb(
        palavras
    )

    # Se ainda não encontramos Valor + C/D, a linha principal pode
    # ter sido quebrada. Junta no máximo as duas linhas seguintes,
    # desde que não comecem outro lançamento.
    proximo = indice + 1

    while (
        not pares
        and proximo < len(linhas)
        and proximo <= indice + 2
    ):
        palavras_proxima = linhas[
            proximo
        ]["palavras"]

        if any(
            _PADRAO_DATA_BB.match(
                str(p["text"]).strip()
            )
            for p in palavras_proxima
        ):
            break

        palavras = (
            _juntar_palavras_sem_duplicar(
                palavras,
                palavras_proxima
            )
        )

        pares = _pares_monetarios_bb(
            palavras
        )

        proximo += 1

    return palavras



def _descricao_linha_continuacao_bb(linhas, indice):
    """
    Retorna a linha imediatamente seguinte quando ela é continuação
    visual do lançamento atual.

    No extrato BB, beneficiário/remetente/detalhe costuma vir na
    segunda linha sem uma nova data completa DD/MM/YYYY.
    """
    proximo = indice + 1

    if proximo >= len(linhas):
        return None

    palavras = linhas[proximo]["palavras"]

    # Se houver uma nova data completa, já é outro lançamento.
    if any(
        _PADRAO_DATA_BB.match(
            str(palavra["text"]).strip()
        )
        for palavra in palavras
    ):
        return None

    texto = " ".join(
        str(palavra["text"]).strip()
        for palavra in sorted(
            palavras,
            key=lambda item: float(item["x0"])
        )
        if str(palavra["text"]).strip()
    ).strip()

    if not texto:
        return None

    texto_normalizado = normalizar_chave(texto)

    # Não carregar cabeçalhos/rodapés para o histórico.
    ignorar = (
        "LANCAMENTOS",
        "DTBALANCETE",
        "DTMOVIMENTO",
        "TRANSACAOEFETUADACOMSUCESSO",
        "SERVICODEATENDIMENTOAOCONSUMIDOR",
        "PARADEFICIENTESAUDITIVOS",
    )

    if any(
        texto_normalizado.startswith(item)
        for item in ignorar
    ):
        return None

    return texto


def _parse_movimento_bb(
    palavras
):
    palavras = sorted(
        palavras,
        key=lambda item: float(item["x0"])
    )

    palavra_data = next(
        (
            p
            for p in palavras
            if _PADRAO_DATA_BB.match(
                str(p["text"]).strip()
            )
        ),
        None
    )

    if palavra_data is None:
        return None

    data = str(
        palavra_data["text"]
    ).strip()

    pares = _pares_monetarios_bb(
        palavras
    )

    if not pares:
        return None

    palavra_valor, sinal_valor = (
        pares[0]
    )

    palavra_saldo = None
    sinal_saldo = None

    if len(pares) >= 2:
        palavra_saldo, sinal_saldo = (
            pares[1]
        )

    valor = converter_valor_bb(
        f"{palavra_valor['text']} "
        f"{sinal_valor}"
    )

    saldo = None

    if palavra_saldo is not None:
        saldo = converter_valor_bb(
            f"{palavra_saldo['text']} "
            f"{sinal_saldo}"
        )

    # Agência
    ag_origem = None

    for palavra in palavras:
        texto = str(
            palavra["text"]
        ).strip()

        if (
            175
            <= float(palavra["x0"])
            < 220
            and re.fullmatch(
                r"\d{4}",
                texto
            )
        ):
            ag_origem = texto
            break

    # Lote + começo do histórico.
    lote = None
    historico_partes = []

    for palavra in palavras:
        texto = str(
            palavra["text"]
        ).strip()

        x0 = float(
            palavra["x0"]
        )

        if not (
            215 <= x0 < 340
        ):
            continue

        resultado_lote = re.match(
            r"^(\d{5})(.*)$",
            texto
        )

        if (
            lote is None
            and resultado_lote
        ):
            lote = (
                resultado_lote
                .group(1)
            )

            restante = (
                resultado_lote
                .group(2)
                .strip()
            )

            if restante:
                historico_partes.append(
                    (
                        x0,
                        restante
                    )
                )

            continue

        historico_partes.append(
            (
                x0,
                texto
            )
        )

    # Documento = último token puramente numérico/pontuado
    # situado antes do Valor R$.
    candidatos_documento = [
        palavra
        for palavra in palavras
        if (
            float(palavra["x0"]) > 300
            and float(
                palavra["x1"]
            )
            <= float(
                palavra_valor["x0"]
            ) + 1
            and _PADRAO_DOCUMENTO_BB.match(
                str(
                    palavra["text"]
                ).strip()
            )
        )
    ]

    documento = None
    palavra_documento = None

    if candidatos_documento:
        palavra_documento = max(
            candidatos_documento,
            key=lambda item: float(
                item["x0"]
            )
        )

        documento = str(
            palavra_documento["text"]
        ).strip()

    # Completa o histórico entre lote e documento.
    limite_historico = (
        float(
            palavra_documento["x0"]
        )
        if palavra_documento
        is not None
        else float(
            palavra_valor["x0"]
        )
    )

    for palavra in palavras:
        texto = str(
            palavra["text"]
        ).strip()

        x0 = float(
            palavra["x0"]
        )

        if (
            250 <= x0
            < limite_historico
            and palavra
            is not palavra_documento
        ):
            if (
                texto == ag_origem
                or texto == lote
                or _PADRAO_DATA_BB.match(
                    texto
                )
            ):
                continue

            historico_partes.append(
                (
                    x0,
                    texto
                )
            )

    # Remove duplicações ocasionais quando uma palavra caiu
    # exatamente no encontro das duas faixas.
    historico_final = []
    vistos = set()

    for _, texto in sorted(
        historico_partes,
        key=lambda item: item[0]
    ):
        chave = (
            texto,
            len(historico_final)
        )

        # evita apenas repetição imediatamente consecutiva
        if (
            historico_final
            and historico_final[-1]
            == texto
        ):
            continue

        historico_final.append(
            texto
        )

    historico = " ".join(
        historico_final
    ).strip()

    historico_normalizado = (
        normalizar_chave(
            historico
        )
    )

    # Linhas informativas de saldo não são movimentos.
    if (
        historico_normalizado
        in (
            "SALDO",
            "SALDOANTERIOR",
        )
        or documento is None
    ):
        return None

    return {
        "data": data,
        "ag_origem": ag_origem,
        "lote": lote,
        "historico": historico or None,
        "documento": documento,
        "valor": valor,
        "saldo": saldo,
    }




def _localizar_tesseract_bb():
    """
    Localiza o Tesseract no Windows somente quando o fallback OCR
    realmente for necessário.
    """
    import pytesseract

    candidatos = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Programs",
            "Tesseract-OCR",
            "tesseract.exe",
        ),
    ]

    for caminho in candidatos:
        if caminho and os.path.isfile(caminho):
            pytesseract.pytesseract.tesseract_cmd = caminho
            return caminho

    # Se estiver no PATH, o próprio pytesseract conseguirá executar.
    return None


def _extrair_palavras_ocr_bb(caminho):
    """
    OCR do BB para PDFs que são apenas imagem.

    Retorna uma lista por página contendo palavras com x0/x1/top/bottom,
    no mesmo formato esperado pelo parser geométrico já existente.
    """
    import pymupdf
    import pytesseract
    from PIL import Image
    from pytesseract import Output

    _localizar_tesseract_bb()

    documento = pymupdf.open(caminho)
    paginas = []

    try:
        for pagina in documento:
            matriz = pymupdf.Matrix(2.5, 2.5)
            pix = pagina.get_pixmap(
                matrix=matriz,
                alpha=False,
            )

            imagem = Image.frombytes(
                "RGB",
                (pix.width, pix.height),
                pix.samples,
            )

            dados = None

            # Português primeiro; inglês como fallback, seguindo o padrão
            # dos demais extratores OCR do projeto.
            for idioma in ("por", "eng"):
                try:
                    dados = pytesseract.image_to_data(
                        imagem,
                        lang=idioma,
                        config="--psm 6",
                        output_type=Output.DICT,
                    )
                    break
                except Exception:
                    dados = None

            if not dados:
                paginas.append([])
                continue

            palavras = []

            # Converte coordenadas do bitmap de volta para o sistema
            # de coordenadas do PDF. Assim o parser atual do BB continua
            # trabalhando com as mesmas faixas x0/x1.
            escala_x = float(pagina.rect.width) / float(imagem.width)
            escala_y = float(pagina.rect.height) / float(imagem.height)

            for i, texto in enumerate(dados.get("text", [])):
                texto = str(texto or "").strip()

                if not texto:
                    continue

                try:
                    confianca = float(dados["conf"][i])
                except Exception:
                    confianca = -1

                if confianca < 0:
                    continue

                esquerda = float(dados["left"][i])
                topo = float(dados["top"][i])
                largura = float(dados["width"][i])
                altura = float(dados["height"][i])

                palavras.append({
                    "text": texto,
                    "x0": esquerda * escala_x,
                    "x1": (esquerda + largura) * escala_x,
                    "top": topo * escala_y,
                    "bottom": (topo + altura) * escala_y,
                })

            paginas.append(palavras)

    finally:
        documento.close()

    return paginas



def _eh_bb_rende_facil_ocr(paginas_palavras):
    """
    Identifica extrato de aplicação BB Rende Fácil pelo conteúdo,
    sem depender do nome do arquivo.

    Esses documentos não pertencem ao extrato de conta corrente
    importado pelo BB Distribuidoras e devem ser ignorados.
    """
    textos = []

    for palavras in paginas_palavras[:2]:
        for palavra in palavras:
            texto = str(
                palavra.get("text", "")
            ).strip()

            if texto:
                textos.append(texto)

    texto_normalizado = normalizar_chave(
        " ".join(textos)
    )

    # O título é suficiente quando reconhecido pelo OCR.
    if "BBRENDEFACIL" in texto_normalizado:
        return True

    # Fallback para pequenas falhas do OCR no título:
    # exige características próprias do relatório de aplicação.
    indicadores = (
        "APLICACOESNOMES",
        "RESGATESLIQUIDOSNOMES",
        "RENDIMENTOSNOMES",
        "HISTORICODEMOVIMENTACAO",
    )

    encontrados = sum(
        indicador in texto_normalizado
        for indicador in indicadores
    )

    return encontrados >= 2


def _localizar_conta_corrente_bb_ocr(paginas_palavras):
    """
    Localiza a conta corrente no OCR.

    Prioriza contas com dígito verificador (ex.: 10770-0, 5630-8,
    5626-X). Só depois tenta conta sem hífen. Isso evita capturar
    datas/períodos do cabeçalho, como 202609.
    """
    linhas_candidatas = []

    for palavras in paginas_palavras[:3]:
        linhas = agrupar_palavras_por_linha(
            palavras,
            tolerancia=4,
        )

        textos_linhas = [
            " ".join(
                str(p["text"]).strip()
                for p in linha["palavras"]
                if str(p["text"]).strip()
            )
            for linha in linhas
        ]

        for texto_linha in textos_linhas:
            normal = re.sub(r"\s+", " ", texto_linha).strip()
            chave = normalizar_chave(normal)

            if "CONTA" not in chave or "CORRENTE" not in chave:
                continue

            # Aceita tanto "Conta corrente" quanto "Contacorrente".
            resultado_rotulo = re.search(
                r"conta\s*corrente",
                normal,
                flags=re.IGNORECASE,
            )

            if not resultado_rotulo:
                continue

            depois = normal[resultado_rotulo.end():]
            depois = re.sub(r"(?<=\d)\s+(?=\d)", "", depois)
            depois = re.sub(r"\s*-\s*", "-", depois)
            linhas_candidatas.append(depois)

    # 1) Prioridade absoluta: conta com dígito verificador.
    for depois in linhas_candidatas:
        resultado = re.search(
            r"\b0*([0-9]{1,12}-[0-9XO])",
            depois,
            flags=re.IGNORECASE,
        )
        if resultado:
            conta = resultado.group(1).upper().strip()
            # OCR: O no dígito verificador do BB representa zero.
            if conta.endswith("-O"):
                conta = conta[:-1] + "0"
            return conta

    # 2) Somente se nenhuma conta com hífen foi encontrada.
    # Limita ao começo do trecho após o rótulo para não pegar datas.
    for depois in linhas_candidatas:
        resultado = re.match(
            r"^\s*:?[ ]*0*([0-9]{4,12})(?:\s|$)",
            depois,
        )
        if resultado:
            return resultado.group(1).strip()

    return None

def _registro_conta_nao_movimentada_bb(
    paginas_palavras,
    conta_corrente,
    campos_configurados=None,
):
    """Gera uma linha informativa para extrato BB válido sem movimentação."""
    textos = []
    datas = []

    for palavras in paginas_palavras:
        for palavra in palavras:
            texto = str(palavra.get("text", "")).strip()
            if not texto:
                continue

            textos.append(texto)

            if _PADRAO_DATA_BB.match(texto):
                datas.append(texto)

    if "ACONTANAOFOIMOVIMENTADA" not in normalizar_chave(" ".join(textos)):
        return None

    # Prefere a data final do período do extrato. Isso evita usar
    # a data/hora de impressão do Internet Banking como data da linha.
    texto_completo = " ".join(textos)
    periodo = re.search(
        r"(?:ate|até)\s*(\d{2}/\d{2}/\d{4})",
        texto_completo,
        flags=re.IGNORECASE,
    )

    data = periodo.group(1) if periodo else (datas[-1] if datas else None)

    registro = {
        normalizar_chave("Dt. balancete"): data,
        normalizar_chave("Dt. movimento"): data,
        normalizar_chave("Ag. origem"): None,
        normalizar_chave("Lote"): None,
        normalizar_chave("Histórico"): "A CONTA NAO FOI MOVIMENTADA",
        normalizar_chave("Documento"): None,
        normalizar_chave("Valor R$"): Decimal("0.00"),
        normalizar_chave("Saldo"): Decimal("0.00"),
        normalizar_chave("Conta"): conta_corrente,
    }

    return filtrar_campos_configurados(registro, campos_configurados)


def _processar_paginas_bb(
    paginas_palavras,
    conta_corrente,
    campos_configurados=None,
):
    """
    Processa palavras já extraídas, sejam do pdfplumber ou do OCR.
    Mantém um único parser para texto e imagem.
    """
    registros = []

    for palavras in paginas_palavras:
        if not palavras:
            continue

        linhas = agrupar_palavras_por_linha(
            palavras
        )

        for indice, linha in enumerate(linhas):
            palavras_linha = linha["palavras"]

            possui_data = any(
                _PADRAO_DATA_BB.match(
                    str(palavra["text"]).strip()
                )
                for palavra in palavras_linha
            )

            if not possui_data:
                continue

            palavras_movimento = _completar_linha_movimento_bb(
                linhas,
                indice,
            )

            movimento = _parse_movimento_bb(
                palavras_movimento
            )

            if movimento is None:
                continue

            complemento = _descricao_linha_continuacao_bb(
                linhas,
                indice,
            )

            if complemento:
                historico_atual = str(
                    movimento.get("historico") or ""
                ).strip()

                movimento["historico"] = (
                    f"{historico_atual} {complemento}"
                ).strip()

            registro = {
                normalizar_chave("Dt. balancete"): movimento["data"],
                normalizar_chave("Dt. movimento"): movimento["data"],
                normalizar_chave("Ag. origem"): movimento["ag_origem"],
                normalizar_chave("Lote"): movimento["lote"],
                normalizar_chave("Histórico"): movimento["historico"],
                normalizar_chave("Documento"): movimento["documento"],
                normalizar_chave("Valor R$"): movimento["valor"],
                normalizar_chave("Saldo"): movimento["saldo"],
                normalizar_chave("Conta"): conta_corrente,
            }

            registro = filtrar_campos_configurados(
                registro,
                campos_configurados,
            )

            registros.append(registro)

    return registros


def extrair_bb_dist_pdf(
    caminho,
    campos_configurados=None
):
    """
    Extrator Banco do Brasil - Distribuidoras.

    Caminho normal:
        PDF com camada de texto -> pdfplumber.

    Fallback:
        PDF somente imagem -> Tesseract OCR.

    O mesmo parser geométrico é usado nos dois caminhos, preservando
    Documento / Valor / Saldo e a concatenação da segunda linha do
    descritivo.
    """
    # Regra de aplicação BB:
    # se "RENDE" aparecer em qualquer parte do nome do arquivo,
    # não pertence ao extrato de conta corrente.
    nome_arquivo_normalizado = normalizar_chave(
        os.path.basename(caminho)
    )

    if "RENDE" in nome_arquivo_normalizado:
        return []

    paginas_texto = []

    with pdfplumber.open(caminho) as pdf:
        conta_corrente = localizar_conta_corrente_bb_dist(
            pdf
        )

        for pagina in pdf.pages:
            palavras = pagina.extract_words(
                use_text_flow=False,
                keep_blank_chars=False,
                x_tolerance=2,
            ) or []

            paginas_texto.append(palavras)

    # Mantém exatamente o caminho já usado para PDFs normais.
    if any(paginas_texto):
        return _processar_paginas_bb(
            paginas_texto,
            conta_corrente,
            campos_configurados,
        )

    # PDF sem camada de texto: fallback OCR.
    paginas_ocr = _extrair_palavras_ocr_bb(
        caminho
    )

    if not any(paginas_ocr):
        raise ValueError(
            f"PDF BB sem texto e OCR não encontrou conteúdo: {caminho}"
        )

    # BB Rende Fácil é relatório de aplicação, não extrato de conta
    # corrente. Ignora pelo conteúdo, mesmo quando o nome do arquivo
    # não contém APLIC.
    if _eh_bb_rende_facil_ocr(
        paginas_ocr
    ):
        return []

    conta_corrente = _localizar_conta_corrente_bb_ocr(
        paginas_ocr
    )

    if not conta_corrente:
        raise ValueError(
            f"Conta corrente não encontrada no PDF BB via OCR: {caminho}"
        )

    # Primeiro processa os movimentos reais. Alguns extratos BB exibem
    # "A CONTA NAO FOI MOVIMENTADA" no fechamento de um dia/período,
    # mesmo contendo movimentos no restante do extrato.
    registros = _processar_paginas_bb(
        paginas_ocr,
        conta_corrente,
        campos_configurados,
    )

    if registros:
        return registros

    # A mensagem fixa só pode ser usada quando nenhum movimento
    # financeiro foi encontrado no documento inteiro.
    registro_sem_movimento = _registro_conta_nao_movimentada_bb(
        paginas_ocr,
        conta_corrente,
        campos_configurados,
    )

    if registro_sem_movimento is not None:
        return [registro_sem_movimento]

    raise ValueError(
        f"Nenhum movimento financeiro válido encontrado no PDF BB via OCR: {caminho}"
    )
