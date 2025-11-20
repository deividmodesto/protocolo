"""Adiciona campo de ordem aos campos do modelo

Revision ID: 336bf9147401
Revises: b6cd452bd36b
Create Date: 2025-09-26 22:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '336bf9147401'
down_revision = 'b6cd452bd36b' # Verifique se esta é a revisão anterior correta
branch_labels = None
depends_on = None


def upgrade():
    # ### Comandos corrigidos para adicionar apenas a coluna 'ordem' ###
    with op.batch_alter_table('CampoModelo', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ordem', sa.Integer(), nullable=True, server_default='0'))


def downgrade():
    # ### Comandos corrigidos para remover apenas a coluna 'ordem' ###
    with op.batch_alter_table('CampoModelo', schema=None) as batch_op:
        batch_op.drop_column('ordem')