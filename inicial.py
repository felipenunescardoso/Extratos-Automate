import os

import psycopg
from dotenv import load_dotenv


load_dotenv()


DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


def conectar():
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=5
    )


def testar_conexao():
    try:
        with conectar() as conexao:

            with conexao.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        current_database(),
                        current_user,
                        version()
                """)

                resultado = cursor.fetchone()

                print("Conexão realizada com sucesso!")

    except Exception as erro:
        print("Erro ao conectar no PostgreSQL:")
        print(erro)


if __name__ == "__main__":
    testar_conexao()