"""add pronunciation columns

Revision ID: dccaddccbbda
Revises: 3ba9a838aae2
Create Date: 2021-03-17 21:10:12.796266

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dccaddccbbda'
down_revision = '3ba9a838aae2'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('person', sa.Column('name_recording', sa.String(), nullable=True))
    op.add_column('person', sa.Column('phonetic_name', sa.String(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('person', 'phonetic_name')
    op.drop_column('person', 'name_recording')
    # ### end Alembic commands ###
