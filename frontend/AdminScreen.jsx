import React, { useState, useEffect, useCallback } from 'react';
import {
  Users, Layers, ListOrdered, Ticket, ScrollText, CheckCircle,
  Ban, Trash2, Copy, HardDrive, Cpu, ShieldAlert,
} from 'lucide-react';

// --- small shared pieces -----------------------------------------------------------

const formatBytes = (bytes) => {
  if (bytes === null || bytes === undefined) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
};

const formatWhen = (iso) => {
  if (!iso) return '—';
  const date = new Date(iso);
  return date.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
};

// A usage bar: the value against its limit. A quota the user cannot see is
// experienced as a bug - showing the limit turns a refusal into information
// (plan A7).
const UsageBar = ({ label, value, limit, formatValue, hint }) => {
  const unlimited = limit === null || limit === undefined;
  const ratio = unlimited ? 0 : Math.min(1, value / limit);
  const tone = ratio >= 0.9 ? 'bg-red-500' : ratio >= 0.7 ? 'bg-amber-500' : 'bg-blue-500';
  return (
    <div className="min-w-[140px]">
      <div className="flex justify-between text-xs text-zinc-400 mb-1">
        <span>{label}</span>
        <span className="tabular-nums">
          {formatValue ? formatValue(value) : value} / {unlimited ? '∞' : (formatValue ? formatValue(limit) : limit)}
        </span>
      </div>
      <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full ${tone} rounded-full transition-all`} style={{ width: `${unlimited ? 4 : Math.max(3, ratio * 100)}%` }} />
      </div>
      {hint ? <div className="text-[11px] text-zinc-500 mt-1">{hint}</div> : null}
    </div>
  );
};

const StatusBadge = ({ status }) => {
  const tone =
    status === 'active'
      ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
      : status === 'pending'
        ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
        : 'bg-red-500/10 text-red-400 border-red-500/30';
  return (
    <span className={`px-2 py-0.5 rounded-full border text-xs font-medium ${tone}`}>{status}</span>
  );
};

const AdminTab = ({ icon: Icon, label, active, onClick }) => (
  <button
    onClick={onClick}
    className={`flex items-center space-x-2 px-3 py-2 rounded-md text-sm transition ${active ? 'bg-blue-500/10 text-blue-400' : 'text-zinc-400 hover:text-white hover:bg-zinc-800'}`}
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
      .catch((err) => setError(err.message));
  }, [apiFetch]);

  useEffect(() => { load(); }, [load]);

  const act = async (path, method = 'POST', body = null) => {
    setBusy(path);
    try {
      const response = await apiFetch(path, { method, body: body ? JSON.stringify(body) : undefined });
      if (!response.ok) throw response;
      load();
      reload();
    } catch (err) {
      setError(err.detail ? JSON.stringify(err.detail) : 'the action failed');
    } finally {
      setBusy(null);
    }
  };

  if (error) {
    return <div className="text-red-400 text-sm">{error}</div>;
  }
  if (!users) {
    return <div className="text-zinc-500 text-sm">Loading the users…</div>;
  }

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-lg border border-zinc-800">
        <table className="w-full text-sm">
          <thead className="bg-zinc-900 text-zinc-400 text-xs uppercase">
            <tr>
              <th className="px-4 py-3 text-left font-medium">User</th>
              <th className="px-4 py-3 text-left font-medium">Status</th>
              <th className="px-4 py-3 text-left font-medium">Profile</th>
              <th className="px-4 py-3 text-left font-medium">Last login</th>
              <th className="px-4 py-3 text-left font-medium">Usage today</th>
              <th className="px-4 py-3 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
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
      <p className="text-xs text-zinc-500">
        A suspended account stops working at its next request. The last admin cannot be
        demoted, suspended or deleted.
      </p>
    </div>
  );
};

const UserRow = ({ user, profiles, busy, onAct, onEdit, editing, apiFetch, reload }) => {
  const [usage, setUsage] = useState(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch(`/api/v1/admin/users/${user.id}`)
      .then((data) => { if (!cancelled) setUsage(data.usage); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [apiFetch, user.id]);

  const limits = usage?.limits || {};
  return (
    <>
      <tr className="hover:bg-zinc-900/60">
        <td className="px-4 py-3">
          <div className="font-medium">{user.username}</div>
          <div className="text-xs text-zinc-500">{user.role}{user.email ? ` · ${user.email}` : ''}</div>
        </td>
        <td className="px-4 py-3"><StatusBadge status={user.status} /></td>
        <td className="px-4 py-3 text-zinc-400">
          {profiles?.find((p) => p.id === user.quota_profile_id)?.name || 'free'}
        </td>
        <td className="px-4 py-3 text-zinc-400 text-xs">{formatWhen(user.last_login_at)}</td>
        <td className="px-4 py-3">
          <div className="flex gap-4">
            <UsageBar label="runs today" value={usage?.runs_today ?? 0} limit={limits.max_runs_per_day} />
            <UsageBar label="storage" value={usage?.storage_bytes ?? 0} limit={limits.max_storage_bytes} formatValue={formatBytes} />
          </div>
        </td>
        <td className="px-4 py-3">
          <div className="flex justify-end gap-1">
            {user.status === 'pending' ? (
              <button
                disabled={busy !== null}
                onClick={() => onAct(`/api/v1/admin/users/${user.id}/approve`)}
                className="p-1.5 rounded-md text-emerald-400 hover:bg-emerald-500/10 disabled:opacity-40"
                title="Approve the pending account"
              >
                <CheckCircle className="w-4 h-4" />
              </button>
            ) : null}
            {user.status === 'active' ? (
              <button
                disabled={busy !== null}
                onClick={() => onAct(`/api/v1/admin/users/${user.id}/suspend`)}
                className="p-1.5 rounded-md text-amber-400 hover:bg-amber-500/10 disabled:opacity-40"
                title="Suspend the account"
              >
                <Ban className="w-4 h-4" />
              </button>
            ) : null}
            {user.status === 'suspended' ? (
              <button
                disabled={busy !== null}
                onClick={() => onAct(`/api/v1/admin/users/${user.id}`, 'PATCH', { status: 'active' })}
                className="p-1.5 rounded-md text-emerald-400 hover:bg-emerald-500/10 disabled:opacity-40"
                title="Reinstate the account"
              >
                <CheckCircle className="w-4 h-4" />
              </button>
            ) : null}
            <button
              onClick={onEdit}
              className="px-2 py-1.5 rounded-md text-xs text-zinc-300 hover:bg-zinc-800"
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
              className="p-1.5 rounded-md text-red-400 hover:bg-red-500/10 disabled:opacity-40"
              title="Delete the user and their files"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </td>
      </tr>
      {editing ? (
        <tr className="bg-zinc-900/40">
          <td colSpan={6} className="px-4 py-4">
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
    const response = await apiFetch(`/api/v1/admin/users/${user.id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
    if (response.ok) {
      setMessage('Saved. The limits apply to the next request.');
      onSaved();
    } else {
      setError(response.detail ? JSON.stringify(response.detail) : 'the save failed');
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <span className="text-xs text-zinc-400">Profile</span>
        <select
          value={profileId ?? ''}
          onChange={(event) => setProfileId(event.target.value ? Number(event.target.value) : null)}
          className="bg-zinc-800 border border-zinc-700 rounded-md px-2 py-1 text-sm"
        >
          {profiles?.map((profile) => (
            <option key={profile.id} value={profile.id}>{profile.name}</option>
          ))}
        </select>
        <span className="text-xs text-zinc-500">The overrides below win over the profile.</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {QUOTA_FIELDS.map(([key, label, kind]) => (
          <label key={key} className="text-xs text-zinc-400">
            {label}
            <input
              type="number"
              placeholder="unlimited"
              value={overrides[key] ?? ''}
              onChange={(event) => {
                const raw = event.target.value;
                setOverrides({ ...overrides, [key]: raw === '' ? null : Number(raw) });
              }}
              className="mt-1 w-full bg-zinc-800 border border-zinc-700 rounded-md px-2 py-1 text-sm text-zinc-100"
            />
          </label>
        ))}
      </div>
      <div className="flex items-center gap-3">
        <button onClick={save} className="px-3 py-1.5 rounded-md bg-blue-600 hover:bg-blue-500 text-sm font-medium">
          Save
        </button>
        {message ? <span className="text-xs text-emerald-400">{message}</span> : null}
        {error ? <span className="text-xs text-red-400">{error}</span> : null}
      </div>
    </div>
  );
};

// --- the queue tab (plan A6/A7) -------------------------------------------------------

const QueueTab = ({ apiFetch }) => {
  const [queue, setQueue] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    apiFetch('/api/v1/admin/queue')
      .then((data) => { setQueue(data.items); setError(null); })
      .catch((err) => setError(err.message));
  }, [apiFetch]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [load]);

  const cancel = async (runId) => {
    const response = await apiFetch(`/api/v1/admin/queue/${runId}/cancel`, { method: 'POST' });
    if (!response.ok) {
      setError('the cancel failed');
    }
    load();
  };

  if (error) return <div className="text-red-400 text-sm">{error}</div>;
  if (!queue) return <div className="text-zinc-500 text-sm">Loading the queue…</div>;

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-lg border border-zinc-800">
        <table className="w-full text-sm">
          <thead className="bg-zinc-900 text-zinc-400 text-xs uppercase">
            <tr>
              <th className="px-4 py-3 text-left font-medium">Run</th>
              <th className="px-4 py-3 text-left font-medium">Owner</th>
              <th className="px-4 py-3 text-left font-medium">Model</th>
              <th className="px-4 py-3 text-left font-medium">Status</th>
              <th className="px-4 py-3 text-left font-medium">Since</th>
              <th className="px-4 py-3 text-right font-medium" />
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {queue.length === 0 ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-zinc-500">The queue is empty.</td></tr>
            ) : queue.map((run) => (
              <tr key={run.id} className="hover:bg-zinc-900/60">
                <td className="px-4 py-3 font-medium">#{run.id}</td>
                <td className="px-4 py-3">{run.owner}</td>
                <td className="px-4 py-3 text-zinc-400">{run.model_name}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={run.status === 'running' ? 'active' : 'pending'} />
                </td>
                <td className="px-4 py-3 text-zinc-400 text-xs">
                  {formatWhen(run.status === 'running' ? run.started_at : run.created_at)}
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    onClick={() => cancel(run.id)}
                    className="px-2 py-1 rounded-md text-xs text-red-400 hover:bg-red-500/10"
                  >
                    Cancel
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-zinc-500">What the machine is doing, answerable without a database shell.</p>
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
    const response = await apiFetch(`/api/v1/admin/quota-profiles/${profile.id}`, {
      method: 'PUT',
      body: JSON.stringify({ values }),
    });
    if (response.ok) {
      setSaved(profile.name);
      setError(null);
      reload();
    } else {
      setError(response.detail ? JSON.stringify(response.detail) : 'the save failed');
      setSaved(null);
    }
  };

  return (
    <div className="space-y-5">
      {profiles?.map((profile) => (
        <div key={profile.id} className="rounded-lg border border-zinc-800 p-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="font-medium">{profile.name}</div>
              <div className="text-xs text-zinc-500">
                The limits are data: an edit applies to the next request. Empty means unlimited.
              </div>
            </div>
            <button
              onClick={() => save(profile)}
              className="px-3 py-1.5 rounded-md bg-blue-600 hover:bg-blue-500 text-sm font-medium"
            >
              Save
            </button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {PROFILE_FIELDS.map(([key, label]) => (
              <label key={key} className="text-xs text-zinc-400">
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
                  className="mt-1 w-full bg-zinc-800 border border-zinc-700 rounded-md px-2 py-1 text-sm text-zinc-100"
                />
              </label>
            ))}
          </div>
        </div>
      ))}
      {saved ? <div className="text-xs text-emerald-400">The profile '{saved}' was saved.</div> : null}
      {error ? <div className="text-xs text-red-400">{error}</div> : null}
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
      .catch((err) => setError(err.message));
  }, [apiFetch]);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    const response = await apiFetch('/api/v1/admin/invites', {
      method: 'POST',
      body: JSON.stringify({ max_uses: maxUses, expires_days: expiresDays }),
    });
    if (response.ok) {
      const data = await response.json();
      setCreated(data);
      load();
    } else {
      setError('the invite could not be created');
    }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-zinc-800 p-4 flex flex-wrap items-end gap-3">
        <label className="text-xs text-zinc-400">
          Uses
          <input
            type="number" min="1" value={maxUses}
            onChange={(event) => setMaxUses(Number(event.target.value))}
            className="mt-1 block w-24 bg-zinc-800 border border-zinc-700 rounded-md px-2 py-1 text-sm"
          />
        </label>
        <label className="text-xs text-zinc-400">
          Expires in (days)
          <input
            type="number" min="1" value={expiresDays}
            onChange={(event) => setExpiresDays(Number(event.target.value))}
            className="mt-1 block w-28 bg-zinc-800 border border-zinc-700 rounded-md px-2 py-1 text-sm"
          />
        </label>
        <button onClick={create} className="px-3 py-2 rounded-md bg-blue-600 hover:bg-blue-500 text-sm font-medium">
          Create an invite code
        </button>
        <span className="text-xs text-zinc-500">
          The code is shown once, stored hashed, and counted: one code can serve a class.
        </span>
      </div>

      {created ? (
        <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 p-4 flex items-center justify-between">
          <div>
            <div className="text-sm font-mono text-blue-300">{created.code}</div>
            <div className="text-xs text-zinc-400 mt-1">Copy it now - it is not shown again.</div>
          </div>
          <button
            onClick={() => { navigator.clipboard?.writeText(created.code); }}
            className="p-2 rounded-md hover:bg-blue-500/20 text-blue-300"
            title="Copy the code"
          >
            <Copy className="w-4 h-4" />
          </button>
        </div>
      ) : null}

      {invites ? (
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full text-sm">
            <thead className="bg-zinc-900 text-zinc-400 text-xs uppercase">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Invite</th>
                <th className="px-4 py-3 text-left font-medium">Uses</th>
                <th className="px-4 py-3 text-left font-medium">Expires</th>
                <th className="px-4 py-3 text-left font-medium">State</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {invites.map((invite) => (
                <tr key={invite.id}>
                  <td className="px-4 py-3">#{invite.id}</td>
                  <td className="px-4 py-3 text-zinc-400">{invite.use_count} / {invite.max_uses}</td>
                  <td className="px-4 py-3 text-zinc-400 text-xs">{formatWhen(invite.expires_at)}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={invite.expired || invite.exhausted ? 'suspended' : 'active'} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {error ? <div className="text-red-400 text-sm">{error}</div> : null}
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
      .catch((err) => setError(err.message));
  }, [apiFetch]);

  if (error) return <div className="text-red-400 text-sm">{error}</div>;
  if (!events) return <div className="text-zinc-500 text-sm">Loading the audit trail…</div>;

  return (
    <div className="space-y-2">
      {events.length === 0 ? (
        <div className="text-zinc-500 text-sm">No privileged change has been recorded yet.</div>
      ) : events.map((event) => (
        <div key={event.id} className="rounded-lg border border-zinc-800 px-4 py-3 flex items-start gap-3">
          <ShieldAlert className="w-4 h-4 text-zinc-500 mt-0.5 shrink-0" />
          <div className="min-w-0">
            <div className="text-sm font-mono text-zinc-300">{event.action}</div>
            <div className="text-xs text-zinc-500">
              actor #{event.actor_id ?? 'system'} · {event.target_type || ''} {event.target_id || ''} · {formatWhen(event.created_at)}
            </div>
            {event.detail && Object.keys(event.detail).length ? (
              <div className="text-xs text-zinc-600 truncate">{JSON.stringify(event.detail)}</div>
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
  const [reloadKey, setReloadKey] = useState(0);

  const reload = useCallback(() => setReloadKey((key) => key + 1), []);

  useEffect(() => {
    apiFetch('/api/v1/admin/quota-profiles')
      .then((data) => setProfiles(data.items))
      .catch(() => {});
    apiFetch('/api/v1/admin/usage')
      .then((data) => setUsage(data.items))
      .catch(() => {});
  }, [apiFetch, reloadKey]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Admin</h1>
        <p className="text-sm text-zinc-500 mt-1">
          The users, their quotas and their usage, the queue, the invites and the audit
          trail - the controls of the deployment, without a database shell.
        </p>
      </div>

      {usage ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <SummaryCard icon={Users} label="users" value={usage.length} />
          <SummaryCard icon={ListOrdered} label="near a limit" value={usage.filter((u) => u.near_limits?.length).length} tone="text-amber-400" />
          <SummaryCard icon={Cpu} label="CPU seconds this month" value={usage.reduce((sum, u) => sum + (u.cpu_seconds_this_month || 0), 0)} />
          <SummaryCard icon={HardDrive} label="storage held" value={formatBytes(usage.reduce((sum, u) => sum + (u.storage_bytes || 0), 0))} />
        </div>
      ) : null}

      <div className="flex flex-wrap gap-1 border-b border-zinc-800 pb-2">
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

const SummaryCard = ({ icon: Icon, label, value, tone = 'text-zinc-100' }) => (
  <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
    <div className="flex items-center gap-2 text-zinc-500 text-xs uppercase">
      <Icon className="w-3.5 h-3.5" />
      {label}
    </div>
    <div className={`text-2xl font-bold mt-1 tabular-nums ${tone}`}>{value}</div>
  </div>
);

export default AdminScreen;
