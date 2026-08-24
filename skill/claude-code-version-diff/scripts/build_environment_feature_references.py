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
    "resolved_dynamic_environment_callsites": 7,
    "unresolved_dynamic_environment_callsites": 138,
    "resolved_dynamic_environment_names": 22,
    "resolved_dynamic_only_typed_names": 0,
    "typed_no_static_consumer": 80,
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
    "ANTHROPIC_DEFAULT_FABLE_MODEL": (
        "覆盖 Fable family 的真实 model ID；只有 third-party/custom-model 路径可用且值非空时才替换 alias 解析，随后仍受 provider、catalog capability 和请求兼容性约束。它也决定 model picker 是否生成 Custom Fable 项，失败不会回写环境。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_DEFAULT_FABLE_MODEL_NAME": (
        "只覆盖 Custom Fable 在 model picker 中的 label；产品 consumer 先要求 ANTHROPIC_DEFAULT_FABLE_MODEL 已形成可选项，缺失时回退真实 model ID，不改变 wire model、能力或授权。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_DEFAULT_FABLE_MODEL_DESCRIPTION": (
        "只覆盖 Custom Fable 的 UI description/descriptionForModel；产品 consumer 在 model ID 已生效后读取，缺失回退 `Custom Fable model`，不会改变请求字段、上下文窗口或价格。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": (
        "覆盖 Haiku family 的真实 model ID，并参与 family fallback、可用性判断和模型选择项构造；显式模型参数仍可更高优先级选择别的模型，provider 拒绝该 ID 时没有本地成功保证。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME": (
        "只在 custom Haiku model ID 已形成 picker 项时覆盖 label；缺失回退 model ID，不能据此改变 alias 解析、模型能力、计费或服务端接受度。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_DEFAULT_HAIKU_MODEL_DESCRIPTION": (
        "只覆盖 custom Haiku picker 的说明文字；缺失回退 `Custom Haiku model`，二次 gate 是 third-party/custom model 可用性与非空 model ID，不参与 wire request。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_DEFAULT_OPUS_MODEL": (
        "覆盖 Opus family 的真实 model ID，进入 alias/fallback、1M-window 检测、模型可用性与 picker 构造；第三方 probe 写入的占位默认会被单独识别，显式 CLI/session model 仍可覆盖，服务端能力是 Boundary。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME": (
        "只覆盖 custom Opus picker label；产品 consumer 要求 custom-model gate 和 Opus model ID 同时成立，缺失回退真实 ID，不改变 wire model 或 1M 判定。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_DEFAULT_OPUS_MODEL_DESCRIPTION": (
        "覆盖 custom Opus picker 的 description 与 descriptionForModel 前缀；缺失时按 model ID 的 1M 检测生成默认文案，文本本身不授予长上下文或模型权限。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_DEFAULT_SONNET_MODEL": (
        "覆盖 Sonnet family 的真实 model ID，参与 alias/fallback、1M-window 检测和 picker；客户端会把 third-party probe 写入的占位默认与用户覆盖区分，显式 model 选择优先，provider 拒绝仍会失败。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME": (
        "只覆盖 custom Sonnet picker label；仅在 custom-model gate 和有效 Sonnet model ID 后消费，缺失回退真实 ID，不改变 API model 字段或 capability。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_DEFAULT_SONNET_MODEL_DESCRIPTION": (
        "覆盖 custom Sonnet picker 的说明；缺失时客户端依据 model ID 是否为 1M 生成默认文字，说明文字不改变 context window、价格或远端部署状态。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_AWS_API_KEY": (
        "Anthropic-on-AWS SDK 的 API-key credential 候选；provider 必须先解析为 anthropicAws，skip-auth 未开启时它优先让 SDK 不走 SigV4 provider chain。缺失才尝试显式 AWS credentials/cache chain，错误 key 的远端拒绝不会自动回退身份。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_AWS_BASE_URL": (
        "覆盖 Anthropic-on-AWS endpoint；缺失时按已解析 AWS region 生成 `https://aws-external-anthropic.<region>.api.aws`。自定义 endpoint 还会关闭部分 first-party/eager-streaming 假设，region、workspace、auth 和网络仍是二次 gate。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_AWS_WORKSPACE_ID": (
        "写入 Anthropic-on-AWS SDK 的 `anthropic-workspace-id` header；只有 anthropicAws provider consumer 会使用，skip-auth 之外缺失会在 client 构造阶段报 `No workspace ID found`，值存在也不证明 workspace 可访问。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_BEDROCK_BASE_URL": (
        "覆盖 Bedrock control/runtime endpoint；缺失时由解析后的 region 生成标准 AWS host。consumer 仍先选择 bedrock provider并装配 proxy/CA/auth；自定义 host 会改变 first-party transport 假设，连接或签名失败不回退到 Anthropic API。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_BEDROCK_MANTLE_BASE_URL": (
        "覆盖 Mantle endpoint；缺失时按 region 生成 `bedrock-mantle.<region>.api.aws`。只有 mantle provider 或叠加 route 消费，bearer/AWS credential、proxy 和 deployment capability 仍是 gate，endpoint 可达不证明模型可用。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_BEDROCK_REGION_PREFIX": (
        "覆盖跨区 Bedrock model ID 的 region prefix；typed enum 只接受发布物列出的区域 token，非法值被解析为未设置并回落 model/region 推导。它不改变 AWS client region、endpoint 或授权。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_BEDROCK_SERVICE_TIER": (
        "仅在 Bedrock request client 分支把非空值写入 `X-Amzn-Bedrock-Service-Tier`，并在 status 中展示；provider 选择、region、auth 和 deployment 支持仍是 gate。上游忽略或拒绝该 header 属于服务端 Boundary。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_FOUNDRY_API_KEY": (
        "Microsoft Foundry SDK 的 API-key credential source；只在 foundry provider 分支消费，显式 ANTHROPIC_FOUNDRY_AUTH_TOKEN 优先，二者都缺失时才尝试 skip-auth 或 DefaultAzureCredential。错误 key 的远端拒绝不会触发 Azure AD fallback。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_FOUNDRY_AUTH_TOKEN": (
        "Foundry 的显式 bearer-token provider，优先于 API key 缺失后的 DefaultAzureCredential；consumer 用函数按请求返回 token。它仍要求 foundry route、base/resource endpoint 和上游接受，客户端不会校验 token 权限。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_FOUNDRY_BASE_URL": (
        "覆盖 Foundry endpoint；未设置时可由 ANTHROPIC_FOUNDRY_RESOURCE 推导 `https://<resource>.services.ai.azure.com/anthropic/`，但 SDK 明确拒绝同时设置 base URL 和 resource。只有 foundry provider 消费，URL、credential 或 deployment 失败都不会切回一方 API。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_FOUNDRY_RESOURCE": (
        "在未给 Foundry base URL 时用作 Azure resource 名并推导 endpoint，同时显示在 provider status；与 ANTHROPIC_FOUNDRY_BASE_URL 同时存在会在 SDK client 构造期报互斥错误。resource 字符串不验证 DNS、tenant、deployment 或访问权限。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_GOOGLE_CLOUD_BASE_URL": (
        "覆盖 Anthropic-on-Google-Cloud endpoint；缺失回退 `https://claude.googleapis.com`。consumer 还要求该 provider 被选择，并解析 project/location/workspace 与 Google auth；自定义 host 会改变 transport 假设，不能继承一方能力。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_GOOGLE_CLOUD_LOCATION": (
        "Anthropic-on-Google-Cloud location 输入，缺失时 SDK 回落 `global`；请求前还要求值通过仅字母/数字/连字符/下划线的 path-segment gate。project、workspace、auth 和 deployment 仍独立校验，location 不等于 Vertex region。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_GOOGLE_CLOUD_PROJECT": (
        "Anthropic-on-Google-Cloud project 的最高优先级显式输入，缺失回落 GOOGLE_CLOUD_PROJECT；请求前还要通过 path-segment 字符集 gate。它参与 endpoint path 构造，但不替代 workspace ID 或 Google credential。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_GOOGLE_CLOUD_WORKSPACE_ID": (
        "把 Anthropic-on-Google-Cloud 请求绑定到 workspace path；请求前先过 path-segment 字符集 gate，普通 auth 模式缺失会在 client 构造期报错。project/location/auth 都是二次 gate，值存在不能证明远端 workspace 可访问。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_VERTEX_BASE_URL": (
        "覆盖 Vertex API base URL；缺失时根据解析后的 CLOUD_ML_REGION 生成 global/us/eu 或区域 aiplatform host。Vertex provider、project、Google auth 和 model deployment 仍是 gate，自定义 host 会关闭部分 eager-input 默认。",
        "models-auth-providers-request.md",
    ),
    "ANTHROPIC_VERTEX_PROJECT_ID": (
        "Vertex SDK constructor 的 projectId 环境默认，同时在没有 GCLOUD/GOOGLE_CLOUD_PROJECT 与 GOOGLE_APPLICATION_CREDENTIALS hint 时传给 Google auth builder；credential 的 x-goog-user-project 仍可补位。消息路由前最终无法解析 project 会直接报错。",
        "models-auth-providers-request.md",
    ),
    "BASH_MAX_OUTPUT_LENGTH": (
        "解析为 Bash 前台输出保留字符上限；未设置回落 30000，非数字或 <=0 记录 invalid 并回落，超过 150000 被 capped。它只改变返回给模型/用户的输出截断，不限制子进程真实 stdout、执行时间或外部副作用。",
        "builtin-tools-reference.md",
    ),
    "API_TIMEOUT_MS": (
        "模型 API client timeout 的环境覆盖；主 client 未设置或非数字时回落 600000ms，Agent Loop attempt resolver 在解析结果为 falsy 时按 remote 120000ms、local 300000ms。源码没有正数 clamp，timeout 终止等待并进入 retry/failure 合同，不回滚已有副作用。",
        "resilience-and-recovery.md",
    ),
    "CLAUDE_CODE_ARTIFACT": (
        "Artifact 总体偏好输入：显式 false 使 eligibility 直接失败，显式 true 仅越过部分 SDK/default-off 判断；仍需 first-party、host/surface、admin policy、account flag 和 tool registration 全部成立。它不代表 publish 已发生。",
        "artifact-watch-comment-autoreact.md",
    ),
    "CLAUDE_CODE_ARTIFACTS_API_TOKEN": (
        "frame host 的专用 bearer token；只有 frame host override 可用时替换普通 claude.ai OAuth header，并在 child/tool env scrub 中删除。token 只认证请求，不绕过 Artifact eligibility、slug/version 校验或服务端授权。",
        "artifact-watch-comment-autoreact.md",
    ),
    "CLAUDE_CODE_ARTIFACT_ASSETS": (
        "Artifact supporting-assets tri-state gate，未设置默认 true；false 会阻止资产读取/上传路径，但不关闭单文件 Artifact 或已发布资源。文件类型、大小、inode/stability 和 remote upload 仍逐项校验。",
        "artifact-watch-comment-autoreact.md",
    ),
    "CLAUDE_CODE_ARTIFACT_AUTO_OPEN": (
        "Artifact 发布成功后的 auto-open 抑制输入：值被判为 false 时记录 `auto_open_skipped_env`；redeploy、background、teammate、remote、desktop/IDE pane 也会独立跳过。它不影响发布 side effect，只影响随后打开 URL。",
        "artifact-watch-comment-autoreact.md",
    ),
    "CLAUDE_CODE_ARTIFACT_COMMENTS": (
        "Artifact comment pipeline 的最高优先级 tri-state；未设置才读取 `tengu_teal_corbel`。开启后仍需 watch/session、auth、thread schema 与轮询状态成立，关闭不会删除远端已有评论或撤销已经派发的回复。",
        "artifact-watch-comment-autoreact.md",
    ),
    "CLAUDE_CODE_ARTIFACT_COMMENTS_AUTOREACT": (
        "自动评论反应的 session-latched opt-in，优先于 `tengu_sorrel_trellis`；comment pipeline、规则匹配、权限和 responder dispatch 仍是二次 gate。关闭只阻止后续自动反应，不撤销已发送 reaction/reply。",
        "artifact-watch-comment-autoreact.md",
    ),
    "CLAUDE_CODE_ARTIFACT_COMMENT_FAST_ACK": (
        "控制 comment fast-ack 外层 gate，未设置回退 `tengu_gorse_pylon`；显式 false 还跳过异步 flag refresh。只有评论触发、规则和远端写入都成功才有 ack side effect，失败不会替代完整 responder。",
        "artifact-watch-comment-autoreact.md",
    ),
    "CLAUDE_CODE_ARTIFACT_COMMENT_FAST_ACK_FIXED": (
        "固定 fast-ack 行为的内层 tri-state，优先于 `tengu_gorse_sill`；只有 fast-ack 外层开启时消费。值存在会阻止动态 refresh，仍不绕过 comment eligibility、auth 或远端错误。",
        "artifact-watch-comment-autoreact.md",
    ),
    "CLAUDE_CODE_ARTIFACT_COMMENT_RESPONDER": (
        "把 comment-thread analyst responder dispatch 设为 session-latched opt-in，未设置回退 `tengu_bracken_sluice`；主 agent、深度、评论规则和工具权限仍会选择 pipeline 或 child responder。已发出的评论是不可回滚远端副作用。",
        "artifact-watch-comment-autoreact.md",
    ),
    "CLAUDE_CODE_ARTIFACT_DB": (
        "Artifact comment/database-backed state路径的 tri-state，未设置回退 `tengu_umber_lattice`；开启只允许进入 DB API consumer，仍受 host、auth、schema、403 capability 和 degraded fallback 约束，不创建本地数据库。",
        "artifact-watch-comment-autoreact.md",
    ),
    "CLAUDE_CODE_ARTIFACT_DIRECT_UPLOAD": (
        "强制发布选择 direct-upload lane，优先于 signed upload/preflight thumbnail 分支；createPath、特定 entrypoint 或远端 flag 也可选择同一路径。它不绕过 page/asset validation、auth、version conflict 或 publish failure。",
        "artifact-watch-comment-autoreact.md",
    ),
    "CLAUDE_CODE_DISABLE_ARTIFACT": (
        "Artifact 硬 disable gate，优先于用户偏好、remote flag 和 plan/workshop 子特性，并记录 env disable reason；它阻止后续 tool/configurability 路径，但不能撤销已经发布的页面、评论或分享版本。",
        "artifact-watch-comment-autoreact.md",
    ),
    "CLAUDE_CODE_PLAN_ARTIFACTS": (
        "Plan 中 Artifact-first/workshop offer 的最高优先级 tri-state，未设置回退 `tengu_basalt_loom`；仍要求 Workshop 可用且不在排除 surface。它只改变计划阶段 offer/注册，不证明发布调用发生。",
        "workflow-artifact-design.md",
    ),
    "CLAUDE_CODE_DISABLE_AGENT_VIEW": (
        "Agent View 的环境硬 gate，优先于 `disableAgentView` setting；命中后 availability 返回明确禁用原因，daemon/PTY/background task 本身仍可运行。它关闭查看/交互表面，不终止已有 agent 或回滚工具副作用。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_CODE_DISABLE_ATTACHMENTS": (
        "关闭 turn 前 attachment 扩展与 attachment reminder section；simple/bare-fork 还有独立 gate，inputMentionsOnly 路径保留最小处理。它不删除 transcript 中已有附件，也不阻止用户文字或已完成上传。",
        "tui-input-accessibility-media-ide-chrome.md",
    ),
    "CLAUDE_CODE_DISABLE_MEMORY_BULK_INFLATE": (
        "禁止 multi-store 初始同步调用 backend.exportAll bulk inflate；还需远端 hashes/invalidated basis 为空且 feature flag 开启才原本可达。关闭该优化会返回 `not-attempted`，后续逐项/其他同步路径仍可运行。",
        "sessions-checkpoints-memory.md",
    ),
    "CLAUDE_CODE_DISABLE_MEMORY_MASS_DELETE_HOLD": (
        "把 memory mass-delete hold 阈值设为正无穷，使批量删除永远进入保护而非按比例阈值执行；backend 仍需可写、delete mode 和 corroboration 成立。它不恢复已删除远端对象，也不关闭普通写入。",
        "sessions-checkpoints-memory.md",
    ),
    "CLAUDE_CODE_DISABLE_MEMORY_PERIODIC_RESYNC": (
        "让 multi-store periodic resync interval resolver 返回 0，优先于远端分钟配置及最小间隔 clamp；只取消周期定时器，首次 pull、watch-triggered sync 和显式恢复仍是独立路径。",
        "sessions-checkpoints-memory.md",
    ),
    "CLAUDE_CODE_DISABLE_MEMORY_STREAM_LIST": (
        "阻止 backend.exportMetadata 的 stream-list 优化；原路径还要求 backend 支持、未标记 unsupported、退避到期且 feature flag 开启。关闭后不会清空 memory，consumer 会使用其余 discovery/sync 路径。",
        "sessions-checkpoints-memory.md",
    ),
    "CLAUDE_CODE_ENABLE_BACKGROUND_PLUGIN_REFRESH": (
        "允许主 Agent Loop 在插件同步标记 `needsRefresh` 后于 turn 边界后台执行 refresh；仍要求确有 refresh 请求，异常只记录并继续。它不绕过 plugin trust/install/MCP discovery，也不保证刷新内容进入当前已发送请求。",
        "plugins-skills-commands-lsp.md",
    ),
    "CLAUDE_CODE_SKIP_PLUGIN_MCP_SERVERS": (
        "在 plugin MCP discovery 入口默认跳过全部 plugin server；EXCEPT allowlist 可按 plugin name/repository 重新放行，plugin 自带 skipMcpDiscovery 和路径安全检查仍继续执行。它不卸载已经连接的 MCP server。",
        "plugins-skills-commands-lsp.md",
    ),
    "CLAUDE_CODE_SKIP_PLUGIN_MCP_SERVERS_EXCEPT": (
        "CLAUDE_CODE_SKIP_PLUGIN_MCP_SERVERS 的逗号分隔例外表；空项忽略，带 `@` 的项匹配 repository，其余只对非 repo-supplied plugin 匹配 name。主 skip 未开启时没有效果，也不绕过 trust/path/download 校验。",
        "plugins-skills-commands-lsp.md",
    ),
    "CLAUDE_CODE_PLUGIN_GIT_TIMEOUT_MS": (
        "覆盖 plugin marketplace git clone/fetch/submodule timeout；typed 值必须为正数，否则回落内置预算。超时被改写成带秒数的诊断，已完成的部分 clone/file side effect 可能残留，host-key 与 credential 失败不因延长 timeout 修复。",
        "plugins-skills-commands-lsp.md",
    ),
    "ALL_PROXY": (
        "Dependency consumer 的通用 proxy fallback：Git helper 在 HTTPS_PROXY 缺失时读取 ALL_PROXY，bundled proxy policy 也把它作为独立 scheme。NO_PROXY、大小写别名、协议支持和每个 transport adapter 仍分别决定路由，设置它不覆盖所有请求。",
        "network-proxy-ca-and-mtls.md",
    ),
    "AWS_SHARED_CREDENTIALS_FILE": (
        "Dependency consumer 的 AWS shared-credentials 路径覆盖，和 access key、profile、config file 一起决定 provider chain；显式 API key/bearer/skip-auth 可使它不被使用。文件缺失、权限或 profile 解析失败不会回退成匿名成功。",
        "models-auth-providers-request.md",
    ),
    "AWS_CONTAINER_CREDENTIALS_FULL_URI": (
        "Dependency consumer 的 ECS/container credential endpoint 完整 URI；AWS chain 只有在更高优先级显式 credential 未命中时才访问，并校验允许的 host/protocol、auth token 与短 timeout。URL 存在不证明 metadata endpoint 可信或返回有效凭据。",
        "models-auth-providers-request.md",
    ),
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": (
        "Dependency consumer 的 ECS credential 相对路径，拼到容器 metadata host；与 FULL_URI 二选一并受 provider-chain precedence、endpoint 校验和 timeout 约束。读取失败只让该 credential source 失败，不证明模型请求已发送。",
        "models-auth-providers-request.md",
    ),
    "GOOGLE_APPLICATION_CREDENTIALS": (
        "Dependency consumer 的 Google service-account/ADC JSON 文件路径；Vertex/Google Cloud provider 在显式 skip-auth 未开启时读取，文件错误会附加明确诊断。project resolution、token exchange、scope 和 deployment 仍是后续 gate，路径会从普通 child env scrub。",
        "models-auth-providers-request.md",
    ),
    "CLAUDE_CODE_PROXY_RESOLVES_HOSTS": (
        "让 HTTPS proxy agent 的 lookup 回调把原 hostname 交给 proxy 解析，避免客户端本地 DNS；只影响使用该 agent 的 transport，NO_PROXY、proxy URL、CA/mTLS 和不走该 adapter 的 SDK 仍独立。",
        "network-proxy-ca-and-mtls.md",
    ),
    "CLAUDE_CODE_PROXY_AUTH_HELPER_TTL_MS": (
        "设置 proxy-auth helper 结果缓存 TTL；非负 typed 值生效，否则回落内置 TTL。enable gate、helper 命令、challenge 和 credential refresh 仍需成功；缓存到期只触发重新取值，不撤销已建立连接。",
        "network-proxy-ca-and-mtls.md",
    ),
    "CLAUDE_CODE_WEBFETCH_USE_CCR_PROXY": (
        "只在 first-party provider 且存在可用 CCR session/relay 时把 WebFetch 切到 CCR proxy route；false 或 relay 不可达时保留普通工具路径。proxy 429/5xx 仍按工具合同失败/重试，不改变 URL permission gate。",
        "network-proxy-ca-and-mtls.md",
    ),
    "CLAUDE_CODE_WEBSEARCH_USE_CCR_PROXY": (
        "只在 first-party provider 且当前 session 有 CCR proxy 能力时让 WebSearch 调用 CCR route；查询域名过滤、auth、schema 和上游错误仍是 gate。它不证明搜索由本地网络发出，也不覆盖普通 API transport。",
        "network-proxy-ca-and-mtls.md",
    ),
    "CLAUDE_BG_AUTH_SNAPSHOT_PATH": (
        "background worker 的一次性认证快照文件路径；启动读取后立即从环境删除并异步 unlink，JSON 内容再经过 accessToken/scopes 等字段校验。文件缺失或损坏不会成为有效 auth，且普通 child env scrub 会移除该路径。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_BG_RV_AUTH": (
        "background rendezvous socket 的一次性 bearer；worker 读取后从环境删除，若 token file 提供 rvAuth 则后者覆盖。它只认证 rendezvous frame，不替代 PTY auth、task permission 或模型 credential，失败不会回滚 child 已有副作用。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_BRIDGE_REATTACH_SESSION": (
        "指定 Remote Control bridge 要重附着的 session；优先于普通 option，并与 seq/grouping/owner/no-backfill/outbound-only 组成一次性 handoff，读取后整组 env 被删除。hydrate/owner 校验失败仍可拒绝重附着，远端历史与本地 transcript 不自动等价。",
        "remote-routines-runner-and-notifications.md",
    ),
    "CLAUDE_CODE_FABLE_BRIDGE_DIALOG_TIMEOUT_MS": (
        "设置 Fable bridge user-dialog 等待预算；typed 值必须大于 0，否则回落 60000ms。timeout 结束等待并进入取消/失败分支，不代表用户拒绝，也不会撤销 dialog 前已经完成的工具或远端副作用。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS": (
        "设置 MCP tool 自动转后台阈值并 clamp 到 0..内置上限；显式值优先于 `tengu_mcp_auto_background`，某些 tool type、环境和 pending elicitation 可禁止 background。转后台只改变等待/registry owner，不重启调用。",
        "mcp-agents-background.md",
    ),
    "CCR_SHR_SSE_HINTS": (
        "self-hosted runner 的 work-hints SSE gate；开启后 runner 使用当前 base URL、runner ID 和 token state 建立提示流，并只用 wake signal 触发调度。断流不等于 session 失败，polling/renewal 与 auth 仍独立。",
        "remote-routines-runner-and-notifications.md",
    ),
    "CCR_SPAWN_TIMESTAMP_MS": (
        "self-hosted/CCR parent 在 spawn 时写入毫秒时间戳，child 用它计算 spawn-to-checkpoint/exec/input/API-request telemetry；非法值被忽略并可回落 CLAUDE_CODE_SPAWN_TIMESTAMP_MS。它只影响观测字段，不控制 timeout 或 readiness。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_AGENT_SDK_VERSION": (
        "Agent SDK caller 的版本标记；SDK entrypoint 未设置时写 `unknown`，随后进入 User-Agent、请求元数据和 telemetry workload 字段。它不改变协议、工具权限或模型能力，任意字符串也不证明 SDK 与 CLI 兼容。",
        "cli-sdk-output-protocol.md",
    ),
    "CLAUDE_AGENT_SDK_CLIENT_APP": (
        "Agent SDK 宿主应用标识，进入 `client-app/<value>` User-Agent 片段和 `x-client-app` 请求 header；只用于归因/路由上下文，不授予 host capability，服务端如何解释属于 Boundary。",
        "cli-sdk-output-protocol.md",
    ),
    "CLAUDE_AGENT_SDK_MCP_NO_PREFIX": (
        "仅对 `config.type === sdk` 的 MCP server 关闭普通 namespacing prefix；其他 stdio/http/sse 配置不受影响。它改变模型看到的工具名，但不绕过 server trust、权限、schema 冲突或连接失败。",
        "connectors-catalog-and-mcp-operators.md",
    ),
    "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": (
        "在 Agent SDK runtime 中把 builtin-agent selection mode 强制为 `none`；非 SDK CLI 不消费该 gate。它只移除内置 agent 定义，显式 SDK agents、普通工具和主 Agent Loop 仍可存在。",
        "mcp-agents-background.md",
    ),
    "CLAUDE_AGENTS_SELECT": (
        "Agent View/selector 的一次性目标 ID；UI 读取后从环境删除，内部跳转会在重挂载前重新写入。目标不存在时仍由 selector 状态处理，变量不启动 agent、不恢复 task，也不改变权限。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_CODE_SUBAGENT_MODEL": (
        "subagent/teammate model 的最高优先级覆盖，`inherit` 视为不覆盖；实际 precedence 为 env > tool > frontmatter > parent/default。若不在 availableModels allowlist，按 family 降级或继承 parent，并记录原因，不保证远端接受。",
        "mcp-agents-background.md",
    ),
    "CLAUDE_CODE_FORK_SUBAGENT": (
        "fork-subagent tri-state：显式 false 硬关闭，显式 true 把来源记为 env，未设置走默认；更高层 child/context gate 仍可禁用。它只允许构造隔离 child messages/worktree，不复制父工具副作用。",
        "mcp-agents-background.md",
    ),
    "CLAUDE_CODE_DISABLE_EXPLORE_PLAN_AGENTS": (
        "Explore/Plan builtin agent registry 的 session-latched disable；首次求值后缓存，后续改环境不会重建当前 registry。它不关闭显式自定义 subagent、Plan Mode 或已运行 child。",
        "plan-mode-and-human-approval.md",
    ),
    "CLAUDE_CODE_ENABLE_APPEND_SUBAGENT_PROMPT": (
        "允许 child system prompt 追加 parent 提供的 subagent prompt；还要求非 isolated context、非受限 child shape 且调用方确有追加内容。它增加 child context/token，不提升工具权限或突破 prompt/tool policy。",
        "mcp-agents-background.md",
    ),
    "CLAUDE_CODE_FORWARD_SUBAGENT_TEXT": (
        "允许 SDK/remote 输出投影 subagent text，和显式 host option 构成 OR gate；只影响事件可见性，不把 child transcript 合并为主线程历史，也不改变 tool_result pairing。",
        "cli-sdk-output-protocol.md",
    ),
    "CLAUDE_CODE_PLAN_V2_AGENT_COUNT": (
        "Plan V2 主并行 agent 数；仅接受 1..10，否则按订阅档位回落 3 或普通回落 1。实际 spawn 仍受 concurrent-subagent、permission、model 与 budget gate，调高不保证全部启动。",
        "plan-mode-and-human-approval.md",
    ),
    "CLAUDE_CODE_PLAN_V2_EXPLORE_AGENT_COUNT": (
        "Plan V2 explore fanout 数；仅接受 1..10，非法或缺失回落 3。它是计划阶段目标并发，不覆盖全局 subagent 上限、失败重试或每个 child 的独立上下文成本。",
        "plan-mode-and-human-approval.md",
    ),
    "CLAUDE_AUTO_BACKGROUND_TASKS": (
        "非交互 MCP/任务自动转后台 gate；noninteractive 未开启时阈值直接为 0，开启时另一 resolver 使用 120000ms 默认。tool type、elicitation 和显式 auto-background threshold 仍可阻止，转后台不重放调用。",
        "mcp-agents-background.md",
    ),
    "CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS": (
        "异步 agent 观察器的 stall budget，truthy typed 值优先，0/缺失回落 600000ms；达到预算会进入 stalled/恢复判断。它不杀死已经脱离 owner 的外部进程，也不回滚 child 工具副作用。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_SUBAGENT_BG_SHELL_MAX_MS": (
        "subagent background shell 的最大等待预算，typed 正整数优先，否则回落内置值；超时只结束 child 对该 shell 的等待/监督，进程清理和外部副作用仍由独立 lifecycle 决定。",
        "mcp-agents-background.md",
    ),
    "CLAUDE_CODE_ENABLE_TODO_TOOLS": (
        "显式开启 Todo tool surface；IDE/特殊 host fast path 或 `tengu_rosy_wren` 也可开启。它只让工具可注册，仍需 request-time assembly、permission 和有效 tool input，不能证明 Todo 已写入。",
        "builtin-tools-reference.md",
    ),
    "CLAUDE_CODE_TODO_REMINDER_MODE": (
        "Todo reminder 的最高优先级枚举，仅允许 `baseline`/`off`；未设置回退 `tengu_soft_slate_nudge`。它控制 attachment reminder，不删除 Todo 状态，也不关闭 Todo tools。",
        "agent-loop.md",
    ),
    "CLAUDE_CODE_TOTAL_TOKENS_REMINDER_AFTER_USER_TURN": (
        "控制 total-token reminder 是否在 user turn 后注入，env tri-state 优先于 setting，再回退远端 flag 默认 true；状态在 session cache 中锁存。它只增加提示 attachment，不改变真实 context window 或计费。",
        "context-governance-and-caching.md",
    ),
    "CLAUDE_CODE_TURN_UPDATES": (
        "turn-updates attachment 的 tri-state输入，由通用 gate 与 host capability共同求值；命中时加入对应动态 section。它不改变 message owner、stream parser 或 tool execution，只改变模型收到的运行状态提示。",
        "agent-loop.md",
    ),
    "CLAUDE_CODE_WEB_FETCH_AGENT": (
        "WebFetch child-agent 路径的最高优先级 tri-state，未设置回退 `tengu_clever_orbit` 并在进程中缓存；URL permission、网络 route、模型/工具预算仍是 gate。开启不等于每次 WebFetch 都 spawn child。",
        "builtin-tools-reference.md",
    ),
    "CLAUDE_MEMORY_STORES": (
        "声明 memory store JSON 数组；解析要求绝对且不覆盖 host 的 path、唯一 mount、最多一个 user scope、合法 rw/ro 与 prompt-index/skills path。无效 JSON/重复 mount 会报错，部分便捷 consumer catch 后视为无 store；显式 stores 还关闭 org discovery。",
        "sessions-checkpoints-memory.md",
    ),
    "CLAUDE_CODE_REMOTE_MEMORY_DIR": (
        "remote session 的 memory 根目录覆盖，优先用于拼接 projects/<project>/agent-memory-local；remote 且该值和 Cowork override 都缺失时 memory path eligibility 可直接关闭。目录存在不证明内容已同步或可信。",
        "sessions-checkpoints-memory.md",
    ),
    "CLAUDE_COWORK_MEMORY_GUIDELINES": (
        "显式替换 Cowork auto-memory system prompt 的主体；非空时优先返回该文本并跳过 base prompt variant，同时仍执行 memory load telemetry/state更新。它不写 memory 文件，也不授予 remote store 权限。",
        "background-model-tasks-and-memory-consolidation.md",
    ),
    "CLAUDE_COWORK_MEMORY_EXTRA_GUIDELINES": (
        "追加到正常 Cowork memory prompt 的额外规则；仅在未被完整 GUIDELINES 主体替换且 memory path/store可用时有意义。内容进入模型上下文并增加 token，但不是持久 memory write。",
        "background-model-tasks-and-memory-consolidation.md",
    ),
    "CLAUDE_COWORK_MEMORY_INDEX_CONTENT": (
        "控制 Cowork memory index content 注入；空字符串显式关闭，未设置会结合 host/remote/memory eligibility 决定是否读取 index。它只影响 prompt附件，磁盘 index、remote store 与同步状态不被删除。",
        "sessions-checkpoints-memory.md",
    ),
    "CLAUDE_COWORK_MEMORY_PATH_OVERRIDE": (
        "覆盖 Cowork auto-memory 路径并经 path normalizer 解析；在 remote memory dir 缺失时也可恢复 eligibility。非法/不可写路径仍会在文件 consumer 失败，覆盖不代表 store 已挂载或同步。",
        "sessions-checkpoints-memory.md",
    ),
    "CLAUDE_CODE_DISABLE_PRECOMPACT_SKIP": (
        "关闭超大 transcript 的 pre-compact 快速跳读/边界裁剪优化：文件读取和 resume hydration 会改走完整读取再按 leaf规则处理。它不关闭 compact 本身，反而可能增加启动 I/O 与内存。",
        "context-governance-and-caching.md",
    ),
    "CLAUDE_AFTER_LAST_COMPACT": (
        "为特定 history API GET 增加 `after_last_compact=true` 查询参数；只有 truthy 时生效，HTTP timeout 固定由该 consumer另管。它请求服务端裁剪视图，不创建 compact boundary，也不证明服务端返回已压缩历史。",
        "context-governance-and-caching.md",
    ),
    "CLAUDE_BG_MEMORY_TOGGLED_OFF": (
        "仅在 `CLAUDE_CODE_SESSION_KIND=bg` 且值精确为 `1` 时恢复 memory-off state；前台 session 忽略。它阻止 background memory行为，但不删除既有 memory、CLAUDE.md 或 transcript。",
        "background-model-tasks-and-memory-consolidation.md",
    ),
    "CLAUDE_CODE_COLD_COMPACT": (
        "选择 cold-compact eligibility 分支的客户端布尔输入；仍需 compact trigger、上下文阈值和 summary pipeline 到达。它不等同于立即执行 `/compact`，也不能保证远端 summary 成功。",
        "context-governance-and-caching.md",
    ),
    "CLAUDE_CODE_DISABLE_ORG_MEMORY": (
        "organization memory discovery 的首个硬 disable gate；命中后不再检查 first-party、feature flag、policy capability 或账户状态。显式 CLAUDE_MEMORY_STORES 和本地 user memory 是不同 owner，不会被一并删除。",
        "sessions-checkpoints-memory.md",
    ),
    "CLAUDE_CODE_MEMORY_PUSH_DELETE_MODE": (
        "memory push 的 delete policy 最高优先级枚举：`immediate`、`never`、`corroborate`；未设置回退远端值，未知远端值降为 corroborate。它只决定后续删除候选处理，已删除对象不可恢复。",
        "sessions-checkpoints-memory.md",
    ),
    "CLAUDE_CODE_TOOL_MEMORY_LIMIT": (
        "Linux tool cgroup memory ceiling；`false`/`none` 关闭，其他值经 size parser，缺失且 feature flag关闭则不配置。写 `/proc/self/cgroup`/limit 文件失败只记录 disabled/error，不限制主 CLI 内存，也不撤销子进程副作用。",
        "runtime-supervision-and-processes.md",
    ),
    "ENABLE_PROMPT_CACHING_1H_BEDROCK": (
        "只在当前 provider 为 Bedrock 时开启 1h prompt-cache eligibility；通用 ENABLE_PROMPT_CACHING_1H 仍可对所有合格 provider生效。request cache_control、模型支持和真实 hit/计费属于后续 gate/Boundary。",
        "context-governance-and-caching.md",
    ),
    "CLAUDE_CODE_SYNC_PLUGIN_INSTALL": (
        "启用同步 plugin install/reconcile，并在 startup/headless 路径等待 registry refresh、安装与 MCP diff；remote/host模式仍可另行触发。失败被记录且部分路径继续启动，已下载文件可能残留。",
        "plugins-skills-commands-lsp.md",
    ),
    "CLAUDE_CODE_PLUGIN_CACHE_DIR": (
        "覆盖 plugin cache 根目录并解析为绝对路径；未设置回落 config 下的普通或 Cowork cache。它同时影响 zip cache/marketplace data位置，目录可写性、trust 和内容 hash 仍需验证。",
        "plugins-skills-commands-lsp.md",
    ),
    "CLAUDE_CODE_SKILL_PROPOSALS": (
        "显式允许 skill-proposal discovery/consumer，和产品 eligibility 构成 OR gate；后续仍检查 session、proposal schema、用户确认及写入路径。它不自动安装或启用提议的 skill。",
        "plugins-skills-commands-lsp.md",
    ),
    "CLAUDE_CODE_SYNC_SKILLS": (
        "启用远端 skill 同步，进入后台 fetch 并与 storage-v5 本地 entries 合并；某些 host eligibility 也可触发。网络/认证失败保留本地状态，下载成功也不绕过 skill trust与名字冲突处理。",
        "plugins-skills-commands-lsp.md",
    ),
    "MCP_TOOL_TIMEOUT": (
        "MCP tool-call 总 timeout fallback；单 server 配置且 >=1000ms 时优先，其次正数 env，最后内置值，并 clamp 到 1s..全局上限。timeout 终止等待，不证明 server取消执行或回滚外部副作用。",
        "mcp-agents-background.md",
    ),
    "CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT": (
        "MCP tool idle watchdog；未设置按 stdio 与 remote transport 使用不同默认，<=0关闭，最终至少覆盖 server timeout并不超过总 tool timeout。它检测无进展，不替代连接 timeout 或模型 turn上限。",
        "mcp-agents-background.md",
    ),
    "CLAUDE_CODE_SYNC_PLUGINS": (
        "启用远端 plugin catalog同步，并与 storage-v5 plugin entries并行读取；host eligibility 也可触发。同步失败不删除已安装 plugin，成功 catalog 仍需安装、trust、platform与MCP reconcile。",
        "plugins-skills-commands-lsp.md",
    ),
    "CLAUDE_CODE_TERMINAL_MCP_TOOLS": (
        "逗号分隔的 terminal MCP tool 名单；trim 后空项丢弃，并在 terminal/tool投影处构成 Set。名单只影响哪些已存在工具进入 terminal surface，不连接 server、不验证名称，也不绕过 permission。",
        "connectors-catalog-and-mcp-operators.md",
    ),
    "CLAUDE_CODE_USE_COWORK_PLUGINS": (
        "强制 plugin settings/cache选择 Cowork 变体；否则由 host/cowork config决定。它改变配置和缓存 owner，不自动信任、安装或启用任何 plugin，错误目录仍会失败。",
        "plugins-skills-commands-lsp.md",
    ),
    "MCP_CLIENT_SECRET": (
        "MCP OAuth confidential-client secret；环境值优先，缺失时仅 TTY 可无回显交互输入，headless 直接报错。它参与 token exchange，但不替代 client_id、redirect/state/PKCE 或服务端授权。",
        "connectors-catalog-and-mcp-operators.md",
    ),
    "MCP_OAUTH_CLIENT_METADATA_URL": (
        "MCP OAuth CIMD URL 覆盖；存在时直接替换内置 metadata URL并记录来源，客户端不会在 getter 中验证其可信性。后续 fetch、schema、TLS 和 authorization server 接受度仍可能失败。",
        "connectors-catalog-and-mcp-operators.md",
    ),
    "MCP_REMOTE_SERVER_CONNECTION_BATCH_SIZE": (
        "MCP 远端 server 并发连接批量大小；解析为正数时采用，否则回落20。它限制调度 fanout，不改变单连接 timeout、auth、retry 或 generation invalidation。",
        "mcp-agents-background.md",
    ),
    "MCP_SERVER_CONNECTION_BATCH_SIZE": (
        "MCP 普通/本地 server 并发连接批量大小；正数生效，否则回落3。调高只增加 dial并发与资源压力，不保证 server initialize成功，也不改变 remote batch。",
        "mcp-agents-background.md",
    ),
    "CLAUDE_CODE_DISABLE_BUNDLED_SKILLS": (
        "bundled skills 的环境硬 disable，与 settings.disableBundledSkills 构成 OR；它只从 discovery/registration移除内置 skills，不删除用户/project/plugin skills或已注入历史内容。",
        "plugins-skills-commands-lsp.md",
    ),
    "CLAUDE_CODE_DISABLE_CLAUDE_API_SKILL": (
        "在 builtin skill装配时显式禁用 Claude API skill；只影响该单一 skill definition，不关闭 Anthropic API client、其他 skills 或 MCP。已执行的 skill副作用不会撤销。",
        "plugins-skills-commands-lsp.md",
    ),
    "CLAUDE_CODE_DISABLE_CLAUDE_CODE_SKILL": (
        "在 builtin skill装配时显式禁用 Claude Code skill；与其他 builtin/plugin skill gate分离。它不禁用当前 CLI 主 Agent Loop，也不移除已写入 transcript 的说明。",
        "plugins-skills-commands-lsp.md",
    ),
    "CLAUDE_CODE_DISABLE_POLICY_SKILLS": (
        "只让 policySettings skill discovery返回空数组；user、synced、project、plugin skill仍按各自 gate加载。它不会修改 managed policy文件，也不撤销当前 turn已注入的 skill内容。",
        "plugins-skills-commands-lsp.md",
    ),
    "CLAUDE_CODE_MCP_ALLOWLIST_ENV": (
        "MCP env passthrough allowlist的 tri-state：truthy开启、false关闭、未设置仅 local-agent默认开启。它控制环境传播范围，不批准 MCP server或工具权限；敏感字段仍受独立 scrub。",
        "connectors-catalog-and-mcp-operators.md",
    ),
    "CLAUDE_CODE_PLUGIN_BINARY_ASSETS": (
        "plugin binary asset处理的显式 enable，与 `tengu_plugin_binary_assets` 构成 OR；开启后仍校验目标平台、cache、下载/解包和插件来源。失败会清理临时 asset cache，不能证明二进制可执行。",
        "plugins-skills-commands-lsp.md",
    ),
    "CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE": (
        "marketplace git pull失败时保留已有 clone，但仅在现有 `.claude-plugin/marketplace.json` 仍存在时；否则继续 backup/reclone恢复。它偏向可用性，可能保留旧 catalog，不把失败标为更新成功。",
        "plugins-skills-commands-lsp.md",
    ),
    "CLAUDE_CODE_PLUGIN_PREFER_HTTPS": (
        "要求 marketplace/source URL选择偏好 HTTPS；remote模式也自动开启。它只影响 transport选择，证书、proxy、credential、host key与repository trust仍独立，不能保证 clone成功。",
        "plugins-skills-commands-lsp.md",
    ),
    "CLAUDE_CODE_PLUGIN_SEED_DIR": (
        "按平台 PATH delimiter解析一个或多个 plugin seed根目录，空项丢弃并规范化绝对路径；未设置为空列表。seed只提供发现候选，不绕过 manifest、trust、copy/install或冲突检查。",
        "plugins-skills-commands-lsp.md",
    ),
    "CLAUDE_CODE_PLUGIN_USE_ZIP_CACHE": (
        "启用 plugin zip-cache路径；后续还要求可解析的 plugin cache dir，否则访问 cache helper会报 `Plugin zip cache is not enabled`。它不验证缓存 freshness/hash，也不代表安装完成。",
        "plugins-skills-commands-lsp.md",
    ),
    "MCP_CONNECT_TIMEOUT_MS": (
        "MCP lazy dial connect budget；正数生效并 cap 到 2147483647ms，否则回落5000ms。abort与timeout生成不同错误，超时只拒绝当前 dial promise，不证明 child/server进程已退出。",
        "mcp-agents-background.md",
    ),
    "CLAUDE_CODE_SYNC_PLUGIN_INSTALL_TIMEOUT_MS": (
        "同步 plugin install等待预算；仅解析结果 >0 时用 Promise.race，超时记录事件并继续 startup，<=0则无限等 install promise。timeout 不取消底层安装，稍后文件/MCP side effect仍可能完成。",
        "plugins-skills-commands-lsp.md",
    ),
    "CLAUDE_CODE_SYNC_PLUGINS_DOWNLOAD_STALL_MS": (
        "plugin catalog/asset同步下载的 stall阈值，typed正整数优先，否则回落内置值；只检测无进展窗口，retry仍由调用方控制。触发 stall不回滚已写临时文件。",
        "plugins-skills-commands-lsp.md",
    ),
    "CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS": (
        "SessionEnd hooks总等待预算；显式 finite正数最高优先，否则扫描各 hook timeout并 clamp 到内置 min/max。到期结束客户端等待，但 async hook或其外部副作用可能继续，退出状态不等于全部 hook成功。",
        "hooks-event-reference.md",
    ),
    "CLAUDE_CODE_USER_DIALOG_TIMEOUT_MS": (
        "用户 dialog等待预算最高优先级；未设置回退 host配置 `60s/5m/10m/never`，再回落300000ms，`never`解析为0。timeout是未及时响应，不等于拒绝，也不撤销此前操作。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_CODE_PARKED_PERMISSION_WAIT_MS": (
        "orphaned/parked permission优先出队前的等待预算，typed非负值优先，缺失回落2000ms并在启动时锁存。它只调整队列时序，不自动批准、拒绝或恢复已过期请求。",
        "tools-permissions-hooks.md",
    ),
    "CLAUDE_BG_BACKEND": (
        "值精确为 `daemon` 时切换 background daemon语义：容忍 dead stdout、SIGHUP/attach probe、同步输出和持久 job owner均走专用分支；其他值不等价。它不证明 daemon socket已认证或 job可恢复。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_CODE_BG_TASKS_REPORT_RUNNING": (
        "让 background task/teammate/pending notification继续把 session视为 running而非 idle，并在全部结束时通知 idle；只改变状态上报/退出等待判断，不延长模型 turn或重启任务。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_BG_SOURCE": (
        "标记 background job来源，缺失 telemetry回落 `shell`，值为 `spare` 还初始化 warm-spare UI state。它用于归因/启动分支，不认证 caller，也不授予额外工具权限。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_BG_POST_CLEAR_RESPAWN": (
        "标记 `/clear` 后 daemon respawn，允许 startup跳过因原 custom agent暂不可见而立即报错的分支；只用于恢复连续性，不伪造 agent definition，后续 registry仍可能找不到该 agent。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_BG_SESSION_PERMISSION_RULES": (
        "仅 background session解析的 JSON permission overlay；必须同时具有 allow/deny数组，否则或非法 JSON静默忽略。它进入 permission context合并，但 deterministic deny/policy floor仍有效，字符串存在不等于授权。",
        "tools-permissions-hooks.md",
    ),
    "CLAUDE_BG_STARTUP_WEDGE_MS": (
        "daemon job卡在 startup-working状态的 watchdog预算，truthy值优先，0/缺失回落45000ms；到期且状态仍匹配时标为 blocked/needs-attention。它不终止 worker或回滚启动副作用。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_BRIDGE_REATTACH_GROUPING": (
        "Remote Control reattach的一次性 grouping ID，只在 CLAUDE_BRIDGE_REATTACH_SESSION carrier存在时成组读取并删除；用于恢复会话归组，不替代 owner/account核验，失败会抑制或重建 history channels。",
        "tui-ide-remote-cloud.md",
    ),
    "CLAUDE_BRIDGE_REATTACH_NO_BACKFILL": (
        "reattach carrier 的 no-history-backfill布尔标记；仅随 session carrier消费，命中会抑制历史 channel/backfill。它不删除本地 transcript，也不阻止新的 outbound events。",
        "tui-ide-remote-cloud.md",
    ),
    "CLAUDE_BRIDGE_REATTACH_OUTBOUND_ONLY": (
        "把 Remote Control reattach解析为 mirror/outbound-only，而非 full bridge；仍要求 session carrier和 bridge eligibility。它限制 inbound控制面，不保证 outbound投递成功，也不改变本地 Agent Loop owner。",
        "tui-ide-remote-cloud.md",
    ),
    "CLAUDE_BRIDGE_REATTACH_SEQ": (
        "reattach history起始 sequence；只在 session carrier存在时 parseInt，0/非法降为未设置，随后整组 env删除。server delta、anchor walkback和owner mismatch仍可改变恢复结果。",
        "tui-ide-remote-cloud.md",
    ),
    "CLAUDE_CODE_REMOTE_SEND_KEEPALIVES": (
        "remote session有 active refcount/activity callback时周期发送 keepalive，并可在显式 activity点立即触发；false时只保留本地 idle timer。keepalive不等于服务端 ack，也不保持模型/API请求无限存活。",
        "tui-ide-remote-cloud.md",
    ),
    "CLAUDE_PTY_ORPHAN_CHECK_MS": (
        "PTY host orphan检查周期，正整数 parser失败或0回落2000ms；连续30次发现 parent变化且无client后 SIGTERM child，再按独立延迟SIGKILL。已完成shell/外部副作用不可回滚。",
        "runtime-supervision-and-processes.md",
    ),
    "CLAUDE_CODE_ACCESSIBILITY": (
        "开启 TUI accessibility mode，强制 native cursor/可见cursor并抑制部分控制序列；screen-reader detection仍有独立 flag/env/runtime gate。它改变渲染，不改变模型、工具或 transcript。",
        "tui-input-accessibility-media-ide-chrome.md",
    ),
    "CLAUDE_CODE_ALT_SCREEN_FULL_REPAINT": (
        "让 alternate-screen renderer采用 full repaint/额外高度补偿；Windows background worker还据此强制显示cursor，Windows启动可自动写1。它只修正渲染兼容性，可能增加输出量，不开启 alt screen本身。",
        "tui-input-accessibility-media-ide-chrome.md",
    ),
    "CLAUDE_CODE_AUTO_CONNECT_IDE": (
        "IDE auto-connect tri-state：显式 false最高优先关闭，true加入 settings、检测到IDE、SSE port等 OR条件。连接仍需 lock/token/version/workspace校验，开启不等于 extension存在或握手成功。",
        "tui-ide-remote-cloud.md",
    ),
    "CLAUDE_CODE_DISABLE_MOUSE": (
        "mouse mode tri-state最高优先：true=`off`，false=`full`；未设置才检查 DISABLE_MOUSE_CLICKS。它只控制 terminal mouse event注册，不改变键盘、工具或 scroll content。",
        "tui-input-accessibility-media-ide-chrome.md",
    ),
    "CLAUDE_CODE_DISABLE_MOUSE_CLICKS": (
        "在 DISABLE_MOUSE未显式设置时选择 true=`scroll`、false=`full`，即保留滚轮但禁用点击；默认full。terminal兼容性仍可能让事件不可达。",
        "tui-input-accessibility-media-ide-chrome.md",
    ),
    "CLAUDE_CODE_DISABLE_VIRTUAL_SCROLL": (
        "关闭 transcript/TUI virtual-scroll windowing，组件在 mount时锁存；内容改为更直接渲染，可能增加内存/重绘成本。它不删除历史、不改变 transcript persistence或实际消息数量。",
        "tui-input-accessibility-media-ide-chrome.md",
    ),
    "CLAUDE_CODE_IDE_HOST_OVERRIDE": (
        "覆盖 IDE connection host探测结果，优先于默认 terminal/extension host推导；只提供候选 host，lockfile、port、auth token与version handshake仍会验证，错误值导致连接失败而非降权成功。",
        "tui-ide-remote-cloud.md",
    ),
    "CLAUDE_CODE_SCROLL_SPEED": (
        "TUI wheel基础速度覆盖；parseFloat为正才生效并 cap到20，否则回落 terminal检测所得1或3。它不改变 adaptive drain/decay gate，也不影响非mouse输入。",
        "tui-input-accessibility-media-ide-chrome.md",
    ),
    "CLAUDE_AX_SCREEN_READER": (
        "screen-reader tri-state precedence为 CLI `--ax-screen-reader` > env > setting，并在首次求值缓存；最终仍经 runtime支持探针。开启改变可访问渲染/播报，不修改会话内容或模型请求。",
        "tui-input-accessibility-media-ide-chrome.md",
    ),
    "CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN": (
        "alternate-screen硬关闭输入，与 CLAUDE_CODE_NO_FLICKER=false构成 OR；background session/screen-reader/tmux/Windows兼容 gate仍分别参与。它只选择 default renderer，不停止 Agent Loop。",
        "tui-input-accessibility-media-ide-chrome.md",
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
    "tengu_sepia_moth": (
        "consumer `c5r` 只在 auto compact 已启用、remote/reactive compact gate 可达、该 flag 为 true，且 `precomputeCompactionEnabled` 设置为 true 时开启预计算摘要。它只把 pending/ready/failed 写入 session precompute registry，达到 compact line 且 boundary UUID 仍存在时才 swap；连续 3 次可计数失败会停止 re-arm，普通 reactive/manual compact 仍是 fallback。",
        "context-governance-and-caching.md",
    ),
    "tengu_amber_packet": (
        "consumer `eyi` 是预计算摘要 sidecar 的持久化/rehydrate gate，且 session persistence 必须未被显式关闭。通过后 main-agent ready 结果可写 `precompact.json`/Storage v5 sidecar；复用还校验 session、model、7 天时效、150000-token 增长、boundary/preserve UUID，失败会删 sidecar 并回退普通总结，不把陈旧 summary 注入历史。",
        "context-governance-and-caching.md",
    ),
    "tengu_amber_redwood2": (
        "与 `tengu_amber_redwood3` 以短路 OR 组成字符串配置，consumer `MPa` 仅在 auto compact 开启、非 bare mode、模型严格等于 `claude-opus-4-8` 时解析 `auto`、K/M 或数值窗口，并限制到 32000-1000000 token；空值/非法值不覆盖正常窗口计算。客户端选择窗口不证明服务端模型接受该上下文长度。",
        "context-governance-and-caching.md",
    ),
    "tengu_amber_redwood3": (
        "作为 `tengu_amber_redwood2` 的第二优先级字符串输入，只在前者为空时生效；后续仍经过 Opus 4.8、auto-compact、bare-mode 和 32000-1000000 范围校验。它改变客户端 compact window 候选，不改变 provider 的实际 context limit；非法值静默回到既有窗口路径。",
        "context-governance-and-caching.md",
    ),
    "tengu_amber_wren": (
        "consumer `pmt` 把 object 字段逐项解析为默认文件读取限制：`maxSizeBytes`/`maxTokens` 只接受 finite positive number，`includeMaxSizeInPrompt`/`targetedRangeNudge` 只接受 boolean；环境 `CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS` 对 maxTokens 优先，结果缓存进 runtime state。非法字段回落 25k-token 等内置值；限制只约束 Read/附件装配，不证明文件内容已进入模型。",
        "builtin-tools-reference.md",
    ),
    "tengu_read_dedup_killswitch": (
        "consumer `Mhv` 为 true 时把 prior read state 置空，关闭 Read 的 unchanged 去重；false 时只有同一路径、相同完整/offset+limit 视图且 mtime 未变，或未变的 seeded full view，才返回 `file_unchanged`。stat/mtime 检查异常会继续真实读取；该 flag 不跳过路径权限、大小/token 限制或动态 skill trigger。",
        "builtin-tools-reference.md",
    ),
    "tengu_mcp_listen_reopen_park_tuning": (
        "consumer 用 schema 解析 object，仅消费 `windowMax` 与 `parkDelayMinutes`；非法 object/字段回落内置 reopen-window 与 park delay，分钟先乘 60000 并 round。该配置只调节反复断开的 `subscriptions/listen` 恢复预算，不建立连接，也不绕过 transport/auth/policy。",
        "mcp-agents-background.md",
    ),
    "tengu_mcp_listen_reopen_park": (
        "控制反复被 server 关闭的 `subscriptions/listen` 是否进入 park。consumer 先按 server key 统计 trailing-window reopen，达到 `windowMax` 且仍有 backoff 项才 sleep `parkDelayMinutes`；等待中会再次读 flag，关闭后立即退出 park。重开仍受有限 delay budget、abort 和真实 server 健康约束，耗尽时记录 gave_up/budget_exhausted。",
        "mcp-agents-background.md",
    ),
    "tengu_mcp_local_oauth_blocked_hosts": (
        "consumer 只接受 `{hosts: string[]}` 且至少一个字符串，否则使用内置 Anthropic-hosted connector host 列表；hostname 会 lowercase 并去尾点。命中后 local/project/user SSE/HTTP 配置被分类为 `anthropic-hosted`，提示改走 claude.ai Connectors，而不是启动 local OAuth；URL 解析失败不命中，真实 cloud entitlement/OAuth 仍是 Boundary。",
        "connectors-catalog-and-mcp-operators.md",
    ),
    "tengu_mcp_singleton_unwrap": (
        "consumer 在 MCP 大结果持久化前检查 content block shape；仅当结果恰为一个无 `annotations`、无 `_meta` 的 text block 时才 unwrap 为纯文本并按 text 保存，string 原值也保持 text。多 block、带元数据或非文本仍 JSON 序列化；persist 失败则返回截断错误，因此该 flag 不保证大结果可恢复。",
        "mcp-agents-background.md",
    ),
    "tengu_mcp_proxy_needs_approval_retry": (
        "consumer 只处理 MCP error `-32003` 且 data 含 `args_sha256`、存在 CCR approval context/toolUseId、尚未重试的调用；它弹出 suppress-always-allow 的 retroactive approval card，原参数获准后仅重试一次。编辑参数、拒绝、无 prompt surface、abort 或重试失败都终止并保留明确错误；已在 server 发生的前置副作用无法由 retry 撤销。",
        "connectors-catalog-and-mcp-operators.md",
    ),
    "tengu_ccr_v2_send_events_cli": (
        "选择 Remote Control event/control-request 的 v2 route/body builder，consumer 覆盖 interrupt、首条 user event、runner client 与 event uploader；OAuth、org/trusted-device headers、session-id 校验和 HTTP 结果仍独立检查。false 走 legacy event path，true 只表示客户端改用 v2 wire shape，不证明服务端接收、持久化或处理了事件。",
        "tui-ide-remote-cloud.md",
    ),
    "tengu_ccr_v2_session_crud_cli": (
        "选择 Remote Control session CRUD 的 `/v1/code/sessions` v2 路由及 cursor/headers shape，覆盖 create/get/update/list/archive/unarchive；legacy 路径仍用 `/v1/sessions`、beta 与 org header。401/403/404/409、trusted-device elevation、malformed body 和网络失败各自保留，route 选择不等于 mutation 成功。",
        "tui-ide-remote-cloud.md",
    ),
    "tengu_ccr_delta_rehydrate": (
        "控制 remote worker resume 是否先用本地 transcript 派生的 last event ID 做 delta hydration；还要求 remote resume argv、可定位 transcript 和 CCR init 成功。consumer 并行读取 main/subagent internal events，再按恢复边界合并；解析或 fetch 失败降级为无 prefetch，不能据此声称服务端事件完整。",
        "sessions-checkpoints-memory.md",
    ),
    "tengu_ccr_subagent_skip_on_delta": (
        "仅在 `tengu_ccr_delta_rehydrate` 同时为 true 时，consumer 跳过独立 subagent internal-event 全量读取，依赖 delta hydration 已覆盖所需状态；任一 gate 为 false 都继续读取 subagent stream。它减少恢复 I/O，但若服务端 delta 缺失，客户端没有静态证据证明子 Agent 状态可完整恢复。",
        "sessions-checkpoints-memory.md",
    ),
    "tengu_ccr_idle_heartbeat": (
        "使 CCR heartbeat request 声明 `supports_heartbeat_probe` 并携带 current interval/idle seconds；只有 server 返回更长有效 interval 才 latch idle grant，失败或非 429 会撤销 grant并回到 seed interval。token expiry 仍会 clamp interval，flag 不保证 server 授权降频或连接存活。",
        "resilience-and-recovery.md",
    ),
    "tengu_ccr_reconnect_beat": (
        "允许 transport reconnect 后在上次成功 heartbeat 已超过放大后的当前 interval、且未处于 429 冷却时立即发 `resync_stale` beat；已有 idle grant 则总走普通 resync。in-flight/spacing 会排队合并，失败恢复 heartbeat 状态但不能重放丢失事件。",
        "resilience-and-recovery.md",
    ),
    "tengu_ccr_reactivation_beat": (
        "只有 idle-heartbeat 协商已授予较长 interval、idle tracker 存在且观察到足够 idle 时才 arm；本地重新活跃会发送一次 `reactivate` beat。429 会恢复 arm，其他失败会撤销 idle grant并缩回 seed interval；它加速重新报活，不证明 remote viewer 已重连。",
        "resilience-and-recovery.md",
    ),
    "tengu_cobalt_plinth": (
        "consumer `zip` 是 Artifact 主 rollout gate，还叠加环境禁用/设置、first-party/account capability、host 和工具装配。true 只允许 Artifact surface 进入候选注册，publish 仍要经过文件读取、slug/ownership、contract、并发 baseVersion、上传和 complete 回执；任何远端副作用均不会被 flag 回滚。",
        "workflow-artifact-design.md",
    ),
    "tengu_cobalt_plinth_sorrel": (
        "consumer `Shi` 只有 Artifact/Frame 可用、未设置 custom base URL、flag 为 true 且 relay capability 成立时，才让已知 API family 尝试 CCR frame relay；未知 route、declined cooldown 或 probe 失败走 direct。它改变 HTTP 路由选择，不证明 relay/server 已采用请求。",
        "workflow-artifact-design.md",
    ),
    "tengu_cobalt_plinth_fern": (
        "consumer `Fzn` 控制普通 redeploy 是否携带 tracked `baseVersion` 做 optimistic concurrency；composed PR review/auto-edit attribution 仍强制保留 baseVersion。关闭后普通更新更少携带版本前置条件，但 server ownership、slug 和 conflict 结果仍是权威，不能把客户端缺字段解释为覆盖成功。",
        "workflow-artifact-design.md",
    ),
    "tengu_cobalt_plinth_moss": (
        "consumer 在 Artifact update stale-guard 中决定是否自动读取 remote current version/metadata再比较本地 tracked base；关闭时该自动 guard 返回 gate_off。即使开启，read 失败、ownership/slug 不匹配或后续 409 都会阻止/要求重试，预读不能构成事务锁。",
        "workflow-artifact-design.md",
    ),
    "tengu_cobalt_plinth_laurel": (
        "consumer 为 Artifact publish tool schema 增加可选 `lang`，且只接受 BCP-47-like 校验通过的值，再进入页面 `<html lang>`/metadata 处理。关闭时字段根本不在 schema；开启不自动识别语言，也不证明 gallery/search 已消费该 metadata。",
        "workflow-artifact-design.md",
    ),
    "tengu_cobalt_plinth_osier": (
        "这是 shared-scope list kill switch：consumer 在 scope 非 `mine` 时直接返回 `scope_disabled`，而不是请求 shared/all 列表。false 只允许继续发 list，OAuth、server capability、分页与共享可见性仍可能失败；它不影响 owner 自己的 mine 列表。",
        "workflow-artifact-design.md",
    ),
    "tengu_cobalt_plinth_bracken": (
        "consumer 同时控制 Artifact tool schema 是否暴露 `files/root`，以及 publish 时是否接受 supporting files；关闭会在任何上传前返回 `multifile_flag_off`。开启后仍限制最多 64 个映射、路径位于工作目录、content type/总预算和单文件 review 约束，部分远端上传不具原子回滚。",
        "workflow-artifact-design.md",
    ),
    "tengu_cobalt_plinth_sedge": (
        "consumer 只放行无 member asset token 的 public-reader Artifact read；关闭时返回 `public_read_disabled`。拥有 asset token/owner 路径不由它阻断，开启后 HTTP、contract、大小和服务端访问控制仍独立决定能否读到内容。",
        "workflow-artifact-design.md",
    ),
    "tengu_cobalt_plinth_reader_persist": (
        "consumer 只作用于非 owner/public Artifact read：开启后把原始 HTML 交给 `persistBinaryContent` 写成本地 `text/html`，同时生成隔离摘要，结果明确报告保存路径或保存失败；关闭时只返回摘要。它不改变 reader authorization，写盘失败也不会把远端 read 改判失败；服务端 grant 寿命仍是 Boundary。",
        "workflow-artifact-design.md",
    ),
    "tengu_cobalt_plinth_putguard": (
        "consumer 在对象存储 PUT 返回 2xx 后强制检查 `x-goog-generation`，缺失时把响应判为 intercepted 403，避免代理伪造上传成功。关闭只移除这项回执 guard，不移除 signed URL、status、complete-call 或 version 检查；generation 存在也不证明 viewer 已渲染。",
        "workflow-artifact-design.md",
    ),
    "tengu_frame_publish_context": (
        "consumer 决定是否把本地 `publishContext` 映射为 create/update metadata 的 `publish_context`，并在 `/api/frame/deploy/complete` 回执中重复携带；字段缺失或 gate off 不影响页面字节上传。开启只证明客户端发送该上下文，服务端保存、索引和下一会话采用仍是 Boundary。",
        "workflow-artifact-design.md",
    ),
    "tengu_cobalt_plinth_direct": (
        "consumer 在 new create、特定 entrypoint、显式环境 override 或该 flag 为 true 时选择 direct upload lane，否则可走既有 staged/relay lane。两条 lane 都要完成 upload 与 deploy/complete，错误可能落在已上传但结果未知的 post-side-effect Boundary；切 lane 不提供自动回滚。",
        "workflow-artifact-design.md",
    ),
    "tengu_cobalt_plinth_dataviz": (
        "consumer 只在生成 Artifact/页面设计指导时追加“图表与 diagram 加载指定 skill”的系统提示段。它改变 prompt/schema residency 与 token 成本，不注册图表执行器，也不证明模型调用了 skill 或产出正确可视化。",
        "workflow-artifact-design.md",
    ),
    "tengu_keybinding_customization_release": (
        "consumer 控制 `/keybindings` 命令、提示和 `keybindings.json` watcher/load path；还受环境级 `keybindings` disable gate。开启后只接受 `{bindings:[{context,bindings}]}` 合法结构并把用户 bindings 叠在默认 bindings 后，解析/validation/read 失败保留默认键位和 warnings，不会让坏配置中断 TUI。",
        "tui-input-accessibility-media-ide-chrome.md",
    ),
    "tengu_session_name_uniqueness": (
        "consumer 在 startup/recheck/rename 时查询已注册 live sessions，按 pid/start time 选出应让位者，为冲突名称追加随机 slug/递增后缀并写回 collision-source name。registry 未注册、当前 pid 缺失或检查异常都会保留原名；该机制只降低本机 live-name 冲突，不提供跨主机全局唯一性。",
        "sessions-checkpoints-memory.md",
    ),
    "tengu_send_file": (
        "consumer `h9r` 还要求 cross-session inbox 可用，才注册非并发安全、可写副作用的 SendFile。调用逐文件执行 Read permission、realpath、16 文件/单文件 30MiB 等校验，再按 UDS/bridge route 投递；目标 elevation 隔离、abort、部分文件失败和 ack 不确定均保留逐项结果，成功发送不能被 conversation rewind 撤销。",
        "cloud-background-channels.md",
    ),
    "tengu_send_user_file": (
        "consumer 还要求 first-party provider、非 essential-traffic privacy、`allow_send_file` policy、desktop/remote host lane 且非禁用宿主，才注册 SendUserFile。调用解析路径并按 render/attach lane 上传，返回每个 attachment 的 `file_uuid` 或 `upload_error`；本地可见但 Remote Control 未送达会明确标记，HTTP 成功不证明远端 viewer 已渲染。",
        "brief-mode-and-user-visible-output.md",
    ),
    "tengu_record_created_pr_to_ccr": (
        "consumer 仅在检测到结构化 PR、flag 开启且 URL 通过允许的 PR URL 校验时，异步调用 `recordCreatedPrToCcr(pr,cwd)` 更新 Remote Control 关联状态；调用从主命令路径 fire-and-observe，不阻塞本地 PR 成功。网络/HTTP/shape 失败只记录 telemetry，远端是否已关联必须重新读取权威 session/PR 状态。",
        "tui-ide-remote-cloud.md",
    ),
    "tengu_ultrareview_post_enabled": (
        "consumer 同时控制 `/ultrareview --post` 的可选 post handoff 与最终 posting routine；还要求 cloud review entitlement、GitHub.com PR scope、用户 consent、合法 findings 和 posting routine 可用。关闭时 findings 仍返回但明确 `not-posted`；开启后 90s routine 等待、最多 61440 bytes、404 rebuild/retry 与 timeout-unknown 都保留，远端评论一旦创建不可由本地回滚。",
        "ultrareview-cloud-review.md",
    ),
    "tengu_import": (
        "consumer 控制 `claude import` fast-path 改写到 `/import` 以及 slash command 可见性；仅接受 codex/gemini、`--dry-run`、`--yes=<32hex digest>` 等 argv shape。apply 前重新扫描并校验 preview digest，漂移即拒绝；写入按项目逐步发生而非事务，dry-run 不写，部分导入失败需按报告恢复。",
        "project-purge-import-and-data-lifecycle.md",
    ),
    "tengu_remote_auto_mode_include_destructive_mcp": (
        "consumer 只在 remote session、Auto Mode 正在评估且 MCP tool 的 `isDestructive(input)` 返回 true 时，把该 destructive MCP 纳入 remote auto-mode 分支；deterministic deny/ask policy、managed rules、hook 和 classifier verdict 仍优先。true 不等于自动批准，更不证明远端 MCP 副作用可撤销。",
        "auto-mode-classifier.md",
    ),
    "tengu_mcp_auto_background": (
        "boolean fallback true；consumer 先排除不支持后台化的 transport、已处于子 Agent、未显式允许后台任务的 non-interactive session，再让 `CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS` 覆盖并 clamp timeout。超时且没有 pending elicitation 时把仍运行的 MCP call 转成 task-registry job，完成/失败异步注入 notification；parent abort、tool error、结果渲染失败分别收口，后台化不撤销 server 已执行动作。",
        "mcp-agents-background.md",
    ),
    "tengu_mcp_claudeai_eligibility_gate": (
        "boolean fallback false；只对 `claudeai-proxy` config 且 server 明确返回 `eligible:false` 的条目生效，consumer 将其排除而不是继续连接。其他 transport、eligible 缺失/true 不受它影响；开启只执行客户端 eligibility gate，账号为何不 eligible 和服务端判定规则仍是 Boundary。",
        "connectors-catalog-and-mcp-operators.md",
    ),
    "tengu_mcp_directory_bff": (
        "boolean fallback false；consumer 在非 essential-traffic privacy、目录未禁用时选择 `/api/directory/servers` BFF，否则走 `/mcp-registry/v0/servers` legacy，并用相同 visibility 集合分页、规范化 URL 后写 session `officialUrls`。HTTP/解析异常只记录 fetch_failed 并保留未加载状态，不把目录失败当成 server trust 证明。",
        "connectors-catalog-and-mcp-operators.md",
    ),
    "tengu_mcp_directory_visibility": (
        "array fallback 为 `commercial/gsuite/enterprise/health`；consumer 只接受全为 string 的数组并过滤空串，非法 shape 整体回落。空数组会把 `officialUrls` 明确设为空且不发网络请求；非空数组进入 BFF/legacy query，但远端目录内容、分页完整性和 URL 官方身份仍由响应与后续校验决定。",
        "connectors-catalog-and-mcp-operators.md",
    ),
    "tengu_mcp_issuer_strict_echo": (
        "boolean fallback false；OAuth metadata consumer 比较 expected/received issuer，关闭时仅 observe 并记录 scheme/host/path 等 mismatch facets，开启时除相同 origin 外抛出 issuer mismatch，阻断 token flow。缺 issuer、不可解析和跨 origin 都 fail-closed；同 origin 的路径差异仍可继续，最终授权服务器行为属于外部 Boundary。",
        "connectors-catalog-and-mcp-operators.md",
    ),
    "tengu_mcp_server_policy_bypass_exempt": (
        "boolean fallback true；只在 remote session、ask rule 来源为 `mcpServerPolicy`、该工具 effective mode 为 `bypassPermissions` 时，consumer 允许跳过这条 ask；显式 deny、input schema、hook、tool `effectiveMaxPermission=ask` 和其他 policy floor 仍执行。它不是通用 MCP 绕过开关，server 副作用也不因本地 mode 可撤销。",
        "tools-permissions-hooks.md",
    ),
    "tengu_mcp_startup_policy_seed": (
        "boolean fallback true；仅在 `CLAUDE_CODE_REMOTE` startup，consumer 把远端启动 policy seed 合并进初始 MCP config，再进入正常 allow/deny、trust、connect 和 generation refresh。关闭只不做这次 seed；它不会移除 managed deny，也不证明 seeded server 已连接或工具已进入请求。",
        "mcp-agents-background.md",
    ),
    "tengu_mcp_strip_trailing_xml_tags": (
        "boolean fallback false；consumer 只检查 object 参数中的 string 尾部，候选必须以 `</invoke>` 结束，可同时去掉匹配的 `</param>`，且原值不得包含对应 opening tag；满足 shape 才复制 input 并剥离。关闭仅记录 wouldStrip telemetry，非字符串/中间 XML/有 opening tag 均原样保留；修复不能证明模型原始意图。",
        "tools-permissions-hooks.md",
    ),
    "tengu_mcp_subagent_prompt": (
        "boolean fallback false；consumer 先尊重显式环境/宿主选择，只有未指定时才决定 subagent 是否接收 MCP instructions/prompts。它改变 child system context 与 token 成本，不改变 MCP client generation、schema residency、permission 或连接状态；prompt 缺失时仍正常运行子 Agent。",
        "mcp-agents-background.md",
    ),
    "tengu_cowork_auto_mode_include_allowed_write_mcp": (
        "boolean fallback false；consumer 只认来源为 `mcpServerPolicy` 的 allow、mode 为 auto 或允许的 plan、且 `isDestructive(input)` 为 true 的 MCP tool，把它送入 Auto Mode 许可分类。显式 deny/ask、schema parse、hook、effective max permission 和 classifier fail-closed 仍优先；纳入候选不等于自动允许写操作。",
        "auto-mode-classifier.md",
    ),
    "tengu_harbor_permissions": (
        "boolean fallback false；consumer 还要求非 remote host并已创建 channel permission callback，才把 callback 写进 app state，承接 MCP channel permission request/allow/deny 回执；effect cleanup 会移除同一 callback。flag off 不影响普通 MCP permission，回调丢失或 channel/server 断连只使该请求无法结算，不回滚此前 channel 动作。",
        "cloud-background-channels.md",
    ),
    "tengu_surface_failed_mcp_servers": (
        "boolean fallback false；consumer 在 Tool Search/deferred-tools attachment 中附加 failed/disabled MCP server 摘要，让模型知道哪些工具缺席；仅影响提示上下文，不重新连接 server。关闭时失败仍留在本地 MCP state/UI；开启也不证明错误可恢复，并增加少量 prompt token。",
        "mcp-agents-background.md",
    ),
    "tengu_official_plugin_prompt_overrides": (
        "object fallback `{}`；consumer 只对官方 marketplace/plugin source 查同名 entry，先验证顶层和单插件 schema，再把 server instructions、tools、search hints、param descriptions、prompts、skills 复制到 null-prototype maps。非官方、缺项、空 object 或 schema 错误都保留 baked-in text；远端 payload 不能改变 plugin trust、permission 或执行代码。",
        "plugins-skills-commands-lsp.md",
    ),
    "tengu_plugin_autoupdate_allow_credential_helper": (
        "boolean fallback false；只在 plugin auto-update 已启用、随机延迟结束并得到待刷新 marketplace 集合后，consumer 决定 Git refresh 是否允许 credential helper；false 传 `disableCredentialHelper:true`。网络、pin、dependency 和单 marketplace 失败形成 partial 结果，已更新插件不会因后续失败自动回滚；开启可能调用本机凭据助手但不保证认证成功。",
        "plugins-skills-commands-lsp.md",
    ),
    "tengu_plugin_command_source_refresh": (
        "boolean fallback true；consumer 还要求非 essential-traffic 模式、managed policy 未禁用，并拒绝 cache/workspace 与受保护目录重叠，才允许后台重新执行 command-sourced plugin producer。命令输出仍要通过 cwd/ancestor、大小、路径和 copy/link 校验；失败保留旧 cache/报错，不把命令执行成功等同于 plugin 可加载。",
        "plugins-skills-commands-lsp.md",
    ),
    "tengu_propose_skills": (
        "boolean fallback false；consumer 还要求 skill-proposal capability或显式环境 override、remote environment type 存在、非 environment worker，并满足 sync-skills/禁用状态，才注册只读并发工具。输入限制 1-3 个 proposal，improvement 必须有 target；调用只显示 review card并返回数量，不直接写 SKILL.md，用户保存结果属于后续 UI Boundary。",
        "plugins-skills-commands-lsp.md",
    ),
    "tengu_repl_mcp_error_throw": (
        "boolean fallback true；仅对 REPL 内 `isMcp` tool wrapper 生效：pre-execution denial或执行失败会抛 `McpToolError`，JSON-looking detail 单独保留；关闭则返回普通错误文本。未 await 的 `o.*` 调用仍在 settle 时包装错误，permission denial 不应重试；此前 REPL 内其他文件/命令副作用不会因 throw 回滚。",
        "repl-programmatic-tool-runtime.md",
    ),
    "tengu_bg_attach_stall_ms": (
        "number fallback 为内置 `bSw`；consumer 将 0 解释为关闭，否则取 flag 与 launcher 场景最小值（有 wrapper 时更高、普通至少 2000ms）的较大者，作为 attach 无首帧检测期限。超时只在 worker 仍 running、socket 未毁、未 shutdown 时 SIGTERM 并以 transcript/session flags respawn；恢复有次数预算，不能恢复已完成外部副作用。",
        "runtime-supervision-and-processes.md",
    ),
    "tengu_bg_attach_upgrade": (
        "boolean fallback true；consumer 仅在非低内存时扫描 version-stale、非 exec、非 pinned worker，按 per-sweep 和 burst 预算做 idle respawn/prewarm；downgrade、booting、host sleep、low memory 或 shutdown 会跳过/停止。它升级后续 attach 的 worker binary，不原地改写正在执行的进程。",
        "runtime-supervision-and-processes.md",
    ),
    "tengu_bg_binary_takeover": (
        "boolean fallback true；consumer 还要求无 launcher 配置错误、当前 binary 更新或旧 daemon 缺 process wrapper、launcher 可运行、daemon lock 带 procStart identity且没有安装提示阻塞，才终止 stale transient daemon，必要时 SIGKILL。身份/锁/版本任一不确定即拒绝 takeover；worker 后续由新 daemon adopt/respawn，旧外部动作不回滚。",
        "runtime-supervision-and-processes.md",
    ),
    "tengu_bg_classifier_config": (
        "object fallback `{useSmallFastModel:true, disableThinking:true, midTurnLlmDebounceMs:60000}`；consumer 分别选择小模型、关闭 thinking，并用 debounce 控制 mid-turn LLM 分类。字段缺失各自回落，非法 interval 不直接授权动作；分类只更新 background intent/progress state，API failure 走既有 degraded classification，不替代工具 permission。",
        "runtime-supervision-and-processes.md",
    ),
    "tengu_bg_leftarrow_inprocess": (
        "boolean fallback true；用户用 left-arrow 把当前 session 后台化后，consumer 优先在本进程打开 Agent View；该路径失败会记录异常并回退启动 `claude agents` 子进程。它仍要求 session persistence、dispatch/materialized transcript 和 background spawn 成功，视图切换不代表 worker 已完成。",
        "runtime-supervision-and-processes.md",
    ),
    "tengu_bg_prewarm_burst_concurrency": (
        "number fallback 3；post-takeover burst consumer 用它限制同时 booting 的 stale workers，值 <=0 关闭 burst。实际候选还排除 exec、pinned、unverified、低内存和已 booting；host sleep/时间预算会提前停止，未处理项留给后续 sweep。",
        "runtime-supervision-and-processes.md",
    ),
    "tengu_bg_prewarm_burst_delay_ms": (
        "number fallback 15000ms；daemon takeover/adopt 后先 unref sleep，再检查 upgrade gate、shutdown、low-memory 与 stale candidates。延迟只改变预热启动时机，不延长 worker task deadline；进程在 timer 前退出则没有 burst，后续普通 attach 仍可冷启动。",
        "runtime-supervision-and-processes.md",
    ),
    "tengu_bg_prewarm_per_sweep": (
        "number fallback 3；每个 supervisor sweep 最多成功 respawn 该数量的 stale idle worker，并另有 12 次检查预算；值 <=0 跳过。booting 会消耗本轮名额，拒绝/错误消耗检查预算，pinned、exec、downgrade 和低内存候选不动，下一 sweep 可重试。",
        "runtime-supervision-and-processes.md",
    ),
    "tengu_bg_revival_guard": (
        "boolean fallback true；worker respawn 时写 `CLAUDE_CODE_RESUME_INTERRUPTED_TURN=1` 并读取 durable job state，consumer 用 revival guard 防止同一 interrupted turn/terminal outcome 被重复复活。状态读取失败降级为无 guard 信息，respawn budget和 session conflict 仍会阻断；它不能判定外部命令是否已完成。",
        "runtime-supervision-and-processes.md",
    ),
    "tengu_bg_spare_enable": (
        "boolean fallback true；daemon 只有在版本完全匹配、非 exec dispatch、未低内存且存在可 claim spare 时才把预热进程改绑到真实 job；claim 异常会 dispose spare 并正常 spawn。关闭时也会清理/不创建 spare，不影响普通 worker 路径；claim 成功只减少冷启动，不复制已执行任务。",
        "runtime-supervision-and-processes.md",
    ),
    "tengu_daemon_refuse_stale_upgrade": (
        "boolean fallback true；daemon 检测 binary target 变化时，若新 target 被版本比较判定为更旧则拒绝 self-restart并继续运行当前 build，持续轮询。关闭允许按普通 binary-change 流程重启；lock race、launcher 不可运行和 identity probe仍可推迟，重启不会撤销 worker 已完成副作用。",
        "runtime-supervision-and-processes.md",
    ),
    "tengu_byte_stream_idle_timeout_ms": (
        "number fallback 为 provider 默认；只有 `CLAUDE_BYTE_STREAM_IDLE_TIMEOUT_MS` 未给正值且 legacy stream timeout 未显式设置时才读 flag，随后 clamp 到内置最小/最大。consumer 重置每块 byte 到达时间，超时 abort 当前 stream并进入既有 request retry/fallback；partial assistant/tool state仍须丢弃或 tombstone，已完成工具副作用不回滚。",
        "resilience-and-recovery.md",
    ),
    "tengu_immediate_model_command": (
        "boolean fallback false；还要求 interactive slash-command host支持，才让带参数的 `/model`、`/config`、Advisor等命令在输入路由中 immediate 执行，而不是等待普通 turn 提交。无参数仍走对应 JSX/控制面，非法参数返回命令错误；切换只更新后续 request model/state，不改变已发出的 API attempt。",
        "tui-input-accessibility-media-ide-chrome.md",
    ),
    "tengu_media_byte_cap": (
        "number fallback 按宿主选择 `Inp/xnp`；request assembler 统计 message与 tool_result 内 base64 image/document bytes，超限时从较旧 media 开始删除并在空内容处放 `[media removed: request limit]`。计数 cap、当前-turn保留量和 provider gate仍独立；剥离只缩小请求，不删除 transcript/本地文件，服务端实际 token计费仍是 Boundary。",
        "context-governance-and-caching.md",
    ),
    "tengu_rc_permission_nudge": (
        "object fallback `fos`，环境 JSON 可优先；consumer 对 `afterPromptCount` 至少取 1，对 probability/maxImpressions 只接受 finite number，再要求 Remote Control 可用、用户未使用过且本地 impression 未达上限。展示会持久增加 seen count；非法 JSON/字段回落，nudge 只提示功能，不改变当前 permission 决策。",
        "tui-ide-remote-cloud.md",
    ),
    "tengu_rc_long_turn_nudge": (
        "null/object fallback 为关闭；true 展开为 90s、概率1、最多3次、7-21点，object 字段分别 clamp threshold 5-3600s、probability 0-1、小时0-24。还要求 Remote Control 可用、时间窗/随机/印象键通过；展示写计数但不启动 Remote Control，非法 shape不显示。",
        "tui-ide-remote-cloud.md",
    ),
    "tengu_terminal_sidebar": (
        "boolean fallback false；开启后 `/config` 才暴露 `showStatusInTerminalTab`，用户值写 local/global config；runtime 还要求该设置 true，才把 post-turn status detail投射到 terminal tab/sidebar。flag off保留已存值但不消费；OSC/宿主支持失败只使状态不可见，不影响 Agent Loop。",
        "tui-input-accessibility-media-ide-chrome.md",
    ),
    "tengu_xterm_atlas_reset": (
        "boolean fallback true；consumer 初始化 glyph atlas recorder 的 auto-reset与 recording，配套诊断 flag可强制持续 recording。关闭且诊断未开会停止采样；开启允许 atlas saturation时重置/记录 cardinality，debug-tainted recorder跳过。它只修复/观测 TUI渲染缓存，不改变会话内容。",
        "tui-input-accessibility-media-ide-chrome.md",
    ),
    "tengu_destructive_command_warning": (
        "boolean fallback false；Bash/PowerShell render consumer 仅在命令尚未执行且静态 destructive classifier命中时生成醒目 warning，另一路在已允许/非危险时返回 null。permission deny/ask、sandbox和实际执行仍独立；提示不是阻断规则，分类漏报不能证明命令安全，执行后的副作用不可撤销。",
        "tools-permissions-hooks.md",
    ),
    "tengu_tool_memory_cgroup": (
        "boolean fallback false；只在 Linux/WSL、未用 `CLAUDE_CODE_TOOL_MEMORY_LIMIT=none/禁用值` 且能解析 `/proc/self/cgroup` 时创建 `claude-code-bash` cgroup并写 memory limit；显式正数可在 flag off时启用。目录/写入/层级失败会缓存 disabled并继续无 cgroup执行，不应把 CLI成功当成内存隔离成功。",
        "sandbox-install-and-runtime-enforcement.md",
    ),
    "tengu_tab_read_sep": (
        "boolean fallback false并缓存到 runtime state；consumer 只改变 Read/diff内容的 tab-aware分隔与行投影，避免 tab列与视觉列混淆。文件权限、offset/limit、token cap和原始字节读取不变；关闭回到旧 separator，任何显示投影都不应替代原文件作写入依据。",
        "builtin-tools-reference.md",
    ),
    "tengu_deferred_stub_tool": (
        "boolean fallback true；当 Tool Search非 standard、运行时未显式决定且宿主允许时，consumer加入一个 `defer_loading:true` 空 schema stub，作为 deferred tool引用入口。关闭或异常返回 null；stub进入 request不表示目标工具已加载，后续 model/tool-search support、generation和permission仍决定可用性。",
        "context-governance-and-caching.md",
    ),
    "tengu_bridge_attestation_enforce_config": (
        "object fallback `{}`；只有 trusted-device总 gate已开、组织 policy标为 enforced且 `tengu_bridge_attestation_enforce` 为 true时才交给 `Mad`解析 filter policy，否则使用内置默认。非法字段按 parser fallback，配置只决定客户端 attestation过滤，server token/enrollment判定仍是 Boundary。",
        "tui-ide-remote-cloud.md",
    ),
    "tengu_bridge_auth_revive": (
        "boolean fallback true；Remote Control因 auth失败而 disabled、非 outbound-only时，consumer轮询 credential generation，只在同 account新 token出现且未触发 noninteractive brake时重新 enable；4094 remint也受该 gate。跨账号、无 profile、达到尝试上限或 flag关闭保持失败，revive不会重放已丢 control request。",
        "auth-account-and-subscription-lifecycle.md",
    ),
    "tengu_bridge_initialize_commands": (
        "boolean fallback false；bridge client initialize时，consumer还排除受限 host，才把当前非 terminal-oriented slash commands映射进 init payload；关闭发空数组。命令列表是快照，可随 plugin/MCP reload过期；暴露命令不等于远端调用获批，handler permission和本地状态仍权威。",
        "cli-sdk-output-protocol.md",
    ),
    "tengu_bridge_owner_pinned_end": (
        "boolean fallback true；仅 first-party、非 privacy禁用、store credential且能解析 account identity时建立 owner pin。identity文件换账号会二次向server归属校验，确认 changed后取消 pending control、停止transport并用原 owner token archive；不确定时保守保持/重查。它防止跨账号续传，但 archive timeout不证明远端已终止。",
        "auth-account-and-subscription-lifecycle.md",
    ),
    "tengu_bridge_recovery_patience": (
        "boolean fallback true；CCR 401/4091/4093/4094恢复中，consumer决定 heartbeat/credential故障是否进入带间隔的 remint/refetch patience path及 cap，关闭会更早按对应 failure终止。owner-change、abort、OAuth拒绝和 superseded session仍立即停止；恢复只重建transport/credential，不重做已执行工具。",
        "resilience-and-recovery.md",
    ),
    "tengu_bridge_requires_action_details": (
        "boolean fallback false；发送 can_use_tool/request_user_dialog control request时，consumer为 Question/Plan/tool构造 label/body details并写 pending-action metadata；关闭只发送基础 pending action。details受已知 tool/input shape和长度裁剪，解析失败省略；它改善远端 UI提示，不改变 permission结果或证明用户已看到。",
        "tui-ide-remote-cloud.md",
    ),
    "tengu_bridge_resume_respects_local_owner": (
        "boolean fallback true；resume命中 persisted bridge pointer且本机 registry显示另一 live pid仍持有时，隐式恢复会 decline并保留原 owner，显式 enable可 takeover。registry查询失败继续既有流程；该 guard只解决本机 ownership竞争，不能证明远端没有其他 client。",
        "sessions-checkpoints-memory.md",
    ),
    "tengu_bridge_system_init": (
        "boolean fallback false；还要求 bridge已连接、非 outbound-only，并与 state-announce gate组合，才发送包含 model、permission mode、commands、agents、skills、MCP commands、fast/effort的 `system/init`；状态变化做去重。构建/发送失败记录但不断开 session，payload是客户端快照，不证明远端 UI已采用。",
        "cli-sdk-output-protocol.md",
    ),
    "tengu_composed_quail": (
        "boolean fallback true。consumer把本地 rate-limit event写入 Remote Control SDK stream，并去重镜像 `rate_limit_info` metadata；还要求存在 active bridge和可用 quota state。发送/metadata异常只记录，不改变本地限流；过期 rejected状态会清空镜像，远端展示与服务端quota权威值仍是 Boundary。",
        "usage-cost-credits-and-limits.md",
    ),
    "tengu_copper_kestrel": (
        "boolean fallback true。consumer控制 Remote Control `apply_flag_settings`中的 effort变更及连接后 effort同步；关闭返回明确 disabled或跳过。model capability、organization ceiling、request field和provider接受度仍独立，UI/bridge同步成功不证明下一API attempt采用该 effort。",
        "thinking-effort-and-fast-mode.md",
    ),
    "tengu_luminous_seal": (
        "boolean fallback true。consumer允许 Remote Control转发 conversation_reset与非 requesting状态/compact结果等 state frames；关闭会过滤这些 frame但本地状态照常变化。compact_error还受宿主可见性过滤，发送成功不等于远端已处理，reset不删除服务端或本地持久历史。",
        "cli-sdk-output-protocol.md",
    ),
    "tengu_sequential_puffin": (
        "boolean fallback true。resume恢复的 bridge pointer若 owner identity匹配，consumer允许保留 fresh-mint fallback；关闭会把该恢复变为 reattach-or-fail pinned路径。owner mismatch仍清指针并抑制history，identity不可读走保守分支；mint/reattach最终结果由远端session API决定。",
        "sessions-checkpoints-memory.md",
    ),
    "tengu_wobbly_pinwheel": (
        "boolean fallback true。consumer控制 permission-mode status frame和SDK state announce入口；还需 bridge连接，完整 system/init另受 `tengu_bridge_system_init`。关闭不阻止本地mode变化，只不向远端镜像；写失败保留本地权威状态，远端可能暂时显示旧mode。",
        "cli-sdk-output-protocol.md",
    ),
    "tengu_cobalt_harbor": (
        "boolean fallback false。它只在非 remote environment、非 persistent-remote session且没有 org `remote_control_at_startup` override时，作为 Remote Control auto-start默认值；用户/组织显式值优先。true仍要通过first-party、OAuth scope、subscription、policy和bridge rollout，失败不会强制启动。",
        "tui-ide-remote-cloud.md",
    ),
    "tengu_ide_rc_auto_enable": (
        "boolean fallback false；consumer仅把 `ide_rc_auto_enable_gate`放进 SDK initialize响应，实际 `remote_control_auto_enable`还由用户设置、host和bridge eligibility计算。它是宿主协商字段，不直接改app state；IDE是否采用、何时发控制请求属于host Boundary。",
        "tui-ide-remote-cloud.md",
    ),
    "tengu_teleport_send_to_cloud": (
        "boolean fallback false；只有当前已绑定非 outbound-only Remote Control session时，`/teleport`才切到 send-to-cloud menu，否则保留本地resume flow。handoff会处理 mayHaveCommitted、断开/重连和10s新session等待；结果未知时提示可能已提交，已移动的远端session不能由本地UI自动回滚。",
        "tui-ide-remote-cloud.md",
    ),
}


MANUAL_CONTRACT_FIELDS = (
    "owner",
    "readLocation",
    "fallbackPrecedence",
    "stateDelta",
    "failureBoundary",
    "userImpact",
    "document",
)


def manual_contract(
    *,
    owner: str,
    read_location: str,
    fallback_precedence: str,
    state_delta: str,
    failure_boundary: str,
    user_impact: str,
    document: str,
    lexical_functions: tuple[str, ...],
    callsite_count: int,
    access_modes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "owner": owner,
        "readLocation": read_location,
        "fallbackPrecedence": fallback_precedence,
        "stateDelta": state_delta,
        "failureBoundary": failure_boundary,
        "userImpact": user_impact,
        "document": document,
        "lexicalFunctions": lexical_functions,
        "callsiteCount": callsite_count,
    }
    if access_modes is not None:
        contract["accessModes"] = access_modes
    return contract


DEPLOYMENT_ENVIRONMENT_RULES: dict[str, tuple[str, str, int]] = {
    "APP_URL": ('value?.includes("ondigitalocean.app")', "digitalocean-app-platform", 1),
    "AWS_EXECUTION_ENV": (
        'value === "AWS_ECS_FARGATE" / value === "AWS_ECS_EC2"',
        "aws-fargate / aws-ecs",
        2,
    ),
    "AWS_LAMBDA_FUNCTION_NAME": ("non-empty", "aws-lambda", 1),
    "AZURE_FUNCTIONS_ENVIRONMENT": ("non-empty", "azure-functions", 1),
    "BUILDKITE": ("truthy", "buildkite", 1),
    "C9_PID": ("C9_PID || C9_USER", "aws-cloud9", 1),
    "C9_USER": ("C9_PID || C9_USER", "aws-cloud9", 1),
    "CF_PAGES": ("Nn(value)", "cloudflare-pages", 1),
    "CIRCLECI": ("truthy", "circleci", 1),
    "CODER": ("Nn(CODER) || CODER_WORKSPACE_NAME", "coder", 1),
    "CODER_WORKSPACE_NAME": ("Nn(CODER) || CODER_WORKSPACE_NAME", "coder", 1),
    "CODESPACES": ("Nn(value)", "codespaces", 1),
    "DAYTONA_WS_ID": ("non-empty", "daytona", 1),
    "DENO_DEPLOYMENT_ID": ("non-empty", "deno-deploy", 1),
    "DEVPOD": ("Nn(DEVPOD) || DEVPOD_WORKSPACE_UID", "devpod", 1),
    "DEVPOD_WORKSPACE_UID": ("Nn(DEVPOD) || DEVPOD_WORKSPACE_UID", "devpod", 1),
    "DYNO": ("non-empty", "heroku", 1),
    "FLY_APP_NAME": ("FLY_APP_NAME || FLY_MACHINE_ID", "fly.io", 1),
    "FLY_MACHINE_ID": ("FLY_APP_NAME || FLY_MACHINE_ID", "fly.io", 1),
    "GITLAB_CI": ("Nn(value)", "gitlab-ci", 1),
    "GITPOD_WORKSPACE_ID": ("non-empty", "gitpod", 1),
    "GOOGLE_CLOUD_WORKSTATIONS": ("Nn(value)", "gcp-cloud-workstations", 1),
    "KUBERNETES_SERVICE_HOST": ("non-empty", "kubernetes", 1),
    "NETLIFY": ("Nn(value)", "netlify", 1),
    "PROJECT_DOMAIN": ("non-empty", "glitch", 1),
    "RAILWAY_ENVIRONMENT_NAME": (
        "RAILWAY_ENVIRONMENT_NAME || RAILWAY_SERVICE_NAME",
        "railway",
        1,
    ),
    "RAILWAY_SERVICE_NAME": (
        "RAILWAY_ENVIRONMENT_NAME || RAILWAY_SERVICE_NAME",
        "railway",
        1,
    ),
    "RENDER": ("Nn(value)", "render", 1),
    "REPL_ID": ("REPL_ID || REPL_SLUG", "replit", 1),
    "REPL_SLUG": ("REPL_ID || REPL_SLUG", "replit", 1),
    "SPACE_CREATOR_USER_ID": ("non-empty", "huggingface-spaces", 1),
    "VERCEL": ("Nn(value)", "vercel", 1),
    "WEBSITE_SITE_NAME": (
        "WEBSITE_SITE_NAME || WEBSITE_SKU",
        "azure-app-service",
        1,
    ),
    "WEBSITE_SKU": (
        "WEBSITE_SITE_NAME || WEBSITE_SKU",
        "azure-app-service",
        1,
    ),
}


ENV_MANUAL_CONTRACTS: dict[str, dict[str, Any]] = {
    name: manual_contract(
        owner="CLI 运行时指纹中的部署环境探测器 `flu.detectDeploymentEnvironment -> x1y`",
        read_location=(
            f"`x1y` 在 "
            "[readable L21360](../reverse/javascript/cli.readable.js#L21360)"
            f" 读取 `process.env.{name}`"
        ),
        fallback_precedence=(
            f"按顺序执行 first-match；`{predicate}` 命中即返回 `{label}`；更早的部署规则优先，"
            "未命中才继续检查后续 cloud/container/platform fallback"
        ),
        state_delta=(
            f"探测器返回 `{label}` 并缓存到 `flu.deploymentEnvironment`；"
            "运行时指纹随后把它投射为 `deploymentEnvironment`"
        ),
        failure_boundary=(
            "缺失或不匹配不会抛错，只会继续 fallback；真实值、最终命中的更早规则和下游遥测是否送达仍是运行时 Boundary"
        ),
        user_impact=(
            "改变诊断和运行时元数据中的环境归因，不选择模型 provider，也不改变工具权限或 sandbox enforcement"
        ),
        document="technical-architecture.md",
        lexical_functions=("x1y",),
        callsite_count=count,
        access_modes=("read",),
    )
    for name, (predicate, label, count) in DEPLOYMENT_ENVIRONMENT_RULES.items()
}


ENV_MANUAL_CONTRACTS.update(
    {
        "SELF_HOSTED_RUNNER_BASE_DIR": manual_contract(
            owner="self-hosted runner 的 argv/环境编译器 `v_y -> dw0`",
            read_location="`v_y` 在 [readable L636958](../reverse/javascript/cli.readable.js#L636958) 读取并解析路径",
            fallback_precedence="`--base-dir` 高于环境变量；两者都缺失时才用内置 `/workspace`",
            state_delta="写入 `config.baseDir/baseDirSource`，随后作为 checkout 根目录、runner 临时状态和 session workspace 的 owner",
            failure_boundary="Windows 拒绝内置 POSIX 默认值；目录不可写会在 runner 注册前以 code 2 退出",
            user_impact="移动全部 self-hosted checkout，直接改变持久化位置、磁盘压力和清理范围",
            document="runtime-supervision-and-processes.md",
            lexical_functions=("v_y",),
            callsite_count=1,
            access_modes=("read",),
        ),
        "SELF_HOSTED_RUNNER_EXEC_PATH": manual_contract(
            owner="self-hosted runner 子进程 launcher `v_y -> dw0 -> C_y`",
            read_location="`v_y` 在 [readable L636958](../reverse/javascript/cli.readable.js#L636958) 把值写入 `config.execPath`",
            fallback_precedence="`--exec-path` 高于环境变量；两者都缺失时先允许 command hook 提供路径，最后回退 `process.execPath`",
            state_delta="选择每个已认领 session child 实际启动的 executable，并保留当前进程 argv fallback",
            failure_boundary="路径不存在或不可 spawn 会在后续 child launch 失败；选中路径不证明其版本和完整性",
            user_impact="决定远端任务究竟由哪个 Claude binary 执行，以及 session 能否启动",
            document="runtime-supervision-and-processes.md",
            lexical_functions=("v_y",),
            callsite_count=1,
            access_modes=("read",),
        ),
        "SELF_HOSTED_RUNNER_LOG_FILE": manual_contract(
            owner="self-hosted runner 日志 sink `v_y -> dw0`",
            read_location="`v_y` 在 [readable L636958](../reverse/javascript/cli.readable.js#L636958) 初始化 `config.logFile`",
            fallback_precedence="`--log-file` 高于环境变量；空值表示只保留 stdout/stderr",
            state_delta="以 0600 mode 打开 append stream，把 runner status/debug 行 tee 到文件且不替换 stdout",
            failure_boundary="打开或后续写入失败只告警并降级为 stdout-only；不能据此证明文件已持久 flush",
            user_impact="增加本地持久的 runner 审计/调试轨迹，同时引入磁盘和隐私成本",
            document="runtime-supervision-and-processes.md",
            lexical_functions=("v_y",),
            callsite_count=1,
            access_modes=("read",),
        ),
        "SELF_HOSTED_RUNNER_DEBUG_TOKEN_DIR": manual_contract(
            owner="self-hosted runner 调试凭据落盘器 `v_y -> dw0 -> p_y`",
            read_location="`v_y` 在 [readable L636958](../reverse/javascript/cli.readable.js#L636958) 初始化 `config.debugTokenDir`",
            fallback_precedence="`--debug-token-dir` 高于环境变量；缺失时不写 token 文件",
            state_delta="best-effort 创建 0700 目录，并以 0600 写入或刷新 `runner_token.jwt`",
            failure_boundary="mkdir/write 错误只记录日志，runner 继续运行；token 有效性和文件系统保密性都未被证明",
            user_impact="为了调试把 live runner credential 暴露到磁盘，显著改变本地 secret-handling surface",
            document="runtime-supervision-and-processes.md",
            lexical_functions=("v_y",),
            callsite_count=1,
            access_modes=("read",),
        ),
        "SELF_HOSTED_RUNNER_LOCK_TO_ACCOUNT": manual_contract(
            owner="self-hosted runner 注册编译器 `v_y -> dw0 -> registerRunner`",
            read_location="`v_y` 在 [readable L636958](../reverse/javascript/cli.readable.js#L636958) 初始化 `config.lockToAccountId`",
            fallback_precedence="`--lock-to-account` 高于环境变量；缺失时不发送 account lock",
            state_delta="把 account id 传给 `registerRunner`，约束服务端 assignment request",
            failure_boundary="注册对暂时性故障最多重试 5 次后 exit 1；服务端是否接受和后续是否分配仍是远端 Boundary",
            user_impact="限制这个 runner 能接收哪个账号的任务；lock 被拒绝时会阻止启动",
            document="remote-routines-runner-and-notifications.md",
            lexical_functions=("v_y",),
            callsite_count=1,
            access_modes=("read",),
        ),
        "CLAUDE_RUNNER_USE_GIT_PROXY": manual_contract(
            owner="self-hosted runner Git transport 编译器 `v_y -> dw0`",
            read_location="`v_y` 在 [readable L636958](../reverse/javascript/cli.readable.js#L636958) 用 `Nn()` 解析该值",
            fallback_precedence="truthy 环境值启用该 lane；`--use-anthropic-git-proxy` 也能强制 true，CLI 没有 false 去覆盖已为 true 的环境值",
            state_delta="启用 per-session Anthropic Git proxy，并为跨 session 隔离重写/清除 HOME-level Git config",
            failure_boundary="capacity >1、Git <2.32、不安全 config target 或 credential-helper 配置都会让启动失败；proxy auth 和 clone 成功仍属外部 Boundary",
            user_impact="改变 Git credential owner 和 clone route，也放大错误 global Git 配置的影响",
            document="remote-routines-runner-and-notifications.md",
            lexical_functions=("v_y",),
            callsite_count=1,
            access_modes=("read",),
        ),
        "SELF_HOSTED_RUNNER_CONFIGURE_GIT": manual_contract(
            owner="self-hosted runner Git identity/signing bootstrap `v_y -> dw0`",
            read_location="`v_y` 在 [readable L636958](../reverse/javascript/cli.readable.js#L636958) 用 `Nn()` 解析该值",
            fallback_precedence="truthy 环境值启用该 lane；`--configure-git` 可强制 true；缺失时保留 image 自带 Git config",
            state_delta="执行 `configureGitForSigning`，并把 coauthor/signing artifacts 传入每个 child session",
            failure_boundary="Git 缺失或 config 不可写会 fatal exit 1；本地配置成功不证明远端 signing service 会接受 commit",
            user_impact="控制 self-hosted session 的 commit identity/signing，并可能在任务开始前阻断 runner",
            document="remote-routines-runner-and-notifications.md",
            lexical_functions=("v_y",),
            callsite_count=1,
            access_modes=("read",),
        ),
        "SELF_HOSTED_RUNNER_PUSH_OUTCOME_ON_RELEASE": manual_contract(
            owner="self-hosted runner 的 release/drain 保全路径 `v_y -> A_y/e_y`",
            read_location="`v_y` 在 [readable L636958](../reverse/javascript/cli.readable.js#L636958) 用 `Nn()` 解析该值",
            fallback_precedence="truthy 环境值启用该 lane；`--push-outcome-on-release` 可强制 true；缺失时 release 只处理本地状态",
            state_delta="增加共享 30 秒 push window，让非 completed release 路径把 tracked outcome branch 推到远端供 resume",
            failure_boundary="server-initiated deassign 和 hook-owned repo 被排除；push timeout/failure 可能留下结果未知的远端状态，且绝不回滚 commit",
            user_impact="改善 runner 重启连续性，但会产生远端 Git 写入，并在 resume 时新增不可信 ref surface",
            document="remote-routines-runner-and-notifications.md",
            lexical_functions=("v_y",),
            callsite_count=1,
            access_modes=("read",),
        ),
        "SELF_HOSTED_RUNNER_TRUST_WORKSPACE": manual_contract(
            owner="self-hosted runner workspace-trust 编译器 `v_y -> child session config`",
            read_location="`v_y` 在 [readable L636946](../reverse/javascript/cli.readable.js#L636946) 通过 `cw0()` 解析该值",
            fallback_precedence="`--trust-workspace` 高于环境变量；空值默认 true；true/false 的允许拼法被显式解析",
            state_delta="控制 repo-level `.claude/settings.json` grants 和 additional directories 是否为 child session 注入 trust",
            failure_boundary="非法环境文本在启动时 fail closed；false 会带诊断丢弃 repo grants，但不能撤销 host-level policy grants",
            user_impact="决定仓库提交的 permission grants 能否影响 self-hosted session 工具",
            document="onboarding-workspace-trust-and-safe-startup.md",
            lexical_functions=("v_y",),
            callsite_count=1,
            access_modes=("read",),
        ),
        "SELF_HOSTED_RUNNER_CONFINE_REPO_SETTINGS": manual_contract(
            owner="self-hosted runner repo-settings confinement 编译器 `v_y -> child preflight`",
            read_location="`v_y` 在 [readable L636952](../reverse/javascript/cli.readable.js#L636952) 通过 `uw0()` 解析该值",
            fallback_precedence="`--confine-repo-settings` 高于环境变量；空值默认 `warn`；只接受 `enforce/warn/off`",
            state_delta="选择 repo-setting 违规仅记录、拒绝 child spawn，或跳过 confinement scan",
            failure_boundary="非法输入会退出启动；warn 仍会 spawn，off 只移除此 scan，不移除其他 policy/permission gate",
            user_impact="决定不安全 repo setting 是提示性问题，还是 self-hosted 执行的硬阻断",
            document="onboarding-workspace-trust-and-safe-startup.md",
            lexical_functions=("v_y",),
            callsite_count=1,
            access_modes=("read",),
        ),
    }
)


FEATURE_MANUAL_CONTRACTS: dict[str, dict[str, Any]] = {
    "tengu_classifier_disabled_surfaces": manual_contract(
        owner="background/remote 状态分类器的 sink 编译器 `$cf`",
        read_location="`$cf` 在 [readable L270312](../reverse/javascript/cli.readable.js#L270312) 通过 `BWS()` 解析逗号列表",
        fallback_precedence="空字符串 fallback 不禁用任何 surface；只接受 `bg/watched/ccr/bridge/desktop/cli/repl`，未知名称忽略且仅告警一次",
        state_delta="在选择 classifier engine 前，删除每个被禁 surface 所拥有的全部 sink",
        failure_boundary="background 会独立删除 `summary`；禁用 sink 不停止任务执行，也不擦除已有 status record",
        user_impact="可压掉指定 host 的 status/headline/summary 投影，但底层 Agent Loop 继续运行",
        document="runtime-supervision-and-processes.md",
        lexical_functions=("$cf",),
        callsite_count=1,
    ),
    "tengu_classifier_summary_kill": manual_contract(
        owner="background/remote 状态分类器的 sink 编译器 `$cf`",
        read_location="`$cf` 在 [readable L270318](../reverse/javascript/cli.readable.js#L270318) 完成 surface 展开后读取该布尔值",
        fallback_precedence="false 保留 surface 提供的 summary sink；true 在所有 surface 合并后删除 `summary`",
        state_delta="强制进入无 summary 的分类形态；除非其他 state sink 要求 LLM，`Bcf` 会选择 heuristic",
        failure_boundary="state/headline sink 仍保留；该 flag 既不取消分类，也不保证 heuristic 结果正确",
        user_impact="从 CCR/bridge/desktop/CLI surface 移除 post-turn summary，但不会停止任务",
        document="runtime-supervision-and-processes.md",
        lexical_functions=("$cf",),
        callsite_count=1,
    ),
    "tengu_classifier_summary_llm_emit": manual_contract(
        owner="classifier engine 选择器 `UWS -> Bcf`",
        read_location="`UWS` 在 [readable L270337](../reverse/javascript/cli.readable.js#L270337) 读取该布尔值",
        fallback_precedence="false 让仅 summary 的 sink 默认走 `heuristic`；显式 `CLAUDE_CODE_CLASSIFIER_SUMMARY` 和 state sink 优先",
        state_delta="为剩余 summary sink 选择 `llm` 而非 `heuristic`，启动带独立 token/timeout budget 的 side-query",
        failure_boundary="LLM error、timeout 或非法 JSON 会降级到 heuristic；classifier 永不授予工具权限",
        user_impact="用延迟、模型 token 和额外降级路径换取更丰富的状态摘要",
        document="runtime-supervision-and-processes.md",
        lexical_functions=("UWS",),
        callsite_count=1,
    ),
    "tengu_feedback_survey_config": manual_contract(
        owner="终端与 VS Code feedback-survey 调度器 `AUg/eEr`、`GJg`",
        read_location="同步 VS Code 路径在 [readable L598084](../reverse/javascript/cli.readable.js#L598084) 的 `GJg` 读取；终端 hook 还会通过 `H_e` 异步解析同一 key",
        fallback_precedence="回退 `Kms`：初始 10 分钟、local interval 1 小时、至少 5 turns、概率 0.005；账号 survey-rate 可覆盖 probability",
        state_delta="在打开 survey UI 前配置 eligibility 时间、model allowlist、随机抽样和 impression 持久化",
        failure_boundary="provider、privacy、policy、disable env、其他 survey 和 cooldown 仍可拒绝；submission/upload 是独立网络 Boundary",
        user_impact="改变产品反馈提示出现的时机和频率，不允许反馈绕过 consent/policy",
        document="telemetry.md",
        lexical_functions=("GJg",),
        callsite_count=1,
    ),
    "tengu_vscode_feedback_survey": manual_contract(
        owner="VS Code/desktop SDK feedback-survey gate `GJg`",
        read_location="`GJg` 在 [readable L598084](../reverse/javascript/cli.readable.js#L598084) 读取；false 时在加载 config 前直接退出",
        fallback_precedence="false 关闭该 host survey；还必须命中支持的 VS Code/desktop host，并通过 product-feedback policy 与 privacy gate",
        state_delta="向 SDK host 返回 survey config，并在 appeared event 后持久化 `lastShownTime`",
        failure_boundary="disabled/error 路径不返回 config；OTLP proxy emission 失败被收口，不会伪造 upload 成功",
        user_impact="控制 IDE/desktop 用户能否看到与终端同源的 feedback flow",
        document="telemetry.md",
        lexical_functions=("GJg",),
        callsite_count=1,
    ),
    "tengu_fleetview_simple": manual_contract(
        owner="Agent/Fleet View 根组件 `CBg`",
        read_location="`CBg` 在 [readable L577686](../reverse/javascript/cli.readable.js#L577686) 把该 flag 与 `CLAUDE_CODE_FLEETVIEW_SIMPLE` 合并",
        fallback_precedence="环境变量 true 优先；否则 false 保留完整视图；显式打开 `remote-*` item 仍会启用 remote lane",
        state_delta="simple mode 在普通 Fleet View 中取消初始 remote-job hydration 和 30 秒 remote poll",
        failure_boundary="local/daemon job 仍保留；remote polling error 本来就被收口，flag 不删除任何 remote job",
        user_impact="降低后台网络和 UI 复杂度，但在显式打开 remote item 前隐藏普通 remote jobs",
        document="runtime-supervision-and-processes.md",
        lexical_functions=("CBg",),
        callsite_count=1,
    ),
    "tengu_fleetview_peers": manual_contract(
        owner="Agent/Fleet View 的 cross-session peer 投影 `CBg`",
        read_location="`CBg` 的 3 次读取在 [readable L578024](../reverse/javascript/cli.readable.js#L578024) 分别控制 peer listener、500ms registry 投影和渲染",
        fallback_precedence="false 隐藏 peers；true 仍要求独立 cross-session messaging gate `Hg()`",
        state_delta="启动 peer observation，把 protocol 达标、24 小时内仍 fresh 的其他 interactive process 投影为 `peer-<pid>` 行",
        failure_boundary="registry/listener 失败被捕获并返回空 peers；出现一行只证明本地 liveness metadata，不证明消息送达或 authority",
        user_impact="在 Agent View 展示其他 Claude session 供发现，同时明确它们不是本 session 的 workers",
        document="cloud-background-channels.md",
        lexical_functions=("<top-level>", "CBg"),
        callsite_count=3,
    ),
    "tengu_ultraplan_config": manual_contract(
        owner="remote Ultraplan eligibility gate `X6e`",
        read_location="`X6e` 在 [readable L363793](../reverse/javascript/cli.readable.js#L363793) 读取 object member `enabled`",
        fallback_precedence="null 表示关闭；`enabled:true` 还必须通过 Remote Control entitlement `uXt()` 与非 remote-session gate `!sc()`",
        state_delta="放行 cloud planning 的 launch/poll 路径，而不是把 planning 留在本地",
        failure_boundary="除显式 true 外的 shape 都视为关闭；账号 rollout、session 创建和远端执行仍属外部 Boundary",
        user_impact="让本地终端可进入高级规划，但不保证 cloud plan 启动或完成",
        document="plan-mode-and-human-approval.md",
        lexical_functions=("X6e",),
        callsite_count=1,
    ),
    "tengu_ultraplan_timeout_seconds": manual_contract(
        owner="Ultraplan poll 编排器 `jzv -> Irm`",
        read_location="`jzv` 在 [readable L363902](../reverse/javascript/cli.readable.js#L363902) 把值乘以 1000 后传给 `Irm`",
        fallback_precedence="数值 fallback 为 5400 秒；可见 callsite 在换算前没有 range clamp",
        state_delta="设置 cloud-plan 总 polling deadline；phase change 同时更新 task state 和本地 notification",
        failure_boundary="timeout 变成 `UltraplanPollError`，best-effort archive 后把 task 标 failed；远端工作可能已经推进",
        user_impact="改变终端等待 plan approval/result 多久后才报告终止",
        document="plan-mode-and-human-approval.md",
        lexical_functions=("<top-level>",),
        callsite_count=1,
    ),
    "tengu_kairos_push_notifications": manual_contract(
        owner="主动通知 capability gate `E3e/KDt`",
        read_location="`E3e` 在 [readable L154799](../reverse/javascript/cli.readable.js#L154799) 读取该布尔值",
        fallback_precedence="false 关闭 capability；真正由模型决定的 push 还要求已保存的 `agentPushNotifEnabled` 以及可用 host/Remote Control state",
        state_delta="暴露 notification settings/tool affordance，并允许主动 push lane 进入候选",
        failure_boundary="config off、终端仍活跃、bridge 缺失或 delivery failure 都返回 not-sent；远端是否收到 push 是外部 Boundary",
        user_impact="在独立用户 opt-in 之后，允许 Claude 把用户注意力从终端外拉回 session",
        document="remote-routines-runner-and-notifications.md",
        lexical_functions=("E3e",),
        callsite_count=1,
    ),
    "tengu_kairos_input_needed_push": manual_contract(
        owner="notification settings 编译器 `B1n -> fdr/config UI`",
        read_location="`B1n` 在 [readable L154802](../reverse/javascript/cli.readable.js#L154802) 读取该布尔值",
        fallback_precedence="false 隐藏该行；true 仍要求父级 push capability、受支持 host 和未禁用的 notification surface",
        state_delta="新增标为 `Push when actions required` 的 `inputNeededNotifEnabled` toggle，并持久化用户选择",
        failure_boundary="该 key 本身不发送 push；permission/question 检测、bridge connectivity 和 mobile delivery 都是后续 gate",
        user_impact="让用户可单独订阅因 permission/question 阻塞而产生的移动端提醒",
        document="remote-routines-runner-and-notifications.md",
        lexical_functions=("B1n",),
        callsite_count=1,
    ),
    "tengu_kairos_ready_nudge": manual_contract(
        owner="Remote Control ready-push nudge parser `OJh`",
        read_location="`OJh` 在 [readable L501906](../reverse/javascript/cli.readable.js#L501906) 读取并校验 config",
        fallback_precedence="null 关闭；true 展开为 probability 1/max 5；object probability clamp 到 0..1，finite max 取整，缺失字段使用默认值",
        state_delta="bridge 新连接后可写一条 SDK message，并持久化 impression count/key",
        failure_boundary="push capability、connection state、历史 impression 和随机抽样均可拒绝；send 不证明移动端已展示",
        user_impact="控制一个有次数上限的提示，告知用户 session 已可在手机继续",
        document="tui-ide-remote-cloud.md",
        lexical_functions=("OJh",),
        callsite_count=1,
    ),
    "tengu_kairos_loop_prompt": manual_contract(
        owner="自主 `/loop` sentinel 解析器 `LZo -> qha/jop`",
        read_location="`LZo` 在 [readable L154955](../reverse/javascript/cli.readable.js#L154955) 读取该布尔值",
        fallback_precedence="false 原样返回 scheduled prompt；true 也只识别固定 sentinel string",
        state_delta="把识别出的 wakeup 改写为 autonomous-loop preamble/tick，并记录 preamble 或 loop file 是否已投递",
        failure_boundary="loop file 缺失/为空时降级为 no-op/autonomous tick；该 flag 自己从不调度下一次 wakeup",
        user_impact="让 recurring wakeup 延续 durable loop，无需每个 tick 重复完整 instructions",
        document="active-goal-and-stop-loop.md",
        lexical_functions=("LZo",),
        callsite_count=1,
    ),
    "tengu_kairos_loop_persistent": manual_contract(
        owner="autonomous-loop instruction 选择器 `MZo -> Bha/j1n`",
        read_location="`MZo` 在 [readable L154926](../reverse/javascript/cli.readable.js#L154926) 读取该 flag",
        fallback_precedence="`CLAUDE_CODE_LOOP_PERSISTENT` true 优先；否则 false 选择保守 preamble，true 选择 persistent-loop guidance",
        state_delta="改变 loop tick 内嵌的 stop criteria 和 blocked-state notification 文案",
        failure_boundary="它改变 instructions，不改变 scheduler enforcement；stop call、age limit、abort 和无可做工作仍会结束 loop",
        user_impact="让自主检查更倾向继续搜索/rearm，而不是一次安静结果后立即停止",
        document="active-goal-and-stop-loop.md",
        lexical_functions=("MZo",),
        callsite_count=1,
    ),
    "tengu_kairos_loop_dynamic": manual_contract(
        owner="dynamic loop scheduler 与 `ScheduleWakeup` tool gate `Vft`",
        read_location="`Vft` 在 [readable L155102](../reverse/javascript/cli.readable.js#L155102) 读取该布尔值",
        fallback_precedence="false 让 `ScheduleWakeup` 保持 deferred，直接调用则以 `gate_off` 结束；true 启用 60..3600 秒 self-paced wakeup",
        state_delta="注册/显露 scheduler tool，替换旧 loop wakeup，并写入 pending cron/loop state",
        failure_boundary="age limit、user abort、显式 stop 和 keepalive budget 都会终止；scheduled time 不证明未来进程仍存活",
        user_impact="让模型选择下一次 loop interval，而不是固定 recurring cron",
        document="active-goal-and-stop-loop.md",
        lexical_functions=("Vft",),
        callsite_count=1,
    ),
    "tengu_kairos_loop_keepalive": manual_contract(
        owner="post-tick fallback rearm 路径 `Wop -> Vop`",
        read_location="`Wop` 在 [readable L155108](../reverse/javascript/cli.readable.js#L155108) 读取该 flag",
        fallback_precedence="`CLAUDE_CODE_LOOP_KEEPALIVE` true 优先；否则 false 表示模型漏掉 rearm 时不补 fallback",
        state_delta="已完成 tick 且没有 pending loop 时，补一个 1200 秒 fallback 并增加 keepalive budget",
        failure_boundary="有限 budget 阻止反复漏调；gate-off/age/abort 也会结束 loop；timer 不构成 durable execution 证明",
        user_impact="避免一次意外漏掉 reschedule 就立刻杀死 active dynamic loop",
        document="active-goal-and-stop-loop.md",
        lexical_functions=("Wop",),
        callsite_count=1,
    ),
    "tengu_loop_noop_fold": manual_contract(
        owner="dynamic-loop tool schema 与 scheduled-task UI 投影 `$2r`",
        read_location="`$2r` 在 [readable L155105](../reverse/javascript/cli.readable.js#L155105) 读取该布尔值",
        fallback_precedence="false 不暴露 `noop` input；true 要求非 stop 调用必须提供，并在 fire 时启用 loop-row folding",
        state_delta="记录 tick 是否改变状态，并在终端视图折叠连续 no-op ticks",
        failure_boundary="缺失必填 `noop` 会拒绝 tool call；folding 只改 presentation，绝不删除 transcript/task state",
        user_impact="减少重复 quiet-loop 噪声，同时保留真正有变化的 tick",
        document="active-goal-and-stop-loop.md",
        lexical_functions=("$2r",),
        callsite_count=1,
    ),
    "tengu_kairos_brief_stop_hook_text": manual_contract(
        owner="Brief post-turn enforcement 文案解析器 `KWS`",
        read_location="`KWS` 在 [readable L270409](../reverse/javascript/cli.readable.js#L270409) 读取该字符串",
        fallback_precedence="空值/非字符串回退 bundled reminder，明确只有 `SendUserMessage` 能到达用户",
        state_delta="Brief turn 结束却没调用必需的用户可见工具时，改变注入的 stop-hook reminder",
        failure_boundary="Brief entitlement、host 和 stop-hook gate 仍适用；文案不能保证模型调用工具或 delivery 成功",
        user_impact="改变防止 Brief 静默回复的 recovery instruction，但不改变隐藏 plain-text 的规则",
        document="brief-mode-and-user-visible-output.md",
        lexical_functions=("KWS",),
        callsite_count=1,
    ),
    "tengu_ptc_enabled": manual_contract(
        owner="SDK/Remote Control 的 staged MCP call dispatcher",
        read_location="`mcp_call` control-request handler 在 [readable L601989](../reverse/javascript/cli.readable.js#L601989) 读取该值",
        fallback_precedence="true 允许 staged request；只有 input/output files、expiry 或 timeout 让调用成为 staged 时才读取该 flag",
        state_delta="false 会在 MCP connect/call 前以 `staged mcp_call is disabled` 拒绝；普通非 staged MCP call 绕过此 switch",
        failure_boundary="true 仍要求已连接的非 SDK MCP server、staging 校验、session/auth/elicitation 状态和工具成功",
        user_impact="只 kill 需要 file staging 或 deadline metadata 的 MCP call，不关闭全部 MCP",
        document="cli-sdk-output-protocol.md",
        lexical_functions=("<top-level>",),
        callsite_count=1,
    ),
    "tengu_native_cursor": manual_contract(
        owner="TUI cursor renderer 选择器 `DTa -> gXe`",
        read_location="`DTa` 在 [readable L178374](../reverse/javascript/cli.readable.js#L178374) 读取该 flag",
        fallback_precedence="accessibility、screen-reader 和 `CLAUDE_CODE_NATIVE_CURSOR` override 优先；否则 false 保留 non-native path，且 `!Mmt()` 也必须通过",
        state_delta="缓存 `nativeCursorEnabled`，在 raw terminal rendering 中启用平台 native cursor handling",
        failure_boundary="unsupported/alternate renderer gate 会 fallback 且不修改输入文本；终端表现仍依赖 host capability",
        user_impact="改变 cursor 可见性和移动兼容性，尤其影响 accessibility 与特定终端渲染",
        document="tui-input-accessibility-media-ide-chrome.md",
        lexical_functions=("DTa",),
        callsite_count=1,
    ),
    "tengu_left_arrow_editing_guard": manual_contract(
        owner="空 editor 的 left-arrow gesture state machine `Ze -> _Nm`",
        read_location="`Ze` 在 [readable L428684](../reverse/javascript/cli.readable.js#L428684) 把值传入 `_Nm`",
        fallback_precedence="true 启用 edit 后的 arm/absorb timing；false 让 solo left-arrow 立即 fire；non-solo input 始终 reject",
        state_delta="选择 `fire/arm/absorb/attach-*` transition，并在打开/脱离 Agent View 前更新 gesture timestamp",
        failure_boundary="guard 只作用于空 editor，绝不修改 message text；modifier/non-solo 情况保留普通 cursor movement",
        user_impact="避免 edit 或 attach 活动后，一次有歧义的左箭头误切换视图",
        document="tui-input-accessibility-media-ide-chrome.md",
        lexical_functions=("Ze",),
        callsite_count=1,
    ),
    "tengu_mem_push_delete_mode": manual_contract(
        owner="shared-memory multi-store 删除策略 `ZQo -> wHn`",
        read_location="`ZQo` 在 [readable L158864](../reverse/javascript/cli.readable.js#L158864) 读取并校验字符串",
        fallback_precedence="`CLAUDE_CODE_MEMORY_PUSH_DELETE_MODE` 原样优先且 `ZQo` 不校验；下游非 `immediate/never` 值走 corroborate 分支；服务端 flag 非这两个值也显式回退 `corroborate`",
        state_delta="在 enqueue delete 前，选择立即远端删除、永久抑制，或两次 walk 加时间的 corroboration",
        failure_boundary="read-only/discovery policy、disk trust、partition manifest、mass-delete hold 和 conflict recovery 仍可阻断；远端删除不可在本地回滚",
        user_impact="控制本地文件消失向 shared team/user memory 传播的激进程度",
        document="sessions-checkpoints-memory.md",
        lexical_functions=("ZQo",),
        callsite_count=1,
    ),
    "tengu_propose_goal": manual_contract(
        owner="`ProposeGoal` tool registration 与 settings surface `REi`",
        read_location="`REi` 在 [readable L299488](../reverse/javascript/cli.readable.js#L299488) 读取该布尔值",
        fallback_precedence="false 不注册 tool/config row；true 仍会被 noninteractive、remote、background 和用户 setting `disabled` gate 拒绝",
        state_delta="注册 non-concurrent read-only proposal tool：要么打开 approval，要么记录用户已明确授权的 goal",
        failure_boundary="agent context 被拒绝，condition 接受长度/schema 校验，用户取消后不留下 active goal",
        user_impact="允许 Claude 提议可度量 completion condition，但不会静默把每个任务变成 persistent goal",
        document="active-goal-and-stop-loop.md",
        lexical_functions=("REi",),
        callsite_count=1,
    ),
    "tengu_retire_chat_relay_artifact_backstop": manual_contract(
        owner="Artifact SDK-default-off 分类器 `Fip -> Uip`",
        read_location="`Fip` 在 [readable L155856](../reverse/javascript/cli.readable.js#L155856) 的 chat-relay/SDK entrypoint 逻辑中读取该 flag",
        fallback_precedence="false 让 chat-relay-like host 默认关闭 Artifact；显式 `CLAUDE_CODE_ARTIFACT=true` 后续仍可覆盖；GitHub Action/MCP 独立保持关闭",
        state_delta="true 只移除这一层 default-off backstop，使正常 first-party/admin/user Artifact gate 可以继续决定是否注册工具",
        failure_boundary="admin disable、provider、host exclusion、rollout、ownership 和 publish failure 都保留；该 flag 不执行 upload",
        user_impact="改变 relay/SDK surface 的 Artifact 可用性，但不绕过 publication control",
        document="workflow-artifact-design.md",
        lexical_functions=("Fip",),
        callsite_count=1,
    ),
    "tengu_cowork_chrome_automode_default": manual_contract(
        owner="Chrome tool 的 permission-context 编译器 `Xza -> jor`",
        read_location="`Xza` 在 [readable L277868](../reverse/javascript/cli.readable.js#L277868) 构建 `chromeClassifierFloorEnabled` 时读取",
        fallback_precedence="显式 `CLAUDE_CHROME_CLASSIFIER_FLOOR` 通过 `??` 优先；flag false 是后备值，Auto Mode availability 还必须为 true",
        state_delta="为 Chrome tool rule 启用 classifier floor，防止 broad allow 在覆盖的 Chrome surface 跳过 Auto Mode review",
        failure_boundary="managed deny/ask、tool schema、hooks、sandbox 和 classifier failure 仍分别决定；true 不是自动 allow",
        user_impact="即使存在 allow rule，也提高 Chrome automation 的 review 强度",
        document="auto-mode-classifier.md",
        lexical_functions=("<top-level>",),
        callsite_count=1,
    ),
}


def reviewed_contract(
    *,
    owner: str,
    reader: str,
    line: int,
    fallback: str,
    state: str,
    failure: str,
    impact: str,
    document: str,
    functions: tuple[str, ...],
    callsites: int,
    access_modes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    return manual_contract(
        owner=owner,
        read_location=(
            f"`{reader}` 在 [readable L{line}]"
            f"(../reverse/javascript/cli.readable.js#L{line}) 读取或写入该值"
        ),
        fallback_precedence=fallback,
        state_delta=state,
        failure_boundary=failure,
        user_impact=impact,
        document=document,
        lexical_functions=functions,
        callsite_count=callsites,
        access_modes=access_modes,
    )


ENV_MANUAL_CONTRACTS.update(
    {
        "SELF_HOSTED_RUNNER_ENVIRONMENT_SECRET": reviewed_contract(
            owner="self-hosted runner 注册凭据解析器 `E_y`",
            reader="E_y",
            line=634185,
            fallback="`--environment-secret-file` 最高；其次 `SELF_HOSTED_RUNNER_ENVIRONMENT_SECRET`；最后才读 deprecated `SELF_HOSTED_RUNNER_POOL_SECRET`",
            state="trim 后作为 `registerRunner` 的 environment secret；spawn child 前显式从继承环境清除",
            failure="缺失会在注册前抛错；无效或已撤销 secret 使 register auth fail 并退出，服务端接受仍是 Boundary",
            impact="决定 self-hosted runner 能否注册，同时避免长期 secret 自然继承到 session child",
            document="remote-routines-runner-and-notifications.md",
            functions=("$gy", "E_y"),
            callsites=2,
            access_modes=("read",),
        ),
        "SELF_HOSTED_RUNNER_POOL_SECRET": reviewed_contract(
            owner="self-hosted runner deprecated 注册凭据解析器 `E_y`",
            reader="E_y",
            line=634187,
            fallback="只在 file 与 `SELF_HOSTED_RUNNER_ENVIRONMENT_SECRET` 均缺失时采用，并打印迁移警告",
            state="trim 后进入同一 runner registration credential slot；spawn child 前清除",
            failure="缺失/无效与新变量走相同 fatal registration path；deprecated alias 不改变远端凭据语义",
            impact="维持旧部署兼容，但用户会收到改用 environment secret 的明确提示",
            document="remote-routines-runner-and-notifications.md",
            functions=("$gy", "E_y"),
            callsites=2,
            access_modes=("read",),
        ),
        "SELF_HOSTED_RUNNER_HOST_CONFIG_DIR": reviewed_contract(
            owner="self-hosted runner host-config snapshot owner `Yyy`",
            reader="Yyy",
            line=634968,
            fallback="该变量优先于 `CLAUDE_CONFIG_DIR`，两者缺失回退 `~/.claude`；空目录可显式关闭 host config seed",
            state="把受控 settings、agents、skills 等复制为 child 的 host config snapshot，runtime state 不按普通目录整包继承",
            failure="symlink/identity/size 检查或总预算失败会拒绝 snapshot；远端 child 后续消费仍单独验证",
            impact="决定管理员/宿主级配置怎样进入每个 self-hosted session，也控制快照大小和信任面",
            document="runtime-supervision-and-processes.md",
            functions=("Yyy",),
            callsites=2,
            access_modes=("read",),
        ),
        "SELF_HOSTED_RUNNER_HEALTH_PORT": reviewed_contract(
            owner="self-hosted runner health listener 配置 `Igy/v_y`",
            reader="Igy/v_y",
            line=633772,
            fallback="env 先形成默认，`--health-port` 可覆盖；空值用内置端口，`0` 关闭，合法范围 0..65535",
            state="设置 `/healthz` listener 端口并把实际 listening port 投射到 session/health state",
            failure="非法 env/CLI 数值在启动时明确失败；listen 冲突不证明 runner registration 失败但会失去健康入口",
            impact="影响编排器 readiness/alerting，不改变 Agent 任务本身的完成状态",
            document="runtime-supervision-and-processes.md",
            functions=("Igy", "v_y"),
            callsites=2,
            access_modes=("read",),
        ),
        "SELF_HOSTED_RUNNER_DRAIN_WAIT_MS": reviewed_contract(
            owner="self-hosted runner drain budget `v_y -> bKc/A_y`",
            reader="v_y/bKc",
            line=636998,
            fallback="env 作为毫秒输入；`--drain-wait-sec`/deprecated bg alias 校验后写回毫秒并覆盖，默认 0",
            state="SIGTERM/SIGINT 后为每个 in-flight foreground turn 与 background result 保留 drain 等待，再进入 child SIGTERM",
            failure="非法值或超过 86400 秒拒绝启动；等待耗尽只推进终止，不回滚已完成工具/远端副作用",
            impact="控制 shutdown 是否给当前工作收尾时间，也增加 supervisor 必须提供的停止预算",
            document="runtime-supervision-and-processes.md",
            functions=("bKc", "v_y"),
            callsites=2,
            access_modes=("read", "write"),
        ),
        "SELF_HOSTED_RUNNER_DRAIN_GRACE_MS": reviewed_contract(
            owner="self-hosted runner warm-drain argv compiler `v_y`",
            reader="v_y",
            line=637055,
            fallback="只由既有 env 或 `--drain-grace-sec` 写入；CLI 值 clamp 到 0..604800 秒后转毫秒，0 表示不再轮询",
            state="active sessions 清空后决定立即退出，还是在 locked account queue 上再保温轮询一段时间",
            failure="非法 CLI 值拒绝；后续动态 reader 不可用值按 0 处理，timer 不保证新任务一定到达",
            impact="在快速缩容与减少冷启动之间取舍，不延长单个 task deadline",
            document="runtime-supervision-and-processes.md",
            functions=("v_y",),
            callsites=1,
            access_modes=("write",),
        ),
        "SELF_HOSTED_RUNNER_IDLE_SHUTDOWN_MS": reviewed_contract(
            owner="self-hosted runner 未使用退出 argv compiler `v_y`",
            reader="v_y",
            line=637039,
            fallback="`--exit-if-unused-min` 校验 0..10080 分钟后写毫秒；缺失表示 never，0 表示 disable",
            state="设置 runner 从启动起从未获分配时的 autoscaler scale-down deadline",
            failure="非法值拒绝；一旦已有 assignment，后续 session idle 由另一计时器负责",
            impact="避免空闲 runner 长驻资源，同时不把 active session 误当未使用实例",
            document="runtime-supervision-and-processes.md",
            functions=("v_y",),
            callsites=1,
            access_modes=("write",),
        ),
        "SELF_HOSTED_RUNNER_MAX_LIFETIME_MS": reviewed_contract(
            owner="self-hosted runner child wall-clock watchdog compiler `v_y`",
            reader="v_y",
            line=637026,
            fallback="`--kill-session-after-min` 写毫秒；缺失/0 关闭，值限制在 0..10080 分钟",
            state="为每个 session child 建立最大 wall-clock；deadline 时若 turn 正执行可 defer，但仍有额外 hard cap",
            failure="非法值拒绝；终止只结束 child，不证明外部命令或远端提交未发生",
            impact="为 runaway session 提供宿主 backstop，代价是长任务可能在完成前被终止",
            document="runtime-supervision-and-processes.md",
            functions=("v_y",),
            callsites=1,
            access_modes=("write",),
        ),
        "SELF_HOSTED_RUNNER_POST_SESSION_HOOK_TIMEOUT_MS": reviewed_contract(
            owner="self-hosted runner post-session Hook budget compiler `v_y`",
            reader="v_y",
            line=637072,
            fallback="`--post-session-hook-timeout-sec` 要求正数并写毫秒；缺失使用内置 Hook budget",
            state="每次 session end（含 runner shutdown）给 post-session lifecycle hook 独立执行期限",
            failure="超时后 hook 被终止并继续 cleanup；不能假装 hook 的外部持久化已完成",
            impact="让 operator Hook 有界收尾，同时要求 supervisor stop timeout 覆盖完整预算",
            document="runtime-supervision-and-processes.md",
            functions=("v_y",),
            callsites=1,
            access_modes=("write",),
        ),
        "SELF_HOSTED_RUNNER_RETIRE_AT": reviewed_contract(
            owner="self-hosted runner wall-clock retire controller `v_y/g_y`",
            reader="v_y/g_y",
            line=637096,
            fallback="`--retire-at` 要求安全整数 Unix 秒并写 env；缺失表示不主动 retire",
            state="到点后停止认领新 work，等 turn 结束释放/park active sessions，slots 清空后 exit 0",
            failure="过期/非法秒值拒绝；host hard kill 太早仍可能截断 drain、push 或 Hook",
            impact="让有限寿命 VM 在宿主强杀前把 session 变成可 resume 状态",
            document="runtime-supervision-and-processes.md",
            functions=("g_y", "v_y"),
            callsites=2,
            access_modes=("read", "write"),
        ),
        "SELF_HOSTED_RUNNER_SESSION_IDLE_MS": reviewed_contract(
            owner="self-hosted runner per-session idle release compiler `v_y`",
            reader="v_y",
            line=637084,
            fallback="`--release-idle-session-min` 写毫秒；缺失/0 关闭，值上限 10080 分钟",
            state="用户无输入且 turn/permission 状态满足 idle 时释放 slot，让 session 在服务端 park",
            failure="非法值拒绝；release 不等于删除 session，后台结果 grace 与 in-flight turn 另有 gate",
            impact="回收长时间无人操作的 slot，用户下一条消息可由新 runner resume",
            document="runtime-supervision-and-processes.md",
            functions=("v_y",),
            callsites=1,
            access_modes=("write",),
        ),
        "SELF_HOSTED_RUNNER_SESSION_STOP_GRACE_MS": reviewed_contract(
            owner="self-hosted runner child graceful-stop compiler `v_y`",
            reader="v_y",
            line=637062,
            fallback="`--session-stop-grace-sec` 要求正数并写毫秒；缺失用内置 SIGKILL timeout",
            state="session end 后先等待 Claude child clean exit，再 force-kill；post-session Hook 在其后运行",
            failure="超时强杀可能截断 child cleanup，但不会撤销已完成 side effects",
            impact="决定结束 session 时给 transcript/进程清理多少时间，也进入总 shutdown budget",
            document="runtime-supervision-and-processes.md",
            functions=("v_y",),
            callsites=1,
            access_modes=("write",),
        ),
        "SELF_HOSTED_RUNNER_STARTUP_TIMEOUT_MS": reviewed_contract(
            owner="self-hosted runner child-init deadline `v_y/t_y`",
            reader="v_y/t_y",
            line=637090,
            fallback="`--startup-timeout-min` 写毫秒；默认 15 分钟，0 关闭，最大 10080 分钟",
            state="从 child spawn 到 `system:init` 建 deadline，覆盖 resume hydration、MCP connect 与无 pending input 卡住",
            failure="到期释放 slot；init 已完成后改由 session-idle controller 管理",
            impact="防止启动阶段永久占槽，但过短值会误杀慢 hydration/MCP 环境",
            document="runtime-supervision-and-processes.md",
            functions=("t_y", "v_y"),
            callsites=2,
            access_modes=("read", "write"),
        ),
        "SELF_HOSTED_RUNNER_SIGKILL_TIMEOUT_MS": reviewed_contract(
            owner="self-hosted runner deprecated-setting fail-fast `dw0`",
            reader="dw0",
            line=637326,
            fallback="没有 fallback；只要变量存在就拒绝，要求改用 `SELF_HOSTED_RUNNER_SESSION_STOP_GRACE_MS`",
            state="打印 fatal rename diagnostic、flush log 后 exit 1，不启动 runner loop",
            failure="这是显式迁移失败而非 timeout 生效；旧值不会被静默解释",
            impact="避免 operator 误以为旧变量仍控制 force-kill 期限",
            document="runtime-supervision-and-processes.md",
            functions=("dw0",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_RUNNER_ACTIVITY_FD": reviewed_contract(
            owner="RemoteIO runner activity side-channel constructor",
            reader="RemoteIO.constructor",
            line=596921,
            fallback="缺失/非法/<=2 不启用；只接受可 `fstat` 的 FIFO/socket fd，写错后降级 stdout",
            state="为 self-hosted parent 提供 child activity/awaiting-action 侧信号，不复用 SDK stdout 内容流",
            failure="fd 不是 pipe/socket 或写错误会清除 side channel并继续；不能用缺 signal 证明 child idle",
            impact="改善 runner 对 turn/activity 的 drain 与健康判断，不暴露为模型输入",
            document="runtime-supervision-and-processes.md",
            functions=("constructor",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_RUNNER_FETCH_DEPTH": reviewed_contract(
            owner="BYOC runner Git fetch-depth parser `ABf`",
            reader="ABf",
            line=327070,
            fallback="缺失用内置 depth；`full`/`0` 变 full history；正整数成为 `--depth`；非法值告警并回默认",
            state="改变 checkout/fetch 获取的 Git 历史深度，不改变目标 ref 与 access validation",
            failure="非法值不会中断任务而是显式 fallback；shallow history 可能缺其他分支/祖先",
            impact="在启动 I/O 与历史可用性之间取舍，影响后续 Git 分析范围",
            document="remote-routines-runner-and-notifications.md",
            functions=("ABf",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_RUNNER_SKIP_GIT_VERIFY": reviewed_contract(
            owner="self-hosted checkout Hook postcondition `Qhy`",
            reader="Qhy",
            line=633296,
            fallback="只有精确字符串 `1` 跳过；默认要求 Hook 创建目录且含 `.git`",
            state="允许 non-Git SCM checkout 通过，或保留默认 Git repository postcondition",
            failure="默认缺 `.git` 即使 Hook exit 0 也判失败；开启后 CLI 不再证明 checkout 是 Git repo",
            impact="支持 non-Git 工作区，但 operator 自己承担后续 Git 工具不可用风险",
            document="remote-routines-runner-and-notifications.md",
            functions=("Qhy",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_RUNNER_DISABLE_AWAITING_ACTION_OVERRIDE": reviewed_contract(
            owner="self-hosted child activity classifier `gr`",
            reader="gr",
            line=635881,
            fallback="默认允许在 turn end 仍有 prompt/blocked state 时投射 `awaiting-action`；truthy 环境关闭该 override",
            state="改变 runner activity side-channel 的终态标签，不改变 permission/dialog 本身",
            failure="关闭后可能把等待用户的 child 报为 deferred turn end；不会自动批准或取消 prompt",
            impact="影响 autoscaler/health 对 session 是否可释放的观察，需与真实 task state 联读",
            document="runtime-supervision-and-processes.md",
            functions=("gr",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_PTY_HOST_EXEC": reviewed_contract(
            owner="PTY host exec handoff `A_T`",
            reader="A_T",
            line=420733,
            fallback="只有精确 `1` 表示当前 PTY host 将 exec child；读取后立即从环境删除，默认 false",
            state="标记一次 supervisor-to-PTY exec handoff，并触发 token file 清理/继承收缩",
            failure="变量只描述当前 handoff，不证明 `execve` 成功；bad argv/socket auth 仍可提前失败",
            impact="避免内部 handoff marker 泄漏给普通 child，同时影响凭据文件清理时机",
            document="runtime-supervision-and-processes.md",
            functions=("A_T",),
            callsites=2,
            access_modes=("delete", "read"),
        ),
        "CLAUDE_PTY_RECORD": reviewed_contract(
            owner="PTY host ring recorder `A_T -> R_T`",
            reader="A_T",
            line=420755,
            fallback="缺失使用普通 ring；值交给 recorder parser，并结合 cols/rows 决定记录形态",
            state="启用/配置 PTY byte recording，供 attach/replay 与诊断消费，不改变 child command",
            failure="非法/不可用配置由 recorder 降级；记录缺失不证明 PTY 没输出",
            impact="提高后台 terminal 可追溯性，同时增加本地字节留存和隐私成本",
            document="runtime-supervision-and-processes.md",
            functions=("A_T",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_FORCE_SESSION_PERSISTENCE": reviewed_contract(
            owner="ambient child-session persistence-suppression gate `LJt`",
            reader="LJt",
            line=76522,
            fallback="truthy 时 `LJt()` 立即返回 false；否则只有 ambient `CLAUDE_CODE_CHILD_SESSION`、处于 nested-session lane、又不是显式 team agent 时才抑制；显式 disable/skip-history 仍由更外层 gate 决定",
            state="只移除 `nested_marker` 这一条 suppression cause，使 transcript writer、prompt history 和 live-session registry 可以继续各自的普通持久化判断",
            failure="force 不覆盖 `--no-session-persistence` 或 `CLAUDE_CODE_SKIP_PROMPT_HISTORY`，也不保证 append/flush/registry write 成功；它更不恢复此前未保存的消息",
            impact="让 tmux 等宿主环境里继承 child marker 的新会话仍可被 `/resume` 找到，代价是增加本地 transcript/history 留存",
            document="sessions-checkpoints-memory.md",
            functions=("LJt",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_RESUME_FROM_SESSION": reviewed_contract(
            owner="URL/SDK 空恢复的 Sessions API backfill `NQg`",
            reader="NQg",
            line=602993,
            fallback="只在已进入 URL/`--sdk-url` resume、常规反序列化没有消息、且 remote-session capability 可用时读取；它不覆盖 CLI 已选定的目标 session ID",
            state="用该 source ID 调 Sessions API `teleportFromSessionsAPI`，反序列化返回 log，并把 backfill messages 放在 SessionStart Hook attachments 之前",
            failure="fetch/鉴权/deserialize 异常只写 `[resume-from] Failed` debug 并继续空 backfill；字符串存在不证明 source 可访问、消息链完整或当前目标会话已恢复",
            impact="让远端/SDK 新 worker 在自身 transcript 为空时继承另一个服务端 session 的消息事实，但不会复活原 worker、socket、工具进程或外部事务",
            document="sessions-checkpoints-memory.md",
            functions=("NQg",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_RESUME_INTERRUPTED_TURN_MAX_AGE_MS": reviewed_contract(
            owner="interrupted-turn age gate `PFf`",
            reader="PFf",
            line=323194,
            fallback="缺失使用内置 maximum age；无效/nonpositive 按实现 fallback，不扩大为无限期恢复",
            state="判断最后中断 turn 是否仍新鲜，决定是否 drop sibling blocks、修复 superseded tool IDs 并继续",
            failure="过期时不自动续跑中断动作；已发生的文件/远端副作用仍需 readback",
            impact="防止陈旧 session 恢复后重复执行旧提议，同时保留近期 crash continuity",
            document="sessions-checkpoints-memory.md",
            functions=("PFf",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_RESUME_PROMPT": reviewed_contract(
            owner="interrupted-turn continuation prompt `HAi`",
            reader="HAi",
            line=323188,
            fallback="env 非空优先；缺失使用内置 continuation 文案，由 resume/worker epoch gate 决定是否注入",
            state="创建 meta user prompt，引导模型先核验新 runner 文件状态再继续，不直接执行历史 tool",
            failure="文案注入不保证模型正确恢复，也不证明先前文件仍存在",
            impact="让迁移到新 runner 的 session 显式重新检查现场，降低错误依赖旧工作区",
            document="sessions-checkpoints-memory.md",
            functions=("HAi",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_RESUME_THRESHOLD_MINUTES": reviewed_contract(
            owner="large/old session resume nudge `yug`",
            reader="yug",
            line=511106,
            fallback="env 优先，缺失默认 70 分钟；还要求 feature gate、未永久 dismiss 与 token threshold 同时命中",
            state="只改变是否显示 full resume 与 summary resume 选择，不自动 compact 或改 transcript",
            failure="未达 age/token 任一条件不显示；估算值不等于真实 API token charge",
            impact="避免用户无提示地把陈旧大 session 整体续入高成本上下文",
            document="sessions-checkpoints-memory.md",
            functions=("yug",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_RESUME_TOKEN_THRESHOLD": reviewed_contract(
            owner="large/old session resume nudge `yug`",
            reader="yug",
            line=511106,
            fallback="env 优先，缺失默认 100000 estimated tokens；age threshold 与 feature gate 仍先后约束",
            state="与 session age 共同决定是否建议 resume from summary",
            failure="阈值只控制 UI nudge，不改变 context window、compact 成功或 usage bill",
            impact="让大 session 的恢复成本在继续前可见，而非静默吞掉使用额度",
            document="sessions-checkpoints-memory.md",
            functions=("yug",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_SYNC_SESSION_REFS": reviewed_contract(
            owner="remote session-ref eligibility `Nsr/oNt`",
            reader="Nsr",
            line=233173,
            fallback="要求 env gate 且能解析当前 remote session ID；普通 local session 返回 false",
            state="允许 plugin/skill/session sync consumer 把引用写到对应 `/v1/code/sessions/<id>/worker` 路径",
            failure="缺 session ID 或 gate off 不同步；HTTP/远端保存失败不会伪成本地 session 失败",
            impact="连接远端 worker 与本地扩展状态，但不会上传完整 transcript 之外的未声明数据",
            document="tui-ide-remote-cloud.md",
            functions=("Nsr",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_TRANSCRIPT_LOCAL_GC": reviewed_contract(
            owner="remote hydration 后的 local transcript physical-compaction gate `UYg -> Lfl`",
            reader="UYg",
            line=596741,
            fallback="tri-state env 通过 `??` 高于 `tengu_transcript_local_gc`，两者缺失时 false；值只在 SDK/URL resume hydration 前写入 transcript store",
            state="允许 CCR delta hydration 在本地文件超过阈值时排队 compact，并允许 append 累积到 backstop 后重写当前 transcript，清除可丢弃/被替代的物理记录而保留可重建逻辑链",
            failure="关闭时仍照常 append/hydrate，只是不触发这些本地压实；compact write/replace 失败保留原文件并进入 writer diagnostic，不删除远端事件，也不按年龄删除其他 session 文件",
            impact="限制长时间 remote/SDK 会话的单文件膨胀和重复事件，但物理 JSONL 不再等同完整事件审计；逻辑 resume 仍依赖压实后保留的链与 metadata",
            document="sessions-checkpoints-memory.md",
            functions=("UYg",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING": reviewed_contract(
            owner="noninteractive SDK file-history gate `ciS`",
            reader="ciS",
            line=194646,
            fallback="interactive 使用普通 file-checkpoint setting；noninteractive/SDK 只有显式 env true 才启用",
            state="允许受管 Edit/Write 前建立 file checkpoint，供 rewind/diff 恢复",
            failure="未启用或路径不受管时没有 snapshot；checkpoint 不覆盖 Bash、数据库、Git push 或远端写",
            impact="给 SDK host 增加本地文件回退能力，同时增加磁盘写入",
            document="sessions-checkpoints-memory.md",
            functions=("ciS",),
            callsites=1,
            access_modes=("read",),
        ),
        "TEST_ENABLE_SESSION_PERSISTENCE": reviewed_contract(
            owner="session persistence test override `tZn`",
            reader="tZn",
            line=400587,
            fallback="只作为测试/受控运行 override；普通产品 gate 与 nested-session marker 优先保护真实路径",
            state="在测试环境显式开启 transcript/session persistence 分支，便于验证 resume 合同",
            failure="测试 override 不证明生产默认启用，也不能替代实际 fs write 检查",
            impact="只影响测试可达性；误用于生产会扩大本地 transcript 留存",
            document="sessions-checkpoints-memory.md",
            functions=("tZn",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_SESSION_ID": reviewed_contract(
            owner="session identity setter/remote ref resolver `hVn/oNt`",
            reader="hVn/oNt",
            line=233162,
            fallback="受控 host 可预置；session 初始化最终写当前 `Kt()`，已有 env 时同步更新而非永久沿用旧 ID",
            state="把 session identity 用于 transcript、remote worker path 与 correlation；初始化时保持当前 session 一致",
            failure="字符串存在不证明 remote ID 合法或 transcript 可读；错误复用可能导致关联错位但不改变外部 owner",
            impact="决定日志、resume 与远端引用如何关联同一 session，属于身份元数据而非凭据",
            document="sessions-checkpoints-memory.md",
            functions=("hVn", "oNt"),
            callsites=3,
            access_modes=("read", "write"),
        ),
        "CLAUDE_CODE_SESSION_NAME": reviewed_contract(
            owner="session display-name generator `_Y_`",
            reader="_Y_",
            line=76835,
            fallback="显式 env name 作为候选；缺失按 prompt/自动命名；nested/disabled persistence 等 gate 可跳过注册",
            state="写入 session registry/display metadata，并处理同机 live-name collision，不改变 session ID",
            failure="冲突或 registry 不可用会保留/后缀化名称；名称不构成全局唯一 identity",
            impact="影响 `/resume`、Agent View 与 cross-session 寻址的可读标签",
            document="sessions-checkpoints-memory.md",
            functions=("_Y_",),
            callsites=2,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_BRIDGE_SESSION_ID": reviewed_contract(
            owner="Remote Control bridge handle setter `nzn`",
            reader="nzn",
            line=242460,
            fallback="只由 bridge lifecycle 写入，teardown/retire 时删除；普通 local session 不设置",
            state="绑定当前 REPL/SDK bridge session identity，用于 metadata、URL 与 teardown owner",
            failure="handle retired 或 transport failed 时清空；变量存在不证明 bridge connected/active",
            impact="让 Remote Control 与本地 session 正确关联，并避免旧 bridge ID 继承到后续进程",
            document="tui-ide-remote-cloud.md",
            functions=("nzn",),
            callsites=2,
            access_modes=("delete", "write"),
        ),
        "CLAUDE_CODE_REMOTE_SESSION_ORIGIN": reviewed_contract(
            owner="review-origin narrow bypass predicate `h4o`",
            reader="h4o",
            line=71585,
            fallback="只有精确字符串 `review` 返回 true；缺失和任意其他 token 都返回 false，没有通用 origin enum parser",
            state="review-origin 时不把 fd 注入的 OAuth/session-ingress token 复制到 well-known disk path，并允许 server-authored dynamic workflow carrier 越过普通 `allow_workflows` org gate；managed `disableWorkflows` 仍先阻断",
            failure="它不验证 session 真由 review 创建，也不改变 session ID；伪造 env 会改变这两个本地分支，后续 token、script、capability 和执行错误仍分别生效",
            impact="review worker 减少敏感 token 落盘，并能消费服务端携带的 deterministic workflow；这不是额外本地用户脚本权限，也不代表 workflow 已执行成功",
            document="tui-ide-remote-cloud.md",
            functions=("h4o",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_SUPPRESS_SESSION_ATTRIBUTION": reviewed_contract(
            owner="commit/PR session attribution resolver `AZa`",
            reader="AZa",
            line=330908,
            fallback="truthy env 最高优先并返回 null；否则再尊重 settings `attribution.sessionUrl=false` 与 remote/bridge validity",
            state="控制 commit trailer/PR body 是否附 Claude session URL，不改变 Git commit 内容之外的 session state",
            failure="invalid/missing remote session URL 也会省略；抑制 attribution 不删除已发布的历史链接",
            impact="降低 commit/PR 暴露 session linkage 的隐私面，但减少协作追溯入口",
            document="tui-ide-remote-cloud.md",
            functions=("AZa",),
            callsites=1,
            access_modes=("read",),
        ),
        "API_FORCE_IDLE_TIMEOUT": reviewed_contract(
            owner="shared fetch/proxy options compiler `mg`",
            reader="mg",
            line=58334,
            fallback="Anthropic API 且有 body watchdog 时默认关闭 undici idle timeout；env true 强制保留默认 timeout，显式 false 可关闭",
            state="决定 request fetch options 是否写 `timeout:false`，与 byte/body watchdog 分工",
            failure="只改客户端 idle timeout owner；proxy、AbortSignal 和 server deadline 仍可独立终止",
            impact="可避免双重 timeout，也可用于诊断底层 transport timeout 行为",
            document="network-proxy-ca-and-mtls.md",
            functions=("mg",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_BYTE_STREAM_IDLE_TIMEOUT_MS": reviewed_contract(
            owner="byte-level response watchdog deadline `S1S`",
            reader="S1S",
            line=230883,
            fallback="正数 env 最高；否则 legacy stream timeout 显式值阻止 flag override；最后按 provider fallback/feature，统一 clamp 10s..30m",
            state="每收到一个 response byte 重置 deadline，超时 error/cancel stream 并携带 bytes/TTFB/sleep evidence",
            failure="非法/非正值不采用；watchdog firing 后可能 retry、partial finalize 或 fail，不回滚已交付 block",
            impact="限制无字节长挂，并把 sleep/stall 与普通 API error 分开诊断",
            document="resilience-and-recovery.md",
            functions=("S1S",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_STREAM_IDLE_TIMEOUT_MS": reviewed_contract(
            owner="legacy event/stream idle budget `vNa/S1S`",
            reader="vNa/S1S",
            line=230879,
            fallback="正数至少取 300000ms，并成为 legacy timeout；同时阻止 byte-watchdog feature default 覆盖",
            state="控制 SSE event stall 检测和 byte watchdog 上层 budget，二者取更严格有效值",
            failure="无效值回默认；过短仍受最小值保护，不能取消 request total timeout",
            impact="控制长 thinking/慢流何时被视作 stall，影响 retry 与 partial-result 用户体验",
            document="resilience-and-recovery.md",
            functions=("S1S", "vNa"),
            callsites=2,
            access_modes=("read",),
        ),
        "CLAUDE_ENABLE_STREAM_WATCHDOG": reviewed_contract(
            owner="Agent stream event watchdog gate `vAm`",
            reader="vAm",
            line=409773,
            fallback="缺失默认 true；显式 false 使 event watchdog deadline 变 Infinity，但 byte watchdog 仍由独立 gate决定",
            state="启停 message event-level stall timer，影响 streaming retry/finalize/fallback 分类",
            failure="关闭后连接仍可由 SDK timeout/network error 结束；不会保证无限等待成功",
            impact="用于自托管/慢链路调优，但关闭可能让无事件 stream 长时间占用 session",
            document="resilience-and-recovery.md",
            functions=("vAm",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_DISABLE_NONSTREAMING_FALLBACK": reviewed_contract(
            owner="stream failure fallback selector `vAm`",
            reader="vAm",
            line=410022,
            fallback="truthy env 硬禁用；否则还受 watchdog-specific flag、remote mode 与 feature gates 影响",
            state="stream error 时选择抛出/保留 partial，还是启动 non-streaming Messages fallback",
            failure="禁用不会阻止已发生 streaming partial；fallback 开启也不保证第二次 request 成功",
            impact="避免 provider/host 不接受 non-stream path 时重复请求，也可能减少自动恢复能力",
            document="resilience-and-recovery.md",
            functions=("vAm",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_ENABLE_BYTE_WATCHDOG": reviewed_contract(
            owner="response body byte-watchdog master gate `V7p`",
            reader="V7p",
            line=230986,
            fallback="显式 false 优先关闭，显式 true 开启，缺失使用 `tengu_stream_watchdog_default_on` true fallback",
            state="允许 first-party/gateway/Anthropic-on-AWS 等合格 content-type response 包装为 byte-aware ReadableStream",
            failure="不合格 provider/content-type 或无 body 不包装；关闭后仍有 event/SDK timeout",
            impact="降低无字节挂死风险，但会在 slow response 上增加 timeout/retry 分支",
            document="resilience-and-recovery.md",
            functions=("V7p",),
            callsites=2,
            access_modes=("read",),
        ),
        "CLAUDE_ENABLE_BYTE_WATCHDOG_BEDROCK": reviewed_contract(
            owner="Bedrock eventstream byte-watchdog gate `K7p`",
            reader="K7p",
            line=230994,
            fallback="默认 false；truthy env 才允许 Bedrock `vnd.amazon.eventstream` body 进入 byte watchdog",
            state="把 Bedrock response 加入同一 byte deadline/cancel/diagnostic path",
            failure="content-type 不符仍由 Bedrock guard 处理；开启不保证 AWS transport 可取消",
            impact="为 Bedrock 慢/挂 stream 增加客户端保护，但需按真实区域/网络调参",
            document="resilience-and-recovery.md",
            functions=("K7p",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_RETRY_WATCHDOG": reviewed_contract(
            owner="API retry policy expansion gate `EZe`",
            reader="EZe",
            line=215555,
            fallback="默认 false 使用普通 retry caps；true 扩大 max retry 与 429/529/background/custom-provider 的可重试范围",
            state="改变 request attempt budget、retry-after 上限和部分 fallback/drop 决策，不增加 Agent `turnCount`",
            failure="仍有总 attempt/backoff 与 status classifier；retry 无法回滚已到达服务端的未知请求",
            impact="提高 self-hosted/remote 对暂时 overload 的韧性，同时增加延迟和重复请求风险",
            document="resilience-and-recovery.md",
            functions=("EZe",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_STALL_TIMEOUT_MS_FOR_TESTING": reviewed_contract(
            owner="update/download stream stall test deadline `UfT`",
            reader="UfT",
            line=412446,
            fallback="Number(value) truthy 时覆盖，否则使用内置 download stall timeout；仅面向测试控制",
            state="刷新下载 pipeline stall timer，每个 chunk/drain 续期，deadline abort 当前下载 attempt",
            failure="0/NaN 回默认；abort 后 update retry/cleanup 另行处理，不证明安装回滚",
            impact="允许确定性测试慢/卡下载，生产误设会改变 updater 容忍时间",
            document="install-update-doctor-lifecycle.md",
            functions=("UfT",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_AUTH_FAIL_EXIT_MS": reviewed_contract(
            owner="remote OAuth zombie-session breaker `CMr`",
            reader="CMr",
            line=87020,
            fallback="remote child 默认 10 分钟；显式 nonpositive 关闭 exit；恢复成功重置失败起点",
            state="连续 unrecovered 401 超阈值后判 `exit`，让 runner recycle session 获取新 credential",
            failure="只在 remote child 生效；exit 前既有副作用不回滚，服务端 token 恢复仍是 Boundary",
            impact="避免失效 credential 让 remote session 永久僵死，代价是进程会被主动回收",
            document="auth-account-and-subscription-lifecycle.md",
            functions=("CMr",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_OAUTH_401_WAIT_MS": reviewed_contract(
            owner="OAuth 401 external-token rotation poller `sob/VEd`",
            reader="sob",
            line=87015,
            fallback="显式值优先；remote session 默认 60s，普通 local 默认 0",
            state="在无本地 refresh owner 时轮询 env/token source，等待不同于 failed token 的新 access token",
            failure="deadline 后未变化返回 false，并可能进入 remote zombie-exit policy；不重用失败 token",
            impact="给宿主注入/轮换 token 留时间，减少瞬时 401 中断",
            document="auth-account-and-subscription-lifecycle.md",
            functions=("sob",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_AWS_CHAIN_RESOLVE_TIMEOUT_MS": reviewed_contract(
            owner="AWS default credential-chain timeout wrapper `KJs`",
            reader="KJs",
            line=86730,
            fallback="显式毫秒值优先，缺失默认 60000ms",
            state="用 Promise race 包住 AWS provider chain，超时生成 `CredentialsProviderError` 并清 timer",
            failure="timeout 后底层 promise rejection 被消费但无法强制取消所有 provider I/O；后续 auth fallback 独立",
            impact="防止 metadata/profile credential discovery 无限阻塞 Bedrock/Anthropic-on-AWS 请求",
            document="models-auth-providers-request.md",
            functions=("KJs",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_API_KEY_HELPER_TTL_MS": reviewed_contract(
            owner="apiKeyHelper cache TTL resolver `BEd/OMr`",
            reader="BEd",
            line=86574,
            fallback="非负 env 优先；负/非法打印错误并回内置 TTL",
            state="控制 helper 输出在进程内 cache 的有效期；过期重新执行 helper",
            failure="helper 执行/输出错误返回 null；TTL 只缓存值，不证明 credential 仍被上游接受",
            impact="在凭据轮换及时性与 helper 启动成本之间取舍",
            document="models-auth-providers-request.md",
            functions=("BEd",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_API_BASE_URL": reviewed_contract(
            owner="Files/API base resolver `O1p`",
            reader="O1p",
            line=209221,
            fallback="`ANTHROPIC_BASE_URL` 最高，其次该变量，最后 `https://api.anthropic.com`",
            state="选择 Files/相关 first-party API endpoint；provider/data-residency gate 仍在调用前检查",
            failure="自定义 endpoint 不自动获得 first-party auth/capability；网络/schema failure 保持原错误",
            impact="允许宿主改 API 路由，但可能让 Files/Remote 等能力不可用或进入不同信任域",
            document="models-auth-providers-request.md",
            functions=("O1p",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_DESIGN_OAUTH_CLIENT_ID": reviewed_contract(
            owner="Claude Design OAuth client resolver `RWn`",
            reader="RWn",
            line=300050,
            fallback="env 优先，否则当前 OAuth environment 的 `DESIGN_CLIENT_ID`；全零 placeholder 视为未配置",
            state="选择 Design authorization request/client slot 的 client_id，并随 credential 保存",
            failure="未配置、remote listener 不可达、scope/refresh/expiry 缺失均明确拒绝，不会保存不可用 token",
            impact="决定 `/design-login` 能否启动与凭据归属，不替代用户授权",
            document="claude-design-and-projects.md",
            functions=("RWn",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_LOCAL_OAUTH_API_BASE": reviewed_contract(
            owner="local OAuth endpoint compiler `PPy`",
            reader="PPy",
            line=17140,
            fallback="trim trailing slash；缺失回 `http://localhost:8000`",
            state="派生 local token、API-key、roles 等 OAuth API routes",
            failure="只在 local OAuth environment/相关调用路径消费；endpoint 存在不证明服务启动或 TLS 安全",
            impact="支持本地 OAuth 集成测试，误设可能把 credential flow 路由到错误进程",
            document="auth-account-and-subscription-lifecycle.md",
            functions=("PPy",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_LOCAL_OAUTH_APPS_BASE": reviewed_contract(
            owner="local Claude.ai OAuth origin compiler `PPy`",
            reader="PPy",
            line=17140,
            fallback="trim trailing slash；缺失回 `http://localhost:4000`",
            state="派生 Claude.ai authorize URL/origin，用于 local OAuth browser flow",
            failure="不校验服务可达；browser/redirect/account match 仍独立失败",
            impact="改变本地 authorize 页面和 origin 信任边界，仅应在受控开发环境使用",
            document="auth-account-and-subscription-lifecycle.md",
            functions=("PPy",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_LOCAL_OAUTH_CONSOLE_BASE": reviewed_contract(
            owner="local Console OAuth route compiler `PPy`",
            reader="PPy",
            line=17140,
            fallback="trim trailing slash；缺失回 `http://localhost:3000`",
            state="派生 console authorize/success/manual callback 与 credits return URLs",
            failure="route 构造成功不证明 redirect listener、client registration 或 server response 正确",
            impact="改变 local OAuth 回调与购买/成功页面，配置错误会导致登录无法完成",
            document="auth-account-and-subscription-lifecycle.md",
            functions=("PPy",),
            callsites=1,
            access_modes=("read",),
        ),
        "USE_LOCAL_OAUTH": reviewed_contract(
            owner="Chrome/Remote bridge environment selector `NpT/FpT`",
            reader="NpT/FpT",
            line=410489,
            fallback="local true（或 `LOCAL_BRIDGE`）优先选择 `ws://localhost:8765`；否则 staging，再 production",
            state="选择 bridge WebSocket endpoint并标记 local bridge mode",
            failure="local socket/extension/account auth 仍可失败；明文 ws 只适合 loopback 开发",
            impact="把 Chrome/bridge 流量切到本机开发服务，不影响普通 Messages provider",
            document="tui-ide-remote-cloud.md",
            functions=("FpT", "NpT"),
            callsites=2,
            access_modes=("read",),
        ),
        "USE_STAGING_OAUTH": reviewed_contract(
            owner="Chrome/Remote bridge environment selector `NpT`",
            reader="NpT",
            line=410489,
            fallback="local/LOCAL_BRIDGE 优先；其后 truthy staging 选择 staging websocket；否则 production",
            state="把 bridge transport 指向 staging claudeusercontent endpoint",
            failure="不改变当前 OAuth credential/account；环境不匹配可导致 authentication error",
            impact="支持 staging 验证，同时明确与 production bridge 隔离",
            document="tui-ide-remote-cloud.md",
            functions=("NpT",),
            callsites=1,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_SKIP_FOUNDRY_AUTH": reviewed_contract(
            owner="Foundry provider auth selector `hme/T7i`",
            reader="hme",
            line=230757,
            fallback="Foundry auth token/API key 优先；仅二者都缺失且 env truthy 时用 `skip-foundry-auth` provider，否则走 Azure credential",
            state="构造 Foundry client 的 `azureADTokenProvider/defaultHeaders`，显式跳过本地 Azure discovery",
            failure="skip 不证明 upstream 允许匿名；request 仍可能 401，diagnostic 会显示 auth skipped",
            impact="适配由外部 gateway/header 管 auth 的 Foundry 环境，错误启用会失去身份",
            document="models-auth-providers-request.md",
            functions=("T7i", "hme"),
            callsites=2,
            access_modes=("read",),
        ),
        "CLAUDE_CODE_DISABLE_BEDROCK_CONTENT_TYPE_GUARD": reviewed_contract(
            owner="Bedrock streaming response content-type guard `w1S`",
            reader="w1S",
            line=231031,
            fallback="默认 guard 开启；truthy env 才跳过对成功 response 的 `vnd.amazon.eventstream` 检查",
            state="异常 content-type 时提前 cancel body并抛 `BedrockUnexpectedContentType`，避免把代理 HTML/JSON 当 eventstream",
            failure="关闭 guard 后 parser 仍可能失败，但诊断更晚更模糊；不改变 HTTP status",
            impact="通常提升代理/网关错误可诊断性；仅在确定非标准兼容层时才应关闭",
            document="models-auth-providers-request.md",
            functions=("<top-level>",),
            callsites=1,
            access_modes=("read",),
        ),
        "ANTHROPIC_SMALL_FAST_MODEL_AWS_REGION": reviewed_contract(
            owner="small/fast model AWS region resolver `Zfi/pIi`",
            reader="Zfi/pIi",
            line=230841,
            fallback="非空值经 region normalizer优先；否则继承主 AWS/Bedrock region",
            state="为 small-fast/Haiku Bedrock side query 选择独立 region 和 runtime endpoint",
            failure="region 无 deployment/credential/network 时 side query 失败并按所属功能 fallback；不改主 session model region",
            impact="可把低延迟辅助请求路由到不同区域，但引入数据驻留与部署一致性要求",
            document="models-auth-providers-request.md",
            functions=("Zfi", "pIi"),
            callsites=2,
            access_modes=("read",),
        ),
        "ANTHROPIC_CUSTOM_MODEL_OPTION_NAME": reviewed_contract(
            owner="model picker custom-option renderer `N6b`",
            reader="N6b",
            line=157992,
            fallback="custom model ID 必须先存在且未在 catalog；name 缺失时直接显示 model ID",
            state="只改变 model picker 中 custom entry 的 label，不改 request body model ID",
            failure="没有 custom model option 时完全不消费；显示名称不证明 provider 支持该 ID",
            impact="让企业自定义 model ID 以友好名称展示，避免混淆 wire identity",
            document="models-auth-providers-request.md",
            functions=("N6b",),
            callsites=1,
            access_modes=("read",),
        ),
        "ANTHROPIC_CUSTOM_MODEL_OPTION_DESCRIPTION": reviewed_contract(
            owner="model picker custom-option renderer `N6b`",
            reader="N6b",
            line=157992,
            fallback="custom model ID 有效时使用；缺失回 `Custom model (<id>)`",
            state="写入 picker entry 的辅助描述，不改变 capability/model validation",
            failure="描述可与实际 capability 漂移；最终 provider acceptance、context window 与 pricing 仍需独立 catalog/运行证据",
            impact="帮助用户理解自定义模型选择，但不能作为技术能力声明",
            document="models-auth-providers-request.md",
            functions=("N6b",),
            callsites=1,
            access_modes=("read",),
        ),
    }
)


FEATURE_MANUAL_CONTRACTS.update(
    {
        "tengu_artifact_hljs_highlight": reviewed_contract(
            owner="Artifact HTML publish enrichment gate `kef -> Hnf/r$a`",
            reader="kef",
            line=242530,
            fallback="boolean fallback 为 true；仍要求 publish caller 请求 highlight runtime，且 HTML 扫描到受支持的 `language-*` code block",
            state="安全校验 vendored highlight.js 与 init script 后，把两段 runtime 注入发布页；单块最多 50,000 字符、整页高亮预算 250,000 字符、注入块小于 4 MiB",
            failure="flag off 或未检出代码只是不注入；bundle unreadable、unsafe、overspan 或 block 无法可靠剥离时记录 `artifact_publish` cause 并保留无高亮页面，不把失败伪装成代码内容错误",
            impact="改变已发布 Artifact 的代码着色、脚本体积和浏览器执行成本，不改变模型上下文、源代码文本或 Artifact 写权限",
            document="workflow-artifact-design.md",
            functions=("kef",),
            callsites=1,
        ),
        "tengu_artifact_mermaid_diagrams": reviewed_contract(
            owner="Artifact Mermaid fence renderer/runtime gate `fNt -> Vrf/Hnf`",
            reader="fNt",
            line=242638,
            fallback="boolean fallback 为 true；只认 fenced code 的首个语言 token `mermaid`，runtime 注入还要求 caller 开启 diagram lane 且页面实际含 diagram",
            state="把合格 fence 变成 `<pre class=\"mermaid\">`，并按页面主题注入 strict-security Mermaid runtime；主题变化会重新渲染但不会改源 diagram text",
            failure="关闭时新页面不获得 diagram renderer；已有 composed PR review 若携带 diagram runtime，republish 会明确拒绝而不是悄悄丢图；bundle load/validation 失败也会保留 named publish error",
            impact="决定 Artifact 中图表是可渲染图还是普通代码，并影响 republish 连续性、页面脚本体积与浏览器执行面",
            document="workflow-artifact-design.md",
            functions=("fNt",),
            callsites=1,
        ),
        "tengu_flint_harbor_share": reviewed_contract(
            owner="team-onboarding share tool eligibility `XWr`",
            reader="XWr",
            line=315058,
            fallback="boolean fallback false；还要求非 excluded auth surface、org policy `allow_team_onboarding` 与账号/host capability `GA()` 同时通过",
            state="注册可写的 onboarding-share tool，并在 `/team-onboarding` prompt 中加入先 create/check、用户答完再 update 同一 short code 的双调用流程",
            failure="每次 create/update/delete/list 都重新检查 org policy；HTTP、auth 或 payload failure 返回 unavailable/error，关闭 flag 时仍可本地生成 `ONBOARDING.md`，只是没有 share URL",
            impact="把本地入门文档变成组织可分享链接并产生远端写入；delete 被标为 destructive，flag 本身不绕过工具 permission",
            document="complex-slash-command-lifecycles.md",
            functions=("XWr",),
            callsites=1,
        ),
        "tengu_pr_footer_surface_suffix": reviewed_contract(
            owner="default PR attribution formatter `Mjf`",
            reader="Mjf",
            line=330904,
            fallback="boolean fallback false；只有 `CLAUDE_CODE_ENTRYPOINT` 能映射为 Desktop、Mobile、Cowork、Claude Tag 或 GitHub Actions 时才有 suffix",
            state="把默认 `Generated with Claude Code` footer 扩展为 `... via <surface>`；自定义 `attribution.pr` 或禁用 attribution 的 setting 仍可覆盖整个默认值",
            failure="未知 entrypoint 原样返回旧 footer；它不验证 PR 实际创建渠道，也不影响 GitHub API/`gh` command 是否成功",
            impact="提高 PR 来源可见性，同时把使用 surface 写入长期 GitHub 文本；不增加 session URL，后者由独立 attribution gate 控制",
            document="settings-reference.md",
            functions=("Mjf",),
            callsites=1,
        ),
        "tengu_fleetview_pr_batch": reviewed_contract(
            owner="Agent View PR status poller batch selector",
            reader="Agent View poller",
            line=578075,
            fallback="boolean fallback true；只在当前可见 jobs 含未 CLOSED/MERGED PR 且 adaptive poll interval 到期时读取",
            state="true 先用 `qcp` 批量查询所有 PR，再只对 batch 标记 unbatched 的 URL 逐个 fallback；false 对每个 URL 直接调用单项 `I_a`，最终写入同一 PR status map",
            failure="batch 失败/限流把该次结果记为 null 并触发 60 秒 backoff；state reducer 不用 null 覆盖既有 last-known status，因此旧值可能继续显示；GitHub 新鲜度仍是 Boundary",
            impact="减少 Agent View 多 PR 刷新的进程/API 次数和 rate-limit 压力，代价是 batch 故障时整组进入退避并暂时保留旧状态",
            document="runtime-supervision-and-processes.md",
            functions=("<top-level>",),
            callsites=1,
        ),
        "tengu_fleet_past_sessions": reviewed_contract(
            owner="Agent View past-session eligibility `jxn -> SNc`",
            reader="jxn",
            line=89152,
            fallback="`CLAUDE_CODE_FLEET_PAST_SESSIONS === true` 高于 boolean flag fallback false；还要求非 remote/unsupported host 的 `vNc()`",
            state="允许 Fleet View 枚举同项目 transcript（受 200 条等边界约束），并让无显式 ID 的裸 `claude --resume` 直接进入 Agent View，而不是普通 resume picker",
            failure="枚举失败记录 `[fleetview] past-session enumeration failed` 并返回空/现有 live jobs；session file 存在仍不证明可合法 resume，实际打开继续走 graph loader",
            impact="把已结束会话与 live/background jobs 放在同一操作面，改善查找与重开，但会增加本地 transcript 扫描和标题/mtime 暴露",
            document="sessions-checkpoints-memory.md",
            functions=("jxn",),
            callsites=1,
        ),
        "tengu_rename_full_session_fork": reviewed_contract(
            owner="automatic `/rename` name generator `cKr`",
            reader="cKr",
            line=362752,
            fallback="boolean fallback false；只有 caller `preferFork` 且 `_Ua()` 证明主请求 cache-safe context 仍在 TTL 约 90% 内、模型未变时使用，失败后回到压平 conversation 的旧生成路径",
            state="为命名启动一个独立一轮 fork，继承完整 session context，禁止全部工具、跳过 transcript/cache write，并要求 JSON title；成功 title 才进入后续 collision/registry write",
            failure="fork abort 返回 null；模型输出无合法 `name`、请求失败或空 title 会 fallback/报无法命名，不会改变原会话消息、工具副作用或 session ID",
            impact="长会话的自动名称可利用更完整上下文，代价是一次额外模型 iteration；命名 fork 无工具权限且不形成可 resume 子会话",
            document="sessions-checkpoints-memory.md",
            functions=("cKr",),
            callsites=1,
        ),
        "tengu_ultraplan_prompt_identifier": reviewed_contract(
            owner="Ultraplan remote system-prompt selector `kYn`",
            reader="kYn",
            line=363882,
            fallback="fallback `simple_plan`；只接受 bundled map 中的 `simple_plan`、`visual_plan`、`three_subagents_with_critique`，任意其他值回落 simple",
            state="选择创建 cloud planning session 时的 system reminder，并同步选择对应 time estimate、dialog pipeline 与 usage blurb；显式 caller promptIdentifier 仍可覆盖此默认",
            failure="非法 rollout 值不会发到远端；远端 session precondition、create/poll/approval/teleport 失败仍由 Ultraplan lifecycle 单独收口",
            impact="在轻量单 Agent 计划、带结构图指导的计划和多 Agent+critique 计划之间改变耗时、token/并发成本与产物深度",
            document="plan-mode-and-human-approval.md",
            functions=("kYn",),
            callsites=1,
        ),
        "tengu_lapis_anchor": reviewed_contract(
            owner="total-token reminder mode resolver `bqS`",
            reader="bqS",
            line=266880,
            fallback="env `CLAUDE_CODE_TOTAL_TOKENS_REMINDER` 高于 setting `totalTokensReminder`，再到 flag fallback `padded-countdown`；每层只接受 off/infinite/fixed/countdown/padded-countdown",
            state="把合法 mode 缓存在 runtime，并决定 system prompt、tool-result batch 与可选 user turn 是否注入 `<total_tokens>`，以及数字来自 Infinite、5,000,000、真实窗口或 task budget",
            failure="非法值回到 padded-countdown；该 reminder 是给模型看的本地提示，不扩展 API context window、不强制停止，也不等同计费 token",
            impact="改变模型感知剩余预算与跨长任务的自我节制，额外占用少量上下文；off 仅移除提示，不关闭 compact/blocking ceiling",
            document="context-governance-and-caching.md",
            functions=("bqS",),
            callsites=1,
        ),
        "tengu_lapis_anchor_budget": reviewed_contract(
            owner="padded-countdown task-budget resolver `SqS`",
            reader="SqS",
            line=266892,
            fallback="正数 finite env 高于正数 setting，再到 flag；任一无效/非正数最终回落 15,000,000 tokens",
            state="只在 `padded-countdown` mode 下设置 task anchor；tracker 用累计 context usage 减去当前 anchor，并保证 displayed used 不倒退",
            failure="极大合法值只会产生宽松提示，不改变硬窗口；估算/rollover 误差也不会改变 API usage accounting 或 compact trigger 的独立预算",
            impact="控制模型看到的长期任务预算尺度，影响何时开始收敛，但不是 maxTurns、价格上限或服务端配额",
            document="context-governance-and-caching.md",
            functions=("SqS",),
            callsites=1,
        ),
        "tengu_lapis_anchor_user_turn": reviewed_contract(
            owner="per-user-turn reminder/reanchor resolver `vqS`",
            reader="vqS",
            line=266904,
            fallback="defined env boolean 高于 defined setting，再到 boolean flag fallback true；与 mode=off 时短路",
            state="true 在每个 regular user prompt 后追加 token block，并让 padded-countdown 在该 turn 重新锚定完整 task budget；false 让预算跨整场 session 累计，仍保留 system/tool-result reminder",
            failure="meta、compact summary、tool result 等非 regular prompt 不触发 reanchor；它不清空历史，也不保证模型遵循提醒",
            impact="决定多轮会话把每条用户任务视为新预算，还是共享一笔递减预算，直接影响长会话行为但不改变真实 context bytes",
            document="context-governance-and-caching.md",
            functions=("vqS",),
            callsites=1,
        ),
        "tengu_moss_anchor": reviewed_contract(
            owner="noninteractive Auto Mode default-fallback gate `PRd`",
            reader="PRd",
            line=94487,
            fallback="boolean fallback false；只在 Auto Mode 未被 disable/circuit breaker 阻断、harbor-willow rollout 开启、且 CLI/frontmatter/settings 都未给出更高优先级 mode 时读取",
            state="让原本只对 interactive 或 IDE-owned session 生效的 auto-default fallback 扩展到其他 noninteractive entrypoint，并标记 `fromAutoFallback=true`",
            failure="false 时 noninteractive session 保持 `default`；true 仍不允许 project/local settings授予 auto，也不越过 deterministic deny/ask、classifier fail-closed、Hook、sandbox 或 OS policy",
            impact="决定无显式 permission mode 的 headless host 是否默认把普通 ask 调用送入 Auto Mode classifier；它不是 bypassPermissions，也不会自动批准任何具体工具",
            document="auto-mode-classifier.md",
            functions=("PRd",),
            callsites=1,
        ),
        "tengu_edit_minimalanchor_jrn": reviewed_contract(
            owner="Edit tool prompt compiler `ziS`",
            reader="ziS",
            line=195722,
            fallback="boolean fallback false；只作用于普通 Edit description，alternate exact-edit lane 使用另一份固定 prompt",
            state="true 把指导从“提供更大 surrounding context”改成“通常只给 1-3 行最小唯一 old_string，额外上下文浪费 token”，同时保留 non-unique 必须补最少上下文或 replace_all 的规则",
            failure="它不改变 Edit schema、read-before-edit gate、exact-match/unique validation 或 write implementation；模型仍可能给出过短/过长 anchor 并收到原有错误",
            impact="降低 Edit 参数 token 与过度复制文件内容的倾向，同时把唯一性修复策略说得更精确；不会放宽文件修改权限",
            document="tools-permissions-hooks.md",
            functions=("ziS",),
            callsites=1,
        ),
        "tengu_alder_compass": reviewed_contract(
            owner="startup tip `powerup-onboarding` relevance predicate",
            reader="isRelevant",
            line=583244,
            fallback="boolean fallback false；还要求 startup count <10 且尚未解锁任何 powerup",
            state="把 `/powerup` 交互教程 tip 加入候选池，priority 3、cooldown 1 session；真正显示还要赢过更高优先级/更久未展示的候选",
            failure="关闭或不相关只隐藏 tip，不禁用 `/powerup`；tip rendering/persistence failure 不影响主会话",
            impact="影响新用户早期发现教学入口，不改变 Agent Loop、工具权限或功能可用性",
            document="onboarding-workspace-trust-and-safe-startup.md",
            functions=("isRelevant",),
            callsites=1,
        ),
        "tengu_cedar_plume": reviewed_contract(
            owner="contextual Claude Design tip relevance predicate",
            reader="isRelevant",
            line=583347,
            fallback="boolean fallback false；还要求 first-party account 且当前 session 的文件/tool signals 被 `G4g` 判为 UI/design context",
            state="把指向 Claude Design 的 contextual tip 加入候选池，priority 1、cooldown 15 sessions，并携带固定 campaign attribution",
            failure="flag off、非 UI context 或非 first-party 只不展示；它不加载 Design tool、不上传项目，也不证明链接可访问",
            impact="在前端/界面任务中提示先做 mockup，属于发现性 UI，而不是 Artifact/Design capability gate",
            document="tui-input-accessibility-media-ide-chrome.md",
            functions=("isRelevant",),
            callsites=1,
        ),
        "tengu_kestrel_arch": reviewed_contract(
            owner="Claude API acquisition tip relevance predicate",
            reader="isRelevant",
            line=583365,
            fallback="string fallback `off`；只有精确 `on`，且 first-party、API acquisition eligible、无已有 primary/custom/env API key、startup count >10 才候选",
            state="允许显示 `/claude-api` onboarding tip，cooldown 15 sessions；不会自动创建 key 或切换当前 credential source",
            failure="任一已有 key/不支持账号/flag 非 on 都静默隐藏；后续 key issuance、billing 与 provider auth 属外部 Boundary",
            impact="只影响成熟用户发现 Claude API 的时机，不改变本 session 的模型路由或认证",
            document="models-auth-providers-request.md",
            functions=("isRelevant",),
            callsites=1,
        ),
        "tengu_maple_rung": reviewed_contract(
            owner="Remote Control next-surface tip relevance predicate",
            reader="isRelevant",
            line=583357,
            fallback="boolean fallback false；还要求 Remote Control 可用、当前已在 bridge、org policy 允许且能确定下一 surface",
            state="最多 3 次、每 15 sessions 把 web 或 mobile 的下一入口加入 tip pool；目标由 `ppc()` 选择并生成对应链接文案",
            failure="无法确定 surface、policy off 或 flag off 只隐藏 tip；它不连接 bridge，也不证明另一设备收到 session",
            impact="帮助已启用 Remote Control 的用户发现第二终端，不改变 session sharing、auth 或 outbound-only 状态",
            document="tui-ide-remote-cloud.md",
            functions=("isRelevant",),
            callsites=1,
        ),
        "tengu_chrome_install_upsell": reviewed_contract(
            owner="Claude in Chrome missing-extension setup eligibility `ROg`",
            reader="ROg",
            line=538506,
            fallback="boolean fallback false，并同时排除已有/禁用 Chrome、noninteractive/remote/SSH/WSL/teleported/unsupported host、managed deny、已 dismiss 与本 session 已结算的 setup",
            state="让 `/chrome` skill 在 extension 缺失时可达；模型真正需要浏览器时通过 requestDialog 启动安装/连接状态机，并把本 session resolution 缓存为继续、跳过或失败",
            failure="managed policy、用户跳过/中断、安装未连上或内部异常都返回明确 continuation guidance；永久 dismiss 写 user state，普通失败不会伪装成 browser tools ready",
            impact="可在任务中插入阻塞安装对话并打开扩展页面；成功后增加对现有 Chrome 会话的交互能力，但 site permission 和 MCP connection 仍独立控制",
            document="tui-input-accessibility-media-ide-chrome.md",
            functions=("ROg",),
            callsites=1,
        ),
        "tengu_cobalt_harbor_notice": reviewed_contract(
            owner="Remote Control auto-default announcement + VS Code gate projection `cCw/uSm`",
            reader="cCw/uSm",
            line=483986,
            fallback="boolean fallback true；VS Code 总会收到该 gate 值，本地 info banner 还要求 bridge auto-on-by-default、Remote Control capability/host/policy 通过且展示次数未达上限",
            state="向 VS Code `experiment_gates` notification 投射同名 boolean，并在终端插入 `Keep working from anywhere` banner；展示后增加 durable seenNotifications count",
            failure="VS Code notification rejection只写 debug；banner gate off/次数耗尽只隐藏文案，既不关闭已经启动的 bridge，也不改变其 inbound/outbound authority",
            impact="解释为什么 session 默认可从 mobile/desktop/web 继续，并提供 `/remote-control` 退出入口；属于告知面，不是连接开关",
            document="tui-ide-remote-cloud.md",
            functions=("cCw", "uSm"),
            callsites=2,
        ),
        "tengu_harbor_willow": reviewed_contract(
            owner="Auto Mode default-launch rollout `HIn -> PRd`",
            reader="HIn",
            line=94552,
            fallback="boolean flag fallback false，与 remote account config `meadow_lantern === true` 做 OR；显式 CLI/frontmatter/mode 与 trusted defaultMode 仍先于 rollout fallback",
            state="在 Auto Mode 未被 settings/circuit breaker 禁用时，让 IDE 读取 trusted defaultMode，并让没有任何显式 mode 的合格 interactive/IDE session 从 `default` 落到 `auto`，标记 `fromAutoFallback`",
            failure="project/local source不能授予 auto；managed disable、circuit breaker、unsupported noninteractive surface 和 classifier fail-closed 仍阻断，flag true 从不等于自动批准某个 tool",
            impact="直接改变新 session 的默认 permission mode，因此影响普通 ask 调用是否进入 Auto Mode classifier；deny/ask rules、Hooks、sandbox 与 OS 权限仍是硬下限",
            document="auto-mode-classifier.md",
            functions=("HIn",),
            callsites=1,
        ),
        "tengu_cobalt_wren": reviewed_contract(
            owner="post-turn summary classifier engine selector `Bcf`",
            reader="Bcf",
            line=270335,
            fallback="boolean fallback false；只在 sinks 本来选中 `llm` 时生效，state-only sinks、无 summary sink 或显式 heuristic 已不需要它",
            state="true 把 summary/headline classification engine 从额外 LLM call 降级为 heuristic；surface detection 与 sink selection 保持不变",
            failure="heuristic 可能丢失细粒度 status/needs-action 语义，但 classifier failure不改变真实 task state；flag off 也不保证 LLM request 一定成功",
            impact="降低 post-turn latency/token/网络调用，代价是 Agent View/Remote Control 摘要质量可能下降；不影响主模型回答",
            document="telemetry.md",
            functions=("Bcf",),
            callsites=1,
        ),
        "tengu_pewter_owl_model": reviewed_contract(
            owner="Pewter Owl tool/Brief model allowlist resolver `qWS -> jcf`",
            reader="qWS",
            line=270373,
            fallback="account config `pewter_owl_model` 的非空字符串最高；否则 flag string fallback empty，empty 表示不加 model restriction",
            state="非空 selector 必须被当前 resolved model identifier 包含，才能继续评估 `pewter_owl_tool` 或 `pewter_owl_brief` 的各自 gate；它不选择或改写 request model",
            failure="不匹配只关闭两个 Pewter Owl surface；noninteractive、env override 和各自 feature gate 仍独立；substring 命中也不验证模型真实能力",
            impact="把实验性 tool/Brief 约束到指定模型族，避免在未验证模型上展示；不会触发 fallback model 或额外计费",
            document="brief-mode-and-user-visible-output.md",
            functions=("qWS",),
            callsites=1,
        ),
        "tengu_c4e_slash_upsell": reviewed_contract(
            owner="Enterprise-only slash-command stub gate `iim`",
            reader="iim",
            line=365919,
            fallback="boolean fallback false；只在没有 first-party Claude account、检测到 Enterprise acquisition context且为 interactive session 时启用",
            state="注册隐藏的 `/ultraplan`、`/ultrareview`、`/teleport`、`/remote-control`、`/schedule`、`/autofix-pr` stubs；调用只记录 shown event 并返回迁移提示",
            failure="stub 不运行真实命令、不创建远端 session；用户已有对应真实命令时由正常 registry/eligibility 决定，Enterprise 迁移和 entitlement 属外部 Boundary",
            impact="让 API-key/企业环境用户输入已知命令时得到可操作说明，而不是 unknown command；不改变账号、费用或权限",
            document="complex-slash-command-lifecycles.md",
            functions=("iim",),
            callsites=1,
        ),
        "tengu_startup_notice": reviewed_contract(
            owner="reactive startup notification subscriber",
            reader="startup notice effect",
            line=585916,
            fallback="string fallback empty；订阅 feature refresh，只有值变化才更新，empty 会移除既有 `startup-notice`",
            state="非空文本以 warning/high-priority notification 插入队列，timeout 30 秒；同 key 更新折叠为新文本而非堆叠多条",
            failure="通知队列/渲染不可见不会阻止 CLI 启动；文本没有本地 schema/来源解释，不能从展示内容反推强制 policy",
            impact="允许服务端在不发版时向启动中的用户展示短期高优先级公告，可能打断注意力但不改变 runtime 配置",
            document="feature-flags-remote-config.md",
            functions=("n",),
            callsites=1,
        ),
        "tengu_gleaming_fair": reviewed_contract(
            owner="large stale-session resume choice gate `yug`",
            reader="yug",
            line=511107,
            fallback="boolean fallback false；还要求用户未永久 dismiss、至少有一条超过一分钟的旧 user/assistant message、age 默认 >=70 分钟且估算 >=100,000 tokens",
            state="返回 age/token evidence，令 resume UI 在载入前提示 full session 会消耗大量额度，并推荐从 summary 恢复；用户仍可选 full、summary、dismiss",
            failure="任一阈值未达只走原 resume；token 是本地估算，summary 生成/质量和后续 API charge 仍独立，flag 不自动 compact transcript",
            impact="把大而陈旧会话的成本选择前置给用户，减少无意加载整段历史；不会删除原 transcript 或外部副作用",
            document="sessions-checkpoints-memory.md",
            functions=("yug",),
            callsites=1,
        ),
        "tengu_quartz_thimble": reviewed_contract(
            owner="Plugin Eval default Artifact-report publish selector `uVm`",
            reader="uVm",
            line=448217,
            fallback="boolean fallback true；只影响存在 default report dir、未显式 `--publish-report`、非 interview session 的隐式 publish，`publish:false` 最高优先关闭，显式 publish 不依赖该 flag",
            state="允许 eval 完成后在写本地 HTML 的同时检查 Artifact capability并尝试发布报告；publish availability 等待最多 3 秒的 policy limits hydration",
            failure="abort、Artifact unavailable 或 publish failure 都保留/尝试本地 report 并写明确 status；它不改变 eval scores、partial 标记或 CI exit",
            impact="默认把 Plugin Eval 结果变成可分享网页，增加网络上传和报告可见性；关闭可保留纯本地产物以降低隐私面",
            document="plugin-evaluation-harness.md",
            functions=("uVm",),
            callsites=1,
        ),
        "tengu_saffron_credits_only_tiers": reviewed_contract(
            owner="usage-credits-only subscription-tier parser `p6b`",
            reader="p6b",
            line=157519,
            fallback="array-of-string fallback `['enterprise']`；按 raw value 缓存解析，shape 不合法告警并回默认；Enterprise 且非特殊排除态本来就硬判 credits-only，因此 flag 主要用于增加其他 tier",
            state="把当前 subscription tier 分类为 credits-only；该分类参与 upgrade/overage prompt、extra-usage availability、Fable model picker disabled reason 与 usage-limit handling",
            failure="tier 不在数组只走普通 plan-limit lane；字符串匹配不证明真实 credits balance、billing entitlement 或服务端会接受请求",
            impact="决定某些套餐看到“需要 usage credits”还是常规 overage/upgrade UX，可能隐藏或禁用 Fable 选择，但不扣费也不购买 credits",
            document="models-auth-providers-request.md",
            functions=("p6b",),
            callsites=1,
        ),
        "tengu_cedar_transom": reviewed_contract(
            owner="Artifact plan-workshop offer kill switch `Sga`",
            reader="Sga",
            line=156021,
            fallback="boolean fallback false，并以 negated gate 参与；true 无条件关闭 offer，false 仍要求 workshop enabled、bundled skills 可用、plan-artifact lane 关闭且 larch enable 打开",
            state="true 让 `eQt()` workshop-offer availability 为 false，停止 workshop doc attachment/reminder、plan offer 与 workshop filename recognition 的这条可达路径",
            failure="它不禁用基础 Artifact tool、已发布页面或已有 workshop 文件，也不回滚读者在页面上的决定；其他 Artifact/skill gates继续独立判断",
            impact="为有问题的 plan-workshop 集成提供快速退场开关，减少模型提示与附件，但不会删除用户内容",
            document="workflow-artifact-design.md",
            functions=("Sga",),
            callsites=1,
        ),
        "tengu_larch_pavise": reviewed_contract(
            owner="Artifact plan-workshop offer rollout enable `Sga`",
            reader="Sga",
            line=156021,
            fallback="boolean fallback false；必须与 workshop enabled、bundled skills 未禁用、cedar kill off、plan-artifact lane off 同时成立",
            state="打开 `eQt()` availability，使主 Agent 可收到 workshop doc/attachment reminder、识别 `.workshop.md`，并把 plan workshop offer 纳入上下文",
            failure="enable 不保证 Artifact publish、runtime capability或 read-back 成功；基础 workshop skill `Dfs`、账号/admin policy与 publish verifier仍分别校验",
            impact="让计划过程可通过可点击 Artifact 决策页反复收集选择，增加 prompt/附件与发布成本；关闭只收回 offer，不删除既有文档",
            document="workflow-artifact-design.md",
            functions=("Sga",),
            callsites=1,
        ),
        "tengu_harbor_kite_mode_emit": reviewed_contract(
            owner="cross-session permission-mode class emitter `_Wr`",
            reader="_Wr",
            line=306275,
            fallback="boolean fallback false；开启时 sender 从当前 permission context 归一为 `bypass` 或 `prompting`，显式 legacy/forced receive path仍可在部分入口要求 mode",
            state="在 bridge/UDS peer message envelope 附 `fromMode`，并让默认 inbound policy在无显式 crossSessionInbound setting 时比较 sender/receiver class：相同 accept，不同 hold；listener 也向 child sender 注入 mode provider",
            failure="mode getter 缺失/抛错或未知值一律 fail-closed hold；关闭后 bypass receiver 对无 mode sender仍 hold、prompting receiver可 accept，显式 accept/hold/refuse setting继续优先",
            impact="减少不同安全姿态 session 间静默消息注入，把不匹配消息送用户审批；它只传粗粒度 class，不传完整 rules，也不证明最终 delivery",
            document="cloud-background-channels.md",
            functions=("_Wr",),
            callsites=1,
        ),
    }
)


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


def format_access_modes(rows: list[dict[str, Any]]) -> str:
    counts = Counter(str(row.get("accessMode", "read")) for row in rows)
    return ", ".join(f"{name} x{counts[name]}" for name in sorted(counts)) or "none"


def consumer_descriptor(row: dict[str, Any]) -> str:
    consumer = row.get("consumer")
    if not isinstance(consumer, dict):
        return "consumer context unavailable"
    role = str(consumer.get("role") or "other")
    details: list[str] = []
    operator = consumer.get("operator")
    if isinstance(operator, str):
        details.append(f"op={operator}")
    target = consumer.get("target")
    if isinstance(target, str):
        details.append(f"target={target}")
    callee = consumer.get("callee")
    if isinstance(callee, str):
        details.append(f"callee={callee}")
    argument_index = consumer.get("argumentIndex")
    if isinstance(argument_index, int):
        details.append(f"arg={argument_index}")
    relation = consumer.get("relation")
    if isinstance(relation, str) and role == "other":
        details.append(f"relation={relation}")
    return role if not details else f"{role} ({', '.join(details)})"


def format_consumer_context(rows: list[dict[str, Any]]) -> str:
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        owner = str(row.get("function") or "<top-level>")
        counts[(owner, consumer_descriptor(row))] += 1
    if not counts:
        return "none"
    rendered: list[str] = []
    for (owner, descriptor), count in sorted(counts.items()):
        suffix = f" x{count}" if count > 1 else ""
        rendered.append(f"{compact_code(owner)}: {compact_code(descriptor)}{suffix}")
    return "<br>".join(rendered)


def render_manual_contract(contract: dict[str, Any]) -> str:
    return (
        "Static consumer 人工合同："
        f"owner={contract['owner']}；"
        f"读取位置={contract['readLocation']}；"
        f"fallback/precedence={contract['fallbackPrecedence']}；"
        f"state delta={contract['stateDelta']}；"
        f"failure/Boundary={contract['failureBoundary']}；"
        f"用户影响={contract['userImpact']}。"
        f"详见 [{contract['document']}]({contract['document']})。"
    )


def validate_manual_contract_shape(
    identifier: str, contract: dict[str, Any], kind: str
) -> None:
    missing = [field for field in MANUAL_CONTRACT_FIELDS if field not in contract]
    if missing:
        raise ValueError(
            f"{kind} manual contract {identifier} missing fields: {', '.join(missing)}"
        )
    for field in MANUAL_CONTRACT_FIELDS:
        value = contract[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{kind} manual contract {identifier} has invalid {field}"
            )
    if not str(contract["document"]).endswith(".md"):
        raise ValueError(
            f"{kind} manual contract {identifier} document must be Markdown"
        )
    functions = contract.get("lexicalFunctions")
    if (
        not isinstance(functions, tuple)
        or not functions
        or any(not isinstance(value, str) or not value for value in functions)
    ):
        raise ValueError(
            f"{kind} manual contract {identifier} has invalid lexicalFunctions"
        )
    if not isinstance(contract.get("callsiteCount"), int) or contract["callsiteCount"] <= 0:
        raise ValueError(
            f"{kind} manual contract {identifier} has invalid callsiteCount"
        )


def validate_environment_manual_contracts(
    env_calls: list[dict[str, Any]],
) -> None:
    overlap = sorted(set(ENV_MEANINGS) & set(ENV_MANUAL_CONTRACTS))
    if overlap:
        raise ValueError(
            "environment structured/manual tuple contracts overlap: "
            + ", ".join(overlap)
        )
    calls_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in env_calls:
        if isinstance(row.get("name"), str):
            calls_by_name[row["name"]].append(row)
    for name, contract in sorted(ENV_MANUAL_CONTRACTS.items()):
        validate_manual_contract_shape(name, contract, "environment")
        rows = calls_by_name.get(name, [])
        if len(rows) != contract["callsiteCount"]:
            raise ValueError(
                f"environment manual contract {name} callsite drift: "
                f"expected={contract['callsiteCount']}, actual={len(rows)}"
            )
        functions = tuple(
            sorted({str(row.get("function") or "<top-level>") for row in rows})
        )
        if functions != tuple(sorted(contract["lexicalFunctions"])):
            raise ValueError(
                f"environment manual contract {name} lexical owner drift: "
                f"expected={contract['lexicalFunctions']}, actual={functions}"
            )
        modes = contract.get("accessModes")
        if not isinstance(modes, tuple) or not modes:
            raise ValueError(
                f"environment manual contract {name} has invalid accessModes"
            )
        observed_modes = tuple(sorted({str(row.get("accessMode")) for row in rows}))
        if observed_modes != tuple(sorted(modes)):
            raise ValueError(
                f"environment manual contract {name} access-mode drift: "
                f"expected={modes}, actual={observed_modes}"
            )


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
    if has_calls and name in ENV_MANUAL_CONTRACTS:
        return render_manual_contract(ENV_MANUAL_CONTRACTS[name])
    if has_calls and name in ENV_MEANINGS:
        meaning, document = ENV_MEANINGS[name]
        return f"Static consumer \u6559\u5b66\u89e3\u91ca\uff1a{meaning}\u8be6\u89c1 [{document}]({document})\u3002"
    if has_calls:
        return (
            "Static immediate consumer\uff1aschema/named access \u4e4b\u5916\uff0c\u672c\u884c\u5df2\u8bb0\u5f55 read/write/delete\u3001"
            "lexical function\u3001immediate AST role/operator/target\u3001fallback \u548c\u4f4d\u7f6e\u3002"
            "Semantic follow-up\uff1a\u4e8c\u6b21 gate\u3001\u72b6\u6001\u53d8\u5316\u548c\u5931\u8d25\u6062\u590d\u5c1a\u672a\u4eba\u5de5\u6536\u53e3\uff1b"
            "\u8fd9\u4ecd\u662f\u53ef\u6062\u590d\u7684\u5ba2\u6237\u7aef\u6b20\u8d26\uff0c\u4e0d\u5f97\u5199\u6210\u670d\u52a1\u7aef Boundary\u3002"
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
    if key in FEATURE_MANUAL_CONTRACTS:
        prefix = (
            "Opaque name / "
            if "opaque experiment codename" in feature_category(key)
            else ""
        )
        return prefix + render_manual_contract(FEATURE_MANUAL_CONTRACTS[key])
    if key in FEATURE_MEANINGS:
        meaning, document = FEATURE_MEANINGS[key]
        if "opaque experiment codename" in feature_category(key):
            return f"Opaque name / Static consumer \u884c\u4e3a\uff1a{meaning}\u8be6\u89c1 [{document}]({document})\u3002"
        return f"Static consumer \u6559\u5b66\u89e3\u91ca\uff1a{meaning}\u8be6\u89c1 [{document}]({document})\u3002"
    category = feature_category(key)
    if "opaque experiment codename" not in category:
        return (
            "Static immediate consumer\uff1a\u672c\u884c\u7ed9\u51fa lexical function\u3001immediate AST role/operator/target\u3001"
            "fallback \u4e0e\u4f4d\u7f6e\uff1b\u63cf\u8ff0\u6027 key \u540d\u53ea\u7528\u4e8e\u5bfc\u822a\u3002Semantic follow-up\uff1a"
            "\u5168\u90e8\u4e8c\u6b21 gate\u3001\u72b6\u6001\u53d8\u5316\u548c\u5931\u8d25\u6062\u590d\u5c1a\u672a\u4eba\u5de5\u6536\u53e3\uff0c"
            "\u4e0d\u5f97\u628a\u8fd9\u9879\u5ba2\u6237\u7aef\u6b20\u8d26\u6539\u5199\u6210 Boundary\u3002"
        )
    return (
        "Opaque name / Static immediate consumer\uff1acodename \u672c\u8eab\u4e0d\u53ef\u89e3\u91ca\uff0c\u4f46\u672c\u884c\u5df2\u7ed9\u51fa"
        " lexical function\u3001immediate AST role/operator/target\u3001fallback \u548c\u4f4d\u7f6e\u3002"
        "Semantic follow-up\uff1a\u5168\u90e8 caller\u3001\u4e8c\u6b21 gate\u3001\u72b6\u6001\u53d8\u5316\u4e0e\u5931\u8d25\u6062\u590d\u5c1a\u672a\u4eba\u5de5\u6536\u53e3\uff1b"
        "\u4e0d\u5f97\u4ece codename \u81ea\u884c\u751f\u6210\u529f\u80fd\u7ed3\u8bba\u3002"
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
    resolved_dynamic_env = [
        row
        for row in dynamic_env
        if "resolvedStaticValue" in row or "resolvedFiniteValues" in row
    ]
    unresolved_dynamic_env = [
        row
        for row in dynamic_env
        if "resolvedStaticValue" not in row and "resolvedFiniteValues" not in row
    ]
    resolved_dynamic_names = {
        str(name)
        for row in resolved_dynamic_env
        for name in (
            [row["resolvedStaticValue"]]
            if "resolvedStaticValue" in row
            else row.get("resolvedFiniteValues", [])
        )
    }
    typed_named_calls = [row for row in named_calls if row["name"] in typed_names]
    untyped_named_calls = [row for row in named_calls if row["name"] not in typed_names]
    typed_used_names = {row["name"] for row in typed_named_calls}
    untyped_names = {row["name"] for row in untyped_named_calls}
    all_static_environment_names = typed_used_names | untyped_names | resolved_dynamic_names
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
        "resolved_dynamic_environment_callsites": len(resolved_dynamic_env),
        "unresolved_dynamic_environment_callsites": len(unresolved_dynamic_env),
        "resolved_dynamic_environment_names": len(resolved_dynamic_names),
        "resolved_dynamic_only_typed_names": len(
            (typed_names & resolved_dynamic_names) - typed_used_names
        ),
        "typed_no_static_consumer": len(
            typed_names - typed_used_names - resolved_dynamic_names
        ),
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
    stale_environment_contracts = sorted(set(ENV_MEANINGS) - all_static_environment_names)
    if stale_environment_contracts:
        raise ValueError(
            "environment consumer contracts have no active named or finite dynamic access: "
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
    validate_environment_manual_contracts(env_calls)
    calls_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    dynamic_calls: list[dict[str, Any]] = []
    for row in env_calls:
        if row.get("name") is None:
            dynamic_calls.append(row)
        else:
            calls_by_name[row["name"]].append(row)
    resolved_dynamic_calls = [
        row
        for row in dynamic_calls
        if "resolvedStaticValue" in row or "resolvedFiniteValues" in row
    ]
    unresolved_dynamic_calls = [
        row
        for row in dynamic_calls
        if "resolvedStaticValue" not in row and "resolvedFiniteValues" not in row
    ]
    unresolved_reason_counts = Counter(
        row.get("unresolvedResolution", {}).get(
            "primaryReason", "missing-classification"
        )
        for row in unresolved_dynamic_calls
    )
    unresolved_reason_explanations = {
        "empty-or-oversized-iteration-domain": "\u9759\u6001\u96c6\u5408\u4e3a\u7a7a\u6216\u8d85\u8fc7\u6709\u9650\u4f20\u64ad\u4e0a\u9650\uff0c\u4e0d\u80fd\u628a\u90e8\u5206\u96c6\u5408\u5192\u5145\u5b8c\u6574\u540d\u79f0\u57df",
        "no-static-function-callers": "\u901a\u7528 helper \u6ca1\u6709\u5b8c\u6574\u7684\u672c\u5730\u9759\u6001 caller \u96c6\uff0c\u5916\u90e8\u6216\u4f9d\u8d56\u8c03\u7528\u4ecd\u53ef\u4f20\u5165\u8fd0\u884c\u65f6\u540d\u79f0",
        "non-direct-function-call": "\u540d\u79f0\u7ee7\u7eed\u6d41\u5165\u6210\u5458\u8c03\u7528\u6216\u9ad8\u9636\u8c03\u7528\uff0c\u5f53\u524d\u8c03\u7528\u53c2\u6570\u4e0d\u80fd\u5b8c\u6574\u9759\u6001\u6c42\u503c",
        "runtime-await-result": "\u540d\u79f0\u6765\u81ea await \u7684\u8fd0\u884c\u65f6\u7ed3\u679c\u5bf9\u8c61",
        "runtime-constructed-collection": "\u540d\u79f0\u6765\u81ea\u8fd0\u884c\u65f6\u6784\u9020\u7684 Map\u3001Set \u6216\u5176\u4ed6\u5bb9\u5668",
        "runtime-environment-keyset": "\u540d\u79f0\u76f4\u63a5\u6765\u81ea\u5f53\u524d\u8fdb\u7a0b\u7684\u52a8\u6001\u73af\u5883 key \u96c6",
        "runtime-function-call": "\u540d\u79f0\u7531\u65e0\u6cd5\u8bc1\u660e\u4e3a\u7eaf\u9759\u6001\u8fd4\u56de\u7684\u51fd\u6570\u8c03\u7528\u4ea7\u751f",
        "runtime-identifier": "\u6807\u8bc6\u7b26\u6700\u7ec8\u6765\u81ea\u8fd0\u884c\u65f6\u8f93\u5165\u3001\u52a8\u6001 import \u89e3\u6784\u6216\u53ef\u53d8\u72b6\u6001",
        "runtime-logical-name": "\u903b\u8f91\u8868\u8fbe\u5f0f\u81f3\u5c11\u4e00\u4fa7\u662f\u8fd0\u884c\u65f6\u53ef\u914d\u7f6e\u540d\u79f0\uff0c\u9759\u6001 fallback \u4e0d\u662f\u5b8c\u6574\u540d\u79f0\u57df",
        "runtime-object-member": "\u5bf9\u8c61\u672c\u8eab\u6216\u6210\u5458\u503c\u7531\u8fd0\u884c\u65f6\u6570\u636e\u51b3\u5b9a",
        "unsupported-expression-node": "\u5931\u8d25\u94fe\u4fdd\u7559\u5177\u4f53 AST \u8282\u70b9\uff0c\u4f46\u5f53\u524d\u6ca1\u6709\u5b8c\u6574\u6709\u9650\u540d\u79f0\u8bc1\u660e",
    }
    resolved_dynamic_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in resolved_dynamic_calls:
        values = (
            [row["resolvedStaticValue"]]
            if "resolvedStaticValue" in row
            else row.get("resolvedFiniteValues", [])
        )
        for name in values:
            resolved_dynamic_by_name[str(name)].append(row)
    resolved_dynamic_names = set(resolved_dynamic_by_name)
    typed_names = {row["name"] for row in env_schema}
    untyped_names = sorted(name for name in calls_by_name if name not in typed_names)
    named_declaration_only = typed_names - set(calls_by_name)
    resolved_dynamic_only_typed = sorted(
        (typed_names & resolved_dynamic_names) - set(calls_by_name)
    )
    declaration_only = sorted(typed_names - set(calls_by_name) - resolved_dynamic_names)
    active_named_names = sorted(calls_by_name)
    active_static_names = set(active_named_names) | resolved_dynamic_names
    all_contract_names = set(ENV_MEANINGS) | set(ENV_MANUAL_CONTRACTS)
    consumer_contract_names = sorted(all_contract_names & active_static_names)
    direct_consumer_contract_names = sorted(all_contract_names & set(active_named_names))
    resolved_dynamic_only_contract_names = sorted(
        set(consumer_contract_names) - set(active_named_names)
    )
    callsite_only_names = sorted(
        set(active_named_names) - set(direct_consumer_contract_names)
    )
    semantic_followup_static_names = sorted(
        active_static_names - set(consumer_contract_names)
    )
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
        "  C --> E{\u5b58\u5728 named \u6216 finite dynamic callsite?}",
        "  D --> E",
        "  E -->|\u5426| F[No static consumer / Boundary]",
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
        f"| \u5df2\u7ed1\u5b9a\u4e1a\u52a1 consumer \u5408\u540c | {len(consumer_contract_names)} \u4e2a\u9759\u6001\u540d\u79f0\uff08{len(direct_consumer_contract_names)} \u4e2a direct named + {len(resolved_dynamic_only_contract_names)} \u4e2a dynamic-only\uff09 | \u5df2\u4eba\u5de5\u8ffd\u5230\u4f18\u5148\u7ea7\u3001fallback\u3001\u4e8c\u6b21 gate\u3001\u72b6\u6001\u53d8\u5316\u548c\u5931\u8d25\u8fb9\u754c | \u5f53\u524d\u8fd0\u884c\u503c\u3001\u8fdc\u7aef\u670d\u52a1\u6216\u4e0d\u53ef\u8fbe\u5e73\u53f0\u5206\u652f |",
        f"| \u5df2\u7ed1\u5b9a immediate AST consumer\u3001\u672a\u5b8c\u6210\u4eba\u5de5\u673a\u5236\u89e3\u91ca | {len(semantic_followup_static_names)} \u4e2a\u9759\u6001\u540d\u79f0\uff08\u5176\u4e2d {len(callsite_only_names)} \u4e2a direct named\uff09 | read/write/delete\u3001lexical function\u3001role/operator/target\u3001fallback \u548c\u5168\u90e8\u4f4d\u7f6e\u53ef\u4ea4\u53c9\u6bd4\u8f83 | \u4e0d\u5f97\u628a immediate syntax \u76f4\u63a5\u5199\u6210\u5df2\u8ffd\u5b8c\u4e8c\u6b21 gate\u3001\u72b6\u6001\u53d8\u5316\u6216\u5931\u8d25\u6062\u590d |",
        f"| \u65e0\u9759\u6001 consumer \u7684 typed \u540d\u79f0 | {len(declaration_only)} | schema \u4e2d\u5b58\u5728\uff0c\u4f46\u65e2\u65e0 named access\uff0c\u4e5f\u672a\u88ab\u5b89\u5168\u7684 dynamic finite-name resolver \u547d\u4e2d | \u53ef\u4ee5\u628a\u5b83\u5199\u6210\u8fd0\u884c\u65f6\u529f\u80fd\u5f00\u5173 |",
        f"| \u4ec5\u901a\u8fc7\u52a8\u6001\u4e0b\u6807\u89e3\u6790\u7684 typed \u540d\u79f0 | {len(resolved_dynamic_only_typed)} | \u65e0 direct named access\uff0c\u4f46\u6709\u5b8c\u6574 caller/finite-name \u8bc1\u636e | \u8fd0\u884c\u503c\u3001\u5f53\u524d\u5206\u652f\u53ef\u8fbe\u6216\u8fdc\u7aef\u63a5\u53d7\u5df2\u8bc1\u660e |",
        f"| \u975e typed \u9759\u6001\u540d\u79f0 | {metrics['untyped_named_names']} \u4e2a\u540d\u79f0 / {metrics['untyped_named_callsites']} \u4e2a\u8c03\u7528\u70b9 | \u8fd0\u884c\u65f6\u4ee3\u7801\u76f4\u63a5\u8bfb\u53d6\u4e86 schema \u5916\u540d\u79f0 | \u503c\u7ecf\u8fc7\u7edf\u4e00\u7c7b\u578b\u9a8c\u8bc1 |",
        f"| \u52a8\u6001\u4e0b\u6807\u8c03\u7528\u70b9 | {metrics['dynamic_environment_callsites']}\uff08{len(resolved_dynamic_calls)} \u4e2a\u5df2\u8bc1\u660e\u9759\u6001/\u6709\u9650\u540d\u79f0\uff0c{len(unresolved_dynamic_calls)} \u4e2a\u672a\u89e3\u6790\uff09 | \u4ee3\u7801\u6309\u8868\u8fbe\u5f0f\u8ba1\u7b97\u73af\u5883\u53d8\u91cf\u540d\uff1b\u6709\u9650\u89e3\u6790\u63a5\u53d7\u53ef\u8bc1\u660e\u7684 assignment/member\u3001\u5bf9\u8c61/\u6570\u7ec4\u3001for-of/callback\u3001\u5b57\u7b26\u4e32\u53d8\u6362\u4e0e\u5b8c\u6574 caller \u53c2\u6570\u96c6 | \u540d\u79f0\u5df2\u89e3\u6790\u4e0d\u7b49\u4e8e\u8fd0\u884c\u503c\u3001consumer \u5206\u652f\u6216\u8fdc\u7a0b\u80fd\u529b\u5df2\u786e\u5b9a |",
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
        "| `access count/accessor kinds` | AST \u6355\u83b7\u5230\u7684 access \u6b21\u6570\u4e0e `process.env`/environment proxy \u5f62\u5f0f | \u6b21\u6570\u8d8a\u591a\u5c31\u8d8a\u91cd\u8981 |",
        "| `access modes / lexical consumer` | \u533a\u5206 read\u3001write\u3001read-write\u3001delete\uff0c\u5e76\u7ed9\u51fa lexical function \u4e0e immediate AST role/operator/target | \u628a minified function \u540d\u7ffb\u8bd1\u6210\u4e1a\u52a1\u6a21\u5757\uff0c\u6216\u628a immediate role \u5f53\u6210\u5168\u90e8 caller \u94fe |",
        "| `fallback expressions` | \u4e0e\u8bfb\u53d6\u8868\u8fbe\u5f0f\u76f8\u90bb\u7684 `||` \u6216 `??` fallback | `||` \u4e0e `??` \u5bf9\u7a7a\u5b57\u7b26\u4e32\u30010\u3001false \u7b49\u4ef7 |",
        "| `locations` | canonical `extracted/cli.js` \u7684 schema/read \u884c\u5217 | \u884c\u53f7\u672c\u8eab\u80fd\u89e3\u91ca minified consumer |",
        "| `sensitivity` | \u4ec5\u6309\u540d\u79f0\u8bc6\u522b credential\u3001identity\u3001path\u3001network \u98ce\u9669 | \u6ca1\u547d\u4e2d\u5173\u952e\u8bcd\u5c31\u53ef\u4ee5\u516c\u5f00\u771f\u5b9e\u503c |",
        f"| `meaning/evidence` | {len(consumer_contract_names)} \u4e2a\u9759\u6001\u540d\u79f0\u8fde\u63a5\u5230\u5df2\u8ffd\u5b8c\u7684\u4eba\u5de5 consumer \u4e13\u9898\uff1b\u5176\u4f59 {len(semantic_followup_static_names)} \u4e2a\u4fdd\u7559 Static immediate consumer \u5e76\u663e\u5f0f\u6807 Semantic follow-up | \u7528\u53d8\u91cf\u540d\u6216 immediate syntax \u81ea\u884c\u8865\u5168\u4e8c\u6b21 gate\u3001\u72b6\u6001\u53d8\u5316\u4e0e\u5931\u8d25\u6062\u590d |",
        "",
        "`||` \u4f1a\u5728\u7a7a\u5b57\u7b26\u4e32\u30010\u3001false \u65f6\u5207 fallback\uff1b`??` \u53ea\u5728 null/undefined \u65f6\u5207 fallback\u3002inventory \u8bb0\u5f55\u7684\u662f\u8868\u8fbe\u5f0f\uff0c\u4e0d\u662f\u4e00\u6b21\u771f\u5b9e\u8fd0\u884c\u7684\u6c42\u503c\u7ed3\u679c\u3002",
        "",
        "## \u5931\u8d25\u4e0e\u670d\u52a1\u7aef\u8fb9\u754c",
        "",
        f"1. typed \u58f0\u660e\u6210\u529f\u3001\u503c\u4e5f\u53ef\u89e3\u6790\uff0c\u4e0d\u4ee3\u8868\u4efb\u4f55 consumer \u8bfb\u53d6\u5b83\uff1b\u539f named-only \u53e3\u5f84\u6709 {len(named_declaration_only)} \u9879\uff0c\u6263\u9664 {len(resolved_dynamic_only_typed)} \u4e2a finite dynamic consumer \u540e\uff0c\u771f\u6b63\u65e0\u9759\u6001 consumer \u7684\u5269 {len(declaration_only)} \u9879\u3002",
        "2. named read \u5b58\u5728\uff0c\u4e0d\u4ee3\u8868\u5f53\u524d provider\u3001entrypoint\u3001policy\u3001platform \u6216\u8d26\u6237\u72b6\u6001\u80fd\u5230\u8fbe\u8be5\u5206\u652f\u3002",
        "3. \u52a8\u6001\u8bfb\u53d6\u7684\u6700\u7ec8\u540d\u79f0\u4f9d\u8d56\u5c40\u90e8\u53d8\u91cf\u3001\u5faa\u73af\u3001\u4f9d\u8d56\u5e93\u6216\u8fd0\u884c\u65f6\u8f93\u5165\uff1b145 \u4e2a\u8c03\u7528\u70b9\u5fc5\u987b\u4fdd\u7559\u8868\u8fbe\u5f0f\u800c\u4e0d\u662f\u731c\u540d\u79f0\u3002",
        "4. credential\u3001endpoint\u3001feature payload\u3001cloud identity\u3001proxy \u548c\u670d\u52a1\u7aef entitlement \u7684\u771f\u5b9e\u503c\u4e0d\u5728 shipped bundle \u4e2d\u3002",
        "5. typed schema \u6df7\u6709 bundled dependency surface\uff1b\u672c\u6587\u7684\u7c7b\u522b\u662f\u5bfc\u822a heuristic\uff0c\u4e0d\u662f Anthropic \u4ea7\u54c1\u5f52\u5c5e\u6807\u7b7e\u3002",
        "",
        "## \u56db\u4e2a\u8bca\u65ad\u573a\u666f",
        "",
        "### 1. \u53d8\u91cf\u5199\u4e86\u4f46\u6ca1\u6709\u6548\u679c",
        "",
        "\u5148\u770b\u672c\u8868\u662f\u5426\u6709 direct named \u6216 finite dynamic consumer\uff0c\u518d\u770b access mode\u3001lexical role\u3001fallback \u548c\u4eba\u5de5 consumer \u4e13\u9898\u3002\u82e5\u53ea\u6709 schema \u58f0\u660e\uff0c\u7ed3\u8bba\u53ea\u80fd\u662f `Boundary`\uff0c\u4e0d\u80fd\u7ee7\u7eed\u731c\u5e03\u5c14\u8bed\u4e49\u3002",
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
        f"\u8986\u76d6\u5408\u540c\uff1a`{metrics['environment_schema']}/{metrics['environment_schema']}`\u3002\u6bcf\u884c\u90fd\u663e\u793a name\u3001type\u3001options\u3001heuristic category\u3001accessor\u3001read/write/delete\u3001lexical owner/immediate consumer\u3001fallback\u3001\u5168\u90e8\u4f4d\u7f6e\u3001sensitivity \u548c meaning/evidence\u3002",
        "",
        "| name | type / options | category | access count / accessor kinds | access modes / lexical owner / immediate consumer | fallback expressions | locations | sensitivity | meaning / evidence |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for row in sorted(env_schema, key=lambda item: item["name"]):
        name = row["name"]
        calls = sorted(
            {
                item["comparisonKey"]: item
                for item in [
                    *calls_by_name.get(name, []),
                    *resolved_dynamic_by_name.get(name, []),
                ]
            }.values(),
            key=lambda item: item["offset"],
        )
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
                    cell(f"{format_access_modes(calls)}<br>{format_consumer_context(calls)}"),
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
            f"## {len(declaration_only)} \u4e2a\u65e0\u9759\u6001 consumer \u7684 typed \u540d\u79f0",
            "",
            f"\u539f\u59cb named-only \u53e3\u5f84\u6709 {len(named_declaration_only)} \u4e2a\uff1b\u5176\u4e2d {len(resolved_dynamic_only_typed)} \u4e2a\u5df2\u88ab\u5b89\u5168\u7684 dynamic finite-name resolver \u7ed1\u5b9a\u5230\u771f\u5b9e callsite\uff0c\u56e0\u6b64\u4e0d\u518d\u7b97 declaration-only\u3002\u4e0b\u5217\u540d\u79f0\u65e2\u65e0 direct named access\uff0c\u4e5f\u6ca1\u6709\u5b8c\u6574\u52a8\u6001\u540d\u79f0\u8bc1\u660e\u3002",
            "",
            ", ".join(compact_code(name) for name in declaration_only),
            "",
            f"### {len(resolved_dynamic_only_typed)} \u4e2a\u4ec5\u901a\u8fc7\u52a8\u6001\u4e0b\u6807\u6062\u590d\u7684 typed \u540d\u79f0",
            "",
            ", ".join(compact_code(name) for name in resolved_dynamic_only_typed),
            "",
            "## 137 \u4e2a\u975e typed \u9759\u6001\u540d\u79f0\u9010\u9879\u53c2\u8003",
            "",
            f"\u8986\u76d6\u5408\u540c\uff1a`{metrics['untyped_named_names']}/{metrics['untyped_named_names']}` \u4e2a\u540d\u79f0\u3001`{metrics['untyped_named_callsites']}/{metrics['untyped_named_callsites']}` \u4e2a\u8c03\u7528\u70b9\u3002`type/options` \u4e00\u5f8b\u662f Boundary\uff0c\u56e0\u4e3a\u8fd9\u4e9b\u540d\u79f0\u4e0d\u5728 typed builder schema \u4e2d\u3002",
            "",
            "| name | type / options | category | access count / accessor kinds | access modes / lexical owner / immediate consumer | fallback expressions | locations | sensitivity | meaning / evidence |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for name in untyped_names:
        calls = sorted(calls_by_name[name], key=lambda item: item["offset"])
        structured_contract = ENV_MANUAL_CONTRACTS.get(name)
        meaning = ENV_MEANINGS.get(name)
        if structured_contract:
            evidence = render_manual_contract(structured_contract)
        elif meaning:
            description, document = meaning
            evidence = f"Static consumer \u6559\u5b66\u89e3\u91ca\uff1a{description}\u8be6\u89c1 [{document}]({document})\u3002"
        else:
            evidence = (
                "Static immediate consumer\uff1adirect named read\u3001read/write/delete\u3001lexical function \u548c immediate AST role \u53ef\u8bc1\uff1b"
                "typed schema \u4e0d\u63d0\u4f9b\u8be5\u540d\u79f0\u7684\u7c7b\u578b\u6821\u9a8c\u3002Semantic follow-up\uff1a\u4e8c\u6b21 gate\u3001"
                "\u72b6\u6001\u53d8\u5316\u4e0e\u5931\u8d25\u6062\u590d\u5c1a\u672a\u4eba\u5de5\u6536\u53e3\uff0ccategory/sensitivity \u4ecd\u662f\u540d\u79f0 heuristic\u3002"
            )
        lines.append(
            "| "
            + " | ".join(
                [
                    compact_code(name),
                    "Boundary\uff1a\u4e0d\u5728 typed schema \u4e2d",
                    cell(environment_category(name)),
                    cell(f"{len(calls)} / {format_accessors(calls)}"),
                    cell(f"{format_access_modes(calls)}<br>{format_consumer_context(calls)}"),
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
            f"## {len(dynamic_calls)} \u4e2a\u52a8\u6001\u4e0b\u6807\u8c03\u7528\u70b9\uff1a{len(resolved_dynamic_calls)} \u4e2a\u540d\u79f0\u53ef\u8bc1\u660e\uff0c{len(unresolved_dynamic_calls)} \u4e2a\u4ecd\u672a\u89e3\u6790",
            "",
            "\u6bcf\u884c\u4ee3\u8868\u4e00\u4e2a\u771f\u5b9e AST callsite\u3002`expression` \u59cb\u7ec8\u4fdd\u7559 bundle \u539f\u8868\u8fbe\u5f0f\uff1b`resolved name(s)` \u53ea\u5728\u540c/\u7956\u5148\u4f5c\u7528\u57df assignment\u3001\u9759\u6001\u6570\u7ec4 callback \u6216\u6240\u6709\u53ef\u89c1 caller \u53c2\u6570\u90fd\u80fd\u6c42\u6210\u6709\u9650\u5b57\u7b26\u4e32\u96c6\u65f6\u51fa\u73b0\u3002\u4efb\u4e00\u8def\u5f84\u6709\u8fd0\u884c\u53c2\u6570\u6216\u52a8\u6001 spread\uff0c\u8be5\u884c\u4ecd\u4fdd\u6301\u672a\u89e3\u6790\uff0c\u4e0d\u628a minified identifier \u7ffb\u8bd1\u6210\u731c\u6d4b\u540d\u79f0\u3002",
            "",
            "\u5f53\u524d\u89e3\u6790\u5668\u8fd8\u8986\u76d6\u552f\u4e00 bundle/member assignment\u3001\u6709\u9650\u5bf9\u8c61/\u6570\u7ec4\u3001for-of\u3001\u547d\u540d callback\u3001\u9759\u6001\u5b57\u7b26\u4e32\u53d8\u6362\u4e0e\u5bf9\u8c61\u679a\u4e3e\uff1b\u6bcf\u79cd\u7b56\u7565\u90fd\u8981\u6c42\u5b8c\u6574\u6709\u9650\u57df\uff0c\u4e0d\u63a5\u53d7\u90e8\u5206\u547d\u4e2d\u3002",
            "",
            f"### {len(unresolved_dynamic_calls)} \u4e2a\u672a\u89e3\u6790\u8c03\u7528\u70b9\u4e3a\u4ec0\u4e48\u505c\u5728\u8fd9\u91cc",
            "",
            "| primary reason | callsites | \u4e0d\u80fd\u7ee7\u7eed\u9759\u6001\u6536\u53e3\u7684\u539f\u56e0 |",
            "| --- | ---: | --- |",
            *(
                f"| {reason} | {count} | {unresolved_reason_explanations.get(reason, '\u5931\u8d25\u94fe\u4fdd\u7559\u4e86\u5177\u4f53 AST \u8282\u70b9\uff1b\u5f53\u524d\u6ca1\u6709\u5b8c\u6574\u6709\u9650\u540d\u79f0\u8bc1\u660e')} |"
                for reason, count in sorted(unresolved_reason_counts.items())
            ),
            "",
            "| comparison key | expression | resolved name(s) | accessor / access mode | lexical owner / immediate consumer | fallback | location | resolution / Boundary |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in sorted(dynamic_calls, key=lambda item: item["offset"]):
        expression = source_text(row.get("expression"))
        fallback = format_fallbacks([row])
        if "resolvedStaticValue" in row:
            resolved = compact_code(str(row["resolvedStaticValue"]))
        elif "resolvedFiniteValues" in row:
            resolved = "<br>".join(
                compact_code(str(value)) for value in row["resolvedFiniteValues"]
            )
        else:
            resolved = "Unresolved"
        resolution = row.get("resolutionEvidence")
        unresolved_resolution = row.get("unresolvedResolution")
        if resolution:
            evidence = (
                "Static/finite name proof: "
                + compact_code(str(resolution.get("strategy", "static-expression")))
                + f"\uff1b{resolution.get('callerCount', len(row.get('caller', [])))} \u4e2a caller/callback \u8bc1\u636e\u3002"
                + "Boundary\uff1a\u672c\u6b21\u8fdb\u7a0b\u4e2d\u7684\u771f\u5b9e\u73af\u5883\u503c\u3001consumer \u53ef\u8fbe\u6027\u548c\u8fdc\u7a0b\u63a5\u53d7\u5ea6\u672a\u6267\u884c\u3002"
            )
        elif unresolved_resolution:
            primary_reason = unresolved_resolution.get(
                "primaryReason", "missing-classification"
            )
            reasons = ", ".join(unresolved_resolution.get("reasons", []))
            evidence = (
                "Unresolved finite-name proof: "
                + compact_code(str(primary_reason))
                + (
                    f"\uff1bfailure chain: {compact_code(reasons)}\u3002"
                    if reasons
                    else "\u3002"
                )
                + "Boundary\uff1a\u539f\u8868\u8fbe\u5f0f\u3001lexical owner \u4e0e immediate consumer \u53ef\u8bc1\uff1b"
                "\u6700\u7ec8\u540d\u79f0\u4ecd\u4f9d\u8d56\u8fd0\u884c\u65f6\u8f93\u5165/\u5bb9\u5668\uff0c\u6216\u7f3a\u5c11\u5b8c\u6574 caller \u96c6\u3002"
            )
        else:
            evidence = (
                "Static callsite context / name Boundary\uff1alexical owner \u548c immediate consumer \u53ef\u8bc1\uff1b"
                "\u8868\u8fbe\u5f0f\u4ecd\u5305\u542b\u672a\u8bc1\u660e\u7684\u8fd0\u884c\u53c2\u6570\u6216\u52a8\u6001\u5bf9\u8c61\u3002"
            )
        lines.append(
            "| "
            + " | ".join(
                [
                    compact_code(row["comparisonKey"]),
                    compact_code(expression),
                    cell(resolved),
                    cell(f"{compact_code(str(row['accessor']))}<br>{compact_code(str(row.get('accessMode', 'read')))}"),
                    cell(format_consumer_context([row])),
                    cell(fallback),
                    source_location(row),
                    evidence,
                ]
            )
            + " |"
        )

    summary = {
        "artifact": "analysis/environment-variable-reference.md",
        "consumerContractCount": len(consumer_contract_names),
        "consumerContractNamesSha256": names_sha256(consumer_contract_names),
        "structuredConsumerContractCount": len(ENV_MANUAL_CONTRACTS),
        "structuredConsumerContractNamesSha256": names_sha256(
            ENV_MANUAL_CONTRACTS
        ),
        "structuredConsumerContractCallsiteCount": sum(
            int(contract["callsiteCount"])
            for contract in ENV_MANUAL_CONTRACTS.values()
        ),
        "directConsumerContractCount": len(direct_consumer_contract_names),
        "resolvedDynamicOnlyConsumerContractCount": len(
            resolved_dynamic_only_contract_names
        ),
        "callsiteOnlyNamedReadCount": len(callsite_only_names),
        "semanticFollowupStaticNameCount": len(semantic_followup_static_names),
        "lexicalContextCallsiteCount": sum(
            1 for row in env_calls if "functionKind" in row
        ),
        "consumerContextCallsiteCount": sum(
            1 for row in env_calls if isinstance(row.get("consumer"), dict)
        ),
        "accessModeCallsiteCount": sum(
            1 for row in env_calls if row.get("accessMode") in {"read", "write", "read-write", "delete"}
        ),
        "resolvedDynamicCallsiteCount": len(resolved_dynamic_calls),
        "unresolvedDynamicCallsiteCount": len(unresolved_dynamic_calls),
        "unresolvedDynamicReasonCounts": dict(sorted(unresolved_reason_counts.items())),
        "resolvedDynamicOnlyTypedNameCount": len(resolved_dynamic_only_typed),
        "noStaticConsumerTypedNameCount": len(declaration_only),
        "resolvedDynamicNamesSha256": names_sha256(resolved_dynamic_names),
        "resolvedDynamicComparisonKeysSha256": names_sha256(
            row["comparisonKey"] for row in resolved_dynamic_calls
        ),
        "unresolvedDynamicComparisonKeysSha256": names_sha256(
            row["comparisonKey"] for row in unresolved_dynamic_calls
        ),
        "generatedBy": "skill/claude-code-version-diff/scripts/build_environment_feature_references.py",
        "inputSha256": hashes,
        "metrics": {
            key: metrics[key]
            for key in metrics
            if key.startswith(
                (
                    "environment",
                    "typed_",
                    "untyped_",
                    "dynamic_environment",
                    "resolved_dynamic_environment",
                    "unresolved_dynamic_environment",
                    "resolved_dynamic_only_typed",
                )
            )
        },
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
            "<!-- BEGIN:ENVIRONMENT_VARIABLE_REFERENCE:RESOLVED_DYNAMIC_NAMES",
            *sorted(resolved_dynamic_names),
            "END:ENVIRONMENT_VARIABLE_REFERENCE:RESOLVED_DYNAMIC_NAMES -->",
            "<!-- BEGIN:ENVIRONMENT_VARIABLE_REFERENCE:NO_STATIC_CONSUMER_TYPED_NAMES",
            *declaration_only,
            "END:ENVIRONMENT_VARIABLE_REFERENCE:NO_STATIC_CONSUMER_TYPED_NAMES -->",
            "<!-- BEGIN:ENVIRONMENT_VARIABLE_REFERENCE:CONSUMER_CONTRACT_NAMES",
            *consumer_contract_names,
            "END:ENVIRONMENT_VARIABLE_REFERENCE:CONSUMER_CONTRACT_NAMES -->",
            "<!-- BEGIN:ENVIRONMENT_VARIABLE_REFERENCE:STRUCTURED_CONTRACT_NAMES",
            *sorted(ENV_MANUAL_CONTRACTS),
            "END:ENVIRONMENT_VARIABLE_REFERENCE:STRUCTURED_CONTRACT_NAMES -->",
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


def validate_feature_manual_contracts(
    feature_keys: list[str], feature_calls: list[dict[str, Any]]
) -> None:
    overlap = sorted(set(FEATURE_MEANINGS) & set(FEATURE_MANUAL_CONTRACTS))
    if overlap:
        raise ValueError(
            "feature structured/manual tuple contracts overlap: " + ", ".join(overlap)
        )
    key_set = set(feature_keys)
    calls_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in feature_calls:
        value = static_feature_value(row)
        if value is not None:
            calls_by_key[value].append(row)
    for key, contract in sorted(FEATURE_MANUAL_CONTRACTS.items()):
        validate_manual_contract_shape(key, contract, "feature")
        if key not in key_set:
            raise ValueError(f"feature manual contract key is absent from inventory: {key}")
        rows = calls_by_key.get(key, [])
        if len(rows) != contract["callsiteCount"]:
            raise ValueError(
                f"feature manual contract {key} callsite drift: "
                f"expected={contract['callsiteCount']}, actual={len(rows)}"
            )
        functions = tuple(
            sorted({str(row.get("function") or "<top-level>") for row in rows})
        )
        if functions != tuple(sorted(contract["lexicalFunctions"])):
            raise ValueError(
                f"feature manual contract {key} lexical owner drift: "
                f"expected={contract['lexicalFunctions']}, actual={functions}"
            )


def build_feature_document(
    version: str,
    feature_keys: list[str],
    feature_calls: list[dict[str, Any]],
    growthbook_keys: list[str],
    growthbook_calls: list[dict[str, Any]],
    metrics: dict[str, int],
    hashes: dict[str, str],
) -> str:
    validate_feature_manual_contracts(feature_keys, feature_calls)
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
    all_contract_keys = set(FEATURE_MEANINGS) | set(FEATURE_MANUAL_CONTRACTS)
    consumer_contract_keys = sorted(key for key in all_contract_keys if calls_by_key.get(key))
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
        f"| \u5df2\u7ed1\u5b9a immediate AST consumer\u3001\u672a\u5b8c\u6210\u4eba\u5de5\u673a\u5236\u89e3\u91ca | {len(callsite_only_keys)} \u4e2a key | key\u3001fallback\u3001lexical function\u3001role/operator/target \u548c\u4f4d\u7f6e\u53ef\u4ea4\u53c9\u6bd4\u8f83 | \u4e0d\u5f97\u4ece codename \u6216 immediate syntax \u76f4\u63a5\u63a8\u65ad\u5168\u90e8 caller\u3001\u4e8c\u6b21 gate \u548c\u4ea7\u54c1\u7ed3\u679c |",
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
        "| `immediate consumer roles / targets` | `et()` \u8fd4\u56de\u503c\u76f4\u63a5\u8fdb\u5165\u7684 if/return/variable/call/member/operator \u4e0e\u9759\u6001 target | \u628a immediate parent \u5f53\u6210\u5168\u90e8 caller \u94fe\u6216\u6700\u7ec8\u72b6\u6001\u53d8\u5316 |",
        "| `category` | \u540d\u79f0\u5173\u952e\u8bcd\u5bfc\u822a\uff0c\u7edf\u4e00\u6807 `Heuristic/name` | \u628a codenames \u5c55\u5f00\u6210\u4ea7\u54c1\u7ed3\u8bba |",
        "| `meaning/evidence` | \u5df2\u4eba\u5de5\u6536\u53e3\u7684 key \u7ed9\u51fa\u5b8c\u6574 consumer \u673a\u5236\uff1b\u5176\u4f59 key \u81f3\u5c11\u7ed9\u51fa Static immediate consumer\uff0ccodename \u4ecd\u6807 Opaque name | \u4ece key \u540d\u6216 immediate parent \u81ea\u884c\u751f\u6210\u4e8c\u6b21 gate\u3001\u5931\u8d25\u6062\u590d\u6216\u5341\u5206\u949f\u6545\u4e8b |",
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
        "`tengu_amber_anchor` \u4e00\u7c7b key \u7684 codename \u4ecd\u4e0d\u53ef\u89e3\u91ca\uff1b\u672c\u6587\u4fdd\u7559 fallback\u3001lexical function\u3001immediate role/operator/target \u548c\u4f4d\u7f6e\uff0c\u6807\u4e3a `Opaque name / Static immediate consumer`\u3002\u53ea\u6709 caller\u3001\u4e8c\u6b21 gate\u3001\u72b6\u6001\u53d8\u5316\u4e0e\u5931\u8d25\u6062\u590d\u4eba\u5de5\u6536\u53e3\u540e\uff0c\u624d\u80fd\u5347\u7ea7\u4e3a\u5b8c\u6574 consumer \u5408\u540c\uff1b\u670d\u52a1\u7aef value/rule/rollout \u4ecd\u5355\u72ec\u662f Boundary\u3002",
        "",
        "## 361 \u4e2a static feature key \u9010\u9879\u53c2\u8003",
        "",
        f"\u8986\u76d6\u5408\u540c\uff1a`{metrics['feature_keys']}/{metrics['feature_keys']}`\uff0c\u5bf9\u5e94 `{metrics['feature_resolvable_static_callsites']}/{metrics['feature_resolvable_static_callsites']}` \u4e2a\u53ef\u9759\u6001\u6062\u590d\u8c03\u7528\u70b9\u3002`count` \u540c\u65f6\u5305\u542b direct literal \u548c assignment-resolved \u9759\u6001\u8c03\u7528\u3002",
        "",
        "| key | defaults / shape | count / functions | immediate consumer roles / targets | locations | category | meaning / evidence | Boundary |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
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
                    cell(format_consumer_context(rows)),
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
            "| comparison key | expression | resolver result | local fallback / shape | function / immediate consumer | location | evidence / Boundary |",
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
                    cell(f"{compact_code(str(row.get('function') or '<top-level>'))}<br>{format_consumer_context([row])}"),
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
            "\u8fd9\u4e9b\u8c03\u7528\u70b9\u65e2\u6ca1\u6709 direct literal\uff0c\u4e5f\u65e0\u6cd5\u7531 assignment resolver \u6062\u590d\u9759\u6001 key\u3002\u672c\u6587\u4fdd\u7559\u8868\u8fbe\u5f0f\u3001fallback\u3001lexical function\u3001immediate consumer role/target \u4e0e\u4f4d\u7f6e\uff0c\u4e0d\u731c\u6700\u7ec8\u540d\u79f0\u3002",
            "",
            "| comparison key | expression | local fallback / shape | function / immediate consumer | location | evidence / Boundary |",
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
                    cell(f"{compact_code(str(row.get('function') or '<top-level>'))}<br>{format_consumer_context([row])}"),
                    source_location(row),
                    "Static callsite context / key Boundary\uff1alexical owner \u548c immediate consumer \u53ef\u8bc1\uff1b\u6700\u7ec8 key \u4e0e\u771f\u5b9e\u8fd0\u884c value \u4ecd\u4f9d\u8d56\u6267\u884c\u72b6\u6001\u3002",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Cached dynamic config\uff1a6 \u4e2a\u9759\u6001 key / 12 \u4e2a\u8c03\u7528\u70b9",
            "",
            "`CB()` \u4e0d\u662f\u53e6\u4e00\u5957\u5929\u7136\u5b9e\u65f6\u914d\u7f6e\u30022.1.235 \u7684\u8be5 wrapper \u8d70\u540c\u6b65\u7f13\u5b58\u8bfb\u53d6\uff1b6 \u4e2a\u8c03\u7528\u70b9\u4f7f\u7528\u9759\u6001 key\uff0c\u53e6\u5916 6 \u4e2a\u4f7f\u7528\u52a8\u6001\u8868\u8fbe\u5f0f\u3002\u4e0b\u8868\u9010\u8c03\u7528\u70b9\u4fdd\u7559\u9ed8\u8ba4\u503c\u3001shape\u3001lexical function\u3001immediate consumer \u548c\u4f4d\u7f6e\u3002",
            "",
            "| comparison key | key / expression | local fallback / shape | function / immediate consumer | location | meaning / Boundary |",
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
            meaning = "Static callsite context / key Boundary\uff1adynamic key expression \u7684 lexical owner \u4e0e immediate consumer \u53ef\u8bc1\uff1b\u6700\u7ec8 key\u3001payload \u4e0e\u4e1a\u52a1\u542b\u4e49\u672a\u89c2\u5bdf\u3002"
        lines.append(
            "| "
            + " | ".join(
                [
                    compact_code(row["comparisonKey"]),
                    compact_code(key_or_expression),
                    cell(f"{compact_code(fallback)} / shape heuristic: {feature_default_shape(fallback)}"),
                    cell(f"{compact_code(str(row.get('function') or '<top-level>'))}<br>{format_consumer_context([row])}"),
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
        "structuredConsumerContractCount": len(FEATURE_MANUAL_CONTRACTS),
        "structuredConsumerContractKeysSha256": names_sha256(
            FEATURE_MANUAL_CONTRACTS
        ),
        "structuredConsumerContractCallsiteCount": sum(
            int(contract["callsiteCount"])
            for contract in FEATURE_MANUAL_CONTRACTS.values()
        ),
        "callsiteOnlyStaticKeyCount": len(callsite_only_keys),
        "lexicalContextCallsiteCount": sum(
            1 for row in feature_calls if "functionKind" in row
        ),
        "consumerContextCallsiteCount": sum(
            1 for row in feature_calls if isinstance(row.get("consumer"), dict)
        ),
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
            "<!-- BEGIN:FEATURE_FLAG_REFERENCE:STRUCTURED_CONTRACT_KEYS",
            *sorted(FEATURE_MANUAL_CONTRACTS),
            "END:FEATURE_FLAG_REFERENCE:STRUCTURED_CONTRACT_KEYS -->",
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
