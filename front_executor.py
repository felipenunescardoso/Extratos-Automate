import subprocess
import sys
from pathlib import Path

import streamlit as st
from inicial import conectar

st.set_page_config(page_title="Execução de Extratos", page_icon="▶️", layout="wide")

DIRETORIO_PROJETO = Path(r"C:\Extratos")
ORQUESTRADOR = DIRETORIO_PROJETO / "orquestrador.py"


def buscar_bancos():
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT id, nome, prefixo, extensao
                FROM extratos.arquivos_bancos
                WHERE ativo = TRUE
                ORDER BY nome
            """)
            return cursor.fetchall()


def buscar_pendentes():
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT cs.id_execucao, ab.nome, ab.prefixo,
                       cs.data_inicio, cs.data_fim, cs.acao, cs.data_log
                FROM extratos.controle_servico cs
                INNER JOIN extratos.arquivos_bancos ab
                    ON ab.id = cs.id_arquivo
                WHERE cs.executado = FALSE
                ORDER BY cs.id_execucao
            """)
            return cursor.fetchall()


def buscar_ultima_execucao(id_arquivo):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT id_execucao, data_inicio, data_fim,
                       acao, data_log, executado
                FROM extratos.controle_servico
                WHERE id_arquivo = %s
                ORDER BY id_execucao DESC
                LIMIT 1
            """, (id_arquivo,))
            return cursor.fetchone()


def marcar_para_reexecucao(id_execucao):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                UPDATE extratos.controle_servico
                SET executado = FALSE
                WHERE id_execucao = %s
            """, (id_execucao,))
        conexao.commit()


def executar_orquestrador():
    if not ORQUESTRADOR.exists():
        raise FileNotFoundError(
            f"Orquestrador não encontrado: {ORQUESTRADOR}"
        )

    processo = subprocess.run(
        [sys.executable, str(ORQUESTRADOR)],
        cwd=str(DIRETORIO_PROJETO),
        capture_output=True,
        text=True
    )

    return (
        processo.returncode,
        processo.stdout or "",
        processo.stderr or ""
    )


st.title("Execução de Extratos")
st.caption("Controle das execuções do Orquestrador.")

st.subheader("Execuções pendentes")

pendentes = buscar_pendentes()

if not pendentes:
    st.success("Nenhuma execução pendente.")
else:
    dados_pendentes = []

    for (
        id_execucao,
        banco,
        prefixo,
        data_inicio,
        data_fim,
        acao,
        data_log
    ) in pendentes:
        dados_pendentes.append({
            "Execução": id_execucao,
            "Banco": banco,
            "Prefixo": prefixo,
            "Data início": data_inicio,
            "Data fim": data_fim,
            "Ação": acao,
            "Criado em": data_log
        })

    st.dataframe(
        dados_pendentes,
        use_container_width=True,
        hide_index=True
    )

    if st.button(
        "▶ Executar tudo pendente",
        type="primary",
        use_container_width=True
    ):
        with st.spinner("Executando Orquestrador..."):
            (
                codigo_retorno,
                saida,
                erro
            ) = executar_orquestrador()

        if codigo_retorno == 0:
            st.success("Execução finalizada.")
        else:
            st.error("O Orquestrador retornou erro.")

        if saida:
            st.subheader("Saída")
            st.code(saida, language="text")

        if erro:
            st.subheader("Erros / avisos")
            st.code(erro, language="text")


st.divider()
st.subheader("Reexecutar banco")
st.write(
    "Selecione o banco. A última execução dele será marcada "
    "novamente como pendente e executada pelo Orquestrador."
)

bancos = buscar_bancos()

if not bancos:
    st.warning("Nenhum banco ativo cadastrado.")
else:
    opcoes = {
        f"{nome} ({prefixo} / {extensao})": id_arquivo
        for id_arquivo, nome, prefixo, extensao in bancos
    }

    banco_selecionado = st.selectbox(
        "Banco",
        options=list(opcoes.keys())
    )

    id_arquivo = opcoes[banco_selecionado]
    ultima_execucao = buscar_ultima_execucao(id_arquivo)

    if ultima_execucao is None:
        st.warning("Este banco ainda não possui execução.")
    else:
        (
            id_execucao,
            data_inicio,
            data_fim,
            acao,
            data_log,
            executado
        ) = ultima_execucao

        st.info(f"Última execução: {id_execucao}")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Data início", data_inicio.strftime("%d/%m/%Y"))

        with col2:
            st.metric("Data fim", data_fim.strftime("%d/%m/%Y"))

        with col3:
            st.metric("Ação", acao)

        st.write(
            "Status atual: "
            + ("**Executado**" if executado else "**Pendente**")
        )

        if st.button(
            "🔄 Reexecutar última execução",
            use_container_width=True
        ):
            marcar_para_reexecucao(id_execucao)

            with st.spinner(f"Reexecutando {banco_selecionado}..."):
                (
                    codigo_retorno,
                    saida,
                    erro
                ) = executar_orquestrador()

            if codigo_retorno == 0:
                st.success(f"Execução {id_execucao} reexecutada.")
            else:
                st.error("O Orquestrador retornou erro.")

            if saida:
                st.subheader("Saída")
                st.code(saida, language="text")

            if erro:
                st.subheader("Erros / avisos")
                st.code(erro, language="text")