from app import db, login_manager, bcrypt
from flask_login import UserMixin
from datetime import datetime
import sqlalchemy as sa # Adicione esta linha
from sqlalchemy.dialects import mssql # Adicione esta linha


@login_manager.user_loader
def load_user(user_id):
    return Colaborador.query.get(int(user_id))

class Setor(db.Model):
    __tablename__ = 'Setor'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    colaboradores = db.relationship('Colaborador', backref='setor', lazy=True)
    protocolos_destinados = db.relationship('Protocolo', backref='setor_destinatario', lazy=True, foreign_keys='Protocolo.setor_destinatario_id')
    modelos_proprietario = db.relationship('ProtocoloModelo', backref='setor_proprietario', lazy=True)

perfil_permissoes = db.Table('perfil_permissoes',
    db.Column('perfil_id', db.Integer, db.ForeignKey('Perfil.id'), primary_key=True),
    db.Column('permissao_id', db.Integer, db.ForeignKey('Permissao.id'), primary_key=True)
)

class Permissao(db.Model):
    __tablename__ = 'Permissao'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), unique=True, nullable=False) # Ex: 'criar_protocolo'

class Perfil(db.Model):
    __tablename__ = 'Perfil'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), unique=True, nullable=False)
    colaboradores = db.relationship('Colaborador', backref='perfil', lazy=True)
    permissoes = db.relationship('Permissao', secondary=perfil_permissoes, lazy='subquery',
                                 backref=db.backref('perfis', lazy=True))

    def __repr__(self):
        return f'<Perfil {self.nome}>'
    
class Colaborador(db.Model, UserMixin):
    __tablename__ = 'Colaborador'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    perfil_id = db.Column(db.Integer, db.ForeignKey('Perfil.id'))
    setor_id = db.Column(db.Integer, db.ForeignKey('Setor.id'))
    protocolos_criados = db.relationship('Protocolo', backref='criado_por', lazy=True, foreign_keys='Protocolo.criado_por_id')
    historicos_criados = db.relationship('Historico', backref='colaborador', lazy=True)

    def tem_permissao(self, nome_permissao):
        if not self.perfil:
            return False
        return any(p.nome == nome_permissao for p in self.perfil.permissoes)
    
    @property
    def senha(self):
        raise AttributeError('senha is not a readable attribute')
    @senha.setter
    def senha(self, senha_texto):
        self.senha_hash = bcrypt.generate_password_hash(senha_texto).decode('utf-8')
    def verificar_senha(self, senha_texto):
        return bcrypt.check_password_hash(self.senha_hash, senha_texto)

class ProtocoloModelo(db.Model):
    __tablename__ = 'ProtocoloModelo'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    descricao = db.Column(db.Text)
    setor_proprietario_id = db.Column(db.Integer, db.ForeignKey('Setor.id'), nullable=False)
    campos = db.relationship('CampoModelo', backref='modelo', lazy=True, cascade="all, delete-orphan", order_by='CampoModelo.ordem')
    protocolos_usados = db.relationship('Protocolo', backref='modelo_usado', lazy=True)

class CampoModelo(db.Model):
    __tablename__ = 'CampoModelo'
    id = db.Column(db.Integer, primary_key=True)
    nome_campo = db.Column(db.String(100), nullable=False)
    tipo_campo = db.Column(db.String(50), nullable=False)
    opcoes = db.Column(db.Text)
    obrigatorio = db.Column(db.Boolean, nullable=False, default=False)
    modelo_id = db.Column(db.Integer, db.ForeignKey('ProtocoloModelo.id'), nullable=False)
    ordem = db.Column(db.Integer, default=0)

class Protocolo(db.Model):
    __tablename__ = 'Protocolo'
    id = db.Column(db.Integer, primary_key=True)
    numero_protocolo = db.Column(db.String(50), unique=True, nullable=False)
    assunto = db.Column(db.String(255), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    data_criacao = db.Column(mssql.DATETIME2, nullable=False, server_default=sa.text('(getdate())'))
    data_vencimento = db.Column(db.Date, nullable=True)
    is_externo = db.Column(db.Boolean, default=False, nullable=False)
    # fornecedor_id = db.Column(db.Integer, db.ForeignKey('Fornecedor.id'), nullable=True)
    fornecedor_ext_cod = db.Column(db.String(20), nullable=True) # Para guardar A2_COD
    fornecedor_ext_nome = db.Column(db.String(255), nullable=True) # Para guardar A2_NOME
    status = db.Column(db.String(50), nullable=False, default='Aberto')
    criado_por_id = db.Column(db.Integer, db.ForeignKey('Colaborador.id'), nullable=False)
    setor_destinatario_id = db.Column(db.Integer, db.ForeignKey('Setor.id'), nullable=False)
    colaborador_destinatario_id = db.Column(db.Integer, db.ForeignKey('Colaborador.id'), nullable=True)
    modelo_usado_id = db.Column(db.Integer, db.ForeignKey('ProtocoloModelo.id'))
    dados_preenchidos = db.Column(db.JSON)
    colaborador_destinatario = db.relationship('Colaborador', foreign_keys=[colaborador_destinatario_id])
    historico = db.relationship('Historico', backref='protocolo', lazy=True, cascade="all, delete-orphan")
    anexos = db.relationship('Anexo', backref='protocolo', lazy=True, cascade="all, delete-orphan")

class Historico(db.Model):
    __tablename__ = 'Historico'
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.Text, nullable=False)
    data_ocorrencia = db.Column(mssql.DATETIME2, nullable=False, server_default=sa.text('(getdate())'))
    protocolo_id = db.Column(db.Integer, db.ForeignKey('Protocolo.id'), nullable=False)
    colaborador_id = db.Column(db.Integer, db.ForeignKey('Colaborador.id'), nullable=False)

class Anexo(db.Model):
    __tablename__ = 'Anexo'
    id = db.Column(db.Integer, primary_key=True)
    nome_arquivo = db.Column(db.String(255), nullable=False)
    caminho_arquivo = db.Column(db.Text, nullable=False)
    protocolo_id = db.Column(db.Integer, db.ForeignKey('Protocolo.id'), nullable=False)

class Fornecedor(db.Model):
    __tablename__ = 'Fornecedor'
    id = db.Column(db.Integer, primary_key=True)
    razao_social = db.Column(db.String(255), nullable=False, unique=True)
    nome_fantasia = db.Column(db.String(255))
    cnpj = db.Column(db.String(20), unique=True)
    contato_nome = db.Column(db.String(100))
    contato_email = db.Column(db.String(120))
    contato_telefone = db.Column(db.String(20))

    # O backref 'protocolos' nos permitirá ver todos os protocolos de um fornecedor
    # protocolos = db.relationship('Protocolo', backref='fornecedor', lazy=True)

    def __repr__(self):
        return f'<Fornecedor {self.razao_social}>'