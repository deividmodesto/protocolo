from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError
from app.models import Colaborador, Setor

class RegistrationForm(FlaskForm):
    """Formulário de registro de novo colaborador."""
    nome = StringField('Nome Completo', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    # O 'coerce=int' garante que o valor do campo seja um inteiro.
    setor = SelectField('Setor', coerce=int, validators=[DataRequired()])
    password = PasswordField('Senha', validators=[DataRequired()])
    confirm_password = PasswordField('Confirmar Senha', 
                                     validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Registrar')

    # Validador customizado para verificar se o email já existe no banco
    def validate_email(self, email):
        user = Colaborador.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Este email já está em uso. Por favor, escolha outro.')

class LoginForm(FlaskForm):
    """Formulário de login."""
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Senha', validators=[DataRequired()])
    submit = SubmitField('Login')