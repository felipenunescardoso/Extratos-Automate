import streamlit as st

from inicial import conectar


st.set_page_config(
    page_title="Configuração de Bancos",
    page_icon="🏦",
    layout="wide"
)


# ============================================================
# FUNÇÕES DE BANCO
# ============================================================

def listar_arquivos_bancos():

    with conectar() as conexao:

        with conexao.cursor() as cursor:

            cursor.execute("""
                SELECT
                    id,
                    nome,
                    prefixo,
                    extensao,
                    ativo
                FROM extratos.arquivos_bancos
                ORDER BY id;
            """)

            return cursor.fetchall()


def cadastrar_arquivo_banco(
    nome,
    prefixo,
    extensao,
    ativo
):

    with conectar() as conexao:

        with conexao.cursor() as cursor:

            cursor.execute("""
                INSERT INTO extratos.arquivos_bancos
                (
                    nome,
                    prefixo,
                    extensao,
                    ativo
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s
                )
                RETURNING id;
            """, (
                nome,
                prefixo,
                extensao,
                ativo
            ))

            id_arquivo = cursor.fetchone()[0]

        conexao.commit()

    return id_arquivo


def atualizar_arquivo_banco(
    id_arquivo,
    nome,
    prefixo,
    extensao,
    ativo
):

    with conectar() as conexao:

        with conexao.cursor() as cursor:

            cursor.execute("""
                UPDATE extratos.arquivos_bancos
                SET
                    nome = %s,
                    prefixo = %s,
                    extensao = %s,
                    ativo = %s
                WHERE id = %s;
            """, (
                nome,
                prefixo,
                extensao,
                ativo,
                id_arquivo
            ))

        conexao.commit()


# ============================================================
# TÍTULO
# ============================================================

st.title("Configuração de Bancos")

st.caption(
    "Cadastre os layouts de extratos que poderão ser "
    "processados pelo serviço."
)


# ============================================================
# NOVO CADASTRO
# ============================================================

st.markdown("## Novo arquivo bancário")

with st.form(
    "form_novo_banco",
    clear_on_submit=True
):

    col1, col2 = st.columns(2)

    with col1:

        nome = st.text_input(
            "Nome do banco / layout"
        )

        prefixo = st.text_input(
            "Prefixo do arquivo"
        )

    with col2:

        extensao = st.selectbox(
            "Extensão",
            options=[
                "pdf",
                "xls",
                "xlsx"
            ]
        )

        ativo = st.checkbox(
            "Ativo",
            value=True
        )

    salvar = st.form_submit_button(
        "Salvar",
        type="primary",
        use_container_width=True
    )


if salvar:

    nome = nome.strip()

    prefixo = (
        prefixo
        .strip()
        .upper()
    )

    extensao = (
        extensao
        .strip()
        .lower()
        .replace(".", "")
    )

    if not nome:

        st.error(
            "Informe o nome."
        )

    elif not prefixo:

        st.error(
            "Informe o prefixo."
        )

    else:

        try:

            id_arquivo = cadastrar_arquivo_banco(
                nome=nome,
                prefixo=prefixo,
                extensao=extensao,
                ativo=ativo
            )

            st.success(
                f"Arquivo cadastrado com sucesso. "
                f"ID: {id_arquivo}"
            )

            st.rerun()

        except Exception as erro:

            if (
                "uq_bancos_prefixo_extensao"
                in str(erro)
                or "duplicate key"
                in str(erro).lower()
            ):

                st.error(
                    "Já existe um cadastro com "
                    "esse prefixo e extensão."
                )

            else:

                st.error(
                    f"Erro ao cadastrar: {erro}"
                )


# ============================================================
# LISTAGEM
# ============================================================

st.divider()

st.markdown(
    "## Arquivos cadastrados"
)

try:

    registros = listar_arquivos_bancos()

except Exception as erro:

    st.error(
        f"Erro ao consultar arquivos: {erro}"
    )

    registros = []


if not registros:

    st.info(
        "Nenhum arquivo bancário cadastrado."
    )

else:

    dados = []

    for registro in registros:

        dados.append(
            {
                "ID": registro[0],
                "Nome": registro[1],
                "Prefixo": registro[2],
                "Extensão": registro[3],
                "Ativo": registro[4]
            }
        )

    st.dataframe(
        dados,
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# EDIÇÃO
# ============================================================

if registros:

    st.divider()

    st.markdown(
        "## Editar cadastro"
    )

    opcoes = {
        f"{registro[0]} - {registro[1]} "
        f"({registro[2]}.{registro[3]})":
        registro
        for registro in registros
    }

    selecionado = st.selectbox(
        "Selecione o cadastro",
        options=list(
            opcoes.keys()
        )
    )

    registro = opcoes[
        selecionado
    ]

    id_arquivo = registro[0]

    with st.form(
        "form_editar_banco"
    ):

        col1, col2 = st.columns(2)

        with col1:

            nome_edicao = st.text_input(
                "Nome",
                value=registro[1]
            )

            prefixo_edicao = st.text_input(
                "Prefixo",
                value=registro[2]
            )

        with col2:

            extensoes = [
                "pdf",
                "xls",
                "xlsx"
            ]

            extensao_atual = (
                str(
                    registro[3]
                )
                .strip()
                .lower()
            )

            indice_extensao = (
                extensoes.index(
                    extensao_atual
                )
                if extensao_atual
                in extensoes
                else 0
            )

            extensao_edicao = st.selectbox(
                "Extensão",
                options=extensoes,
                index=indice_extensao
            )

            ativo_edicao = st.checkbox(
                "Ativo",
                value=bool(
                    registro[4]
                )
            )

        atualizar = st.form_submit_button(
            "Salvar alterações",
            type="primary",
            use_container_width=True
        )


    if atualizar:

        try:

            atualizar_arquivo_banco(
                id_arquivo=id_arquivo,
                nome=nome_edicao.strip(),
                prefixo=(
                    prefixo_edicao
                    .strip()
                    .upper()
                ),
                extensao=(
                    extensao_edicao
                    .strip()
                    .lower()
                    .replace(".", "")
                ),
                ativo=ativo_edicao
            )

            st.success(
                "Cadastro atualizado com sucesso."
            )

            st.rerun()

        except Exception as erro:

            if (
                "uq_bancos_prefixo_extensao"
                in str(erro)
                or "duplicate key"
                in str(erro).lower()
            ):

                st.error(
                    "Já existe outro cadastro com "
                    "esse prefixo e extensão."
                )

            else:

                st.error(
                    f"Erro ao atualizar: {erro}"
                )