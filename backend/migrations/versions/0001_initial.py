from alembic import op
from app.main import Base
revision = "0001_initial"
down_revision = None
def upgrade(): Base.metadata.create_all(op.get_bind())
def downgrade(): Base.metadata.drop_all(op.get_bind())
