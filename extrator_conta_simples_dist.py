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
                    f"Falha no OCR Conta Simples: {ultimo_erro}"
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
                        dados["left"][i] + dados["width"][i]
                    ) / escala,
                    "top": dados["top"][i] / escala,
                    "bottom": (
                        dados["top"][i] + dados["height"][i]
                    ) / escala,
                })

            paginas.append(palavras)

    return paginas


def _agrupar_linhas(palavras: list[dict], tolerancia: float = 4.0):
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
            destino = {"centro": centro, "palavras": []}
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
    # Primeiro procura no cabeçalho da primeira página:
    # "Conta número 155239359"
    for palavras in paginas[:2]:
        linhas = _agrupar_linhas(palavras)

        for linha in linhas:
            texto = _texto_linha(linha)

            match = re.search(
                r"Conta\s*(?:n[uú]mero|numero)?\s*:?\s*([0-9.\-]+)",
                texto,
                flags=re.IGNORECASE,
            )

            if match:
                conta = re.sub(r"[^0-9X\-]", "", match.group(1).upper())
                if conta:
                    return conta

    # Fallback da página contábil:
    # linha "Conta 155239359"
    for palavras in paginas:
        linhas = _agrupar_linhas(palavras)

        for i, linha in enumerate(linhas):
            texto = _texto_linha(linha)

            if _normalizar(texto) == "CONTA" and i + 1 < len(linhas):
                prox = _texto_linha(linhas[i + 1])
                match = re.search(r"\b([0-9]{5,20})\b", prox)
                if match:
                    return match.group(1)

    return None


def _converter_moeda(texto: str) -> Decimal:
    texto = str(texto or "").strip()
    texto = texto.replace("R$", "").replace(" ", "")

    match = re.search(r"-?[\d.]+,\d{2}", texto)
    if not match:
        raise ValueError(
            f"Valor monetário Conta Simples inválido: {texto!r}"
        )

    bruto = match.group(0)
    negativo = bruto.startswith("-")

    numero = (
        bruto.replace("-", "")
        .replace(".", "")
        .replace(",", ".")
    )

    try:
        valor = Decimal(numero)
    except InvalidOperation as exc:
        raise ValueError(
            f"Valor monetário Conta Simples inválido: {texto!r}"
        ) from exc

    return -valor if negativo else valor


def _achar_limites_colunas(paginas: list[list[dict]]) -> dict:
    """
    Localiza as colunas:
    Data | Histórico | Crédito | Débito | Saldo | Situação
    """
    for palavras in paginas[:1]:
        for linha in _agrupar_linhas(palavras):
            ps = linha["palavras"]
            texto = _normalizar(_texto_linha(linha))

            if (
                "DATA" in texto
                and "HISTORICO" in texto
                and "CREDITO" in texto
                and "DEBITO" in texto
                and "SALDO" in texto
            ):
                posicoes = {}

                for p in ps:
                    chave = _normalizar(p["text"])

                    if chave == "DATA":
                        posicoes["data"] = p["x0"]
                    elif chave == "HISTORICO":
                        posicoes["historico"] = p["x0"]
                    elif chave == "CREDITO":
                        posicoes["credito"] = p["x0"]
                    elif chave == "DEBITO":
                        posicoes["debito"] = p["x0"]
                    elif chave == "SALDO":
                        posicoes["saldo"] = p["x0"]
                    elif chave in {"SITUACAO", "SITUAÇÃO"}:
                        posicoes["situacao"] = p["x0"]

                if all(
                    k in posicoes
                    for k in ("data", "historico", "credito", "debito", "saldo")
                ):
                    return posicoes

    # Fallback aproximado do layout enviado.
    return {
        "data": 14.0,
        "historico": 115.0,
        "credito": 270.0,
        "debito": 395.0,
        "saldo": 515.0,
        "situacao": 635.0,
    }


def _texto_faixa(
    linha: dict,
    inicio: float,
    fim: float | None = None,
) -> str:
    palavras = []

    for p in linha["palavras"]:
        centro = (p["x0"] + p["x1"]) / 2

        if centro < inicio:
            continue
        if fim is not None and centro >= fim:
            continue

        palavras.append(p["text"])

    return " ".join(palavras).strip()


def _extrair_data_linha(linha: dict, limites: dict) -> str | None:
    texto = _texto_faixa(
        linha,
        limites["data"] - 10,
        limites["historico"] - 5,
    )

    match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", texto)

    if not match:
        # fallback no texto inteiro
        match = re.search(
            r"\b(\d{2}/\d{2}/\d{4})\b",
            _texto_linha(linha),
        )

    if not match:
        return None

    return datetime.strptime(
        match.group(1),
        "%d/%m/%Y",
    ).strftime("%d/%m/%Y")


def _extrair_valor_faixa(
    linha: dict,
    inicio: float,
    fim: float,
) -> Decimal | None:
    texto = _texto_faixa(linha, inicio, fim)

    if not re.search(r"[\d.]+,\d{2}", texto):
        return None

    try:
        return _converter_moeda(texto)
    except ValueError:
        return None


def _montar_valor(
    credito: Decimal | None,
    debito: Decimal | None,
) -> Decimal | None:
    """
    Crédito > 0 -> positivo
    Débito > 0  -> negativo

    Se uma coluna vier R$ 0,00 e a outra possuir valor,
    utiliza apenas a coluna efetivamente movimentada.
    """
    zero = Decimal("0.00")

    credito = credito if credito is not None else zero
    debito = debito if debito is not None else zero

    if credito != zero and debito == zero:
        return abs(credito)

    if debito != zero and credito == zero:
        return -abs(debito)

    if credito == zero and debito == zero:
        return None

    # Layout não deveria ter crédito e débito simultaneamente.
    raise ValueError(
        f"Lançamento Conta Simples com crédito e débito simultâneos: "
        f"crédito={credito}, débito={debito}"
    )


def extrair_conta_simples_dist_pdf(caminho, campos_configurados=None):
    """
    Conta Simples - Distribuidoras.

    Layout:
      Data | Histórico | Crédito | Débito | Saldo | Situação

    Regras:
    - PDF do layout enviado é imagem -> OCR/Tesseract.
    - Crédito é valor positivo.
    - Débito é valor negativo.
    - Saldo não é lançamento.
    - Conta é obtida do cabeçalho.
    - Histórico quebrado em mais de uma linha é concatenado.
    """

    paginas = _ocr_paginas(str(caminho))

    if not any(paginas):
        raise ValueError(
            f"OCR não encontrou conteúdo no PDF Conta Simples: {caminho}"
        )

    conta = _extrair_conta(paginas)

    if not conta:
        raise ValueError(
            f"Conta não encontrada no PDF Conta Simples: {caminho}"
        )

    limites = _achar_limites_colunas(paginas)
    registros = []

    for palavras in paginas:
        linhas = _agrupar_linhas(palavras)
        i = 0

        while i < len(linhas):
            linha = linhas[i]
            data = _extrair_data_linha(linha, limites)

            if not data:
                i += 1
                continue

            historico = _texto_faixa(
                linha,
                limites["historico"] - 5,
                limites["credito"] - 5,
            )

            credito = _extrair_valor_faixa(
                linha,
                limites["credito"] - 10,
                limites["debito"] - 10,
            )

            debito = _extrair_valor_faixa(
                linha,
                limites["debito"] - 10,
                limites["saldo"] - 10,
            )

            # Algumas descrições ocupam duas linhas.
            j = i + 1

            while j < len(linhas):
                proxima = linhas[j]

                if _extrair_data_linha(proxima, limites):
                    break

                texto_proxima = _texto_linha(proxima)
                chave = _normalizar(texto_proxima)

                # Encerra ao sair da tabela de lançamentos.
                if (
                    chave.startswith("OSDADOSACIMA")
                    or chave.startswith("DADOSPARADECLARACAO")
                    or chave.startswith("INSTITUICAODEPAGAMENTO")
                    or chave.startswith("RAZAOSOCIAL")
                    or chave.startswith("CNPJ")
                    or chave.startswith("ENDERECO")
                    or chave.startswith("PARCEIRODADOCK")
                    or chave.startswith("TITULARDACONTA")
                ):
                    break

                complemento = _texto_faixa(
                    proxima,
                    limites["historico"] - 5,
                    limites["credito"] - 5,
                )

                # Só concatena texto que realmente esteja na coluna Histórico.
                if complemento:
                    historico = f"{historico} {complemento}".strip()

                j += 1

            valor = _montar_valor(credito, debito)

            if historico and valor is not None:
                registro = {
                    "Data": data,
                    "Histórico": re.sub(r"\s+", " ", historico).strip(),
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

            i = max(i + 1, j)

    return registros