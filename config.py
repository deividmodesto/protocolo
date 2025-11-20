import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    """Classe de configuração da aplicação."""
    SECRET_KEY = os.environ.get('SECRET_KEY')

    # --- CONFIGURAÇÕES DE UPLOAD ---
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads/')
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx'}

    # --- CONFIGURAÇÕES DO BANCO DE DADOS PRINCIPAL ---
    DB_SERVER = os.environ.get('DB_SERVER')
    DB_NAME = os.environ.get('DB_NAME')
    DB_USER = os.environ.get('DB_USER')
    DB_PASSWORD = os.environ.get('DB_PASSWORD')

    # Monta a string de conexão principal de forma segura aqui dentro
    if DB_SERVER and DB_NAME and DB_USER and DB_PASSWORD:
        params = quote_plus(
            f'DRIVER={{ODBC Driver 17 for SQL Server}};'
            f'SERVER={DB_SERVER};'
            f'DATABASE={DB_NAME};'
            f'UID={DB_USER};'
            f'PWD={DB_PASSWORD};'
            f'TrustServerCertificate=yes;'
        )
        SQLALCHEMY_DATABASE_URI = f"mssql+pyodbc:///?odbc_connect={params}"
    else:
        SQLALCHEMY_DATABASE_URI = None

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- CONFIGURAÇÕES DE EMAIL ---
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 25)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

    # --- CONFIGURAÇÕES DO BANCO DE DADOS EXTERNO (FORNECEDORES) --- <--- MOVER PARA DENTRO DA CLASSE
    EXT_DB_SERVER = '172.16.1.223'
    EXT_DB_NAME = 'P12_BI'  # <--- IMPORTANTE: Substitua pelo nome correto!
    EXT_DB_USER = 'sa'
    EXT_DB_PASSWORD = 'Rp@T3ch#50'

    # String de conexão para o banco externo
    if EXT_DB_SERVER and EXT_DB_NAME and EXT_DB_USER and EXT_DB_PASSWORD:
         EXT_DB_CONN_STR = (
            f'DRIVER={{ODBC Driver 17 for SQL Server}};'
            f'SERVER={EXT_DB_SERVER};'
            f'DATABASE={EXT_DB_NAME};'
            f'UID={EXT_DB_USER};'
            f'PWD={EXT_DB_PASSWORD};'
            f'TrustServerCertificate=yes;'
        )
    else:
        EXT_DB_CONN_STR = None # Define como None se faltar alguma informação

# Fim da classe Config