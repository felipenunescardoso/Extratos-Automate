import re
import unicodedata
from datetime import date
from decimal import Decimal

import pdfplumber


# ============================================================
# FUNÇÕES INTERNAS
# ============================================================

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
        _normalizar_texto(texto)
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
        .replace("–", "-")
        .replace("—", "-")
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


def _extrair_periodo(texto):
    resultado = re.search(
        r"PER[IÍ]ODO\s*-\s*"
        r"(\d{2}/\d{2}/\d{4})\s*-\s*"
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
    Layout Planner observado:

        44006 - 76 OIL DISTRIBUIDORA DE COMBUSTIVEIS S.A.

    O código antes do hífen é tratado como Conta.
    """
    linhas = [
        re.sub(
            r"\s+",
            " ",
            linha
        ).strip()
        for linha in texto.splitlines()
        if linha.strip()
    ]

    for linha in linhas:
        resultado = re.match(
            r"^\s*(\d{3,})\s+-\s+.+$",
            linha
        )

        if resultado:
            return resultado.group(1)

    return None


def _data_com_ano(data_texto, inicio_periodo):
    data_texto = str(data_texto or "").strip()

    for formato in (
        "%d/%m/%Y",
        "%d/%m/%y"
    ):
        try:
            from datetime import datetime

            return datetime.strptime(
                data_texto,
                formato
            ).date()

        except ValueError:
            pass

    resultado = re.fullmatch(
        r"(\d{1,2})/(\d{1,2})",
        data_texto
    )

    if not resultado or inicio_periodo is None:
        return None

    dia = int(
        resultado.group(1)
    )

    mes = int(
        resultado.group(2)
    )

    candidatos = [
        inicio_periodo.year - 1,
        inicio_periodo.year,
        inicio_periodo.year + 1
    ]

    def distancia(ano):
        try:
            candidato = date(
                ano,
                mes,
                dia
            )
        except ValueError:
            return 10**9

        return abs(
            (candidato - inicio_periodo).days
        )

    ano = min(
        candidatos,
        key=distancia
    )

    try:
        return date(
            ano,
            mes,
            dia
        )
    except ValueError:
        return None


def _eh_linha_ignorada(texto):
    texto = _normalizar_texto(texto)

    termos = (
        "SALDO ANTERIOR",
        "CLIENTE SEM MOVIMENTACAO NO PERIODO",
        "SELECIONADO DE",
        "TOTAL CLIENTE",
        "DISPONIVEL",
        "RESULTADO",
        "BLOQUEADO",
        "PROJETADO",
    )

    return any(
        termo in texto
        for termo in termos
    )


def _extrair_por_linha(
    linha,
    inicio_periodo,
    conta
):
    """
    Fallback textual para linhas no formato esperado:

        05/01 05/01 HISTORICO 100,00 1.000,00
        05/01/2026 05/01/2026 HISTORICO -100,00 1.000,00

    Caso haja 3 valores monetários:
        Débito | Crédito | Saldo

    Caso haja 2:
        Valor | Saldo

    No layout posicional principal, Débito e Crédito são
    identificados pelas colunas do PDF.
    """

    if _eh_linha_ignorada(
        linha
    ):
        return None

    resultado = re.match(
        r"^\s*"
        r"(\d{1,2}/\d{1,2}(?:/\d{2,4})?)"
        r"(?:\s+"
        r"(\d{1,2}/\d{1,2}(?:/\d{2,4})?))?"
        r"\s+(.+)$",
        linha
    )

    if not resultado:
        return None

    data_liq = resultado.group(1)
    data_mov = resultado.group(2)
    restante = resultado.group(3).strip()

    valores = list(
        re.finditer(
            r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}",
            restante
        )
    )

    if not valores:
        return None

    saldo = None
    valor = None

    if len(valores) >= 3:
        debito = _converter_valor(
            valores[-3].group(0)
        )

        credito = _converter_valor(
            valores[-2].group(0)
        )

        saldo = _converter_valor(
            valores[-1].group(0)
        )

        if debito not in (
            None,
            Decimal("0")
        ):
            valor = -abs(
                debito
            )
        elif credito is not None:
            valor = abs(
                credito
            )

        inicio_descricao = valores[-3].start()

    elif len(valores) == 2:
        valor = _converter_valor(
            valores[-2].group(0)
        )

        saldo = _converter_valor(
            valores[-1].group(0)
        )

        inicio_descricao = valores[-2].start()

    else:
        valor = _converter_valor(
            valores[-1].group(0)
        )

        inicio_descricao = valores[-1].start()

    descricao = restante[
        :inicio_descricao
    ].strip()

    if (
        not descricao
        or valor is None
        or _eh_linha_ignorada(
            descricao
        )
    ):
        return None

    data_movimento = _data_com_ano(
        data_mov or data_liq,
        inicio_periodo
    )

    if data_movimento is None:
        return None

    return {
        "DATA": data_movimento.strftime(
            "%d/%m/%Y"
        ),
        "HISTORICO": descricao,
        "VALOR": valor,
        "SALDO": saldo,
        "CONTA": conta
    }


def _agrupar_palavras_por_linha(pagina):
    palavras = pagina.extract_words(
        x_tolerance=2,
        y_tolerance=2,
        keep_blank_chars=False
    )

    if not palavras:
        return []

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
            ) <= 2.5:
                linha["palavras"].append(
                    palavra
                )
                adicionada = True
                break

        if not adicionada:
            linhas.append({
                "top": palavra["top"],
                "palavras": [
                    palavra
                ]
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


def _localizar_colunas(pagina):
    """
    Usa o cabeçalho do próprio PDF para obter as posições
    de Débito, Crédito e Saldo.
    """

    palavras = pagina.extract_words(
        x_tolerance=2,
        y_tolerance=2
    )

    candidatos = []

    for palavra in palavras:
        chave = _normalizar_texto(
            palavra["text"]
        )

        if chave in (
            "LIQ",
            "MOV",
            "HISTORICO",
            "DEBITO",
            "CREDITO",
            "SALDO"
        ):
            candidatos.append({
                "nome": chave,
                "x0": palavra["x0"],
                "top": palavra["top"]
            })

    # O cabeçalho útil é o conjunto em uma mesma linha
    # contendo LIQ, MOV e HISTORICO.
    grupos = {}

    for item in candidatos:
        chave_top = round(
            item["top"] / 3
        ) * 3

        grupos.setdefault(
            chave_top,
            []
        ).append(
            item
        )

    for itens in grupos.values():
        nomes = {
            item["nome"]
            for item in itens
        }

        if not {
            "LIQ",
            "MOV",
            "HISTORICO",
            "DEBITO",
            "CREDITO",
            "SALDO"
        }.issubset(
            nomes
        ):
            continue

        posicoes = {}

        for nome in (
            "LIQ",
            "MOV",
            "HISTORICO",
            "DEBITO",
            "CREDITO",
            "SALDO"
        ):
            posicoes[nome] = min(
                item["x0"]
                for item in itens
                if item["nome"] == nome
            )

        posicoes["TOP"] = min(
            item["top"]
            for item in itens
        )

        return posicoes

    return None


def _valor_coluna(
    palavras,
    inicio_x,
    fim_x=None
):
    selecionadas = []

    for palavra in palavras:
        centro = (
            palavra["x0"]
            + palavra["x1"]
        ) / 2

        if centro < inicio_x:
            continue

        if (
            fim_x is not None
            and centro >= fim_x
        ):
            continue

        selecionadas.append(
            palavra["text"]
        )

    if not selecionadas:
        return None

    texto = " ".join(
        selecionadas
    )

    valores = re.findall(
        r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}",
        texto
    )

    if not valores:
        return None

    return _converter_valor(
        valores[-1]
    )


def _extrair_posicional(
    pagina,
    inicio_periodo,
    conta
):
    colunas = _localizar_colunas(
        pagina
    )

    if not colunas:
        return []

    linhas = _agrupar_palavras_por_linha(
        pagina
    )

    registros = []

    limite_hist = (
        colunas["DEBITO"]
        + colunas["HISTORICO"]
    ) / 2

    limite_debito_credito = (
        colunas["DEBITO"]
        + colunas["CREDITO"]
    ) / 2

    limite_credito_saldo = (
        colunas["CREDITO"]
        + colunas["SALDO"]
    ) / 2

    for linha in linhas:
        if linha["top"] <= colunas["TOP"] + 3:
            continue

        palavras = linha["palavras"]

        texto_linha = " ".join(
            palavra["text"]
            for palavra in palavras
        )

        if _eh_linha_ignorada(
            texto_linha
        ):
            continue

        # Datas são esperadas nas primeiras colunas.
        datas = [
            palavra["text"]
            for palavra in palavras
            if re.fullmatch(
                r"\d{1,2}/\d{1,2}(?:/\d{2,4})?",
                palavra["text"]
            )
        ]

        if not datas:
            continue

        data_movimento = _data_com_ano(
            datas[1]
            if len(datas) >= 2
            else datas[0],
            inicio_periodo
        )

        if data_movimento is None:
            continue

        historico_palavras = [
            palavra["text"]
            for palavra in palavras
            if (
                (
                    palavra["x0"]
                    + palavra["x1"]
                ) / 2
                >= colunas["HISTORICO"]
                and (
                    (
                        palavra["x0"]
                        + palavra["x1"]
                    ) / 2
                    < limite_hist
                )
                and not re.fullmatch(
                    r"\d{1,2}/\d{1,2}(?:/\d{2,4})?",
                    palavra["text"]
                )
            )
        ]

        historico = " ".join(
            historico_palavras
        ).strip()

        debito = _valor_coluna(
            palavras,
            limite_hist,
            limite_debito_credito
        )

        credito = _valor_coluna(
            palavras,
            limite_debito_credito,
            limite_credito_saldo
        )

        saldo = _valor_coluna(
            palavras,
            limite_credito_saldo,
            None
        )

        valor = None

        if debito not in (
            None,
            Decimal("0")
        ):
            valor = -abs(
                debito
            )

        elif credito is not None:
            valor = abs(
                credito
            )

        if (
            valor is None
            or not historico
            or _eh_linha_ignorada(
                historico
            )
        ):
            continue

        registros.append({
            "DATA": data_movimento.strftime(
                "%d/%m/%Y"
            ),
            "HISTORICO": historico,
            "VALOR": valor,
            "SALDO": saldo,
            "CONTA": conta
        })

    return registros


# ============================================================
# EXTRATOR PÚBLICO
# ============================================================

def extrair_pl_dist_pdf(
    caminho,
    campos_configurados=None
):
    """
    Extrator Planner - Distribuidoras.

    Campos:
        DATA
        HISTORICO
        VALOR
        SALDO
        CONTA

    Regras:
        - conta obtida do código antes do nome do cliente;
        - Débito vira valor negativo;
        - Crédito vira valor positivo;
        - cliente sem movimentação retorna lista vazia;
        - período do PDF determina o ano quando a linha usa DD/MM.
    """

    caminho = str(
        caminho
    )

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

        texto_completo = "\n".join(
            textos_paginas
        )

        texto_normalizado = _normalizar_texto(
            texto_completo
        )

        if (
            "EXTRATO DE CONTAS CORRENTES"
            not in texto_normalizado
            or "CTAS CORRENTES"
            not in texto_normalizado
        ):
            raise ValueError(
                "Layout do Banco Planner não reconhecido."
            )

        inicio_periodo, fim_periodo = (
            _extrair_periodo(
                texto_completo
            )
        )

        if inicio_periodo is None:
            raise ValueError(
                "Não foi possível identificar o período "
                "no extrato Planner."
            )

        conta = _extrair_conta(
            texto_completo
        )

        if not conta:
            raise ValueError(
                "Não foi possível identificar a conta "
                "no extrato Planner."
            )

        # Layout explicitamente sem movimentação.
        # Gera uma linha informativa para registrar o período.
        if (
            "CLIENTE SEM MOVIMENTACAO NO PERIODO"
            in texto_normalizado
        ):
            registro_sem_movimento = {
                "DATA": fim_periodo.strftime(
                    "%d/%m/%Y"
                ),
                "HISTORICO": (
                    "CLIENTE SEM MOVIMENTAÇÃO NO PERÍODO"
                ),
                "VALOR": Decimal("0.00"),
                "SALDO": Decimal("0.00"),
                "CONTA": conta
            }

            return [
                _filtrar_campos_configurados(
                    registro_sem_movimento,
                    campos_configurados
                )
            ]

        registros = []

        for pagina, texto_pagina in zip(
            pdf.pages,
            textos_paginas
        ):
            registros_pagina = (
                _extrair_posicional(
                    pagina,
                    inicio_periodo,
                    conta
                )
            )

            registros.extend(
                registros_pagina
            )

            # Fallback para layouts onde a posição das colunas
            # não seja preservada pelo PDF.
            if not registros_pagina:
                for linha in texto_pagina.splitlines():
                    linha = re.sub(
                        r"\s+",
                        " ",
                        linha
                    ).strip()

                    if not linha:
                        continue

                    registro = _extrair_por_linha(
                        linha,
                        inicio_periodo,
                        conta
                    )

                    if registro is not None:
                        registros.append(
                            registro
                        )

    # Remove duplicidade causada por eventual coincidência
    # entre leitura posicional e fallback.
    unicos = []
    vistos = set()

    for registro in registros:
        chave = (
            registro.get("DATA"),
            registro.get("HISTORICO"),
            registro.get("VALOR"),
            registro.get("SALDO"),
            registro.get("CONTA"),
        )

        if chave in vistos:
            continue

        vistos.add(
            chave
        )

        unicos.append(
            _filtrar_campos_configurados(
                registro,
                campos_configurados
            )
        )

    return unicos