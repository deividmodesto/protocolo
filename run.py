from app import create_app

# Cria a aplicação chamando a nossa factory function
app = create_app()

if __name__ == '__main__':
    # Executa a aplicação na porta que você pediu e com o modo debug ativo
    app.run(host='0.0.0.0', port=5041, debug=True)