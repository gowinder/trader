import { useEffect, useState } from "react";
import { Save, SendHorizonal } from "lucide-react";

interface NotificationConfig {
  telegram_enabled: boolean;
  trade: {
    enabled: boolean;
    open_long: boolean;
    open_short: boolean;
    close_long: boolean;
    close_short: boolean;
    add_reduce: boolean;
    stop_loss_take_profit: boolean;
  };
  decision: {
    enabled: boolean;
    action: boolean;
    hold: boolean;
  };
  backtest: {
    enabled: boolean;
    completed: boolean;
  };
  advisory: {
    enabled: boolean;
    suggestion: boolean;
  };
}

const defaultConfig: NotificationConfig = {
  telegram_enabled: true,
  trade: {
    enabled: true,
    open_long: true,
    open_short: true,
    close_long: true,
    close_short: true,
    add_reduce: true,
    stop_loss_take_profit: true,
  },
  decision: {
    enabled: true,
    action: true,
    hold: false,
  },
  backtest: {
    enabled: true,
    completed: true,
  },
  advisory: {
    enabled: true,
    suggestion: true,
  },
};

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${
        disabled ? "cursor-not-allowed opacity-50" : ""
      } ${checked ? "bg-blue-600" : "bg-gray-300"}`}
    >
      <span
        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
          checked ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </button>
  );
}

function SwitchRow({
  label,
  checked,
  onChange,
  indent,
  disabled,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  indent?: boolean;
  disabled?: boolean;
}) {
  return (
    <div
      className={`flex items-center justify-between py-2 ${
        indent ? "pl-6" : ""
      } ${disabled ? "opacity-50" : ""}`}
    >
      <span className="text-sm font-medium">{label}</span>
      <Toggle checked={checked} onChange={onChange} disabled={disabled} />
    </div>
  );
}

export default function NotificationSettings() {
  const [config, setConfig] = useState<NotificationConfig>(defaultConfig);
  const [toast, setToast] = useState<{
    message: string;
    type: "success" | "error";
  } | null>(null);

  useEffect(() => {
    fetch("/api/notification-settings")
      .then((res) => res.json())
      .then((data) => {
        if (data && typeof data.telegram_enabled === "boolean") {
          setConfig(data);
        }
      })
      .catch(() => {
        showToast("加载配置失败", "error");
      });
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(timer);
  }, [toast]);

  function showToast(message: string, type: "success" | "error") {
    setToast({ message, type });
  }

  function update<K extends keyof NotificationConfig>(
    key: K,
    value: NotificationConfig[K]
  ) {
    setConfig((prev) => ({ ...prev, [key]: value }));
  }

  function updateSub<
    K extends "trade" | "decision" | "backtest" | "advisory",
    S extends keyof NotificationConfig[K],
  >(category: K, field: S, value: boolean) {
    setConfig((prev) => ({
      ...prev,
      [category]: { ...prev[category], [field]: value },
    }));
  }

  async function handleSave() {
    try {
      const res = await fetch("/api/notification-settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (res.ok) {
        showToast("保存成功", "success");
      } else {
        showToast("保存失败", "error");
      }
    } catch {
      showToast("保存失败", "error");
    }
  }

  async function handleTest() {
    try {
      const res = await fetch("/api/notification-settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ _action: "test" }),
      });
      if (res.ok) {
        showToast("测试消息已发送", "success");
      } else {
        showToast("发送失败", "error");
      }
    } catch {
      showToast("发送失败", "error");
    }
  }

  const globalDisabled = !config.telegram_enabled;

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">通知设置</h1>

      {toast && (
        <div
          className={`rounded-lg px-4 py-3 text-sm font-medium ${
            toast.type === "success"
              ? "bg-green-100 text-green-800"
              : "bg-red-100 text-red-800"
          }`}
        >
          {toast.message}
        </div>
      )}

      {/* Global Toggle */}
      <div className="rounded-lg border bg-card p-4">
        <SwitchRow
          label="🔔 Telegram 推送"
          checked={config.telegram_enabled}
          onChange={(v) => update("telegram_enabled", v)}
        />
      </div>

      {/* Trade */}
      <div className="rounded-lg border bg-card p-4">
        <SwitchRow
          label="📈 交易通知"
          checked={config.trade.enabled}
          onChange={(v) => updateSub("trade", "enabled", v)}
          disabled={globalDisabled}
        />
        <SwitchRow
          label="开多"
          checked={config.trade.open_long}
          onChange={(v) => updateSub("trade", "open_long", v)}
          indent
          disabled={globalDisabled || !config.trade.enabled}
        />
        <SwitchRow
          label="开空"
          checked={config.trade.open_short}
          onChange={(v) => updateSub("trade", "open_short", v)}
          indent
          disabled={globalDisabled || !config.trade.enabled}
        />
        <SwitchRow
          label="平多"
          checked={config.trade.close_long}
          onChange={(v) => updateSub("trade", "close_long", v)}
          indent
          disabled={globalDisabled || !config.trade.enabled}
        />
        <SwitchRow
          label="平空"
          checked={config.trade.close_short}
          onChange={(v) => updateSub("trade", "close_short", v)}
          indent
          disabled={globalDisabled || !config.trade.enabled}
        />
        <SwitchRow
          label="加仓/减仓"
          checked={config.trade.add_reduce}
          onChange={(v) => updateSub("trade", "add_reduce", v)}
          indent
          disabled={globalDisabled || !config.trade.enabled}
        />
        <SwitchRow
          label="止损/止盈触发"
          checked={config.trade.stop_loss_take_profit}
          onChange={(v) => updateSub("trade", "stop_loss_take_profit", v)}
          indent
          disabled={globalDisabled || !config.trade.enabled}
        />
      </div>

      {/* Decision */}
      <div className="rounded-lg border bg-card p-4">
        <SwitchRow
          label="🧠 决策通知"
          checked={config.decision.enabled}
          onChange={(v) => updateSub("decision", "enabled", v)}
          disabled={globalDisabled}
        />
        <SwitchRow
          label="有动作的决策"
          checked={config.decision.action}
          onChange={(v) => updateSub("decision", "action", v)}
          indent
          disabled={globalDisabled || !config.decision.enabled}
        />
        <SwitchRow
          label="持仓不动"
          checked={config.decision.hold}
          onChange={(v) => updateSub("decision", "hold", v)}
          indent
          disabled={globalDisabled || !config.decision.enabled}
        />
      </div>

      {/* Backtest */}
      <div className="rounded-lg border bg-card p-4">
        <SwitchRow
          label="📊 回测通知"
          checked={config.backtest.enabled}
          onChange={(v) => updateSub("backtest", "enabled", v)}
          disabled={globalDisabled}
        />
        <SwitchRow
          label="回测完成"
          checked={config.backtest.completed}
          onChange={(v) => updateSub("backtest", "completed", v)}
          indent
          disabled={globalDisabled || !config.backtest.enabled}
        />
      </div>

      {/* Advisory */}
      <div className="rounded-lg border bg-card p-4">
        <SwitchRow
          label="🤖 Advisory 通知"
          checked={config.advisory.enabled}
          onChange={(v) => updateSub("advisory", "enabled", v)}
          disabled={globalDisabled}
        />
        <SwitchRow
          label="AI 建议"
          checked={config.advisory.suggestion}
          onChange={(v) => updateSub("advisory", "suggestion", v)}
          indent
          disabled={globalDisabled || !config.advisory.enabled}
        />
      </div>

      {/* Buttons */}
      <div className="flex gap-4">
        <button
          onClick={handleSave}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          <Save className="h-4 w-4" />
          保存设置
        </button>
        <button
          onClick={handleTest}
          className="inline-flex items-center gap-2 rounded-lg border bg-white px-4 py-2 text-sm font-medium hover:bg-gray-50"
        >
          <SendHorizonal className="h-4 w-4" />
          发送测试消息
        </button>
      </div>
    </div>
  );
}
