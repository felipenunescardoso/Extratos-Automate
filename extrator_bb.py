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


def localizar_conta_corrente_bb(df):
    """
    Hardcode 1 do BB:
    a Conta corrente fica fora da tabela.

    Procura a célula cujo conteúdo normalizado seja
    CONTACORRENTE e retorna o primeiro valor preenchido
    à direita, preservando zeros à esquerda.
    """

    chave_conta = normalizar_chave(
        "Conta corrente"
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

            if (
                normalizar_chave(valor)
                != chave_conta
            ):
                continue

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
                    and str(candidato).strip()
                ):
                    return str(
                        candidato
                    ).strip()

    return None


def localizar_linha_cabecalho(
    df,
    campos_configurados=None
):
    """
    Localiza a linha de cabeçalho dando preferência
    aos campos configurados no DE/PARA.

    Conta corrente não participa porque fica fora da tabela.
    Inf. também não precisa estar no DE/PARA, pois é uma
    regra interna do BB.
    """

    campos_normalizados = {
        normalizar_chave(campo)
        for campo in (
            campos_configurados
            or []
        )
        if normalizar_chave(campo)
        != normalizar_chave(
            "Conta corrente"
        )
    }

    melhor_linha = None
    maior_quantidade = 0

    limite = min(
        len(df),
        30
    )

    for indice in range(
        limite
    ):
        chaves_linha = {
            normalizar_chave(valor)
            for valor in df.iloc[
                indice
            ]
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
            "BB: não foi possível localizar "
            "o cabeçalho do arquivo."
        )

    return melhor_linha


def converter_valor(valor):
    if (
        valor is None
        or pd.isna(valor)
    ):
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

    texto = (
        texto
        .replace("R$", "")
        .replace(".", "")
        .replace(",", ".")
        .strip()
    )

    if not texto:
        return None

    return Decimal(
        texto
    )


def extrair_bb_excel(
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

    # ------------------------------------------------
    # HARD-CODE 1:
    # Conta corrente fica fora da tabela.
    # ------------------------------------------------

    conta_corrente = (
        localizar_conta_corrente_bb(
            df_bruto
        )
    )

    # ------------------------------------------------
    # CABEÇALHO
    # ------------------------------------------------

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

    # ------------------------------------------------
    # HARD-CODE 2:
    # Inf. define Crédito / Débito.
    # ------------------------------------------------

    chave_inf = normalizar_chave(
        "Inf."
    )

    indice_inf = next(
        (
            indice
            for (
                indice,
                chave
            ) in colunas.items()
            if chave == chave_inf
        ),
        None
    )

    # ------------------------------------------------
    # VALOR
    # Não fixa "Valor R$", "Valor", etc.
    # Procura dinamicamente uma coluna contendo VALOR.
    # ------------------------------------------------

    candidatos_valor = [
        (
            indice,
            chave
        )
        for (
            indice,
            chave
        ) in colunas.items()
        if "VALOR" in chave
    ]

    if not candidatos_valor:
        raise ValueError(
            "BB: nenhuma coluna contendo "
            "'Valor' foi encontrada no arquivo."
        )

    if len(
        candidatos_valor
    ) > 1:
        raise ValueError(
            "BB: mais de uma coluna contendo "
            "'Valor' foi encontrada no arquivo."
        )

    indice_valor, _ = (
        candidatos_valor[0]
    )

    # ------------------------------------------------
    # CAMPOS CONFIGURADOS
    # ------------------------------------------------

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
                "Conta corrente"
            )
            in campos_normalizados
        )

    else:
        colunas_retorno = dict(
            colunas
        )

        incluir_conta = True

    # ------------------------------------------------
    # DADOS
    # ------------------------------------------------

    dados = df_bruto.iloc[
        linha_cabecalho + 1:
    ]

    registros = []

    for _, linha in dados.iterrows():
        registro = {}
        possui_dados = False

        # Inf. é usada apenas para a regra C/D.
        if indice_inf is not None:
            inf = linha.iloc[
                indice_inf
            ]

            inf = (
                ""
                if pd.isna(inf)
                else str(
                    inf
                ).strip().upper()
            )
        else:
            inf = None

        # Lê o conteúdo exatamente da coluna
        # correspondente no arquivo.
        for (
            indice,
            chave
        ) in colunas_retorno.items():

            valor = linha.iloc[
                indice
            ]

            if pd.isna(valor):
                valor = None

            # Só o campo monetário recebe
            # tratamento de sinal.
            if (
                indice
                == indice_valor
            ):
                valor = converter_valor(
                    valor
                )

                if valor is not None:
                    if inf == "D":
                        valor = -abs(
                            valor
                        )

                    elif inf == "C":
                        valor = abs(
                            valor
                        )

            # Campos textuais ficam exatamente
            # como vieram da célula.
            elif valor is not None:
                valor = str(
                    valor
                ).strip()

            if valor is not None:
                possui_dados = True

            registro[
                chave
            ] = valor

        # Conta corrente é replicada em cada lançamento.
        if incluir_conta:
            registro[
                normalizar_chave(
                    "Conta corrente"
                )
            ] = conta_corrente

        if possui_dados:
            registros.append(
                registro
            )

    return registros