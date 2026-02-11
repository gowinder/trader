import { useState, useEffect, useCallback } from "react";
import { Eye, EyeOff, Plus, Trash2, X, ChevronUp, ChevronDown, Save, RefreshCw, Zap } from "lucide-react";

// ── Types ──────────────────────────────────────────────────────────────────

interface Provider {
  id: number;
  name: string;
  displayName: string;
  providerType: string;
  apiKey: string;
  hasApiKey: boolean;
  baseUrl: string;
  timeout: number;
  models: string[];
  isBuiltin: boolean;
  isEnabled: boolean;
}

interface RoutingItem {
  id: number;
  scope: string;
  providerId: number;
  model: string;
  priority: number;
  isEnabled: boolean;
  providerName: string;
  providerDisplayName: string;
}

interface LocalRouting {
  providerId: number;
  model: string;
}

interface Toast {
  type: "success" | "error";
  message: string;
}

// ── Component ──────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [mainRouting, setMainRouting] = useState<LocalRouting[]>([]);
  const [advisoryRouting, setAdvisoryRouting] = useState<LocalRouting[]>([]);
  const [mainStrategy, setMainStrategy] = useState("priority");
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<Toast | null>(null);

  // provider card local state
  const [cardEdits, setCardEdits] = useState<Record<number, Partial<Provider>>>({});
  const [showKey, setShowKey] = useState<Record<number, boolean>>({});
  const [newModelInput, setNewModelInput] = useState<Record<number, string>>({});
  const [savingProvider, setSavingProvider] = useState<Record<number, boolean>>({});

  // fetch models & test
  const [fetchingModels, setFetchingModels] = useState<Record<number, boolean>>({});
  const [testingProvider, setTestingProvider] = useState<Record<number, boolean>>({});
  const [testResult, setTestResult] = useState<Record<number, { success: boolean; message: string } | null>>({});
  const [modelPickerOpen, setModelPickerOpen] = useState<Record<number, boolean>>({});
  const [availableModels, setAvailableModels] = useState<Record<number, string[]>>({});

  // add provider modal
  const [showAddModal, setShowAddModal] = useState(false);
  const [newProvider, setNewProvider] = useState({
    name: "",
    displayName: "",
    providerType: "openai_compatible",
    apiKey: "",
    baseUrl: "",
    timeout: 30,
  });

  // routing saving
  const [savingMain, setSavingMain] = useState(false);
  const [savingAdvisory, setSavingAdvisory] = useState(false);

  const showToast = useCallback((type: "success" | "error", message: string) => {
    setToast({ type, message });
  }, []);

  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(t);
    }
  }, [toast]);

  // ── Fetch data ────────────────────────────────────────────────────────

  const fetchProviders = useCallback(async () => {
    try {
      const res = await fetch("/api/llm-config/providers");
      const data = await res.json();
      if (data.providers) setProviders(data.providers);
    } catch {
      showToast("error", "加载 Provider 列表失败");
    }
  }, [showToast]);

  const fetchRouting = useCallback(
    async (scope: "main" | "advisory") => {
      try {
        const res = await fetch(`/api/llm-config/routing?scope=${scope}`);
        const data = await res.json();
        const items: RoutingItem[] = data.routing || [];
        const local = items.map((r) => ({ providerId: r.providerId, model: r.model }));
        if (scope === "main") setMainRouting(local);
        else setAdvisoryRouting(local);
      } catch {
        showToast("error", `加载 ${scope} 调度配置失败`);
      }
    },
    [showToast]
  );

  useEffect(() => {
    Promise.all([fetchProviders(), fetchRouting("main"), fetchRouting("advisory")]).finally(() =>
      setLoading(false)
    );
  }, [fetchProviders, fetchRouting]);

  // ── Provider helpers ──────────────────────────────────────────────────

  const getCardEdit = (p: Provider) => ({ ...p, ...cardEdits[p.id] });

  const updateCardEdit = (id: number, patch: Partial<Provider>) => {
    setCardEdits((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  };

  const handleSaveProvider = async (p: Provider) => {
    setSavingProvider((s) => ({ ...s, [p.id]: true }));
    const edit = getCardEdit(p);
    const body: Record<string, unknown> = { id: p.id };
    if (edit.displayName !== p.displayName) body.displayName = edit.displayName;
    if (edit.baseUrl !== p.baseUrl) body.baseUrl = edit.baseUrl;
    if (edit.timeout !== p.timeout) body.timeout = edit.timeout;
    if (edit.isEnabled !== p.isEnabled) body.isEnabled = edit.isEnabled;
    if (JSON.stringify(edit.models) !== JSON.stringify(p.models)) body.models = edit.models;
    // apiKey: send if user typed something
    const editedKey = cardEdits[p.id]?.apiKey;
    if (editedKey !== undefined && editedKey !== "") body.apiKey = editedKey;
    try {
      const res = await fetch("/api/llm-config/providers", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        showToast("success", `${edit.displayName} 已保存`);
        await fetchProviders();
        setCardEdits((prev) => {
          const next = { ...prev };
          delete next[p.id];
          return next;
        });
      } else {
        const d = await res.json().catch(() => ({}));
        showToast("error", d.error || "保存失败");
      }
    } catch {
      showToast("error", "网络错误");
    } finally {
      setSavingProvider((s) => ({ ...s, [p.id]: false }));
    }
  };

  const handleDeleteProvider = async (p: Provider) => {
    if (!confirm(`确定删除 ${p.displayName}?`)) return;
    try {
      const res = await fetch("/api/llm-config/providers", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: p.id }),
      });
      if (res.ok) {
        showToast("success", "已删除");
        await fetchProviders();
      } else {
        showToast("error", "删除失败");
      }
    } catch {
      showToast("error", "网络错误");
    }
  };

  const handleAddProvider = async () => {
    if (!newProvider.name || !newProvider.displayName) {
      showToast("error", "请填写名称和显示名");
      return;
    }
    try {
      const res = await fetch("/api/llm-config/providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newProvider),
      });
      if (res.ok) {
        showToast("success", "Provider 已创建");
        setShowAddModal(false);
        setNewProvider({ name: "", displayName: "", providerType: "openai_compatible", apiKey: "", baseUrl: "", timeout: 30 });
        await fetchProviders();
      } else {
        const d = await res.json().catch(() => ({}));
        showToast("error", d.error || "创建失败");
      }
    } catch {
      showToast("error", "网络错误");
    }
  };

  const removeModel = (providerId: number, model: string) => {
    const p = providers.find((x) => x.id === providerId);
    if (!p) return;
    const edit = getCardEdit(p);
    updateCardEdit(providerId, { models: edit.models.filter((m) => m !== model) });
  };

  const addModel = (providerId: number) => {
    const val = (newModelInput[providerId] || "").trim();
    if (!val) return;
    const p = providers.find((x) => x.id === providerId);
    if (!p) return;
    const edit = getCardEdit(p);
    if (edit.models.includes(val)) return;
    updateCardEdit(providerId, { models: [...edit.models, val] });
    setNewModelInput((prev) => ({ ...prev, [providerId]: "" }));
  };

  const handleFetchModels = async (p: Provider) => {
    setFetchingModels((s) => ({ ...s, [p.id]: true }));
    try {
      const body: Record<string, unknown> = { providerId: p.id };
      const editedKey = cardEdits[p.id]?.apiKey;
      if (editedKey) body.apiKey = editedKey;
      const res = await fetch("/api/llm-config/models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (res.ok && data.models) {
        if (data.models.length === 0) {
          showToast("error", data.message || "未获取到模型");
        } else {
          setAvailableModels((s) => ({ ...s, [p.id]: data.models }));
          setModelPickerOpen((s) => ({ ...s, [p.id]: true }));
          showToast("success", `获取到 ${data.models.length} 个模型`);
        }
      } else {
        showToast("error", data.error || "获取模型列表失败");
      }
    } catch {
      showToast("error", "网络错误");
    } finally {
      setFetchingModels((s) => ({ ...s, [p.id]: false }));
    }
  };

  const handleTestProvider = async (p: Provider) => {
    const edit = getCardEdit(p);
    if (edit.models.length === 0) {
      showToast("error", "请先添加至少一个模型");
      return;
    }
    const model = edit.models[0];
    setTestingProvider((s) => ({ ...s, [p.id]: true }));
    setTestResult((s) => ({ ...s, [p.id]: null }));
    try {
      const body: Record<string, unknown> = { providerId: p.id, model };
      const editedKey = cardEdits[p.id]?.apiKey;
      if (editedKey) body.apiKey = editedKey;
      const res = await fetch("/api/llm-config/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      setTestResult((s) => ({
        ...s,
        [p.id]: { success: data.success, message: data.message },
      }));
      showToast(data.success ? "success" : "error", data.message);
    } catch {
      setTestResult((s) => ({
        ...s,
        [p.id]: { success: false, message: "网络错误" },
      }));
      showToast("error", "网络错误");
    } finally {
      setTestingProvider((s) => ({ ...s, [p.id]: false }));
    }
  };

  const toggleModelSelection = (providerId: number, model: string) => {
    const p = providers.find((x) => x.id === providerId);
    if (!p) return;
    const edit = getCardEdit(p);
    if (edit.models.includes(model)) {
      updateCardEdit(providerId, { models: edit.models.filter((m) => m !== model) });
    } else {
      updateCardEdit(providerId, { models: [...edit.models, model] });
    }
  };

  // ── Routing helpers ───────────────────────────────────────────────────

  const enabledProviders = providers.filter((p) => {
    const edit = cardEdits[p.id];
    return edit?.isEnabled !== undefined ? edit.isEnabled : p.isEnabled;
  });

  const handleSaveRouting = async (scope: "main" | "advisory") => {
    const setter = scope === "main" ? setSavingMain : setSavingAdvisory;
    const items = scope === "main" ? mainRouting : advisoryRouting;
    setter(true);
    try {
      const body: Record<string, unknown> = {
        scope,
        items: items.map((r, i) => ({ providerId: r.providerId, model: r.model, priority: i + 1 })),
      };
      if (scope === "main") body.strategy = mainStrategy;
      const res = await fetch("/api/llm-config/routing", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        showToast("success", `${scope === "main" ? "主 LLM" : "Advisory LLM"} 调度已保存`);
      } else {
        const d = await res.json().catch(() => ({}));
        showToast("error", d.error || "保存失败");
      }
    } catch {
      showToast("error", "网络错误");
    } finally {
      setter(false);
    }
  };

  const addRoutingItem = (scope: "main" | "advisory") => {
    if (enabledProviders.length === 0) return;
    const first = enabledProviders[0];
    const firstEdit = getCardEdit(first);
    const item: LocalRouting = {
      providerId: first.id,
      model: firstEdit.models[0] || "",
    };
    if (scope === "main") setMainRouting((prev) => [...prev, item]);
    else setAdvisoryRouting((prev) => [...prev, item]);
  };

  const moveRoutingItem = (scope: "main" | "advisory", index: number, dir: -1 | 1) => {
    const setter = scope === "main" ? setMainRouting : setAdvisoryRouting;
    setter((prev) => {
      const arr = [...prev];
      const target = index + dir;
      if (target < 0 || target >= arr.length) return arr;
      [arr[index], arr[target]] = [arr[target], arr[index]];
      return arr;
    });
  };

  const removeRoutingItem = (scope: "main" | "advisory", index: number) => {
    const setter = scope === "main" ? setMainRouting : setAdvisoryRouting;
    setter((prev) => prev.filter((_, i) => i !== index));
  };

  const updateRoutingItem = (scope: "main" | "advisory", index: number, patch: Partial<LocalRouting>) => {
    const setter = scope === "main" ? setMainRouting : setAdvisoryRouting;
    setter((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  };

  // ── Render ────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center">
        <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  const inputCls = "w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary";
  const tagCls = "inline-flex items-center gap-1 px-2 py-1 rounded-md bg-secondary text-secondary-foreground text-xs";

  const renderToggle = (enabled: boolean, onToggle: () => void) => (
    <button
      type="button"
      onClick={onToggle}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
        enabled ? "bg-primary" : "bg-muted"
      }`}
    >
      <span
        className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
          enabled ? "translate-x-4.5" : "translate-x-0.5"
        }`}
      />
    </button>
  );

  const renderRoutingPanel = (
    scope: "main" | "advisory",
    title: string,
    items: LocalRouting[],
    saving: boolean
  ) => (
    <div className="rounded-lg border border-border bg-card p-6">
      <h3 className="text-base font-semibold mb-4">{title}</h3>

      {scope === "main" && (
        <div className="mb-4">
          <label className="block text-sm text-muted-foreground mb-1">调度策略</label>
          <select
            value={mainStrategy}
            onChange={(e) => setMainStrategy(e.target.value)}
            className={inputCls}
          >
            <option value="priority">优先级 (priority)</option>
            <option value="cost_first">成本优先 (cost_first)</option>
            <option value="round_robin">轮询 (round_robin)</option>
          </select>
        </div>
      )}

      <div className="space-y-2 mb-4">
        {items.length === 0 && (
          <p className="text-sm text-muted-foreground py-4 text-center">暂无调度项，请点击下方添加</p>
        )}
        {items.map((item, idx) => {
          const prov = providers.find((p) => p.id === item.providerId);
          const provEdit = prov ? getCardEdit(prov) : null;
          return (
            <div
              key={`${scope}-${idx}`}
              className="flex items-center gap-2 rounded-md border border-border p-2"
            >
              <span className="text-xs text-muted-foreground w-6 text-center">{idx + 1}</span>

              {/* provider select */}
              <select
                value={item.providerId}
                onChange={(e) => {
                  const newId = Number(e.target.value);
                  const np = providers.find((p) => p.id === newId);
                  const npEdit = np ? getCardEdit(np) : null;
                  updateRoutingItem(scope, idx, {
                    providerId: newId,
                    model: npEdit?.models[0] || "",
                  });
                }}
                className="rounded-md border border-border bg-background px-2 py-1 text-sm flex-1 min-w-0"
              >
                {enabledProviders.map((ep) => (
                  <option key={ep.id} value={ep.id}>
                    {getCardEdit(ep).displayName}
                  </option>
                ))}
              </select>

              {/* model select */}
              <select
                value={item.model}
                onChange={(e) => updateRoutingItem(scope, idx, { model: e.target.value })}
                className="rounded-md border border-border bg-background px-2 py-1 text-sm flex-1 min-w-0"
              >
                {(provEdit?.models || []).map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>

              {/* move buttons */}
              <button
                type="button"
                onClick={() => moveRoutingItem(scope, idx, -1)}
                disabled={idx === 0}
                className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"
              >
                <ChevronUp className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => moveRoutingItem(scope, idx, 1)}
                disabled={idx === items.length - 1}
                className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"
              >
                <ChevronDown className="h-4 w-4" />
              </button>

              <button
                type="button"
                onClick={() => removeRoutingItem(scope, idx)}
                className="p-1 text-red-400 hover:text-red-300"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          );
        })}
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => addRoutingItem(scope)}
          disabled={enabledProviders.length === 0}
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md border border-border text-sm hover:bg-accent disabled:opacity-50"
        >
          <Plus className="h-3.5 w-3.5" /> 添加
        </button>
        <button
          type="button"
          onClick={() => handleSaveRouting(scope)}
          disabled={saving}
          className="inline-flex items-center gap-1 px-4 py-1.5 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
        >
          <Save className="h-3.5 w-3.5" /> {saving ? "保存中..." : "保存调度"}
        </button>
      </div>
    </div>
  );

  return (
    <div className="p-6 space-y-8">
      {/* Toast */}
      {toast && (
        <div
          className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-sm font-medium ${
            toast.type === "success"
              ? "bg-green-500/20 text-green-400 border border-green-500/30"
              : "bg-red-500/20 text-red-400 border border-red-500/30"
          }`}
        >
          {toast.message}
        </div>
      )}

      {/* ── Section 1: Provider Pool ──────────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-bold">LLM Provider 配置</h1>
          <button
            type="button"
            onClick={() => setShowAddModal(true)}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" /> 添加自定义 Provider
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {providers.map((p) => {
            const edit = getCardEdit(p);
            return (
              <div key={p.id} className="rounded-lg border border-border bg-card">
                {/* Card Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-border">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{edit.displayName}</span>
                    {p.isBuiltin && (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-secondary text-secondary-foreground">
                        内置
                      </span>
                    )}
                  </div>
                  {renderToggle(edit.isEnabled, () => updateCardEdit(p.id, { isEnabled: !edit.isEnabled }))}
                </div>

                {/* Card Content */}
                <div className="px-6 py-4 space-y-4">
                  {/* API Key */}
                  <div>
                    <label className="block text-sm text-muted-foreground mb-1">API Key</label>
                    <div className="relative">
                      <input
                        type={showKey[p.id] ? "text" : "password"}
                        value={cardEdits[p.id]?.apiKey ?? ""}
                        onChange={(e) => updateCardEdit(p.id, { apiKey: e.target.value })}
                        placeholder={p.hasApiKey ? p.apiKey : "未设置"}
                        className={inputCls + " pr-9"}
                      />
                      <button
                        type="button"
                        onClick={() => setShowKey((s) => ({ ...s, [p.id]: !s[p.id] }))}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      >
                        {showKey[p.id] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>

                  {/* Base URL */}
                  <div>
                    <label className="block text-sm text-muted-foreground mb-1">Base URL</label>
                    <input
                      type="text"
                      value={edit.baseUrl}
                      onChange={(e) => updateCardEdit(p.id, { baseUrl: e.target.value })}
                      placeholder={p.isBuiltin ? p.baseUrl || "使用默认" : "https://..."}
                      className={inputCls}
                    />
                  </div>

                  {/* Timeout */}
                  <div>
                    <label className="block text-sm text-muted-foreground mb-1">Timeout (秒)</label>
                    <input
                      type="number"
                      min={1}
                      value={edit.timeout}
                      onChange={(e) => updateCardEdit(p.id, { timeout: Number(e.target.value) })}
                      className={inputCls}
                    />
                  </div>

                  {/* Models */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-sm text-muted-foreground">模型列表</label>
                      <button
                        type="button"
                        onClick={() => handleFetchModels(p)}
                        disabled={fetchingModels[p.id]}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs border border-border hover:bg-accent disabled:opacity-50"
                      >
                        <RefreshCw className={`h-3 w-3 ${fetchingModels[p.id] ? "animate-spin" : ""}`} />
                        {fetchingModels[p.id] ? "获取中..." : "获取模型"}
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-1.5 mb-2">
                      {edit.models.map((m) => (
                        <span key={m} className={tagCls}>
                          {m}
                          <button
                            type="button"
                            onClick={() => removeModel(p.id, m)}
                            className="text-muted-foreground hover:text-foreground"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </span>
                      ))}
                      {edit.models.length === 0 && (
                        <span className="text-xs text-muted-foreground">暂无模型</span>
                      )}
                    </div>

                    {/* Model Picker */}
                    {modelPickerOpen[p.id] && availableModels[p.id]?.length > 0 && (
                      <div className="mb-2 rounded-md border border-border bg-background p-2 max-h-48 overflow-y-auto">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-muted-foreground">可用模型（点击选择/取消）</span>
                          <button
                            type="button"
                            onClick={() => setModelPickerOpen((s) => ({ ...s, [p.id]: false }))}
                            className="text-muted-foreground hover:text-foreground"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </div>
                        <div className="space-y-0.5">
                          {availableModels[p.id].map((m) => (
                            <label key={m} className="flex items-center gap-2 px-1 py-0.5 rounded hover:bg-accent cursor-pointer text-xs">
                              <input
                                type="checkbox"
                                checked={edit.models.includes(m)}
                                onChange={() => toggleModelSelection(p.id, m)}
                                className="rounded"
                              />
                              <span className="truncate">{m}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                    )}

                    <input
                      type="text"
                      value={newModelInput[p.id] || ""}
                      onChange={(e) => setNewModelInput((s) => ({ ...s, [p.id]: e.target.value }))}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          addModel(p.id);
                        }
                      }}
                      placeholder="输入模型名称，回车添加"
                      className={inputCls}
                    />
                  </div>
                </div>

                {/* Card Footer */}
                <div className="flex items-center gap-2 px-6 py-3 border-t border-border">
                  {testResult[p.id] && (
                    <span className={`text-xs mr-auto ${testResult[p.id]!.success ? "text-green-400" : "text-red-400"}`}>
                      {testResult[p.id]!.message}
                    </span>
                  )}
                  <div className="flex items-center gap-2 ml-auto">
                    {!p.isBuiltin && (
                      <button
                        type="button"
                        onClick={() => handleDeleteProvider(p)}
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-sm text-red-400 hover:bg-red-500/10"
                      >
                        <Trash2 className="h-3.5 w-3.5" /> 删除
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => handleTestProvider(p)}
                      disabled={testingProvider[p.id] || edit.models.length === 0}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md border border-border text-sm hover:bg-accent disabled:opacity-50"
                    >
                      <Zap className={`h-3.5 w-3.5 ${testingProvider[p.id] ? "animate-pulse" : ""}`} />
                      {testingProvider[p.id] ? "测试中..." : "测试"}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSaveProvider(p)}
                      disabled={savingProvider[p.id]}
                      className="inline-flex items-center gap-1 px-4 py-1.5 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
                    >
                      <Save className="h-3.5 w-3.5" /> {savingProvider[p.id] ? "保存中..." : "保存"}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Section 2: Routing Config ────────────────────────────────── */}
      <div>
        <h2 className="text-2xl font-bold mb-4">LLM 调度配置</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {renderRoutingPanel("main", "主 LLM", mainRouting, savingMain)}
          {renderRoutingPanel("advisory", "Advisory LLM", advisoryRouting, savingAdvisory)}
        </div>
      </div>

      {/* ── Add Provider Modal ───────────────────────────────────────── */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60" onClick={() => setShowAddModal(false)} />
          <div className="relative w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-xl mx-4">
            <h3 className="text-lg font-semibold mb-4">添加自定义 Provider</h3>

            <div className="space-y-3">
              <div>
                <label className="block text-sm text-muted-foreground mb-1">名称 (唯一标识)</label>
                <input
                  type="text"
                  value={newProvider.name}
                  onChange={(e) => setNewProvider({ ...newProvider, name: e.target.value })}
                  placeholder="my-provider"
                  className={inputCls}
                />
              </div>
              <div>
                <label className="block text-sm text-muted-foreground mb-1">显示名称</label>
                <input
                  type="text"
                  value={newProvider.displayName}
                  onChange={(e) => setNewProvider({ ...newProvider, displayName: e.target.value })}
                  placeholder="My Provider"
                  className={inputCls}
                />
              </div>
              <div>
                <label className="block text-sm text-muted-foreground mb-1">Provider 类型</label>
                <select
                  value={newProvider.providerType}
                  onChange={(e) => setNewProvider({ ...newProvider, providerType: e.target.value })}
                  className={inputCls}
                >
                  <option value="openai_compatible">OpenAI Compatible</option>
                  <option value="anthropic_compatible">Anthropic Compatible</option>
                  <option value="gemini_native">Gemini Native</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-muted-foreground mb-1">API Key</label>
                <input
                  type="password"
                  value={newProvider.apiKey}
                  onChange={(e) => setNewProvider({ ...newProvider, apiKey: e.target.value })}
                  placeholder="sk-..."
                  className={inputCls}
                />
              </div>
              <div>
                <label className="block text-sm text-muted-foreground mb-1">Base URL</label>
                <input
                  type="text"
                  value={newProvider.baseUrl}
                  onChange={(e) => setNewProvider({ ...newProvider, baseUrl: e.target.value })}
                  placeholder="https://api.example.com/v1"
                  className={inputCls}
                />
              </div>
              <div>
                <label className="block text-sm text-muted-foreground mb-1">Timeout (秒)</label>
                <input
                  type="number"
                  min={1}
                  value={newProvider.timeout}
                  onChange={(e) => setNewProvider({ ...newProvider, timeout: Number(e.target.value) })}
                  className={inputCls}
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="px-4 py-1.5 rounded-md border border-border text-sm hover:bg-accent"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleAddProvider}
                className="px-4 py-1.5 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90"
              >
                创建
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
