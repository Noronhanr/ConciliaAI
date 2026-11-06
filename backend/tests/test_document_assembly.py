from app.document_assembly import (
    clean_cnpj,
    cnpj_valid,
    extract_metadata_from_text,
    format_cnpj,
    parse_money,
    segment_source_file_pages,
)
from app.models import Page


def test_cnpj_validation_and_cleaning():
    valid = "87.000.001/1001-78"
    raw_digits = "87000001100178"
    assert cnpj_valid(valid) is True
    assert cnpj_valid(raw_digits) is True
    assert cnpj_valid("11.111.111/1111-11") is False
    assert cnpj_valid("87000001100148") is False  # DV errado

    # OCR cleaning with 'O' instead of '0'
    ocr_noisy = "87.OOO.OO1/1OO1-78"
    cleaned = clean_cnpj(ocr_noisy)
    assert cleaned == raw_digits
    assert cnpj_valid(cleaned) is True
    assert format_cnpj(cleaned) == "87.000.001/1001-78"


def test_parse_money():
    assert parse_money("R$ 4.000,00") == 4000.0
    assert parse_money("2.500,50") == 2500.50
    assert parse_money("1234.56") == 1234.56
    assert parse_money(None) is None


def test_extract_contract_metadata():
    text = (
        "CONTRATO DE PRESTACAO DE SERVICOS\n"
        "Instrumento: CTR-001\n"
        "Contratada: Empresa Alfa Servicos Ltda\n"
        "CNPJ contratada: 87.000.001/1001-78\n"
        "CNPJ contratante: 87.000.999/1999-99\n"
        "Objeto: Manutencao predial\n"
        "Valor mensal: R$ 4.000,00\n"
        "Vigencia: 01/01/2026 a 31/12/2026\n"
        "Pagina 1 de 2"
    )
    meta = extract_metadata_from_text(text)
    assert meta["doc_type"] == "contrato"
    assert meta["document_code"] == "CTR-001"
    assert meta["prestador_cnpj"] == "87000001100178"
    assert meta["tomador_cnpj"] == "87000999199999"
    assert meta["razao_social"] == "Empresa Alfa Servicos Ltda"
    assert meta["valor"] == 4000.0
    assert meta["vigencia"] == "01/01/2026 a 31/12/2026"


def test_extract_invoice_and_amendment_metadata():
    inv_text = (
        "NOTA FISCAL DE SERVICOS - DEMONSTRACAO\n"
        "Numero: 30001\n"
        "Prestador: Empresa Alfa Servicos Ltda\n"
        "CNPJ prestador: 87.000.001/1001-78\n"
        "CNPJ tomador: 87.000.999/1999-99\n"
        "Data emissao: 2026-08-01\n"
        "Descricao: Manutencao predial\n"
        "Valor do servico: R$ 6.500,00\n"
        "Contrato referenciado: CTR-001\n"
        "Pagina 1 de 1"
    )
    meta_inv = extract_metadata_from_text(inv_text)
    assert meta_inv["doc_type"] == "nota_fiscal_servico"
    assert meta_inv["document_code"] == "NF-30001"
    assert meta_inv["prestador_cnpj"] == "87000001100178"
    assert meta_inv["valor"] == 6500.0
    assert meta_inv["contrato_referenciado"] == "CTR-001"

    adt_text = (
        "TERMO ADITIVO CONTRATUAL\n"
        "Aditivo: ADT-001\n"
        "Contrato: CTR-001\n"
        "Fornecedor: 87.000.001/1001-78\n"
        "Acrescimo mensal: R$ 2.500,00\n"
        "Vigencia do aditivo: 2026-08-01 ate 2026-12-31\n"
        "Pagina 1 de 1"
    )
    meta_adt = extract_metadata_from_text(adt_text)
    assert meta_adt["doc_type"] == "aditivo_contratual"
    assert meta_adt["document_code"] == "ADT-001"
    assert meta_adt["prestador_cnpj"] == "87000001100178"
    assert meta_adt["valor"] == 2500.0
    assert meta_adt["contrato_referenciado"] == "CTR-001"



def test_segment_source_file_pages():
    pages = [
        Page(page_number=1, ocr_text="CONTRATO DE PRESTACAO\nInstrumento: CTR-001\nPagina 1 de 2"),
        Page(page_number=2, ocr_text="Clausula segunda\nPagina 2 de 2"),
        Page(page_number=3, ocr_text="NOTA FISCAL DE SERVICOS\nNumero: 101\nPagina 1 de 1"),
    ]
    segments = segment_source_file_pages(pages)
    assert len(segments) == 2
    assert [p.page_number for p in segments[0]] == [1, 2]
    assert [p.page_number for p in segments[1]] == [3]
