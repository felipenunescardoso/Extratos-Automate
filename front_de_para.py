import streamlit as st

from inicial import conectar


st.set_page_config(
    page_title="DE/PARA Bancos",
    page_icon="🏦",
    layout="wide"
)


# ============================================================
# BANCO
# ============================================================

def buscar_bancos():
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT
                    id,
                    nome,
                    prefixo,
                    extensao
                FROM extratos.arquivos_bancos
                WHERE ativo = TRUE
                ORDER BY nome
            """)

            return cursor.fetchall()


def buscar_de_para(id_arquivo):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT
                    dp.nome_campo_arquivo,
                    dp.nome_campo_planilha_mae
                FROM extratos.de_para_banco_planilha_mae dp
                INNER JOIN extratos.arquivos_bancos ab
                    ON ab.id = dp.id_arquivo
                WHERE dp.id_arquivo = %s
                ORDER BY
                    dp.nome_campo_arquivo
            """, (
                id_arquivo,
            ))

            return cursor.fetchall()


def inserir_de_para(
    id_arquivo,
    campo_arquivo,
    campo_planilha
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                INSERT INTO
                    extratos.de_para_banco_planilha_mae
                (
                    id_arquivo,
                    nome_campo_arquivo,
                    nome_campo_planilha_mae
                )
                VALUES
                (
                    %s,
                    %s,
                    %s
                )
            """, (
                id_arquivo,
                campo_arquivo,
                campo_planilha
            ))

        conexao.commit()


def excluir_de_para(
    id_arquivo,
    campo_arquivo
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                DELETE FROM
                    extratos.de_para_banco_planilha_mae
                WHERE id_arquivo = %s
                  AND nome_campo_arquivo = %s
            """, (
                id_arquivo,
                campo_arquivo
            ))

        conexao.commit()


# ============================================================
# INTERFACE
# ============================================================

st.title(
    "DE/PARA - Bancos"
)

st.caption(
    "Configuração dos campos dos extratos "
    "para a Planilha Mãe."
)


bancos = buscar_bancos()

if not bancos:
    st.warning(
        "Nenhum banco ativo cadastrado."
    )

    st.stop()


# ============================================================
# IDENTIFICADOR VISUAL
# ============================================================

opcoes_bancos = {}

for (
    id_arquivo,
    nome,
    prefixo,
    extensao
) in bancos:

    identificador = (
        f"{nome} "
        f"({prefixo} / {extensao})"
    )

    opcoes_bancos[
        identificador
    ] = id_arquivo


banco_selecionado = st.selectbox(
    "Banco / Layout",
    options=list(
        opcoes_bancos.keys()
    )
)


id_arquivo = opcoes_bancos[
    banco_selecionado
]


st.info(
    f"ID do arquivo: {id_arquivo}"
)


# ============================================================
# NOVO DE/PARA
# ============================================================

st.subheader(
    "Adicionar campo"
)


col1, col2 = st.columns(2)


with col1:

    campo_arquivo = st.text_input(
        "Campo no arquivo",
        placeholder="Ex.: Histórico"
    )


with col2:

    campo_planilha = st.text_input(
        "Campo na Planilha Mãe",
        placeholder="Ex.: Descritivo Bancário"
    )


if st.button(
    "Adicionar DE/PARA",
    type="primary",
    use_container_width=True
):

    campo_arquivo = (
        campo_arquivo.strip()
    )

    campo_planilha = (
        campo_planilha.strip()
    )

    if not campo_arquivo:

        st.error(
            "Informe o campo do arquivo."
        )

    elif not campo_planilha:

        st.error(
            "Informe o campo da Planilha Mãe."
        )

    else:

        try:

            inserir_de_para(
                id_arquivo,
                campo_arquivo,
                campo_planilha
            )

            st.success(
                "DE/PARA cadastrado."
            )

            st.rerun()

        except Exception as erro:

            st.error(
                f"Erro ao cadastrar: {erro}"
            )


# ============================================================
# DE/PARA CADASTRADO
# ============================================================

st.divider()

st.subheader(
    f"Campos cadastrados - {banco_selecionado}"
)


registros = buscar_de_para(
    id_arquivo
)


if not registros:

    st.info(
        "Este banco ainda não possui "
        "DE/PARA cadastrado."
    )

else:

    for (
        campo_origem,
        campo_destino
    ) in registros:

        col1, col2, col3 = st.columns(
            [4, 4, 1]
        )


        with col1:

            st.text_input(
                "Campo arquivo",
                value=campo_origem,
                disabled=True,
                key=(
                    f"origem_"
                    f"{id_arquivo}_"
                    f"{campo_origem}"
                )
            )


        with col2:

            st.text_input(
                "Planilha Mãe",
                value=campo_destino,
                disabled=True,
                key=(
                    f"destino_"
                    f"{id_arquivo}_"
                    f"{campo_origem}"
                )
            )


        with col3:

            st.write("")

            st.write("")

            if st.button(
                "Excluir",
                key=(
                    f"excluir_"
                    f"{id_arquivo}_"
                    f"{campo_origem}"
                )
            ):

                excluir_de_para(
                    id_arquivo,
                    campo_origem
                )

                st.rerun()





