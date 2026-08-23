#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


EXPECTED_2_1_235 = {
    "environment_schema": 842,
    "environment_callsites": 2548,
    "typed_named_callsites": 2161,
    "typed_used_names": 762,
    "typed_declaration_only": 80,
    "untyped_named_names": 137,
    "untyped_named_callsites": 242,
    "dynamic_environment_callsites": 145,
    "feature_keys": 361,
    "feature_callsites": 498,
    "feature_resolvable_static_callsites": 455,
    "feature_direct_literal_callsites": 444,
    "feature_nonliteral_syntax_callsites": 54,
    "feature_resolved_nonliteral_callsites": 11,
    "feature_unresolved_dynamic_callsites": 43,
    "dynamic_config_static_keys": 6,
    "dynamic_config_callsites": 12,
}


ENV_MEANINGS: dict[str, tuple[str, str]] = {
    "ANTHROPIC_CONFIG_DIR": (
        "覆盖 Anthropic profile/config 根目录，改变 config、credentials 和 active_config 的查找位置；它不改变 Claude Code 自身 CLAUDE_CONFIG_DIR，目录存在也不证明 profile 合法。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_PROFILE": (
        "显式选择 WIF/profile；只有 profile 存在且 authentication.type 为 oidc_federation 或 user_oauth 才成为 profile-explicit credential source，非法名称或类型不会伪装成凭据。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_FEDERATION_RULE_ID": (
        "与 organization 和 identity 输入共同构成 env-quad OIDC federation 候选；单独设置不能完成 token exchange，也不能证明远端 federation rule 可用。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_ORGANIZATION_ID": (
        "绑定 env-quad OIDC federation 候选的 organization；它需与 federation rule 和 identity material 配套，不能当作当前登录组织的证明。",
        "models-auth-providers-request.md",
    ),
    "APPDATA": (
        "参与 Windows Anthropic profile config-root fallback；只在更高优先级 ANTHROPIC_CONFIG_DIR 缺失时推导文件查找位置，不授予 profile 或 token 权限。",
        "models-auth-providers-request.md",
    ),
    "USERPROFILE": (
        "参与 Windows Anthropic profile config-root fallback；它只决定候选路径，不证明 profile 文件存在、类型有效或凭据可用。",
        "models-auth-providers-request.md",
    ),
    "XDG_CONFIG_HOME": (
        "参与 Unix Anthropic profile config-root fallback；只决定配置文件查找位置，不改变 credential precedence 或授予 token 权限。",
        "models-auth-providers-request.md",
    ),
    "HOME": (
        "作为 Unix profile/config-root 和多个本地状态目录的 fallback；具体 consumer 各自追加子路径，HOME 本身不授予 profile、plugin、session 或 tool 权限。",
        "models-auth-providers-request.md",
    ),
    "AWS_BEARER_TOKEN_BEDROCK": (
        "Mantle/Anthropic-on-AWS bearer credential source，命中时与普通 AWS credential signer 分流；仍受 provider selector、region/workspace、网络和上游接受度约束。",
        "models-auth-providers-request.md",
    ),
    "CLAUDE_CODE_USE_ANTHROPIC_AWS": (
        "在 provider precedence 中选择 Anthropic-on-AWS client；真实 AWS identity、workspace、region、网络和 deployment capability 仍需运行验证。",
        "models-auth-providers-request.md",
    ),
    "CLAUDE_CODE_USE_ANTHROPIC_GOOGLE_CLOUD": (
        "在 provider precedence 中选择 Anthropic-on-Google-Cloud client；project、location、workspace、Google identity 和 deployment capability 是附加 gate。",
        "models-auth-providers-request.md",
    ),
    "CLAUDE_CODE_USE_MANTLE": (
        "选择 Mantle client；credential path 优先 bearer、否则回退 AWS signer，它不等于普通 Bedrock wire 形态或服务端已接受该身份。",
        "models-auth-providers-request.md",
    ),
    "CLAUDE_CODE_EXTRA_BODY": (
        "把 JSON object 解析为 request-body overlay，可覆盖较早装配的普通字段；output_config、speed、cache diagnostics 等受管尾字段随后重建，非法 JSON 或非 object 回退为空。",
        "models-auth-providers-request.md",
    ),
    "CLAUDE_CODE_OAUTH_TOKEN": (
        "进程注入的 OAuth bearer source，可进入 Authorization header；它通常没有本地 refresh token，因此 401、续期和 logout 生命周期不同于已保存的 claude.ai 登录。",
        "auth-account-and-subscription-lifecycle.md",
    ),
    "CLAUDE_CODE_OAUTH_REFRESH_TOKEN": (
        "启动 OAuth refresh-token 登录的输入；必须与 scopes 同时存在，exchange 成功前不会替换旧持久凭据，远端撤销状态仍需服务端确认。",
        "auth-account-and-subscription-lifecycle.md",
    ),
    "CLAUDE_CODE_OAUTH_SCOPES": (
        "空格分隔的 refresh-token scope contract；缺失时本地退出，remote runner 也用它声明 inference、CCR 和 file-upload 能力，但字符串存在不证明服务端已授权。",
        "auth-account-and-subscription-lifecycle.md",
    ),
    "CLAUDE_CODE_OAUTH_CLIENT_ID": (
        "可选覆盖 refresh-token exchange 的 OAuth client_id；不会替代 refresh token、scopes、identity validation 或回调/服务端校验。",
        "auth-account-and-subscription-lifecycle.md",
    ),
    "AGENT_PROXY_AUTH_TOKEN": (
        "Remote/CCR Agent Proxy 的 bootstrap bearer token。初始化入口读取后立即从环境删除；它只用于建立到 hosted policy egress proxy 的 WebSocket relay，不会继续自然继承给普通工具子进程。",
        "network-proxy-ca-and-mtls.md",
    ),
    "AGENT_PROXY_URL": (
        "Remote/CCR Agent Proxy 的独立 relay base URL。初始化入口读取后立即从环境删除；存在时进入 standalone relay 形态，并覆盖默认 CCR/API base URL。",
        "network-proxy-ca-and-mtls.md",
    ),
    "ANTHROPIC_API_KEY": (
        "Anthropic API key \u51ed\u636e\uff1b\u5df2\u9a8c\u8bc1\u8bf7\u6c42\u8def\u5f84\u53d1\u9001 x-api-key\uff0c\u4e14\u4e0d\u4f1a\u540c\u65f6\u53d1\u9001 Authorization\u3002",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_AUTH_TOKEN": (
        "Bearer \u51ed\u636e\uff1b\u5df2\u9a8c\u8bc1\u8bf7\u6c42\u8def\u5f84\u53d1\u9001 Authorization: Bearer\uff0c\u4e14\u4e0d\u4f1a\u540c\u65f6\u53d1\u9001 x-api-key\u3002",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_BASE_URL": (
        "\u9009\u62e9 API endpoint\uff0c\u540c\u65f6\u6539\u53d8 first-party host \u5224\u5b9a\uff1b\u81ea\u5b9a\u4e49 host \u4e0d\u4f1a\u81ea\u52a8\u7ee7\u627f\u4e00\u65b9\u79c1\u6709\u80fd\u529b\u3002",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_MODEL": (
        "\u63d0\u4f9b\u6a21\u578b\u9009\u62e9\u8f93\u5165\uff0c\u4f46\u4e3b session\u3001subagent\u3001compact\u3001background \u548c\u663e\u5f0f CLI \u53c2\u6570\u53ef\u4ee5\u5206\u522b\u6301\u6709\u4e0d\u540c\u6a21\u578b\u3002",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_BETAS": (
        "\u5411\u8bf7\u6c42\u88c5\u914d\u63d0\u4f9b beta identifier\uff1b\u53d8\u91cf\u5b58\u5728\u4e0d\u8bc1\u660e\u6240\u9009 provider \u6216 deployment \u63a5\u53d7\u8fd9\u4e9b beta\u3002",
        "models-auth-providers-request.md",
    ),
    "CLAUDE_CODE_USE_BEDROCK": (
        "\u5728\u8bf7\u6c42\u88c5\u914d\u524d\u9009\u62e9 Bedrock provider \u5206\u652f\uff1b\u771f\u5b9e AWS identity \u4e0e\u670d\u52a1\u53ef\u8fbe\u6027\u4ecd\u662f\u8fd0\u884c\u65f6\u8fb9\u754c\u3002",
        "models-auth-providers-request.md",
    ),
    "CLAUDE_CODE_USE_FOUNDRY": (
        "\u9009\u62e9 Foundry provider \u5206\u652f\uff1bdeployment capability \u4e0e Azure identity \u4ecd\u662f\u8fd0\u884c\u65f6\u8fb9\u754c\u3002",
        "models-auth-providers-request.md",
    ),
    "CLAUDE_CODE_USE_VERTEX": (
        "\u9009\u62e9 Vertex provider \u5206\u652f\uff1bproject\u3001location \u4e0e Google identity \u4ecd\u662f\u8fd0\u884c\u65f6\u8fb9\u754c\u3002",
        "models-auth-providers-request.md",
    ),
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": (
        "\u628a\u5ba2\u6237\u7aef\u6d41\u91cf\u7ea7\u522b\u964d\u5230 essential-traffic\uff0c\u5173\u95ed\u4e00\u65b9 analytics\u3001\u5728\u7ebf Feature Evaluation \u548c\u5176\u4ed6\u975e\u5fc5\u8981 lookup\uff1b\u5b83\u4e0d\u4f1a\u5173\u95ed\u6a21\u578b\u8bf7\u6c42\u3002",
        "telemetry.md",
    ),
    "DISABLE_TELEMETRY": (
        "\u5173\u95ed telemetry \u7c7b\u6d41\u91cf\uff0c\u56e0\u6b64\u4e5f\u53c2\u4e0e GrowthBook \u5916\u5c42 enable gate\uff1b\u5b83\u4e0d\u662f permission \u6216 sandbox \u63a7\u5236\u3002",
        "telemetry.md",
    ),
    "DO_NOT_TRACK": (
        "\u53c2\u4e0e no-telemetry \u6d41\u91cf gate\uff1b\u5728\u7ebf\u6c42\u503c\u590d\u7528\u8be5\u5916\u5c42 gate\uff0c\u56e0\u6b64\u4e0b\u6e38 feature \u53ef\u7528\u6027\u4e5f\u53ef\u80fd\u53d8\u5316\u3002",
        "telemetry.md",
    ),
    "CLAUDE_CODE_GB_DISK_CACHE_WHEN_TELEMETRY_OFF": (
        "\u5728\u7ebf telemetry/evaluation \u5173\u95ed\u65f6\uff0c\u5141\u8bb8\u4e00\u65b9 provider \u8bfb\u53d6 stale-capable \u7684 GrowthBook \u78c1\u76d8\u72b6\u6001\uff1b\u4e0d\u4f1a\u628a\u65e7\u7f13\u5b58\u53d8\u6210 fresh\u3002",
        "feature-flags-remote-config.md",
    ),
    "CLAUDE_CODE_BRIEF": (
        "Brief 的显式环境入口，同时参与 entitlement 与启动来源判定；consumer 仍要求 host、工具装配和 Brief gate 成立，不能据此推断 SendUserMessage 已被调用或内容已渲染。",
        "brief-mode-and-user-visible-output.md",
    ),
    "CLAUDE_CODE_BRIEF_UPLOAD": (
        "允许 Brief 附件进入 env_brief_upload lane；各 lane 复用同一 OAuth 上传函数，HTTP success 和 file_uuid 只证明上传响应，不证明远端 viewer 已展示附件。",
        "brief-mode-and-user-visible-output.md",
    ),
    "CLAUDE_CODE_CERT_STORE": (
        "选择 bundled、system 或二者组合的 CA store 输入；非法 token 会失败，CA 信任与 client-certificate 身份、transport 覆盖范围仍是分开的控制面。",
        "network-proxy-ca-and-mtls.md",
    ),
    "CLAUDE_CODE_CLIENT_CERT": (
        "提供 mTLS client certificate 路径；consumer 要求它与 CLAUDE_CODE_CLIENT_KEY 配对、加载成功，并按连接生命周期应用，单一 transport 成功不能外推全部网络路径。",
        "network-proxy-ca-and-mtls.md",
    ),
    "CLAUDE_CODE_CLIENT_KEY": (
        "提供与 client certificate 配对的 mTLS private-key 路径；缺失配对项、文件读取或 key 解密失败都会阻止该身份材料生效。",
        "network-proxy-ca-and-mtls.md",
    ),
    "CLAUDE_CODE_CLIENT_KEY_PASSPHRASE": (
        "提供 mTLS private key 的解密输入；它属于敏感本地材料，只参与 key 加载，不能单独建立 client identity 或证明握手成功。",
        "network-proxy-ca-and-mtls.md",
    ),
    "CLAUDE_CODE_DISABLE_MTLS_RELOAD_ON_STALE_CONNECTION": (
        "关闭 stale connection 触发的 mTLS material reload 分支；已有连接、证书文件变化、重连和各 transport 的 agent 生命周期仍分别持有状态。",
        "network-proxy-ca-and-mtls.md",
    ),
    "CLAUDE_CODE_REPL": (
        "开启 REPL/programmatic tool runtime 的客户端入口；实际可达性还取决于 entrypoint、variant、宿主 bridge 和工具注册状态。",
        "repl-programmatic-tool-runtime.md",
    ),
    "CLAUDE_CODE_ENTRYPOINT": (
        "选择内部程序入口和宿主启动路径；不同入口拥有不同协议与生命周期，设置该值不等于 REPL、worker 或 bridge 已完成初始化。",
        "repl-programmatic-tool-runtime.md",
    ),
    "CLAUDE_REPL_VARIANT": (
        "选择 REPL runtime variant；consumer 仍检查 REPL gate、host 能力和会话状态，variant 名称本身不证明对应工具已进入请求。",
        "repl-programmatic-tool-runtime.md",
    ),
    "DISABLE_ERROR_REPORTING": (
        "关闭 error-reporting lane；first-party analytics、OTEL、Datadog、debug log 和 diagnostics 分别有独立 gate，因此不能把它解释为关闭全部遥测。",
        "telemetry.md",
    ),
    "OTEL_LOG_TOOL_CONTENT": (
        "允许 OTEL log/export 路径包含工具内容；这是隐私敏感开关，仍受 telemetry enable、exporter 配置、content truncation 和具体字段构造约束。",
        "telemetry.md",
    ),
    "CLAUDE_CODE_OTEL_CONTENT_MAX_LENGTH": (
        "设置 OTEL content 字段的本地截断上限；它限制单字段暴露长度，不限制事件数量，也不替代关闭 content logging 的 gate。",
        "telemetry.md",
    ),
    "CLAUDE_CODE_OTEL_FLUSH_TIMEOUT_MS": (
        "设置 OTEL flush deadline；超时只限定关闭/刷新等待预算，不能证明 collector 已接收、持久化或导出成功。",
        "telemetry.md",
    ),
    "CLAUDE_CODE_OTEL_SHUTDOWN_TIMEOUT_MS": (
        "设置 OTEL provider shutdown deadline；到期后客户端停止等待，尚未确认的 batch 可能丢失，且不影响其他 telemetry lane 的关闭策略。",
        "telemetry.md",
    ),
    "CLAUDE_CODE_STOP_HOOK_BLOCK_CAP": (
        "限制 Stop hook 连续阻塞和 Agent Loop re-entry 次数；达到 cap 后停止继续回灌，已完成的工具或远端副作用不会因此回滚。",
        "active-goal-and-stop-loop.md",
    ),
    "CLAUDE_CODE_MAX_RETRIES": (
        "限制模型/API attempt 的 retry budget；它与 Agent Loop max turns、工具调用数和 provider/model fallback 是不同计数器。",
        "resilience-and-recovery.md",
    ),
    "ENABLE_PROMPT_CACHING_1H": (
        "开启一小时 prompt-cache eligibility 分支；客户端仍按请求类型、provider 和 breakpoint 选择 cache_control，真实 cache hit 与计费结果属于服务端 Boundary。",
        "context-governance-and-caching.md",
    ),
    "CLAUDE_CODE_ALWAYS_ENABLE_EFFORT": (
        "强制让 effort 选择路径保持可用；实际 request effort 仍受显式 level、模型支持、组织 ceiling 和 provider compatibility 约束。",
        "thinking-effort-and-fast-mode.md",
    ),
    "CLAUDE_CODE_EFFORT_LEVEL": (
        "提供 effort level 输入并参与命令、设置与环境 precedence；最终 request 字段仍需通过模型 capability、组织上限和兼容性检查。",
        "thinking-effort-and-fast-mode.md",
    ),
    "CLAUDE_CODE_DISABLE_FAST_MODE": (
        "关闭 Fast Mode/service-tier 客户端分支；它不关闭普通模型调用，也不改变模型本身的 thinking/effort capability。",
        "thinking-effort-and-fast-mode.md",
    ),
    "CLAUDE_CODE_DISABLE_ADVISOR_TOOL": (
        "Advisor eligibility 的首个硬 disable gate；true 时立即返回 false，不再读取 first-party、experimental feature、catalog rank 或 server-tool 组装路径。",
        "advisor-dual-model-runtime.md",
    ),
    "DISABLE_BRIEF_MODE_STOP_HOOK": (
        "只关闭 Brief 主线程/SDK turn 在漏调 SendUserMessage 时注入 sentinel 并 re-entry 的 post-turn enforcement；不关闭 entitlement、Brief 工具或已经完成的消息/附件副作用。",
        "brief-mode-and-user-visible-output.md",
    ),
    "CLAUDE_CODE_SESSION_LOG": (
        "在本版可见 consumer 中写入 concurrent-session PID metadata 的 logPath 字段；未观察到该变量自身创建或开启 session recorder，文件写入 owner 属于独立 Boundary。",
        "telemetry.md",
    ),
    "CLAUDE_CODE_PERFETTO_TRACE": (
        "本版读取该值并写 Perfetto 初始化 debug 消息；span bridge 仅在 owner l4 非空时工作，但发布物可见路径中 l4 保持 null，未观察到 recorder 构造或 trace 文件输出。",
        "telemetry.md",
    ),
    "BETA_TRACING_ENDPOINT": (
        "仅在 detailed beta-tracing 资格成立时，为 delegate trace/log exporter 拼接 /v1/traces 和 /v1/logs；endpoint 存在本身不会启用 tracing 或绕过 exporter gate。",
        "telemetry.md",
    ),
    "CLAUDE_CODE_DIAGNOSTICS_FILE": (
        "选择本地 diagnostics JSONL sink；未设置时 writer 直接返回，写文件成功只证明本地 side effect，不证明内容被网络上传。",
        "telemetry.md",
    ),
    "CLAUDE_CODE_OTEL_DIAG_STDERR": (
        "把 OTEL SDK error diagnostics 同步写到 stderr；普通 tool/MCP child env 会 scrub 它，且该变量不启用任何 exporter。",
        "telemetry.md",
    ),
    "CLAUDE_CODE_PROFILE_QUERY": (
        "开启 query phase marks、memory snapshots 与报告生成，覆盖 context load、autocompact、tool schema、TTFB 和 tool execution；它是本地 profiler，不等于 OTEL export。",
        "telemetry.md",
    ),
    "CLAUDE_CODE_PROFILE_STARTUP": (
        "强制启动 startup profiling，否则还存在抽样路径；consumer 记录 bootstrap checkpoint/span，但开关存在不证明报告已持久化或上传。",
        "telemetry.md",
    ),
    "CLAUDE_CODE_TEE_SDK_STDOUT": (
        "在非 bridge remote transport 中把 session-state、turn-start 和可投影事件 tee 到 activity/stdout；不复制 transcript_mirror，也不改变 CCR 主 transport ownership。",
        "telemetry.md",
    ),
    "CLAUDE_DEBUG": (
        "让捕获到的 Node warning 同时进入 debug warning 输出；warning telemetry 仍独立记录，它不是通用 DEBUG namespace 或遥测总开关。",
        "telemetry.md",
    ),
    "DEBUG": (
        "驱动 bundled dependencies 的 namespace debug，并在 self-hosted setup/doctor 路径打印经脱敏的 spawn argv；可能扩大本地 stderr，不等于一方 telemetry 已启用。",
        "telemetry.md",
    ),
    "OTEL_EXPORTER_OTLP_ENDPOINT": (
        "generic OTLP base endpoint；logs、metrics 和 traces 的 signal-specific endpoint 可覆盖，Gateway 路径还可锁定自己的出口，因此不能只检查这一项。",
        "telemetry.md",
    ),
    "OTEL_EXPORTER_OTLP_PROTOCOL": (
        "generic OTLP protocol fallback；signal-specific protocol 优先，未知值在 exporter 构造期报错，但不等于 CLI 模型请求本身失败。",
        "telemetry.md",
    ),
    "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE": (
        "控制 metric temporality；未显式设置时 bootstrap 写 delta，self-hosted Prometheus bridge 可显式改为 cumulative。",
        "telemetry.md",
    ),
    "OTEL_LOGS_EXPORTER": (
        "选择 logs exporter，如 console、otlp 或 none；仍需 telemetry enable、endpoint/protocol 构造成功，Gateway/Cowork 还可移除 console 或注入 otlp。",
        "telemetry.md",
    ),
    "OTEL_METRICS_EXPORTER": (
        "选择 metrics exporter，如 console、otlp 或 prometheus；未知类型失败，remote runner 可把 Prometheus child 改接 loopback OTLP。",
        "telemetry.md",
    ),
    "OTEL_TRACES_EXPORTER": (
        "选择 traces exporter；还需 enhanced/session-tracing eligibility，设置 otlp 不证明 span 已被 collector 接收或持久化。",
        "telemetry.md",
    ),
    "OTEL_RESOURCE_ATTRIBUTES": (
        "解析附加 resource attributes；identity/user 字段可受隐私路径过滤，remote runner 会补 session/client attributes，不能假定原字符串原样发送。",
        "telemetry.md",
    ),
    "OTEL_LOG_USER_PROMPTS": (
        "允许 prompt 正文替代 <REDACTED> 进入 OTEL log/span，属于显式敏感内容 gate；本版正向 collector Probe 已证明默认与开启后的 wire 差异。",
        "telemetry.md",
    ),
    "OTEL_LOG_ASSISTANT_RESPONSES": (
        "控制 assistant content；未显式设置时兼容继承 user-prompt gate，仍受 content length、telemetry 和 exporter gate 约束。",
        "telemetry.md",
    ),
    "OTEL_LOG_TOOL_DETAILS": (
        "扩大工具相关结构化 details；它与 OTEL_LOG_TOOL_CONTENT 分开，details=true 不表示无上限记录所有 input/result。",
        "telemetry.md",
    ),
    "OTEL_LOG_RAW_API_BODIES": (
        "开启 raw API body capture，支持 inline/file 配置形态；范围可包含完整历史，必须独立于 prompt/tool content gate 审计，文件模式也不证明网络上传。",
        "telemetry.md",
    ),
    "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING": (
        "仅对 Opus/Sonnet 4.6 request 把 adaptive thinking 选择压回 fixed budget；它不关闭 thinking，model override、effort 和 capability 仍参与最终配置。",
        "thinking-effort-and-fast-mode.md",
    ),
    "DISABLE_INTERLEAVED_THINKING": (
        "阻止 request 加入 interleaved-thinking beta descriptor；不删除普通/fixed thinking，也不证明目标 provider 原本会接受该 beta。",
        "thinking-effort-and-fast-mode.md",
    ),
    "MAX_THINKING_TOKENS": (
        "既参与产品层 thinking on/off（大于 0）又作为未显式 thinking config 时的 budget/disabled override；最终 budget 仍会被 max output 夹在合法范围。",
        "thinking-effort-and-fast-mode.md",
    ),
    "DISABLE_AUTO_COMPACT": (
        "只关闭自动 compact 调度；手动 /compact 仍可达，与同时关闭手动、自动和提示路径的 DISABLE_COMPACT 范围不同。",
        "context-governance-and-caching.md",
    ),
    "DISABLE_COMPACT": (
        "关闭手动命令、自动/预计算 compact 及相关提示路径；不会删除既有 transcript、memory、prompt-cache service state 或外部工具副作用。",
        "context-governance-and-caching.md",
    ),
    "DISABLE_PROMPT_CACHING": (
        "阻止 request 写 cache_control marker；wire Probe 已证明 marker 从 3 变 0，但不能外推服务端账单、已有 cache 清除或 provider 之外的历史状态。",
        "context-governance-and-caching.md",
    ),
    "FORCE_PROMPT_CACHING_5M": (
        "在 cache TTL precedence 中强制 5 分钟并高于一小时入口；provider 接受度、真实 hit、retention 与计费仍属服务端 Boundary。",
        "context-governance-and-caching.md",
    ),
    "ENABLE_TOOL_SEARCH": (
        "解析 bool、force、auto 和 auto:N，按工具 schema 字符体积与模型窗口阈值决定 defer；不是简单开关，也不证明 deferred tool 最终被发现或允许执行。",
        "context-governance-and-caching.md",
    ),
    "USE_API_CONTEXT_MANAGEMENT": (
        "2.1.235 的环境变量分支被 && false 硬封，单独设置无效；可达 context_management 来自模型或远程 capability，这是已确认 dead env branch，不是未知 Boundary。",
        "context-governance-and-caching.md",
    ),
    "MAX_STRUCTURED_OUTPUT_RETRIES": (
        "覆盖默认 5 次 StructuredOutput 尝试预算；耗尽返回专用 terminal error，不回滚之前工具副作用，schema 正确也不等于业务语义正确。",
        "structured-output-and-schema-contract.md",
    ),
    "CLAUDE_BG_ISOLATION": (
        "选择 background checkout 写保护 worktree|none；worktree 模式在共享 checkout 前置拒绝 Edit/Write，不负责 Git merge、文件 checkpoint 或副作用回滚。",
        "cloud-background-channels.md",
    ),
    "CLAUDE_BG_PTY_AUTH": (
        "PTY host 启动时读取后立即从 env 删除，可被一次性 token file 的 ptyAuth 覆盖；只认证 socket input/control，不授权 child command 本身。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_BG_RENDEZVOUS_SOCK": (
        "为 worker 指定 supervisor rendezvous socket；worker 建立 server 后清理 socket/token env，通道断开不会回滚 child side effects。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_CODE_DAEMON_COLD_START": (
        "以最高优先级选择 transient|ask，再回落 trusted settings、GrowthBook 和默认值；它决定没有 daemon 时的启动策略，不证明 service 已安装或存活。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP": (
        "关闭交互主进程对长期空闲 local background Bash 的 memory-pressure reap；不影响 OS OOM、daemon worker、remote job 或用户显式终止。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_CODE_RESUME_INTERRUPTED_TURN": (
        "开启中断 turn 修复，移除不闭合 sibling blocks、记录 superseded tool IDs 并注入继续提示；不会把未确认工具副作用当作已回滚。",
        "sessions-checkpoints-memory.md",
    ),
    "CLAUDE_CODE_RESUME_SOURCE_ALIVE": (
        "源进程仍存活且 identity 匹配时，禁止新进程恢复 fileHistorySnapshots 以避免双 owner；message/context 状态仍可加载，外部副作用不受此锁保护。",
        "sessions-checkpoints-memory.md",
    ),
    "CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION": (
        "true/false 显式覆盖 Prompt Suggestion feature，随后仍受 interactive、swarm、settings 和 turn gates；不启用持久 memory，也不保证建议生成成功。",
        "background-model-tasks-and-memory-consolidation.md",
    ),
    "CLAUDE_CODE_GOAL_CHECKIN_MINUTES": (
        "覆盖 active-goal 后台 deferral check-in 的默认 30 分钟；feature 关闭时 interval=0，check-in 只唤醒检查，不表示后台任务已完成。",
        "active-goal-and-stop-loop.md",
    ),
    "CLAUDE_CHROME_PERMISSION_MODE": (
        "为 Chrome MCP bridge 选择 ask、skip_all_permission_checks 或 follow_a_plan；非法值 warning 后忽略，extension 连接、账号匹配和工具可达性仍独立。",
        "tui-input-accessibility-media-ide-chrome.md",
    ),
    "CLAUDE_CODE_ENVIRONMENT_KIND": (
        "区分 byoc、anthropic_cloud 和 bridge host ownership，影响 remote IO、Datadog、tool audience 与 auth-refresh adoption；不是单一 remote=true 别名。",
        "cloud-background-channels.md",
    ),
    "CLAUDE_CODE_REMOTE": (
        "标记 remote session，参与 connector、cloud listing、routine suppression 和 Agent Proxy gates；单独 true 不提供 session ID、token、first-party capability 或 durable state。",
        "cloud-background-channels.md",
    ),
    "CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE": (
        "附加 remote environment type（如 self_hosted），改变 diagnostics、attachment lane 和部分 tool gates；它是宿主分类，不证明远端任务持久或可恢复。",
        "cloud-background-channels.md",
    ),
    "CLAUDE_CODE_REMOTE_SESSION_ID": (
        "经格式校验后用于 request header、telemetry、Agent Proxy 和 remote identity；ID 存在不证明 session 在线、caller 有权访问或远端状态可恢复。",
        "cloud-background-channels.md",
    ),
    "CLAUDE_CODE_SESSION_ACCESS_TOKEN": (
        "优先提供 session ingress bearer，用于 Remote IO/Files 等 host-owned 请求；缺失可回落 token file，且必须避免继承给 Git/tool child。",
        "cli-startup-files-plugins-deeplinks.md",
    ),
    "CLAUDE_GATEWAY_ALLOW_LOOPBACK": (
        "只为 Gateway safe-fetch/JWKS loopback test mock 打开 escape；生产默认仍拒绝 metadata、link-local 和 loopback，不能当作通用 SSRF allow。",
        "enterprise-gateway-runtime.md",
    ),
    "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY": (
        "仅在 Gateway provider 下允许 GET /v1/models；未设置返回空 additional options，404 可回退 built-in catalog，成功列表仍受本地 family/allowlist 处理。",
        "enterprise-gateway-runtime.md",
    ),
    "CLAUDE_CODE_ENABLE_PROXY_AUTH_HELPER": (
        "允许消费 trusted settings 的 proxyAuthHelper shell command，并缓存其 Proxy-Authorization value；关闭时 helper 不执行，开启也不绕过 URL/policy 或 407 refresh 检查。",
        "network-proxy-ca-and-mtls.md",
    ),
    "NODE_EXTRA_CA_CERTS": (
        "读取额外 PEM 文件并按 path+content 缓存，再合并 bundled/system CA；读取失败会清旧 extra cache，且只证明 client trust material，不证明 mTLS 或所有 transport 成功。",
        "network-proxy-ca-and-mtls.md",
    ),
    "SSL_CERT_FILE": (
        "CCR policy CA 可写入该标准 env 供兼容 child transport 使用；Claude 主请求与不读取该变量的 SDK 仍需分别验证。",
        "network-proxy-ca-and-mtls.md",
    ),
    "JAVA_TOOL_OPTIONS": (
        "CCR 配置 JVM PKCS#12 truststore 时向 Java child 注入相应 options；Bazel embedded JDK 可能忽略它，因此另有 bazelrc 路径，不能据此宣称所有 Java 工具已信任。",
        "network-proxy-ca-and-mtls.md",
    ),
    "CLAUDE_CODE_DISABLE_CRON": (
        "与 tengu_kairos_cron 共同关闭 Cron tool surface；durable gate 与既有计划状态另算，不会自动删除已经创建的 cron 或撤销其外部副作用。",
        "builtin-tools-reference.md",
    ),
    "CLAUDE_CODE_DISABLE_WORKFLOWS": (
        "与 managed disableWorkflows 一起关闭 Workflow availability；不会撤销已发生的脚本/remote side effects，也不等于禁用普通 subagent。",
        "workflow-artifact-design.md",
    ),
    "CLAUDE_CODE_ENABLE_REFRESH_MCP_TOOLS": (
        "为当前工具集装配 RefreshMcpTools；tool 仍要求 live MCP client，只刷新已连接 server 的工具，不负责 dial、auth 或 reconnect。",
        "connectors-catalog-and-mcp-operators.md",
    ),
    "CLAUDE_CODE_ENABLE_XAA": (
        "条件加入 xaaIdp settings schema 和 mcp xaa command tree；关闭时 surface 不存在，开启后也不证明 IdP discovery、login 或 MCP connection 成功。",
        "cli-command-reference.md",
    ),
    "CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL": (
        "跳过 IDE extension 自动安装尝试；仍会检测和连接已有 extension，workspace trust、token、focus/selection transport 分别持有状态。",
        "tui-ide-remote-cloud.md",
    ),
    "CLAUDE_CODE_NO_FLICKER": (
        "tri-state 选择 fullscreen/alt-screen renderer；true 可越过普通 tmux/Windows 自动关闭，但仍受 local-agent、screen-reader 和 alternate-screen 硬兼容 gate，false 明确关闭。",
        "tui-input-accessibility-media-ide-chrome.md",
    ),
    "CLAUDE_ENV_FILE": (
        "向特定 command Hook 提供可写 env-file 路径；Hook 写入的 exports 影响后续 Bash 环境，是跨命令状态副作用，不等于当前 Hook stdout。",
        "hooks-event-reference.md",
    ),
    "CLAUDE_IMPORT_CONVERSATIONS": (
        "打开 hidden import-conversations handler；仍强制 --cwd、archive/path/size/manifest 校验，dry-run 不创建 transcript。",
        "project-purge-import-and-data-lifecycle.md",
    ),
    "CLAUDE_PROJECT_UUID": (
        "把当前 session 绑定到宿主指定 Project，并参与 Projects tool gate/API path；模型不能借此枚举或切换其他 Project，远端内容也不是本地事务。",
        "claude-design-and-projects.md",
    ),
    "CLAUDE_INTERNAL_FC_OVERRIDES": (
        "2.1.235 保留 parse/read 形态，但 getEnvironmentOverrides() 在读取前提前 return，精确 Probe 也未生效；这是 unreachable/dead branch，不是可建议用户使用的开关。",
        "feature-flags-remote-config.md",
    ),
    "DISABLE_LOGOUT_COMMAND": (
        "只隐藏/禁用 /logout local command object；不会自动撤销远端 OAuth grant，也不等于凭据不能通过其他 auth 生命周期清理。",
        "slash-command-reference.md",
    ),
    "DISABLE_AUTOUPDATER": (
        "停止后台 update check/install；旧 autoUpdates:false 会迁移为 settings env，手动 update/install surface 仍可使用。",
        "install-update-doctor-lifecycle.md",
    ),
    "DISABLE_UPDATES": (
        "管理员级阻断全部客户端更新路径，包括手动 update；Probe exit 0 只表示禁用策略被正常处理，不表示更新完成。",
        "install-update-doctor-lifecycle.md",
    ),
    "DISABLE_UPGRADE_COMMAND": (
        "关闭 upgrade command/prompt surface；不关闭后台 updater、doctor、外部分发或已经安装的旧 bytes。",
        "install-update-doctor-lifecycle.md",
    ),
    "DISABLE_DOCTOR_COMMAND": (
        "禁用 doctor/checkup command object；不等于跳过全部启动 installation checks、安全检查或自动 diagnostics telemetry。",
        "install-update-doctor-lifecycle.md",
    ),
    "DISABLE_INSTALLATION_CHECKS": (
        "跳过 install-method mismatch 检查和 sudo npm auto-update notice；不会关闭全部 doctor、安全检查、版本 policy 或 updater。",
        "install-update-doctor-lifecycle.md",
    ),
    "DISABLE_GROWTHBOOK": (
        "关闭在线 GrowthBook initialization/evaluation；只有显式 disk-cache-when-telemetry-off 条件满足时才可能读取 stale cache，各 feature consumer 仍按本地 fallback 处理。",
        "feature-flags-remote-config.md",
    ),
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": (
        "\u8986\u76d6\u4e0a\u4e0b\u6587\u6cbb\u7406\u4f7f\u7528\u7684 precompute/compact \u7a97\u53e3\u767e\u5206\u6bd4\uff1b\u6700\u7ec8\u9608\u503c\u4ecd\u4f9d\u8d56\u6240\u9009\u6a21\u578b\u7a97\u53e3\u548c\u8f93\u51fa reservation\u3002",
        "context-governance-and-caching.md",
    ),
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW": (
        "auto-compact window 的最高优先级输入。resolver 先读 env，再看 settings、clientdata/experiment 和模型默认；有效值按 100k-1M 解析并受模型窗口上限约束。只要 env 生效，`/autocompact` 会拒绝用 settings 覆盖；移除 env 后命令才可写 `autoCompactWindow` 并向宿主发 `apply_flag_settings`。非法值不会成为有效 window，最终 threshold 还要减 summary buffer。",
        "context-governance-and-caching.md",
    ),
    "CLAUDE_CODE_ENABLE_AWAY_SUMMARY": (
        "自动 Away Summary 的初始化优先级 gate。显式 false 直接关闭，显式 true 直接开启；未设置时 remote/非交互环境先关闭，再读取 `awaySummaryEnabled`，最后默认开启。它只控制自动调度，不改变 `/recap` 的显式 text-only 命令路径。",
        "background-model-tasks-and-memory-consolidation.md",
    ),
    "CLAUDE_CODE_MAX_CONTEXT_TOKENS": (
        "\u63d0\u4f9b context-window cap \u8f93\u5165\uff1b\u6a21\u578b\u76ee\u5f55\u4e0a\u9650\u3001\u8f93\u51fa reservation \u4e0e compact policy \u4ecd\u53c2\u4e0e\u6709\u6548\u9608\u503c\u8ba1\u7b97\u3002",
        "context-governance-and-caching.md",
    ),
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS": (
        "\u4e3a\u8bf7\u6c42\u4e0e\u6062\u590d\u8def\u5f84\u63d0\u4f9b\u6700\u5927 output-token \u8f93\u5165\uff1bprovider \u548c model \u4e0a\u9650\u53ef\u80fd\u5f62\u6210\u66f4\u4f4e\u7684\u6709\u6548 ceiling\u3002",
        "context-governance-and-caching.md",
    ),
    "CLAUDE_CODE_MAX_TURNS": (
        "\u9650\u5236 Agent Loop \u7684\u6a21\u578b iteration\uff0c\u4e0d\u662f shell \u547d\u4ee4\u6570\u6216 API retry \u6b21\u6570\uff1b\u8fbe\u5230\u4e0a\u9650\u4e5f\u4e0d\u4f1a\u56de\u6eda\u5df2\u5b8c\u6210\u5de5\u5177\u526f\u4f5c\u7528\u3002",
        "agent-loop.md",
    ),
    "CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY": (
        "\u9650\u5236\u5e76\u53d1\u5de5\u5177\u6267\u884c\u6570\uff1bconcurrency-safe \u5206\u7c7b\u4e0e unsafe barrier \u4ecd\u51b3\u5b9a\u54ea\u4e9b\u8c03\u7528\u53ef\u4ee5\u91cd\u53e0\u3002",
        "agent-loop.md",
    ),
    "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": (
        "\u9650\u5236\u540c\u65f6\u6d3b\u8dc3\u7684 child agent \u6570\uff1b\u6bcf\u4e2a agent \u7684 model\u3001context\u3001tools\u3001worktree \u4e0e transcript \u4ecd\u72ec\u7acb\u6301\u6709\u3002",
        "mcp-agents-background.md",
    ),
    "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": (
        "\u9650\u5236 subagent \u5d4c\u5957 spawn \u6df1\u5ea6\uff1b\u4e0d\u4f1a\u628a child context \u6216 permission \u5408\u5e76\u8fdb parent\u3002",
        "mcp-agents-background.md",
    ),
    "CLAUDE_CODE_DISABLE_FILE_CHECKPOINTING": (
        "\u5173\u95ed\u6587\u4ef6 checkpoint \u6355\u83b7\u4e0e\u6062\u590d\u8def\u5f84\uff1bconversation rewind \u4e0e\u5916\u90e8\u526f\u4f5c\u7528\u5c5e\u4e8e\u4e0d\u540c\u6062\u590d\u57df\u3002",
        "sessions-checkpoints-memory.md",
    ),
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": (
        "\u5173\u95ed\u81ea\u52a8 memory \u884c\u4e3a\uff1bCLAUDE.md\u3001transcript persistence\u3001compact summary \u4e0e prompt cache \u4ecd\u662f\u4e0d\u540c\u72b6\u6001 owner\u3002",
        "sessions-checkpoints-memory.md",
    ),
    "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": (
        "\u5173\u95ed background task \u8868\u9762\uff1bforeground \u5de5\u5177\u6267\u884c\u4e0e\u5df2\u7ecf\u6301\u4e45\u5316\u7684\u5916\u90e8\u5de5\u4f5c\u5c5e\u4e8e\u72ec\u7acb\u8fb9\u754c\u3002",
        "mcp-agents-background.md",
    ),
    "CLAUDE_CODE_ENABLE_FINE_GRAINED_TOOL_STREAMING": (
        "\u5728 model/provider \u652f\u6301\u65f6\u5f00\u542f\u66f4\u7ec6\u7c92\u5ea6\u7684 tool-input streaming\uff1b\u5b8c\u6574 tool_use \u7684\u6821\u9a8c\u4ecd\u53d1\u751f\u5728\u6267\u884c\u4e4b\u524d\u3002",
        "agent-loop.md",
    ),
    "CLAUDE_CODE_DISABLE_THINKING": (
        "\u5728\u8bf7\u6c42\u6784\u9020\u9636\u6bb5\u786c\u5173\u95ed thinking\uff1beffort \u8bbe\u7f6e\u548c\u6a21\u578b\u652f\u6301\u4e0d\u80fd\u91cd\u65b0\u5f00\u542f\u8be5\u8bf7\u6c42\u5206\u652f\u3002",
        "thinking-effort-and-fast-mode.md",
    ),
    "CLAUDE_CODE_DISABLE_1M_CONTEXT": (
        "\u5173\u95ed long-context capability \u8def\u5f84\uff1baccount entitlement\u3001\u6a21\u578b\u76ee\u5f55\u652f\u6301\u4e0e provider \u63a5\u53d7\u5ea6\u4ecd\u662f\u9644\u52a0 gate\u3002",
        "context-governance-and-caching.md",
    ),
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": (
        "\u5f00\u542f\u5b9e\u9a8c\u6027 team \u8868\u9762\uff0c\u4f46 task registry\u3001mailbox\u3001permission\u3001worktree \u4e0e remote service gate \u4ecd\u51b3\u5b9a\u53ef\u8fbe\u6027\u3002",
        "mcp-agents-background.md",
    ),
    "CLAUDE_CODE_EXPERIMENTAL_OBSERVER_AGENTS": (
        "\u5f00\u542f observer agent \u7ba1\u7ebf\uff1bobserver \u63a5\u6536\u72ec\u7acb stream/state view\uff0c\u4e0d\u4f1a\u6210\u4e3a\u4e3b\u5faa\u73af owner\u3002",
        "agent-loop.md",
    ),
    "CLAUDE_CODE_AGENT_PROXY_GH_SHIM": (
        "为 tool-scoped Agent Proxy 写入 gh path shim；与 Git config arm 任一开启时进入 tool-scoped 形态。写入失败只记录诊断并保留已建立 relay，不会伪装成完整工具治理成功。",
        "network-proxy-ca-and-mtls.md",
    ),
    "CLAUDE_CODE_AGENT_PROXY_GIT_CONFIG": (
        "为 tool-scoped Agent Proxy 向受治理的 GIT_CONFIG_GLOBAL 追加 proxy、CA、credential 与可选 URL rewrite。全局配置路径缺失或不安全时拒绝写入，relay 本身仍可保持运行。",
        "network-proxy-ca-and-mtls.md",
    ),
    "CLAUDE_CODE_ENABLE_TASKS": (
        "\u5f00\u542f task-oriented \u4ea7\u54c1\u8868\u9762\uff1b\u4e0d\u8bc1\u660e remote task backend\u3001team entitlement \u6216 background durability \u5df2\u53ef\u7528\u3002",
        "mcp-agents-background.md",
    ),
    "CLAUDE_PTY_HEARTBEAT_MS": (
        "background PTY host 的 client heartbeat 周期，typed parser 要求正整数；运行时解析失败或结果为 0 时回落 `60000ms`。每个已 armed socket 连续 3 个周期未 pong 就被断开，但 child PTY 不因此自动回滚；orphan watchdog 由独立的 `CLAUDE_PTY_ORPHAN_CHECK_MS` 控制。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_BG_CLAIM_AUTH": (
        "warm background spare 的一次性 claim bearer。worker 启动后立即从 `process.env` 删除；若同时有 `CLAUDE_BG_SOCKET_TOKENS_PATH`，则优先读取 token file 中的 `claimAuth`、随后删除 token file，并在不可读时降级回 env 值。它只认证 claim frame，不能替代 PTY socket auth 或任务权限。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_BG_SOCKET_TOKENS_PATH": (
        "background PTY/spare 的一次性 token-file 路径，用来转交 `ptyAuth/claimAuth` 而不把二者长期留在环境。PTY host/spare 读取后从环境删除；相应分支还会 unlink 文件。文件缺失会按各自现有 env token 降级，不能据此推断 socket 已认证。",
        "runtime-supervision-and-processes.md",
    ),
    "HTTP_PROXY": (
        "\u628a\u7b26\u5408\u6761\u4ef6\u7684 HTTP \u6d41\u91cf\u4ea4\u7ed9 proxy\uff1bNO_PROXY\u3001\u5c0f\u5199\u522b\u540d\u3001transport \u652f\u6301\u4e0e custom agent \u90fd\u53ef\u80fd\u6539\u53d8\u6709\u6548\u8def\u7531\u3002",
        "models-auth-providers-request.md",
    ),
    "HTTPS_PROXY": (
        "\u628a\u7b26\u5408\u6761\u4ef6\u7684 HTTPS \u6d41\u91cf\u4ea4\u7ed9 proxy\uff1b\u8bc1\u4e66\u4fe1\u4efb\u4e0e NO_PROXY \u4ecd\u662f\u72ec\u7acb\u63a7\u5236\u3002",
        "models-auth-providers-request.md",
    ),
    "NO_PROXY": (
        "\u4ece proxy \u8def\u7531\u6392\u9664\u5339\u914d\u76ee\u6807\uff1b\u7cbe\u786e host matching \u8bed\u4e49\u7531 bundle \u5185\u4ee3\u7406\u5b9e\u73b0\u6301\u6709\u3002",
        "models-auth-providers-request.md",
    ),
    "CCR_AGENT_PROXY_ENABLED": (
        "Remote/CCR Agent Proxy 的硬 enable gate；还必须处于 remote session、持有 session ID 和 bootstrap token，并成功建立本地 relay，最终 state 才会变为 enabled。",
        "network-proxy-ca-and-mtls.md",
    ),
    "CCR_AGENT_PROXY_INCLUDE_HOSTS": (
        "在 relay mode=selective 时解析逗号分隔 host allowlist。列表为空或不可解析时 fail-closed 到 tunnel-all，而不是绕过代理。入口读取后立即从环境删除。",
        "network-proxy-ca-and-mtls.md",
    ),
    "CCR_AGENT_PROXY_RELAY_MODE": (
        "选择 Agent Proxy relay 模式；值为 selective 且存在 include-host 列表时仅隧道匹配 host，否则使用全量 relay。入口读取后立即从环境删除。",
        "network-proxy-ca-and-mtls.md",
    ),
}


FEATURE_MEANINGS: dict[str, tuple[str, str]] = {
    "tengu_ccr_bridge": (
        "Remote Control rollout gate\u3002\u53ea\u6709 first-party host\u3001authentication scope\u3001subscription/organization \u4e0e policy \u68c0\u67e5\u901a\u8fc7\u540e\u624d\u8bfb\u53d6\uff1b\u5355\u72ec true \u4e0d\u80fd\u8ba9 Remote Control \u53ef\u7528\u3002",
        "feature-flags-remote-config.md",
    ),
    "tengu_auto_mode_config": (
        "\u4ea4\u4ed8 Auto Mode \u914d\u7f6e\u5bf9\u8c61\u3002consumer \u7ee7\u7eed\u89e3\u6790 enabled/config \u5b57\u6bb5\uff0cdeterministic permission/policy floor \u4ecd\u5177\u6709\u6700\u7ec8\u7ea6\u675f\u529b\u3002",
        "auto-mode-classifier.md",
    ),
    "tengu_workflows_enabled": (
        "\u63a7\u5236 Workflow \u4ea7\u54c1\u8868\u9762\u3002registry \u53ef\u7528\u6027\u3001host mode\u3001account capability \u4e0e workflow runtime \u4ecd\u662f\u9644\u52a0 gate\u3002",
        "workflow-artifact-design.md",
    ),
    "tengu_structured_output_strict": (
        "\u63a7\u5236 strict wire-schema \u8f6c\u6362\u3002model support \u4e0e provider/deployment acceptance \u5206\u5f00\u68c0\u67e5\uff1bFoundry 400 \u53ef\u4ee5\u964d\u7ea7 wire path\uff0c\u540c\u65f6\u4fdd\u7559\u672c\u5730\u6821\u9a8c\u3002",
        "structured-output-and-schema-contract.md",
    ),
    "tengu_skills_dashboard_enabled": (
        "控制 Skills Dashboard 的健康状态拉取。false 时不发请求；true 时 GET /api/claude_code/skills，使用 async auth、5 秒 timeout，并把非 ok、HTTP >=400、非法 skills 数组或异常统一降级为 null；成功时只保留具有已知 health 枚举的 skill_name -> health Map。",
        "plugins-skills-commands-lsp.md",
    ),
    "tengu_copper_thistle": (
        "Task/Job 命名与任务 footer 的 UI 分支 gate，fallback 为 false。false 时 MCP background item 仍称 task，并保留旧 footer/task hint 组合；true 时称 job，同时启用新的 footer 管理分支并从旧 keyed hints 中排除相应项。它不改变 task registry、执行权限或远端 durability。",
        "mcp-agents-background.md",
    ),
    "tengu_flint_harbor_prompt": (
        "`/team-onboarding` 的对象配置覆盖。consumer 分别校验 `prompt`、`guideTemplate` 和 `windowDays`；字符串字段非法时回落内置模板，天数先 floor 再 clamp 到 1-365，随后才扫描使用数据、写 `teamOnboardingLastUsedAt` 并组装命令 prompt。远端 payload 不能绕过 workspace/command enable gate。",
        "complex-slash-command-lifecycles.md",
    ),
    "tengu_sedge_lantern_config": (
        "自动 Away Summary 的 delay 配置对象，fallback `{delayMs:180000}`。consumer 只接受 finite number，并把值下限抬到 `30000ms`；实际定时再取该 delay 与 prompt-cache 剩余寿命 80% 的较小值，且必须通过 turn/cache/rate-limit/draft/background-work gates。它不控制 `/recap` 的显式调用。",
        "background-model-tasks-and-memory-consolidation.md",
    ),
    "tengu_harbor_moth": (
        "remote recap metadata 的 fallback gate，默认 false；只有环境 `CLAUDE_CODE_ENABLE_REMOTE_RECAP` 未显式给值时才读取。consumer 还要求非 remote-worker、本地 bridge/host 条件成立且存在 `onMetadataChanged`，每个 turn-end 只启动一次，成功后写 metadata `recap`。它与自动 `away_summary` event 是不同 sink。",
        "background-model-tasks-and-memory-consolidation.md",
    ),
    "tengu_malformed_tool_use_clean_retry": (
        "\u9009\u62e9 clean malformed-tool retry history\uff1a\u91cd\u8bd5\u524d tombstone \u9996\u6b21 assistant\uff0c\u800c\u4e0d\u662f\u4fdd\u7559\u5b83\u5e76\u8ffd\u52a0 correction prompt\uff1b\u4e0d\u4f1a\u589e\u52a0 retry \u6b21\u6570\u3002",
        "agent-loop.md",
    ),
    "tengu_thinking_block_resumption": (
        "\u5141\u8bb8\u517c\u5bb9\u7684 max-output \u6062\u590d\u8def\u5f84\u7eed\u63a5\u5c3e\u90e8 signed thinking block\uff1bstop reason\u3001block shape \u4e0e model support \u662f\u72ec\u7acb gate\u3002",
        "agent-loop.md",
    ),
    "tengu_compact_cache_prefix": (
        "\u63a7\u5236 compact \u76f8\u5173 prompt-cache prefix \u8def\u5f84\u3002key \u4e0e\u4e24\u4e2a\u9759\u6001 consumer \u8bc1\u660e\u5ba2\u6237\u7aef\u5206\u652f\u5b58\u5728\uff0c\u4f46\u670d\u52a1\u7aef cache-hit \u884c\u4e3a\u4ecd\u662f Boundary\u3002",
        "context-governance-and-caching.md",
    ),
    "tengu_reactive_compact_remote": (
        "\u63a7\u5236 remote/reactive compact \u8def\u5f84\u3002\u672c\u5730 prompt-too-long \u68c0\u6d4b\u3001retry budget\u3001summary \u5408\u6cd5\u6027\u4e0e transcript repair \u4ecd\u5171\u540c\u51b3\u5b9a\u662f\u5426\u5b8c\u6210\u3002",
        "context-governance-and-caching.md",
    ),
    "tengu_prompt_cache_1h_config": (
        "\u63d0\u4f9b\u4e00\u5c0f\u65f6 prompt-cache eligibility \u7684 object allowlist\u3002\u5185\u7f6e fallback \u5217\u51fa repl_main_thread*\u3001sdk\u3001auto_mode \u4e0e memdir_relevance\uff1bprovider \u63a5\u53d7\u5ea6\u548c\u771f\u5b9e cache hit \u5728\u670d\u52a1\u7aef\u3002",
        "context-governance-and-caching.md",
    ),
    "tengu_prompt_cache_diagnostics": (
        "\u63a7\u5236 prompt-cache \u8bca\u65ad\u8f93\u51fa\uff0c\u4e0d\u662f\u7f13\u5b58\u672c\u8eab\uff1b\u770b\u89c1\u8bca\u65ad\u4fe1\u606f\u4e0d\u80fd\u8bc1\u660e\u670d\u52a1\u7aef\u53d1\u751f cache hit\u3002",
        "context-governance-and-caching.md",
    ),
    "tengu_subagent_cache_evict": (
        "\u63a7\u5236 subagent prompt-cache eviction \u8def\u5f84\uff1bchild context \u4e0e cache owner \u4ecd\u548c parent Agent Loop \u5206\u79bb\u3002",
        "mcp-agents-background.md",
    ),
    "tengu_stream_watchdog_default_on": (
        "\u63a7\u5236 streaming watchdog \u7684 default-on \u72b6\u6001\uff1bwatchdog timeout\u3001partial block state\u3001retry \u4e0e non-stream fallback \u4ecd\u662f\u72ec\u7acb\u63a7\u5236\u3002",
        "resilience-and-recovery.md",
    ),
    "tengu_disable_streaming_to_non_streaming_fallback": (
        "\u5173\u95ed\u5931\u8d25 streaming attempt \u5230 non-streaming transport \u7684 fallback\uff1b\u4e0d\u4f1a\u5173\u95ed\u666e\u901a HTTP retry \u6216 model fallback\u3002",
        "resilience-and-recovery.md",
    ),
    "tengu_watchdog_skip_nonstreaming_fallback": (
        "\u8ba9 watchdog \u8def\u5f84\u8df3\u8fc7 non-stream fallback\uff1bpartial assistant/tool \u72b6\u6001\u4ecd\u9700\u666e\u901a discard/tombstone \u6062\u590d\u89c4\u5219\u3002",
        "resilience-and-recovery.md",
    ),
    "tengu_gzip_request_bodies": (
        "\u63a7\u5236 gzip request-body transport\uff1bprovider \u517c\u5bb9\u6027\u4e0e request retry \u5206\u7c7b\u4ecd\u76f8\u4e92\u72ec\u7acb\u3002",
        "models-auth-providers-request.md",
    ),
    "tengu_mcp_discovery_cache": (
        "\u63a7\u5236 MCP discovery \u7ed3\u679c\u7f13\u5b58\uff1bconnection generation \u53d8\u5316\u4e0e tool-schema invalidation \u4ecd\u51b3\u5b9a freshness\u3002",
        "mcp-agents-background.md",
    ),
    "tengu_mcp_connect_timeout_retry": (
        "\u63a7\u5236 MCP connection timeout \u540e\u7684 retry\uff1btransport type\u3001auth\u3001policy \u4e0e server process health \u4ecd\u662f\u72ec\u7acb\u5931\u8d25 owner\u3002",
        "mcp-agents-background.md",
    ),
    "tengu_mcp_stateless_skip_init": (
        "\u5141\u8bb8 stateless MCP \u5728\u534f\u8bae\u7ea6\u675f\u4e0b\u8df3\u8fc7\u666e\u901a initialization\uff1b\u4e0d\u662f trust \u6216 policy \u7684\u901a\u7528\u7ed5\u8fc7\u3002",
        "mcp-agents-background.md",
    ),
    "tengu_mcp_skills": (
        "\u63a7\u5236 MCP \u63d0\u4f9b\u7684 skill \u8868\u9762\uff1bserver connection\u3001listing\u3001trust\u3001namespacing \u4e0e prompt injection budget \u4ecd\u76f8\u4e92\u72ec\u7acb\u3002",
        "plugins-skills-commands-lsp.md",
    ),
    "tengu_mcp_protocol_negotiation_http": (
        "\u63a7\u5236 HTTP MCP transport \u7684 protocol negotiation\uff1btrue fallback \u4e0d\u8bc1\u660e\u76ee\u6807 server \u652f\u6301\u534f\u5546\u7248\u672c\u3002",
        "mcp-agents-background.md",
    ),
    "tengu_mcp_protocol_negotiation_stdio": (
        "\u63a7\u5236 stdio MCP transport \u7684 protocol negotiation\uff1bchild process launch \u4e0e initialize success \u4ecd\u662f\u8fd0\u884c\u65f6\u8fb9\u754c\u3002",
        "mcp-agents-background.md",
    ),
    "tengu_mcp_protocol_negotiation_claudeai": (
        "\u63a7\u5236 claude.ai-owned MCP transport \u7684 protocol negotiation\uff1baccount entitlement \u4e0e remote service \u884c\u4e3a\u4ecd\u662f Boundary\u3002",
        "mcp-agents-background.md",
    ),
    "tengu_memory_stream_list": (
        "\u63a7\u5236 streamed memory listing\uff1bstorage backend \u53ef\u8fbe\u6027\u3001pagination\u3001retention \u4e0e account scope \u4ecd\u76f8\u4e92\u72ec\u7acb\u3002",
        "sessions-checkpoints-memory.md",
    ),
    "tengu_memory_bulk_inflate": (
        "\u63a7\u5236 bulk memory hydration\uff1b\u4e0d\u4f1a\u628a memory \u4e0e transcript\u3001prompt cache \u6216 compact-summary owner \u5408\u5e76\u3002",
        "sessions-checkpoints-memory.md",
    ),
    "tengu_memory_store_resync_interval_minutes": (
        "\u63d0\u4f9b memory-store resynchronization interval\uff0c\u5355\u4f4d\u5206\u949f\uff1bremote store \u4e0e conflict semantics \u4ecd\u662f service/runtime Boundary\u3002",
        "sessions-checkpoints-memory.md",
    ),
    "tengu_transcript_local_gc": (
        "\u63a7\u5236\u672c\u5730 transcript garbage collection\uff1bserver history\u3001prompt cache\u3001memory \u4e0e\u5916\u90e8\u526f\u4f5c\u7528\u4e0d\u4f1a\u88ab\u8be5 client GC \u5220\u9664\u3002",
        "sessions-checkpoints-memory.md",
    ),
    "tengu_rewind_first_message": (
        "\u63a7\u5236 first-message rewind \u8868\u9762\uff1bfile checkpoint \u4e0e conversation graph rewind \u8303\u56f4\u4e0d\u540c\uff0c\u90fd\u4e0d\u80fd\u64a4\u9500\u8fdc\u7aef\u526f\u4f5c\u7528\u3002",
        "sessions-checkpoints-memory.md",
    ),
    "tengu_observer_agents_enabled": (
        "\u63a7\u5236 observer-agent \u53ef\u7528\u6027\uff1bobserver state \u662f\u8f85\u52a9\u72b6\u6001\uff0c\u4e0d\u66ff\u4ee3\u4e3b\u5faa\u73af\u7684 message/tool owner\u3002",
        "agent-loop.md",
    ),
    "tengu_observer_subagent_fanout": (
        "\u63a7\u5236 observer \u5411 subagent fanout\uff1b\u6bcf\u4e2a child \u4ecd\u6301\u6709\u9694\u79bb loop/context\uff0c\u5e76\u589e\u52a0 token \u4e0e coordination cost\u3002",
        "agent-loop.md",
    ),
    "tengu_bridge_attestation_enforce": (
        "\u63a7\u5236 bridge attestation \u5f3a\u5236\u6267\u884c\uff1b\u914d\u5957 config key\u3001\u672c\u5730 identity material \u4e0e remote verifier result \u4ecd\u662f\u9644\u52a0\u8f93\u5165\u3002",
        "runtime-supervision-and-processes.md",
    ),
    "tengu_bridge_selfheal_heartbeats": (
        "\u63a7\u5236 bridge heartbeat self-healing\uff1bownership\u3001socket authentication\u3001reconnect budget \u4e0e durable job state \u4ecd\u76f8\u4e92\u72ec\u7acb\u3002",
        "runtime-supervision-and-processes.md",
    ),
    "tengu_ccr_bundle_max_bytes": (
        "\u63d0\u4f9b Remote Control bundle-size ceiling\uff1b\u672c\u5730 fallback \u4e3a null\uff0c\u8868\u793a\u6c42\u503c\u524d\u6709\u6548\u503c\u53ef\u4ee5\u4fdd\u6301\u7f3a\u5931\u3002",
        "tui-ide-remote-cloud.md",
    ),
    "tengu_ccr_stream_event_flush_ms": (
        "\u63d0\u4f9b Remote Control stream-event flush cadence\uff0c\u5355\u4f4d\u6beb\u79d2\uff1bnetwork delivery \u4e0e server acknowledgement \u4ecd\u662f Boundary\u3002",
        "tui-ide-remote-cloud.md",
    ),
    "tengu_plugin_binary_assets": (
        "\u63a7\u5236 plugin binary asset \u5904\u7406\uff1bmarketplace/source trust\u3001platform compatibility\u3001install state \u4e0e execution permission \u4ecd\u76f8\u4e92\u72ec\u7acb\u3002",
        "plugins-skills-commands-lsp.md",
    ),
    "tengu_plugin_official_mkt_git_fallback": (
        "\u63a7\u5236 official marketplace \u8def\u5f84\u7684 Git fallback\uff1bnetwork\u3001credential helper\u3001source trust \u4e0e repository validity \u4ecd\u76f8\u4e92\u72ec\u7acb\u3002",
        "plugins-skills-commands-lsp.md",
    ),
    "tengu_chrome_auto_enable": (
        "\u63a7\u5236 Chrome integration \u81ea\u52a8\u542f\u7528\uff1bextension/native host \u662f\u5426\u5b58\u5728\u3001browser state\u3001consent \u4e0e platform support \u4ecd\u662f\u9644\u52a0 gate\u3002",
        "tui-input-accessibility-media-ide-chrome.md",
    ),
    "tengu_bg_low_mem_mb": (
        "\u63d0\u4f9b background supervisor \u7684 low-memory threshold\uff0c\u5355\u4f4d MiB\uff0c\u5185\u7f6e fallback \u4e3a 1024\uff1b\u771f\u5b9e pressure detection \u4e0e reap eligibility \u4ecd\u662f\u8fd0\u884c\u65f6\u72b6\u6001\u3002",
        "runtime-supervision-and-processes.md",
    ),
    "tengu_bg_retire_grace_bridged_min": (
        "\u63d0\u4f9b bridged background process \u7684 retirement grace\uff0c\u5355\u4f4d\u5206\u949f\uff0c\u5185\u7f6e fallback \u4e3a 480\uff1bretirement \u524d\u4ecd\u68c0\u67e5 liveness \u4e0e ownership\u3002",
        "runtime-supervision-and-processes.md",
    ),
    "tengu_auto_mode_worktree_fast_path": (
        "\u63a7\u5236 Auto Mode worktree fast path\uff1bdeterministic policy floor\u3001classifier result\u3001worktree creation \u4e0e tool permission \u4ecd\u5177\u6709\u6700\u7ec8\u7ea6\u675f\u529b\u3002",
        "auto-mode-classifier.md",
    ),
    "tengu_cfc_in_product_permissions": (
        "\u63a7\u5236\u4ea7\u54c1\u5185 CFC permission \u5904\u7406\uff1bmanaged policy\u3001deterministic rule\u3001classifier outcome\u3001hook \u4e0e interactive fallback \u4ecd\u76f8\u4e92\u72ec\u7acb\u3002",
        "tools-permissions-hooks.md",
    ),
    "tengu_tool_search_unsupported_models": (
        "\u643a\u5e26\u7528\u4e8e\u5728\u4e0d\u652f\u6301\u6a21\u578b\u4e0a\u5173\u95ed Tool Search \u7684 model list/config\uff1btool generation \u4e0e deferred-schema residency \u4ecd\u51b3\u5b9a live registry\u3002",
        "mcp-agents-background.md",
    ),
    "tengu_non_deferrable_builtins": (
        "\u643a\u5e26\u4e0d\u53ef defer \u7684 built-in tool list/config\uff1b\u63a7\u5236 schema residency\uff0c\u4e0d\u63a7\u5236 tool permission \u6216\u6267\u884c\u6210\u529f\u3002",
        "context-governance-and-caching.md",
    ),
    "tengu_gb_refresh_interval_minutes": (
        "控制 GrowthBook 定时 refresh 周期，单位为分钟；consumer 使用 360 分钟默认值，将有效值 clamp 到 5-360 分钟、乘 0.9-1.1 jitter 后换算为 timer，flagged refresh 失败再进入补偿路径。它不能证明 refresh 已成功或配置已改变。",
        "feature-flags-remote-config.md",
    ),
    "tengu_hazel_osprey": (
        "控制 prompt-cache breakpoint/selection 的客户端分支，改变 cache_control 放置策略；provider 接受度、真实 cache hit、TTL 和计费结果仍属服务端 Boundary。",
        "context-governance-and-caching.md",
    ),
    "tengu_hover_rest": (
        "控制 Claude storage v5 及相关迁移读取分支；namespace、migration fallback、本地缓存和远端持久性分别持有状态，不能由 flag 值合并推断。",
        "storage-v5-reference.md",
    ),
    "tengu_kairos_brief": (
        "Brief 模式总 gate；只有 entitlement、host、配置和工具装配同时成立才进入 Brief lane，true 不等于附件已上传或用户端已渲染。",
        "brief-mode-and-user-visible-output.md",
    ),
    "tengu_kairos_brief_config": (
        "交付 Brief 配置对象；consumer 对阈值、上传和行为字段逐项解析并应用 fallback，非法远端字段不能直接穿透到运行时。",
        "brief-mode-and-user-visible-output.md",
    ),
    "tengu_remote_backend": (
        "选择 remote-backend 客户端分支；真实 backend capability、鉴权、任务持久性、投递确认和恢复语义仍是 remote Boundary。",
        "cloud-background-channels.md",
    ),
    "tengu_slate_harbor": (
        "控制 REPL/programmatic tool runtime 的可达分支；还受 entrypoint、variant、宿主 bridge、工具注册和会话状态约束。",
        "repl-programmatic-tool-runtime.md",
    ),
    "tengu_surreal_dali": (
        "控制 remote routines、runner 和 notification 的客户端分支；队列交付、ack、远端执行结果与通知到达不能由 flag 值证明。",
        "remote-routines-runner-and-notifications.md",
    ),
    "tengu_umber_kestrel": (
        "控制 EndConversation 风控终止面；consumer 仍执行风险判定、许可和结束状态转换，true 不表示无条件结束，也不撤销已经完成的副作用。",
        "end-conversation-risk-control.md",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build deterministic environment and feature reference documents."
    )
    parser.add_argument("repo", nargs="?", default=".", help="Snapshot repository root")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if committed outputs differ instead of writing them",
    )
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected object")
        rows.append(value)
    return rows


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def names_sha256(values: Iterable[str]) -> str:
    data = "".join(f"{value}\n" for value in sorted(values)).encode("utf-8")
    return sha256_bytes(data)


def compact_code(value: str) -> str:
    return f"<code>{html.escape(value, quote=False)}</code>"


def cell(value: Any) -> str:
    text = str(value).replace("\n", " ").replace("|", "&#124;")
    return text if text else "-"


def source_text(record: Any) -> str:
    if not isinstance(record, dict):
        return "<missing>"
    source = record.get("source")
    if isinstance(source, dict):
        if isinstance(source.get("text"), str):
            return source["text"]
        if source.get("sha256"):
            return f"<redacted sha256={source['sha256']}>"
    if "staticValue" in record:
        return json.dumps(record["staticValue"], ensure_ascii=False, sort_keys=True)
    if "resolvedStaticValue" in record:
        return json.dumps(record["resolvedStaticValue"], ensure_ascii=False, sort_keys=True)
    return "<missing>"


def source_location(row: dict[str, Any], label: str = "read") -> str:
    line = row.get("line")
    column = row.get("column")
    if isinstance(line, int) and isinstance(column, int):
        return f"[{label} L{line}:C{column}](../extracted/cli.js#L{line})"
    return f"{label} <unknown>"


def schema_location(row: dict[str, Any]) -> str:
    builder_line = row.get("builderLine")
    builder_column = row.get("builderColumn")
    export_line = row.get("exportLine")
    export_column = row.get("exportColumn")
    return (
        f"[builder L{builder_line}:C{builder_column}](../extracted/cli.js#L{builder_line})"
        f"<br>[export L{export_line}:C{export_column}](../extracted/cli.js#L{export_line})"
    )


def format_options(options: Any) -> str:
    if options is None:
        return "none"
    return source_text(options)


def format_fallbacks(rows: list[dict[str, Any]]) -> str:
    values: list[str] = []
    for row in rows:
        fallback = row.get("fallbackExpression")
        if not isinstance(fallback, dict):
            continue
        operator = row.get("fallbackOperator", "?")
        item = f"{operator} {source_text(fallback)}"
        if item not in values:
            values.append(item)
    if not values:
        return "Static\uff1a\u672a\u6355\u83b7\u5230\u76f8\u90bb fallback \u8868\u8fbe\u5f0f"
    return "<br>".join(compact_code(value) for value in values)


def format_accessors(rows: list[dict[str, Any]]) -> str:
    counts = Counter(str(row.get("accessor", "unknown")) for row in rows)
    return ", ".join(f"{name} x{counts[name]}" for name in sorted(counts)) or "none"


def format_locations(rows: list[dict[str, Any]]) -> str:
    return "<br>".join(source_location(row) for row in sorted(rows, key=lambda item: item["offset"])) or "none"


def environment_category(name: str) -> str:
    upper = name.upper()
    rules = [
        (r"ANTHROPIC|MODEL|BEDROCK|VERTEX|FOUNDRY|AWS_|GOOGLE_CLOUD|AZURE", "\u6a21\u578b/provider/\u8ba4\u8bc1"),
        (r"TOKEN|API_KEY|AUTH|CREDENTIAL|PASSWORD|SECRET|CERT|PRIVATE_KEY|OAUTH", "\u51ed\u636e/\u8eab\u4efd"),
        (r"OTEL|TELEMET|DATADOG|DD_|TRACE|METRIC|LOG|SENTRY|GROWTHBOOK", "\u9065\u6d4b/\u8bca\u65ad"),
        (r"PROXY|BASE_URL|HOST|PORT|SOCKET|HTTP|HTTPS|TLS|SSL|NO_PROXY", "\u7f51\u7edc/transport"),
        (r"COMPACT|CONTEXT|CACHE|MEMORY|TRANSCRIPT|CHECKPOINT|REWIND", "\u4e0a\u4e0b\u6587/session/memory"),
        (r"AGENT|SUBAGENT|MAX_TURNS|TOOL|PERMISSION|SANDBOX|CLASSIFIER", "Agent/\u5de5\u5177/policy"),
        (r"MCP|PLUGIN|SKILL|LSP", "MCP/plugin/skill"),
        (r"BRIDGE|CCR|REMOTE|BACKGROUND|BG_|DAEMON|PTY|RENDEZVOUS|CLOUD", "\u8fdc\u7a0b/background/\u76d1\u7763"),
        (r"TERM|TTY|COLOR|SCREEN|ACCESSIBILITY|AX_|IDE|VSCODE|CHROME|CURSOR|UI", "\u7ec8\u7aef/UI/IDE"),
        (r"GIT|GITHUB|GITLAB|CI|WORKSPACE|PROJECT|REPO", "\u7248\u672c\u63a7\u5236/CI/workspace"),
        (r"NODE|BUN|NPM|YARN|PNPM|DENO", "JavaScript runtime/\u4f9d\u8d56"),
        (r"PATH|HOME|DIR|FILE|TMP|SHELL|USER|UID|GID|XDG|APPDATA", "\u64cd\u4f5c\u7cfb\u7edf/\u8def\u5f84/\u8fdb\u7a0b"),
    ]
    for pattern, category in rules:
        if re.search(pattern, upper):
            return f"Heuristic/name\uff1a{category}"
    return "Heuristic/name\uff1a\u5176\u4ed6\u6216 bundled dependency"


def environment_sensitivity(name: str) -> str:
    upper = name.upper()
    if re.search(r"PASSWORD|SECRET|PRIVATE_KEY|API_KEY|AUTH_TOKEN|ACCESS_KEY|SESSION_TOKEN|CREDENTIAL", upper):
        return "Heuristic/name\uff1acredential secret\uff1b\u4e0d\u5f97\u53d1\u5e03\u771f\u5b9e\u8fd0\u884c\u503c"
    if re.search(r"TOKEN|COOKIE|CERT|KEY_FILE|OAUTH|BEARER", upper):
        return "Heuristic/name\uff1a\u51ed\u636e\u6216\u5b89\u5168\u6750\u6599"
    if re.search(r"EMAIL|ACCOUNT|ORG|ORGANIZATION|USER|WORKSPACE_ID|DEVICE|SESSION_ID", upper):
        return "Heuristic/name\uff1a\u8eab\u4efd\u6216\u5173\u8054\u5143\u6570\u636e"
    if re.search(r"PATH|HOME|DIR|FILE|SOCKET|CWD|PWD", upper):
        return "Heuristic/name\uff1a\u672c\u5730\u8def\u5f84\u6216\u8fdb\u7a0b\u62d3\u6251"
    if re.search(r"URL|HOST|PROXY|PORT", upper):
        return "Heuristic/name\uff1a\u7f51\u7edc\u8def\u7531\u5143\u6570\u636e"
    return "Heuristic/name\uff1a\u672a\u547d\u4e2d\u660e\u663e secret \u6807\u8bb0\uff1b\u771f\u5b9e\u8fd0\u884c\u503c\u4ecd\u672a\u89c2\u5bdf"


def environment_meaning(name: str, has_calls: bool) -> str:
    if has_calls and name in ENV_MEANINGS:
        meaning, document = ENV_MEANINGS[name]
        return f"Static consumer \u6559\u5b66\u89e3\u91ca\uff1a{meaning}\u8be6\u89c1 [{document}]({document})\u3002"
    if has_calls:
        return (
            "Untraced/Inventory only\uff1aschema \u4e0e named access \u5df2\u8bc1\u660e\u5ba2\u6237\u7aef\u5b58\u5728\u8bfb\u53d6\u70b9\uff0c"
            "\u4f46\u5c1a\u672a\u628a minified consumer\u3001\u4e8c\u6b21 gate \u548c\u6545\u969c\u5206\u652f\u8ffd\u5230\u53ef\u8fa9\u62a4\u7684\u4e1a\u52a1\u6548\u679c\u3002"
            "\u8fd9\u662f\u5f85\u6062\u590d\u7684\u5ba2\u6237\u7aef\u8bc1\u636e\uff0c\u4e0d\u662f\u4e0d\u53ef\u6062\u590d\u7684\u670d\u52a1\u7aef Boundary\uff1bcategory \u4e0e sensitivity \u4ecd\u662f\u540d\u79f0 heuristic\u3002"
        )
    return (
        "Opaque/Boundary\uff1a\u53ea\u6709 typed declaration\uff1b\u672c inventory \u6ca1\u6709 named access callsite\u3002"
        "\u4e0d\u5f97\u636e\u6b64\u58f0\u79f0 bundled CLI \u5728\u8fd0\u884c\u65f6\u6d88\u8d39\u8be5\u53d8\u91cf\u3002"
    )


def feature_category(key: str) -> str:
    lowered = key.lower()
    rules = [
        (r"compact|cache|context|thinking|token|output", "\u4e0a\u4e0b\u6587/cache/\u6a21\u578b\u8f93\u51fa"),
        (r"agent|subagent|observer|tool|loop|turn", "Agent Loop/\u5de5\u5177"),
        (r"mcp|plugin|skill|lsp", "MCP/plugin/skill"),
        (r"auto_mode|classifier|permission|policy|attestation|destructive|cfc", "permission/Auto Mode/policy"),
        (r"bridge|ccr|remote|cloud|kairos|teleport", "Remote Control/cloud/bridge"),
        (r"background|bg_|daemon|pty|prewarm|retire|rendezvous", "background/runtime \u76d1\u7763"),
        (r"memory|transcript|rewind|session", "session/memory/\u6062\u590d"),
        (r"stream|gzip|request|model|structured_output|watchdog", "\u8bf7\u6c42/stream/protocol"),
        (r"chrome|vscode|ide|artifact|media|terminal|xterm|keybinding", "UI/IDE/\u5a92\u4f53"),
        (r"workflow|design", "workflow/design"),
        (r"telemetry|trace|feedback|survey|datadog", "\u9065\u6d4b/feedback"),
    ]
    for pattern, category in rules:
        if re.search(pattern, lowered):
            return f"Heuristic/name\uff1a{category}"
    return "Heuristic/name\uff1aopaque experiment codename"


def feature_default_shape(expression: str) -> str:
    value = expression.strip()
    if value in {"!0", "true"}:
        return "boolean(true)"
    if value in {"!1", "false"}:
        return "boolean(false)"
    if value in {"null", "void 0", "undefined"}:
        return "nullish"
    if value.startswith("{"):
        return "object-like"
    if value.startswith("["):
        return "array-like"
    if value.startswith(('"', "'", "`")):
        return "string-like"
    if re.fullmatch(r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:e[-+]?\d+)?", value, re.IGNORECASE):
        return "number-like"
    if value == "<missing>":
        return "missing"
    return "expression/unknown"


def feature_defaults(rows: list[dict[str, Any]]) -> tuple[str, str]:
    expressions: list[str] = []
    for row in rows:
        arguments = row.get("arguments", [])
        expression = source_text(arguments[1]) if len(arguments) >= 2 else "<missing>"
        if expression not in expressions:
            expressions.append(expression)
    shapes = sorted({feature_default_shape(expression) for expression in expressions})
    rendered = "<br>".join(compact_code(expression) for expression in expressions)
    return rendered, ", ".join(shapes)


def feature_functions(rows: list[dict[str, Any]]) -> str:
    counts = Counter(str(row.get("function") or "<top-level>") for row in rows)
    return ", ".join(f"{compact_code(name)} x{counts[name]}" for name in sorted(counts))


def feature_meaning(key: str) -> str:
    if key in FEATURE_MEANINGS:
        meaning, document = FEATURE_MEANINGS[key]
        return f"Static \u6559\u5b66\u89e3\u91ca\uff1a{meaning}\u8be6\u89c1 [{document}]({document})\u3002"
    category = feature_category(key)
    if "opaque experiment codename" not in category:
        return (
            "\u4ec5 Heuristic/name\uff1a\u63cf\u8ff0\u6027 key \u53ea\u63d0\u793a\u6240\u5c5e\u5b50\u7cfb\u7edf\uff0ccallsite/default \u53ea\u8bc1\u660e\u8bfb\u53d6\u5408\u540c\u3002"
            "\u5728 consumer \u5206\u652f\u548c\u5168\u90e8\u4e8c\u6b21 gate \u8ffd\u6e05\u524d\u6807\u4e3a Untraced/Inventory only\uff0c\u4e0d\u5f97\u628a\u5b83\u5199\u6210\u4e0d\u53ef\u6062\u590d\u7684 Boundary\u3002"
        )
    return (
        "Opaque codename / Inventory only\uff1acodename \u52a0 fallback/callsite \u4ecd\u4e0d\u80fd\u63ed\u793a\u4ea7\u54c1\u542b\u4e49\uff1b"
        "\u8fd9\u662f\u5ba2\u6237\u7aef consumer \u5f85\u8ffd\u7684\u9759\u6001\u7d22\u5f15\uff0c\u4e0d\u5f97\u628a\u5355\u8bcd\u81ea\u884c\u6269\u5199\u6210\u529f\u80fd\u7ed3\u8bba\uff0c\u4e5f\u4e0d\u5f97\u7528 Boundary \u63a9\u76d6\u672a\u5b8c\u6210\u7684\u5206\u6790\u3002"
    )


def input_hashes(inventory: Path) -> dict[str, str]:
    names = [
        "environment-schema.jsonl",
        "environment-access-callsites.jsonl",
        "feature-flags.txt",
        "feature-flag-callsites.jsonl",
        "growthbook-keys.txt",
        "growthbook-callsites.jsonl",
    ]
    return {name: file_sha256(inventory / name) for name in names}


def validate_contract(
    version: str,
    env_schema: list[dict[str, Any]],
    env_calls: list[dict[str, Any]],
    feature_keys: list[str],
    feature_calls: list[dict[str, Any]],
    growthbook_keys: list[str],
    growthbook_calls: list[dict[str, Any]],
) -> dict[str, int]:
    typed_names = {row["name"] for row in env_schema}
    if len(typed_names) != len(env_schema):
        raise ValueError("environment schema contains duplicate names")
    named_calls = [row for row in env_calls if row.get("name") is not None]
    dynamic_env = [row for row in env_calls if row.get("name") is None]
    typed_named_calls = [row for row in named_calls if row["name"] in typed_names]
    untyped_named_calls = [row for row in named_calls if row["name"] not in typed_names]
    typed_used_names = {row["name"] for row in typed_named_calls}
    untyped_names = {row["name"] for row in untyped_named_calls}
    all_named_environment_reads = typed_used_names | untyped_names
    direct_feature = [row for row in feature_calls if row.get("nameArgument", {}).get("staticValue") is not None]
    nonliteral_feature = [row for row in feature_calls if row.get("nameArgument", {}).get("staticValue") is None]
    resolved_nonliteral = [
        row
        for row in nonliteral_feature
        if row.get("nameArgument", {}).get("resolvedStaticValue") is not None
    ]
    unresolved_feature = [
        row
        for row in nonliteral_feature
        if row.get("nameArgument", {}).get("resolvedStaticValue") is None
    ]
    resolvable_feature = direct_feature + resolved_nonliteral
    metrics = {
        "environment_schema": len(env_schema),
        "environment_callsites": len(env_calls),
        "typed_named_callsites": len(typed_named_calls),
        "typed_used_names": len(typed_used_names),
        "typed_declaration_only": len(typed_names - typed_used_names),
        "untyped_named_names": len(untyped_names),
        "untyped_named_callsites": len(untyped_named_calls),
        "dynamic_environment_callsites": len(dynamic_env),
        "feature_keys": len(feature_keys),
        "feature_callsites": len(feature_calls),
        "feature_resolvable_static_callsites": len(resolvable_feature),
        "feature_direct_literal_callsites": len(direct_feature),
        "feature_nonliteral_syntax_callsites": len(nonliteral_feature),
        "feature_resolved_nonliteral_callsites": len(resolved_nonliteral),
        "feature_unresolved_dynamic_callsites": len(unresolved_feature),
        "dynamic_config_static_keys": len(growthbook_keys),
        "dynamic_config_callsites": len(growthbook_calls),
    }
    if len(set(feature_keys)) != len(feature_keys):
        raise ValueError("feature-flags.txt contains duplicate keys")
    if len(set(growthbook_keys)) != len(growthbook_keys):
        raise ValueError("growthbook-keys.txt contains duplicate keys")
    stale_environment_contracts = sorted(set(ENV_MEANINGS) - all_named_environment_reads)
    if stale_environment_contracts:
        raise ValueError(
            "environment consumer contracts have no active named read: "
            + ", ".join(stale_environment_contracts)
        )
    stale_feature_contracts = sorted(set(FEATURE_MEANINGS) - set(feature_keys))
    if stale_feature_contracts:
        raise ValueError(
            "feature consumer contracts have no static key: "
            + ", ".join(stale_feature_contracts)
        )
    if version == "2.1.235" and metrics != EXPECTED_2_1_235:
        delta = {
            key: {"expected": EXPECTED_2_1_235[key], "actual": metrics.get(key)}
            for key in sorted(EXPECTED_2_1_235)
            if EXPECTED_2_1_235[key] != metrics.get(key)
        }
        raise ValueError(f"2.1.235 inventory contract drift: {json.dumps(delta, sort_keys=True)}")
    return metrics


def build_environment_document(
    version: str,
    env_schema: list[dict[str, Any]],
    env_calls: list[dict[str, Any]],
    metrics: dict[str, int],
    hashes: dict[str, str],
) -> str:
    calls_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    dynamic_calls: list[dict[str, Any]] = []
    for row in env_calls:
        if row.get("name") is None:
            dynamic_calls.append(row)
        else:
            calls_by_name[row["name"]].append(row)
    typed_names = {row["name"] for row in env_schema}
    untyped_names = sorted(name for name in calls_by_name if name not in typed_names)
    declaration_only = sorted(name for name in typed_names if not calls_by_name.get(name))
    active_named_names = sorted(calls_by_name)
    consumer_contract_names = sorted(name for name in ENV_MEANINGS if calls_by_name.get(name))
    callsite_only_names = sorted(set(active_named_names) - set(consumer_contract_names))
    accessor_counts = Counter(row["accessor"] for row in env_calls)
    type_counts = Counter(row["type"] for row in env_schema)

    lines: list[str] = [
        f"# Claude Code CLI {version} \u73af\u5883\u53d8\u91cf\u53c2\u8003\uff1a\u58f0\u660e\u3001\u8bfb\u53d6\u548c\u771f\u5b9e\u4f5c\u7528\u4e3a\u4ec0\u4e48\u4e0d\u662f\u4e00\u56de\u4e8b",
        "",
        "## \u8bfb\u8005\u95ee\u9898",
        "",
        "\u4e3a\u4ec0\u4e48\u540c\u4e00\u4e2a\u73af\u5883\u53d8\u91cf\u51fa\u73b0\u5728 bundle \u91cc\uff0c\u5374\u53ef\u80fd\u5b8c\u5168\u4e0d\u5f71\u54cd Claude Code\uff1f\u4e3a\u4ec0\u4e48\u53e6\u4e00\u4e2a\u53d8\u91cf\u4e0d\u5728 typed schema \u4e2d\uff0c\u5ba2\u6237\u7aef\u53cd\u800c\u771f\u7684\u8bfb\u53d6\u4e86\u5b83\uff1f",
        "",
        "## \u4e00\u53e5\u8bdd\u5fc3\u667a\u6a21\u578b",
        "",
        "\u73af\u5883\u53d8\u91cf\u8981\u7ecf\u8fc7 **\u540d\u79f0\u8fdb\u5165 schema -> \u8fd0\u884c\u65f6\u88ab\u8bfb\u53d6 -> \u89e3\u6790/\u9ed8\u8ba4\u503c -> \u4e1a\u52a1 consumer -> provider/policy/service \u4e8c\u6b21\u95e8** \u624d\u80fd\u6539\u53d8\u884c\u4e3a\uff1b\u4efb\u4f55\u4e00\u5c42\u7f3a\u5931\uff0c\u90fd\u4e0d\u80fd\u628a\u4e00\u4e2a\u5b57\u7b26\u4e32\u547d\u4e2d\u5199\u6210\u5df2\u542f\u7528\u529f\u80fd\u3002",
        "",
        "```mermaid",
        "flowchart LR",
        "  A[\u8fdb\u7a0b\u73af\u5883] --> B{typed builder?}",
        "  B -->|\u662f| C[\u7c7b\u578b\u4e0e options \u89e3\u6790]",
        "  B -->|\u5426| D[\u76f4\u63a5\u6216\u4ee3\u7406\u8bfb\u53d6]",
        "  C --> E{\u5b58\u5728 named callsite?}",
        "  D --> E",
        "  E -->|\u5426| F[Declaration only / Boundary]",
        "  E -->|\u662f| G[consumer \u89e3\u91ca\u4e0e fallback]",
        "  G --> H[provider / policy / service gates]",
        "  H --> I[\u7528\u6237\u53ef\u89c1\u884c\u4e3a]",
        "```",
        "",
        "## \u8d2f\u7a7f\u573a\u666f",
        "",
        "\u7528\u6237\u8bbe\u7f6e `ANTHROPIC_BASE_URL`\u3001`ANTHROPIC_AUTH_TOKEN` \u548c `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`\u3002\u7b2c\u4e00\u4e2a\u53d8\u91cf\u65e2\u6539\u53d8\u8bf7\u6c42 endpoint\uff0c\u4e5f\u6539\u53d8 first-party host \u5224\u5b9a\uff1b\u7b2c\u4e8c\u4e2a\u53d8\u91cf\u8fdb\u5165 bearer header\uff1b\u7b2c\u4e09\u4e2a\u53d8\u91cf\u5173\u95ed\u4e00\u65b9 analytics \u548c\u5728\u7ebf Feature Evaluation\uff0c\u5374\u4e0d\u5173\u95ed\u6a21\u578b\u8bf7\u6c42\u3002\u4e09\u4e2a\u53d8\u91cf\u90fd\u88ab\u8bfb\u53d6\uff0c\u4f46\u5b83\u4eec\u62e5\u6709\u4e0d\u540c consumer\u3001\u4f18\u5148\u7ea7\u548c\u5931\u8d25\u8fb9\u754c\u3002\u53ea\u770b\u540d\u79f0\u5217\u8868\u65e0\u6cd5\u5f97\u5230\u8fd9\u4e9b\u7ed3\u8bba\u3002",
        "",
        "## \u72b6\u6001\u603b\u8868",
        "",
        "| \u72b6\u6001 | \u672c\u7248\u6570\u91cf | \u80fd\u8bc1\u660e\u4ec0\u4e48 | \u4e0d\u80fd\u8bc1\u660e\u4ec0\u4e48 |",
        "| --- | ---: | --- | --- |",
        f"| typed schema \u58f0\u660e | {metrics['environment_schema']} | builder \u58f0\u660e\u4e86\u540d\u79f0\u3001type\u3001options | \u5f53\u524d\u4e3b\u4ea7\u54c1\u4e00\u5b9a\u8bfb\u53d6\u6216\u751f\u6548 |",
        f"| typed named callsites | {metrics['typed_named_callsites']}\uff0c\u8986\u76d6 {metrics['typed_used_names']} \u4e2a\u540d\u79f0 | bundle \u4e2d\u5b58\u5728\u9759\u6001\u547d\u540d\u8bfb\u53d6 | consumer \u5206\u652f\u5728\u5f53\u524d\u73af\u5883\u53ef\u8fbe |",
        f"| \u5df2\u7ed1\u5b9a\u4e1a\u52a1 consumer \u5408\u540c | {len(consumer_contract_names)} \u4e2a named read | \u5df2\u4eba\u5de5\u8ffd\u5230\u4f18\u5148\u7ea7\u3001fallback\u3001\u4e8c\u6b21 gate\u3001\u72b6\u6001\u53d8\u5316\u548c\u5931\u8d25\u8fb9\u754c | \u5f53\u524d\u8fd0\u884c\u503c\u3001\u8fdc\u7aef\u670d\u52a1\u6216\u4e0d\u53ef\u8fbe\u5e73\u53f0\u5206\u652f |",
        f"| \u4ec5 callsite \u7ed1\u5b9a\u3001\u672a\u5b8c\u6210\u4e1a\u52a1\u89e3\u91ca | {len(callsite_only_names)} \u4e2a named read | accessor\u3001fallback \u548c\u5168\u90e8\u4f4d\u7f6e\u4ecd\u5b8c\u6574\u4fdd\u7559 | \u4e0d\u5f97\u628a\u540d\u79f0 heuristic \u6216 minified \u4f4d\u7f6e\u5199\u6210\u5df2\u6062\u590d\u4e1a\u52a1\u673a\u5236 |",
        f"| declaration-only typed \u540d\u79f0 | {metrics['typed_declaration_only']} | schema \u4e2d\u5b58\u5728\uff0c\u4f46\u672c inventory \u6ca1\u6709 named read | \u53ef\u4ee5\u628a\u5b83\u5199\u6210\u8fd0\u884c\u65f6\u529f\u80fd\u5f00\u5173 |",
        f"| \u975e typed \u9759\u6001\u540d\u79f0 | {metrics['untyped_named_names']} \u4e2a\u540d\u79f0 / {metrics['untyped_named_callsites']} \u4e2a\u8c03\u7528\u70b9 | \u8fd0\u884c\u65f6\u4ee3\u7801\u76f4\u63a5\u8bfb\u53d6\u4e86 schema \u5916\u540d\u79f0 | \u503c\u7ecf\u8fc7\u7edf\u4e00\u7c7b\u578b\u9a8c\u8bc1 |",
        f"| \u52a8\u6001\u540d\u79f0\u8c03\u7528\u70b9 | {metrics['dynamic_environment_callsites']} | \u4ee3\u7801\u6309\u8868\u8fbe\u5f0f\u8ba1\u7b97\u73af\u5883\u53d8\u91cf\u540d | \u4ec5\u9760\u5f53\u524d AST \u6062\u590d\u6700\u7ec8\u540d\u79f0\u548c\u503c |",
        f"| \u5168\u90e8\u73af\u5883\u8bfb\u53d6 | {metrics['environment_callsites']} | \u56db\u7c7b accessor \u7684\u5b8c\u6574\u8c03\u7528\u70b9\u96c6\u5408 | \u670d\u52a1\u5668\u3001shell \u6ce8\u5165\u548c\u771f\u5b9e\u8fd0\u884c\u503c |",
        "",
        "Accessor \u5206\u5e03\uff1a" + "\uff1b".join(f"`{name}`={accessor_counts[name]}" for name in sorted(accessor_counts)) + "\u3002",
        "",
        "typed \u7c7b\u578b\u5206\u5e03\uff1a" + "\uff1b".join(f"`{name}`={type_counts[name]}" for name in sorted(type_counts)) + "\u3002",
        "",
        "## \u5b57\u6bb5\u600e\u4e48\u8bfb",
        "",
        "| \u5b57\u6bb5 | \u7cbe\u786e\u542b\u4e49 | \u5e38\u89c1\u8bef\u8bfb |",
        "| --- | --- | --- |",
        "| `type/options` | typed builder \u7684\u89e3\u6790\u5408\u540c\uff1boptions \u4fdd\u7559\u539f\u8868\u8fbe\u5f0f | \u628a\u5b83\u5f53\u6210\u670d\u52a1\u7aef\u53c2\u6570 schema |",
        "| `category` | \u53ea\u6309\u540d\u79f0\u5173\u952e\u8bcd\u5206\u7ec4\uff0c\u6240\u6709\u884c\u660e\u786e\u6807 `Heuristic/name` | \u628a\u5206\u7c7b\u5f53\u6210\u4ea7\u54c1\u5f52\u5c5e\u5b9e\u9524 |",
        "| `access count/accessor kinds` | AST \u6355\u83b7\u5230\u7684\u8bfb\u53d6\u6b21\u6570\u4e0e `process.env`/environment proxy \u5f62\u5f0f | \u6b21\u6570\u8d8a\u591a\u5c31\u8d8a\u91cd\u8981 |",
        "| `fallback expressions` | \u4e0e\u8bfb\u53d6\u8868\u8fbe\u5f0f\u76f8\u90bb\u7684 `||` \u6216 `??` fallback | `||` \u4e0e `??` \u5bf9\u7a7a\u5b57\u7b26\u4e32\u30010\u3001false \u7b49\u4ef7 |",
        "| `locations` | canonical `extracted/cli.js` \u7684 schema/read \u884c\u5217 | \u884c\u53f7\u672c\u8eab\u80fd\u89e3\u91ca minified consumer |",
        "| `sensitivity` | \u4ec5\u6309\u540d\u79f0\u8bc6\u522b credential\u3001identity\u3001path\u3001network \u98ce\u9669 | \u6ca1\u547d\u4e2d\u5173\u952e\u8bcd\u5c31\u53ef\u4ee5\u516c\u5f00\u771f\u5b9e\u503c |",
        f"| `meaning/evidence` | {len(consumer_contract_names)} \u4e2a named read \u8fde\u63a5\u5230\u5df2\u8ffd consumer \u4e13\u9898\uff1b\u5176\u4f59 {len(callsite_only_names)} \u4e2a\u660e\u786e\u6807\u4e3a Untraced/Inventory only | \u7528\u53d8\u91cf\u540d\u81ea\u884c\u8865\u5168\u4e1a\u52a1\u542b\u4e49\uff0c\u6216\u628a\u672a\u8ffd consumer \u8bef\u5199\u6210\u4e0d\u53ef\u6062\u590d Boundary |",
        "",
        "`||` \u4f1a\u5728\u7a7a\u5b57\u7b26\u4e32\u30010\u3001false \u65f6\u5207 fallback\uff1b`??` \u53ea\u5728 null/undefined \u65f6\u5207 fallback\u3002inventory \u8bb0\u5f55\u7684\u662f\u8868\u8fbe\u5f0f\uff0c\u4e0d\u662f\u4e00\u6b21\u771f\u5b9e\u8fd0\u884c\u7684\u6c42\u503c\u7ed3\u679c\u3002",
        "",
        "## \u5931\u8d25\u4e0e\u670d\u52a1\u7aef\u8fb9\u754c",
        "",
        "1. typed \u58f0\u660e\u6210\u529f\u3001\u503c\u4e5f\u53ef\u89e3\u6790\uff0c\u4e0d\u4ee3\u8868\u4efb\u4f55 consumer \u8bfb\u53d6\u5b83\uff1b\u672c\u7248\u6709 80 \u4e2a declaration-only \u540d\u79f0\u3002",
        "2. named read \u5b58\u5728\uff0c\u4e0d\u4ee3\u8868\u5f53\u524d provider\u3001entrypoint\u3001policy\u3001platform \u6216\u8d26\u6237\u72b6\u6001\u80fd\u5230\u8fbe\u8be5\u5206\u652f\u3002",
        "3. \u52a8\u6001\u8bfb\u53d6\u7684\u6700\u7ec8\u540d\u79f0\u4f9d\u8d56\u5c40\u90e8\u53d8\u91cf\u3001\u5faa\u73af\u3001\u4f9d\u8d56\u5e93\u6216\u8fd0\u884c\u65f6\u8f93\u5165\uff1b145 \u4e2a\u8c03\u7528\u70b9\u5fc5\u987b\u4fdd\u7559\u8868\u8fbe\u5f0f\u800c\u4e0d\u662f\u731c\u540d\u79f0\u3002",
        "4. credential\u3001endpoint\u3001feature payload\u3001cloud identity\u3001proxy \u548c\u670d\u52a1\u7aef entitlement \u7684\u771f\u5b9e\u503c\u4e0d\u5728 shipped bundle \u4e2d\u3002",
        "5. typed schema \u6df7\u6709 bundled dependency surface\uff1b\u672c\u6587\u7684\u7c7b\u522b\u662f\u5bfc\u822a heuristic\uff0c\u4e0d\u662f Anthropic \u4ea7\u54c1\u5f52\u5c5e\u6807\u7b7e\u3002",
        "",
        "## \u56db\u4e2a\u8bca\u65ad\u573a\u666f",
        "",
        "### 1. \u53d8\u91cf\u5199\u4e86\u4f46\u6ca1\u6709\u6548\u679c",
        "",
        "\u5148\u770b\u672c\u8868\u662f\u5426\u4e3a declaration-only\uff0c\u518d\u770b accessor\u3001fallback \u548c consumer \u4e13\u9898\u3002\u82e5\u53ea\u6709 schema \u58f0\u660e\uff0c\u7ed3\u8bba\u53ea\u80fd\u662f `Boundary`\uff0c\u4e0d\u80fd\u7ee7\u7eed\u731c\u5e03\u5c14\u8bed\u4e49\u3002",
        "",
        "### 2. \u81ea\u5b9a\u4e49 endpoint \u540e\u90e8\u5206\u80fd\u529b\u6d88\u5931",
        "",
        "`ANTHROPIC_BASE_URL` \u4e0d\u53ea\u662f URL\u3002\u5b83\u8fd8\u53c2\u4e0e first-party host \u5224\u5b9a\uff0c\u56e0\u6b64 Remote Control\u3001\u90e8\u5206\u4e0a\u4f20\u3001Feature Evaluation \u6216\u79c1\u6709 beta \u53ef\u80fd\u5728 endpoint \u8bf7\u6c42\u524d\u5c31\u88ab\u672c\u5730 gate \u62d2\u7edd\u3002",
        "",
        "### 3. \u5173\u95ed\u9065\u6d4b\u540e\u540c\u7248\u672c\u529f\u80fd\u4e0d\u540c",
        "",
        "`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`\u3001`DISABLE_TELEMETRY` \u548c `DO_NOT_TRACK` \u4f4d\u4e8e\u5728\u7ebf Feature Evaluation \u7684\u5916\u5c42\u3002\u5173\u95ed\u6d41\u91cf\u53ef\u80fd\u4fdd\u7559 disk last-known-good\uff0c\u4e5f\u53ef\u80fd\u8ba9\u6ca1\u6709\u7f13\u5b58\u7684\u65b0\u8fdb\u7a0b\u53ea\u5f97\u5230 fallback\u3002",
        "",
        "### 4. \u8bbe\u4e86\u5e76\u53d1\u6216 turn \u4e0a\u9650\u540e\u4ecd\u6709\u526f\u4f5c\u7528",
        "",
        "`CLAUDE_CODE_MAX_TURNS` \u63a7\u5236 Agent Loop iteration\uff0c\u4e0d\u56de\u6eda\u5df2\u7ecf\u5b8c\u6210\u7684\u5de5\u5177\u3002\u5e76\u53d1\u4e0a\u9650\u4e5f\u53ea\u9650\u5236\u8c03\u5ea6\uff1b\u8fdc\u7aef\u5199\u5165\u3001shell \u8fdb\u7a0b\u548c\u6587\u4ef6\u4fee\u6539\u4ecd\u9700\u5404\u81ea\u7684 permission\u3001checkpoint \u4e0e\u6062\u590d\u7b56\u7565\u3002",
        "",
        "## 842 \u4e2a typed \u73af\u5883\u53d8\u91cf\u9010\u9879\u53c2\u8003",
        "",
        f"\u8986\u76d6\u5408\u540c\uff1a`{metrics['environment_schema']}/{metrics['environment_schema']}`\u3002\u6bcf\u884c\u90fd\u663e\u793a name\u3001type\u3001options\u3001heuristic category\u3001\u8bbf\u95ee\u6b21\u6570\u4e0e accessor\u3001fallback\u3001\u5168\u90e8\u4f4d\u7f6e\u3001sensitivity \u548c meaning/evidence\u3002",
        "",
        "| name | type / options | category | access count / accessor kinds | fallback expressions | locations | sensitivity | meaning / evidence |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for row in sorted(env_schema, key=lambda item: item["name"]):
        name = row["name"]
        calls = sorted(calls_by_name.get(name, []), key=lambda item: item["offset"])
        options = format_options(row.get("options"))
        locations = schema_location(row)
        if calls:
            locations += "<br>" + format_locations(calls)
        lines.append(
            "| "
            + " | ".join(
                [
                    compact_code(name),
                    cell(f"{row['type']} / {options}"),
                    cell(environment_category(name)),
                    cell(f"{len(calls)} / {format_accessors(calls)}"),
                    cell(format_fallbacks(calls)),
                    cell(locations),
                    cell(environment_sensitivity(name)),
                    cell(environment_meaning(name, bool(calls))),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 80 \u4e2a declaration-only typed \u540d\u79f0",
            "",
            "\u8fd9\u4e9b\u540d\u79f0\u5df2\u7ecf\u5305\u542b\u5728\u4e0a\u9762\u7684 842 \u884c\u4e2d\uff1b\u8fd9\u91cc\u5355\u72ec\u5217\u51fa\u662f\u4e3a\u4e86\u9632\u6b62\u8bfb\u8005\u628a schema declaration \u8bef\u5199\u6210 reachable feature\u3002",
            "",
            ", ".join(compact_code(name) for name in declaration_only),
            "",
            "## 137 \u4e2a\u975e typed \u9759\u6001\u540d\u79f0\u9010\u9879\u53c2\u8003",
            "",
            f"\u8986\u76d6\u5408\u540c\uff1a`{metrics['untyped_named_names']}/{metrics['untyped_named_names']}` \u4e2a\u540d\u79f0\u3001`{metrics['untyped_named_callsites']}/{metrics['untyped_named_callsites']}` \u4e2a\u8c03\u7528\u70b9\u3002`type/options` \u4e00\u5f8b\u662f Boundary\uff0c\u56e0\u4e3a\u8fd9\u4e9b\u540d\u79f0\u4e0d\u5728 typed builder schema \u4e2d\u3002",
            "",
            "| name | type / options | category | access count / accessor kinds | fallback expressions | locations | sensitivity | meaning / evidence |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for name in untyped_names:
        calls = sorted(calls_by_name[name], key=lambda item: item["offset"])
        meaning = ENV_MEANINGS.get(name)
        if meaning:
            description, document = meaning
            evidence = f"Static consumer \u6559\u5b66\u89e3\u91ca\uff1a{description}\u8be6\u89c1 [{document}]({document})\u3002"
        else:
            evidence = (
                "Untraced/Inventory only\uff1adirect named read \u5c5e\u4e8e Static\uff0c\u4f46 typed schema \u4e0d\u63d0\u4f9b\u8be5\u540d\u79f0\u7684\u7c7b\u578b\u6821\u9a8c\uff0c"
                "consumer \u548c\u4e8c\u6b21 gate \u5c1a\u672a\u8ffd\u6e05\uff1bcategory/sensitivity \u90fd\u662f\u540d\u79f0 heuristic\u3002"
            )
        lines.append(
            "| "
            + " | ".join(
                [
                    compact_code(name),
                    "Boundary\uff1a\u4e0d\u5728 typed schema \u4e2d",
                    cell(environment_category(name)),
                    cell(f"{len(calls)} / {format_accessors(calls)}"),
                    cell(format_fallbacks(calls)),
                    cell(format_locations(calls)),
                    cell(environment_sensitivity(name)),
                    cell(evidence),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 145 \u4e2a\u52a8\u6001\u73af\u5883\u540d\u79f0\u8c03\u7528\u70b9",
            "",
            "\u6bcf\u884c\u4ee3\u8868\u4e00\u4e2a\u771f\u5b9e AST callsite\u3002`expression` \u662f bundle \u4e2d\u7684\u539f\u8868\u8fbe\u5f0f\uff1b\u672c\u6587\u4e0d\u628a minified identifier \u89e3\u6790\u6210\u731c\u6d4b\u7684\u53d8\u91cf\u540d\u3002",
            "",
            "| comparison key | expression | accessor | fallback | location | sensitivity / evidence |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in sorted(dynamic_calls, key=lambda item: item["offset"]):
        expression = source_text(row.get("expression"))
        fallback = format_fallbacks([row])
        lines.append(
            "| "
            + " | ".join(
                [
                    compact_code(row["comparisonKey"]),
                    compact_code(expression),
                    compact_code(str(row["accessor"])),
                    cell(fallback),
                    source_location(row),
                    "Opaque/Boundary\uff1a\u6700\u7ec8\u540d\u79f0\u4e0e\u771f\u5b9e\u8fd0\u884c\u503c\u4f9d\u8d56\u6267\u884c\u72b6\u6001\uff1b\u4e0d\u5f97\u4ece minified expression \u63a8\u65ad sensitivity \u6216\u4e1a\u52a1\u542b\u4e49\u3002",
                ]
            )
            + " |"
        )

    summary = {
        "artifact": "analysis/environment-variable-reference.md",
        "consumerContractCount": len(consumer_contract_names),
        "consumerContractNamesSha256": names_sha256(consumer_contract_names),
        "callsiteOnlyNamedReadCount": len(callsite_only_names),
        "generatedBy": "skill/claude-code-version-diff/scripts/build_environment_feature_references.py",
        "inputSha256": hashes,
        "metrics": {key: metrics[key] for key in metrics if key.startswith("environment") or key.startswith("typed_") or key.startswith("untyped_") or key.startswith("dynamic_environment")},
        "typedNamesSha256": names_sha256(typed_names),
        "untypedNamesSha256": names_sha256(untyped_names),
        "dynamicComparisonKeysSha256": names_sha256(row["comparisonKey"] for row in dynamic_calls),
        "version": version,
    }
    lines.extend(
        [
            "",
            "<!-- BEGIN:ENVIRONMENT_VARIABLE_REFERENCE:MACHINE_SUMMARY",
            json.dumps(summary, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
            "END:ENVIRONMENT_VARIABLE_REFERENCE:MACHINE_SUMMARY -->",
            "<!-- BEGIN:ENVIRONMENT_VARIABLE_REFERENCE:TYPED_NAMES",
            *sorted(typed_names),
            "END:ENVIRONMENT_VARIABLE_REFERENCE:TYPED_NAMES -->",
            "<!-- BEGIN:ENVIRONMENT_VARIABLE_REFERENCE:UNTYPED_NAMES",
            *untyped_names,
            "END:ENVIRONMENT_VARIABLE_REFERENCE:UNTYPED_NAMES -->",
            "<!-- BEGIN:ENVIRONMENT_VARIABLE_REFERENCE:DYNAMIC_COMPARISON_KEYS",
            *(row["comparisonKey"] for row in sorted(dynamic_calls, key=lambda item: item["comparisonKey"])),
            "END:ENVIRONMENT_VARIABLE_REFERENCE:DYNAMIC_COMPARISON_KEYS -->",
            "<!-- BEGIN:ENVIRONMENT_VARIABLE_REFERENCE:CONSUMER_CONTRACT_NAMES",
            *consumer_contract_names,
            "END:ENVIRONMENT_VARIABLE_REFERENCE:CONSUMER_CONTRACT_NAMES -->",
        ]
    )
    return "\n".join(lines) + "\n"


def static_feature_value(row: dict[str, Any]) -> str | None:
    argument = row.get("nameArgument", {})
    if argument.get("staticValue") is not None:
        return str(argument["staticValue"])
    if argument.get("resolvedStaticValue") is not None:
        return str(argument["resolvedStaticValue"])
    return None


def build_feature_document(
    version: str,
    feature_keys: list[str],
    feature_calls: list[dict[str, Any]],
    growthbook_keys: list[str],
    growthbook_calls: list[dict[str, Any]],
    metrics: dict[str, int],
    hashes: dict[str, str],
) -> str:
    calls_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in feature_calls:
        value = static_feature_value(row)
        if value is not None:
            calls_by_key[value].append(row)
    nonliteral_calls = [
        row for row in feature_calls if row.get("nameArgument", {}).get("staticValue") is None
    ]
    resolved_assignment_calls = [
        row
        for row in nonliteral_calls
        if row.get("nameArgument", {}).get("resolvedStaticValue") is not None
    ]
    unresolved_dynamic_calls = [
        row
        for row in nonliteral_calls
        if row.get("nameArgument", {}).get("resolvedStaticValue") is None
    ]
    resolvable_static_calls = [
        row for row in feature_calls if static_feature_value(row) is not None
    ]
    growthbook_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in growthbook_calls:
        value = static_feature_value(row)
        if value is not None:
            growthbook_by_key[value].append(row)
    consumer_contract_keys = sorted(key for key in FEATURE_MEANINGS if calls_by_key.get(key))
    callsite_only_keys = sorted(set(feature_keys) - set(consumer_contract_keys))

    lines: list[str] = [
        f"# Claude Code CLI {version} Feature Flag \u9010 key \u53c2\u8003\uff1a\u9ed8\u8ba4\u503c\u3001consumer \u548c\u670d\u52a1\u7aef\u8fb9\u754c",
        "",
        "## \u8bfb\u8005\u95ee\u9898",
        "",
        "\u4e3a\u4ec0\u4e48 bundle \u4e2d\u660e\u660e\u5b58\u5728\u4e00\u4e2a `tengu_*` key\uff0c\u522b\u4eba\u7684\u5ba2\u6237\u7aef\u6709\u529f\u80fd\u800c\u6211\u7684\u6ca1\u6709\uff1f\u4e3a\u4ec0\u4e48\u67d0\u4e2a key \u7684 fallback \u662f `true`\uff0c\u529f\u80fd\u4ecd\u53ef\u80fd\u88ab policy\u3001provider \u6216 host \u5173\u95ed\uff1f",
        "",
        "## \u4e00\u53e5\u8bdd\u5fc3\u667a\u6a21\u578b",
        "",
        "Feature key \u53ea\u662f\u53d6\u503c\u5165\u53e3\uff1a**reader + \u672c\u5730 fallback + fresh/disk/remote source + consumer \u81ea\u5df1\u7684\u7c7b\u578b\u89e3\u6790 + policy/provider/protocol \u4e8c\u6b21\u95e8** \u5171\u540c\u51b3\u5b9a\u884c\u4e3a\uff1bkey \u540d\u548c fallback \u90fd\u4e0d\u662f\u529f\u80fd\u5df2\u4ea4\u4ed8\u7684\u8bc1\u660e\u3002",
        "",
        "```mermaid",
        "flowchart LR",
        "  A[et key, local fallback] --> B{manager source}",
        "  B -->|fresh payload| C[fresh value]",
        "  B -->|disk cache| D[stale-capable value]",
        "  B -->|missing/disabled| E[local fallback]",
        "  C --> F[consumer type/range parse]",
        "  D --> F",
        "  E --> F",
        "  F --> G[policy/provider/host/protocol gates]",
        "  G --> H[user-visible surface]",
        "```",
        "",
        "## \u8d2f\u7a7f\u573a\u666f",
        "",
        "\u7528\u6237\u6253\u5f00 Remote Control\u3002\u5ba2\u6237\u7aef\u5148\u901a\u8fc7 first-party endpoint\u3001auth scope\u3001subscription/organization \u548c managed policy\uff0c\u518d\u8bfb\u53d6 `tengu_ccr_bridge`\u3002fresh true \u53ef\u4ee5\u7acb\u5373\u901a\u8fc7\uff1bdisk true \u662f stale-capable\uff1b\u6ca1\u6709\u503c\u65f6\u4f7f\u7528\u672c\u5730 fallback\u3002\u5373\u4f7f flag \u4e3a true\uff0c\u524d\u7f6e gate \u4ecd\u53ef\u62d2\u7edd\u3002\u53cd\u8fc7\u6765\uff0cbundle \u4e2d\u51fa\u73b0 key \u4e5f\u4e0d\u4ee3\u8868\u670d\u52a1\u7aef\u7ed9\u5f53\u524d\u8d26\u53f7\u4e0b\u53d1 true\u3002",
        "",
        "## \u72b6\u6001\u603b\u8868",
        "",
        "| \u72b6\u6001 | \u672c\u7248\u6570\u91cf | \u80fd\u8bc1\u660e\u4ec0\u4e48 | \u4e0d\u80fd\u8bc1\u660e\u4ec0\u4e48 |",
        "| --- | ---: | --- | --- |",
        f"| static feature keys | {metrics['feature_keys']} | \u81f3\u5c11\u4e00\u4e2a `et()` \u540d\u79f0\u53ef\u9759\u6001\u6062\u590d | \u8d26\u53f7\u5f53\u524d\u503c\u6216\u529f\u80fd\u5df2\u542f\u7528 |",
        f"| \u5df2\u7ed1\u5b9a\u4e1a\u52a1 consumer \u5408\u540c | {len(consumer_contract_keys)} \u4e2a key | \u5df2\u4eba\u5de5\u8ffd\u5230 fallback \u89e3\u6790\u3001\u4e8c\u6b21 gate\u3001\u72b6\u6001\u53d8\u5316\u4e0e\u5931\u8d25\u8fb9\u754c | \u670d\u52a1\u7aef value/rule/rollout \u548c\u5f53\u524d\u8d26\u53f7\u53ef\u8fbe\u6027 |",
        f"| \u4ec5 static callsite/fallback\u3001\u672a\u5b8c\u6210\u4e1a\u52a1\u89e3\u91ca | {len(callsite_only_keys)} \u4e2a key | key\u3001fallback\u3001function \u548c\u4f4d\u7f6e\u4ecd\u53ef\u4ea4\u53c9\u6bd4\u8f83 | \u4e0d\u5f97\u4ece codename \u6216\u63cf\u8ff0\u6027 key \u76f4\u63a5\u63a8\u65ad\u4ea7\u54c1\u6548\u679c |",
        f"| \u53ef\u9759\u6001\u6062\u590d\u7684 `et()` callsites | {metrics['feature_resolvable_static_callsites']} | direct literal \u6216 assignment resolver \u5f97\u5230 361 \u4e2a key | \u8fdc\u7aef\u503c\u3001consumer reachability \u6216\u7ebf\u4e0a rollout |",
        f"| direct literal `et()` callsites | {metrics['feature_direct_literal_callsites']} | key \u76f4\u63a5\u5199\u5728\u8c03\u7528\u53c2\u6570\u4e2d | consumer \u5206\u652f\u5f53\u524d\u53ef\u8fbe |",
        f"| assignment-resolved `et()` callsites | {metrics['feature_resolved_nonliteral_callsites']} | \u975e literal \u8bed\u6cd5\u53ef\u8ffd\u5230\u9759\u6001 key\uff1b6 \u4e2a key \u53ea\u901a\u8fc7\u8fd9\u4e00\u7ea7\u8fdb\u5165 361 key \u96c6\u5408 | \u8fd0\u884c\u65f6 feature value \u5df2\u77e5 |",
        f"| truly dynamic unresolved `et()` callsites | {metrics['feature_unresolved_dynamic_callsites']} | \u53ea\u4fdd\u7559\u8868\u8fbe\u5f0f\u548c\u8c03\u7528\u70b9 | \u6700\u7ec8 key\u3001\u8fdc\u7aef\u503c\u548c\u8bed\u4e49 |",
        f"| nonliteral syntax\uff08\u8bc1\u636e\u5f62\u6001\uff0c\u4e0d\u662f dynamic \u53e3\u5f84\uff09 | {metrics['feature_nonliteral_syntax_callsites']} | 11 \u4e2a assignment-resolved + 43 \u4e2a unresolved | \u53ef\u4ee5\u628a 54 \u4e2a\u5168\u90e8\u6807\u4e3a dynamic |",
        f"| \u5168\u90e8 `et()` callsites | {metrics['feature_callsites']} | reader \u8c03\u7528\u9762\u5b8c\u6574 | \u670d\u52a1\u5668\u89c4\u5219\u3001rollout \u6bd4\u4f8b\u3001entitlement |",
        f"| cached dynamic-config static keys | {metrics['dynamic_config_static_keys']} | `CB()` \u7684\u9759\u6001 key \u96c6\u5408 | dynamic config \u5929\u7136 fresh \u6216 schema \u5df2\u9a8c\u8bc1 |",
        f"| \u5168\u90e8 cached dynamic-config callsites | {metrics['dynamic_config_callsites']} | \u9759\u6001\u4e0e\u52a8\u6001 `CB()` \u8c03\u7528\u9762 | \u5f53\u524d payload \u4e0e\u670d\u52a1\u7aef\u89c4\u5219 |",
        "",
        "## \u5b57\u6bb5\u600e\u4e48\u8bfb",
        "",
        "| \u5b57\u6bb5 | \u7cbe\u786e\u542b\u4e49 | \u5e38\u89c1\u8bef\u8bfb |",
        "| --- | --- | --- |",
        "| `defaults` | \u6bcf\u4e2a callsite \u4f20\u7ed9 reader \u7684\u672c\u5730 fallback \u539f\u8868\u8fbe\u5f0f | \u628a\u5b83\u53eb\u670d\u52a1\u7aef\u9ed8\u8ba4\u503c |",
        "| `shape` | \u4ec5\u4ece fallback syntax \u63a8\u5bfc\u7684\u5f62\u72b6\uff0c\u660e\u786e\u662f heuristic | \u628a object-like \u5f53\u6210\u5df2\u9a8c\u8bc1 JSON schema |",
        "| `count/functions` | \u8be5 key \u7684\u9759\u6001\u8c03\u7528\u6b21\u6570\u548c lexical function | \u628a minified function \u540d\u7ffb\u8bd1\u6210\u4e1a\u52a1\u6a21\u5757 |",
        "| `category` | \u540d\u79f0\u5173\u952e\u8bcd\u5bfc\u822a\uff0c\u7edf\u4e00\u6807 `Heuristic/name` | \u628a codenames \u5c55\u5f00\u6210\u4ea7\u54c1\u7ed3\u8bba |",
        "| `meaning/evidence` | \u91cd\u8981 key \u7ed9\u51fa consumer \u673a\u5236\u548c\u4e13\u9898\uff1b\u672a\u8ffd consumer \u7684\u63cf\u8ff0\u6027 key \u6807 Untraced\uff0ccodename \u6807 Opaque/Inventory only | \u4ece key \u540d\u81ea\u884c\u751f\u6210\u5341\u5206\u949f\u6545\u4e8b\uff0c\u6216\u628a\u5ba2\u6237\u7aef\u672a\u5b8c\u6210\u5206\u6790\u4f2a\u88c5\u6210 Boundary |",
        "| `Boundary` | \u5f53\u524d\u8d26\u53f7 payload\u3001server rule\u3001experiment \u5206\u6876\u3001entitlement \u4e0d\u5728 bundle | \u7528\u672c\u5730\u9759\u6001\u8bc1\u636e\u5ba3\u79f0\u7ebf\u4e0a rollout |",
        "",
        "## \u5931\u8d25\u4e0e\u670d\u52a1\u7aef\u8fb9\u754c",
        "",
        "1. `et(key, fallback)` \u7684 fallback \u662f\u5ba2\u6237\u7aef\u8c03\u7528\u70b9\u9ed8\u8ba4\uff0c\u4e0d\u662f\u670d\u52a1\u7aef feature definition \u7684 default\u3002",
        "2. fresh map\u3001disk last-known-good\u3001fallback \u53ef\u4ee5\u8ba9\u540c\u4e00\u7248\u672c\u3001\u4e0d\u540c\u542f\u52a8\u72b6\u6001\u51fa\u73b0\u4e0d\u540c\u7ed3\u679c\u3002",
        "3. consumer \u5fc5\u987b\u81ea\u884c\u9a8c\u8bc1 object/string/number \u7684\u7c7b\u578b\u548c\u8303\u56f4\uff1bFeature manager \u4e0d\u66ff\u4e1a\u52a1\u5b8c\u6210 schema \u6821\u9a8c\u3002",
        "4. policy\u3001permission\u3001provider\u3001host\u3001model\u3001protocol \u548c subscription gate \u53ef\u4ee5\u5728 flag \u4e4b\u540e\u518d\u6b21\u62d2\u7edd\u3002",
        "5. server-side rule\u3001rollout \u767e\u5206\u6bd4\u3001\u5b9e\u9a8c\u5206\u6876\u3001\u7d27\u6025 kill switch\u3001\u8d26\u53f7\u5b9e\u65f6\u503c\u90fd\u5c5e\u4e8e Boundary\u3002",
        "6. 498 \u4e2a\u8c03\u7528\u70b9\u5fc5\u987b\u6309 `455 static-resolvable + 43 truly dynamic` \u8ba1\u6570\uff1b455 \u53c8\u5206\u4e3a 444 direct literal \u548c 11 assignment-resolved\u3002\u4e0d\u80fd\u628a 54 \u4e2a nonliteral syntax \u5168\u90e8\u53eb dynamic\u3002",
        "",
        "## \u4e09\u4e2a\u8bfb\u6cd5\u793a\u4f8b",
        "",
        "### 1. \u5e03\u5c14 fallback",
        "",
        "`!0` \u662f\u538b\u7f29\u540e\u7684 true\uff0c`!1` \u662f false\u3002\u5b83\u53ea\u56de\u7b54\u201cmanager \u6ca1\u7ed9\u503c\u65f6 consumer \u6536\u5230\u4ec0\u4e48\u201d\uff0c\u4e0d\u56de\u7b54\u670d\u52a1\u5668\u662f\u5426\u4e0b\u53d1\u3001\u662f\u5426\u66dd\u5149\u3001\u5176\u4ed6 gate \u662f\u5426\u901a\u8fc7\u3002",
        "",
        "### 2. object fallback",
        "",
        "`tengu_prompt_cache_1h_config` \u7684 fallback \u662f\u5e26 allowlist \u7684 object\uff1b\u8fd9\u80fd\u8bf4\u660e consumer \u671f\u5f85\u914d\u7f6e\u5f62\u72b6\uff0c\u4f46\u4e0d\u80fd\u8bc1\u660e\u670d\u52a1\u7aef\u4e0d\u4f1a\u589e\u52a0\u5b57\u6bb5\uff0c\u4e5f\u4e0d\u80fd\u8bc1\u660e provider \u5b9e\u9645\u547d\u4e2d\u4e00\u5c0f\u65f6\u7f13\u5b58\u3002",
        "",
        "### 3. opaque codename",
        "",
        "`tengu_amber_anchor` \u4e00\u7c7b key \u53ea\u6709 codename\u3001fallback \u548c\u8c03\u7528\u70b9\u3002\u672c\u6587\u4fdd\u7559\u5168\u90e8\u6280\u672f\u8bc1\u636e\uff0c\u540c\u65f6\u660e\u786e `Opaque codename / Inventory only`\uff0c\u4e0d\u4f1a\u628a\u989c\u8272\u6216\u7269\u4f53\u8bcd\u89e3\u91ca\u6210\u865a\u6784\u529f\u80fd\uff1b\u670d\u52a1\u7aef value/rule/rollout \u624d\u5728 Boundary \u5217\u5355\u72ec\u8bb0\u5f55\u3002",
        "",
        "## 361 \u4e2a static feature key \u9010\u9879\u53c2\u8003",
        "",
        f"\u8986\u76d6\u5408\u540c\uff1a`{metrics['feature_keys']}/{metrics['feature_keys']}`\uff0c\u5bf9\u5e94 `{metrics['feature_resolvable_static_callsites']}/{metrics['feature_resolvable_static_callsites']}` \u4e2a\u53ef\u9759\u6001\u6062\u590d\u8c03\u7528\u70b9\u3002`count` \u540c\u65f6\u5305\u542b direct literal \u548c assignment-resolved \u9759\u6001\u8c03\u7528\u3002",
        "",
        "| key | defaults / shape | count / functions | locations | category | meaning / evidence | Boundary |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for key in sorted(feature_keys):
        rows = sorted(calls_by_key.get(key, []), key=lambda item: item["offset"])
        defaults, shapes = feature_defaults(rows)
        boundary = (
            "\u670d\u52a1\u7aef value/rule/rollout \u4e0e consumer reachability \u5747\u672a\u89c2\u5bdf\u3002"
            if rows
            else "key inventory \u6ca1\u6709\u53ef\u6062\u590d callsite group\uff1b\u53ea\u80fd\u8bc1\u660e declaration/surface\u3002"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    compact_code(key),
                    cell(f"{defaults}<br>shape heuristic: {shapes}"),
                    cell(f"{len(rows)} / {feature_functions(rows) if rows else 'none'}"),
                    cell(format_locations(rows)),
                    cell(feature_category(key)),
                    cell(feature_meaning(key)),
                    cell(boundary),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 11 \u4e2a assignment-resolved `et()` \u8c03\u7528\u70b9",
            "",
            "\u8fd9\u4e9b\u8c03\u7528\u70b9\u7684\u7b2c\u4e00\u53c2\u6570\u4e0d\u662f literal\uff0c\u4f46 inventory \u7684 lexical assignment resolver \u80fd\u6062\u590d\u9759\u6001 key\u3002\u5b83\u4eec\u5c5e\u4e8e 455 \u4e2a static-resolvable callsites\uff0c\u4e0d\u5c5e\u4e8e 43 \u4e2a truly dynamic callsites\u3002",
            "",
            "| comparison key | expression | resolver result | local fallback / shape | function | location | evidence / Boundary |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in sorted(resolved_assignment_calls, key=lambda item: item["offset"]):
        argument = row.get("nameArgument", {})
        expression = source_text(argument)
        resolved = argument.get("resolvedStaticValue")
        arguments = row.get("arguments", [])
        fallback = source_text(arguments[1]) if len(arguments) >= 2 else "<missing>"
        result = f"Static assignment resolution: {compact_code(str(resolved))}"
        evidence = "Static\uff1a\u8bed\u6cd5\u4e0d\u662f literal\uff0c\u4f46 inventory resolver \u5df2\u6062\u590d\u9759\u6001 key\uff1b\u771f\u5b9e\u8fd0\u884c value \u4e0e rollout \u4ecd\u662f Boundary\u3002"
        lines.append(
            "| "
            + " | ".join(
                [
                    compact_code(row["comparisonKey"]),
                    compact_code(expression),
                    cell(result),
                    cell(f"{compact_code(fallback)} / shape heuristic: {feature_default_shape(fallback)}"),
                    compact_code(str(row.get("function") or "<top-level>")),
                    source_location(row),
                    cell(evidence),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 43 \u4e2a truly dynamic unresolved `et()` \u8c03\u7528\u70b9",
            "",
            "\u8fd9\u4e9b\u8c03\u7528\u70b9\u65e2\u6ca1\u6709 direct literal\uff0c\u4e5f\u65e0\u6cd5\u7531 assignment resolver \u6062\u590d\u9759\u6001 key\u3002\u672c\u6587\u4fdd\u7559\u8868\u8fbe\u5f0f\u3001fallback\u3001function \u4e0e\u4f4d\u7f6e\uff0c\u4e0d\u731c\u6700\u7ec8\u540d\u79f0\u3002",
            "",
            "| comparison key | expression | local fallback / shape | function | location | evidence / Boundary |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in sorted(unresolved_dynamic_calls, key=lambda item: item["offset"]):
        argument = row.get("nameArgument", {})
        expression = source_text(argument)
        arguments = row.get("arguments", [])
        fallback = source_text(arguments[1]) if len(arguments) >= 2 else "<missing>"
        lines.append(
            "| "
            + " | ".join(
                [
                    compact_code(row["comparisonKey"]),
                    compact_code(expression),
                    cell(f"{compact_code(fallback)} / shape heuristic: {feature_default_shape(fallback)}"),
                    compact_code(str(row.get("function") or "<top-level>")),
                    source_location(row),
                    "Opaque/Boundary\uff1a\u6700\u7ec8 key \u4e0e\u771f\u5b9e\u8fd0\u884c value \u4f9d\u8d56\u6267\u884c\u72b6\u6001\uff1b\u672c\u6587\u4e0d\u751f\u6210\u8bed\u4e49 key \u7ed3\u8bba\u3002",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Cached dynamic config\uff1a6 \u4e2a\u9759\u6001 key / 12 \u4e2a\u8c03\u7528\u70b9",
            "",
            "`CB()` \u4e0d\u662f\u53e6\u4e00\u5957\u5929\u7136\u5b9e\u65f6\u914d\u7f6e\u30022.1.235 \u7684\u8be5 wrapper \u8d70\u540c\u6b65\u7f13\u5b58\u8bfb\u53d6\uff1b6 \u4e2a\u8c03\u7528\u70b9\u4f7f\u7528\u9759\u6001 key\uff0c\u53e6\u5916 6 \u4e2a\u4f7f\u7528\u52a8\u6001\u8868\u8fbe\u5f0f\u3002\u4e0b\u8868\u9010\u8c03\u7528\u70b9\u4fdd\u7559\u9ed8\u8ba4\u503c\u3001shape\u3001function \u548c\u4f4d\u7f6e\u3002",
            "",
            "| comparison key | key / expression | local fallback / shape | function | location | meaning / Boundary |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in sorted(growthbook_calls, key=lambda item: item["offset"]):
        argument = row.get("nameArgument", {})
        value = static_feature_value(row)
        key_or_expression = value if value is not None else source_text(argument)
        arguments = row.get("arguments", [])
        fallback = source_text(arguments[1]) if len(arguments) >= 2 else "<missing>"
        if value is not None:
            meaning = (
                "Static cached dynamic-config key\uff1afallback shape \u53ef\u89c1\uff1bpayload schema\u3001freshness\u3001server rule \u4e0e consumer validation \u4ecd\u662f Boundary\u3002"
            )
        else:
            meaning = "Opaque/Boundary\uff1adynamic key expression\uff1b\u6700\u7ec8 key\u3001payload \u4e0e\u4e1a\u52a1\u542b\u4e49\u5747\u672a\u89c2\u5bdf\u3002"
        lines.append(
            "| "
            + " | ".join(
                [
                    compact_code(row["comparisonKey"]),
                    compact_code(key_or_expression),
                    cell(f"{compact_code(fallback)} / shape heuristic: {feature_default_shape(fallback)}"),
                    compact_code(str(row.get("function") or "<top-level>")),
                    source_location(row),
                    cell(meaning),
                ]
            )
            + " |"
        )

    summary = {
        "artifact": "analysis/feature-flag-reference.md",
        "consumerContractCount": len(consumer_contract_keys),
        "consumerContractKeysSha256": names_sha256(consumer_contract_keys),
        "callsiteOnlyStaticKeyCount": len(callsite_only_keys),
        "dynamicConfigKeysSha256": names_sha256(growthbook_keys),
        "dynamicConfigComparisonKeysSha256": names_sha256(row["comparisonKey"] for row in growthbook_calls),
        "featureKeysSha256": names_sha256(feature_keys),
        "resolvableStaticComparisonKeysSha256": names_sha256(row["comparisonKey"] for row in resolvable_static_calls),
        "resolvedAssignmentComparisonKeysSha256": names_sha256(row["comparisonKey"] for row in resolved_assignment_calls),
        "unresolvedDynamicComparisonKeysSha256": names_sha256(row["comparisonKey"] for row in unresolved_dynamic_calls),
        "generatedBy": "skill/claude-code-version-diff/scripts/build_environment_feature_references.py",
        "inputSha256": hashes,
        "metrics": {key: metrics[key] for key in metrics if key.startswith("feature_") or key.startswith("dynamic_config")},
        "nonliteralSyntaxComparisonKeysSha256": names_sha256(row["comparisonKey"] for row in nonliteral_calls),
        "version": version,
    }
    lines.extend(
        [
            "",
            "<!-- BEGIN:FEATURE_FLAG_REFERENCE:MACHINE_SUMMARY",
            json.dumps(summary, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
            "END:FEATURE_FLAG_REFERENCE:MACHINE_SUMMARY -->",
            "<!-- BEGIN:FEATURE_FLAG_REFERENCE:STATIC_KEYS",
            *sorted(feature_keys),
            "END:FEATURE_FLAG_REFERENCE:STATIC_KEYS -->",
            "<!-- BEGIN:FEATURE_FLAG_REFERENCE:STATIC_RESOLVABLE_COMPARISON_KEYS",
            *(row["comparisonKey"] for row in sorted(resolvable_static_calls, key=lambda item: item["comparisonKey"])),
            "END:FEATURE_FLAG_REFERENCE:STATIC_RESOLVABLE_COMPARISON_KEYS -->",
            "<!-- BEGIN:FEATURE_FLAG_REFERENCE:ASSIGNMENT_RESOLVED_COMPARISON_KEYS",
            *(row["comparisonKey"] for row in sorted(resolved_assignment_calls, key=lambda item: item["comparisonKey"])),
            "END:FEATURE_FLAG_REFERENCE:ASSIGNMENT_RESOLVED_COMPARISON_KEYS -->",
            "<!-- BEGIN:FEATURE_FLAG_REFERENCE:DYNAMIC_UNRESOLVED_COMPARISON_KEYS",
            *(row["comparisonKey"] for row in sorted(unresolved_dynamic_calls, key=lambda item: item["comparisonKey"])),
            "END:FEATURE_FLAG_REFERENCE:DYNAMIC_UNRESOLVED_COMPARISON_KEYS -->",
            "<!-- BEGIN:FEATURE_FLAG_REFERENCE:DYNAMIC_CONFIG_STATIC_KEYS",
            *sorted(growthbook_keys),
            "END:FEATURE_FLAG_REFERENCE:DYNAMIC_CONFIG_STATIC_KEYS -->",
            "<!-- BEGIN:FEATURE_FLAG_REFERENCE:DYNAMIC_CONFIG_COMPARISON_KEYS",
            *(row["comparisonKey"] for row in sorted(growthbook_calls, key=lambda item: item["comparisonKey"])),
            "END:FEATURE_FLAG_REFERENCE:DYNAMIC_CONFIG_COMPARISON_KEYS -->",
            "<!-- BEGIN:FEATURE_FLAG_REFERENCE:CONSUMER_CONTRACT_KEYS",
            *consumer_contract_keys,
            "END:FEATURE_FLAG_REFERENCE:CONSUMER_CONTRACT_KEYS -->",
        ]
    )
    return "\n".join(lines) + "\n"


def write_or_check(path: Path, content: str, check: bool) -> None:
    encoded = content.encode("utf-8")
    if check:
        if not path.exists():
            raise SystemExit(f"missing generated file: {path}")
        if path.read_bytes() != encoded:
            raise SystemExit(f"generated file differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    inventory = repo / "analysis" / "source-inventory"
    version = (repo / "VERSION").read_text(encoding="utf-8").strip()
    env_schema = read_jsonl(inventory / "environment-schema.jsonl")
    env_calls = read_jsonl(inventory / "environment-access-callsites.jsonl")
    feature_keys = sorted(
        line.strip()
        for line in (inventory / "feature-flags.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    feature_calls = read_jsonl(inventory / "feature-flag-callsites.jsonl")
    growthbook_keys = sorted(
        line.strip()
        for line in (inventory / "growthbook-keys.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    growthbook_calls = read_jsonl(inventory / "growthbook-callsites.jsonl")
    metrics = validate_contract(
        version,
        env_schema,
        env_calls,
        feature_keys,
        feature_calls,
        growthbook_keys,
        growthbook_calls,
    )
    hashes = input_hashes(inventory)
    environment_document = build_environment_document(
        version, env_schema, env_calls, metrics, hashes
    )
    feature_document = build_feature_document(
        version,
        feature_keys,
        feature_calls,
        growthbook_keys,
        growthbook_calls,
        metrics,
        hashes,
    )
    environment_path = repo / "analysis" / "environment-variable-reference.md"
    feature_path = repo / "analysis" / "feature-flag-reference.md"
    write_or_check(environment_path, environment_document, args.check)
    write_or_check(feature_path, feature_document, args.check)
    action = "checked" if args.check else "wrote"
    print(
        f"{action}: {environment_path} ({len(environment_document.encode('utf-8'))} bytes, sha256={sha256_bytes(environment_document.encode('utf-8'))})"
    )
    print(
        f"{action}: {feature_path} ({len(feature_document.encode('utf-8'))} bytes, sha256={sha256_bytes(feature_document.encode('utf-8'))})"
    )
    print("metrics=" + json.dumps(metrics, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
