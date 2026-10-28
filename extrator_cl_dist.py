import io
import os
import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber


MESES = {
    "JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4,
    "MAI": 5, "JUN": 6, "JUL": 7, "AGO": 8,
    "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12,
}


def _texto_ascii(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().upper()


def _normalizar_chave(texto):
    return re.sub(r"[^A-Z0-9]", "", _texto_ascii(texto))


def _filtrar_campos_configurados(registro, campos_configurados):
    if not campos_configurados:
        return registro
    campos = {_normalizar_chave(campo) for campo in campos_configurados}
    return {chave: valor for chave, valor in registro.items() if chave in campos}


def _converter_valor(texto):
    texto = str(texto or "").strip()
    texto = (texto.replace("R$", "").replace("RS$", "").replace("RS", "")
                  .replace(" ", "").replace("−", "-").replace("–", "-"))
    achado = re.search(r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}", texto)
    if not achado:
        return None
    try:
        return Decimal(achado.group(0).replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def _converter_data(texto):
    texto = re.sub(r"\s+", " ", str(texto or "")).strip()

    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", texto)
    if m:
        try:
            return datetime.strptime(texto, "%d/%m/%Y").strftime("%d/%m/%Y")
        except ValueError:
            return None

    m = re.fullmatch(r"(\d{1,2})\s+([A-Za-zÀ-ÿ]{3,})\.?\s+(\d{4})", texto)
    if not m:
        return None

    mes = MESES.get(_texto_ascii(m.group(2))[:3])
    if not mes:
        return None

    try:
        return datetime(int(m.group(3)), mes, int(m.group(1))).strftime("%d/%m/%Y")
    except ValueError:
        return None


def _registro(data, descricao, valor, conta, campos_configurados):
    registro = {
        _normalizar_chave("Data"): data,
        _normalizar_chave("Descrição"): re.sub(r"\s+", " ", descricao).strip(),
        _normalizar_chave("Valor"): valor,
        _normalizar_chave("Conta"): conta,
    }
    return _filtrar_campos_configurados(registro, campos_configurados)


def _configurar_tesseract():
    try:
        import pytesseract
    except ImportError as erro:
        raise RuntimeError("OCR do Clara CL requer pytesseract.") from erro

    caminhos = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        str(Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe"),
    ]
    for caminho in caminhos:
        if caminho and Path(caminho).exists():
            pytesseract.pytesseract.tesseract_cmd = caminho
            break
    return pytesseract


def _ocr_pdf(caminho_pdf):
    try:
        import fitz
        from PIL import Image
    except ImportError as erro:
        raise RuntimeError("OCR do Clara CL requer pymupdf e pillow.") from erro

    pytesseract = _configurar_tesseract()
    textos = []
    documento = fitz.open(str(caminho_pdf))
    try:
        for pagina in documento:
            pix = pagina.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
            imagem = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            try:
                texto = pytesseract.image_to_string(imagem, lang="por", config="--psm 6")
            except Exception:
                texto = pytesseract.image_to_string(imagem, lang="eng", config="--psm 6")
            textos.append(texto or "")
    finally:
        documento.close()
    return textos


def _ler_paginas(caminho_pdf):
    with pdfplumber.open(caminho_pdf) as pdf:
        textos = [(pagina.extract_text(x_tolerance=2, y_tolerance=2) or "") for pagina in pdf.pages]
    if any(texto.strip() for texto in textos):
        return textos
    return _ocr_pdf(caminho_pdf)


def _extrair_conta(textos):
    texto = "\n".join(textos)
    padroes = (
        r"\bCONTA\s*[:\-]?\s*(\d{4,10}\s*-\s*\d)\b",
        r"\bCONTA\s*[:\-]?\s*(\d{5,11})\b",
        r"\b(\d{5,10}\s*-\s*\d)\b",
    )
    ascii_texto = _texto_ascii(texto)
    for padrao in padroes:
        m = re.search(padrao, ascii_texto, flags=re.IGNORECASE)
        if m:
            return re.sub(r"\s+", "", m.group(1))
    return None


def _eh_inicio_transacional(texto):
    chave = _texto_ascii(texto)
    # Tolerante a OCR: Movimentações / Movimentag6es / Movimentacées etc.
    return (
        "CONTA TRANSACIONAL" in chave
        and ("MOVIMENT" in chave or "DATA DESCR" in chave)
        and "RESUMO" not in chave
    )


def _eh_inicio_limite(texto):
    chave = _texto_ascii(texto)
    return "LIMITE FLEXIVEL" in chave and ("MOVIMENT" in chave or "RESUMO" in chave)


def _eh_cabecalho_tabela(texto):
    chave = _texto_ascii(texto)
    return "DATA" in chave and "DESCR" in chave and "VALOR" in chave


def _eh_linha_ignorada(texto):
    chave = _texto_ascii(texto)
    return (
        chave.startswith("SALDO NO FINAL DO DIA")
        or chave.startswith("GERADO EM")
        or chave.startswith("EXTRATO DA CONTA")
        or chave.startswith("RESUMO ")
        or chave.startswith("SALDO INICIAL")
        or chave.startswith("TOTAL DE ")
        or chave.startswith("TARIFAS CLARA")
        or chave.startswith("PAGINA ")
        or ("CNPJ" in chave and "CONTA" in chave)
    )


def _extrair_inicio_movimento(texto):
    texto = re.sub(r"\s+", " ", str(texto or "")).strip()

    padroes_data = (
        r"^(\d{2}/\d{2}/\d{4})\s+(.+)$",
        r"^(\d{1,2}\s+[A-Za-zÀ-ÿ]{3,}\.?\s+\d{4})\s+(.+)$",
    )

    for padrao in padroes_data:
        m = re.match(padrao, texto)
        if not m:
            continue

        data = _converter_data(m.group(1))
        if not data:
            continue

        restante = m.group(2).strip()
        valores = list(re.finditer(r"-?\s*(?:R\$|RS\$?|R\s*\$)?\s*[\d.]+,\d{2}", restante, re.I))
        if not valores:
            return {"data": data, "descricao": [restante], "valor": None}

        ultimo = valores[-1]
        valor = _converter_valor(ultimo.group(0))
        descricao = restante[:ultimo.start()].strip()

        # O OCR às vezes lê o sinal "-" como aspas. No layout Clara,
        # a natureza do lançamento permite recuperar o sinal sem ambiguidade.
        descricao_chave = _texto_ascii(descricao)
        if valor is not None:
            if (
                "PAGAMENTO REALIZADO" in descricao_chave
                or "LIMITE FLEXIVEL - AUMENTO DE LIMITE" in descricao_chave
            ):
                valor = -abs(valor)
            elif (
                "TRANSFERENCIA RECEBIDA" in descricao_chave
                or "LIMITE FLEXIVEL - RESGATE DE LIMITE" in descricao_chave
            ):
                valor = abs(valor)

        return {"data": data, "descricao": [descricao.rstrip(' \"“”')], "valor": valor}

    return None


def _processar_paginas(textos_paginas, campos_configurados):
    conta = _extrair_conta(textos_paginas)
    if not conta:
        raise ValueError("Conta não encontrada no PDF Clara CL.")

    registros = []
    dentro_transacional = False
    secao_transacional_encontrada = False
    limite_flexivel_encontrado = False
    atual = None

    def finalizar():
        nonlocal atual
        if not atual:
            return
        descricao = re.sub(r"\s+", " ", " ".join(atual["descricao"])).strip()
        if descricao and atual["valor"] is not None:
            registros.append(_registro(
                atual["data"], descricao, atual["valor"], conta, campos_configurados
            ))
        atual = None

    for texto_pagina in textos_paginas:
        linhas = [re.sub(r"\s+", " ", l).strip() for l in texto_pagina.splitlines() if l.strip()]

        for linha in linhas:
            if _eh_inicio_limite(linha):
                finalizar()
                dentro_transacional = False
                limite_flexivel_encontrado = True
                continue

            if _eh_inicio_transacional(linha):
                finalizar()
                dentro_transacional = True
                secao_transacional_encontrada = True
                continue

            # Nas páginas seguintes do mesmo extrato Clara a tabela continua sem repetir
            # o título "Movimentações na conta transacional".
            if (secao_transacional_encontrada and not limite_flexivel_encontrado
                    and _eh_cabecalho_tabela(linha) and not dentro_transacional):
                dentro_transacional = True
                continue

            if not dentro_transacional:
                continue

            if _eh_cabecalho_tabela(linha) or _eh_linha_ignorada(linha):
                continue

            novo = _extrair_inicio_movimento(linha)
            if novo:
                finalizar()
                atual = novo
                continue

            if atual:
                valor_sozinho = re.fullmatch(r"-?\s*(?:R\$|RS\$?|R\s*\$)?\s*[\d.]+,\d{2}", linha, re.I)
                if valor_sozinho and atual["valor"] is None:
                    atual["valor"] = _converter_valor(valor_sozinho.group(0))
                elif not _eh_linha_ignorada(linha):
                    atual["descricao"].append(linha)

        # Não carrega continuação de descrição para o cabeçalho da página seguinte.
        finalizar()

    finalizar()

    # Extrato Clara válido, mas sem movimentação (ex.: saldo 0 e tabela vazia).
    if secao_transacional_encontrada and not registros:
        return []

    if not secao_transacional_encontrada:
        raise ValueError("Seção de movimentações da conta transacional não encontrada no PDF Clara CL.")

    return registros


def extrair_cl_dist(caminho_pdf, campos_configurados=None):
    """
    Extrator Clara CL - Distribuidoras.

    Trata PDF com camada de texto e PDF imagem/OCR.
    Importa somente a seção da conta transacional.
    A seção separada "Movimentações no limite flexível" é ignorada.

    Campos retornados:
        Data
        Descrição
        Valor
        Conta
    """
    textos_paginas = _ler_paginas(caminho_pdf)
    return _processar_paginas(textos_paginas, campos_configurados)
