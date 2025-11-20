import pyodbc

# String de conexão montada para o pyodbc, usando os dados do 'sa' e o IP.
# Note que o formato é um pouco diferente da URL do SQLAlchemy.
conn_str = (
    r'DRIVER={ODBC Driver 17 for SQL Server};'
    r'SERVER=172.16.1.223,1433;'  # Usamos IP,PORTA
    r'DATABASE=protocolo_db;'
    r'UID=sa;'
    r'PWD=Rp@T3ch#50;'
    r'TrustServerCertificate=yes;' # Evita problemas com certificado SSL em dev
)

print("Tentando conectar ao banco de dados com o usuário 'sa'...")
print(f"String de conexão: {conn_str}")

try:
    # Tenta estabelecer a conexão com um timeout de 5 segundos
    cnxn = pyodbc.connect(conn_str, timeout=5)
    print("\n🎉 SUCESSO! A conexão com o banco de dados foi estabelecida com sucesso! 🎉")
    
    # Cria um cursor e executa uma consulta simples para confirmar
    cursor = cnxn.cursor()
    cursor.execute("SELECT DB_NAME()") # Pergunta ao banco qual o nome dele
    row = cursor.fetchone()
    print(f"\nConectado ao banco de dados: {row[0]}")
    
    # Fecha a conexão
    cnxn.close()

except pyodbc.OperationalError as ex:
    print("\n❌ FALHA! A conexão falhou.")
    print("Se este teste falhar usando 'sa', há definitivamente um problema de rede/firewall.")
    print(f"Erro: {ex}")

except Exception as ex:
    print(f"\n❌ FALHA! Ocorreu um erro inesperado: {ex}")