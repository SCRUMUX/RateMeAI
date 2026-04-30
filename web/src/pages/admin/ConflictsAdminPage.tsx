import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import * as api from '../../lib/api';
import type { AdminConflictReport } from '../../lib/api';
import { ApiError } from '../../lib/api';

export default function ConflictsAdminPage() {
  const [report, setReport] = useState<AdminConflictReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchReport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listAdminStyleConflicts();
      setReport(data);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setError('Доступ запрещён. Этот аккаунт не в ADMIN_USER_IDS.');
      } else if (e instanceof ApiError && e.status === 401) {
        setError('Сессия не активна. Войдите в основной кабинет и вернитесь.');
      } else {
        setError(e instanceof Error ? e.message : 'Не удалось загрузить отчёт');
      }
      setReport(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchReport();
  }, [fetchReport]);

  const empty =
    report &&
    report.duplicate_labels.length === 0 &&
    report.similar_labels.length === 0 &&
    report.duplicate_ids.length === 0;

  return (
    <div className="min-h-screen bg-[#0E1216] text-[#E6EEF8] p-6">
      <header className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold">Style Naming Conflicts</h1>
          <p className="text-sm text-[#8b95a3] mt-1">
            Отчёт о дубликатах <code>display_label</code>, похожих названиях
            (Levenshtein ≤ 2) и дублирующихся <code>id</code>.
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            to="/admin/styles"
            className="px-4 py-2 rounded-lg border border-white/10 hover:bg-white/5 text-sm"
          >
            ← Back to catalog
          </Link>
          <button
            onClick={fetchReport}
            className="px-4 py-2 rounded-lg border border-white/10 hover:bg-white/5"
          >
            Refresh
          </button>
        </div>
      </header>

      {error && (
        <div className="mb-4 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-300">
          {error}
        </div>
      )}

      {loading && (
        <div className="text-sm text-[#8b95a3]">Загружаем отчёт…</div>
      )}

      {empty && (
        <div className="px-4 py-3 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-sm text-emerald-200">
          Каталог чист — ни одного конфликта названий или дублирующего id.
        </div>
      )}

      {report && !empty && (
        <div className="space-y-6">
          <Section title={`Duplicate labels (${report.duplicate_labels.length})`}>
            {report.duplicate_labels.length === 0 ? (
              <p className="text-sm text-[#8b95a3]">—</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-white/5 text-[#8b95a3]">
                  <tr>
                    <th className="text-left px-3 py-2 font-medium">label (normalised)</th>
                    <th className="text-left px-3 py-2 font-medium">styles</th>
                  </tr>
                </thead>
                <tbody>
                  {report.duplicate_labels.map((dup) => (
                    <tr key={dup.normalised} className="border-t border-white/5 align-top">
                      <td className="px-3 py-2">
                        <div className="font-medium">{dup.label}</div>
                        <div className="text-xs text-[#8b95a3] font-mono">{dup.normalised}</div>
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex flex-wrap gap-2">
                          {dup.ids.map((sid) => (
                            <Link
                              key={sid}
                              to={`/admin/styles?focus=${encodeURIComponent(sid)}`}
                              className="px-2 py-1 rounded bg-white/5 border border-white/10 font-mono text-xs hover:bg-white/10"
                            >
                              {sid}
                            </Link>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Section>

          <Section title={`Similar labels (${report.similar_labels.length})`}>
            {report.similar_labels.length === 0 ? (
              <p className="text-sm text-[#8b95a3]">—</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-white/5 text-[#8b95a3]">
                  <tr>
                    <th className="text-left px-3 py-2 font-medium">style A</th>
                    <th className="text-left px-3 py-2 font-medium">style B</th>
                    <th className="text-left px-3 py-2 font-medium">distance</th>
                  </tr>
                </thead>
                <tbody>
                  {report.similar_labels.map((pair) => (
                    <tr
                      key={`${pair.id_a}|${pair.id_b}`}
                      className="border-t border-white/5"
                    >
                      <td className="px-3 py-2">
                        <Link
                          to={`/admin/styles?focus=${encodeURIComponent(pair.id_a)}`}
                          className="font-mono text-xs hover:underline"
                        >
                          {pair.id_a}
                        </Link>
                        <div className="text-[#8b95a3]">{pair.label_a}</div>
                      </td>
                      <td className="px-3 py-2">
                        <Link
                          to={`/admin/styles?focus=${encodeURIComponent(pair.id_b)}`}
                          className="font-mono text-xs hover:underline"
                        >
                          {pair.id_b}
                        </Link>
                        <div className="text-[#8b95a3]">{pair.label_b}</div>
                      </td>
                      <td className="px-3 py-2 text-amber-300">{pair.distance}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Section>

          <Section title={`Duplicate IDs (${report.duplicate_ids.length})`}>
            {report.duplicate_ids.length === 0 ? (
              <p className="text-sm text-[#8b95a3]">—</p>
            ) : (
              <ul className="space-y-1">
                {report.duplicate_ids.map((id) => (
                  <li
                    key={id}
                    className="font-mono text-sm px-3 py-1.5 rounded bg-red-500/10 border border-red-500/30 text-red-300"
                  >
                    {id}
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>
      )}
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-white/10 overflow-hidden">
      <h2 className="px-4 py-2 bg-white/5 text-sm font-medium uppercase tracking-wide text-[#8b95a3]">
        {title}
      </h2>
      <div className="p-3">{children}</div>
    </section>
  );
}
