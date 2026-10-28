import pdfplumber


def _normalizar_cabecalhos(cabecalhos):
    resultado = []
    usados = {}

    for indice, valor in enumerate(cabecalhos, start=1):
        nome = str(valor or "").strip()

        if not nome:
            nome = f"COLUNA_{indice}"

        quantidade = usados.get(nome, 0) + 1
        usados[nome] = quantidade

        if quantidade > 1:
            nome = f"{nome}_{quantidade}"

        resultado.append(nome)

    return resultado


def extrair_pdf_generico(caminho, abas=None):
    """
    Extrator genérico de PDF tabular.
    Não possui regra bancária hardcoded.
    """

    registros = []

    with pdfplumber.open(caminho) as pdf:

        for numero_pagina, pagina in enumerate(pdf.pages, start=1):

            tabelas = pagina.extract_tables() or []

            for numero_tabela, tabela in enumerate(tabelas, start=1):

                linhas = [
                    linha
                    for linha in tabela
                    if linha and any(
                        str(valor or "").strip()
                        for valor in linha
                    )
                ]

                if len(linhas) < 2:
                    continue

                cabecalhos = _normalizar_cabecalhos(linhas[0])

                for linha in linhas[1:]:

                    valores = list(linha)

                    if len(valores) < len(cabecalhos):
                        valores.extend(
                            [None] * (len(cabecalhos) - len(valores))
                        )

                    if len(valores) > len(cabecalhos):
                        valores = valores[:len(cabecalhos)]

                    registro = {
                        cabecalhos[i]: (
                            str(valor).strip()
                            if valor is not None
                            else None
                        )
                        for i, valor in enumerate(valores)
                    }

                    registro["_Pagina"] = numero_pagina
                    registro["_Tabela"] = numero_tabela

                    registros.append(registro)

    return registros