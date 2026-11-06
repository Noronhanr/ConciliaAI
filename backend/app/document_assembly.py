"""Segmentação de documentos, extração de entidades e resolução por empresa."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Batch, Company, Document, Page, SourceFile


def cnpj_valid(number: str) -> bool:
    """Valida CNPJ com dígitos verificadores (módulo 11)."""
    digits = re.sub(r"\D", "", number or "")
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    for length in (12, 13):
        weights = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] if length == 12 else [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        rem = sum(int(d) * w for d, w in zip(digits[:length], weights)) % 11
        expected = 0 if rem < 2 else 11 - rem
        if int(digits[length]) != expected:
            return False
    return True


def clean_cnpj(raw: str) -> str:
    """Remove caracteres não-dígitos e normaliza trocas comuns de OCR."""
    if not raw:
        return ""
    # Corrige confusões clássicas de OCR antes da limpeza de pontuação
    s = raw.replace("O", "0").replace("o", "0")
    digits = re.sub(r"\D", "", s)
    return digits


def format_cnpj(digits: str) -> str:
    """Formata 14 dígitos no padrão XX.XXX.XXX/XXXX-XX."""
    d = clean_cnpj(digits)
    if len(d) != 14:
        return digits
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def parse_money(raw: str | None) -> float | None:
    """Converte 'R$ 4.000,00' ou '4000.00' em float."""
    if not raw:
        return None
    cleaned = re.sub(r"[^\d,.]", "", raw).strip()
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_metadata_from_text(full_text: str) -> dict[str, Any]:
    """Extrai campos estruturados, tipo de documento e CNPJs do texto OCR."""
    text_upper = full_text.upper()

    # 1. Tipo do documento
    doc_type = "outro"
    title = "Documento Desconhecido"
    if "CONTRATO DE PRESTACAO" in text_upper or ("CONTRATO" in text_upper and "INSTRUMENTO" in text_upper):
        doc_type = "contrato"
        title = "Contrato de Prestação de Serviços"
    elif "TERMO ADITIVO" in text_upper or "ADITIVO CONTRATUAL" in text_upper:
        doc_type = "aditivo_contratual"
        title = "Termo Aditivo Contratual"
    elif "NOTA FISCAL" in text_upper or "NFS-E" in text_upper or "VALOR DO SERVICO" in text_upper:
        doc_type = "nota_fiscal_servico"
        title = "Nota Fiscal de Serviços"

    # 2. Código identificador do documento
    document_code = None
    if doc_type == "contrato":
        m = re.search(r"Instrumento:\s*([A-Za-z0-9_-]+)", full_text, re.IGNORECASE)
        if m:
            document_code = m.group(1).strip()
    elif doc_type == "aditivo_contratual":
        m = re.search(r"Aditivo:\s*([A-Za-z0-9_-]+)", full_text, re.IGNORECASE)
        if m:
            document_code = m.group(1).strip()
    elif doc_type == "nota_fiscal_servico":
        m = re.search(r"Numero:\s*([A-Za-z0-9_-]+)", full_text, re.IGNORECASE)
        if m:
            document_code = f"NF-{m.group(1).strip()}"

    # 3. CNPJ Prestador / Contratada
    prestador_cnpj = None
    m_prest = re.search(
        r"(?:CNPJ\s+(?:prestador|contratada)|Fornecedor):\s*([0-9O./ -]+)",
        full_text,
        re.IGNORECASE,
    )
    if m_prest:
        candidate = clean_cnpj(m_prest.group(1))
        if cnpj_valid(candidate):
            prestador_cnpj = candidate

    # 4. CNPJ Tomador / Contratante
    tomador_cnpj = None
    m_tom = re.search(
        r"CNPJ\s+(?:tomador|contratante):\s*([0-9O./ -]+)",
        full_text,
        re.IGNORECASE,
    )
    if m_tom:
        candidate = clean_cnpj(m_tom.group(1))
        if cnpj_valid(candidate):
            tomador_cnpj = candidate

    # Fallback se não pegou por rótulo: busca todos os CNPJs válidos no texto
    if not prestador_cnpj:
        all_cnpjs = []
        for m in re.finditer(r"\b[0-9O]{2}[.\s]?[0-9O]{3}[.\s]?[0-9O]{3}[/\s]?[0-9O]{4}[-\s]?[0-9O]{2}\b", full_text):
            cand = clean_cnpj(m.group(0))
            if cnpj_valid(cand) and cand not in all_cnpjs:
                all_cnpjs.append(cand)
        if all_cnpjs:
            prestador_cnpj = all_cnpjs[0]
            if len(all_cnpjs) > 1 and not tomador_cnpj:
                tomador_cnpj = all_cnpjs[1]

    # 5. Razão Social
    razao_social = None
    m_razao = re.search(
        r"(?:Contratada|Prestador):\s*([^\n\r]+)",
        full_text,
        re.IGNORECASE,
    )
    if m_razao:
        clean_name = m_razao.group(1).strip()
        if len(clean_name) > 2:
            razao_social = clean_name[:255]

    # 6. Valores
    valor = None
    m_val = re.search(
        r"(?:Valor\s+(?:mensal|do\s+servico)|Acrescimo\s+mensal):\s*([R$\s0-9.,]+)",
        full_text,
        re.IGNORECASE,
    )
    if m_val:
        valor = parse_money(m_val.group(1))

    # 7. Vigência / Datas
    vigencia = None
    m_vig = re.search(
        r"Vigencia(?:\s+do\s+aditivo)?:\s*([^\n\r]+)",
        full_text,
        re.IGNORECASE,
    )
    if m_vig:
        vigencia = m_vig.group(1).strip()

    data_emissao = None
    m_dt = re.search(r"Data\s+emissao:\s*([0-9/-]+)", full_text, re.IGNORECASE)
    if m_dt:
        data_emissao = m_dt.group(1).strip()

    # 8. Contrato referenciado (em notas e aditivos)
    contrato_ref = None
    m_cref = re.search(r"Contrato(?:\s+referenciado)?:\s*([A-Za-z0-9_-]+)", full_text, re.IGNORECASE)
    if m_cref:
        c_code = m_cref.group(1).strip()
        if c_code.lower() != "nao":
            contrato_ref = c_code

    # 9. Descrição do serviço / objeto
    descricao = None
    m_desc = re.search(r"(?:Objeto|Descricao):\s*([^\n\r]+)", full_text, re.IGNORECASE)
    if m_desc:
        descricao = m_desc.group(1).strip()

    extracted = {
        "doc_type": doc_type,
        "title": title,
        "document_code": document_code,
        "prestador_cnpj": prestador_cnpj,
        "tomador_cnpj": tomador_cnpj,
        "razao_social": razao_social,
        "valor": valor,
        "vigencia": vigencia,
        "data_emissao": data_emissao,
        "contrato_referenciado": contrato_ref,
        "descricao": descricao,
    }
    return extracted


def resolve_company(session: Session, cnpj: str, razao_social: str | None) -> Company:
    """Busca empresa pelo CNPJ ou cria um novo registro."""
    clean = clean_cnpj(cnpj)
    stmt = select(Company).where(Company.cnpj == clean)
    company = session.scalar(stmt)
    if not company:
        name = razao_social or f"Fornecedor {format_cnpj(clean)}"
        company = Company(
            cnpj=clean,
            razao_social=name,
            role="supplier",
        )
        session.add(company)
        session.flush()
    elif razao_social and (not company.razao_social or company.razao_social.startswith("Fornecedor ")):
        company.razao_social = razao_social
        session.flush()
    return company


def segment_source_file_pages(pages: list[Page]) -> list[list[Page]]:
    """Agrupa páginas contínuas do mesmo documento físico usando rodapé 'Página X de Y' ou cabeçalhos."""
    if not pages:
        return []

    segments: list[list[Page]] = []
    current_segment: list[Page] = []

    for page in pages:
        text = page.ocr_text or ""
        # Verifica padrão "Página X de Y"
        m = re.search(r"P[aá]gina\s+(\d+)\s+de\s+(\d+)", text, re.IGNORECASE)

        # Verifica se esta página é explicitamente o início de um novo documento pelo cabeçalho
        is_explicit_start = False
        text_upper = text.upper()
        if (
            "CONTRATO DE PRESTACAO" in text_upper
            or "TERMO ADITIVO CONTRATUAL" in text_upper
            or "NOTA FISCAL DE SERVICOS" in text_upper
        ):
            # Se for página 1 explícita ou novo cabeçalho encontrado
            if m and int(m.group(1)) == 1:
                is_explicit_start = True
            elif not m and current_segment:
                is_explicit_start = True

        if is_explicit_start and current_segment:
            segments.append(current_segment)
            current_segment = []

        current_segment.append(page)

        if m:
            p_curr = int(m.group(1))
            p_total = int(m.group(2))
            if p_curr == p_total:
                # Chegou ao fim do documento indicado pelo rodapé
                segments.append(current_segment)
                current_segment = []

    if current_segment:
        segments.append(current_segment)

    return segments


def assemble_batch_documents(session: Session, batch_id: int) -> list[Document]:
    """Identifica documentos lógicos dentro do lote, associa páginas e vincula à empresa."""
    batch = session.get(Batch, batch_id)
    if not batch:
        return []

    # Limpa documentos anteriores caso seja um reprocessamento
    existing_docs = list(session.scalars(select(Document).where(Document.batch_id == batch_id)))
    if existing_docs:
        for p in session.scalars(select(Page).join(SourceFile).where(SourceFile.batch_id == batch_id)):
            p.document_id = None
        for d in existing_docs:
            session.delete(d)
        session.flush()

    source_files = list(
        session.scalars(select(SourceFile).where(SourceFile.batch_id == batch_id).order_by(SourceFile.id))
    )

    created_documents: list[Document] = []

    for sfile in source_files:
        pages = list(
            session.scalars(
                select(Page).where(Page.source_file_id == sfile.id).order_by(Page.page_number)
            )
        )
        if not pages:
            continue

        doc_segments = segment_source_file_pages(pages)

        for segment in doc_segments:
            start_page = segment[0].page_number
            end_page = segment[-1].page_number

            # Consolida texto e calcula média de confiança do OCR
            full_text = "\n\n".join(p.ocr_text for p in segment if p.ocr_text)
            confidences = [p.ocr_confidence for p in segment if p.ocr_confidence is not None]
            avg_confidence = round(sum(confidences) / len(confidences), 4) if confidences else 1.0

            # Extração de campos e metadados
            extracted = extract_metadata_from_text(full_text)

            # Resolução de empresa pelo CNPJ do prestador
            company_id = None
            if extracted.get("prestador_cnpj"):
                comp = resolve_company(session, extracted["prestador_cnpj"], extracted.get("razao_social"))
                company_id = comp.id

            doc = Document(
                batch_id=batch_id,
                source_file_id=sfile.id,
                company_id=company_id,
                doc_type=extracted["doc_type"],
                document_code=extracted["document_code"],
                title=extracted["title"],
                start_page=start_page,
                end_page=end_page,
                status="extracted",
                extracted_data=extracted,
                confidence=avg_confidence,
            )
            session.add(doc)
            session.flush()

            # Vincula cada página ao documento lógico criado
            for page in segment:
                page.document_id = doc.id

            created_documents.append(doc)

    batch.total_documents = len(created_documents)
    session.commit()
    return created_documents
