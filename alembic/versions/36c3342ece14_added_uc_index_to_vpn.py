"""Added UC index to VPN

Revision ID: 36c3342ece14
Revises: 3faeedfd1352
Create Date: 2016-05-31 20:47:40.054363

"""

# revision identifiers, used by Alembic.
revision = '36c3342ece14'
down_revision = '3faeedfd1352'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_index('ix_vpmap_vpno', 'VendorPartNumber', ['vpmap_id', 'vpno'], unique=False)
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('ix_vpmap_vpno', table_name='VendorPartNumber')
    ### end Alembic commands ###