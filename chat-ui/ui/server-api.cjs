/**
 * Vite dev server 中间件 —— 为 Web 模式 Settings 提供 HTTP API
 * 直接读写 ~/.openclaw/openclaw.json
 */
const fs = require("fs");
const path = require("path");
const https = require("https");
const http = require("http");

const HOME = process.env.HOME || process.env.USERPROFILE || "";
const CONFIG_PATH = path.join(HOME, ".openclaw", "openclaw.json");
const STATE_DIR = path.join(HOME, ".openclaw");

// ── Provider 预设 ──
const PROVIDER_PRESETS = {
  anthropic: { baseUrl: "https://api.anthropic.com/v1", api: "anthropic-messages" },
  openai: { baseUrl: "https://api.openai.com/v1", api: "openai-completions" },
  google: { baseUrl: "https://generativelanguage.googleapis.com/v1beta", api: "google-generative-ai" },
};

const MOONSHOT_SUB_PLATFORMS = {
  "moonshot-cn": { baseUrl: "https://api.moonshot.cn/v1", api: "openai-completions", providerKey: "moonshot" },
  "moonshot-ai": { baseUrl: "https://api.moonshot.ai/v1", api: "openai-completions", providerKey: "moonshot" },
  "kimi-code": { baseUrl: "https://api.kimi.com/coding", api: "anthropic-messages", providerKey: "kimi-coding" },
};

const CUSTOM_PROVIDER_PRESETS = {
  "minimax": { providerKey: "minimax", baseUrl: "https://api.minimax.io/anthropic", api: "anthropic-messages" },
  "minimax-cn": { providerKey: "minimax-cn", baseUrl: "https://api.minimaxi.com/anthropic", api: "anthropic-messages" },
  "zai-global": { providerKey: "zai", baseUrl: "https://api.z.ai/api/paas/v4", api: "openai-completions" },
  "zai-cn": { providerKey: "zai", baseUrl: "https://open.bigmodel.cn/api/paas/v4", api: "openai-completions" },
  "zai-cn-coding": { providerKey: "zai", baseUrl: "https://open.bigmodel.cn/api/coding/paas/v4", api: "openai-completions" },
  "volcengine": { providerKey: "volcengine", baseUrl: "https://ark.cn-beijing.volces.com/api/v3", api: "openai-completions" },
  "volcengine-coding": { providerKey: "volcengine", baseUrl: "https://ark.cn-beijing.volces.com/api/coding", api: "openai-completions" },
  "qwen": { providerKey: "qwen", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", api: "openai-completions" },
  "qwen-coding": { providerKey: "qwen", baseUrl: "https://coding.dashscope.aliyuncs.com/v1", api: "openai-completions" },
};

// ── 配置读写 ──
function readConfig() {
  try {
    if (!fs.existsSync(CONFIG_PATH)) return {};
    return JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
  } catch { return {}; }
}

function writeConfig(config) {
  fs.mkdirSync(STATE_DIR, { recursive: true });
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2), "utf-8");
}

// ── API Key 验证 ──
function httpRequest(url, opts) {
  return new Promise((resolve, reject) => {
    const mod = url.startsWith("https") ? https : http;
    const urlObj = new URL(url);
    const req = mod.request({
      hostname: urlObj.hostname,
      port: urlObj.port,
      path: urlObj.pathname + urlObj.search,
      method: opts.method || "GET",
      headers: opts.headers,
      timeout: 15000,
    }, (res) => {
      let body = "";
      res.on("data", (d) => body += d);
      res.on("end", () => {
        const code = res.statusCode || 0;
        if (code >= 200 && code < 300) resolve({ code, body });
        else if (code === 401 || code === 403) reject(new Error(`API Key 无效 (${code})`));
        else reject(new Error(`请求失败 (${code}): ${body.slice(0, 200)}`));
      });
    });
    req.on("error", (e) => reject(new Error(`网络错误: ${e.message}`)));
    req.on("timeout", () => { req.destroy(); reject(new Error("请求超时")); });
    if (opts.body) req.write(opts.body);
    req.end();
  });
}

async function verifyProvider(params) {
  const { provider, apiKey, baseURL, subPlatform, apiType, modelID, customPreset } = params;
  try {
    switch (provider) {
      case "anthropic":
        await httpRequest("https://api.anthropic.com/v1/messages", {
          method: "POST",
          headers: { "x-api-key": apiKey, "anthropic-version": "2023-06-01", "content-type": "application/json" },
          body: JSON.stringify({ model: modelID || "claude-haiku-4-5-20251001", max_tokens: 1, messages: [{ role: "user", content: "hi" }] }),
        });
        break;
      case "openai":
        await httpRequest("https://api.openai.com/v1/models", { headers: { Authorization: `Bearer ${apiKey}` } });
        break;
      case "google":
        await httpRequest(`https://generativelanguage.googleapis.com/v1beta/models?key=${apiKey}`, {});
        break;
      case "moonshot": {
        const sub = MOONSHOT_SUB_PLATFORMS[subPlatform || "moonshot-cn"];
        if (subPlatform === "kimi-code") {
          await httpRequest(`${sub.baseUrl}/v1/messages`, {
            method: "POST",
            headers: { "x-api-key": apiKey, "anthropic-version": "2023-06-01", "content-type": "application/json" },
            body: JSON.stringify({ model: modelID || "k2p5", max_tokens: 1, messages: [{ role: "user", content: "hi" }] }),
          });
        } else {
          await httpRequest(`${sub.baseUrl}/models`, { headers: { Authorization: `Bearer ${apiKey}` } });
        }
        break;
      }
      case "custom": {
        const pre = customPreset ? CUSTOM_PROVIDER_PRESETS[customPreset] : undefined;
        const effectiveBase = (pre ? pre.baseUrl : baseURL || "").replace(/\/$/, "");
        const effectiveApi = pre ? pre.api : (apiType || "openai-completions");
        if (!effectiveBase) throw new Error("Base URL 不能为空");
        if (!modelID) throw new Error("Model ID 不能为空");
        if (effectiveApi === "anthropic-messages") {
          await httpRequest(`${effectiveBase}/v1/messages`, {
            method: "POST",
            headers: { "x-api-key": apiKey, "anthropic-version": "2023-06-01", "content-type": "application/json" },
            body: JSON.stringify({ model: modelID, max_tokens: 1, messages: [{ role: "user", content: "hi" }] }),
          });
        } else {
          await httpRequest(`${effectiveBase}/chat/completions`, {
            method: "POST",
            headers: { Authorization: `Bearer ${apiKey}`, "content-type": "application/json" },
            body: JSON.stringify({ model: modelID, max_tokens: 1, messages: [{ role: "user", content: "hi" }] }),
          });
        }
        break;
      }
      default:
        return { success: false, message: `未知 Provider: ${provider}` };
    }
    return { success: true };
  } catch (err) {
    return { success: false, message: err.message || String(err) };
  }
}

// ── 从配置提取 provider 信息 ──
function extractProviderInfo(config) {
  const primary = config?.agents?.defaults?.model?.primary || "";
  const [provKey, ...modelParts] = primary.split("/");
  const modelID = modelParts.join("/");
  const provConfig = config?.models?.providers?.[provKey] || {};

  // 反推 provider 名称
  let provider = provKey;
  let subPlatform = "";
  if (provKey === "kimi-coding") { provider = "moonshot"; subPlatform = "kimi-code"; }
  else if (provKey === "moonshot") { provider = "moonshot"; subPlatform = "moonshot-cn"; }
  else if (PROVIDER_PRESETS[provKey]) { provider = provKey; }
  else { provider = "custom"; }

  return {
    provider,
    modelID,
    apiKey: provConfig.apiKey || "",
    baseURL: provConfig.baseUrl || "",
    api: provConfig.api || "",
    subPlatform,
    configuredModels: (provConfig.models || []).map(m => typeof m === "string" ? m : m.id),
    savedProviders: {},
  };
}

// ── 保存 provider 配置 ──
function saveProvider(config, params) {
  const { provider, apiKey, modelID, baseURL, api, subPlatform, supportImage, customPreset } = params;

  config.models = config.models || {};
  config.models.providers = config.models.providers || {};
  config.agents = config.agents || {};
  config.agents.defaults = config.agents.defaults || {};
  config.agents.defaults.model = config.agents.defaults.model || {};

  if (provider === "moonshot") {
    const sub = MOONSHOT_SUB_PLATFORMS[subPlatform || "moonshot-cn"];
    const provKey = sub.providerKey;
    config.models.providers[provKey] = {
      apiKey,
      baseUrl: sub.baseUrl,
      api: sub.api,
      models: [{ id: modelID, name: modelID, input: ["text", "image"] }],
    };
    config.agents.defaults.model.primary = `${provKey}/${modelID}`;
  } else {
    const customPre = customPreset ? CUSTOM_PROVIDER_PRESETS[customPreset] : undefined;
    const configKey = customPre ? customPre.providerKey : provider;
    const preset = PROVIDER_PRESETS[provider];
    const effectiveBase = customPre ? customPre.baseUrl : (preset ? preset.baseUrl : baseURL);
    const effectiveApi = customPre ? customPre.api : (preset ? preset.api : (api || "openai-completions"));
    const input = supportImage !== false ? ["text", "image"] : ["text"];

    config.models.providers[configKey] = {
      apiKey,
      baseUrl: effectiveBase,
      api: effectiveApi,
      models: [{ id: modelID, name: modelID, input }],
    };
    config.agents.defaults.model.primary = `${configKey}/${modelID}`;
  }
}

// ── 读取 body ──
function readBody(req) {
  return new Promise((resolve) => {
    let data = "";
    req.on("data", (chunk) => data += chunk);
    req.on("end", () => {
      try { resolve(JSON.parse(data)); }
      catch { resolve({}); }
    });
  });
}

// ── 中间件 ──
function settingsApiMiddleware(req, res, next) {
  if (!req.url.startsWith("/__api/settings/")) return next();

  const route = req.url.replace("/__api/settings/", "").split("?")[0];
  res.setHeader("Content-Type", "application/json");

  const handle = async () => {
    try {
      switch (route) {
        case "get-config": {
          const config = readConfig();
          return res.end(JSON.stringify({ success: true, data: extractProviderInfo(config) }));
        }
        case "verify-key": {
          const params = await readBody(req);
          const result = await verifyProvider(params);
          return res.end(JSON.stringify(result));
        }
        case "save-provider": {
          const params = await readBody(req);
          const config = readConfig();
          saveProvider(config, params);
          writeConfig(config);
          return res.end(JSON.stringify({ success: true }));
        }
        case "get-channel-config": {
          const config = readConfig();
          const feishu = config?.channels?.feishu || {};
          return res.end(JSON.stringify({
            success: true,
            data: {
              appId: feishu.appId || "", appSecret: feishu.appSecret || "",
              enabled: config?.plugins?.entries?.feishu?.enabled === true,
              dmPolicy: feishu.dmPolicy || "pairing", dmScope: config?.session?.dmScope || "main",
              groupPolicy: feishu.groupPolicy || "allowlist",
            }
          }));
        }
        case "save-channel": {
          const params = await readBody(req);
          const config = readConfig();
          config.plugins = config.plugins || {};
          config.plugins.entries = config.plugins.entries || {};
          config.channels = config.channels || {};
          config.channels.feishu = config.channels.feishu || {};
          if (params.enabled === false) {
            config.plugins.entries.feishu = { ...(config.plugins.entries.feishu || {}), enabled: false };
          } else {
            config.plugins.entries.feishu = { enabled: true };
            config.channels.feishu.appId = params.appId;
            config.channels.feishu.appSecret = params.appSecret;
          }
          writeConfig(config);
          return res.end(JSON.stringify({ success: true }));
        }
        case "get-advanced": {
          return res.end(JSON.stringify({
            success: true,
            data: { browserProfile: "openclaw", sessionMemory: true, imessage: false, launchAtLogin: false, cliInstalled: false, clawHubRegistry: "" }
          }));
        }
        case "get-about-info": {
          return res.end(JSON.stringify({
            success: true,
            data: { version: "web", buildDate: "", os: process.platform, arch: process.arch }
          }));
        }
        default:
          return res.end(JSON.stringify({ success: true, data: null }));
      }
    } catch (err) {
      return res.end(JSON.stringify({ success: false, message: err.message || String(err) }));
    }
  };

  handle();
}

module.exports = { settingsApiMiddleware };
