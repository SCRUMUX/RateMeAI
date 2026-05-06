import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import * as api from '../../lib/api';
import type { AdminConflictReport } from '../../lib/api';
import { ApiError } from '../../lib/api';
import AdminLayout from './AdminLayout';

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
    <AdminLayout>
      <div className="flex flex-col tablet:flex-row tablet:items-start tablet:justify-between gap-[var(--space-16)] mb-[var(--space-32)]">
        <div className="flex flex-col gap-[var(--space-6)]">
          <h2 className="text-[24px] leading-[32px] font-semibold text-white">
            Конфликты названий
          </h2>
          <p className="text-[13px] leading-[18px] text-[#8b95a3]">
            Дубликаты <code className="text-[#a8b1bf]">display_label</code>, похожие
            названия (Levenshtein ≤ 2) и дублирующиеся <code className="text-[#a8b1bf]">id</code>.
          </p>
        </div>
        <div>
          <button
            onClick={fetchReport}
            className="px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] border border-white/10 hover:bg-white/5 text-[13px] leading-[18px]"
          >
            Обновить отчёт
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-[var(--space-16)] px-[var(--space-16)] py-[var(--space-12)] bg-red-500/10 border border-red-500/30 rounded-[var(--radius-12)] text-[13px] leading-[18px] text-red-300">
          {error}
        </div>
      )}

      {loading && (
        <div className="text-[13px] text-[#8b95a3]">Загружаем отчёт…</div>
      )}

      {empty && (
        <div className="px-[var(--space-16)] py-[var(--space-12)] bg-emerald-500/10 border border-emerald-500/30 rounded-[var(--radius-12)] text-[13px] leading-[18px] text-emerald-200">
          Каталог чист — ни одного конфликта названий или дублирующего id.
        </div>
      )}

      {report && !empty && (
        <div className="space-y-[var(--space-24)]">
          <Section title={`Дубликаты названий (${report.duplicate_labels.length})`}>
            {report.duplicate_labels.length === 0 ? (
              <p className="text-[13px] text-[#8b95a3]">—</p>
            ) : (
              <table className="w-full text-[13px] leading-[18px]">
                <thead className="bg-white/[0.04] text-[#8b95a3] border-b border-white/10">
                  <tr>
                    <th className="text-left px-[var(--space-16)] py-[var(--space-12)] font-medium uppercase tracking-wide text-[11px]">Название (нормализованное)</th>
                    <th className="text-left px-[var(--space-16)] py-[var(--space-12)] font-medium uppercase tracking-wide text-[11px]">Стили</th>
                  </tr>
                </thead>
                <tbody>
                  {report.duplicate_labels.map((dup) => (
                    <tr key={dup.normalised} className="border-t border-white/5 align-top">
                      <td className="px-[var(--space-16)] py-[var(--space-12)]">
                        <div className="font-medium">{dup.label}</div>
                        <div className="text-[12px] text-[#8b95a3] font-mono">{dup.normalised}</div>
                      </td>
                      <td className="px-[var(--space-16)] py-[var(--space-12)]">
                        <div className="flex flex-wrap gap-[var(--space-8)]">
                          {dup.ids.map((sid) => (
                            <Link
                              key={sid}
                              to={`/admin/styles?focus=${encodeURIComponent(sid)}`}
                              className="px-[var(--space-8)] py-[var(--space-4)] rounded bg-white/5 border border-white/10 font-mono text-[12px] hover:bg-white/10"
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

          <Section title={`Похожие названия (${report.similar_labels.length})`}>
            {report.similar_labels.length === 0 ? (
              <p className="text-[13px] text-[#8b95a3]">—</p>
            ) : (
              <table className="w-full text-[13px] leading-[18px]">
                <thead className="bg-white/[0.04] text-[#8b95a3] border-b border-white/10">
                  <tr>
                    <th className="text-left px-[var(--space-16)] py-[var(--space-12)] font-medium uppercase tracking-wide text-[11px]">Стиль A</th>
                    <th className="text-left px-[var(--space-16)] py-[var(--space-12)] font-medium uppercase tracking-wide text-[11px]">Стиль B</th>
                    <th className="text-left px-[var(--space-16)] py-[var(--space-12)] font-medium uppercase tracking-wide text-[11px]">Дистанция</th>
                  </tr>
                </thead>
                <tbody>
                  {report.similar_labels.map((pair) => (
                    <tr
                      key={`${pair.id_a}|${pair.id_b}`}
                      className="border-t border-white/5"
                    >
                      <td className="px-[var(--space-16)] py-[var(--space-12)]">
                        <Link
                          to={`/admin/styles?focus=${encodeURIComponent(pair.id_a)}`}
                          className="font-mono text-[12px] hover:underline"
                        >
                          {pair.id_a}
                        </Link>
                        <div className="text-[#8b95a3]">{pair.label_a}</div>
                      </td>
                      <td className="px-[var(--space-16)] py-[var(--space-12)]">
                        <Link
                          to={`/admin/styles?focus=${encodeURIComponent(pair.id_b)}`}
                          className="font-mono text-[12px] hover:underline"
                        >
                          {pair.id_b}
                        </Link>
                        <div className="text-[#8b95a3]">{pair.label_b}</div>
                      </td>
                      <td className="px-[var(--space-16)] py-[var(--space-12)] text-amber-300">{pair.distance}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Section>

          <Section title={`Дубликаты ID (${report.duplicate_ids.length})`}>
            {report.duplicate_ids.length === 0 ? (
              <p className="text-[13px] text-[#8b95a3]">—</p>
            ) : (
              <ul className="space-y-[var(--space-4)]">
                {report.duplicate_ids.map((id) => (
                  <li
                    key={id}
                    className="font-mono text-[13px] px-[var(--space-12)] py-[var(--space-8)] rounded bg-red-500/10 border border-red-500/30 text-red-300"
                  >
                    {id}
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>
      )}
    </AdminLayout>
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
    <section className="rounded-[var(--radius-12)] border border-white/10 bg-white/[0.02] overflow-hidden">
      <h3 className="px-[var(--space-16)] py-[var(--space-12)] bg-white/[0.04] text-[12px] font-medium uppercase tracking-wide text-[#8b95a3] border-b border-white/10">
        {title}
      </h3>
      <div className="p-[var(--space-16)]">{children}</div>
    </section>
  );
}
