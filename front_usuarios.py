import hashlib

import streamlit as st

from inicial import conectar


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Usuários",
    page_icon="👤",
    layout="wide"
)


# ============================================================
# SEGURANÇA
# ============================================================

def validar_acesso_admin():
    if not st.session_state.get("autenticado"):
        st.error(
            "Usuário não autenticado."
        )
        st.stop()

    if not st.session_state.get(
        "administrador",
        False
    ):
        st.error(
            "Acesso permitido somente para administradores."
        )
        st.stop()


validar_acesso_admin()


# ============================================================
# SENHA
# ============================================================

def gerar_hash_senha(senha):
    return hashlib.sha256(
        senha.encode("utf-8")
    ).hexdigest()


# ============================================================
# BANCO
# ============================================================

def buscar_usuarios():
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT
                    id_usuario,
                    nome,
                    usuario,
                    administrador,
                    ativo,
                    data_cadastro
                FROM extratos.usuarios
                ORDER BY nome
            """)

            return cursor.fetchall()


def buscar_usuario_por_id(
    id_usuario
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT
                    id_usuario,
                    nome,
                    usuario,
                    administrador,
                    ativo
                FROM extratos.usuarios
                WHERE id_usuario = %s
            """, (
                id_usuario,
            ))

            return cursor.fetchone()


def inserir_usuario(
    nome,
    usuario,
    senha,
    administrador,
    ativo
):
    senha_hash = gerar_hash_senha(
        senha
    )

    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                INSERT INTO extratos.usuarios
                (
                    nome,
                    usuario,
                    senha,
                    administrador,
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
                nome,
                usuario,
                senha_hash,
                administrador,
                ativo
            ))

        conexao.commit()


def atualizar_usuario(
    id_usuario,
    nome,
    usuario,
    administrador,
    ativo
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                UPDATE extratos.usuarios
                SET
                    nome = %s,
                    usuario = %s,
                    administrador = %s,
                    ativo = %s
                WHERE id_usuario = %s
            """, (
                nome,
                usuario,
                administrador,
                ativo,
                id_usuario
            ))

        conexao.commit()


def redefinir_senha(
    id_usuario,
    nova_senha
):
    senha_hash = gerar_hash_senha(
        nova_senha
    )

    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                UPDATE extratos.usuarios
                SET senha = %s
                WHERE id_usuario = %s
            """, (
                senha_hash,
                id_usuario
            ))

        conexao.commit()


# ============================================================
# TELA
# ============================================================

st.title(
    "Cadastro de Usuários"
)

st.caption(
    "Gerenciamento de usuários do sistema de Extratos."
)


aba_novo, aba_editar = st.tabs(
    [
        "Novo usuário",
        "Usuários cadastrados"
    ]
)


# ============================================================
# NOVO USUÁRIO
# ============================================================

with aba_novo:

    st.subheader(
        "Cadastrar usuário"
    )

    col1, col2 = st.columns(2)

    with col1:

        nome = st.text_input(
            "Nome"
        )

        usuario = st.text_input(
            "Usuário"
        )

    with col2:

        senha = st.text_input(
            "Senha",
            type="password"
        )

        confirmar_senha = st.text_input(
            "Confirmar senha",
            type="password"
        )

    col3, col4 = st.columns(2)

    with col3:

        administrador = st.checkbox(
            "Administrador"
        )

    with col4:

        ativo = st.checkbox(
            "Ativo",
            value=True
        )

    if st.button(
        "Cadastrar usuário",
        type="primary",
        use_container_width=True
    ):

        nome = nome.strip()
        usuario = usuario.strip()

        if not nome:

            st.error(
                "Informe o nome."
            )

        elif not usuario:

            st.error(
                "Informe o usuário."
            )

        elif not senha:

            st.error(
                "Informe a senha."
            )

        elif senha != confirmar_senha:

            st.error(
                "As senhas não conferem."
            )

        else:

            try:

                inserir_usuario(
                    nome=nome,
                    usuario=usuario,
                    senha=senha,
                    administrador=administrador,
                    ativo=ativo
                )

                st.success(
                    "Usuário cadastrado com sucesso."
                )

                st.rerun()

            except Exception as erro:

                st.error(
                    f"Erro ao cadastrar usuário: {erro}"
                )


# ============================================================
# USUÁRIOS CADASTRADOS
# ============================================================

with aba_editar:

    st.subheader(
        "Usuários cadastrados"
    )

    usuarios = buscar_usuarios()

    if not usuarios:

        st.info(
            "Nenhum usuário cadastrado."
        )

    else:

        dados = []

        opcoes = {}

        for (
            id_usuario,
            nome_usuario,
            login_usuario,
            admin_usuario,
            ativo_usuario,
            data_cadastro
        ) in usuarios:

            dados.append({
                "ID": id_usuario,
                "Nome": nome_usuario,
                "Usuário": login_usuario,
                "Administrador": (
                    "Sim"
                    if admin_usuario
                    else "Não"
                ),
                "Ativo": (
                    "Sim"
                    if ativo_usuario
                    else "Não"
                ),
                "Cadastro": data_cadastro
            })

            descricao = (
                f"{nome_usuario} "
                f"({login_usuario})"
            )

            opcoes[
                descricao
            ] = id_usuario

        st.dataframe(
            dados,
            use_container_width=True,
            hide_index=True
        )

        st.divider()

        usuario_selecionado = st.selectbox(
            "Selecionar usuário",
            options=list(
                opcoes.keys()
            )
        )

        id_usuario = opcoes[
            usuario_selecionado
        ]

        registro = buscar_usuario_por_id(
            id_usuario
        )

        if registro:

            (
                id_usuario,
                nome_atual,
                usuario_atual,
                admin_atual,
                ativo_atual
            ) = registro

            col1, col2 = st.columns(2)

            with col1:

                nome_edicao = st.text_input(
                    "Nome",
                    value=nome_atual,
                    key="nome_edicao"
                )

                usuario_edicao = st.text_input(
                    "Usuário",
                    value=usuario_atual,
                    key="usuario_edicao"
                )

            with col2:

                admin_edicao = st.checkbox(
                    "Administrador",
                    value=admin_atual,
                    key="admin_edicao"
                )

                ativo_edicao = st.checkbox(
                    "Ativo",
                    value=ativo_atual,
                    key="ativo_edicao"
                )

            if st.button(
                "Salvar alterações",
                use_container_width=True
            ):

                try:

                    atualizar_usuario(
                        id_usuario=id_usuario,
                        nome=nome_edicao.strip(),
                        usuario=usuario_edicao.strip(),
                        administrador=admin_edicao,
                        ativo=ativo_edicao
                    )

                    st.success(
                        "Usuário atualizado."
                    )

                    st.rerun()

                except Exception as erro:

                    st.error(
                        f"Erro ao atualizar: {erro}"
                    )

            st.divider()

            st.subheader(
                "Redefinir senha"
            )

            nova_senha = st.text_input(
                "Nova senha",
                type="password",
                key="nova_senha"
            )

            confirmar_nova_senha = st.text_input(
                "Confirmar nova senha",
                type="password",
                key="confirmar_nova_senha"
            )

            if st.button(
                "Redefinir senha",
                use_container_width=True
            ):

                if not nova_senha:

                    st.error(
                        "Informe a nova senha."
                    )

                elif (
                    nova_senha
                    != confirmar_nova_senha
                ):

                    st.error(
                        "As senhas não conferem."
                    )

                else:

                    try:

                        redefinir_senha(
                            id_usuario,
                            nova_senha
                        )

                        st.success(
                            "Senha redefinida."
                        )

                    except Exception as erro:

                        st.error(
                            f"Erro ao redefinir senha: {erro}"
                        )