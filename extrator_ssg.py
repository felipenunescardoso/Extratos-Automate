import re
import unicodedata
from decimal import Decimal

import pdfplumber


def normalizar_chave(texto):
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

    return re.sub(
        r"[^A-Z0-9]",
        "",
        texto
    )


def converter_valor(valor):
    if valor is None:
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    resultado = re.search(
        r"(-?)R\$\s*([\d.]+,\d{2})",
        texto
    )

    if resultado:
        negativo = resultado.group(1) == "-"
        numero_texto = resultado.group(2)
    else:
        resultado = re.search(
            r"(-?)[\d.]+,\d{2}",
            texto
        )

        if not resultado:
            return None

        numero_bruto = resultado.group(0)
        negativo = numero_bruto.startswith("-")
        numero_texto = numero_bruto.lstrip("-")

    numero_texto = (
        numero_texto
        .replace(".", "")
        .replace(",", ".")
    )

    numero = Decimal(
        numero_texto
    )

    if negativo:
        numero = -numero

    return numero


def extrair_conta_ssg(texto):
    resultado = re.search(
        r"(\d{4,}-\d+)\s+Data\s+Inicial:",
        texto,
        re.IGNORECASE
    )

    if resultado:
        return resultado.group(1)

    return None


def obter_campo_configurado(
    campos,
    nome_campo
):
    return campos.get(
        normalizar_chave(
            nome_campo
        )
    )


def preencher_campo(
    registro,
    campos,
    nome_campo,
    valor
):
    campo = obter_campo_configurado(
        campos,
        nome_campo
    )

    if campo is not None:
        registro[campo] = valor


def juntar_palavras(palavras):
    if not palavras:
        return ""

    palavras = sorted(
        palavras,
        key=lambda item: (
            round(item["top"], 1),
            item["x0"]
        )
    )

    linhas = []
    linha_atual = []
    top_atual = None

    for palavra in palavras:
        top = palavra["top"]

        if (
            top_atual is None
            or abs(top - top_atual) <= 3
        ):
            linha_atual.append(
                palavra
            )

            if top_atual is None:
                top_atual = top

        else:
            linha_atual = sorted(
                linha_atual,
                key=lambda item: item["x0"]
            )

            linhas.append(
                " ".join(
                    item["text"]
                    for item in linha_atual
                )
            )

            linha_atual = [
                palavra
            ]

            top_atual = top

    if linha_atual:
        linha_atual = sorted(
            linha_atual,
            key=lambda item: item["x0"]
        )

        linhas.append(
            " ".join(
                item["text"]
                for item in linha_atual
            )
        )

    return " ".join(
        linha.strip()
        for linha in linhas
        if linha.strip()
    ).strip()


def localizar_cabecalho_tabela(palavras):
    """
    Localiza verticalmente o cabeçalho da tabela SSG.

    A separação dos dados será feita pela posição horizontal
    das colunas, e não pelo conteúdo do Número Documento.
    """

    candidatos_data = [
        palavra
        for palavra in palavras
        if normalizar_chave(
            palavra["text"]
        ) == "DATA"
    ]

    for palavra_data in candidatos_data:
        top = palavra_data["top"]

        mesma_linha = [
            palavra
            for palavra in palavras
            if abs(
                palavra["top"] - top
            ) <= 3
        ]

        texto_linha = normalizar_chave(
            " ".join(
                palavra["text"]
                for palavra in mesma_linha
            )
        )

        if (
            "NUMERODOCUMENTO" in texto_linha
            and "HISTORICO" in texto_linha
            and "LANCAMENTO" in texto_linha
            and "SALDO" in texto_linha
        ):
            return top

    return None


def limites_colunas_ssg(largura_pagina):
    """
    O layout SSG possui cinco colunas fixas.

    Os limites são proporcionais à largura da página,
    para não depender de conteúdo ou texto específico
    dentro de Número Documento / Histórico.

    Data
    Número Documento
    Histórico
    Lançamento
    Saldo
    """

    return {
        "DATA": (
            0,
            largura_pagina * 0.16
        ),
        "NUMERODOCUMENTO": (
            largura_pagina * 0.16,
            largura_pagina * 0.35
        ),
        "HISTORICO": (
            largura_pagina * 0.35,
            largura_pagina * 0.70
        ),
        "LANCAMENTO": (
            largura_pagina * 0.70,
            largura_pagina * 0.84
        ),
        "SALDO": (
            largura_pagina * 0.84,
            largura_pagina
        )
    }


def palavras_da_coluna(
    palavras,
    limite_inicial,
    limite_final
):
    return [
        palavra
        for palavra in palavras
        if (
            palavra["x0"] >= limite_inicial
            and palavra["x0"] < limite_final
        )
    ]


def extrair_registros_pagina(
    pagina,
    campos,
    conta
):
    palavras = pagina.extract_words(
        keep_blank_chars=False,
        use_text_flow=False
    )

    if not palavras:
        return []

    top_cabecalho = localizar_cabecalho_tabela(
        palavras
    )

    if top_cabecalho is None:
        return []

    limites = limites_colunas_ssg(
        pagina.width
    )

    palavras_dados = [
        palavra
        for palavra in palavras
        if palavra["top"] > (
            top_cabecalho + 5
        )
    ]

    # Cada lançamento começa por uma data na primeira coluna.
    datas = []

    for palavra in palavras_dados:
        if not re.fullmatch(
            r"\d{2}/\d{2}/\d{4}",
            palavra["text"].strip()
        ):
            continue

        inicio_data, fim_data = limites[
            "DATA"
        ]

        if (
            palavra["x0"] >= inicio_data
            and palavra["x0"] < fim_data
        ):
            datas.append(
                palavra
            )

    datas = sorted(
        datas,
        key=lambda item: item["top"]
    )

    if not datas:
        return []

    top_totais = None

    for palavra in palavras_dados:
        if normalizar_chave(
            palavra["text"]
        ) == "TOTAIS":
            mesma_linha = [
                item
                for item in palavras_dados
                if abs(
                    item["top"] - palavra["top"]
                ) <= 3
            ]

            texto_linha = normalizar_chave(
                " ".join(
                    item["text"]
                    for item in mesma_linha
                )
            )

            if "TOTAISDOPERIODO" in texto_linha:
                top_totais = palavra["top"]
                break

    registros = []

    for indice, palavra_data in enumerate(
        datas
    ):
        top_data = palavra_data["top"]

        if indice == 0:
            limite_superior = (
                top_cabecalho + 5
            )
        else:
            limite_superior = (
                datas[indice - 1]["top"]
                + top_data
            ) / 2

        if indice + 1 < len(datas):
            limite_inferior = (
                top_data
                + datas[indice + 1]["top"]
            ) / 2
        else:
            limite_inferior = (
                top_totais
                if top_totais is not None
                else pagina.height
            )

        palavras_registro = [
            palavra
            for palavra in palavras_dados
            if (
                palavra["top"]
                >= limite_superior
                and palavra["top"]
                < limite_inferior
            )
        ]

        registro = {
            campo: None
            for campo in campos.values()
        }

        preencher_campo(
            registro,
            campos,
            "Data",
            palavra_data["text"].strip()
        )

        # Conta = exceção SSG fora da tabela.
        preencher_campo(
            registro,
            campos,
            "Conta",
            conta
        )

        inicio, fim = limites[
            "NUMERODOCUMENTO"
        ]

        numero_documento = juntar_palavras(
            palavras_da_coluna(
                palavras_registro,
                inicio,
                fim
            )
        )

        preencher_campo(
            registro,
            campos,
            "Número Documento",
            numero_documento
        )

        inicio, fim = limites[
            "HISTORICO"
        ]

        historico = juntar_palavras(
            palavras_da_coluna(
                palavras_registro,
                inicio,
                fim
            )
        )

        preencher_campo(
            registro,
            campos,
            "Histórico",
            historico
        )

        inicio, fim = limites[
            "LANCAMENTO"
        ]

        lancamento_texto = juntar_palavras(
            palavras_da_coluna(
                palavras_registro,
                inicio,
                fim
            )
        )

        preencher_campo(
            registro,
            campos,
            "Lançamento (R$)",
            converter_valor(
                lancamento_texto
            )
        )

        inicio, fim = limites[
            "SALDO"
        ]

        saldo_texto = juntar_palavras(
            palavras_da_coluna(
                palavras_registro,
                inicio,
                fim
            )
        )

        preencher_campo(
            registro,
            campos,
            "Saldo (R$)",
            converter_valor(
                saldo_texto
            )
        )

        registros.append(
            registro
        )

    return registros


def extrair_ssg_pdf(
    caminho,
    campos_configurados
):
    campos = {
        normalizar_chave(campo): campo
        for campo in campos_configurados
    }

    registros = []

    with pdfplumber.open(caminho) as pdf:
        texto_completo = "\n".join(
            pagina.extract_text() or ""
            for pagina in pdf.pages
        )

        conta = extrair_conta_ssg(
            texto_completo
        )

        for pagina in pdf.pages:
            registros.extend(
                extrair_registros_pagina(
                    pagina,
                    campos,
                    conta
                )
            )

    return registros