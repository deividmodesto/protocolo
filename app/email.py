from threading import Thread
from flask import current_app, render_template
from flask_mail import Message
from . import mail

def send_async_email(app, msg):
    """Função que roda em uma thread para enviar o email."""
    with app.app_context():
        mail.send(msg)

def send_email(subject, recipients, template, **kwargs):
    """Função principal para preparar e disparar o envio de email em segundo plano."""
    # Pega a instância atual da aplicação
    app = current_app._get_current_object()

    # Cria a mensagem de email
    msg = Message(
        subject,
        sender=f"Sistema de Protocolo <{app.config['MAIL_USERNAME']}>",
        recipients=recipients
    )

    # Renderiza o corpo do email a partir de um template HTML
    msg.html = render_template(template + '.html', **kwargs)

    # Cria e inicia a thread para enviar o email de forma assíncrona
    thr = Thread(target=send_async_email, args=[app, msg])
    thr.start()
    return thr