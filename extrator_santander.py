import re
import unicodedata

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


def localizar_conta_santander(df):
    # Exceção específica do Santander:
    # a Conta fica fora da tabela.

    chave_conta = normalizar_chave(
        "Conta"
    )

    for linha in range(len(df)):

        for coluna in range(
            len(df.columns)
        ):

            valor = df.iat[
                linha,
                coluna
            ]

            if pd.isna(valor):
                continue

            if (
                normalizar_chave(valor)
                != chave_conta
            ):
                continue

            # Encontrou a palavra CONTA.
            # Procura o primeiro valor preenchido
            # à direita dela.
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

    return None


def localizar_linha_cabecalho(
    df,
    campos_configurados=None
):
    campos_normalizados = {
        normalizar_chave(campo)
        for campo in (
            campos_configurados
            or []
        )
        if (
            normalizar_chave(campo)
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

    for indice in range(limite):

        chaves_linha = {
            normalizar_chave(valor)
            for valor
            in df.iloc[indice]
            if (
                pd.notna(valor)
                and str(valor).strip()
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
            "Santander: não foi possível "
            "localizar o cabeçalho do arquivo."
        )

    return melhor_linha


def extrair_santander_excel(
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
    # Fica fora da tabela.
    # --------------------------------------------

    conta = localizar_conta_santander(
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

        if pd.isna(nome_coluna):
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
    # FILTRA SOMENTE CAMPOS CONFIGURADOS
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

        # Não interpreta o conteúdo.
        # Pega exatamente o valor da célula
        # pertencente à coluna encontrada.
        for (
            indice,
            chave
        ) in colunas_retorno.items():

            valor = linha.iloc[
                indice
            ]

            if pd.isna(valor):

                valor = None

            else:

                possui_dados = True

            registro[
                chave
            ] = valor

        # Conta é adicionada separadamente
        # porque está fora da tabela.
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