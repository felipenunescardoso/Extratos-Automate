import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from inicial import conectar


# ============================================================
# CONFIGURAÇÃO
# ============================================================

INTERVALO_SEGUNDOS = 86400

DIRETORIO_PROJETO = Path(__file__).resolve().parent
ORQUESTRADOR = DIRETORIO_PROJETO / "orquestrador.py"


# ============================================================
# BANCO
# ============================================================

def buscar_pendencias():
    """
    Retorna todas as execuções ainda pendentes,
    ordenadas pelo id_execucao.
    """

    with conectar() as conexao:
        with conexao.cursor() as cursor:

            cursor.execute("""
                SELECT
                    id_execucao,
                    data_inicio,
                    data_fim,
                    acao,
                    id_arquivo
                FROM extratos.controle_servico
                WHERE executado = FALSE
                ORDER BY id_execucao
            """)

            return cursor.fetchall()


# ============================================================
# ORQUESTRADOR
# ============================================================

def executar_orquestrador():
    """
    Executa o orquestrador usando o mesmo interpretador
    Python que iniciou este agente.
    """

    if not ORQUESTRADOR.exists():
        raise FileNotFoundError(
            f"Orquestrador não encontrado: {ORQUESTRADOR}"
        )

    processo = subprocess.run(
        [
            sys.executable,
            str(ORQUESTRADOR)
        ],
        cwd=str(DIRETORIO_PROJETO),
        capture_output=True,
        text=True
    )

    if processo.stdout:
        print()
        print("[SAÍDA ORQUESTRADOR]")
        print(processo.stdout)

    if processo.stderr:
        print()
        print("[ERRO ORQUESTRADOR]")
        print(processo.stderr)

    if processo.returncode != 0:
        raise RuntimeError(
            f"Orquestrador finalizou com código "
            f"{processo.returncode}."
        )


# ============================================================
# EXECUÇÃO DO ESTAGIÁRIO
# ============================================================

def main():

    print()
    print("=" * 70)
    print("AGENTE ESTAGIÁRIO")
    print(
        f"Data: {datetime.now():%d/%m/%Y %H:%M:%S}"
    )
    print("=" * 70)

    pendencias = buscar_pendencias()

    if not pendencias:

        print()
        print(
            "[SEM PENDÊNCIAS] Nenhuma execução com "
            "executado = FALSE."
        )

        return

    print()
    print(
        f"[PENDÊNCIAS ENCONTRADAS] {len(pendencias)}"
    )

    for (
        id_execucao,
        data_inicio,
        data_fim,
        acao,
        id_arquivo
    ) in pendencias:

        print(
            f"ID execução: {id_execucao} | "
            f"id_arquivo: {id_arquivo} | "
            f"ação: {acao} | "
            f"período: {data_inicio} até {data_fim}"
        )

    print()
    print(
        "[EXECUTANDO] Enviando pendências "
        "para o orquestrador."
    )

    executar_orquestrador()

    print()
    print(
        "[FINALIZADO] O orquestrador terminou "
        "o processamento das pendências."
    )


# ============================================================
# SERVIÇO
# ============================================================

if __name__ == "__main__":

    while True:

        try:

            main()

        except Exception as erro:

            print()
            print("=" * 70)
            print("[ERRO NO AGENTE ESTAGIÁRIO]")
            print(erro)
            print("=" * 70)

        print()
        print(
            "Próxima verificação em 24 horas."
        )

        time.sleep(
            INTERVALO_SEGUNDOS
        )
