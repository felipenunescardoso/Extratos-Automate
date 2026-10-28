import hashlib
import streamlit as st
from inicial import conectar

st.set_page_config(
    page_title="Extratos",
    page_icon="🏦",
    layout="wide"
)


def iniciar_sessao():
    padrao = {
        "autenticado": False,
        "id_usuario": None,
        "nome": None,
        "usuario": None,
        "administrador": False
    }

    for chave, valor in padrao.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor


def gerar_hash_senha(senha):
    return hashlib.sha256(
        senha.encode("utf-8")
    ).hexdigest()


def autenticar_usuario(usuario, senha):
    senha_hash = gerar_hash_senha(senha)

    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT
                    id_usuario,
                    nome,
                    usuario,
                    administrador
                FROM extratos.usuarios
                WHERE UPPER(usuario) = UPPER(%s)
                  AND senha = %s
                  AND ativo = TRUE
                LIMIT 1
            """, (
                usuario,
                senha_hash
            ))

            return cursor.fetchone()


def sair():
    st.session_state["autenticado"] = False
    st.session_state["id_usuario"] = None
    st.session_state["nome"] = None
    st.session_state["usuario"] = None
    st.session_state["administrador"] = False
    st.rerun()


def pagina_login():
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 520px;
            padding-top: 8rem;
        }

        .titulo-login {
            text-align: center;
            font-size: 36px;
            font-weight: 800;
            margin-bottom: 6px;
        }

        .subtitulo-login {
            text-align: center;
            opacity: 0.70;
            margin-bottom: 35px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="titulo-login">Extratos</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="subtitulo-login">'
        'Automação e consolidação bancária'
        '</div>',
        unsafe_allow_html=True
    )

    with st.form("form_login"):
        usuario = st.text_input("Usuário")
        senha = st.text_input(
            "Senha",
            type="password"
        )

        entrar = st.form_submit_button(
            "Entrar",
            type="primary",
            use_container_width=True
        )

    if entrar:
        usuario = usuario.strip()

        if not usuario or not senha:
            st.error("Informe usuário e senha.")
            return

        try:
            registro = autenticar_usuario(
                usuario,
                senha
            )

        except Exception as erro:
            st.error(
                f"Falha ao conectar ao banco: {erro}"
            )
            return

        if not registro:
            st.error(
                "Usuário ou senha inválidos."
            )
            return

        (
            id_usuario,
            nome,
            login_usuario,
            administrador
        ) = registro

        st.session_state["autenticado"] = True
        st.session_state["id_usuario"] = id_usuario
        st.session_state["nome"] = nome
        st.session_state["usuario"] = login_usuario
        st.session_state["administrador"] = bool(
            administrador
        )

        st.rerun()


def pagina_inicial():
    nome = (
        st.session_state.get("nome")
        or st.session_state.get("usuario")
        or ""
    )

    st.title("Extratos")
    st.write(
        f"Bem-vindo, **{nome}**."
    )

    if st.session_state.get(
        "administrador",
        False
    ):
        st.caption("Perfil: Administrador")
    else:
        st.caption("Perfil: Usuário")

    st.divider()
    st.subheader("Módulos")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            """
            **Bancos**  
            Cadastro dos layouts e arquivos bancários.

            **DE/PARA**  
            Relacionamento entre os campos dos bancos
            e as colunas da Planilha Mãe.

            **Execução**  
            Consulta e reexecução das cargas.
            """
        )

    with col2:
        st.markdown(
            """
            **Configuração**  
            Diretórios utilizados pelo sistema.

            **Usuários**  
            Cadastro e manutenção dos acessos.
            Disponível somente para administradores.
            """
        )

    st.divider()

    if st.button("Sair"):
        sair()


iniciar_sessao()

if not st.session_state["autenticado"]:
    pagina_login()

else:
    paginas = {
        "Sistema": [
            st.Page(
                pagina_inicial,
                title="Início",
                icon="🏠",
                default=True
            ),
            st.Page(
                "front_executor.py",
                title="Execução",
                icon="▶️"
            )
        ],

        "Cadastros": [
            st.Page(
                "front_bancos.py",
                title="Bancos",
                icon="🏦"
            ),
            st.Page(
                "front_de_para.py",
                title="DE/PARA",
                icon="🔄"
            ),
            st.Page(
                "front_configuracao.py",
                title="Diretórios",
                icon="📁"
            )
        ]
    }

    if st.session_state.get(
        "administrador",
        False
    ):
        paginas["Administração"] = [
            st.Page(
                "front_usuarios.py",
                title="Usuários",
                icon="👤"
            )
        ]

    navegacao = st.navigation(paginas)

    with st.sidebar:
        st.markdown(
            f"**{st.session_state.get('nome')}**"
        )

        if st.session_state.get(
            "administrador",
            False
        ):
            st.caption("Administrador")
        else:
            st.caption("Usuário")

        st.divider()

        if st.button(
            "Sair",
            use_container_width=True,
            key="logout_sidebar"
        ):
            sair()

    navegacao.run()
