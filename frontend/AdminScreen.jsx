import React, { useState, useEffect, useCallback } from 'react';
import {
  Users, Layers, ListOrdered, Ticket, ScrollText, CheckCircle,
  Ban, Trash2, Copy, HardDrive, Cpu, ShieldAlert,
} from 'lucide-react';
import { formatBytes, formatWhen } from './format.js';

// --- small shared pieces -----------------------------------------------------------

// A usage bar: the value against its limit. A quota the user cannot see is
// experienced as a bug - showing the limit turns a refusal into information
// (plan A7).
const UsageBar = ({ label, value, limit, formatValue, hint }) => {
  const unknown = value === null || value === undefined;
  const unlimited = limit === null || limit === undefined;
  const ratio = unlimited || unknown ? 0 : Math.min(1, value / limit);
  const tone = ratio >= 0.9 ? 'admin-usage-fill--bad' : ratio >= 0.7 ? 'admin-usage-fill--warn' : 'admin-usage-fill--accent';
  return (
    <div className="admin-usage">
      <div className="admin-usage-head">
        <span>{label}</span>
        <span className="tabular-nums">
          {unknown ? '—' : (formatValue ? formatValue(value) : value)} / {unlimited ? '∞' : (formatValue ? formatValue(limit) : limit)}
        </span>
      </div>
      <div className="admin-usage-track">
        <div className={`admin-usage-fill ${tone}`} style={{ width: `${unlimited ? 4 : Math.max(3, ratio * 100)}%` }} />
      </div>
      {hint ? <div className="admin-hint">{hint}</div> : null}
    </div>
  );
};

const StatusBadge = ({ status }) => {
  const tone =
    status === 'active'
      ? 'admin-badge--active'
      : status === 'pending'
        ? 'admin-badge--pending'
        : 'admin-badge--suspended';
  return (
    <span className={`admin-badge ${tone}`}>{status}</span>
  );
};

const AdminTab = ({ icon: Icon, label, active, onClick }) => (
  <button
    onClick={onClick}
    aria-current={active ? 'page' : undefined}
    className="admin-tab"
  >
    <Icon className="w-4 h-4" />
    <span>{label}</span>
  </button>
);

// --- the users tab (plan A6/A7) ------------------------------------------------------

const UsersTab = ({ apiFetch, profiles, reload }) => {
  const [users, setUsers] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);
  const [editing, setEditing] = useState(null); // the user whose quota editor is open

  const load = useCallback(() => {
    apiFetch('/api/v1/admin/users?limit=200')
      .then((data) => { setUsers(data.items); setError(null); })
      .catch((err) => setError(err?.message || 'The request failed. Please try again.'));
  }, [apiFetch]);

  useEffect(() => { load(); }, [load]);

  const act = async (path, method = 'POST', body = null) => {
    setBusy(path);
    try {
      await apiFetch(path, { method, body: body ? JSON.stringify(body) : undefined });
      setError(null);
      load();
      reload();
    } catch (err) {
      setError(err?.message || 'The request failed. Please try again.');
    } finally {
      setBusy(null);
    }
  };

  if (!users) {
    if (error) {
      return <div role="alert" className="notice notice-bad">{error}</div>;
    }
    return <div className="text-faint text-sm">Loading the users…</div>;
  }

  return (
    <div className="space-y-4">
      {error ? <div role="alert" className="notice notice-bad">{error}</div> : null}
      <div className="admin-table-wrap">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th scope="col" className="th">User</th>
              <th scope="col" className="th">Status</th>
              <th scope="col" className="th">Profile</th>
              <th scope="col" className="th">Last login</th>
              <th scope="col" className="th">Usage today</th>
              <th scope="col" className="th text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <UserRow
                key={user.id}
                user={user}
                profiles={profiles}
                busy={busy}
                onAct={act}
                onEdit={() => setEditing(editing === user.id ? null : user.id)}
                editing={editing === user.id}
                apiFetch={apiFetch}
                reload={reload}
              />
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-faint">
        A suspended account stops working at its next request. The last admin cannot be
        demoted, suspended or deleted.
      </p>
    </div>
  );
};

const UserRow = ({ user, profiles, busy, onAct, onEdit, editing, apiFetch, reload }) => {
  const [usage, setUsage] = useState(null);
  const [usageFailed, setUsageFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiFetch(`/api/v1/admin/users/${user.id}`)
      .then((data) => {
        if (cancelled) return;
        setUsage(data.usage);
        setUsageFailed(false);
      })
      .catch(() => { if (!cancelled) setUsageFailed(true); });
    return () => { cancelled = true; };
  }, [apiFetch, user.id]);

  const limits = usage?.limits || {};
  const runsValue = usage ? (usage.runs_today ?? null) : null;
  const storageValue = usage ? (usage.storage_bytes ?? null) : null;
  return (
    <>
      <tr className="hover:bg-surface/60">
        <td className="td">
          <div className="font-medium">{user.username}</div>
          <div className="text-xs text-faint">{user.role}{user.email ? ` · ${user.email}` : ''}</div>
        </td>
        <td className="td"><StatusBadge status={user.status} /></td>
        <td className="td text-muted">
          {profiles?.find((p) => p.id === user.quota_profile_id)?.name ?? '—'}
        </td>
        <td className="td text-muted text-xs">{formatWhen(user.last_login_at)}</td>
        <td className="td">
          <div className="flex gap-4">
            <UsageBar label="runs today" value={runsValue} limit={limits.max_runs_per_day} />
            <UsageBar label="storage" value={storageValue} limit={limits.max_storage_bytes} formatValue={formatBytes} />
          </div>
          {usageFailed ? <div className="admin-hint-bad">Usage could not be loaded.</div> : null}
        </td>
        <td className="td">
          <div className="flex justify-end gap-1">
            {user.status === 'pending' ? (
              <button
                disabled={busy !== null}
                onClick={() => onAct(`/api/v1/admin/users/${user.id}/approve`)}
                className="admin-icon-btn admin-icon-btn--ok"
                title="Approve the pending account"
                aria-label="Approve the pending account"
              >
                <CheckCircle className="w-4 h-4" />
              </button>
            ) : null}
            {user.status === 'active' ? (
              <button
                disabled={busy !== null}
                onClick={() => onAct(`/api/v1/admin/users/${user.id}/suspend`)}
                className="admin-icon-btn admin-icon-btn--warn"
                title="Suspend the account"
                aria-label="Suspend the account"
              >
                <Ban className="w-4 h-4" />
              </button>
            ) : null}
            {user.status === 'suspended' ? (
              <button
                disabled={busy !== null}
                onClick={() => onAct(`/api/v1/admin/users/${user.id}`, 'PATCH', { status: 'active' })}
                className="admin-icon-btn admin-icon-btn--ok"
                title="Reinstate the account"
                aria-label="Reinstate the account"
              >
                <CheckCircle className="w-4 h-4" />
              </button>
            ) : null}
            <button
              onClick={onEdit}
              className="btn btn-quiet"
              title="Edit the quota of this user"
            >
              Quota
            </button>
            <button
              disabled={busy !== null}
              onClick={() => {
                if (window.confirm(`Delete ${user.username} with every run, dataset and file?`)) {
                  onAct(`/api/v1/admin/users/${user.id}`, 'DELETE');
                }
              }}
              className="admin-icon-btn admin-icon-btn--bad"
              title="Delete the user and their files"
              aria-label="Delete the user and their files"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </td>
      </tr>
      {editing ? (
        <tr>
          <td colSpan={6} className="td">
            <QuotaEditor apiFetch={apiFetch} user={user} profiles={profiles} onSaved={reload} />
          </td>
        </tr>
      ) : null}
    </>
  );
};

// The per-user quota editor (plan A3/A6): the profile selects the bundle, the
// overrides keep the exceptions out of it. Empty means unlimited.
const QUOTA_FIELDS = [
  ['max_concurrent_runs', 'concurrent runs'],
  ['max_queued_runs', 'queued runs'],
  ['max_runs_per_day', 'runs per day'],
  ['max_run_seconds', 'seconds per run'],
  ['max_storage_bytes', 'storage (bytes)', 'bytes'],
  ['max_predict_rows_per_request', 'predict rows per request'],
];

const QuotaEditor = ({ apiFetch, user, profiles, onSaved }) => {
  const [overrides, setOverrides] = useState({});
  const [profileId, setProfileId] = useState(user.quota_profile_id);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);

  const save = async () => {
    setError(null);
    setMessage(null);
    const body = { quota_profile_id: profileId, overrides };
    try {
      await apiFetch(`/api/v1/admin/users/${user.id}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      });
      setMessage('Saved. The limits apply to the next request.');
      onSaved();
    } catch (err) {
      setError(err?.message || 'The request failed. Please try again.');
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <label htmlFor="quota-profile" className="text-xs text-muted">Profile</label>
        <select
          id="quota-profile"
          value={profileId ?? ''}
          onChange={(event) => setProfileId(event.target.value ? Number(event.target.value) : null)}
          className="field w-auto"
        >
          {profiles?.map((profile) => (
            <option key={profile.id} value={profile.id}>{profile.name}</option>
          ))}
        </select>
        <span className="text-xs text-faint">The overrides below win over the profile.</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {QUOTA_FIELDS.map(([key, label, kind]) => (
          <label key={key} className="admin-form-label">
            {label}
            <input
              type="number"
              placeholder="unlimited"
              value={overrides[key] ?? ''}
              onChange={(event) => {
                const raw = event.target.value;
                setOverrides({ ...overrides, [key]: raw === '' ? null : Number(raw) });
              }}
              className="field"
            />
          </label>
        ))}
      </div>
      <div className="flex items-center gap-3">
        <button onClick={save} className="btn btn-primary">
          Save
        </button>
        {message ? <span className="notice notice-ok text-xs">{message}</span> : null}
        {error ? <span role="alert" className="notice notice-bad text-xs">{error}</span> : null}
      </div>
    </div>
  );
};

// --- the queue tab (plan A6/A7) -------------------------------------------------------

const QueueTab = ({ apiFetch }) => {
  const [queue, setQueue] = useState(null);
  // DECISION: keep load errors separate from mutation errors. The queue
  // polls every 5s; a poll success must not wipe a refused cancel alert.
  // The poll only clears its own loadError.
  const [loadError, setLoadError] = useState(null);
  const [actionError, setActionError] = useState(null);
  // INVARIANT: at most one alert is shown (action wins over load) so the
  // existing single role="alert" contract is preserved.
  const error = actionError || loadError;

  const load = useCallback(() => {
    apiFetch('/api/v1/admin/queue')
      .then((data) => { setQueue(data.items); setLoadError(null); })
      .catch((err) => setLoadError(err?.message || 'The request failed. Please try again.'));
  }, [apiFetch]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [load]);

  const cancel = async (runId) => {
    try {
      await apiFetch(`/api/v1/admin/queue/${runId}/cancel`, { method: 'POST' });
      setActionError(null);
      load();
    } catch (err) {
      setActionError(err?.message || 'The request failed. Please try again.');
    }
  };

  if (!queue) {
    if (error) return <div role="alert" className="notice notice-bad">{error}</div>;
    return <div className="text-faint text-sm">Loading the queue…</div>;
  }

  return (
    <div className="space-y-4">
      {error ? <div role="alert" className="notice notice-bad">{error}</div> : null}
      <div className="admin-table-wrap">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th scope="col" className="th">Run</th>
              <th scope="col" className="th">Owner</th>
              <th scope="col" className="th">Model</th>
              <th scope="col" className="th">Status</th>
              <th scope="col" className="th">Since</th>
              <th scope="col" className="th text-right" />
            </tr>
          </thead>
          <tbody>
            {queue.length === 0 ? (
              <tr><td colSpan={6} className="td text-center text-faint">The queue is empty.</td></tr>
            ) : queue.map((run) => (
              <tr key={run.id} className="hover:bg-surface/60">
                <td className="td font-medium">#{run.id}</td>
                <td className="td">{run.owner}</td>
                <td className="td text-muted">{run.model_name}</td>
                <td className="td">
                  <StatusBadge status={run.status === 'running' ? 'active' : 'pending'} />
                </td>
                <td className="td text-muted text-xs">
                  {formatWhen(run.status === 'running' ? run.started_at : run.created_at)}
                </td>
                <td className="td text-right">
                  <button
                    onClick={() => cancel(run.id)}
                    className="btn btn-danger"
                  >
                    Cancel
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-faint">What the machine is doing, answerable without a database shell.</p>
    </div>
  );
};

// --- the profiles tab (plan A3/A6) ----------------------------------------------------

const PROFILE_FIELDS = [
  ['max_concurrent_runs', 'concurrent runs'],
  ['max_queued_runs', 'queued runs'],
  ['max_runs_per_day', 'runs per day'],
  ['max_run_seconds', 'seconds per run'],
  ['max_run_memory_mb', 'memory per run (MB)'],
  ['max_cpu_seconds_per_month', 'CPU seconds per month'],
  ['max_storage_bytes', 'storage (bytes)'],
  ['max_datasets', 'datasets'],
  ['max_upload_bytes', 'upload limit (bytes)'],
  ['max_rows', 'rows per dataset'],
  ['max_predict_rows_per_request', 'predict rows per request'],
  ['max_predict_requests_per_minute', 'predict requests per minute'],
];

const ProfilesTab = ({ apiFetch, profiles, reload }) => {
  const [drafts, setDrafts] = useState({});
  const [saved, setSaved] = useState(null);
  const [error, setError] = useState(null);

  const valueOf = (profile, key) => {
    if (drafts[profile.id] && key in drafts[profile.id]) return drafts[profile.id][key];
    return profile[key] ?? '';
  };

  const save = async (profile) => {
    const values = drafts[profile.id] || {};
    try {
      await apiFetch(`/api/v1/admin/quota-profiles/${profile.id}`, {
        method: 'PUT',
        body: JSON.stringify({ values }),
      });
      setSaved(profile.name);
      setError(null);
      reload();
    } catch (err) {
      setError(err?.message || 'The request failed. Please try again.');
      setSaved(null);
    }
  };

  return (
    <div className="space-y-5">
      {profiles?.map((profile) => (
        <div key={profile.id} className="admin-card">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="font-medium">{profile.name}</div>
              <div className="text-xs text-faint">
                The limits are data: an edit applies to the next request. Empty means unlimited.
              </div>
            </div>
            <button
              onClick={() => save(profile)}
              className="btn btn-primary"
            >
              Save
            </button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {PROFILE_FIELDS.map(([key, label]) => (
              <label key={key} className="admin-form-label">
                {label}
                <input
                  type="number"
                  placeholder="unlimited"
                  value={valueOf(profile, key)}
                  onChange={(event) => {
                    const raw = event.target.value;
                    setDrafts({
                      ...drafts,
                      [profile.id]: { ...(drafts[profile.id] || {}), [key]: raw === '' ? null : Number(raw) },
                    });
                    setSaved(null);
                  }}
                  className="field"
                />
              </label>
            ))}
          </div>
        </div>
      ))}
      {saved ? <div className="notice notice-ok text-xs">The profile '{saved}' was saved.</div> : null}
      {error ? <div role="alert" className="notice notice-bad text-xs">{error}</div> : null}
    </div>
  );
};

// --- the invites tab (plan A1/A6) ------------------------------------------------------

const InvitesTab = ({ apiFetch }) => {
  const [invites, setInvites] = useState(null);
  const [created, setCreated] = useState(null);
  const [maxUses, setMaxUses] = useState(1);
  const [expiresDays, setExpiresDays] = useState(7);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    apiFetch('/api/v1/admin/invites')
      .then((data) => { setInvites(data.items); setError(null); })
      .catch((err) => setError(err?.message || 'The request failed. Please try again.'));
  }, [apiFetch]);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    try {
      const data = await apiFetch('/api/v1/admin/invites', {
        method: 'POST',
        body: JSON.stringify({ max_uses: maxUses, expires_days: expiresDays }),
      });
      setCreated(data);
      setError(null);
      load();
    } catch (err) {
      setError(err?.message || 'The request failed. Please try again.');
    }
  };

  return (
    <div className="space-y-4">
      <div className="admin-card flex flex-wrap items-end gap-3">
        <label className="admin-form-label">
          Uses
          <input
            type="number" min="1" value={maxUses}
            onChange={(event) => setMaxUses(Number(event.target.value))}
            className="field w-24"
          />
        </label>
        <label className="admin-form-label">
          Expires in (days)
          <input
            type="number" min="1" value={expiresDays}
            onChange={(event) => setExpiresDays(Number(event.target.value))}
            className="field w-28"
          />
        </label>
        <button onClick={create} className="btn btn-primary">
          Create an invite code
        </button>
        <span className="text-xs text-faint">
          The code is shown once, stored hashed, and counted: one code can serve a class.
        </span>
      </div>

      {created?.code ? (
        <div className="admin-invite-code">
          <div>
            <div className="text-sm tabular-nums text-accent">{created.code}</div>
            <div className="text-xs text-muted mt-1">Copy it now - it is not shown again.</div>
          </div>
          <button
            onClick={() => { if (created?.code) navigator.clipboard?.writeText(created.code); }}
            className="admin-icon-btn admin-icon-btn--accent"
            title="Copy the code"
            aria-label="Copy the code"
          >
            <Copy className="w-4 h-4" />
          </button>
        </div>
      ) : null}

      {invites ? (
        <div className="admin-table-wrap">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th scope="col" className="th">Invite</th>
                <th scope="col" className="th">Uses</th>
                <th scope="col" className="th">Expires</th>
                <th scope="col" className="th">State</th>
              </tr>
            </thead>
            <tbody>
              {invites.map((invite) => (
                <tr key={invite.id}>
                  <td className="td">#{invite.id}</td>
                  <td className="td text-muted">{invite.use_count} / {invite.max_uses}</td>
                  <td className="td text-muted text-xs">{formatWhen(invite.expires_at)}</td>
                  <td className="td">
                    <StatusBadge status={invite.expired || invite.exhausted ? 'suspended' : 'active'} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {error ? <div role="alert" className="notice notice-bad">{error}</div> : null}
    </div>
  );
};

// --- the audit tab (plan A9) ------------------------------------------------------------

const AuditTab = ({ apiFetch }) => {
  const [events, setEvents] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    apiFetch('/api/v1/admin/audit?limit=100')
      .then((data) => { setEvents(data.items); setError(null); })
      .catch((err) => setError(err?.message || 'The request failed. Please try again.'));
  }, [apiFetch]);

  if (error) return <div className="notice notice-bad">{error}</div>;
  if (!events) return <div className="text-faint text-sm">Loading the audit trail…</div>;

  return (
    <div className="space-y-2">
      {events.length === 0 ? (
        <div className="text-faint text-sm">No privileged change has been recorded yet.</div>
      ) : events.map((event) => (
        <div key={event.id} className="admin-audit-row">
          <ShieldAlert className="w-4 h-4 text-faint mt-0.5 shrink-0" />
          <div className="min-w-0">
            <div className="text-sm tabular-nums text-ink">{event.action}</div>
            <div className="text-xs text-faint">
              actor #{event.actor_id ?? 'system'} · {event.target_type || ''} {event.target_id || ''} · {formatWhen(event.created_at)}
            </div>
            {event.detail && Object.keys(event.detail).length ? (
              <div className="text-xs text-faint truncate">{JSON.stringify(event.detail)}</div>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
};

// --- the screen (plan A7) ----------------------------------------------------------------

const TABS = [
  ['users', Users, 'Users'],
  ['queue', ListOrdered, 'Queue'],
  ['profiles', Layers, 'Quota profiles'],
  ['invites', Ticket, 'Invites'],
  ['audit', ScrollText, 'Audit trail'],
];

export const AdminScreen = ({ apiFetch }) => {
  const [tab, setTab] = useState('users');
  const [profiles, setProfiles] = useState(null);
  const [usage, setUsage] = useState(null);
  const [profilesFailed, setProfilesFailed] = useState(false);
  const [usageFailed, setUsageFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const reload = useCallback(() => setReloadKey((key) => key + 1), []);

  useEffect(() => {
    apiFetch('/api/v1/admin/quota-profiles')
      .then((data) => { setProfiles(data.items); setProfilesFailed(false); })
      .catch(() => { setProfilesFailed(true); });
    apiFetch('/api/v1/admin/usage')
      .then((data) => { setUsage(data.items); setUsageFailed(false); })
      .catch(() => { setUsageFailed(true); });
  }, [apiFetch, reloadKey]);

  return (
    <div className="admin-page">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Admin</h1>
        <p className="text-sm text-faint mt-1">
          The users, their quotas and their usage, the queue, the invites and the audit
          trail - the controls of the deployment, without a database shell.
        </p>
      </div>

      {usageFailed ? <div className="notice notice-bad">Usage could not be loaded.</div> : null}
      {profilesFailed ? <div className="notice notice-bad">Quota profiles could not be loaded.</div> : null}

      {usage ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <SummaryCard icon={Users} label="users" value={usage.length} />
          <SummaryCard icon={ListOrdered} label="near a limit" value={usage.filter((u) => u.near_limits?.length).length} tone="warn" />
          <SummaryCard icon={Cpu} label="CPU seconds this month" value={usage.reduce((sum, u) => sum + (u.cpu_seconds_this_month || 0), 0)} />
          <SummaryCard icon={HardDrive} label="storage held" value={formatBytes(usage.reduce((sum, u) => sum + (u.storage_bytes || 0), 0))} />
        </div>
      ) : usageFailed ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <SummaryCard icon={Users} label="users" value="—" />
          <SummaryCard icon={ListOrdered} label="near a limit" value="—" tone="warn" />
          <SummaryCard icon={Cpu} label="CPU seconds this month" value="—" />
          <SummaryCard icon={HardDrive} label="storage held" value="—" />
        </div>
      ) : null}

      <div className="admin-tabs">
        {TABS.map(([key, Icon, label]) => (
          <AdminTab key={key} icon={Icon} label={label} active={tab === key} onClick={() => setTab(key)} />
        ))}
      </div>

      {tab === 'users' ? <UsersTab apiFetch={apiFetch} profiles={profiles} reload={reload} /> : null}
      {tab === 'queue' ? <QueueTab apiFetch={apiFetch} /> : null}
      {tab === 'profiles' ? <ProfilesTab apiFetch={apiFetch} profiles={profiles} reload={reload} /> : null}
      {tab === 'invites' ? <InvitesTab apiFetch={apiFetch} /> : null}
      {tab === 'audit' ? <AuditTab apiFetch={apiFetch} /> : null}
    </div>
  );
};

const SummaryCard = ({ icon: Icon, label, value, tone }) => (
  <div className="admin-summary">
    <div className="admin-summary-head">
      <Icon className="w-3.5 h-3.5" />
      {label}
    </div>
    <div className={`admin-summary-value ${tone === 'warn' ? 'admin-summary-value-warn' : ''}`}>{value}</div>
  </div>
);

export default AdminScreen;
