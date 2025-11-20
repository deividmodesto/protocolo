from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user # Adicione current_user ao import
from flask_bcrypt import Bcrypt
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
import pytz
from datetime import datetime, date, timedelta

def format_datetime_local(utc_datetime):
    if not utc_datetime:
        return ""
    local_tz = pytz.timezone('America/Sao_Paulo')
    local_dt = utc_datetime.replace(tzinfo=pytz.utc).astimezone(local_tz)
    return local_dt.strftime('%d/%m/%Y às %H:%M:%S')

# Cria instâncias das extensões
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'main.login'
bcrypt = Bcrypt()
mail = Mail()
csrf = CSRFProtect()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Inicializa as extensões com a aplicação
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)

    # Registra o filtro de template
    app.jinja_env.filters['localdatetime'] = format_datetime_local
    
    # Registra funções auxiliares para estarem disponíveis em todos os templates
    @app.context_processor
    def utility_processor():
        # Define a lista de todas as permissões que consideramos administrativas
        admin_permissions_list = [
            'acessar_painel_admin', 'gerenciar_setores', 'gerenciar_colaboradores',
            'gerenciar_fornecedores', 'gerenciar_modelos', 'ver_relatorios_gerenciais'
        ]

        def sla_status(vencimento, status):
            if status in ['Finalizado', 'Arquivado'] or not vencimento:
                return None
            
            hoje = date.today()
            dias_restantes = (vencimento - hoje).days
            
            if dias_restantes < 0:
                return {'cor': 'danger', 'texto': f'Atrasado {-dias_restantes} dia(s)'}
            elif dias_restantes <= 3:
                return {'cor': 'warning', 'texto': f'Vence em {dias_restantes} dia(s)'}
            else:
                return None

        # Nova função que verifica se o usuário tem QUALQUER uma das permissões da lista
        def tem_alguma_permissao(lista_de_permissoes):
            if not current_user.is_authenticated or not current_user.perfil:
                return False
            permissoes_do_usuario = {p.nome for p in current_user.perfil.permissoes}
            return not permissoes_do_usuario.isdisjoint(lista_de_permissoes)

        # Retorna as funções e a lista para os templates
        return dict(
            sla_status=sla_status, 
            tem_alguma_permissao=tem_alguma_permissao,
            admin_permissions=admin_permissions_list
        )

    # Popula o banco com permissões iniciais (se necessário)
    @app.cli.command('seed')
    def seed_db():
        """Popula o banco de dados com permissões iniciais e um perfil de admin."""
        from app.models import Permissao, Perfil

        permissoes = [
            'acessar_painel_admin', 'gerenciar_setores', 'gerenciar_colaboradores',
            'gerenciar_fornecedores', 'gerenciar_modelos', 'ver_relatorios_gerenciais',
            'gerenciar_perfis'
        ]

        for p_nome in permissoes:
            if not Permissao.query.filter_by(nome=p_nome).first():
                db.session.add(Permissao(nome=p_nome))
        
        admin_perfil = Perfil.query.filter_by(nome='Super Admin').first()
        if not admin_perfil:
            admin_perfil = Perfil(nome='Super Admin')
            db.session.add(admin_perfil)
            db.session.flush()
        
        todas_as_permissoes = Permissao.query.all()
        admin_perfil.permissoes = todas_as_permissoes

        print("Banco de dados populado com permissões e perfil de Super Admin.")
        db.session.commit()

    # Importa e registra os Blueprints
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    return app
