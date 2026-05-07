import { useCallback, useEffect, useMemo, useState } from 'react';
import * as api from '../../lib/api';
import { ApiError } from '../../lib/api';
import type {
  AdminUserDetailResponse,
  AdminUserSummary,
  AdminUserTransaction,
} from '../../lib/api';
import AdminLayout from './AdminLayout';

type ActionMode = null | 'grant' | 'debit' | 'refund';

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString('ru-RU', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function formatRelative(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso).getTime();
  if (!Number.isFinite(d)) return '—';
  const diff = Date.now() - d;
  const day = 1000 * 60 * 60 * 24;
  const hours = Math.floor(diff / (1000 * 60 * 60));
  if (hours < 1) return 'меньше часа назад';
  if (hours < 24) return `${hours} ч. назад`;
  const days = Math.floor(diff / day);
  if (days < 30) return `${days} дн. назад`;
  const months = Math.floor(days / 30);
  return `${months} мес. назад`;
}

function txTypeLabel(type: string): string {
  const map: Record<string, string> = {
    purchase: 'Покупка',
    admin_grant: 'Начисление (admin)',
    admin_debit: 'Списание (admin)',
    admin_refund: 'Возврат (admin)',
    refund_failed_task: 'Возврат: ошибка задачи',
    refund_no_image: 'Возврат: нет результата',
    refund_stuck_task: 'Возврат: зависшая задача',
    refund_stuck_edge_task: 'Возврат: edge-задача',
    debit: 'Списание (генерация)',
    grant: 'Начисление (бонус)',
  };
  return map[type] ?? type;
}

function describeProviders(user: AdminUserSummary): string {
  if (!user.providers.length && user.telegram_id) return 'telegram (legacy)';
  if (!user.providers.length) return '—';
  return user.providers.join(', ');
}

function describeContact(user: AdminUserSummary): string {
  if (user.primary_email) return user.primary_email;
  if (user.username) return `@${user.username}`;
  if (user.telegram_id) return `tg:${user.telegram_id}`;
  return user.id.slice(0, 8) + '…';
}

interface ConfirmActionState {
  mode: ActionMode;
  amount: string;
  reason: string;
  paymentId: string;
}

const EMPTY_ACTION: ConfirmActionState = {
  mode: null,
  amount: '',
  reason: '',
  paymentId: '',
};

export default function UsersAdminPage() {
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [limit, setLimit] = useState(50);
  const [users, setUsers] = useState<AdminUserSummary[] | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  const [activeUserId, setActiveUserId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AdminUserDetailResponse | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [action, setAction] = useState<ConfirmActionState>(EMPTY_ACTION);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Block / unblock / delete have their own busy flag and inline error.
  // Block uses a small inline form (textarea for reason). Delete asks
  // the admin to retype the user-id to prevent fat-finger destruction.
  const [blockBusy, setBlockBusy] = useState(false);
  const [blockReason, setBlockReason] = useState('');
  const [blockOpen, setBlockOpen] = useState(false);
  const [moderationError, setModerationError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState('');
  const [deleteBusy, setDeleteBusy] = useState(false);

  const fetchUsers = useCallback(async (q: string, lim: number) => {
    setLoadingList(true);
    setListError(null);
    try {
      const res = await api.listAdminUsers({ q, limit: lim });
      setUsers(res.items);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setListError('Доступ запрещён. Аккаунт не в ADMIN_USER_IDS / ADMIN_EMAILS.');
      } else if (e instanceof ApiError && e.status === 401) {
        setListError('Сессия не активна. Войдите в основной кабинет и вернитесь.');
      } else {
        setListError(e instanceof Error ? e.message : 'Не удалось загрузить список');
      }
      setUsers([]);
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    void fetchUsers(submittedQuery, limit);
  }, [fetchUsers, submittedQuery, limit]);

  const fetchDetail = useCallback(async (userId: string) => {
    setLoadingDetail(true);
    setDetailError(null);
    try {
      const res = await api.getAdminUser(userId);
      setDetail(res);
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : 'Не удалось загрузить пользователя');
      setDetail(null);
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    if (!activeUserId) {
      setDetail(null);
      setAction(EMPTY_ACTION);
      setActionError(null);
      setBlockOpen(false);
      setBlockReason('');
      setDeleteOpen(false);
      setDeleteConfirmId('');
      setModerationError(null);
      return;
    }
    void fetchDetail(activeUserId);
  }, [activeUserId, fetchDetail]);

  const handleSearch = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      setSubmittedQuery(query.trim());
    },
    [query],
  );

  const closeDrawer = useCallback(() => {
    setActiveUserId(null);
  }, []);

  const startAction = useCallback((mode: ActionMode) => {
    setAction({ ...EMPTY_ACTION, mode });
    setActionError(null);
  }, []);

  const cancelAction = useCallback(() => {
    setAction(EMPTY_ACTION);
    setActionError(null);
  }, []);

  const submitAction = useCallback(async () => {
    if (!detail || !action.mode) return;
    const userId = detail.user.id;
    const amountNum = Number(action.amount);
    if (!Number.isFinite(amountNum) || amountNum <= 0) {
      setActionError('Введите положительное целое число.');
      return;
    }
    if (action.reason.trim().length < 3) {
      setActionError('Поле «причина / комментарий» обязательно (минимум 3 символа).');
      return;
    }
    setActionBusy(true);
    setActionError(null);
    try {
      if (action.mode === 'grant') {
        await api.adminAdjustCredits(userId, {
          amount: Math.trunc(amountNum),
          reason: action.reason.trim(),
        });
      } else if (action.mode === 'debit') {
        await api.adminAdjustCredits(userId, {
          amount: -Math.trunc(amountNum),
          reason: action.reason.trim(),
        });
      } else if (action.mode === 'refund') {
        if (!window.confirm(
          `Подтвердить возврат ${Math.trunc(amountNum)} кредитов? ` +
          `Реальные деньги через ЮKassa/Stripe нужно вернуть отдельно.`,
        )) {
          setActionBusy(false);
          return;
        }
        await api.adminRefund(userId, {
          credits: Math.trunc(amountNum),
          payment_id: action.paymentId.trim() || undefined,
          note: action.reason.trim(),
        });
      }
      setAction(EMPTY_ACTION);
      await fetchDetail(userId);
      void fetchUsers(submittedQuery, limit);
    } catch (e) {
      if (e instanceof ApiError) {
        try {
          const parsed = JSON.parse(e.body);
          if (
            parsed?.detail?.code === 'insufficient_credits' ||
            parsed?.code === 'insufficient_credits'
          ) {
            const balance =
              parsed?.detail?.balance ?? parsed?.balance ?? '?';
            setActionError(
              `Недостаточно кредитов. Текущий баланс: ${balance}.`,
            );
            return;
          }
        } catch {
          /* fall through to generic message */
        }
      }
      setActionError(e instanceof Error ? e.message : 'Не удалось выполнить операцию');
    } finally {
      setActionBusy(false);
    }
  }, [detail, action, fetchDetail, fetchUsers, submittedQuery, limit]);

  const handleBlock = useCallback(async () => {
    if (!detail) return;
    const reason = blockReason.trim();
    if (reason.length < 3) {
      setModerationError('Укажите причину блокировки (мин. 3 символа).');
      return;
    }
    setBlockBusy(true);
    setModerationError(null);
    try {
      await api.adminBlockUser(detail.user.id, reason);
      setBlockOpen(false);
      setBlockReason('');
      await fetchDetail(detail.user.id);
      void fetchUsers(submittedQuery, limit);
    } catch (e) {
      setModerationError(e instanceof Error ? e.message : 'Не удалось заблокировать');
    } finally {
      setBlockBusy(false);
    }
  }, [detail, blockReason, fetchDetail, fetchUsers, submittedQuery, limit]);

  const handleUnblock = useCallback(async () => {
    if (!detail) return;
    setBlockBusy(true);
    setModerationError(null);
    try {
      await api.adminUnblockUser(detail.user.id);
      await fetchDetail(detail.user.id);
      void fetchUsers(submittedQuery, limit);
    } catch (e) {
      setModerationError(e instanceof Error ? e.message : 'Не удалось разблокировать');
    } finally {
      setBlockBusy(false);
    }
  }, [detail, fetchDetail, fetchUsers, submittedQuery, limit]);

  const handleDelete = useCallback(async () => {
    if (!detail) return;
    if (deleteConfirmId.trim() !== detail.user.id) {
      setModerationError('UUID не совпадает — введите id пользователя точно как в карточке.');
      return;
    }
    setDeleteBusy(true);
    setModerationError(null);
    try {
      await api.adminDeleteUser(detail.user.id);
      setDeleteOpen(false);
      setDeleteConfirmId('');
      setActiveUserId(null);
      void fetchUsers(submittedQuery, limit);
    } catch (e) {
      setModerationError(e instanceof Error ? e.message : 'Не удалось удалить пользователя');
    } finally {
      setDeleteBusy(false);
    }
  }, [detail, deleteConfirmId, fetchUsers, submittedQuery, limit]);

  const totalCount = users?.length ?? 0;

  return (
    <AdminLayout>
      <div className="flex flex-col tablet:flex-row tablet:items-end tablet:justify-between gap-[var(--space-16)] mb-[var(--space-32)]">
        <div className="flex flex-col gap-[var(--space-6)]">
          <h2 className="text-[24px] leading-[32px] font-semibold text-white">
            Пользователи
          </h2>
          <p className="text-[13px] leading-[18px] text-[#8b95a3]">
            Поиск, баланс кредитов, история транзакций и генераций. Фото
            намеренно не отображаются (privacy-by-design).
          </p>
        </div>
        <form onSubmit={handleSearch} className="flex flex-wrap items-center gap-[var(--space-8)]">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="email, telegram_id или @username"
            className="w-[260px] px-[var(--space-12)] h-[36px] rounded-[var(--radius-pill)] border border-white/10 bg-transparent text-[13px] leading-[18px] focus:outline-none focus:border-blue-400"
          />
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="px-[var(--space-12)] h-[36px] rounded-[var(--radius-pill)] border border-white/10 bg-transparent text-[13px] leading-[18px] focus:outline-none focus:border-blue-400"
          >
            <option value={20}>20</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={200}>200</option>
          </select>
          <button
            type="submit"
            className="px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] bg-blue-600 hover:bg-blue-500 text-[13px] leading-[18px] font-medium"
            disabled={loadingList}
          >
            Найти
          </button>
          <button
            type="button"
            onClick={() => fetchUsers(submittedQuery, limit)}
            className="px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] border border-white/10 hover:bg-white/5 text-[13px] leading-[18px]"
            disabled={loadingList}
          >
            Обновить
          </button>
        </form>
      </div>

      {listError && (
        <div className="mb-[var(--space-16)] px-[var(--space-16)] py-[var(--space-12)] bg-red-500/10 border border-red-500/30 rounded-[var(--radius-12)] text-[13px] leading-[18px] text-red-300">
          {listError}
        </div>
      )}

      <div className="rounded-[var(--radius-12)] border border-white/10 bg-white/[0.02] overflow-hidden">
        <div className="flex items-baseline justify-between px-[var(--space-16)] py-[var(--space-12)] border-b border-white/5">
          <span className="text-[11px] text-[#8b95a3] uppercase tracking-wide">
            {loadingList ? 'Загрузка…' : `Найдено: ${totalCount}`}
          </span>
          {submittedQuery && (
            <span className="text-[11px] text-[#5a6470]">
              запрос: <code className="text-[#a8b1bf]">{submittedQuery}</code>
            </span>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[13px] leading-[18px]">
            <thead className="bg-white/[0.04] text-[11px] uppercase tracking-wide text-[#8b95a3]">
              <tr>
                <th className="text-left px-[var(--space-16)] py-[var(--space-12)]">Контакт</th>
                <th className="text-left px-[var(--space-16)] py-[var(--space-12)]">Провайдеры</th>
                <th className="text-right px-[var(--space-16)] py-[var(--space-12)]">Кредиты</th>
                <th className="text-right px-[var(--space-16)] py-[var(--space-12)]">Генераций</th>
                <th className="text-left px-[var(--space-16)] py-[var(--space-12)]">Создан</th>
                <th className="text-left px-[var(--space-16)] py-[var(--space-12)]">Активен</th>
                <th className="text-left px-[var(--space-16)] py-[var(--space-12)]">Статус</th>
              </tr>
            </thead>
            <tbody>
              {(users ?? []).map((u) => (
                <tr
                  key={u.id}
                  onClick={() => setActiveUserId(u.id)}
                  className="border-t border-white/5 hover:bg-white/[0.04] cursor-pointer"
                >
                  <td className="px-[var(--space-16)] py-[var(--space-12)] text-white">
                    <div className="flex flex-col gap-[2px]">
                      <span>{describeContact(u)}</span>
                      <span className="text-[11px] text-[#5a6470]">
                        {u.id.slice(0, 8)}…
                      </span>
                    </div>
                  </td>
                  <td className="px-[var(--space-16)] py-[var(--space-12)] text-[#a8b1bf]">
                    {describeProviders(u)}
                  </td>
                  <td className="px-[var(--space-16)] py-[var(--space-12)] text-right font-mono text-white">
                    {u.image_credits}
                  </td>
                  <td className="px-[var(--space-16)] py-[var(--space-12)] text-right font-mono text-[#a8b1bf]">
                    {u.total_generations}
                  </td>
                  <td className="px-[var(--space-16)] py-[var(--space-12)] text-[#8b95a3]">
                    {formatDate(u.created_at)}
                  </td>
                  <td className="px-[var(--space-16)] py-[var(--space-12)] text-[#8b95a3]">
                    {formatRelative(u.last_task_at ?? u.last_seen)}
                  </td>
                  <td className="px-[var(--space-16)] py-[var(--space-12)]">
                    {u.blocked_at ? (
                      <span
                        className="inline-flex items-center gap-[4px] px-[8px] h-[22px] rounded-full bg-red-500/15 border border-red-500/30 text-[11px] leading-[14px] text-red-300 font-medium"
                        title={u.blocked_reason ?? ''}
                      >
                        🔒 Заблокирован
                      </span>
                    ) : (
                      <span className="text-[12px] text-[#5a6470]">активен</span>
                    )}
                  </td>
                </tr>
              ))}
              {!loadingList && users && users.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-[var(--space-16)] py-[var(--space-32)] text-center text-[#5a6470]">
                    Никого не нашли. Попробуйте другой запрос.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {activeUserId && (
        <UserDrawer
          userId={activeUserId}
          detail={detail}
          loading={loadingDetail}
          error={detailError}
          action={action}
          actionBusy={actionBusy}
          actionError={actionError}
          onClose={closeDrawer}
          onStartAction={startAction}
          onCancelAction={cancelAction}
          onChangeAction={setAction}
          onSubmitAction={submitAction}
          blockOpen={blockOpen}
          blockReason={blockReason}
          blockBusy={blockBusy}
          deleteOpen={deleteOpen}
          deleteConfirmId={deleteConfirmId}
          deleteBusy={deleteBusy}
          moderationError={moderationError}
          onOpenBlock={() => {
            setBlockOpen(true);
            setBlockReason('');
            setModerationError(null);
          }}
          onCancelBlock={() => {
            setBlockOpen(false);
            setBlockReason('');
            setModerationError(null);
          }}
          onChangeBlockReason={setBlockReason}
          onSubmitBlock={handleBlock}
          onSubmitUnblock={handleUnblock}
          onOpenDelete={() => {
            setDeleteOpen(true);
            setDeleteConfirmId('');
            setModerationError(null);
          }}
          onCancelDelete={() => {
            setDeleteOpen(false);
            setDeleteConfirmId('');
            setModerationError(null);
          }}
          onChangeDeleteConfirmId={setDeleteConfirmId}
          onSubmitDelete={handleDelete}
        />
      )}
    </AdminLayout>
  );
}

interface UserDrawerProps {
  userId: string;
  detail: AdminUserDetailResponse | null;
  loading: boolean;
  error: string | null;
  action: ConfirmActionState;
  actionBusy: boolean;
  actionError: string | null;
  onClose: () => void;
  onStartAction: (mode: ActionMode) => void;
  onCancelAction: () => void;
  onChangeAction: (next: ConfirmActionState) => void;
  onSubmitAction: () => void;
  blockOpen: boolean;
  blockReason: string;
  blockBusy: boolean;
  deleteOpen: boolean;
  deleteConfirmId: string;
  deleteBusy: boolean;
  moderationError: string | null;
  onOpenBlock: () => void;
  onCancelBlock: () => void;
  onChangeBlockReason: (next: string) => void;
  onSubmitBlock: () => void;
  onSubmitUnblock: () => void;
  onOpenDelete: () => void;
  onCancelDelete: () => void;
  onChangeDeleteConfirmId: (next: string) => void;
  onSubmitDelete: () => void;
}

function UserDrawer({
  userId,
  detail,
  loading,
  error,
  action,
  actionBusy,
  actionError,
  onClose,
  onStartAction,
  onCancelAction,
  onChangeAction,
  onSubmitAction,
  blockOpen,
  blockReason,
  blockBusy,
  deleteOpen,
  deleteConfirmId,
  deleteBusy,
  moderationError,
  onOpenBlock,
  onCancelBlock,
  onChangeBlockReason,
  onSubmitBlock,
  onSubmitUnblock,
  onOpenDelete,
  onCancelDelete,
  onChangeDeleteConfirmId,
  onSubmitDelete,
}: UserDrawerProps) {
  const summary = detail?.user;
  const [tab, setTab] = useState<'transactions' | 'tasks'>('transactions');

  const transactions: AdminUserTransaction[] = useMemo(
    () => detail?.transactions ?? [],
    [detail],
  );

  return (
    <div className="fixed inset-0 z-40 flex">
      <div
        className="flex-1 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        aria-label="Закрыть карточку пользователя"
      />
      <aside className="w-full max-w-[640px] h-full overflow-y-auto bg-[#0E1216] border-l border-white/10 px-[var(--space-24)] py-[var(--space-24)]">
        <div className="flex items-start justify-between gap-[var(--space-12)] mb-[var(--space-16)]">
          <div className="flex flex-col gap-[var(--space-4)] min-w-0">
            <span className="text-[11px] uppercase tracking-[0.18em] text-[#5a6470]">Пользователь</span>
            <h3 className="text-[18px] leading-[24px] font-semibold text-white truncate">
              {summary ? describeContact(summary) : userId.slice(0, 8) + '…'}
            </h3>
            <span className="text-[12px] text-[#5a6470] font-mono break-all">{userId}</span>
          </div>
          <button
            onClick={onClose}
            className="px-[var(--space-12)] h-[32px] rounded-[var(--radius-pill)] border border-white/10 hover:bg-white/5 text-[12px] leading-[16px]"
          >
            Закрыть
          </button>
        </div>

        {loading && (
          <div className="text-[13px] text-[#8b95a3] py-[var(--space-32)] text-center">
            Загрузка пользователя…
          </div>
        )}
        {error && (
          <div className="px-[var(--space-16)] py-[var(--space-12)] bg-red-500/10 border border-red-500/30 rounded-[var(--radius-12)] text-[13px] text-red-300 mb-[var(--space-16)]">
            {error}
          </div>
        )}

        {summary && (
          <>
            <div className="grid grid-cols-2 gap-[var(--space-12)] mb-[var(--space-24)]">
              <Stat label="Кредитов сейчас" value={String(summary.image_credits)} accent />
              <Stat label="Всего генераций" value={String(summary.total_generations)} />
              <Stat
                label="Последняя задача"
                value={formatRelative(summary.last_task_at)}
              />
              <Stat
                label="Последняя активность"
                value={formatRelative(summary.last_seen ?? summary.last_task_at)}
              />
              <Stat label="Создан" value={formatDate(summary.created_at)} />
              <Stat label="Премиум" value={summary.is_premium ? 'да' : 'нет'} />
            </div>

            <section className="mb-[var(--space-24)]">
              <h4 className="text-[13px] uppercase tracking-wide text-[#8b95a3] mb-[var(--space-8)]">
                Контакты
              </h4>
              <div className="rounded-[var(--radius-12)] border border-white/10 bg-white/[0.02] p-[var(--space-16)]">
                <ContactRow label="Email" values={summary.emails} />
                <ContactRow
                  label="Telegram ID"
                  values={summary.telegram_id ? [String(summary.telegram_id)] : []}
                />
                <ContactRow
                  label="Username"
                  values={summary.username ? [`@${summary.username}`] : []}
                />
                <ContactRow label="OAuth" values={summary.providers} />
              </div>
            </section>

            {summary.blocked_at && (
              <div className="mb-[var(--space-16)] rounded-[var(--radius-12)] border border-red-500/30 bg-red-500/10 p-[var(--space-16)]">
                <div className="flex items-center gap-[var(--space-8)] mb-[var(--space-8)]">
                  <span className="text-[12px] uppercase tracking-wide text-red-300 font-semibold">
                    🔒 Аккаунт заблокирован
                  </span>
                  <span className="text-[11px] text-[#8b95a3]">
                    с {formatDate(summary.blocked_at)}
                  </span>
                </div>
                {summary.blocked_reason && (
                  <p className="text-[12px] leading-[16px] text-[#a8b1bf] italic">
                    Причина: {summary.blocked_reason}
                  </p>
                )}
              </div>
            )}

            <section className="mb-[var(--space-24)]">
              <h4 className="text-[13px] uppercase tracking-wide text-[#8b95a3] mb-[var(--space-8)]">
                Действия
              </h4>
              <div className="flex flex-wrap gap-[var(--space-8)]">
                <button
                  onClick={() => onStartAction('grant')}
                  className="px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] bg-emerald-500/15 border border-emerald-400/30 hover:bg-emerald-500/25 text-[13px] leading-[18px] text-emerald-200"
                >
                  + Начислить кредиты
                </button>
                <button
                  onClick={() => onStartAction('debit')}
                  className="px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] bg-amber-500/10 border border-amber-400/30 hover:bg-amber-500/20 text-[13px] leading-[18px] text-amber-200"
                >
                  − Списать кредиты
                </button>
                <button
                  onClick={() => onStartAction('refund')}
                  className="px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] bg-blue-500/15 border border-blue-400/30 hover:bg-blue-500/25 text-[13px] leading-[18px] text-blue-200"
                >
                  Подтвердить возврат
                </button>
              </div>
              {action.mode && (
                <ActionForm
                  action={action}
                  busy={actionBusy}
                  error={actionError}
                  onChange={onChangeAction}
                  onSubmit={onSubmitAction}
                  onCancel={onCancelAction}
                />
              )}
            </section>

            <section className="mb-[var(--space-24)]">
              <h4 className="text-[13px] uppercase tracking-wide text-[#8b95a3] mb-[var(--space-8)]">
                Модерация
              </h4>
              <div className="flex flex-wrap gap-[var(--space-8)]">
                {summary.blocked_at ? (
                  <button
                    onClick={onSubmitUnblock}
                    disabled={blockBusy}
                    className="px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] bg-emerald-500/15 border border-emerald-400/30 hover:bg-emerald-500/25 disabled:opacity-50 text-[13px] leading-[18px] text-emerald-200"
                  >
                    {blockBusy ? 'Разблокируем…' : 'Разблокировать'}
                  </button>
                ) : (
                  <button
                    onClick={onOpenBlock}
                    className="px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] bg-red-500/10 border border-red-500/30 hover:bg-red-500/20 text-[13px] leading-[18px] text-red-200"
                  >
                    Заблокировать
                  </button>
                )}
                <button
                  onClick={onOpenDelete}
                  className="px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] bg-red-500/15 border border-red-500/40 hover:bg-red-500/25 text-[13px] leading-[18px] text-red-200"
                >
                  Удалить из системы
                </button>
              </div>

              {moderationError && (
                <div className="mt-[var(--space-12)] px-[var(--space-12)] py-[var(--space-8)] bg-red-500/10 border border-red-500/30 rounded-[var(--radius-8)] text-[12px] text-red-300">
                  {moderationError}
                </div>
              )}

              {blockOpen && (
                <div className="mt-[var(--space-12)] rounded-[var(--radius-12)] border border-white/10 bg-white/[0.02] p-[var(--space-16)] flex flex-col gap-[var(--space-12)]">
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] font-semibold text-white">
                      Блокировка пользователя
                    </span>
                    <button
                      onClick={onCancelBlock}
                      className="text-[12px] text-[#5a6470] hover:text-white"
                    >
                      Отмена
                    </button>
                  </div>
                  <label className="flex flex-col gap-[var(--space-4)]">
                    <span className="text-[11px] uppercase tracking-wide text-[#8b95a3]">
                      Причина (показывается пользователю)
                    </span>
                    <textarea
                      value={blockReason}
                      onChange={(e) => onChangeBlockReason(e.target.value)}
                      rows={3}
                      maxLength={500}
                      className="w-full px-[var(--space-12)] py-[var(--space-8)] rounded-[var(--radius-8)] border border-white/10 bg-black/30 text-[13px] leading-[18px] focus:outline-none focus:border-red-400"
                      placeholder="например: нарушение правил сервиса (тикет #...)"
                    />
                  </label>
                  <button
                    onClick={onSubmitBlock}
                    disabled={blockBusy}
                    className={`px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] text-[13px] leading-[18px] font-medium ${
                      blockBusy
                        ? 'bg-white/10 text-[#8b95a3] cursor-not-allowed'
                        : 'bg-red-600 hover:bg-red-500 text-white'
                    }`}
                  >
                    {blockBusy ? 'Блокируем…' : 'Подтвердить блокировку'}
                  </button>
                </div>
              )}

              {deleteOpen && (
                <div className="mt-[var(--space-12)] rounded-[var(--radius-12)] border border-red-500/40 bg-red-500/[0.06] p-[var(--space-16)] flex flex-col gap-[var(--space-12)]">
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] font-semibold text-white">
                      Удаление аккаунта (необратимо)
                    </span>
                    <button
                      onClick={onCancelDelete}
                      className="text-[12px] text-[#5a6470] hover:text-white"
                    >
                      Отмена
                    </button>
                  </div>
                  <p className="text-[12px] leading-[16px] text-[#a8b1bf]">
                    Удалит запись пользователя и все связанные артефакты
                    (генерации, согласия, идентичности, ledger). Восстановить
                    нельзя. Отметка останется только в <code>deletion_log</code>
                    (без PII).
                  </p>
                  <label className="flex flex-col gap-[var(--space-4)]">
                    <span className="text-[11px] uppercase tracking-wide text-[#8b95a3]">
                      Подтвердите: введите UUID пользователя
                    </span>
                    <input
                      value={deleteConfirmId}
                      onChange={(e) => onChangeDeleteConfirmId(e.target.value)}
                      className="w-full px-[var(--space-12)] h-[36px] rounded-[var(--radius-8)] border border-red-500/30 bg-black/30 text-[13px] leading-[18px] font-mono focus:outline-none focus:border-red-400"
                      placeholder={summary.id}
                    />
                  </label>
                  <button
                    onClick={onSubmitDelete}
                    disabled={deleteBusy || deleteConfirmId.trim() !== summary.id}
                    className={`px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] text-[13px] leading-[18px] font-medium ${
                      deleteBusy || deleteConfirmId.trim() !== summary.id
                        ? 'bg-white/10 text-[#8b95a3] cursor-not-allowed'
                        : 'bg-red-700 hover:bg-red-600 text-white'
                    }`}
                  >
                    {deleteBusy ? 'Удаляем…' : 'Удалить навсегда'}
                  </button>
                </div>
              )}
            </section>

            <section className="mb-[var(--space-24)]">
              <div className="flex gap-[var(--space-4)] mb-[var(--space-12)]">
                <TabButton active={tab === 'transactions'} onClick={() => setTab('transactions')}>
                  Транзакции ({transactions.length})
                </TabButton>
                <TabButton active={tab === 'tasks'} onClick={() => setTab('tasks')}>
                  Генерации ({detail?.tasks?.length ?? 0})
                </TabButton>
              </div>

              {tab === 'transactions' && <TransactionsList items={transactions} />}
              {tab === 'tasks' && <TasksList items={detail?.tasks ?? []} />}
            </section>
          </>
        )}
      </aside>
    </div>
  );
}

interface StatProps {
  label: string;
  value: string;
  accent?: boolean;
}

function Stat({ label, value, accent }: StatProps) {
  return (
    <div className="rounded-[var(--radius-12)] border border-white/10 bg-white/[0.02] px-[var(--space-12)] py-[var(--space-12)]">
      <div className="text-[11px] uppercase tracking-wide text-[#8b95a3]">{label}</div>
      <div className={`text-[16px] leading-[20px] font-mono mt-[2px] ${accent ? 'text-emerald-300' : 'text-white'}`}>
        {value}
      </div>
    </div>
  );
}

interface ContactRowProps {
  label: string;
  values: string[];
}

function ContactRow({ label, values }: ContactRowProps) {
  return (
    <div className="flex items-baseline justify-between gap-[var(--space-12)] py-[var(--space-4)]">
      <span className="text-[12px] text-[#5a6470] uppercase tracking-wide">{label}</span>
      <span className="text-[13px] text-white text-right break-all">
        {values.length ? values.join(', ') : '—'}
      </span>
    </div>
  );
}

interface ActionFormProps {
  action: ConfirmActionState;
  busy: boolean;
  error: string | null;
  onChange: (next: ConfirmActionState) => void;
  onSubmit: () => void;
  onCancel: () => void;
}

function ActionForm({ action, busy, error, onChange, onSubmit, onCancel }: ActionFormProps) {
  const titles: Record<NonNullable<ActionMode>, string> = {
    grant: 'Начислить кредиты',
    debit: 'Списать кредиты',
    refund: 'Подтвердить возврат',
  };
  const submitLabels: Record<NonNullable<ActionMode>, string> = {
    grant: 'Начислить',
    debit: 'Списать',
    refund: 'Зафиксировать возврат',
  };
  if (!action.mode) return null;

  return (
    <div className="mt-[var(--space-12)] rounded-[var(--radius-12)] border border-white/10 bg-white/[0.02] p-[var(--space-16)] flex flex-col gap-[var(--space-12)]">
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-semibold text-white">{titles[action.mode]}</span>
        <button
          onClick={onCancel}
          className="text-[12px] text-[#5a6470] hover:text-white"
        >
          Отмена
        </button>
      </div>

      <label className="flex flex-col gap-[var(--space-4)]">
        <span className="text-[11px] uppercase tracking-wide text-[#8b95a3]">
          {action.mode === 'refund' ? 'Кредитов к возврату' : 'Сумма (кредиты)'}
        </span>
        <input
          type="number"
          inputMode="numeric"
          min={1}
          value={action.amount}
          onChange={(e) => onChange({ ...action, amount: e.target.value })}
          className="w-full px-[var(--space-12)] h-[36px] rounded-[var(--radius-8)] border border-white/10 bg-black/30 text-[13px] leading-[18px] focus:outline-none focus:border-blue-400"
          placeholder="100"
        />
      </label>

      {action.mode === 'refund' && (
        <label className="flex flex-col gap-[var(--space-4)]">
          <span className="text-[11px] uppercase tracking-wide text-[#8b95a3]">
            payment_id (опционально)
          </span>
          <input
            value={action.paymentId}
            onChange={(e) => onChange({ ...action, paymentId: e.target.value })}
            className="w-full px-[var(--space-12)] h-[36px] rounded-[var(--radius-8)] border border-white/10 bg-black/30 text-[13px] leading-[18px] focus:outline-none focus:border-blue-400"
            placeholder="pay_abc123 (если известен)"
          />
        </label>
      )}

      <label className="flex flex-col gap-[var(--space-4)]">
        <span className="text-[11px] uppercase tracking-wide text-[#8b95a3]">
          {action.mode === 'refund' ? 'Комментарий / причина возврата' : 'Причина'}
        </span>
        <textarea
          value={action.reason}
          onChange={(e) => onChange({ ...action, reason: e.target.value })}
          rows={3}
          className="w-full px-[var(--space-12)] py-[var(--space-8)] rounded-[var(--radius-8)] border border-white/10 bg-black/30 text-[13px] leading-[18px] focus:outline-none focus:border-blue-400"
          placeholder="например: тикет #123, support refund"
        />
      </label>

      {error && (
        <div className="px-[var(--space-12)] py-[var(--space-8)] bg-red-500/10 border border-red-500/30 rounded-[var(--radius-8)] text-[12px] text-red-300">
          {error}
        </div>
      )}

      <div className="flex gap-[var(--space-8)]">
        <button
          onClick={onSubmit}
          disabled={busy}
          className={`px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] text-[13px] leading-[18px] font-medium ${
            busy ? 'bg-white/10 text-[#8b95a3] cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-500'
          }`}
        >
          {busy ? 'Применяем…' : submitLabels[action.mode]}
        </button>
        <button
          onClick={onCancel}
          disabled={busy}
          className="px-[var(--space-16)] h-[36px] rounded-[var(--radius-pill)] border border-white/10 hover:bg-white/5 text-[13px] leading-[18px]"
        >
          Закрыть форму
        </button>
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-[var(--space-12)] h-[32px] rounded-[var(--radius-pill)] text-[12px] leading-[16px] border ${
        active
          ? 'bg-blue-500/15 border-blue-400/40 text-white'
          : 'border-white/10 text-[#8b95a3] hover:text-white hover:bg-white/5'
      }`}
    >
      {children}
    </button>
  );
}

function TransactionsList({ items }: { items: AdminUserTransaction[] }) {
  if (!items.length) {
    return (
      <div className="text-[13px] text-[#5a6470] py-[var(--space-24)] text-center">
        Транзакций нет.
      </div>
    );
  }
  return (
    <div className="rounded-[var(--radius-12)] border border-white/10 bg-white/[0.02] overflow-hidden">
      <table className="w-full text-[12px] leading-[16px]">
        <thead className="bg-white/[0.04] text-[10px] uppercase tracking-wide text-[#8b95a3]">
          <tr>
            <th className="text-left px-[var(--space-12)] py-[var(--space-8)]">Дата</th>
            <th className="text-left px-[var(--space-12)] py-[var(--space-8)]">Тип</th>
            <th className="text-right px-[var(--space-12)] py-[var(--space-8)]">±</th>
            <th className="text-right px-[var(--space-12)] py-[var(--space-8)]">Баланс</th>
            <th className="text-left px-[var(--space-12)] py-[var(--space-8)]">Причина / payment_id</th>
          </tr>
        </thead>
        <tbody>
          {items.map((tx) => (
            <tr key={tx.id} className="border-t border-white/5">
              <td className="px-[var(--space-12)] py-[var(--space-8)] text-[#a8b1bf]">
                {formatDate(tx.created_at)}
              </td>
              <td className="px-[var(--space-12)] py-[var(--space-8)] text-white">
                {txTypeLabel(tx.tx_type)}
              </td>
              <td
                className={`px-[var(--space-12)] py-[var(--space-8)] text-right font-mono ${
                  tx.amount > 0 ? 'text-emerald-300' : 'text-amber-300'
                }`}
              >
                {tx.amount > 0 ? `+${tx.amount}` : tx.amount}
              </td>
              <td className="px-[var(--space-12)] py-[var(--space-8)] text-right font-mono text-[#a8b1bf]">
                {tx.balance_after}
              </td>
              <td className="px-[var(--space-12)] py-[var(--space-8)] text-[#8b95a3] break-all">
                {tx.payment_id ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TasksList({
  items,
}: {
  items: { id: string; mode: string; status: string; created_at: string | null; completed_at: string | null; error_message: string | null }[];
}) {
  if (!items.length) {
    return (
      <div className="text-[13px] text-[#5a6470] py-[var(--space-24)] text-center">
        Задач нет.
      </div>
    );
  }
  return (
    <div className="rounded-[var(--radius-12)] border border-white/10 bg-white/[0.02] overflow-hidden">
      <table className="w-full text-[12px] leading-[16px]">
        <thead className="bg-white/[0.04] text-[10px] uppercase tracking-wide text-[#8b95a3]">
          <tr>
            <th className="text-left px-[var(--space-12)] py-[var(--space-8)]">Создано</th>
            <th className="text-left px-[var(--space-12)] py-[var(--space-8)]">Режим</th>
            <th className="text-left px-[var(--space-12)] py-[var(--space-8)]">Статус</th>
            <th className="text-left px-[var(--space-12)] py-[var(--space-8)]">Ошибка</th>
          </tr>
        </thead>
        <tbody>
          {items.map((t) => (
            <tr key={t.id} className="border-t border-white/5">
              <td className="px-[var(--space-12)] py-[var(--space-8)] text-[#a8b1bf]">
                {formatDate(t.created_at)}
              </td>
              <td className="px-[var(--space-12)] py-[var(--space-8)] text-white">{t.mode}</td>
              <td className="px-[var(--space-12)] py-[var(--space-8)] text-[#a8b1bf]">{t.status}</td>
              <td className="px-[var(--space-12)] py-[var(--space-8)] text-[#8b95a3] break-all">
                {t.error_message ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
