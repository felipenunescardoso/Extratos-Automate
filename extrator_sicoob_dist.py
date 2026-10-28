from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pdfplumber


def _normalizar_chave(valor: str) -> str:
    valor = unicodedata.normalize("NFKD", str(valor or ""))
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]+", "", valor.upper())


def _converter_valor_sicoob(texto: str) -> Decimal:
    texto = str(texto or "").strip().upper()
    texto = texto.replace("R$", "").replace(" ", "")

    match = re.search(r"([\d.]+,\d{2})([CD])$", texto)
    if not match:
        raise ValueError(f"Valor Sicoob inválido: {texto!r}")

    numero, natureza = match.groups()

    try:
        valor = Decimal(numero.replace(".", "").replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"Valor Sicoob inválido: {texto!r}") from exc

    return -valor if natureza == "D" else valor


def _extrair_conta(texto: str) -> str | None:
    match = re.search(
        r"Conta\s*:\s*([\d.]+-[0-9X])",
        texto,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1).replace(".", "").upper()


def _extrair_periodo(texto: str) -> tuple[datetime, datetime] | None:
    match = re.search(
        r"Per[ií]odo\s*:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})",
        texto,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return (
        datetime.strptime(match.group(1), "%d/%m/%Y"),
        datetime.strptime(match.group(2), "%d/%m/%Y"),
    )


def _data_com_ano(data_ddmm: str, periodo: tuple[datetime, datetime]) -> str:
    _, fim = periodo
    dia, mes = map(int, data_ddmm.split("/"))
    ano = fim.year
    if mes > fim.month:
        ano -= 1
    return f"{dia:02d}/{mes:02d}/{ano:04d}"


def _eh_saldo(historico: str) -> bool:
    chave = _normalizar_chave(historico)
    return (
        chave.startswith("SALDODODIA")
        or chave.startswith("SALDOANTERIOR")
        or chave.startswith("SALDOBLOQUEADOANTERIOR")
        or chave.startswith("SALDOBLOQUEIOJUDICIALANTERIOR")
        or chave == "SALDO"
    )


def _montar_registro(
    data: str,
    documento: str | None,
    historico: str,
    valor: Decimal,
    conta: str,
    campos_configurados=None,
) -> dict:
    base = {
        "Data": data,
        "Documento": documento,
        "Histórico": historico.strip(),
        "Valor": valor,
        "Conta": conta,
    }

    if not campos_configurados:
        return base

    resultado = {
        campo: base[campo]
        for campo in campos_configurados
        if campo in base
    }
    return resultado or base


def extrair_sicoob_dist_pdf(caminho, campos_configurados=None):
    """
    Sicoob - Distribuidoras.

    C = crédito/positivo
    D = débito/negativo
    Linhas de saldo não são lançamentos.
    Complementos são concatenados ao histórico.
    """
    with pdfplumber.open(caminho) as pdf:
        paginas = [
            pagina.extract_text(x_tolerance=2, y_tolerance=3) or ""
            for pagina in pdf.pages
        ]

    texto_total = "\n".join(paginas)

    if not texto_total.strip():
        raise ValueError(f"PDF Sicoob sem texto extraível: {caminho}")

    conta = _extrair_conta(texto_total)
    if not conta:
        raise ValueError(f"Conta não encontrada no PDF Sicoob: {caminho}")

    periodo = _extrair_periodo(texto_total)
    if not periodo:
        raise ValueError(f"Período não encontrado no PDF Sicoob: {caminho}")

    regex_valor = re.compile(
        r"(?:R\$\s*)?([\d.]+,\d{2}[CD])\s*$",
        flags=re.IGNORECASE,
    )
    regex_inicio = re.compile(r"^(\d{2}/\d{2})(?:\s+(.*))?$")

    registros = []
    pendente = None

    def finalizar_pendente():
        nonlocal pendente
        if not pendente:
            return

        historico = " ".join(
            x.strip()
            for x in pendente["historico"]
            if x and x.strip()
        ).strip()

        if (
            pendente.get("valor") is not None
            and historico
            and not _eh_saldo(historico)
        ):
            registros.append(
                _montar_registro(
                    _data_com_ano(pendente["data"], periodo),
                    pendente.get("documento"),
                    historico,
                    pendente["valor"],
                    conta,
                    campos_configurados,
                )
            )
        pendente = None

    for pagina in paginas:
        for linha_original in pagina.splitlines():
            linha = re.sub(r"\s+", " ", linha_original).strip()
            if not linha:
                continue

            chave = _normalizar_chave(linha)

            # Seções que não pertencem aos lançamentos.
            if (
                chave.startswith("SISTEMADECOOPERATIVAS")
                or chave.startswith("PLATAFORMADESERVICOS")
                or chave.startswith("EXTRATODECONTACORRENTE")
                or chave.startswith("COOPERATIVA")
                or chave.startswith("CONTA")
                or chave.startswith("PERIODO")
                or chave.startswith("HISTORICODEMOVIMENTACAO")
                or chave.startswith("DATADOCUMENTOHISTORICOVALOR")
                or chave == "RESUMO"
                or chave.startswith("SALDOEMCONTA")
                or chave.startswith("CHEQUEESPECIALCONTRATADO")
                or chave.startswith("JUROSVENCIDOSPROVISIONADOS")
                or chave.startswith("TARIFASVENCIDASPROVISIONADAS")
                or chave.startswith("SALDODISPONIVEL")
                or chave.startswith("SALDOBLOQUEADOCHEQUES")
                or chave.startswith("SALDOBLOQUEADOJUDICIAL")
                or chave.startswith("ENCARGOS")
                or chave.startswith("PREVISAO")
                or chave.startswith("OUTRASINFORMACOES")
                or chave.startswith("VENCIMENTODECHEQUEESPECIAL")
                or chave.startswith("TAXACHEQUEESPECIAL")
                or chave.startswith("CUSTOEFETIVOTOTAL")
                or chave == "INFORMACOES"
                or chave.startswith("SAC")
                or "SICOOBINTERNETBANKING" in chave
                or chave.startswith("HTTPSWWWSICOOB")
            ):
                continue

            inicio = regex_inicio.match(linha)

            if inicio:
                finalizar_pendente()

                data = inicio.group(1)
                resto = (inicio.group(2) or "").strip()

                valor_match = regex_valor.search(resto)
                valor = None
                if valor_match:
                    valor = _converter_valor_sicoob(valor_match.group(1))
                    resto = resto[:valor_match.start()].strip()

                partes = resto.split(maxsplit=1)
                documento = None
                historico = ""

                if partes:
                    if _normalizar_chave(partes[0]).startswith("SALDO"):
                        historico = resto
                    elif len(partes) >= 2:
                        documento = partes[0]
                        historico = partes[1]
                    else:
                        historico = partes[0]

                pendente = {
                    "data": data,
                    "documento": documento,
                    "historico": [historico],
                    "valor": valor,
                }
                continue

            if pendente:
                valor_match = regex_valor.search(linha)

                if valor_match:
                    if pendente["valor"] is None:
                        pendente["valor"] = _converter_valor_sicoob(
                            valor_match.group(1)
                        )
                    complemento = linha[:valor_match.start()].strip()
                    if complemento:
                        pendente["historico"].append(complemento)
                else:
                    pendente["historico"].append(linha)

    finalizar_pendente()
    return registros