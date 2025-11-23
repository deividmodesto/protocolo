from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError
from app.models import Colaborador, Setor

class RegistrationForm(FlaskForm):
    """Formulário de registro de novo colaborador."""
    nome = StringField('Nome Completo', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    setor = SelectField('Setor', coerce=int, validators=[DataRequired()])
    password = PasswordField('Senha', validators=[DataRequired()])
    confirm_password = PasswordField('Confirmar Senha', 
                                     validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Registrar')

    def validate_email(self, email):
        user = Colaborador.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Este email já está em uso. Por favor, escolha outro.')

class LoginForm(FlaskForm):
    """Formulário de login."""
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Senha', validators=[DataRequired()])
    submit = SubmitField('Login')

class ProtocoloForm(FlaskForm):
    """Formulário para a criação de um novo protocolo."""
    assunto = StringField('Assunto', validators=[DataRequired()])
    setor_destinatario = SelectField('Encaminhar para o Setor', coerce=int, validators=[DataRequired()])
    descricao = TextAreaField('Descrição detalhada', validators=[DataRequired()])
    habilita_conferencia = BooleanField('Habilitar Conferência de Linhas (Checklist)')
    submit = SubmitField('Criar Protocolo')
    submit_rascunho = SubmitField('Salvar como Rascunho')