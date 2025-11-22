from flask import render_template, redirect, url_for, flash, Blueprint, request, current_app, send_from_directory, make_response, abort, send_file, jsonify
from flask_login import login_user, logout_user, current_user, login_required
from app import db, csrf, format_datetime_local
from app.models import Colaborador, Setor, Protocolo, Historico, Anexo, ProtocoloModelo, CampoModelo, Fornecedor, Perfil, Permissao
from datetime import date, datetime, timedelta, timezone
from functools import wraps
import os 
from werkzeug.utils import secure_filename
from sqlalchemy import or_, func, text, literal_column
import sqlalchemy as sa
from app.email import send_email
import pandas as pd
from io import BytesIO
from weasyprint.css import CSS
import zlib
import base64
from zeep import Client, xsd # Importa o xsd para tratamento de schema
from zeep.transports import Transport
from requests import Session
from requests.auth import HTTPBasicAuth
from requests_pkcs12 import Pkcs12Adapter
from zeep.helpers import serialize_object
from lxml import etree
from sqlalchemy.orm import joinedload
import warnings
from urllib3.exceptions import InsecureRequestWarning
from config import Config
import json
import pyodbc
warnings.simplefilter('ignore', InsecureRequestWarning)
from sqlalchemy import func
from sqlalchemy.orm.attributes import flag_modified

# Imports que antes estavam em forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, TextAreaField, MultipleFileField, DateField, BooleanField, SelectMultipleField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, Optional, Length
from flask import make_response
from weasyprint import HTML
from brazilfiscalreport.danfe import Danfe


# ===================================================================
# FUNÇÃO AUXILIAR E DECORATOR
# ===================================================================
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def permission_required(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.tem_permissao(permission):
                abort(403) # Erro de Acesso Proibido
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ===================================================================
# FUNÇÃO AUXILIAR E DECORATOR
# ===================================================================
def _obter_xml_por_chave_sefaz(chave_acesso):
    """
    Consulta automática da NF-e por chave de acesso.
    Seleciona o webservice correto de acordo com a UF (cUF) da chave.
    """
    try:
        # =========================
        # MAPA UF -> URL PRODUÇÃO
        # =========================
        WSDL_CONSULTA_NFE = {
            "11": "https://nfe.sefaz.ac.gov.br/nfe/services/NFeConsultaProtocolo4?wsdl",
            "12": "https://nfe.sefaz.ac.gov.br/nfe/services/NFeConsultaProtocolo4?wsdl",
            "13": "https://nfe.sefaz.am.gov.br/services2/services/NfeConsulta4?wsdl",
            "14": "https://nfe.sefaz.rr.gov.br/nfe/services/NFeConsultaProtocolo4?wsdl",
            "15": "https://nfe.sefaz.pa.gov.br/nfe/services/NFeConsultaProtocolo4?wsdl",
            "16": "https://nfe.sefaz.ap.gov.br/nfe/services/NFeConsultaProtocolo4?wsdl",
            "17": "https://nfe.sefaz.to.gov.br/nfe/services/NFeConsultaProtocolo4?wsdl",
            "21": "https://nfe.sefaz.ma.gov.br/ws/NFeConsultaProtocolo4?wsdl",
            "22": "https://nfe.sefaz.pi.gov.br/nfe/services/NFeConsultaProtocolo4?wsdl",
            "23": "https://nfe.sefaz.ce.gov.br/nfe/services/NFeConsultaProtocolo4?wsdl",
            "24": "https://nfe.set.rn.gov.br/ws/NFeConsultaProtocolo4?wsdl",
            "25": "https://www.sefaz.pb.gov.br/nfe/services/NFeConsultaProtocolo4?wsdl",
            "26": "https://nfe.sefaz.pe.gov.br/nfe-service/services/NFeConsultaProtocolo4?wsdl",
            "27": "https://nfe.sefaz.al.gov.br/nfe/services/NFeConsultaProtocolo4?wsdl",
            "28": "https://nfe.sefaz.se.gov.br/nfe/services/NFeConsultaProtocolo4?wsdl",
            "29": "https://nfe.sefaz.ba.gov.br/webservices/NFeConsultaProtocolo4/NFeConsultaProtocolo4.asmx?wsdl",
            "31": "https://nfe.fazenda.mg.gov.br/nfe2/services/NFeConsultaProtocolo4?wsdl",
            "32": "https://www.nfe.fazenda.es.gov.br/ConsultaNFe/NFeConsultaProtocolo4?wsdl",
            "33": "https://nfe.fazenda.rj.gov.br/NFeConsultaProtocolo4/NFeConsultaProtocolo4.asmx?wsdl",
            "35": "https://nfe.fazenda.sp.gov.br/nfe/services/NFeConsultaProtocolo4?wsdl",
            "41": "https://nfe.sefa.pr.gov.br/nfe/NFeConsultaProtocolo4?wsdl",
            "42": "https://nfe.sef.sc.gov.br/nfe/services/NFeConsultaProtocolo4?wsdl",
            "43": "https://nfe.sefaz.rs.gov.br/ws/NfeConsultaProtocolo4/NfeConsultaProtocolo4.asmx?wsdl",
            "50": "https://nfe.sefaz.ms.gov.br/ws/NFeConsultaProtocolo4?wsdl",
            "51": "https://nfe.sefaz.mt.gov.br/nfews/v2/services/NfeConsulta4?wsdl",
            "52": "https://nfe.sefaz.go.gov.br/nfe/services/NFeConsultaProtocolo4?wsdl",
            "53": "https://nfe.fazenda.df.gov.br/nfe/services/NFeConsultaProtocolo4?wsdl",
        }

        # =========================
        # VERIFICAÇÃO DA CHAVE
        # =========================
        if not chave_acesso or len(chave_acesso) < 44:
            raise ValueError("Chave de acesso inválida.")
        uf_code = chave_acesso[:2]
        WSDL_URL = WSDL_CONSULTA_NFE.get(uf_code)
        if not WSDL_URL:
            raise ValueError(f"UF {uf_code} não mapeada para consulta NFe.")
        SERVICE_DOMAIN = WSDL_URL.split("/nfe")[0]  # para montar a sessão SSL

        # =========================
        # CERTIFICADO
        # =========================
        base_dir = current_app.root_path.replace('/app', '')
        CERT_FILENAME = '000181.pfx'
        CERT_PASSWORD = 'Fr12345'  # ajuste para a senha real
        CERT_FILE_PATH = os.path.join(base_dir, 'certs', CERT_FILENAME)
        if not os.path.exists(CERT_FILE_PATH):
            raise FileNotFoundError(f"Certificado não encontrado: {CERT_FILE_PATH}")

        # =========================
        # REQUISIÇÃO
        # =========================
        from requests import Session
        from requests_pkcs12 import Pkcs12Adapter
        from zeep import Client
        from zeep.transports import Transport
        from lxml import etree

        session = Session()
        session.verify = False
        session.mount(
            SERVICE_DOMAIN,
            Pkcs12Adapter(pkcs12_filename=CERT_FILE_PATH, pkcs12_password=CERT_PASSWORD)
        )
        transport = Transport(session=session)
        client = Client(wsdl=WSDL_URL, transport=transport)

        # Monta o XML de consulta
        NFE_NAMESPACE = "http://www.portalfiscal.inf.br/nfe"
        consSitNFe = etree.Element("consSitNFe", versao="4.00", xmlns=NFE_NAMESPACE)
        etree.SubElement(consSitNFe, "tpAmb").text = "1"       # 1 = produção
        etree.SubElement(consSitNFe, "xServ").text = "CONSULTAR"
        etree.SubElement(consSitNFe, "chNFe").text = chave_acesso

        # Chamada ao serviço
        resultado = client.service.nfeConsultaNF(consSitNFe)
        if resultado is None:
            flash("A SEFAZ não retornou uma resposta válida.", 'danger')
            return None

        # Analisa a resposta
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        cstat_element = resultado.find('nfe:cStat', ns)
        status_code = cstat_element.text if cstat_element is not None else None

        if status_code == '100':  # Autorizado o uso da NF-e
            flash('XML completo da Nota Fiscal obtido com sucesso!', 'success')
            return etree.tostring(resultado, encoding='utf-8', xml_declaration=True)

        motivo_element = resultado.find('nfe:xMotivo', ns)
        motivo = motivo_element.text if motivo_element is not None else 'Motivo não informado'
        flash(f"SEFAZ ({uf_code}): ({status_code}) {motivo}", 'warning')
        return None

    except Exception as e:
        print(f"Erro ao consultar NF-e: {e}")
        flash('Ocorreu um erro ao comunicar com o serviço de consulta da SEFAZ.', 'danger')
        return None

    
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def permission_required(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.tem_permissao(permission):
                abort(403) # Erro de Acesso Proibido
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ===================================================================
# CLASSES DE FORMULÁRIO
# ===================================================================
class NFeConsultaForm(FlaskForm):
    """Formulário para consultar uma NF-e pela chave de acesso."""
    chave_acesso = StringField('Chave de Acesso da NF-e', 
                               validators=[DataRequired(), Length(min=44, max=44, message='A chave de acesso deve ter 44 dígitos.')])
    submit = SubmitField('Consultar Nota Fiscal')

class PerfilForm(FlaskForm):
    """Formulário para criar ou editar um Perfil."""
    nome = StringField('Nome do Perfil', validators=[DataRequired()])
    permissoes = SelectMultipleField('Permissões', coerce=int)
    submit = SubmitField('Salvar Perfil')

class FornecedorForm(FlaskForm):
    """Formulário para criar ou editar um Fornecedor."""
    razao_social = StringField('Razão Social', validators=[DataRequired()])
    nome_fantasia = StringField('Nome Fantasia', validators=[Optional()])
    cnpj = StringField('CNPJ', validators=[Optional()])
    contato_nome = StringField('Nome do Contato', validators=[Optional()])
    contato_email = StringField('Email do Contato', validators=[Optional(), Email()])
    contato_telefone = StringField('Telefone do Contato', validators=[Optional()])
    submit = SubmitField('Salvar')

    def validate_razao_social(self, razao_social):
        # Lógica para edição: ignora o próprio registro na validação de duplicidade
        if hasattr(self, 'original_razao_social') and self.original_razao_social == razao_social.data:
            return
        fornecedor = Fornecedor.query.filter_by(razao_social=razao_social.data).first()
        if fornecedor:
            raise ValidationError('Esta Razão Social já está cadastrada.')

    def validate_cnpj(self, cnpj):
        if cnpj.data: # Valida apenas se o CNPJ foi preenchido
            if hasattr(self, 'original_cnpj') and self.original_cnpj == cnpj.data:
                return
            fornecedor = Fornecedor.query.filter_by(cnpj=cnpj.data).first()
            if fornecedor:
                raise ValidationError('Este CNPJ já está cadastrado.')
            
        
class AuditoriaForm(FlaskForm):
    """Formulário para filtrar o log de auditoria."""
    protocolo_numero = StringField('Número do Protocolo', validators=[Optional()])
    colaborador = SelectField('Filtrar por Colaborador', coerce=int, validators=[Optional()])
    data_inicio = DateField('Data Inicial', format='%Y-%m-%d', validators=[Optional()])
    data_fim = DateField('Data Final', format='%Y-%m-%d', validators=[Optional()])
    submit = SubmitField('Filtrar Log')

class RegistrationForm(FlaskForm):
    nome = StringField('Nome Completo', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    setor = SelectField('Setor', coerce=int, validators=[DataRequired()])
    password = PasswordField('Senha', validators=[DataRequired()])
    confirm_password = PasswordField('Confirmar Senha', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Registrar')
    def validate_email(self, email):
        user = Colaborador.query.filter_by(email=email.data).first()
        if user: raise ValidationError('Este email já está em uso.')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Senha', validators=[DataRequired()])
    submit = SubmitField('Login')

class ProtocoloForm(FlaskForm):
    """Formulário para a criação de um novo protocolo."""
    modelo = SelectField('Usar Modelo de Protocolo (Opcional)', coerce=int, validators=[Optional()])
    assunto = StringField('Assunto', validators=[DataRequired()])
    #fornecedor = SelectField('Fornecedor Associado (Opcional)', coerce=int, validators=[Optional()])
    setor_destinatario = SelectField('Encaminhar para o Setor', coerce=int, validators=[DataRequired()])
    colaborador_destinatario = SelectField('Direcionar para Colaborador (Opcional)', coerce=int, validators=[Optional()])

    # --- ADICIONE ESTE CAMPO ---
    data_vencimento = DateField('Prazo Final (Opcional)', format='%Y-%m-%d', validators=[Optional()])
    is_externo = BooleanField('Protocolo Externo (para impressão e assinatura)')

    # *** MUDANÇA #2 (Validação) ***
    descricao = TextAreaField('Descrição detalhada', validators=[Optional()])
    anexos = MultipleFileField('Anexos (opcional)', validators=[Optional()])
    submit = SubmitField('Criar Protocolo')

class DespachoForm(FlaskForm):
    descricao = TextAreaField('Comentário / Despacho', validators=[DataRequired()])
    novo_status = SelectField('Mudar status para', choices=[('Aberto', 'Aberto'), ('Em Análise', 'Em Análise'), ('Pendente', 'Pendente'), ('Finalizado', 'Finalizado'), ('Arquivado', 'Arquivado')], validators=[DataRequired()])
    submit = SubmitField('Adicionar Despacho')

class SetorForm(FlaskForm):
    nome = StringField('Nome do Setor', validators=[DataRequired()])
    submit = SubmitField('Salvar')

class AdminColaboradorCreateForm(FlaskForm):
    """Formulário para admin criar um novo colaborador."""
    nome = StringField('Nome Completo', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    setor = SelectField('Setor', coerce=int, validators=[DataRequired()])
    # --- MUDANÇA AQUI ---
    perfil = SelectField('Perfil de Acesso', coerce=int, validators=[DataRequired()])
    password = PasswordField('Senha', validators=[DataRequired()])
    confirm_password = PasswordField('Confirmar Senha', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Criar Colaborador')
    # ... (validação de email continua igual) ...

class AdminColaboradorEditForm(FlaskForm):
    """Formulário para admin editar um colaborador."""
    nome = StringField('Nome Completo', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    setor = SelectField('Setor', coerce=int, validators=[DataRequired()])
    # --- MUDANÇA AQUI ---
    perfil = SelectField('Perfil de Acesso', coerce=int, validators=[DataRequired()])
    password = PasswordField('Nova Senha (deixe em branco para não alterar)', validators=[Optional()])
    confirm_password = PasswordField('Confirmar Nova Senha', validators=[EqualTo('password', message='As senhas devem ser iguais.')])
    submit = SubmitField('Salvar Alterações')

    def __init__(self, original_email, *args, **kwargs):
        super(AdminColaboradorEditForm, self).__init__(*args, **kwargs)
        self.original_email = original_email
    def validate_email(self, email):
        if email.data != self.original_email:
            user = Colaborador.query.filter_by(email=email.data).first()
            if user: raise ValidationError('Este email já está em uso por outro colaborador.')

class BuscaProtocoloForm(FlaskForm):
    """Formulário para buscar e filtrar protocolos."""
    termo_busca = StringField('Buscar por Assunto/Descrição/Número', validators=[Optional()])
    
    # --- LINHA ADICIONADA ---
    modelo = SelectField('Filtrar por Modelo', coerce=int, validators=[Optional()])
    # --- FIM DA LINHA ADICIONADA ---

    status = SelectField('Filtrar por Status', choices=[
        ('', 'Todos os Status'), # Valor vazio para representar "todos"
        ('Aberto', 'Aberto'),
        ('Em Análise', 'Em Análise'),
        ('Pendente', 'Pendente'),
        ('Finalizado', 'Finalizado'),
        ('Arquivado', 'Arquivado')
    ], validators=[Optional()])
    data_inicio = DateField('Data Inicial', format='%Y-%m-%d', validators=[Optional()])
    data_fim = DateField('Data Final', format='%Y-%m-%d', validators=[Optional()])
    submit = SubmitField('Pesquisar')

class ProtocoloModeloForm(FlaskForm):
    """Formulário para criar ou editar um Modelo de Protocolo."""
    nome = StringField('Nome do Modelo', validators=[DataRequired()])
    descricao = TextAreaField('Descrição', validators=[Optional()])
    habilita_conferencia = BooleanField('Habilitar Conferência de Linhas')
    submit = SubmitField('Salvar Modelo')

class CampoModeloForm(FlaskForm):
    """Formulário para adicionar um campo a um Modelo de Protocolo."""
    nome_campo = StringField('Nome do Campo', validators=[DataRequired()])
    tipo_campo = SelectField('Tipo do Campo', choices=[
        ('texto', 'Texto Curto'),
        ('area_de_texto', 'Texto Longo'),
        ('numero', 'Número'),
        ('data', 'Data')
    ], validators=[DataRequired()])
    obrigatorio = BooleanField('Obrigatório')
    submit = SubmitField('Adicionar Campo')

class ChangePasswordForm(FlaskForm):
    """Formulário para o usuário alterar a própria senha."""
    senha_atual = PasswordField('Senha Atual', validators=[DataRequired()])
    nova_senha = PasswordField('Nova Senha', validators=[DataRequired()])
    confirmar_senha = PasswordField('Confirmar Nova Senha', 
                                    validators=[DataRequired(), EqualTo('nova_senha', message='As senhas devem ser iguais.')])
    submit = SubmitField('Alterar Senha')


class DeleteForm(FlaskForm):
    """Um formulário genérico para botões de exclusão que só precisa de proteção CSRF."""
    pass

# ===================================================================
# ROTAS DA APLICAÇÃO
# ===================================================================

main_bp = Blueprint('main', __name__)

# --- ROTAS PRINCIPAIS E DE AUTENTICAÇÃO ---

@main_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.login'))

@main_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('main.index'))
    form = RegistrationForm()
    form.setor.choices = [(s.id, s.nome) for s in Setor.query.order_by('nome').all()]
    if form.validate_on_submit():
        colaborador = Colaborador(nome=form.nome.data, email=form.email.data, setor_id=form.setor.data)
        colaborador.senha = form.password.data
        db.session.add(colaborador)
        db.session.commit()
        flash('Sua conta foi criada! Agora você pode fazer o login.', 'success')
        return redirect(url_for('main.login'))
    return render_template('register.html', form=form)


@main_bp.route('/meus-relatorios')
@login_required
def meus_relatorios():
    # Status que consideramos como "em aberto" ou "pendente"
    status_pendentes = ['Aberto', 'Em Análise', 'Pendente']

    # Query 1: Protocolos que o usuário criou e que estão pendentes
    protocolos_enviados = Protocolo.query.options(joinedload(Protocolo.modelo_usado)).filter(
        Protocolo.criado_por_id == current_user.id,
        Protocolo.status.in_(status_pendentes)
    ).order_by(Protocolo.data_criacao.desc()).all()

    # Query 2: Protocolos destinados ao usuário/setor dele e que estão pendentes
    protocolos_recebidos = Protocolo.query.options(joinedload(Protocolo.modelo_usado)).filter(
        or_(
            Protocolo.setor_destinatario_id == current_user.setor_id,
            Protocolo.colaborador_destinatario_id == current_user.id
        ),
        Protocolo.status.in_(status_pendentes)
    ).order_by(Protocolo.data_criacao.desc()).all()

    return render_template('meus_relatorios.html', 
                           enviados=protocolos_enviados, 
                           recebidos=protocolos_recebidos,
                           title="Meus Relatórios")

# --- ROTAS DE PROTOCOLO ---

@main_bp.route('/protocolo/novo', methods=['GET', 'POST'])
@login_required
def criar_protocolo():
    form = ProtocoloForm()
    
    # Popula os dropdowns estáticos
    form.setor_destinatario.choices = [(s.id, s.nome) for s in Setor.query.order_by('nome').all()]
    form.modelo.choices = [(m.id, m.nome) for m in ProtocoloModelo.query.order_by('nome').all()]
    form.modelo.choices.insert(0, (0, '--- Nenhum ---'))
    #form.fornecedor.choices = [(f.id, f.razao_social) for f in Fornecedor.query.order_by('razao_social').all()]
    #form.fornecedor.choices.insert(0, (0, '--- Nenhum ---'))

    if request.method == 'POST':
        setor_id = request.form.get('setor_destinatario')
        if setor_id:
            colaboradores = Colaborador.query.filter_by(setor_id=setor_id).order_by(Colaborador.nome).all()
            form.colaborador_destinatario.choices = [(c.id, c.nome) for c in colaboradores]
            form.colaborador_destinatario.choices.insert(0, (0, '--- Nenhum ---'))
    else:
        form.colaborador_destinatario.choices = [(0, '--- Selecione um Setor Primeiro ---')]

    if form.validate_on_submit():
        lista_dados_customizados = []
        if form.modelo.data and form.modelo.data != 0:
            modelo_selecionado = ProtocoloModelo.query.get(form.modelo.data)
            if modelo_selecionado and modelo_selecionado.campos:
                i = 0
                primeiro_campo = modelo_selecionado.campos[0].nome_campo 
                while request.form.get(f'{primeiro_campo}-{i}') is not None:
                    registro_linha = {}
                    for campo in modelo_selecionado.campos:
                        valor = request.form.get(f'{campo.nome_campo}-{i}')
                        registro_linha[campo.nome_campo] = valor
                    lista_dados_customizados.append(registro_linha)
                    i += 1
        
        # *** MUDANÇA #1 (LÓGICA) ***
        # SUBSTITUI O BLOCO DE CÓDIGO ANTIGO
        ano_atual = date.today().year
        setor_destino = Setor.query.get(form.setor_destinatario.data)

        # Encontra o 'numero_protocolo' mais alto deste ano
        ultimo_protocolo_str = db.session.query(func.max(Protocolo.numero_protocolo)).filter(
            Protocolo.numero_protocolo.like(f'{ano_atual}%')
        ).scalar()

        sequencial = 1 # Define o padrão como 1 (para o primeiro protocolo do ano)
        if ultimo_protocolo_str:
            # Se um protocolo foi encontrado (ex: "2025-000003"), extrai o sequencial
            try:
                ultimo_sequencial_int = int(ultimo_protocolo_str.split('-')[1])
                sequencial = ultimo_sequencial_int + 1
            except (IndexError, ValueError, AttributeError):
                # Se falhar (ex: formato inesperado), volta para 1 como segurança
                sequencial = 1
                
        numero_protocolo_gerado = f"{ano_atual:04d}-{sequencial:06d}"
        # *** FIM DA MUDANÇA #1 ***

        novo_protocolo = Protocolo(
            numero_protocolo=numero_protocolo_gerado,
            assunto=form.assunto.data,
            # *** MUDANÇA #3 (Suporte à Validação) ***
            descricao=form.descricao.data or '',
            data_vencimento=form.data_vencimento.data,
            is_externo=form.is_externo.data,
            
            # vvv LINHAS CORRIGIDAS vvv
            # Lê os dados dos campos hidden que vêm do formulário HTML
            fornecedor_ext_cod=request.form.get('fornecedor_ext_cod') if request.form.get('fornecedor_ext_cod') else None,
            fornecedor_ext_nome=request.form.get('fornecedor_ext_nome') if request.form.get('fornecedor_ext_nome') else None,
            # ^^^ LINHAS CORRIGIDAS ^^^

            criado_por_id=current_user.id,
            setor_destinatario_id=form.setor_destinatario.data,
            colaborador_destinatario_id=form.colaborador_destinatario.data if form.colaborador_destinatario.data and form.colaborador_destinatario.data != 0 else None,
            modelo_usado_id=form.modelo.data if form.modelo.data and form.modelo.data != 0 else None,
            # --- GARANTIA DA CORREÇÃO ---
            dados_preenchidos=lista_dados_customizados if lista_dados_customizados else []
        )
        
        db.session.add(novo_protocolo)
        files = request.files.getlist(form.anexos.name)
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                db.session.flush()
                novo_nome_arquivo = f"{novo_protocolo.id}_{filename}"
                caminho_salvo = os.path.join(current_app.config['UPLOAD_FOLDER'], novo_nome_arquivo)
                file.save(caminho_salvo)
                novo_anexo = Anexo(nome_arquivo=filename, caminho_arquivo=novo_nome_arquivo, protocolo=novo_protocolo)
                db.session.add(novo_anexo)
        
        primeiro_historico = Historico(descricao=f"Protocolo criado e encaminhado para o setor {setor_destino.nome}.", protocolo=novo_protocolo, colaborador_id=current_user.id)
        db.session.add(primeiro_historico)
        
        db.session.commit()
        flash('Protocolo criado com sucesso!', 'success')

        if novo_protocolo.colaborador_destinatario:
            destinatario = novo_protocolo.colaborador_destinatario
            if destinatario.email and destinatario.id != current_user.id:
                send_email(
                    subject=f"Novo Protocolo Recebido: {novo_protocolo.numero_protocolo}",
                    recipients=[destinatario.email],
                    template='email/novo_protocolo',
                    destinatario=destinatario,
                    protocolo=novo_protocolo,
                    remetente=current_user
                )

        return redirect(url_for('main.protocolo_detalhe', protocolo_id=novo_protocolo.id))
        
    elif request.method == 'POST':
        print("--- ERROS DE VALIDAÇÃO DO FORMULÁRIO ---")
        print(form.errors)
        print("---------------------------------------")
        
    return render_template('criar_protocolo.html', form=form, title="Novo Protocolo")

@main_bp.route('/protocolo/<int:protocolo_id>')
@login_required
def protocolo_detalhe(protocolo_id):
    protocolo = Protocolo.query.get_or_404(protocolo_id)
    
    # Lógica de permissão de visualização atualizada
    if not current_user.tem_permissao('acessar_painel_admin') and \
   protocolo.criado_por_id != current_user.id and \
   protocolo.setor_destinatario_id != current_user.setor_id and \
   protocolo.colaborador_destinatario_id != current_user.id:
        abort(403)
            
    form = DespachoForm()
    form.novo_status.data = protocolo.status
    return render_template('protocolo_detalhe.html', protocolo=protocolo, form=form)



@main_bp.route('/protocolo/<int:protocolo_id>/tramitar', methods=['POST'])
@login_required
def tramitar_protocolo(protocolo_id):
    protocolo = Protocolo.query.get_or_404(protocolo_id)
    
    # Lógica de permissão de ação atualizada
    if not current_user.tem_permissao('acessar_painel_admin') and \
   protocolo.criado_por_id != current_user.id and \
   protocolo.setor_destinatario_id != current_user.setor_id and \
   protocolo.colaborador_destinatario_id != current_user.id:
        abort(403)

    form = DespachoForm()
    if form.validate_on_submit():
        protocolo.status = form.novo_status.data
        novo_historico = Historico(
            descricao=form.descricao.data,
            protocolo_id=protocolo.id,
            colaborador_id=current_user.id
        )
        db.session.add(novo_historico)
        db.session.commit()
        flash('Protocolo atualizado com sucesso.', 'success')

        if protocolo.criado_por.email and protocolo.criado_por_id != current_user.id:
            send_email(
                subject=f"Atualização no Protocolo {protocolo.numero_protocolo}",
                recipients=[protocolo.criado_por.email],
                template='email/status_update',
                criador=protocolo.criado_por,
                protocolo=protocolo,
                novo_status=protocolo.status,
                despacho=form.descricao.data,
                autor_despacho=current_user.nome
            )
    else:
        flash('Ocorreu um erro na validação. O campo de despacho não pode estar em branco.', 'danger')

    return redirect(url_for('main.protocolo_detalhe', protocolo_id=protocolo.id))

@main_bp.route('/uploads/<path:filename>')
@login_required
def download_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

# --- ROTAS DE ADMINISTRAÇÃO ---

@main_bp.route('/admin/perfis')
@login_required
@permission_required('gerenciar_perfis') # Por enquanto, usaremos o decorator antigo
def listar_perfis():
    perfis = Perfil.query.order_by(Perfil.nome).all()
    return render_template('admin/perfis.html', perfis=perfis, title="Gerenciar Perfis")

@main_bp.route('/admin/perfil/novo', methods=['GET', 'POST'])
@login_required
@permission_required('gerenciar_perfis')
def adicionar_perfil():
    form = PerfilForm()
    form.permissoes.choices = [(p.id, p.nome) for p in Permissao.query.order_by('nome').all()]

    # --- INÍCIO DA CORREÇÃO ---
    # Garante que, na primeira vez que a página é carregada (GET), 
    # a lista de dados das permissões seja uma lista vazia, e não None.
    if request.method == 'GET':
        form.permissoes.data = []
    # --- FIM DA CORREÇÃO ---

    if form.validate_on_submit():
        novo_perfil = Perfil(nome=form.nome.data)
        permissoes_selecionadas = Permissao.query.filter(Permissao.id.in_(form.permissoes.data)).all()
        novo_perfil.permissoes = permissoes_selecionadas
        db.session.add(novo_perfil)
        db.session.commit()
        flash('Perfil criado com sucesso!', 'success')
        return redirect(url_for('main.listar_perfis'))
    elif request.method == 'POST':
        flash('Não foi possível criar o perfil. Por favor, verifique os dados inseridos.', 'danger')
        form.permissoes.data = [int(p) for p in request.form.getlist('permissoes')]

    return render_template('admin/perfil_form.html', form=form, title="Adicionar Perfil")

@main_bp.route('/admin/perfil/<int:perfil_id>/editar', methods=['GET', 'POST'])
@login_required
@permission_required('gerenciar_perfis')
def editar_perfil(perfil_id):
    perfil = Perfil.query.get_or_404(perfil_id)
    form = PerfilForm(obj=perfil) # 'obj=perfil' pré-popula o nome
    form.permissoes.choices = [(p.id, p.nome) for p in Permissao.query.order_by('nome').all()]
    if form.validate_on_submit():
        perfil.nome = form.nome.data
        permissoes_selecionadas = Permissao.query.filter(Permissao.id.in_(form.permissoes.data)).all()
        perfil.permissoes = permissoes_selecionadas
        db.session.commit()
        flash('Perfil atualizado com sucesso!', 'success')
        return redirect(url_for('main.listar_perfis'))
    elif request.method == 'GET':
        # Pré-seleciona as permissões atuais do perfil
        form.permissoes.data = [p.id for p in perfil.permissoes]
    return render_template('admin/perfil_form.html', form=form, title="Editar Perfil")


@main_bp.route('/admin/fornecedores')
@login_required
@permission_required('gerenciar_fornecedores') # Ajuste a permissão se necessário
def listar_fornecedores():
    fornecedores_externos = []
    try:
        conn = pyodbc.connect(Config.EXT_DB_CONN_STR, timeout=5)
        cursor = conn.cursor()
        # Seleciona as colunas desejadas da tabela SA2010
        # Adicionei um filtro D_E_L_E_T_E_ <> '*' que é comum em Protheus para registros não deletados
        # Se não for o caso, pode remover essa parte do WHERE
        sql = """
            SELECT
                A2_COD, A2_LOJA, A2_NOME, A2_END, A2_BAIRRO,
                A2_MUN, A2_EST, A2_CEP, A2_CGC
            FROM
                SA2010
            WHERE
                D_E_L_E_T_ <> '*'
            ORDER BY
                A2_NOME
        """
        cursor.execute(sql)
        # Transforma as linhas em dicionários para facilitar o uso no template
        fornecedores_externos = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        conn.close()
    except Exception as e:
        flash(f"Erro ao conectar ou buscar fornecedores no banco externo: {e}", "danger")
        print(f"Erro DB Externo: {e}") # Para debug no console

    # Não precisamos mais do form_excluir aqui
    return render_template('admin/fornecedores.html',
                           fornecedores=fornecedores_externos,
                           title="Consultar Fornecedores Externos") # Título atualizado

@main_bp.route('/admin/fornecedor/novo', methods=['GET', 'POST'])
@login_required
@permission_required('acessar_painel_admin')
def adicionar_fornecedor():
    form = FornecedorForm()
    if form.validate_on_submit():
        novo_fornecedor = Fornecedor(
            razao_social=form.razao_social.data,
            nome_fantasia=form.nome_fantasia.data,
            cnpj=form.cnpj.data,
            contato_nome=form.contato_nome.data,
            contato_email=form.contato_email.data,
            contato_telefone=form.contato_telefone.data
        )
        db.session.add(novo_fornecedor)
        db.session.commit()
        flash('Fornecedor cadastrado com sucesso!', 'success')
        return redirect(url_for('main.listar_fornecedores'))
    return render_template('admin/fornecedor_form.html', form=form, title="Adicionar Fornecedor")



@main_bp.route('/admin/fornecedor/<int:fornecedor_id>/excluir', methods=['POST'])
@login_required
@permission_required('acessar_painel_admin')
def excluir_fornecedor(fornecedor_id):
    fornecedor = Fornecedor.query.get_or_404(fornecedor_id)
    if fornecedor.protocolos:
        flash('Este fornecedor não pode ser excluído, pois está associado a um ou mais protocolos.', 'danger')
    else:
        db.session.delete(fornecedor)
        db.session.commit()
        flash('Fornecedor excluído com sucesso!', 'success')
    return redirect(url_for('main.listar_fornecedores'))


@main_bp.route('/admin/modelo/<int:modelo_id>/editar', methods=['GET', 'POST'])
@login_required
@permission_required('acessar_painel_admin')
def editar_modelo(modelo_id):
    modelo = ProtocoloModelo.query.get_or_404(modelo_id)
    form = ProtocoloModeloForm()
    if form.validate_on_submit():
        modelo.nome = form.nome.data
        modelo.descricao = form.descricao.data
        modelo.habilita_conferencia = form.habilita_conferencia.data
        db.session.commit()
        flash('Modelo atualizado com sucesso!', 'success')
        return redirect(url_for('main.listar_modelos'))
    elif request.method == 'GET':
        form.nome.data = modelo.nome
        form.descricao.data = modelo.descricao
        form.habilita_conferencia.data = modelo.habilita_conferencia
    return render_template('admin/modelo_form.html', form=form, title="Editar Modelo de Protocolo")

@main_bp.route('/admin/modelo/<int:modelo_id>/excluir', methods=['POST'])
#@csrf.exempt
@login_required
@permission_required('acessar_painel_admin')
def excluir_modelo(modelo_id):
    modelo = ProtocoloModelo.query.get_or_404(modelo_id)
    # VERIFICAÇÃO DE SEGURANÇA: Não exclui se o modelo já foi usado em algum protocolo.
    if modelo.protocolos_usados:
        flash('Este modelo não pode ser excluído pois já está em uso por protocolos existentes.', 'danger')
    else:
        db.session.delete(modelo)
        db.session.commit()
        flash('Modelo de protocolo excluído com sucesso!', 'success')
    return redirect(url_for('main.listar_modelos'))

@main_bp.route('/admin')
@login_required
@permission_required('acessar_painel_admin')
def admin_dashboard():
    return render_template('admin/dashboard.html', title="Painel do Admin")

@main_bp.route('/admin/setores')
@login_required
@permission_required('acessar_painel_admin')
def listar_setores():
    setores = Setor.query.order_by(Setor.nome).all()
    form_excluir = DeleteForm()
    return render_template('admin/setores.html', 
                           setores=setores, 
                           form_excluir=form_excluir)

@main_bp.route('/admin/setor/novo', methods=['GET', 'POST'])
@login_required
@permission_required('acessar_painel_admin')
def adicionar_setor():
    form = SetorForm()
    if form.validate_on_submit():
        novo_setor = Setor(nome=form.nome.data)
        db.session.add(novo_setor)
        db.session.commit()
        flash('Setor criado com sucesso!', 'success')
        return redirect(url_for('main.listar_setores'))
    return render_template('admin/setor_form.html', form=form, title="Adicionar Setor")

@main_bp.route('/admin/setor/<int:setor_id>/editar', methods=['GET', 'POST'])
@login_required
@permission_required('acessar_painel_admin')
def editar_setor(setor_id):
    setor = Setor.query.get_or_404(setor_id)
    form = SetorForm()
    if form.validate_on_submit():
        setor.nome = form.nome.data
        db.session.commit()
        flash('Setor atualizado com sucesso!', 'success')
        return redirect(url_for('main.listar_setores'))
    elif request.method == 'GET':
        form.nome.data = setor.nome
    return render_template('admin/setor_form.html', form=form, title="Editar Setor")

@main_bp.route('/admin/setor/<int:setor_id>/excluir', methods=['POST'])
@login_required
@permission_required('acessar_painel_admin')
def excluir_setor(setor_id):
    setor = Setor.query.get_or_404(setor_id)
    if setor.colaboradores or setor.protocolos_destinados:
        flash('Este setor não pode ser excluído pois está associado a colaboradores ou protocolos.', 'danger')
    else:
        db.session.delete(setor)
        db.session.commit()
        flash('Setor excluído com sucesso!', 'success')
    return redirect(url_for('main.listar_setores'))

@main_bp.route('/admin/colaboradores')
@login_required
@permission_required('acessar_painel_admin')
def listar_colaboradores():
    colaboradores = Colaborador.query.order_by(Colaborador.nome).all()
    form_excluir = DeleteForm()
    return render_template('admin/colaboradores.html', 
                           colaboradores=colaboradores, 
                           form_excluir=form_excluir)

@main_bp.route('/admin/colaborador/novo', methods=['GET', 'POST'])
@login_required
@permission_required('acessar_painel_admin') # Manteremos o decorator antigo por enquanto
def adicionar_colaborador():
    form = AdminColaboradorCreateForm()
    form.setor.choices = [(s.id, s.nome) for s in Setor.query.order_by('nome').all()]
    # --- MUDANÇA AQUI ---
    form.perfil.choices = [(p.id, p.nome) for p in Perfil.query.order_by('nome').all()]
    if form.validate_on_submit():
        novo_colaborador = Colaborador(
            nome=form.nome.data,
            email=form.email.data,
            setor_id=form.setor.data,
            # --- MUDANÇA AQUI ---
            perfil_id=form.perfil.data
        )
        novo_colaborador.senha = form.password.data
        db.session.add(novo_colaborador)
        db.session.commit()
        flash('Colaborador criado com sucesso!', 'success')
        return redirect(url_for('main.listar_colaboradores'))
    return render_template('admin/colaborador_form.html', form=form, title="Adicionar Colaborador")

@main_bp.route('/admin/colaborador/<int:colab_id>/editar', methods=['GET', 'POST'])
@login_required
@permission_required('acessar_painel_admin')
def editar_colaborador(colab_id):
    colaborador = Colaborador.query.get_or_404(colab_id)
    form = AdminColaboradorEditForm(original_email=colaborador.email)
    form.setor.choices = [(s.id, s.nome) for s in Setor.query.order_by('nome').all()]
    # --- MUDANÇA AQUI ---
    form.perfil.choices = [(p.id, p.nome) for p in Perfil.query.order_by('nome').all()]
    if form.validate_on_submit():
        colaborador.nome = form.nome.data
        colaborador.email = form.email.data
        colaborador.setor_id = form.setor.data
        # --- MUDANÇA AQUI ---
        colaborador.perfil_id = form.perfil.data
        if form.password.data:
            colaborador.senha = form.password.data
        db.session.commit()
        flash('Colaborador atualizado com sucesso!', 'success')
        return redirect(url_for('main.listar_colaboradores'))
    elif request.method == 'GET':
        form.nome.data = colaborador.nome
        form.email.data = colaborador.email
        form.setor.data = colaborador.setor_id
        # --- MUDANÇA AQUI ---
        form.perfil.data = colaborador.perfil_id
    return render_template('admin/colaborador_form.html', form=form, title="Editar Colaborador")

@main_bp.route('/admin/colaborador/<int:colab_id>/excluir', methods=['POST'])
@login_required
@permission_required('acessar_painel_admin')
def excluir_colaborador(colab_id):
    colaborador = Colaborador.query.get_or_404(colab_id)
    if colaborador.id == current_user.id:
        flash('Você não pode excluir a si mesmo.', 'danger')
        return redirect(url_for('main.listar_colaboradores'))
    if colaborador.protocolos_criados or colaborador.historicos_criados:
        flash('Este colaborador não pode ser excluído pois possui protocolos ou históricos associados.', 'danger')
    else:
        db.session.delete(colaborador)
        db.session.commit()
        flash('Colaborador excluído com sucesso!', 'success')
    return redirect(url_for('main.listar_colaboradores'))



@main_bp.route('/admin/fornecedor/<int:fornecedor_id>/editar', methods=['GET', 'POST'])
@login_required
@permission_required('acessar_painel_admin')
def editar_fornecedor(fornecedor_id):
    fornecedor = Fornecedor.query.get_or_404(fornecedor_id)
    form = FornecedorForm()
    # Passa os valores originais para o formulário para a lógica de validação
    form.original_razao_social = fornecedor.razao_social
    form.original_cnpj = fornecedor.cnpj

    if form.validate_on_submit():
        fornecedor.razao_social = form.razao_social.data
        fornecedor.nome_fantasia = form.nome_fantasia.data
        fornecedor.cnpj = form.cnpj.data
        fornecedor.contato_nome = form.contato_nome.data
        fornecedor.contato_email = form.contato_email.data
        fornecedor.contato_telefone = form.contato_telefone.data
        db.session.commit()
        flash('Fornecedor atualizado com sucesso!', 'success')
        return redirect(url_for('main.listar_fornecedores'))
    elif request.method == 'GET':
        form.razao_social.data = fornecedor.razao_social
        form.nome_fantasia.data = fornecedor.nome_fantasia
        form.cnpj.data = fornecedor.cnpj
        form.contato_nome.data = fornecedor.contato_nome
        form.contato_email.data = fornecedor.contato_email
        form.contato_telefone.data = fornecedor.contato_telefone
    return render_template('admin/fornecedor_form.html', form=form, title="Editar Fornecedor")


@main_bp.route('/admin/modelos')
@login_required
@permission_required('acessar_painel_admin')
def listar_modelos():
    modelos = ProtocoloModelo.query.order_by(ProtocoloModelo.nome).all()
    form_excluir = DeleteForm()
    return render_template('admin/modelos.html', modelos=modelos, form_excluir=form_excluir)

@main_bp.route('/admin/modelo/novo', methods=['GET', 'POST'])
@login_required
@permission_required('acessar_painel_admin')
def adicionar_modelo():
    form = ProtocoloModeloForm()
    if form.validate_on_submit():
        novo_modelo = ProtocoloModelo(
            nome=form.nome.data,
            descricao=form.descricao.data,
            habilita_conferencia=form.habilita_conferencia.data,
            setor_proprietario_id=current_user.setor_id # O setor do admin que está criando
        )
        db.session.add(novo_modelo)
        db.session.commit()
        flash('Modelo de protocolo criado com sucesso!', 'success')
        return redirect(url_for('main.design_modelo', modelo_id=novo_modelo.id))
    return render_template('admin/modelo_form.html', form=form, title="Novo Modelo de Protocolo")

@main_bp.route('/admin/modelo/<int:modelo_id>/design', methods=['GET', 'POST'])
@login_required
@permission_required('acessar_painel_admin')
def design_modelo(modelo_id):
    modelo = ProtocoloModelo.query.get_or_404(modelo_id)
    form = CampoModeloForm()
    
    # --- INÍCIO DA CORREÇÃO ---
    # Cria a instância do formulário de exclusão para os botões na lista de campos.
    form_excluir = DeleteForm()
    # --- FIM DA CORREÇÃO ---

    if form.validate_on_submit():
        ordem_atual = len(modelo.campos)
        novo_campo = CampoModelo(
            nome_campo=form.nome_campo.data,
            tipo_campo=form.tipo_campo.data,
            obrigatorio=form.obrigatorio.data,
            modelo_id=modelo.id,
            ordem=ordem_atual # <-- ADICIONE ESTA LINHA
        )
        db.session.add(novo_campo)
        db.session.commit()
        flash(f'Campo "{form.nome_campo.data}" adicionado ao modelo.', 'success')
        return redirect(url_for('main.design_modelo', modelo_id=modelo.id))
        
    # Adiciona form_excluir ao render_template
    return render_template('admin/modelo_design.html', 
                           modelo=modelo, 
                           form=form, 
                           form_excluir=form_excluir, # <-- Passe a variável aqui
                           title="Design do Modelo")

@main_bp.route('/admin/modelo/<int:modelo_id>/campo/<int:campo_id>/editar', methods=['GET', 'POST'])
@login_required
@permission_required('acessar_painel_admin')
def editar_campo_modelo(modelo_id, campo_id):
    campo = CampoModelo.query.get_or_404(campo_id)
    # Garante que o campo pertence ao modelo correto para segurança
    if campo.modelo_id != modelo_id:
        abort(404)

    form = CampoModeloForm()
    if form.validate_on_submit():
        campo.nome_campo = form.nome_campo.data
        campo.tipo_campo = form.tipo_campo.data
        campo.obrigatorio = form.obrigatorio.data
        db.session.commit()
        flash('Campo atualizado com sucesso!', 'success')
        return redirect(url_for('main.design_modelo', modelo_id=modelo_id))
    elif request.method == 'GET':
        form.nome_campo.data = campo.nome_campo
        form.tipo_campo.data = campo.tipo_campo
        form.obrigatorio.data = campo.obrigatorio

    return render_template('admin/campo_form.html', form=form, title="Editar Campo")

@main_bp.route('/admin/modelo/campo/<int:campo_id>/excluir', methods=['POST'])
@login_required
@permission_required('acessar_painel_admin')
def excluir_campo_modelo(campo_id):
    campo = CampoModelo.query.get_or_404(campo_id)
    modelo_id = campo.modelo_id
    db.session.delete(campo)
    db.session.commit()
    flash('Campo excluído com sucesso!', 'success')
    return redirect(url_for('main.design_modelo', modelo_id=modelo_id))

@main_bp.route('/admin/relatorios')
@login_required
@permission_required('acessar_painel_admin')
def relatorios():
    return render_template('admin/relatorios.html', title="Relatórios e Gráficos")

@main_bp.route('/api/modelo/<int:modelo_id>/campos')
@login_required
def get_campos_modelo(modelo_id):
    modelo = ProtocoloModelo.query.get_or_404(modelo_id)
    campos_schema = []
    for campo in modelo.campos:
        campos_schema.append({
            'nome_campo': campo.nome_campo,
            'tipo_campo': campo.tipo_campo,
            'obrigatorio': campo.obrigatorio
        })
    return jsonify(campos_schema)


@main_bp.route('/')
@main_bp.route('/index')
@login_required
def index():
    # Pega o parâmetro 'view' da URL, o padrão é 'list'
    view_mode = request.args.get('view', 'list')

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    if per_page not in [10, 25, 50]: per_page = 25

    form = BuscaProtocoloForm(request.args)
    
    # --- POPULAR OS DROPDOWNS DO FORMULÁRIO DE FILTRO ---
    form.modelo.choices = [(m.id, m.nome) for m in ProtocoloModelo.query.order_by('nome').all()]
    form.modelo.choices.insert(0, (0, 'Todos os Modelos'))
    # --- FIM DO BLOCO ---
    
    # A lógica de consulta base com permissões continua a mesma
    if current_user.tem_permissao('acessar_painel_admin'):
        query = Protocolo.query.options(joinedload(Protocolo.modelo_usado))
    else:
        query = Protocolo.query.filter(or_(
            Protocolo.criado_por_id == current_user.id,
            Protocolo.setor_destinatario_id == current_user.setor_id,
            Protocolo.colaborador_destinatario_id == current_user.id
        )).options(joinedload(Protocolo.modelo_usado))
    
    # --- LÓGICA DE FILTRO ATUALIZADA ---
    if form.termo_busca.data:
        termo = f"%{form.termo_busca.data}%"
        query = query.filter(or_(Protocolo.assunto.ilike(termo), Protocolo.descricao.ilike(termo), Protocolo.numero_protocolo.ilike(termo)))
    
    if form.modelo.data and form.modelo.data != 0:
        query = query.filter(Protocolo.modelo_usado_id == form.modelo.data)

    if form.status.data:
        query = query.filter(Protocolo.status == form.status.data)
    if form.data_inicio.data:
        query = query.filter(Protocolo.data_criacao >= form.data_inicio.data)
    if form.data_fim.data:
        from datetime import datetime, time
        data_fim_completa = datetime.combine(form.data_fim.data, time.max)
        query = query.filter(Protocolo.data_criacao <= data_fim_completa)
    # --- FIM DA LÓGICA DE FILTRO ---

    # --- LÓGICA DE VISUALIZAÇÃO CORRIGIDA ---
    protocolos_agrupados = None
    pagination = None

    if view_mode == 'kanban':
        # Para o Kanban, pegamos todos os resultados filtrados, sem paginação
        protocolos_filtrados = query.order_by(Protocolo.data_criacao.desc()).all()
        # Agora, agrupamos em um dicionário
        protocolos_agrupados = {
            'Aberto': [], 'Em Análise': [], 'Pendente': [], 'Finalizado': [], 'Arquivado': []
        }
        for p in protocolos_filtrados:
            if p.status in protocolos_agrupados:
                protocolos_agrupados[p.status].append(p)
    else: # O modo padrão é 'list'
        pagination = query.order_by(Protocolo.data_criacao.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
    # --- FIM DA LÓGICA DE VISUALIZAÇÃO ---

    return render_template('dashboard.html', 
                           protocolos=pagination.items if pagination else [], 
                           form=form, 
                           pagination=pagination,
                           view_mode=view_mode,
                           protocolos_agrupados=protocolos_agrupados)


@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = Colaborador.query.filter_by(email=form.email.data).first()
        if user and user.verificar_senha(form.password.data):
            login_user(user)
            flash('Login bem-sucedido!', 'success')
            return redirect(url_for('main.index'))
        else:
            flash('Login falhou. Verifique seu email e senha.', 'danger')
    return render_template('login.html', form=form)

@main_bp.route('/api/setor/<int:setor_id>/colaboradores')
@login_required
def get_colaboradores_por_setor(setor_id):
    colaboradores = Colaborador.query.filter_by(setor_id=setor_id).order_by(Colaborador.nome).all()
    colaboradores_schema = [{'id': c.id, 'nome': c.nome} for c in colaboradores]
    return jsonify(colaboradores_schema)

@main_bp.route('/api/buscar_fornecedores')
@login_required
def api_buscar_fornecedores():
    term = request.args.get('term', '').strip()
    results = []
    if len(term) < 2: # Evita buscar com menos de 2 caracteres
        return jsonify(results)

    try:
        # CORREÇÃO IMPORTANTE: Usar current_app.config, que é acessível nas rotas
        conn_str = current_app.config['EXT_DB_CONN_STR']
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        search_term = f"%{term}%"

        # Busca por código OU nome, excluindo deletados e ordenando por nome
        # Lembre-se que ajustamos o nome da coluna D_E_L_E_T_
        sql = """
            SELECT TOP 20 -- Limita a 20 resultados para performance
                A2_COD, A2_NOME, A2_LOJA
            FROM
                SA2010
            WHERE
                (A2_COD LIKE ? OR A2_NOME LIKE ?)
                AND D_E_L_E_T_ <> '*'
            ORDER BY
                A2_NOME
        """
        cursor.execute(sql, (search_term, search_term))

        for row in cursor.fetchall():
            # Formato esperado por muitas bibliotecas autocomplete simples
            results.append({
                "id": row.A2_COD.strip(), # Código do Fornecedor
                "text": f"{row.A2_COD.strip()} - {row.A2_NOME.strip()} (Loja: {row.A2_LOJA.strip()})", # Texto exibido
                "nome": row.A2_NOME.strip() # Nome separado para salvar no BD
            })
        conn.close()
    except Exception as e:
        print(f"Erro ao buscar fornecedores externos: {e}")
        # Retorna lista vazia em caso de erro, mas loga no console

    return jsonify(results)

@main_bp.route('/protocolo/<int:protocolo_id>/pdf')
@login_required
def gerar_protocolo_pdf(protocolo_id):
    protocolo = Protocolo.query.get_or_404(protocolo_id)
    
    # A sua lógica de permissão continua aqui...
    if not current_user.tem_permissao('acessar_painel_admin') and \
       protocolo.criado_por_id != current_user.id and \
       protocolo.setor_destinatario_id != current_user.setor_id and \
       protocolo.colaborador_destinatario_id != current_user.id:
        abort(403)

    html_renderizado = render_template('pdf/protocolo_pdf.html', protocolo=protocolo)
    
    # --- CÓDIGO CORRIGIDO PARA FORÇAR MODO PAISAGEM ---
    # Define a orientação da página e as margens
    css_string = '@page { size: A4 landscape; margin: 1.5cm; }'
    pdf_css = CSS(string=css_string)
    
    # Passa a folha de estilos para o renderizador
    pdf = HTML(string=html_renderizado, base_url=request.url_root).write_pdf(stylesheets=[pdf_css])
    # --- FIM DA CORREÇÃO ---
    
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=protocolo_{protocolo.numero_protocolo}.pdf'
    
    return response

# --- ROTA PARA EXPORTAÇÃO EM EXCEL ---
@main_bp.route('/exportar/excel')
@login_required
def exportar_excel():
    # PASSO 1: REUTILIZAR EXATAMENTE A MESMA LÓGICA DE FILTRO E PERMISSÃO DA ROTA INDEX
    # Isso garante que o Excel exportado corresponda ao que o usuário está vendo na tela.
    if current_user.role == 'admin':
        query = Protocolo.query
    else:
        query = Protocolo.query.filter(or_(
            Protocolo.criado_por_id == current_user.id,
            Protocolo.setor_destinatario_id == current_user.setor_id,
            Protocolo.colaborador_destinatario_id == current_user.id
        ))
    
    args = request.args
    if args.get('termo_busca'):
        termo = f"%{args.get('termo_busca')}%"
        query = query.filter(or_(Protocolo.assunto.ilike(termo), Protocolo.descricao.ilike(termo), Protocolo.numero_protocolo.ilike(termo)))
    if args.get('status'):
        query = query.filter(Protocolo.status == args.get('status'))
    if args.get('data_inicio'):
        query = query.filter(Protocolo.data_criacao >= args.get('data_inicio'))
    if args.get('data_fim'):
        from datetime import datetime, time
        data_fim_obj = datetime.strptime(args.get('data_fim'), '%Y-%m-%d')
        data_fim_completa = datetime.combine(data_fim_obj, time.max)
        query = query.filter(Protocolo.data_criacao <= data_fim_completa)

    protocolos = query.order_by(Protocolo.data_criacao.desc()).all()
    
    # PASSO 2: PREPARAR OS DADOS PARA O PANDAS
    dados_para_excel = []
    for p in protocolos:
        dados_para_excel.append({
            'Número Protocolo': p.numero_protocolo,
            'Status': p.status,
            'Assunto': p.assunto,
            'Criado Por': p.criado_por.nome,
            'Data Criação': p.data_criacao.strftime('%d/%m/%Y %H:%M'),
            'Setor Destino': p.setor_destinatario.nome,
            'Destinatário Específico': p.colaborador_destinatario.nome if p.colaborador_destinatario else ''
        })
        
    df = pd.DataFrame(dados_para_excel)
    
    # PASSO 3: CRIAR O ARQUIVO EXCEL EM MEMÓRIA
    output = BytesIO()
    df.to_excel(output, index=False, sheet_name='Protocolos')
    output.seek(0)
    
    # PASSO 4: ENVIAR O ARQUIVO PARA O USUÁRIO
    return send_file(
        output,
        download_name="relatorio_protocolos.xlsx",
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# --- ROTAS DE API PARA RELATÓRIOS ---

@main_bp.route('/api/relatorios/protocolos_por_mes')
@login_required
@permission_required('acessar_painel_admin')
def api_protocolos_por_mes():
    doze_meses_atras = datetime.utcnow() - timedelta(days=365)
    
    # --- CORREÇÃO FINAL ---
    # Usamos literal_column para tratar o texto como uma coluna que pode ser nomeada com .label()
    # E a usamos tanto no select, quanto no group_by e no order_by para consistência.
    mes_expression = literal_column("FORMAT(data_criacao, 'yyyy-MM')")
    
    dados = db.session.query(
        mes_expression.label('mes'),
        func.count(Protocolo.id).label('total')
    ).filter(Protocolo.data_criacao >= doze_meses_atras).group_by(mes_expression).order_by(mes_expression).all()
    # --- FIM DA CORREÇÃO ---
    
    labels = [dado.mes for dado in dados]
    data = [dado.total for dado in dados]
    
    return jsonify({'labels': labels, 'data': data})

@main_bp.route('/api/relatorios/protocolos_por_status')
@login_required
@permission_required('acessar_painel_admin')
def api_protocolos_por_status():
    dados = db.session.query(
        Protocolo.status,
        func.count(Protocolo.id).label('total')
    ).group_by(Protocolo.status).order_by(func.count(Protocolo.id).desc()).all()
    
    labels = [dado.status for dado in dados]
    data = [dado.total for dado in dados]
    
    return jsonify({'labels': labels, 'data': data})

@main_bp.route('/api/relatorios/protocolos_por_setor')
@login_required
@permission_required('acessar_painel_admin')
def api_protocolos_por_setor():
    dados = db.session.query(
        Setor.nome,
        func.count(Protocolo.id).label('total')
    ).join(Protocolo, Setor.id == Protocolo.setor_destinatario_id).group_by(Setor.nome).order_by(func.count(Protocolo.id).desc()).all()

    labels = [dado.nome for dado in dados]
    data = [dado.total for dado in dados]
    
    return jsonify({'labels': labels, 'data': data})


@main_bp.route('/admin/relatorios/auditoria')
@login_required
@permission_required('acessar_painel_admin')
def relatorio_auditoria():
    page = request.args.get('page', 1, type=int)
    per_page = 25 # Definimos um padrão de 25 por página para o log

    form = AuditoriaForm(request.args)
    # Popula o dropdown de colaboradores com uma opção "Todos"
    form.colaborador.choices = [(c.id, c.nome) for c in Colaborador.query.order_by(Colaborador.nome).all()]
    form.colaborador.choices.insert(0, (0, 'Todos os Colaboradores'))

    # Consulta base na tabela de Histórico
    query = Historico.query

    # Aplica filtros
    if form.protocolo_numero.data:
        # Precisa de um join para buscar pelo número do protocolo
        query = query.join(Protocolo).filter(Protocolo.numero_protocolo.ilike(f"%{form.protocolo_numero.data}%"))

    if form.colaborador.data and form.colaborador.data != 0:
        query = query.filter(Historico.colaborador_id == form.colaborador.data)

    if form.data_inicio.data:
        query = query.filter(Historico.data_ocorrencia >= form.data_inicio.data)

    if form.data_fim.data:
        from datetime import datetime, time
        data_fim_completa = datetime.combine(form.data_fim.data, time.max)
        query = query.filter(Historico.data_ocorrencia <= data_fim_completa)

    pagination = query.order_by(Historico.data_ocorrencia.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template('admin/auditoria.html', 
                           pagination=pagination, 
                           form=form, 
                           title="Trilha de Auditoria")


@main_bp.route('/minha-conta', methods=['GET', 'POST'])
@login_required
def minha_conta():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        # Verifica se a senha atual está correta
        if current_user.verificar_senha(form.senha_atual.data):
            # Atualiza para a nova senha (o setter no modelo já faz o hash)
            current_user.senha = form.nova_senha.data
            db.session.commit()
            flash('Sua senha foi alterada com sucesso!', 'success')
            return redirect(url_for('main.minha_conta'))
        else:
            flash('Senha atual incorreta.', 'danger')

    return render_template('minha_conta.html', title="Minha Conta", form=form)


@main_bp.route('/api/protocolo/update_status', methods=['POST'])
@login_required
def api_update_protocolo_status():
    data = request.get_json()
    if not data or 'protocolo_id' not in data or 'novo_status' not in data:
        abort(400) # Erro de "Bad Request" se os dados estiverem incompletos

    protocolo = Protocolo.query.get_or_404(data['protocolo_id'])
    novo_status = data['novo_status']

    # Reutiliza a mesma lógica de permissão da tramitação!
    if not current_user.tem_permissao('acessar_painel_admin') and \
   protocolo.criado_por_id != current_user.id and \
   protocolo.setor_destinatario_id != current_user.setor_id and \
   protocolo.colaborador_destinatario_id != current_user.id:
        abort(403)

    # Atualiza o status
    protocolo.status = novo_status

    # Cria o registro de histórico para a trilha de auditoria
    novo_historico = Historico(
        descricao=f"Status alterado para '{novo_status}' através do quadro Kanban.",
        protocolo_id=protocolo.id,
        colaborador_id=current_user.id
    )
    db.session.add(novo_historico)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Status atualizado com sucesso.'})


@main_bp.route('/api/modelo/update_order', methods=['POST'])
@csrf.exempt
@login_required
def update_field_order():
    data = request.get_json()
    if not data or 'field_ids' not in data:
        abort(400) # Erro de requisição inválida

    try:
        for index, field_id in enumerate(data['field_ids']):
            campo = CampoModelo.query.get(field_id)
            if campo:
                campo.ordem = index

        db.session.commit()
        return jsonify({'success': True, 'message': 'Ordem atualizada com sucesso.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    
@main_bp.route('/consultar-nfe', methods=['GET', 'POST'])
@login_required
def consultar_nfe():
    form = NFeConsultaForm()
    if form.validate_on_submit():
        chave = form.chave_acesso.data
        return render_template('admin/nfe_resultado.html', chave_acesso=chave, title="Resultado da Consulta")
    return render_template('admin/consultar_nfe.html', form=form, title="Consultar NF-e")


@main_bp.route('/download-nfe/xml/<chave_acesso>')
@login_required
def download_nfe_xml(chave_acesso):
    xml_content = _obter_xml_por_chave_sefaz(chave_acesso)
    
    if not xml_content:
        flash('Não foi possível obter o XML completo para esta chave de acesso.', 'danger')
        return redirect(url_for('main.consultar_nfe'))

    response = make_response(xml_content)
    response.headers['Content-Type'] = 'application/xml'
    response.headers['Content-Disposition'] = f'attachment; filename={chave_acesso}-nfe.xml'
    return response

@main_bp.route('/api/protocolo/<int:protocolo_id>/toggle_conferencia', methods=['POST'])
@login_required
def toggle_conferencia_linha(protocolo_id):
    data = request.get_json()
    row_index = data.get('row_index')

    if row_index is None:
        return jsonify({'success': False, 'message': 'Índice da linha não fornecido.'}), 400

    protocolo = Protocolo.query.get_or_404(protocolo_id)

    # Verifica permissões (mesma lógica de visualização)
    if not current_user.tem_permissao('acessar_painel_admin') and \
       protocolo.criado_por_id != current_user.id and \
       protocolo.setor_destinatario_id != current_user.setor_id and \
       protocolo.colaborador_destinatario_id != current_user.id:
        return jsonify({'success': False, 'message': 'Acesso negado.'}), 403

    # Lógica para alternar o status
    if protocolo.dados_preenchidos and len(protocolo.dados_preenchidos) > row_index:
        # Precisamos clonar a lista para modificá-la
        dados_lista = list(protocolo.dados_preenchidos)
        linha = dados_lista[row_index]
        
        # Alterna o valor booleano (cria se não existir)
        estado_atual = linha.get('_conferido', False)
        linha['_conferido'] = not estado_atual
        
        # Salva de volta
        protocolo.dados_preenchidos = dados_lista
        
        # Informa ao SQLAlchemy que o campo JSON mudou
        flag_modified(protocolo, "dados_preenchidos")
        
        db.session.commit()
        
        return jsonify({'success': True, 'novo_estado': linha['_conferido']})
    
    return jsonify({'success': False, 'message': 'Linha não encontrada.'}), 404

@main_bp.route('/download-nfe/pdf/<chave_acesso>')
@login_required
def download_nfe_pdf(chave_acesso):
    xml_content = _obter_xml_por_chave_sefaz(chave_acesso)
    
    if not xml_content:
        flash('Não foi possível obter o XML completo para gerar o PDF.', 'danger')
        return redirect(url_for('main.consultar_nfe'))
    
    try:
        danfe = Danfe(xml=xml_content)
        pdf_buffer = BytesIO()
        danfe.gerarPDF(output=pdf_buffer)
        pdf_buffer.seek(0)
        
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=f'{chave_acesso}-danfe.pdf',
            mimetype='application/pdf'
        )
    except Exception as e:
        flash(f'Ocorreu um erro ao gerar o PDF: {e}', 'danger')
        return redirect(url_for('main.consultar_nfe'))