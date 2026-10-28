import re
import unicodedata
from decimal import Decimal

import pandas as pd


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
    if valor is None or pd.isna(valor):
        return None

    if isinstance(
        valor,
        (int, float, Decimal)
    ):
        return Decimal(
            str(valor)
        )

    texto = str(
        valor
    ).strip()

    if not texto:
        return None

    negativo = (
        texto.startswith("-")
        or (
            texto.startswith("(")
            and texto.endswith(")")
        )
    )

    texto = (
        texto
        .replace("R$", "")
        .replace("(", "")
        .replace(")", "")
        .replace("-", "")
        .replace(".", "")
        .replace(",", ".")
        .strip()
    )

    if not texto:
        return None

    numero = Decimal(
        texto
    )

    if negativo:
        numero = -numero

    return numero


def localizar_conta_itau(df):
    """
    Exceção específica do Itaú:
    a Conta fica fora da tabela.

    Procura a palavra CONTA e retorna
    o primeiro valor preenchido à direita.

    Também aceita casos como:
    Conta: 12345-6
    """

    chave_conta = normalizar_chave(
        "Conta"
    )

    limite_linhas = min(
        len(df),
        30
    )

    for linha in range(
        limite_linhas
    ):

        for coluna in range(
            len(df.columns)
        ):

            valor = df.iat[
                linha,
                coluna
            ]

            if pd.isna(valor):
                continue

            texto = str(
                valor
            ).strip()

            # ----------------------------------------
            # CONTA EM CÉLULA SEPARADA
            # ----------------------------------------

            if (
                normalizar_chave(texto)
                == chave_conta
            ):

                for deslocamento in range(
                    1,
                    4
                ):

                    proxima_coluna = (
                        coluna
                        + deslocamento
                    )

                    if (
                        proxima_coluna
                        >= len(df.columns)
                    ):
                        break

                    candidato = df.iat[
                        linha,
                        proxima_coluna
                    ]

                    if (
                        pd.notna(candidato)
                        and str(
                            candidato
                        ).strip()
                    ):
                        return str(
                            candidato
                        ).strip()

            # ----------------------------------------
            # CONTA NA MESMA CÉLULA
            # Ex:
            # Conta: 12345-6
            # ----------------------------------------

            resultado = re.match(
                r"^\s*CONTA\s*:?\s*(.+)$",
                texto,
                re.IGNORECASE
            )

            if resultado:

                conta = resultado.group(
                    1
                ).strip()

                if conta:
                    return conta

    return None


def localizar_linha_cabecalho(
    df,
    campos_configurados=None
):
    """
    Localiza o cabeçalho usando os próprios
    campos configurados no DE/PARA.

    Conta não participa porque fica
    fora da tabela.
    """

    campos_normalizados = {
        normalizar_chave(
            campo
        )
        for campo
        in (
            campos_configurados
            or []
        )
        if (
            normalizar_chave(
                campo
            )
            != normalizar_chave(
                "Conta"
            )
        )
    }

    melhor_linha = None
    maior_quantidade = 0

    limite = min(
        len(df),
        50
    )

    for indice in range(
        limite
    ):

        chaves_linha = {
            normalizar_chave(
                valor
            )
            for valor
            in df.iloc[indice]
            if (
                pd.notna(valor)
                and str(
                    valor
                ).strip()
            )
        }

        if campos_normalizados:

            quantidade = len(
                chaves_linha
                & campos_normalizados
            )

        else:

            quantidade = len(
                chaves_linha
            )

        if (
            quantidade
            > maior_quantidade
        ):

            maior_quantidade = (
                quantidade
            )

            melhor_linha = indice

    if melhor_linha is None:
        raise ValueError(
            "IT: não foi possível localizar "
            "o cabeçalho do arquivo."
        )

    return melhor_linha


def extrair_it_excel(
    caminho,
    campos_configurados=None
):

    df_bruto = pd.read_excel(
        caminho,
        header=None,
        dtype=object
    )

    if df_bruto.empty:
        return []

    # --------------------------------------------
    # CONTA
    # ÚNICA EXCEÇÃO ESPECÍFICA DO ITAÚ
    # --------------------------------------------

    conta = localizar_conta_itau(
        df_bruto
    )

    # --------------------------------------------
    # CABEÇALHO
    # --------------------------------------------

    linha_cabecalho = (
        localizar_linha_cabecalho(
            df_bruto,
            campos_configurados
        )
    )

    cabecalho = df_bruto.iloc[
        linha_cabecalho
    ]

    colunas = {}

    for (
        indice,
        nome_coluna
    ) in cabecalho.items():

        if pd.isna(
            nome_coluna
        ):
            continue

        nome_coluna = str(
            nome_coluna
        ).strip()

        if not nome_coluna:
            continue

        chave = normalizar_chave(
            nome_coluna
        )

        if chave:

            colunas[
                indice
            ] = chave

    # --------------------------------------------
    # CAMPOS CONFIGURADOS NO DE/PARA
    # --------------------------------------------

    if campos_configurados:

        campos_normalizados = {
            normalizar_chave(
                campo
            )
            for campo
            in campos_configurados
        }

        colunas_retorno = {
            indice: chave
            for (
                indice,
                chave
            ) in colunas.items()
            if (
                chave
                in campos_normalizados
            )
        }

        incluir_conta = (
            normalizar_chave(
                "Conta"
            )
            in campos_normalizados
        )

    else:

        colunas_retorno = dict(
            colunas
        )

        incluir_conta = True

    # --------------------------------------------
    # DADOS
    # --------------------------------------------

    dados = df_bruto.iloc[
        linha_cabecalho + 1:
    ]

    registros = []

    for _, linha in dados.iterrows():

        registro = {}
        possui_dados = False

        for (
            indice,
            chave
        ) in colunas_retorno.items():

            valor = linha.iloc[
                indice
            ]

            if pd.isna(valor):

                valor = None

            # Valor e Saldo:
            # apenas conversão numérica.
            elif (
                "VALOR" in chave
                or "SALDO" in chave
            ):

                valor = converter_valor(
                    valor
                )

            # Data / Lançamento / demais:
            # conteúdo integral da célula.
            else:

                valor = str(
                    valor
                ).strip()

            if valor is not None:
                possui_dados = True

            registro[
                chave
            ] = valor

        # ----------------------------------------
        # CONTA FORA DA TABELA
        # ----------------------------------------

        if incluir_conta:

            registro[
                normalizar_chave(
                    "Conta"
                )
            ] = conta

        if possui_dados:

            registros.append(
                registro
            )

    return registros