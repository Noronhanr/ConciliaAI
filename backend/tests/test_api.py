import fitz

from app import main


def headers(client):
    response = client.post('/auth/token', data={'username': 'teste', 'password': 'senha-forte'})
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def test_health(client):
    assert client.get('/health').json()['phase'] == 3


def test_auth_and_batch(client):
    assert client.get('/batches').status_code == 401
    assert client.post('/auth/token', data={'username': 'teste', 'password': 'errada'}).status_code == 401
    h = headers(client)
    assert client.get('/auth/me', headers=h).json()['role'] == 'operador'
    created = client.post('/batches', headers=h)
    assert created.status_code == 201
    assert created.json()['status'] == 'created'
    assert len(client.get('/batches', headers=h).json()) == 1


def test_upload_progress_and_enqueue(client, monkeypatch):
    h = headers(client)
    batch_id = client.post('/batches', headers=h).json()['id']
    monkeypatch.setattr(main, 'upload_stream', lambda *args: None)
    sent = []
    monkeypatch.setattr(main.process_page, 'delay', lambda page_id: sent.append(page_id))
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), 'Um contrato de demonstracao para testar OCR')
    raw = doc.tobytes()
    doc.close()
    response = client.post(f'/batches/{batch_id}/upload', headers=h,
        files={'file': ('contrato.pdf', raw, 'application/pdf')})
    assert response.status_code == 201, response.text
    assert response.json()['total_pages'] == 1
    assert client.get(f'/batches/{batch_id}/progress', headers=h).json()['pages_total'] == 1
    queued = client.post(f'/batches/{batch_id}/start', headers=h)
    assert queued.status_code == 200
    assert len(sent) == 1
    assert client.get(f'/batches/{batch_id}/pages', headers=h).json()[0]['status'] == 'pending'


def test_reject_invalid_and_unauthorized(client, monkeypatch):
    h = headers(client)
    batch = client.post('/batches', headers=h).json()['id']
    assert client.post(f'/batches/{batch}/upload',
        files={'file': ('x.pdf', b'bad', 'application/pdf')}).status_code == 401
    assert client.post(f'/batches/{batch}/upload', headers=h,
        files={'file': ('x.exe', b'bad', 'application/octet-stream')}).status_code == 415
    assert client.post(f'/batches/{batch}/upload', headers=h,
        files={'file': ('x.pdf', b'bad', 'application/pdf')}).status_code == 422


def test_companies_and_dossier(client, monkeypatch):
    from app.database import SessionLocal
    from app.models import Page

    h = headers(client)
    batch_id = client.post('/batches', headers=h).json()['id']
    monkeypatch.setattr(main, 'upload_stream', lambda *args: None)

    # Cria páginas com OCR mockado de contrato, aditivo e nota fiscal
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), 'Teste')
    raw = doc.tobytes()
    doc.close()

    res = client.post(f'/batches/{batch_id}/upload', headers=h,
                      files={'file': ('lote_teste.pdf', raw, 'application/pdf')})
    file_id = res.json()['id']

    with SessionLocal() as db:
        # Atualiza a página criada com texto de contrato
        p1 = db.query(Page).filter_by(source_file_id=file_id, page_number=1).first()
        p1.status = 'ok'
        p1.ocr_text = (
            "CONTRATO DE PRESTACAO DE SERVICOS\n"
            "Instrumento: CTR-001\n"
            "Contratada: Empresa Alfa Servicos Ltda\n"
            "CNPJ contratada: 87.000.001/1001-78\n"
            "CNPJ contratante: 87.000.999/1999-99\n"
            "Valor mensal: R$ 4.000,00\n"
            "Vigencia: 01/01/2026 a 31/12/2026\n"
            "Pagina 1 de 1"
        )
        # Adiciona página de nota fiscal
        p2 = Page(
            source_file_id=file_id,
            page_number=2,
            status='ok',
            ocr_text=(
                "NOTA FISCAL DE SERVICOS - DEMONSTRACAO\n"
                "Numero: 30001\n"
                "Prestador: Empresa Alfa Servicos Ltda\n"
                "CNPJ prestador: 87.000.001/1001-78\n"
                "Valor do servico: R$ 4.000,00\n"
                "Contrato referenciado: CTR-001\n"
                "Pagina 1 de 1"
            )
        )
        db.add(p2)
        db.commit()

    # Aciona a montagem de documentos
    res_assemble = client.post(f'/batches/{batch_id}/assemble', headers=h)
    assert res_assemble.status_code == 200
    assert res_assemble.json()['total_documents'] == 2
    assert res_assemble.json()['total_companies'] == 1

    # Consulta empresas do lote
    comps = client.get(f'/batches/{batch_id}/companies', headers=h).json()
    assert len(comps) == 1
    c = comps[0]
    assert c['cnpj'] == '87000001100178'
    assert c['razao_social'] == 'Empresa Alfa Servicos Ltda'
    assert c['total_contracts'] == 1
    assert c['total_invoices'] == 1
    assert c['total_invoiced_value'] == 4000.0


    # Consulta dossiê
    dossier = client.get(f'/batches/{batch_id}/companies/{c["id"]}/dossier', headers=h).json()
    assert len(dossier['contracts']) == 1
    assert dossier['contracts'][0]['contract']['document_code'] == 'CTR-001'
    assert len(dossier['invoices']) == 1
    assert dossier['invoices'][0]['document_code'] == 'NF-30001'

