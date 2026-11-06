"""Empresas, documentos lógicos e relacionamento com páginas.

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cnpj", sa.String(14), nullable=False, unique=True),
        sa.Column("razao_social", sa.String(255), nullable=False),
        sa.Column("nome_fantasia", sa.String(255), nullable=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="supplier"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_companies_cnpj", "companies", ["cnpj"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("batches.id"), nullable=False),
        sa.Column("source_file_id", sa.Integer(), sa.ForeignKey("source_files.id"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("doc_type", sa.String(50), nullable=False, server_default="outro"),
        sa.Column("document_code", sa.String(80), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("start_page", sa.Integer(), nullable=False),
        sa.Column("end_page", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="extracted"),
        sa.Column("extracted_data", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_batch_id", "documents", ["batch_id"])
    op.create_index("ix_documents_source_file_id", "documents", ["source_file_id"])
    op.create_index("ix_documents_company_id", "documents", ["company_id"])

    op.add_column("pages", sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=True))
    op.create_index("ix_pages_document_id", "pages", ["document_id"])


def downgrade():
    op.drop_index("ix_pages_document_id", "pages")
    op.drop_column("pages", "document_id")
    op.drop_index("ix_documents_company_id", "documents")
    op.drop_index("ix_documents_source_file_id", "documents")
    op.drop_index("ix_documents_batch_id", "documents")
    op.drop_table("documents")
    op.drop_index("ix_companies_cnpj", "companies")
    op.drop_table("companies")
