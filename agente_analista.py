import re
import time
import calendar
import unicodedata
import importlib
from datetime import date, datetime
from pathlib import Path

from inicial import conectar
from extrator_ssg import extrair_ssg_pdf
from extrator_santander import extrair_santander_excel
from extrator_bb import extrair_bb_excel
from extrator_bb_dist import extrair_bb_dist_pdf
from extrator_it import extrair_it_excel
from extrator_pdf_generico import extrair_pdf_generico
from extrator_xls_generico import extrair_xls_generico
from extrator_xlsx_generico import extrair_xlsx_generico


# ============================================================
# CONFIGURAÇÃO
# ============================================================

INTERVALO_SEGUNDOS = 86400


# ============================================================
# NORMALIZAÇÃO
# ============================================================

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


def como_data(valor):
    if valor is None:
        return None

    if isinstance(valor, datetime):
        return valor.date()

    if isinstance(valor, date):
        return valor

    texto = str(valor).strip()

    if not texto:
        return None

    for formato in (
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d-%m-%Y"
    ):
        try:
            return datetime.strptime(
                texto,
                formato
            ).date()

        except ValueError:
            pass

    return None


def inicio_fim_mes(data_referencia):
    data_referencia = como_data(
        data_referencia
    )

    ultimo_dia = calendar.monthrange(
        data_referencia.year,
        data_referencia.month
    )[1]

    return (
        date(
            data_referencia.year,
            data_referencia.month,
            1
        ),
        date(
            data_referencia.year,
            data_referencia.month,
            ultimo_dia
        )
    )


# ============================================================
# BANCO
# ============================================================

def buscar_diretorios(conexao):
    with conexao.cursor() as cursor:
        cursor.execute("""
            SELECT
                id,
                diretorio,
                tipo,
                usuario,
                senha,
                finalidade,
                nome_arquivo
            FROM extratos.diretorios
            WHERE ativo = TRUE
            ORDER BY id
        """)

        return cursor.fetchall()


def buscar_arquivos_bancos(conexao):
    with conexao.cursor() as cursor:
        cursor.execute("""
            SELECT
                id,
                nome,
                prefixo,
                extensao,
                abas,
                id_configuracao,
                extrator
            FROM extratos.arquivos_bancos
            WHERE ativo = TRUE
            ORDER BY id
        """)

        return cursor.fetchall()


def buscar_de_para(
    conexao,
    id_arquivo
):
    with conexao.cursor() as cursor:
        cursor.execute("""
            SELECT
                nome_campo_arquivo,
                nome_campo_planilha_mae
            FROM extratos.de_para_banco_planilha_mae
            WHERE id_arquivo = %s
        """, (
            id_arquivo,
        ))

        registros = cursor.fetchall()

    de_para = {}

    for origem, destino in registros:
        de_para[
            normalizar_chave(origem)
        ] = normalizar_chave(destino)

    return de_para


def buscar_campo_data_origem(
    de_para
):
    chave_data = normalizar_chave(
        "Data"
    )

    for origem, destino in de_para.items():
        if destino == chave_data:
            return origem

    return None


def buscar_ultima_data_fim(
    conexao,
    id_arquivo
):
    with conexao.cursor() as cursor:
        cursor.execute("""
            SELECT
                MAX(data_fim)
            FROM extratos.controle_servico
            WHERE id_arquivo = %s
              AND executado = TRUE
        """, (
            id_arquivo,
        ))

        resultado = cursor.fetchone()

    if not resultado:
        return None

    return como_data(
        resultado[0]
    )


def existe_pendencia(
    conexao,
    id_arquivo
):
    """
    Não cria nova ordem para um banco enquanto
    já existir uma execução FALSE desse id_arquivo.
    """

    with conexao.cursor() as cursor:
        cursor.execute("""
            SELECT 1
            FROM extratos.controle_servico
            WHERE id_arquivo = %s
              AND executado = FALSE
            LIMIT 1
        """, (
            id_arquivo,
        ))

        return (
            cursor.fetchone()
            is not None
        )


def ja_existe_periodo(
    conexao,
    id_arquivo,
    data_inicio,
    data_fim
):
    with conexao.cursor() as cursor:
        cursor.execute("""
            SELECT 1
            FROM extratos.controle_servico
            WHERE id_arquivo = %s
              AND data_inicio::date = %s
              AND data_fim::date = %s
            LIMIT 1
        """, (
            id_arquivo,
            data_inicio,
            data_fim
        ))

        return (
            cursor.fetchone()
            is not None
        )


def criar_controle_servico(
    conexao,
    id_arquivo,
    data_inicio,
    data_fim
):
    with conexao.cursor() as cursor:
        cursor.execute("""
            INSERT INTO extratos.controle_servico
            (
                data_inicio,
                data_fim,
                acao,
                data_log,
                executado,
                id_arquivo
            )
            VALUES
            (
                %s,
                %s,
                'INSERT',
                CURRENT_TIMESTAMP,
                FALSE,
                %s
            )
            RETURNING id_execucao
        """, (
            datetime.combine(
                data_inicio,
                datetime.min.time()
            ),
            datetime.combine(
                data_fim,
                datetime.max.time()
            ),
            id_arquivo
        ))

        id_execucao = (
            cursor.fetchone()[0]
        )

    conexao.commit()

    return id_execucao


# ============================================================
# CONFIGURAÇÃO / DIRETÓRIO
# ============================================================

def diretorios_do_layout(
    diretorios,
    id_configuracao
):
    return [
        diretorio
        for diretorio in diretorios
        if int(diretorio[0])
        == int(id_configuracao)
    ]


def localizar_pasta_mes(
    raiz,
    mes
):
    """
    Distribuidoras:
        01 - JANEIRO
        02 - FEVEREIRO
        ...
    """

    padrao = re.compile(
        rf"^\s*{mes:02d}\s*[-_]"
    )

    for pasta in raiz.iterdir():
        if (
            pasta.is_dir()
            and padrao.search(
                pasta.name.upper()
            )
        ):
            return pasta

    return None


def localizar_pasta_banco(
    pasta_mes,
    nome_banco,
    prefixo
):
    nome_normalizado = normalizar_chave(
        nome_banco
    )

    nome_base_normalizado = normalizar_chave(
        str(nome_banco or "").split(" - ")[0]
    )

    prefixo_normalizado = normalizar_chave(
        prefixo
    )

    for pasta in pasta_mes.iterdir():
        if not pasta.is_dir():
            continue

        chave = normalizar_chave(
            pasta.name
        )

        if chave == prefixo_normalizado:
            return pasta

        if chave == nome_normalizado:
            return pasta

        if chave == nome_base_normalizado:
            return pasta

        # BB / Banco do Brasil
        if (
            prefixo_normalizado == "BB"
            and chave in (
                "BB",
                "BANCODOBRASIL"
            )
        ):
            return pasta

    return None


# ============================================================
# IDENTIFICAÇÃO DE ARQUIVO - POSTOS
# ============================================================

def identificar_layout_postos(
    arquivo,
    layout_bruto
):
    id_arquivo = layout_bruto[0]
    nome = layout_bruto[1]
    prefixo = layout_bruto[2]
    extensao = layout_bruto[3]
    abas = layout_bruto[4]
    id_configuracao = layout_bruto[5]

    nome_arquivo = (
        arquivo.name.upper()
    )

    extensao_arquivo = (
        arquivo.suffix
        .lower()
        .replace(".", "")
    )

    prefixo_comparacao = (
        str(prefixo or "")
        .strip()
        .upper()
    )

    extensao_comparacao = (
        str(extensao or "")
        .strip()
        .lower()
        .replace(".", "")
    )

    if not nome_arquivo.startswith(
        prefixo_comparacao
    ):
        return None

    if (
        extensao_arquivo
        != extensao_comparacao
    ):
        return None

    return {
        "id": id_arquivo,
        "nome": nome,
        "prefixo": prefixo_comparacao,
        "extensao": extensao_comparacao,
        "abas": abas,
        "id_configuracao": id_configuracao
    }


def montar_layout(
    layout_bruto
):
    return {
        "id": layout_bruto[0],
        "nome": layout_bruto[1],
        "prefixo": str(
            layout_bruto[2] or ""
        ).strip().upper(),
        "extensao": str(
            layout_bruto[3] or ""
        ).strip().lower().replace(
            ".",
            ""
        ),
        "abas": layout_bruto[4],
        "id_configuracao": layout_bruto[5],
        "extrator": layout_bruto[6]
    }


# ============================================================
# EXTRAÇÃO
# ============================================================

def carregar_extrator(layout):
    nome_modulo = str(
        layout.get("extrator") or ""
    ).strip()

    if not nome_modulo:
        raise ValueError(
            f"Layout ID {layout['id']} não possui extrator configurado "
            "em extratos.arquivos_bancos."
        )

    modulo = importlib.import_module(
        nome_modulo
    )

    funcoes = [
        getattr(modulo, nome)
        for nome in dir(modulo)
        if nome.startswith("extrair_")
        and callable(getattr(modulo, nome))
        and getattr(modulo, nome).__module__ == modulo.__name__
    ]

    if len(funcoes) != 1:
        raise ValueError(
            f"Extrator '{nome_modulo}' deve possuir exatamente uma "
            "função pública iniciada por 'extrair_'. "
            f"Encontradas: {len(funcoes)}."
        )

    return funcoes[0]


def extrair_registros(
    arquivo,
    layout,
    campos_configurados
):
    nome_extrator = str(
        layout.get("extrator") or ""
    ).strip()

    if nome_extrator in (
        "extrator_pdf_generico",
        "extrator_xls_generico",
        "extrator_xlsx_generico"
    ):
        extensao = str(
            layout.get("extensao") or ""
        ).strip().lower().replace(".", "")

        abas = layout.get(
            "abas"
        )

        if extensao == "pdf":
            return extrair_pdf_generico(
                arquivo,
                abas=abas
            )

        if extensao == "xls":
            return extrair_xls_generico(
                arquivo,
                abas=abas
            )

        if extensao == "xlsx":
            return extrair_xlsx_generico(
                arquivo,
                abas=abas
            )

        return []

    funcao_extrator = carregar_extrator(
        layout
    )

    return funcao_extrator(
        arquivo,
        campos_configurados
    )


# ============================================================
# COLETA DE DATAS
# ============================================================

def coletar_datas_arquivo(
    arquivo,
    layout,
    de_para
):
    campo_data = buscar_campo_data_origem(
        de_para
    )

    if campo_data is None:
        return []

    try:
        registros = extrair_registros(
            arquivo,
            layout,
            list(de_para.keys())
        )

    except Exception as erro:
        print(
            f"    [ERRO ARQUIVO] "
            f"{arquivo.name}: {erro}"
        )
        return []

    datas = []

    for registro in registros:
        registro_normalizado = {
            normalizar_chave(chave): valor
            for chave, valor
            in registro.items()
        }

        data_registro = como_data(
            registro_normalizado.get(
                campo_data
            )
        )

        if data_registro is not None:
            datas.append(
                data_registro
            )

    return datas


# ============================================================
# POSTOS
# ============================================================

def analisar_postos(
    conexao,
    diretorios,
    layout_bruto,
    de_para,
    ultima_data_fim
):
    datas_novas = []
    arquivos_encontrados = 0

    for diretorio in diretorios:
        raiz = Path(
            diretorio[1]
        )

        if not raiz.exists():
            continue

        for arquivo in raiz.rglob("*"):
            if not arquivo.is_file():
                continue

            layout = identificar_layout_postos(
                arquivo,
                layout_bruto
            )

            if layout is None:
                continue

            arquivos_encontrados += 1

            datas = coletar_datas_arquivo(
                arquivo,
                layout,
                de_para
            )

            for data_registro in datas:
                if (
                    ultima_data_fim is not None
                    and data_registro
                    <= ultima_data_fim
                ):
                    continue

                datas_novas.append(
                    data_registro
                )

    print(
        f"[ARQUIVOS ENCONTRADOS] "
        f"{arquivos_encontrados}"
    )

    if not datas_novas:
        return None

    # Para postos preserva a regra existente:
    # trabalha com a competência mais recente encontrada.
    competencia = max(
        (
            item.year,
            item.month
        )
        for item in datas_novas
    )

    datas_competencia = [
        item
        for item in datas_novas
        if (
            item.year,
            item.month
        ) == competencia
    ]

    return inicio_fim_mes(
        min(datas_competencia)
    )


# ============================================================
# DISTRIBUIDORAS
# ============================================================

def analisar_distribuidoras(
    conexao,
    diretorios,
    layout_bruto,
    de_para,
    ultima_data_fim
):
    """
    Estrutura:
        raiz
        ├── 01 - JANEIRO
        │   ├── BB
        │   ├── ITAÚ
        │   └── ...
        ├── 02 - FEVEREIRO
        └── ...

    Para distribuidoras o nome do arquivo NÃO precisa
    começar pelo prefixo do banco. A pasta do banco
    identifica qual layout deve ser utilizado.

    Retorna TODAS as competências novas encontradas,
    em ordem cronológica.
    """

    layout = montar_layout(
        layout_bruto
    )

    competencias = {}

    for diretorio in diretorios:
        raiz = Path(
            diretorio[1]
        )

        if not raiz.exists():
            continue

        for pasta_mes in raiz.iterdir():
            if not pasta_mes.is_dir():
                continue

            resultado_mes = re.match(
                r"^\s*(\d{2})\s*[-_]",
                pasta_mes.name
            )

            if not resultado_mes:
                continue

            mes_pasta = int(
                resultado_mes.group(1)
            )

            if not 1 <= mes_pasta <= 12:
                continue

            pasta_banco = localizar_pasta_banco(
                pasta_mes,
                layout["nome"],
                layout["prefixo"]
            )

            if pasta_banco is None:
                continue

            print(
                f"    [MÊS/BANCO] "
                f"{pasta_mes.name} / "
                f"{pasta_banco.name}"
            )

            for arquivo in pasta_banco.rglob("*"):
                if not arquivo.is_file():
                    continue

                extensao_arquivo = (
                    arquivo.suffix
                    .lower()
                    .replace(".", "")
                )

                if (
                    extensao_arquivo
                    != layout["extensao"]
                ):
                    continue

                datas = coletar_datas_arquivo(
                    arquivo,
                    layout,
                    de_para
                )

                for data_registro in datas:
                    if (
                        data_registro.month
                        != mes_pasta
                    ):
                        continue

                    if (
                        ultima_data_fim is not None
                        and data_registro
                        <= ultima_data_fim
                    ):
                        continue

                    chave = (
                        data_registro.year,
                        data_registro.month
                    )

                    competencias.setdefault(
                        chave,
                        []
                    ).append(
                        data_registro
                    )

    if not competencias:
        return []

    periodos = []

    for ano, mes in sorted(
        competencias.keys()
    ):
        data_referencia = date(
            ano,
            mes,
            1
        )

        data_inicio, data_fim = inicio_fim_mes(
            data_referencia
        )

        periodos.append({
            "data_inicio": data_inicio,
            "data_fim": data_fim
        })

    return periodos


# ============================================================
# VARREDURA DE UM LAYOUT
# ============================================================

def analisar_layout(
    conexao,
    diretorios,
    layout_bruto
):
    id_arquivo = int(
        layout_bruto[0]
    )

    nome_banco = layout_bruto[1]

    prefixo = str(
        layout_bruto[2] or ""
    ).strip().upper()

    id_configuracao = int(
        layout_bruto[5]
    )

    print()
    print("=" * 70)
    print(
        f"[BANCO] {nome_banco} "
        f"| Prefixo {prefixo} "
        f"| ID {id_arquivo} "
        f"| Configuração {id_configuracao}"
    )

    de_para = buscar_de_para(
        conexao,
        id_arquivo
    )

    if not de_para:
        print(
            "[PULADO] Sem DE/PARA configurado."
        )
        return []

    if (
        buscar_campo_data_origem(
            de_para
        )
        is None
    ):
        print(
            "[PULADO] DE/PARA não possui "
            "campo de origem para Data."
        )
        return []

    diretorios_layout = diretorios_do_layout(
        diretorios,
        id_configuracao
    )

    if not diretorios_layout:
        print(
            "[PULADO] Nenhum diretório ativo "
            "para esta configuração."
        )
        return []

    ultima_data_fim = buscar_ultima_data_fim(
        conexao,
        id_arquivo
    )

    print(
        f"[ÚLTIMA DATA FIM] "
        f"{ultima_data_fim}"
    )

    finalidade = str(
        diretorios_layout[0][5]
        or ""
    ).strip().upper()

    resultados = []

    if finalidade == "DISTRIBUIDORAS":
        periodos = analisar_distribuidoras(
            conexao,
            diretorios_layout,
            layout_bruto,
            de_para,
            ultima_data_fim
        )

        if not periodos:
            print(
                "[SEM NOVIDADE] Nenhuma competência "
                "nova encontrada."
            )
            return []

        for periodo in periodos:
            data_inicio = periodo["data_inicio"]
            data_fim = periodo["data_fim"]

            print(
                f"[PERÍODO CANDIDATO] "
                f"{data_inicio} até {data_fim}"
            )

            if ja_existe_periodo(
                conexao,
                id_arquivo,
                data_inicio,
                data_fim
            ):
                print(
                    "[PULADO] Este banco/período "
                    "já existe no controle_servico."
                )
                continue

            resultados.append({
                "id_arquivo": id_arquivo,
                "nome_banco": nome_banco,
                "finalidade": finalidade,
                "id_configuracao": id_configuracao,
                "data_inicio": data_inicio,
                "data_fim": data_fim
            })

        return resultados

    periodo = analisar_postos(
        conexao,
        diretorios_layout,
        layout_bruto,
        de_para,
        ultima_data_fim
    )

    if periodo is None:
        print(
            "[SEM NOVIDADE] Nenhuma competência "
            "nova encontrada."
        )
        return []

    data_inicio, data_fim = periodo

    print(
        f"[PERÍODO CANDIDATO] "
        f"{data_inicio} até {data_fim}"
    )

    if ja_existe_periodo(
        conexao,
        id_arquivo,
        data_inicio,
        data_fim
    ):
        print(
            "[PULADO] Este banco/período "
            "já existe no controle_servico."
        )
        return []

    resultados.append({
        "id_arquivo": id_arquivo,
        "nome_banco": nome_banco,
        "finalidade": finalidade,
        "id_configuracao": id_configuracao,
        "data_inicio": data_inicio,
        "data_fim": data_fim
    })

    return resultados


# ============================================================
# MAIN
# ============================================================

def main():

    with conectar() as conexao:

        diretorios = buscar_diretorios(
            conexao
        )

        layouts = buscar_arquivos_bancos(
            conexao
        )

        if not diretorios:
            print(
                "Nenhum diretório ativo cadastrado."
            )
            return

        if not layouts:
            print(
                "Nenhum arquivo de banco "
                "ativo cadastrado."
            )
            return

        print()
        print("=" * 70)
        print("AGENTE ANALISTA")
        print(
            f"Data: "
            f"{datetime.now():%d/%m/%Y %H:%M:%S}"
        )
        print("=" * 70)

        criadas = 0

        # Cada layout/banco é analisado separadamente.
        # Distribuidoras pode retornar várias competências
        # no mesmo ciclo.
        for layout in layouts:

            resultados = analisar_layout(
                conexao,
                diretorios,
                layout
            )

            if not resultados:
                continue

            for resultado in resultados:

                id_execucao = criar_controle_servico(
                    conexao=conexao,
                    id_arquivo=resultado[
                        "id_arquivo"
                    ],
                    data_inicio=resultado[
                        "data_inicio"
                    ],
                    data_fim=resultado[
                        "data_fim"
                    ]
                )

                criadas += 1

                print()
                print(
                    "[CONTROLE AUTOMÁTICO CRIADO]"
                )
                print(
                    f"ID execução: {id_execucao}"
                )
                print(
                    f"id_arquivo: "
                    f"{resultado['id_arquivo']}"
                )
                print(
                    f"Banco: "
                    f"{resultado['nome_banco']}"
                )
                print(
                    f"Finalidade: "
                    f"{resultado['finalidade']}"
                )
                print(
                    f"data_inicio: "
                    f"{resultado['data_inicio']}"
                )
                print(
                    f"data_fim: "
                    f"{resultado['data_fim']}"
                )
                print(
                    "ação: INSERT"
                )
                print(
                    "executado: FALSE"
                )

        print()
        print("=" * 70)

        if criadas == 0:
            print(
                "[SEM ORDEM] Nenhuma nova "
                "execução foi criada."
            )
        else:
            print(
                f"[ORDENS CRIADAS] {criadas}"
            )

        print(
            "VARREDURA FINALIZADA"
        )
        print("=" * 70)


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
            print(
                "[ERRO NO AGENTE ANALISTA]"
            )
            print(erro)
            print("=" * 70)

        print()
        print(
            "Próxima varredura em 24 horas."
        )

        time.sleep(
            INTERVALO_SEGUNDOS
        )