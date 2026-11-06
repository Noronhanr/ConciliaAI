import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function formatCurrency(val) {
  if (val == null) return '—';
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(val);
}

function App() {
  const [username, setUsername] = useState('operador');
  const [password, setPassword] = useState('');
  const [token, setToken] = useState('');
  const [role, setRole] = useState('');
  const [batches, setBatches] = useState([]);
  const [selected, setSelected] = useState(null);
  const [files, setFiles] = useState([]);
  const [progress, setProgress] = useState(null);
  const [pages, setPages] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState(null);
  const [dossier, setDossier] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const auth = { Authorization: `Bearer ${token}` };

  async function request(path, options = {}) {
    const res = await fetch(`${BASE}${path}`, options);
    if (!res.ok) {
      const payload = await res.json().catch(() => ({}));
      throw new Error(typeof payload.detail === 'string' ? payload.detail : `Erro HTTP ${res.status}`);
    }
    return res.json();
  }

  async function refresh(sessionToken = token, batchId = selected, companyId = selectedCompanyId) {
    if (!sessionToken) return;
    const headers = { Authorization: `Bearer ${sessionToken}` };
    const all = await request('/batches', { headers });
    setBatches(all);
    if (batchId != null) {
      const prog = await request(`/batches/${batchId}/progress`, { headers });
      setProgress(prog);
      const pgs = await request(`/batches/${batchId}/pages`, { headers });
      setPages(pgs);
      const comps = await request(`/batches/${batchId}/companies`, { headers }).catch(() => []);
      setCompanies(comps);

      if (companyId != null) {
        const d = await request(`/batches/${batchId}/companies/${companyId}/dossier`, { headers }).catch(() => null);
        setDossier(d);
      }
    }
  }

  useEffect(() => {
    if (!token || selected == null) return;
    refresh().catch(e => setError(e.message));
    const timer = setInterval(() => refresh().catch(e => setError(e.message)), 2500);
    return () => clearInterval(timer);
  }, [token, selected, selectedCompanyId]);

  async function login(event) {
    event.preventDefault();
    setError('');
    try {
      const body = new URLSearchParams({ username, password });
      const data = await request('/auth/token', { method: 'POST', body });
      setToken(data.access_token);
      setRole(data.role);
      setPassword('');
      await refresh(data.access_token, null);
    } catch (e) {
      setError(e.message);
    }
  }

  async function addBatch() {
    setError('');
    try {
      const b = await request('/batches', { method: 'POST', headers: auth });
      setSelected(b.id);
      setSelectedCompanyId(null);
      setDossier(null);
      await refresh(token, b.id, null);
    } catch (e) {
      setError(e.message);
    }
  }

  async function uploadFiles(event) {
    event.preventDefault();
    if (!files.length || selected == null) return;
    setBusy(true);
    setError('');
    try {
      for (const file of files) {
        const form = new FormData();
        form.append('file', file);
        await request(`/batches/${selected}/upload`, { method: 'POST', headers: auth, body: form });
      }
      setFiles([]);
      event.target.reset();
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    setBusy(true);
    setError('');
    try {
      await request(`/batches/${selected}/start`, { method: 'POST', headers: auth });
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function assemble() {
    setBusy(true);
    setError('');
    try {
      await request(`/batches/${selected}/assemble`, { method: 'POST', headers: auth });
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function openDossier(companyId) {
    setSelectedCompanyId(companyId);
    setError('');
    try {
      const d = await request(`/batches/${selected}/companies/${companyId}/dossier`, { headers: auth });
      setDossier(d);
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <main className="min-h-screen bg-slate-100 text-slate-900 pb-12">
      <header className="bg-slate-950 text-white px-8 py-6">
        <div className="max-w-6xl mx-auto flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold">Concilia AI</h1>
            <p className="text-slate-300 text-sm">Inteligência documental e conciliação contratual</p>
          </div>
          <span className="text-xs bg-blue-700 rounded-full px-3 py-1">Fases 3 & 4 · OCR e Dossiê por Empresa</span>
        </div>
      </header>

      <div className="max-w-6xl mx-auto p-6">
        <div className="bg-amber-50 border border-amber-200 rounded p-4 text-sm mb-6">
          Apoio à conferência. Não substitui análise jurídica ou tributária. Use somente arquivos sintéticos ou autorizados.
        </div>

        {!token ? (
          <form onSubmit={login} className="bg-white p-6 rounded-xl shadow max-w-md space-y-4">
            <h2 className="text-xl font-semibold">Entrar</h2>
            <label className="block text-sm">
              Usuário
              <input className="border rounded w-full p-2 mt-1" value={username} onChange={e => setUsername(e.target.value)} required />
            </label>
            <label className="block text-sm">
              Senha
              <input type="password" className="border rounded w-full p-2 mt-1" value={password} onChange={e => setPassword(e.target.value)} required />
            </label>
            <button className="bg-blue-700 text-white px-5 py-2 rounded font-medium hover:bg-blue-800 transition">Entrar</button>
          </form>
        ) : (
          <div className="grid md:grid-cols-3 gap-5">
            {/* Barra lateral de lotes */}
            <section className="bg-white rounded-xl shadow p-5">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-semibold">Lotes</h2>
                <button onClick={addBatch} className="bg-blue-700 text-white px-3 py-2 rounded text-sm hover:bg-blue-800 transition">Novo lote</button>
              </div>
              <p className="text-xs text-slate-500 mb-4">Perfil: {role}</p>
              <div className="space-y-2">
                {batches.map(b => (
                  <button
                    key={b.id}
                    onClick={() => {
                      setSelected(b.id);
                      setSelectedCompanyId(null);
                      setDossier(null);
                    }}
                    className={`block w-full text-left border rounded p-3 transition ${
                      selected === b.id ? 'border-blue-600 bg-blue-50' : 'hover:bg-slate-50'
                    }`}
                  >
                    <strong>Lote #{b.id}</strong>
                    <p className="text-xs text-slate-600 mt-1">{b.status} · {b.total_documents} documento(s)</p>
                  </button>
                ))}
                {!batches.length && <p className="text-slate-500 text-sm">Crie um lote para começar.</p>}
              </div>
              <button
                onClick={() => {
                  setToken('');
                  setBatches([]);
                  setSelected(null);
                  setProgress(null);
                  setPages([]);
                  setCompanies([]);
                  setDossier(null);
                }}
                className="border px-4 py-2 rounded mt-6 text-sm text-slate-600 hover:bg-slate-50"
              >
                Sair
              </button>
            </section>

            {/* Conteúdo principal */}
            <section className="md:col-span-2 space-y-5">
              {selected == null ? (
                <div className="bg-white p-6 rounded-xl shadow text-slate-600">Selecione ou crie um lote para continuar.</div>
              ) : (
                <>
                  {/* Upload */}
                  <form onSubmit={uploadFiles} className="bg-white p-5 rounded-xl shadow">
                    <h2 className="font-semibold mb-3">Enviar PDF ou imagens · Lote #{selected}</h2>
                    <input
                      type="file"
                      accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff"
                      multiple
                      onChange={e => setFiles([...e.target.files])}
                      className="block w-full text-sm mb-3"
                    />
                    <p className="text-xs text-slate-500 mb-3">Até 40 MB e 500 páginas por arquivo (PDF, PNG, JPG, TIFF).</p>
                    <button
                      disabled={busy || !files.length}
                      className="bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded font-medium hover:bg-blue-800 transition"
                    >
                      {busy ? 'Aguarde...' : `Enviar ${files.length || ''} arquivo(s)`}
                    </button>
                  </form>

                  {/* Progresso do OCR e Ações */}
                  <div className="bg-white p-5 rounded-xl shadow">
                    <div className="flex flex-wrap justify-between items-center gap-2">
                      <h2 className="font-semibold">Progresso do Processamento</h2>
                      <div className="flex gap-2">
                        <button
                          onClick={start}
                          disabled={busy || !progress || progress.counts.pending === 0}
                          className="bg-emerald-700 disabled:opacity-50 text-white px-3 py-1.5 rounded text-sm hover:bg-emerald-800 transition"
                        >
                          Iniciar OCR
                        </button>
                        <button
                          onClick={assemble}
                          disabled={busy || !progress || progress.pages_done === 0}
                          className="bg-indigo-700 disabled:opacity-50 text-white px-3 py-1.5 rounded text-sm hover:bg-indigo-800 transition"
                        >
                          Organizar por Empresa
                        </button>
                      </div>
                    </div>
                    <div className="mt-4 h-3 bg-slate-200 rounded overflow-hidden">
                      <div className="h-full bg-blue-600 transition-all" style={{ width: `${progress?.percent || 0}%` }} />
                    </div>
                    <p className="text-sm mt-2">
                      {progress ? `${progress.pages_done}/${progress.pages_total} páginas · ${progress.percent}% · ${progress.status}` : 'Carregando...'}
                    </p>
                    <div className="text-xs text-slate-500 mt-2">
                      {progress && `Concluídas: ${progress.counts.ok} · Falhas: ${progress.counts.error} · Pendentes: ${progress.counts.pending} · Processando: ${progress.counts.processing}`}
                    </div>
                  </div>

                  {/* Dossiês por Empresa / Fornecedor */}
                  <div className="bg-white p-5 rounded-xl shadow">
                    <div className="flex justify-between items-center mb-4">
                      <div>
                        <h2 className="font-semibold text-lg">Dossiês por Empresa / Fornecedor</h2>
                        <p className="text-xs text-slate-500">Documentos lógicos segmentados e agrupados por CNPJ</p>
                      </div>
                      {companies.length > 0 && (
                        <span className="text-xs bg-indigo-100 text-indigo-800 font-semibold px-2.5 py-1 rounded-full">
                          {companies.length} empresa(s)
                        </span>
                      )}
                    </div>

                    {!companies.length ? (
                      <div className="text-sm text-slate-500 bg-slate-50 p-4 rounded border text-center">
                        Nenhuma empresa identificada ainda. Conclua o OCR das páginas e clique em <strong>"Organizar por Empresa"</strong>.
                      </div>
                    ) : (
                      <div className="space-y-3">
                        <div className="grid sm:grid-cols-2 gap-3">
                          {companies.map(comp => (
                            <div
                              key={comp.id}
                              onClick={() => openDossier(comp.id)}
                              className={`p-4 border rounded-lg cursor-pointer transition ${
                                selectedCompanyId === comp.id
                                  ? 'border-indigo-600 bg-indigo-50/50 shadow-sm'
                                  : 'hover:border-slate-400 bg-white'
                              }`}
                            >
                              <div className="flex justify-between items-start">
                                <div>
                                  <h3 className="font-semibold text-sm text-slate-900">{comp.razao_social}</h3>
                                  <p className="text-xs text-slate-500 mt-0.5 font-mono">CNPJ: {comp.cnpj_formatted}</p>
                                </div>
                                <span className="text-xs font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                                  {formatCurrency(comp.total_invoiced_value)}
                                </span>
                              </div>
                              <div className="flex gap-2 mt-3 text-xs text-slate-600">
                                <span className="bg-slate-100 px-2 py-0.5 rounded">📄 {comp.total_contracts} contrato(s)</span>
                                <span className="bg-slate-100 px-2 py-0.5 rounded">➕ {comp.total_amendments} aditivo(s)</span>
                                <span className="bg-slate-100 px-2 py-0.5 rounded">📑 {comp.total_invoices} nota(s)</span>
                              </div>
                            </div>
                          ))}
                        </div>

                        {/* Visualizador de Dossiê Expandido */}
                        {dossier && (
                          <div className="mt-6 border-t pt-5">
                            <div className="flex justify-between items-center mb-4">
                              <div>
                                <h3 className="text-base font-bold text-slate-900">
                                  Dossiê: {dossier.company.razao_social}
                                </h3>
                                <p className="text-xs text-slate-500 font-mono">
                                  CNPJ {dossier.company.cnpj_formatted} · Total faturado: {formatCurrency(dossier.company.total_invoiced_value)}
                                </p>
                              </div>
                              <button
                                onClick={() => {
                                  setSelectedCompanyId(null);
                                  setDossier(null);
                                }}
                                className="text-xs text-slate-500 hover:text-slate-800 underline"
                              >
                                Fechar dossiê
                              </button>
                            </div>

                            {/* Contratos e Aditivos */}
                            <div className="space-y-3 mb-5">
                              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">Contratos & Aditivos Vinculados</h4>
                              {!dossier.contracts.length ? (
                                <p className="text-xs text-slate-400 italic">Nenhum contrato formal identificado para esta empresa.</p>
                              ) : (
                                dossier.contracts.map(item => (
                                  <div key={item.contract.id} className="border border-blue-200 bg-blue-50/40 rounded-lg p-4">
                                    <div className="flex justify-between items-start">
                                      <div>
                                        <div className="flex items-center gap-2">
                                          <span className="bg-blue-700 text-white text-xs px-2 py-0.5 rounded font-bold">
                                            {item.contract.document_code || 'CONTRATO'}
                                          </span>
                                          <span className="text-xs text-slate-500">
                                            Páginas {item.contract.start_page} a {item.contract.end_page}
                                          </span>
                                        </div>
                                        <p className="text-sm font-medium mt-1">
                                          {item.contract.extracted_data?.descricao || item.contract.title}
                                        </p>
                                        <p className="text-xs text-slate-600 mt-1">
                                          Vigência: {item.contract.extracted_data?.vigencia || '—'} · Valor Mensal: {formatCurrency(item.contract.extracted_data?.valor)}
                                        </p>
                                      </div>
                                    </div>

                                    {/* Aditivos do Contrato */}
                                    {item.amendments.length > 0 && (
                                      <div className="mt-3 pl-4 border-l-2 border-blue-300 space-y-2">
                                        <p className="text-xs font-semibold text-blue-900">Termos Aditivos Registrados:</p>
                                        {item.amendments.map(adt => (
                                          <div key={adt.id} className="bg-white p-2.5 rounded border border-blue-100 text-xs">
                                            <div className="flex justify-between items-center">
                                              <span className="font-bold text-slate-800">{adt.document_code || 'ADITIVO'}</span>
                                              <span className="text-emerald-700 font-medium">+{formatCurrency(adt.extracted_data?.valor)}</span>
                                            </div>
                                            <p className="text-slate-500 text-[11px] mt-0.5">
                                              Vigência: {adt.extracted_data?.vigencia || '—'} · Páginas {adt.start_page} a {adt.end_page}
                                            </p>
                                          </div>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                ))
                              )}
                            </div>

                            {/* Notas Fiscais */}
                            <div className="space-y-3">
                              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">Notas Fiscais de Serviço Extraídas</h4>
                              {!dossier.invoices.length ? (
                                <p className="text-xs text-slate-400 italic">Nenhuma nota fiscal encontrada para esta empresa.</p>
                              ) : (
                                <div className="grid sm:grid-cols-2 gap-2.5">
                                  {dossier.invoices.map(inv => (
                                    <div key={inv.id} className="border rounded-lg p-3 bg-white hover:border-slate-300 transition">
                                      <div className="flex justify-between items-start">
                                        <span className="font-bold text-xs bg-slate-100 text-slate-800 px-2 py-0.5 rounded">
                                          {inv.document_code || 'NOTA FISCAL'}
                                        </span>
                                        <span className="text-xs font-bold text-emerald-700">
                                          {formatCurrency(inv.extracted_data?.valor)}
                                        </span>
                                      </div>
                                      <p className="text-xs text-slate-700 mt-2 line-clamp-1">
                                        {inv.extracted_data?.descricao || 'Serviço prestado'}
                                      </p>
                                      <div className="flex justify-between items-center text-[11px] text-slate-500 mt-2 border-t pt-1.5">
                                        <span>Emissão: {inv.extracted_data?.data_emissao || '—'}</span>
                                        <span>Páginas {inv.start_page} a {inv.end_page}</span>
                                      </div>
                                      {inv.extracted_data?.contrato_referenciado && (
                                        <p className="text-[11px] text-blue-700 mt-1">
                                          Ref: {inv.extracted_data.contrato_referenciado}
                                        </p>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Texto extraído por página (Inspecionar OCR) */}
                  <div className="bg-white p-5 rounded-xl shadow">
                    <h2 className="font-semibold mb-3">Texto extraído por página (OCR)</h2>
                    <div className="space-y-3">
                      {pages
                        .filter(p => p.status === 'ok' || p.status === 'error')
                        .map(p => (
                          <details key={p.id} className="border rounded p-3">
                            <summary className="cursor-pointer text-sm font-medium">
                              Página {p.page_number} · {p.status} · {p.ocr_method || 'erro'} · Confiança{' '}
                              {p.ocr_confidence == null ? '—' : `${(p.ocr_confidence * 100).toFixed(1)}%`}
                            </summary>
                            <pre className="whitespace-pre-wrap text-xs mt-3 max-h-48 overflow-auto text-slate-700 bg-slate-50 p-2 rounded">
                              {p.ocr_text || p.error || '(nenhum texto reconhecido)'}
                            </pre>
                          </details>
                        ))}
                    </div>
                  </div>
                </>
              )}
            </section>
          </div>
        )}

        {error && (
          <p role="alert" className="text-red-700 bg-red-50 border border-red-200 p-3 rounded mt-4">
            {error}
          </p>
        )}

        <footer className="text-xs text-slate-500 mt-8">
          Hack Garanhuns Tech 2026 · Desafio 3 · Document AI Factory & Conciliação
        </footer>
      </div>
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
