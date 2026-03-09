import { useEffect, useState, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { Button } from "~/components/ui/button";
import { Switch } from "~/components/ui/switch";
import { Coins, Search, Save, RefreshCw } from "lucide-react";

interface SymbolsData {
  available: string[];
  enabled: string[];
}

const DEFAULT_SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"];

export default function SymbolsPage() {
  const [data, setData] = useState<SymbolsData>({ available: [], enabled: [] });
  const [enabledSet, setEnabledSet] = useState<Set<string>>(new Set(DEFAULT_SYMBOLS));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const fetchData = async () => {
    try {
      const res = await fetch("/api/symbols");
      const json = await res.json();
      setData(json);
      setEnabledSet(new Set(json.enabled));
    } catch {
      // use defaults
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const toggleSymbol = (symbol: string) => {
    setEnabledSet((prev) => {
      const next = new Set(prev);
      if (next.has(symbol)) {
        if (next.size <= 1) return prev; // 至少保留一个
        next.delete(symbol);
      } else {
        next.add(symbol);
      }
      return next;
    });
  };

  const saveSymbols = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch("/api/symbols", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: Array.from(enabledSet) }),
      });
      if (res.ok) {
        setMessage({ type: "success", text: "交易对配置已保存，将在下一个决策周期生效" });
      } else {
        const err = await res.json();
        setMessage({ type: "error", text: err.error || "保存失败" });
      }
    } catch {
      setMessage({ type: "error", text: "保存失败" });
    } finally {
      setSaving(false);
    }
  };

  // 合并可用列表和已启用列表（处理可用列表尚未加载的情况）
  const allSymbols = useMemo(() => {
    const set = new Set([...data.available, ...enabledSet]);
    return Array.from(set).sort();
  }, [data.available, enabledSet]);

  const filteredSymbols = useMemo(() => {
    if (!search.trim()) return allSymbols;
    const q = search.toUpperCase();
    return allSymbols.filter((s) => s.toUpperCase().includes(q));
  }, [allSymbols, search]);

  const hasChanges = useMemo(() => {
    const originalSet = new Set(data.enabled);
    if (originalSet.size !== enabledSet.size) return true;
    for (const s of enabledSet) {
      if (!originalSet.has(s)) return true;
    }
    return false;
  }, [data.enabled, enabledSet]);

  if (loading) {
    return <div className="p-8 text-center text-muted-foreground">加载中...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Coins className="h-6 w-6" />
          交易对管理
        </h1>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">
            已启用 {enabledSet.size} / {allSymbols.length} 个
          </span>
        </div>
      </div>

      {message && (
        <div
          className={`p-3 rounded-md ${
            message.type === "success"
              ? "bg-green-500/10 text-green-500 border border-green-500/20"
              : "bg-red-500/10 text-red-500 border border-red-500/20"
          }`}
        >
          {message.text}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center justify-between">
            <span className="flex items-center gap-2">
              交易对列表
              {data.available.length === 0 && (
                <span className="text-xs text-yellow-500 font-normal">
                  (交易所可用列表尚未加载，请等待 Trader 启动)
                </span>
              )}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={saveSymbols}
                disabled={saving || !hasChanges}
              >
                {saving ? (
                  <>
                    <RefreshCw className="mr-1 h-3 w-3 animate-spin" />
                    保存中...
                  </>
                ) : (
                  <>
                    <Save className="mr-1 h-3 w-3" />
                    保存
                  </>
                )}
              </Button>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* 搜索框 */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              placeholder="搜索交易对..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-9 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            {search && (
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">
                {filteredSymbols.length} 个结果
              </span>
            )}
          </div>

          {/* 快捷操作 */}
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEnabledSet(new Set(DEFAULT_SYMBOLS))}
            >
              仅默认 (3个)
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEnabledSet(new Set(allSymbols))}
            >
              全选
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEnabledSet(new Set(DEFAULT_SYMBOLS))}
            >
              重置
            </Button>
          </div>

          {/* Symbol 列表 */}
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {filteredSymbols.map((symbol) => {
              const isEnabled = enabledSet.has(symbol);
              const displayName = symbol.replace(":USDT", "").replace("/USDT", "");
              const baseSymbol = displayName.split("/")[0] || displayName;

              return (
                <div
                  key={symbol}
                  className={`flex items-center justify-between rounded-md border px-3 py-2 transition-colors ${
                    isEnabled
                      ? "border-primary/30 bg-primary/5"
                      : "border-border"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`h-2 w-2 rounded-full ${
                        isEnabled ? "bg-green-500" : "bg-muted"
                      }`}
                    />
                    <span className="font-mono text-sm font-medium">
                      {baseSymbol}
                    </span>
                    <span className="text-xs text-muted-foreground">/USDT</span>
                  </div>
                  <Switch
                    checked={isEnabled}
                    onCheckedChange={() => toggleSymbol(symbol)}
                  />
                </div>
              );
            })}
          </div>

          {filteredSymbols.length === 0 && (
            <div className="text-center text-sm text-muted-foreground py-8">
              没有匹配的交易对
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
