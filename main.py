from pathlib import Path
import subprocess
import sys

BASE_DIR = Path(__file__).resolve().parent
PYTHON = sys.executable

def executar(script):
    caminho = BASE_DIR / script
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")

    print("\n" + "=" * 70)
    print(f"INICIANDO: {script}")
    print("=" * 70)

    resultado = subprocess.run([PYTHON, str(caminho)], cwd=str(BASE_DIR))
    if resultado.returncode != 0:
        raise RuntimeError(
            f"{script} terminou com erro. Código de saída: {resultado.returncode}"
        )

def main():
    try:
        executar("agente_analista.py")
        executar("orquestrador.py")
        print("\n" + "=" * 70)
        print("PROCESSO FINALIZADO COM SUCESSO")
        print("=" * 70)
    except KeyboardInterrupt:
        print("\nProcesso interrompido pelo usuário.")
        sys.exit(130)
    except Exception as erro:
        print(f"\n[ERRO] {erro}")
        sys.exit(1)

if __name__ == "__main__":
    main()
