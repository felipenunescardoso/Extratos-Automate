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


def converter_valor_bradesco(valor, negativo=False):
    if valor is None:
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    resultado = re.search(
        r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}",
        texto
    )

    if not resultado:
        return None

    numero = (
        resultado.group(0)
        .replace(".", "")
        .replace(",", ".")
    )

    valor_decimal = Decimal(numero)

    if negativo:
        return -abs(valor_decimal)

    return abs(valor_decimal)


def localizar_conta_corrente_bradesco(pdf):
    """
    Exemplos:
        Extrato de: Ag: 3442 | CC: 0025624-2
        Agência | Conta ...
        03442 | 0025624-2 ...
    """

    padroes = (
        r"\bCC\s*:\s*([0-9]{4,12}-[0-9X])",
        r"\bCONTA\s*:?\s*([0-9]{4,12}-[0-9X])",
    )

    for pagina in pdf.pages[:2]:
        texto = pagina.extract_text() or ""
        texto = re.sub(r"\s+", " ", texto)

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


def obter_limites_colunas(pagina, linhas=None):
    """
    Localiza as colunas pelo cabeçalho real do PDF.

    Cabeçalho esperado:
        Data | Lançamento | Dcto. | Crédito (R$) | Débito (R$) | Saldo (R$)

    Se o cabeçalho não for encontrado, usa limites de segurança.
    """

    largura = float(pagina.width)

    if linhas:
        for linha in linhas:
            palavras = linha["palavras"]

            encontrados = {}

            for palavra in palavras:
                chave = normalizar_chave(palavra["text"])

                if chave == "DATA" and "data" not in encontrados:
                    encontrados["data"] = palavra["x0"]

                elif chave.startswith("LANCAMENTO") and "lancamento" not in encontrados:
                    encontrados["lancamento"] = palavra["x0"]

                elif chave.startswith("DCTO") and "documento" not in encontrados:
                    encontrados["documento"] = palavra["x0"]

                elif chave.startswith("CREDITO") and "credito" not in encontrados:
                    encontrados["credito"] = palavra["x0"]

                elif chave.startswith("DEBITO") and "debito" not in encontrados:
                    encontrados["debito"] = palavra["x0"]

                elif chave.startswith("SALDO") and "saldo" not in encontrados:
                    encontrados["saldo"] = palavra["x0"]

            ordem = (
                "data",
                "lancamento",
                "documento",
                "credito",
                "debito",
                "saldo"
            )

            if all(nome in encontrados for nome in ordem):
                centros = [encontrados[nome] for nome in ordem]

                cortes = [
                    0.0,
                    (centros[0] + centros[1]) / 2,
                    (centros[1] + centros[2]) / 2,
                    (centros[2] + centros[3]) / 2,
                    (centros[3] + centros[4]) / 2,
                    (centros[4] + centros[5]) / 2,
                    largura * 1.01
                ]

                return {
                    "data": (cortes[0], cortes[1]),
                    "lancamento": (cortes[1], cortes[2]),
                    "documento": (cortes[2], cortes[3]),
                    "credito": (cortes[3], cortes[4]),
                    "debito": (cortes[4], cortes[5]),
                    "saldo": (cortes[5], cortes[6])
                }

    # Fallback apenas se não for possível localizar o cabeçalho.
    return {
        "data": (0.00 * largura, 0.120 * largura),
        "lancamento": (0.120 * largura, 0.490 * largura),
        "documento": (0.490 * largura, 0.650 * largura),
        "credito": (0.650 * largura, 0.775 * largura),
        "debito": (0.775 * largura, 0.885 * largura),
        "saldo": (0.885 * largura, 1.01 * largura)
    }


def localizar_data_na_linha(
    palavras,
    limites
):
    texto_data = texto_intervalo(
        palavras,
        *limites["data"]
    )

    resultado = re.search(
        r"\b\d{2}/\d{2}/\d{4}\b",
        texto_data
    )

    if resultado:
        return resultado.group(0)

    return None


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

    campos_sempre_preservados = {
        normalizar_chave("Valor"),
        normalizar_chave("Lançamento (R$)")
    }

    return {
        chave: valor
        for chave, valor
        in registro.items()
        if (
            chave in campos_normalizados
            or chave in campos_sempre_preservados
        )
    }


def eh_secao_invest_facil(texto_linha):
    texto = normalizar_chave(
        texto_linha
    )

    return (
        "SALDOSINVESTFACILPLUS" in texto
        or "ULTIMOSLANCAMENTOS" in texto
    )



def eh_linha_ignorada_bradesco(texto_linha):
    chave = normalizar_chave(texto_linha)

    if not chave:
        return True

    marcadores_ignorar = (
        "DATALANCAMENTODCTO",
        "TOTAL",
        "EXTRATODE",
        "AGENCIACONTA",
        "OSDADOSACIMA",
        "ESTAOSUJEITOSAALTERACOES",
        "ESTAOSUJEITAS AALTERACOES",
        "CENTRALDEATENDIMENTO",
        "SAC",
        "OUVIDORIA",
    )

    if any(
        marcador.replace(" ", "") in chave
        for marcador in marcadores_ignorar
    ):
        return True

    return False



def valores_movimento_da_linha(
    palavras_linha,
    limites
):
    credito_texto = texto_intervalo(
        palavras_linha,
        *limites["credito"]
    )

    debito_texto = texto_intervalo(
        palavras_linha,
        *limites["debito"]
    )

    credito = converter_valor_bradesco(
        credito_texto,
        negativo=False
    )

    debito = converter_valor_bradesco(
        debito_texto,
        negativo=True
    )

    return credito, debito


def linha_tem_movimento(
    palavras_linha,
    limites
):
    credito, debito = valores_movimento_da_linha(
        palavras_linha,
        limites
    )

    return (
        credito is not None
        or debito is not None
    )


def filtrar_palavras_continuacao(
    palavras_linha,
    limites,
    permitir_valores=False
):
    """
    Em uma linha sem data, evita jogar rodapé/observações
    inteiros para dentro do histórico.

    Se o lançamento anterior ainda não possui crédito/débito,
    permite também documento/valor/saldo, pois a transação pode
    ter quebrado fisicamente em duas linhas.

    Se o lançamento anterior já possui valor, mantém somente
    a área textual de Lançamento/Documento.
    """

    if permitir_valores:
        x_inicio = limites["lancamento"][0]
        x_fim = limites["saldo"][1]
    else:
        x_inicio = limites["lancamento"][0]
        x_fim = limites["documento"][1]

    return [
        palavra
        for palavra in palavras_linha
        if (
            palavra["x0"] >= x_inicio
            and palavra["x0"] < x_fim
        )
    ]

def montar_registro_bradesco(
    palavras_linha,
    limites,
    data_movimento,
    conta_corrente
):
    lancamento = texto_intervalo(
        palavras_linha,
        *limites["lancamento"]
    )

    documento = texto_intervalo(
        palavras_linha,
        *limites["documento"]
    )

    credito_texto = texto_intervalo(
        palavras_linha,
        *limites["credito"]
    )

    debito_texto = texto_intervalo(
        palavras_linha,
        *limites["debito"]
    )

    saldo_texto = texto_intervalo(
        palavras_linha,
        *limites["saldo"]
    )

    credito = converter_valor_bradesco(
        credito_texto,
        negativo=False
    )

    debito = converter_valor_bradesco(
        debito_texto,
        negativo=True
    )

    saldo = converter_valor_bradesco(
        saldo_texto,
        negativo=False
    )

    # SALDO ANTERIOR e qualquer linha sem crédito/débito
    # não são lançamentos.
    if credito is None and debito is None:
        return None

    valor = credito if credito is not None else debito

    return {
        normalizar_chave("Data"): data_movimento,
        normalizar_chave("Lançamento"): lancamento or None,
        normalizar_chave("Dcto."): documento or None,
        normalizar_chave("Crédito (R$)"): credito,
        normalizar_chave("Débito (R$)"): debito,
        normalizar_chave("Saldo (R$)"): saldo,
        normalizar_chave("Valor"): valor,
        normalizar_chave("Lançamento (R$)"): valor,
        normalizar_chave("Conta"): conta_corrente
    }

def extrair_br_dist_pdf(
    caminho,
    campos_configurados=None
):
    """
    Extrator Bradesco - Distribuidoras.

    Estratégia:
        - usa as linhas com Crédito/Débito como âncora real da transação;
        - preserva a última data válida quando o Bradesco omite a data;
        - associa linhas textuais quebradas ao movimento mais próximo
          verticalmente;
        - ignora saldo anterior, total, rodapés e Invest Fácil.

    Isso trata corretamente casos como:

        TARIFA MANUTENCAO C/C
        09/01/2026                20126       -6,40
        VR.PARCIAL TAR.MANUT.C/C

    e também:

        TRANSFERENCIA PIX
        12/01/2026                1228481      90,00
        REM: 76 OIL COMBUSTIVEIS 12/01
    """

    registros = []

    with pdfplumber.open(caminho) as pdf:

        conta_corrente = localizar_conta_corrente_bradesco(pdf)
        ultima_data_movimento = None

        for pagina in pdf.pages:

            palavras = pagina.extract_words(
                use_text_flow=False,
                keep_blank_chars=False
            )

            if not palavras:
                continue

            linhas = agrupar_palavras_por_linha(
                palavras
            )

            limites = obter_limites_colunas(
                pagina,
                linhas
            )

            linhas_historico = []
            dentro_tabela_movimentos = False

            for linha in linhas:

                palavras_linha = linha["palavras"]

                texto_linha = " ".join(
                    palavra["text"]
                    for palavra in palavras_linha
                ).strip()

                chave_linha = normalizar_chave(
                    texto_linha
                )

                # Só começa a considerar conteúdo depois do cabeçalho
                # real da tabela de movimentos.
                if (
                    "DATA" in chave_linha
                    and "LANCAMENTO" in chave_linha
                    and "DCTO" in chave_linha
                    and "CREDITO" in chave_linha
                    and "DEBITO" in chave_linha
                    and "SALDO" in chave_linha
                ):
                    dentro_tabela_movimentos = True
                    continue

                if not dentro_tabela_movimentos:
                    continue

                # A linha Total encerra a tabela principal.
                if chave_linha.startswith("TOTAL"):
                    break

                if eh_secao_invest_facil(
                    texto_linha
                ):
                    break

                if eh_linha_ignorada_bradesco(
                    texto_linha
                ):
                    continue

                if "SALDOANTERIOR" in chave_linha:
                    continue

                linhas_historico.append({
                    "top": float(
                        linha["top"]
                    ),
                    "palavras": palavras_linha,
                    "texto": texto_linha,
                    "data": localizar_data_na_linha(
                        palavras_linha,
                        limites
                    ),
                    "movimento": linha_tem_movimento(
                        palavras_linha,
                        limites
                    ),
                    "lancamento": texto_intervalo(
                        palavras_linha,
                        *limites["lancamento"]
                    )
                })

            # --------------------------------------------------------
            # Âncoras = linhas que realmente possuem Crédito ou Débito.
            # "Total" não é transação.
            # --------------------------------------------------------
            ancoras = []

            for item in linhas_historico:

                if not item["movimento"]:
                    continue

                chave = normalizar_chave(
                    item["texto"]
                )

                if chave.startswith("TOTAL"):
                    continue

                data_linha = item["data"]

                if data_linha is not None:
                    ultima_data_movimento = data_linha

                if ultima_data_movimento is None:
                    continue

                ancoras.append({
                    "top": item["top"],
                    "palavras": list(
                        item["palavras"]
                    ),
                    "data": ultima_data_movimento,
                    "partes_lancamento": (
                        [item["lancamento"]]
                        if item["lancamento"]
                        else []
                    )
                })

            if not ancoras:
                continue

            # --------------------------------------------------------
            # Linhas textuais sem valor são associadas ao movimento
            # verticalmente mais próximo.
            #
            # Isso resolve o padrão real do Bradesco em que a descrição
            # pode aparecer imediatamente antes ou depois da linha que
            # contém Data/Dcto./Valor.
            # --------------------------------------------------------
            for item in linhas_historico:

                if item["movimento"]:
                    continue

                if item["data"] is not None:
                    continue

                lancamento = str(
                    item["lancamento"] or ""
                ).strip()

                if not lancamento:
                    continue

                chave = normalizar_chave(
                    item["texto"]
                )

                if (
                    chave.startswith("TOTAL")
                    or "SALDOANTERIOR" in chave
                ):
                    continue

                ancora_proxima = min(
                    ancoras,
                    key=lambda ancora: abs(
                        ancora["top"]
                        - item["top"]
                    )
                )

                ancora_proxima[
                    "partes_lancamento"
                ].append(
                    (
                        item["top"],
                        lancamento
                    )
                )

            # Normaliza partes de lançamento da própria âncora
            # e das linhas complementares em ordem vertical.
            for ancora in ancoras:

                partes = []

                for parte in ancora[
                    "partes_lancamento"
                ]:
                    if isinstance(
                        parte,
                        tuple
                    ):
                        partes.append(
                            parte
                        )
                    else:
                        partes.append(
                            (
                                ancora["top"],
                                parte
                            )
                        )

                partes.sort(
                    key=lambda item: item[0]
                )

                lancamento_final = " ".join(
                    parte[1]
                    for parte in partes
                    if parte[1]
                ).strip()

                registro = montar_registro_bradesco(
                    ancora["palavras"],
                    limites,
                    ancora["data"],
                    conta_corrente
                )

                if registro is None:
                    continue

                registro[
                    normalizar_chave(
                        "Lançamento"
                    )
                ] = (
                    lancamento_final
                    or None
                )

                registro_filtrado = (
                    filtrar_campos_configurados(
                        registro,
                        campos_configurados
                    )
                )

                registros.append(
                    registro_filtrado
                )

    return registros