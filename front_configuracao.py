import streamlit as st

from inicial import conectar


st.set_page_config(
    page_title="Configuração de Diretórios",
    page_icon="📁",
    layout="wide"
)


# ============================================================
# BANCO
# ============================================================

def buscar_diretorios():
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT
                    id,
                    diretorio,
                    tipo,
                    usuario,
                    senha,
                    ativo
                FROM extratos.diretorios
                ORDER BY id
            """)

            return cursor.fetchall()


def buscar_diretorio_por_id(id_diretorio):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT
                    id,
                    diretorio,
                    tipo,
                    usuario,
                    senha,
                    ativo
                FROM extratos.diretorios
                WHERE id = %s
            """, (
                id_diretorio,
            ))

            return cursor.fetchone()


def inserir_diretorio(
    diretorio,
    tipo,
    usuario,
    senha,
    ativo
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                INSERT INTO extratos.diretorios
                (
                    diretorio,
                    tipo,
                    usuario,
                    senha,
                    ativo
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (
                diretorio,
                tipo,
                usuario or None,
                senha or None,
                ativo
            ))

        conexao.commit()


def atualizar_diretorio(
    id_diretorio,
    diretorio,
    tipo,
    usuario,
    senha,
    ativo
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                UPDATE extratos.diretorios
                SET
                    diretorio = %s,
                    tipo = %s,
                    usuario = %s,
                    senha = %s,
                    ativo = %s
                WHERE id = %s
            """, (
                diretorio,
                tipo,
                usuario or None,
                senha or None,
                ativo,
                id_diretorio
            ))

        conexao.commit()


def excluir_diretorio(id_diretorio):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                DELETE FROM extratos.diretorios
                WHERE id = %s
            """, (
                id_diretorio,
            ))

        conexao.commit()


# ============================================================
# TELA
# ============================================================

st.title(
    "Configuração de Diretórios"
)

st.caption(
    "Cadastro dos diretórios usados pelo sistema de Extratos."
)


aba_novo, aba_editar, aba_excluir = st.tabs(
    [
        "Novo diretório",
        "Alterar diretório",
        "Excluir diretório"
    ]
)


# ============================================================
# NOVO
# ============================================================

with aba_novo:

    st.subheader(
        "Cadastrar diretório"
    )

    diretorio_novo = st.text_input(
        "Diretório",
        placeholder=(
            r"D:\AutomateBancos\EXTRATOS MENSAIS"
        ),
        key="diretorio_novo"
    )

    tipo_novo = st.selectbox(
        "Tipo",
        [
            "Local",
            "Rede"
        ],
        key="tipo_novo"
    )

    col1, col2 = st.columns(2)

    with col1:

        usuario_novo = st.text_input(
            "Usuário",
            help=(
                "Opcional. Use para diretórios de rede."
            ),
            key="usuario_novo"
        )

    with col2:

        senha_nova = st.text_input(
            "Senha",
            type="password",
            help=(
                "Opcional. Use para diretórios de rede."
            ),
            key="senha_nova"
        )

    ativo_novo = st.checkbox(
        "Ativo",
        value=True,
        key="ativo_novo"
    )

    if st.button(
        "Cadastrar diretório",
        type="primary",
        use_container_width=True
    ):

        diretorio_novo = (
            diretorio_novo.strip()
        )

        if not diretorio_novo:

            st.error(
                "Informe o diretório."
            )

        else:

            try:

                inserir_diretorio(
                    diretorio=diretorio_novo,
                    tipo=tipo_novo,
                    usuario=usuario_novo.strip(),
                    senha=senha_nova,
                    ativo=ativo_novo
                )

                st.success(
                    "Diretório cadastrado."
                )

                st.rerun()

            except Exception as erro:

                st.error(
                    f"Erro ao cadastrar: {erro}"
                )


# ============================================================
# ALTERAR
# ============================================================

with aba_editar:

    st.subheader(
        "Alterar diretório"
    )

    diretorios = buscar_diretorios()

    if not diretorios:

        st.info(
            "Nenhum diretório cadastrado."
        )

    else:

        opcoes = {}

        for (
            id_diretorio,
            caminho,
            tipo,
            usuario,
            senha,
            ativo
        ) in diretorios:

            descricao = (
                f"{id_diretorio} - "
                f"{caminho}"
            )

            opcoes[
                descricao
            ] = id_diretorio


        selecionado = st.selectbox(
            "Diretório",
            options=list(
                opcoes.keys()
            ),
            key="editar_diretorio"
        )


        id_diretorio = opcoes[
            selecionado
        ]


        registro = buscar_diretorio_por_id(
            id_diretorio
        )


        if registro:

            (
                id_diretorio,
                caminho_atual,
                tipo_atual,
                usuario_atual,
                senha_atual,
                ativo_atual
            ) = registro


            caminho_edicao = st.text_input(
                "Diretório",
                value=(
                    caminho_atual
                    or ""
                ),
                key=f"caminho_edicao_{id_diretorio}"
            )


            tipos = [
                "Local",
                "Rede"
            ]

            indice_tipo = (
                tipos.index(
                    tipo_atual
                )
                if tipo_atual in tipos
                else 0
            )


            tipo_edicao = st.selectbox(
                "Tipo",
                tipos,
                index=indice_tipo,
                key=f"tipo_edicao_{id_diretorio}"
            )


            col1, col2 = st.columns(2)


            with col1:

                usuario_edicao = st.text_input(
                    "Usuário",
                    value=(
                        usuario_atual
                        or ""
                    ),
                    key=f"usuario_edicao_{id_diretorio}"
                )


            with col2:

                senha_edicao = st.text_input(
                    "Senha",
                    value=(
                        senha_atual
                        or ""
                    ),
                    type="password",
                    key=f"senha_edicao_{id_diretorio}"
                )


            ativo_edicao = st.checkbox(
                "Ativo",
                value=ativo_atual,
                key=f"ativo_edicao_{id_diretorio}"
            )


            if st.button(
                "Salvar alterações",
                use_container_width=True
            ):

                try:

                    atualizar_diretorio(
                        id_diretorio=id_diretorio,
                        diretorio=caminho_edicao.strip(),
                        tipo=tipo_edicao,
                        usuario=usuario_edicao.strip(),
                        senha=senha_edicao,
                        ativo=ativo_edicao
                    )

                    st.success(
                        "Diretório atualizado."
                    )

                    st.rerun()

                except Exception as erro:

                    st.error(
                        f"Erro ao atualizar: {erro}"
                    )


# ============================================================
# EXCLUIR
# ============================================================

with aba_excluir:

    st.subheader(
        "Excluir diretório"
    )

    diretorios = buscar_diretorios()

    if not diretorios:

        st.info(
            "Nenhum diretório cadastrado."
        )

    else:

        opcoes_exclusao = {}

        for (
            id_diretorio,
            caminho,
            tipo,
            usuario,
            senha,
            ativo
        ) in diretorios:

            descricao = (
                f"{id_diretorio} - "
                f"{caminho}"
            )

            opcoes_exclusao[
                descricao
            ] = id_diretorio


        excluir_selecionado = st.selectbox(
            "Diretório para excluir",
            options=list(
                opcoes_exclusao.keys()
            ),
            key="excluir_diretorio"
        )


        id_excluir = (
            opcoes_exclusao[
                excluir_selecionado
            ]
        )


        st.warning(
            "A exclusão remove o registro "
            "da tabela extratos.diretorios."
        )


        confirmar = st.checkbox(
            "Confirmo a exclusão deste diretório.",
            key="confirmar_exclusao_diretorio"
        )


        if st.button(
            "Excluir diretório",
            type="primary",
            use_container_width=True,
            disabled=not confirmar
        ):

            try:

                excluir_diretorio(
                    id_excluir
                )

                st.success(
                    "Diretório excluído."
                )

                st.rerun()

            except Exception as erro:

                st.error(
                    f"Erro ao excluir: {erro}"
                )