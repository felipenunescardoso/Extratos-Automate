from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pymupdf
from PIL import Image
import pytesseract
from pytesseract import Output


def _normalizar(valor: str) -> str:
    valor = unicodedata.normalize("NFKD", str(valor or ""))
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]+", "", valor.upper())


def _localizar_tesseract() -> str | None:
    candidatos = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.join(
            os.getenv("LOCALAPPDATA", ""),
            "Programs",
            "Tesseract-OCR",
            "tesseract.exe",
        ),
    ]

    for caminho in candidatos:
        if caminho and os.path.isfile(caminho):
            return caminho

    return None


def _ocr_paginas(caminho: str) -> list[list[dict]]:
    executavel = _localizar_tesseract()
    if executavel:
        pytesseract.pytesseract.tesseract_cmd = executavel

    paginas = []

    with pymupdf.open(caminho) as pdf:
        for pagina in pdf:
            escala = 3.0
            pix = pagina.get_pixmap(
                matrix=pymupdf.Matrix(escala, escala),
                alpha=False,
            )

            imagem = Image.frombytes(
                "RGB",
                [pix.width, pix.height],
                pix.samples,
            )

            dados = None
            ultimo_erro = None

            for idioma in ("por", "eng"):
                try:
                    dados = pytesseract.image_to_data(
                        imagem,
                        lang=idioma,
                        config="--psm 6",
                        output_type=Output.DICT,
                    )
                    break
                except Exception as exc:
                    ultimo_erro = exc

            if dados is None:
                raise RuntimeError(
                    f"Falha no OCR Only Up: {ultimo_erro}"
                )

            palavras = []

            for i, texto in enumerate(dados["text"]):
                texto = str(texto or "").strip()
                if not texto:
                    continue

                try:
                    conf = float(dados["conf"][i])
                except (TypeError, ValueError):
                    conf = -1

                if conf < 15:
                    continue

                palavras.append({
                    "text": texto,
                    "x0": dados["left"][i] / escala,
                    "x1": (
                        dados["left"][i]
                        + dados["width"][i]
                    ) / escala,
                    "top": dados["top"][i] / escala,
                    "bottom": (
                        dados["top"][i]
                        + dados["height"][i]
                    ) / escala,
                })

            paginas.append(palavras)

    return paginas


def _agrupar_linhas(palavras: list[dict], tolerancia: float = 3.5):
    ordenadas = sorted(
        palavras,
        key=lambda p: (
            (p["top"] + p["bottom"]) / 2,
            p["x0"],
        ),
    )

    linhas = []

    for palavra in ordenadas:
        centro = (palavra["top"] + palavra["bottom"]) / 2

        destino = None
        for linha in reversed(linhas[-4:]):
            if abs(centro - linha["centro"]) <= tolerancia:
                destino = linha
                break

        if destino is None:
            destino = {
                "centro": centro,
                "palavras": [],
            }
            linhas.append(destino)

        destino["palavras"].append(palavra)

        centros = [
            (p["top"] + p["bottom"]) / 2
            for p in destino["palavras"]
        ]
        destino["centro"] = sum(centros) / len(centros)

    for linha in linhas:
        linha["palavras"].sort(key=lambda p: p["x0"])

    return linhas


def _texto_linha(linha: dict) -> str:
    return " ".join(
        str(p["text"]).strip()
        for p in linha["palavras"]
        if str(p["text"]).strip()
    ).strip()


def _extrair_conta(paginas: list[list[dict]]) -> str | None:
    for palavras in paginas[:2]:
        for linha in _agrupar_linhas(palavras):
            texto = _texto_linha(linha)

            # Cabeçalho:
            # Cliente: ... - Agência: 0001 - Conta: 12335
            match = re.search(
                r"Conta\s*:\s*([0-9.\-X]+)",
                texto,
                flags=re.IGNORECASE,
            )

            if match:
                return (
                    match.group(1)
                    .replace(".", "")
                    .strip()
                    .upper()
                )

    return None


def _converter_valor(texto: str) -> Decimal:
    texto = str(texto or "").upper()
    negativo = "-" in texto

    texto = texto.replace("R$", "")
    texto = texto.replace(" ", "")
    texto = texto.replace("-", "")

    match = re.search(r"([\d.]+,\d{2})", texto)

    if not match:
        raise ValueError(
            f"Valor Only Up inválido: {texto!r}"
        )

    numero = (
        match.group(1)
        .replace(".", "")
        .replace(",", ".")
    )

    try:
        valor = Decimal(numero)
    except InvalidOperation as exc:
        raise ValueError(
            f"Valor Only Up inválido: {texto!r}"
        ) from exc

    return -valor if negativo else valor


def _eh_saldo_anterior(descricao: str) -> bool:
    return _normalizar(descricao).startswith("SALDOANTERIOR")


def _extrair_data(texto: str) -> str | None:
    match = re.search(
        r"\b(\d{2}/\d{2}/\d{4})\s+\d{2}:\d{2}(?::\d{2})?\b",
        texto,
    )
    if not match:
        return None

    # Mantém o padrão dos demais extratores.
    return datetime.strptime(
        match.group(1),
        "%d/%m/%Y",
    ).strftime("%d/%m/%Y")


def _linha_tem_valor(texto: str) -> bool:
    return bool(
        re.search(
            r"-?\s*R?\$?\s*[\d.]+,\d{2}",
            texto,
            flags=re.IGNORECASE,
        )
    )


def _extrair_valor_da_linha(texto: str) -> Decimal | None:
    # No layout o campo Valor fica antes de "Saldo na conta".
    # A primeira moeda da linha corresponde ao Valor do lançamento.
    matches = list(
        re.finditer(
            r"-?\s*R?\$?\s*[\d.]+,\d{2}",
            texto,
            flags=re.IGNORECASE,
        )
    )

    if not matches:
        return None

    return _converter_valor(matches[0].group(0))


def _remover_colunas_finais(texto: str) -> str:
    """
    Remove Data/Hora e as colunas monetárias do texto bruto.
    A descrição será obtida preferencialmente por posição geométrica.
    """
    texto = re.sub(
        r"\b\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}(?::\d{2})?\b.*$",
        "",
        texto,
    ).strip()

    return texto


def _desc_por_geometria(linha: dict, limites: dict) -> str:
    palavras = [
        p["text"]
        for p in linha["palavras"]
        if p["x0"] < limites["valor"]
    ]

    return " ".join(palavras).strip()


def _valor_por_geometria(linha: dict, limites: dict) -> Decimal | None:
    palavras = [
        p["text"]
        for p in linha["palavras"]
        if (
            p["x0"] >= limites["valor"]
            and p["x0"] < limites["saldo"]
        )
    ]

    texto = " ".join(palavras)
    if not _linha_tem_valor(texto):
        return None

    return _extrair_valor_da_linha(texto)


def _data_por_geometria(linha: dict, limites: dict) -> str | None:
    palavras = [
        p["text"]
        for p in linha["palavras"]
        if p["x0"] >= limites["data"]
    ]

    return _extrair_data(" ".join(palavras))


def _limites_colunas(paginas: list[list[dict]]) -> dict:
    """
    Descobre as colunas pela linha de cabeçalho:
    Descrição | Valor | Saldo na conta | Tipo | Debitado |
    Creditado | Referência | Data/Hora
    """
    for palavras in paginas:
        for linha in _agrupar_linhas(palavras):
            ps = linha["palavras"]
            mapa = {
                _normalizar(p["text"]): p["x0"]
                for p in ps
            }

            texto = _normalizar(_texto_linha(linha))

            if (
                "DESCRICAO" in texto
                and "VALOR" in texto
                and "DATAHORA" in texto
            ):
                x_valor = next(
                    (
                        p["x0"]
                        for p in ps
                        if _normalizar(p["text"]) == "VALOR"
                    ),
                    None,
                )

                x_saldo = next(
                    (
                        p["x0"]
                        for p in ps
                        if _normalizar(p["text"]) == "SALDO"
                    ),
                    None,
                )

                x_data = next(
                    (
                        p["x0"]
                        for p in ps
                        if _normalizar(p["text"]) in {
                            "DATAHORA",
                            "DATA/HORA",
                        }
                    ),
                    None,
                )

                if x_data is None:
                    # Data/Hora costuma ser a última coluna.
                    x_data = max(p["x0"] for p in ps) - 5

                if x_valor is not None and x_saldo is not None:
                    return {
                        "valor": x_valor - 8,
                        "saldo": x_saldo - 8,
                        "data": x_data - 8,
                    }

    # Fallback proporcional ao layout enviado (página A4 paisagem).
    return {
        "valor": 250.0,
        "saldo": 335.0,
        "data": 735.0,
    }


def extrair_only_dist_pdf(caminho, campos_configurados=None):
    """
    Only Up - Distribuidoras.

    Layout incremental:
      Descrição | Valor | Saldo na conta | Tipo | Debitado |
      Creditado | Referência | Data/Hora

    Regras:
    - PDF do layout enviado é imagem, portanto usa OCR.
    - Valor já traz o sinal: -R$ = débito; R$ = crédito.
    - Saldo Anterior é ignorado.
    - Conta vem do cabeçalho.
    - Descrições quebradas em mais de uma linha são concatenadas.
    """

    paginas = _ocr_paginas(str(caminho))

    if not any(paginas):
        raise ValueError(
            f"OCR não encontrou conteúdo no PDF Only Up: {caminho}"
        )

    conta = _extrair_conta(paginas)

    if not conta:
        raise ValueError(
            f"Conta não encontrada no PDF Only Up: {caminho}"
        )

    limites = _limites_colunas(paginas)
    registros = []

    for palavras in paginas:
        linhas = _agrupar_linhas(palavras)

        # Cada lançamento termina na linha que contém Data/Hora.
        # Linhas anteriores sem Data/Hora pertencem ao mesmo lançamento.
        acumulado = []

        for linha in linhas:
            texto = _texto_linha(linha)
            chave = _normalizar(texto)

            if not texto:
                continue

            # Cabeçalho/rodapé.
            if (
                chave.startswith("ONLYUP")
                or chave.startswith("CLIENTE")
                or chave == "LANCAMENTOS"
                or chave.startswith("DE01")
                or (
                    "DESCRICAO" in chave
                    and "VALOR" in chave
                    and "DATAHORA" in chave
                )
                or chave.startswith("PAG")
            ):
                continue

            data = _data_por_geometria(
                linha,
                limites,
            ) or _extrair_data(texto)

            acumulado.append(linha)

            if not data:
                continue

            # O lançamento pode ocupar várias linhas.
            descricao_partes = []
            valor = None

            for parte in acumulado:
                desc = _desc_por_geometria(
                    parte,
                    limites,
                )

                if desc:
                    descricao_partes.append(desc)

                if valor is None:
                    valor = _valor_por_geometria(
                        parte,
                        limites,
                    )

            descricao = " ".join(descricao_partes)
            descricao = re.sub(
                r"\s+",
                " ",
                descricao,
            ).strip()

            # Fallback se o OCR deslocar as colunas.
            if valor is None:
                for parte in acumulado:
                    texto_parte = _texto_linha(parte)
                    candidato = _extrair_valor_da_linha(
                        texto_parte
                    )
                    if candidato is not None:
                        valor = candidato
                        break

            if (
                descricao
                and valor is not None
                and not _eh_saldo_anterior(descricao)
            ):
                registro = {
                    "Data/Hora": data,
                    "Descrição": descricao,
                    "Valor": valor,
                    "Conta": conta,
                }

                if campos_configurados:
                    filtrado = {
                        campo: registro[campo]
                        for campo in campos_configurados
                        if campo in registro
                    }
                    registro = filtrado or registro

                registros.append(registro)

            acumulado = []

    return registros