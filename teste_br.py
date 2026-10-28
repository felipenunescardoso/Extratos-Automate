from pathlib import Path
from extrator_br_dist import extrair_br_dist_pdf

pasta = Path(
    r"D:\AutomateBancos\Dist Extratos Mensais\Extratos Mensais\08 - AGOSTO\BRADESCO"
)

print("Pasta existe:", pasta.exists())

arquivos = list(pasta.glob("*.pdf"))

print("PDFs encontrados:", len(arquivos))

for arquivo in arquivos:
    print("\nPDF:", arquivo.name)

    registros = extrair_br_dist_pdf(
        arquivo,
        [
            "Data",
            "Lançamento",
            "Dcto.",
            "Valor",
            "Saldo (R$)",
            "Conta"
        ]
    )

    print("Registros extraídos:", len(registros))

    for registro in registros[:5]:
        print(registro)