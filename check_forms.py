print("--- Iniciando verificação do módulo app.forms ---")

try:
    # Tenta importar o módulo problemático
    import app.forms
    print("SUCESSO: O arquivo 'app/forms.py' foi encontrado e importado.")

    print("\nConteúdo encontrado dentro de 'app.forms':")

    # Lista tudo que o Python encontrou dentro do módulo
    conteudo_encontrado = []
    for item in dir(app.forms):
        # Ignora os itens internos do Python que começam com '__'
        if not item.startswith('__'):
            conteudo_encontrado.append(item)

    if conteudo_encontrado:
        for item in sorted(conteudo_encontrado):
             print(f"- {item}")
    else:
        print("- Nenhum conteúdo exportável encontrado.")

    # Verificação final e definitiva
    if 'ProtocoloForm' in conteudo_encontrado:
        print("\n✅ MISTÉRIO: A classe 'ProtocoloForm' FOI encontrada. O problema é mais complexo.")
    else:
        print("\n❌ DIAGNÓSTICO: A classe 'ProtocoloForm' NÃO foi encontrada. A versão do arquivo no disco está desatualizada.")

except ImportError:
    print("\n❌ FALHA CRÍTICA: O arquivo 'app/forms.py' não pôde ser importado. Verifique se há erros de sintaxe nele.")
except Exception as e:
    print(f"\n❌ Ocorreu um erro inesperado: {e}")