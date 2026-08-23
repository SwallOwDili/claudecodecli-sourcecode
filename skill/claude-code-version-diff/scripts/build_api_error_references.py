#!/usr/bin/env python3
"""Build and validate the API/Beta catalog and error/diagnostic metrics blocks."""

from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
from collections import Counter
from pathlib import Path


API_START = "<!-- API_PATH_CATALOG_START -->"
API_END = "<!-- API_PATH_CATALOG_END -->"
BETA_START = "<!-- BETA_IDENTIFIER_CATALOG_START -->"
BETA_END = "<!-- BETA_IDENTIFIER_CATALOG_END -->"
METRICS_START = "<!-- ERROR_DIAGNOSTIC_METRICS_START -->"
METRICS_END = "<!-- ERROR_DIAGNOSTIC_METRICS_END -->"


API_EVIDENCE_LINES = {
    "/.well-known/oauth-authorization-server": [151218, 440543, 627530],
    "/api/claude_cli_feedback": [448980, 449002, 449020],
    "/api/claude_code/notification/preferences": [332452, 332465, 332506],
    "/api/claude_code/organizations/metrics_enabled": [338513, 338517, 338529],
    "/api/claude_code/skills": [495556, 495558, 495563],
    "/api/claude_code_grove": [334824, 334836, 334839],
    "/api/claude_code_shared_session_transcripts": [581317, 581319, 581327],
    "/api/frame/deploy/direct": [260784, 260801, 260804, 260808, 261088],
    "/api/oauth/account/grove_notice_viewed": [334736, 334739, 334742],
    "/api/oauth/account/settings": [334747, 334750, 334824],
    "/api/oauth/organizations/:orgUUID/admin_requests": [366756, 366758, 366767],
    "/api/oauth/organizations/:orgUUID/billing/tax_rate": [216387, 216389, 216393],
    "/api/oauth/organizations/:orgUUID/claude_code/pro_trial": [482585, 482589, 482591],
    "/api/oauth/organizations/:orgUUID/contracts/auto_reload_settings": [216312, 216316, 216318],
    "/api/oauth/organizations/:orgUUID/contracts/prepaid/credits": [216368, 216376, 216378],
    "/api/oauth/organizations/:orgUUID/mcp/connectors/list": [298650, 298676],
    "/api/oauth/organizations/:orgUUID/mcp/connectors/search": [298636, 298676],
    "/api/oauth/organizations/:orgUUID/mcp/connectors/suggest": [298643, 298676],
    "/api/oauth/organizations/:orgUUID/overage_credit_grant": [276151, 276155, 276180],
    "/api/oauth/organizations/:orgUUID/overage_spend_limit": [216284, 216290, 216303],
    "/api/oauth/organizations/:orgUUID/payment_method": [216359, 216363, 216365],
    "/api/oauth/organizations/:orgUUID/plugin_ratings": [582513, 582521, 582527],
    "/api/oauth/organizations/:orgUUID/plugin_ratings/appearances": [582506, 582510],
    "/api/oauth/organizations/:orgUUID/plugin_ratings/appearances/outcome": [582524, 582526],
    "/api/oauth/organizations/:orgUUID/plugins/search": [298946, 298985],
    "/api/oauth/organizations/:orgUUID/prepaid/bundles": [216345, 216349, 216353],
    "/api/oauth/organizations/:orgUUID/prepaid/credits": [216325, 216329, 216332],
    "/api/oauth/organizations/:orgUUID/setup_overage_billing": [216284, 216288, 216292],
    "/api/oauth/organizations/:orgUUID/skills/search": [298946, 298985],
    "/api/oauth/organizations/:orgUUID/sync/github/auth": [508876, 508878, 508881],
    "/api/oauth/usage": [216437, 216442, 216446],
    "/api/organization/claude_code_first_token_date": [433890, 433898, 433910],
    "/api/organizations/:orgUUID/claude_code/onboarding": [315063, 315069, 315084],
    "/api/organizations/:orgUUID/cowork/remote_devices": [210500, 210510, 210544],
    "/managed/settings": [625196, 627665],
    "/oauth/callback": [627575, 627597],
    "/oauth/device_authorization": [440545, 627547],
    "/oauth/token": [216501, 440545, 627606],
    "/v1/complete": [12718, 219442],
    "/v1/logs": [626498, 627680],
    "/v1/messages": [13132, 625736, 627688],
    "/v1/messages/batches": [13086, 13092],
    "/v1/messages/count_tokens": [13142, 625744, 627688],
    "/v1/metrics": [626498, 627680, 633160],
    "/v1/models": [13160, 622294, 627687],
    "/v1/organizations/spend_limits": [626029, 626040, 626187],
    "/v1/traces": [626498, 627680],
}


API_PATH_DETAILS: dict[str, tuple[str, str, str]] = {
    "/api/desktop/": (
        "Updater egress prefix",
        "Desktop updater 把该固定 prefix 与 /update suffix 组合，并根据 updateViaUpdatesHost 选择当前 Anthropic host 或专用 update host；它同时进入 renderer/main firewall egress rules。",
        "prefix 只证明路由合同；实际 release feed、签名、下载与安装结果由 updater/远端服务决定。",
    ),
    "/api/directory/": (
        "Anthropic MCP registry egress prefix",
        "作为 nonessential-services 下的 MCP directory/registry renderer egress allowlist，与 /mcp-registry/ 并列；设置可整体关闭该网络能力。",
        "allowlist 不证明目录请求已发生，也不证明 catalog 内容、entitlement 或 connector 可用。",
    ),
    "/api/event_logging/": (
        "First-party telemetry egress prefix",
        "作为 nonessential telemetry 的 renderer egress path，绑定当前 Anthropic host；disableNonessentialTelemetry 可从服务集合移除。具体 batch consumer 使用 /api/event_logging/v2/batch。",
        "egress 允许不等于 event gate、采样、发送、接收或保留已经发生。",
    ),
    "/api/event_logging/v2/batch": (
        "First-party telemetry batch transport",
        "一方 event queue 把通过 enable/sample/privacy gate 的事件批量 POST 到该固定 path；batch exporter 自己拥有队列、flush、retry 与 auth fallback，单个业务 event 不直接发 HTTP。",
        "静态 path 和队列合同不证明某事件本次被采样、成功到达或被服务端保留。",
    ),
    "/api/frame/": (
        "Frame host-routing prefix",
        "作为 Frame/Artifact host routing 与 normalization anchor；真正请求由 contract、deploy、upload、track、DB 等精确子路由构造，prefix 本身不可独立调用。",
        "只能证明 client routing surface，不能推断任一子路由 entitlement 或成功。",
    ),
    "/api/frame/contract/latest": (
        "Artifact capability-contract consumer",
        "GET 最新 contract，限制响应体并做 schema 校验；publish 前用它校验 capability 名、解析 dual spelling、选择 explicit/echo/latest pin，服务不可用时拒绝需要 contract 的发布，而不是猜版本。",
        "客户端可证 contract adoption；远端 contract 内容、yank 和 rollout 仍需实时响应。",
    ),
    "/api/frame/db/agent": (
        "Artifact DB read/write consumer",
        "承载 get/list/query/set/update/delete；客户端校验 slug/path/operator、读响应上限 4 MiB、写 data 16 KiB、路径 1,000 bytes，并把 not_found/quota/busy/auth/store errors 映射成 typed result。",
        "远端数据库事务、索引一致性、配额和持久化不在客户端；成功 echo 也不等于跨区域 durable。",
    ),
    "/api/frame/deploy/complete": (
        "Artifact signed-upload completion notifier",
        "POST slug/version/ok 与 publish telemetry，15 s timeout；期望 204。该调用是 best-effort，非 ok、非 204 或异常只记录日志，不改写前面 upload 的真实结果。",
        "通知失败时 signed upload 可能已经完成，不能据此自动重发或回滚对象。",
    ),
    "/api/frame/deploy/direct": (
        "Artifact inline publish consumer",
        "POST HTML/manifest 与 metadata，timeout 60 s；处理 409 version conflict、404 create gate、400 compatibility retry、429 一次等待与 503 最多 3 attempts。成功响应先按 schema 校验 slug/version 的存在与格式；已有目标 slug 时只校验 slug 相等，version 采用服务端返回值并更新本地已知版本。",
        "request/relay error、响应格式错误或 slug mismatch 时，错误文本会提示‘可能已经发布’并建议再次发布前检查 artifact list；这是恢复建议，不是该 direct-publish 函数强制执行的 list/read-before-write gate，远端是否落库仍需实际 readback。",
    ),
    "/api/frame/deploy/init": (
        "Artifact signed-upload preflight consumer",
        "POST publish metadata 获取 slug/version、signed PUT URL/headers 与可选 thumbnail URL，15 s timeout；503 等待 2 s 重试一次，并对旧 control plane 的 unknown force/baseVersion/thumbType 做有界兼容重试。",
        "init 成功只分配上传合同，不证明后续 object PUT、complete 通知或页面渲染成功。",
    ),
    "/api/frame/deploy/prepare": (
        "Artifact multi-file hash preflight consumer",
        "POST 可选 slug 与 SHA-256 列表，timeout 30 s；返回 reserved slug 和 missing hashes，429 最多重试一次。客户端随后分批 upload，若 deploy 仍报告缺块只再准备一次，拒绝无限 GC loop。",
        "preflight 可能已保留 slug；后续失败不是原子回滚，重试必须复用返回 slug。",
    ),
    "/api/frame/track": (
        "Artifact view/action tracking consumer",
        "POST event_name、slug/via/mode，timeout 5 s；期望 204。失败、非 204 或异常只写 debug，不阻断 artifact 的主读取/发布流程。",
        "事件接收、采样、归因和保留属于服务端 telemetry Boundary。",
    ),
    "/api/frame/upload": (
        "Artifact missing-blob upload consumer",
        "multi-file publish 按 preflight missing SHA 分批 POST path/content/contentType，timeout 60 s；单批 wire 预算约 15 MiB，429 等待后只重试一次，非 200 终止发布并保留可恢复 slug。",
        "上传成功不等于 manifest deploy 已提交；失败后远端可能已有部分 blob debris。",
    ),
    "/api/claude_cli_feedback": (
        "Feedback upload consumer",
        "POST 经过清洗和大小预检的 description、session/subagent transcript 与可选 debug log，timeout 30 s；200 还必须返回 feedback_id。413、RangeError、疑似大包 timeout、ZDR 403、auth/data-residency 和网络错误分别映射为 typed failure。",
        "客户端可证发送内容、redaction 和失败分类；服务端保存期、工单处理、删除与最终隐私策略不可见。",
    ),
    "/api/claude_code/notification/preferences": (
        "Notification preference hydrate/patch consumer",
        "登录后 GET/PATCH，timeout 10 s。GET 先做 schema parse，再把 push reachability 写入进程状态，并且只在本地对应 setting 尚未显式设置时 seed userSettings；PATCH 失败只记录诊断，不回滚本地设置。",
        "服务端 channel 注册、push token 健康和真实送达结果属于远端 Boundary。",
    ),
    "/api/claude_code/organizations/metrics_enabled": (
        "Organization metrics opt-out consumer",
        "GET 使用 async auth、5 s timeout，并允许绕过 essential-traffic-only gate；成功值进入最多 24 h 的本地 cache，失败返回 enabled=false/hasError=true，避免把未知状态写成已允许。",
        "组织策略值、审计保留和服务端是否接受后续 metrics 不在静态快照内。",
    ),
    "/api/claude_code/skills": (
        "Skills Dashboard health consumer",
        "仅在 tengu_skills_dashboard_enabled 为 true 时 GET，async auth、5 s timeout、接受任意 HTTP status 后自行判断；非 ok、status>=400、非法 skills 数组或异常都降级 null，成功只保留 good/warn/poor 的 skill_name -> health。",
        "健康计算算法和账号 rollout 在服务端；null 只表示本次没有可采用的 health map。",
    ),
    "/api/claude_code_grove": (
        "Grove notice/config consumer",
        "GET 读取 grove_enabled、domain_excluded、grace-period 与 reminder frequency，timeout 3 s；失败返回 success=false。客户端另以 24 h cache 决定当前 session 展示或后台刷新。",
        "服务端条款状态、domain classification 与实际账号选择属于远端 Boundary。",
    ),
    "/api/claude_code_shared_session_transcripts": (
        "Shared transcript upload consumer",
        "POST JSON transcript，timeout 30 s；200/201 提取 transcript_id，essential-traffic-only/data-residency/no-auth 记为 blocked，413、RangeError、timeout/network 等按 payload-too-large 与普通失败分流。",
        "远端 transcript 的访问控制、保留、分享页面渲染和删除状态需服务端 readback。",
    ),
    "/api/oauth/account/grove_notice_viewed": (
        "Grove notice acknowledgement consumer",
        "POST 空 body 标记 notice viewed；成功清 Grove account cache，失败只记诊断，不伪造已确认状态。",
        "服务端是否持久化、跨设备同步和条款合规判定属于远端 Boundary。",
    ),
    "/api/oauth/account/settings": (
        "Grove account settings consumer",
        "GET 以 3 s timeout 读取 Grove account config；PATCH 写 grove_enabled。成功后清 account cache，读取失败返回 success=false，写失败不更新为远端成功。",
        "账号级设置的服务端版本、并发冲突和跨设备最终一致性不可见。",
    ),
    "/api/oauth/organizations/:orgUUID/admin_requests": (
        "Usage-credit admin request consumer",
        "teleport-org auth 下 POST 创建 limit_increase 等请求；同一 owner 还从 /me 与 /eligibility 派生 GET，按 request_type/status 查询。非 5xx 结构化 message 可直接向用户展示。",
        "管理员审批、通知、SLA 和最终额度变更由组织服务拥有。",
    ),
    "/api/oauth/organizations/:orgUUID/billing/tax_rate": (
        "Credit purchase tax preview consumer",
        "POST product_id、price、currency，timeout 5 s；有 tax_rate 才计算本地 tax_minor_units，缺 product/rate 或请求失败都降级为无 preview。",
        "税务归属、最终结算税额和支付合规由 billing 服务决定。",
    ),
    "/api/oauth/organizations/:orgUUID/claude_code/pro_trial": (
        "Pro trial activation consumer",
        "teleport-org auth 下 POST 空 body；成功采用 ends_at 更新本地 trial state，no-auth 与服务不可用转成显式失败。",
        "资格、重复领取、订阅状态和最终到期时间由账号服务拥有。",
    ),
    "/api/oauth/organizations/:orgUUID/contracts/auto_reload_settings": (
        "Prepaid auto-reload settings consumer",
        "PUT enabled、threshold、reload amount 与 currency，timeout 30 s；失败保留服务端 user-facing reason，不把本地表单值当成已生效。",
        "支付方式、触发扣款、并发更新和最终账单属于 billing Boundary。",
    ),
    "/api/oauth/organizations/:orgUUID/contracts/prepaid/credits": (
        "Prepaid credit purchase consumer",
        "POST amount，或 amount + bundle_id + expected_price_minor_units，timeout 30 s；响应可进入 success、3DS requires_action 或 pending invoice 后续状态机。",
        "支付授权、3DS、invoice settlement、退款和余额入账由 billing 服务决定。",
    ),
    "/api/oauth/organizations/:orgUUID/mcp/connectors/list": (
        "Connector catalog list consumer",
        "POST 空 body，teleport-org auth、15 s timeout；schema 校验后返回 connector results，并用当前 MCP server IDs 标注 enabledInChat。opt_in_required 是可见状态，不当成空目录。",
        "服务端 catalog、entitlement、自定义 connector 内容和实时安装状态需运行验证。",
    ),
    "/api/oauth/organizations/:orgUUID/mcp/connectors/search": (
        "Connector keyword search consumer",
        "POST keywords + include_custom=true，teleport-org auth、15 s timeout；>=400 解析 error envelope，成功结果必须通过 schema，opt-in requirement 单独返回。",
        "搜索排序、索引新鲜度、账号 entitlement 与第三方 connector 质量在服务端。",
    ),
    "/api/oauth/organizations/:orgUUID/mcp/connectors/suggest": (
        "Connector UUID lookup/suggestion consumer",
        "POST uuids，teleport-org auth、15 s timeout；复用 connector response schema 和 opt-in 分支，用于把候选 UUID 解析为可展示 connector。",
        "建议算法、候选生成来源和远端 catalog 内容不可从客户端恢复。",
    ),
    "/api/oauth/organizations/:orgUUID/overage_credit_grant": (
        "Promotional overage credit eligibility/claim consumer",
        "GET campaign eligibility 使用 10 s timeout；POST campaign/feature/enable_overages claim 使用 60 s timeout。两者接受 <500 status 后由客户端区分 unavailable、eligible、claimed 或 failed。",
        "campaign 规则、风控、额度到账和重复领取判定由服务端拥有。",
    ),
    "/api/oauth/organizations/:orgUUID/overage_spend_limit": (
        "Overage spend-limit consumer",
        "PUT 可只开启 overage，或写 monthly_credit_limit + currency；成功返回 disabled_until/used_credits，失败保留 user-facing reason。setup flow 会在 setup_overage_billing 成功后再调用本路由。",
        "最终信用额度、计费、并发更新和管理员策略属于 billing Boundary。",
    ),
    "/api/oauth/organizations/:orgUUID/payment_method": (
        "Payment-method summary consumer",
        "GET 使用 teleport-org auth 和 5 s timeout，返回支付方式摘要或 null；请求失败不会凭空构造可支付状态。",
        "完整卡数据、支付处理商 token、验证和可扣款性不在客户端。",
    ),
    "/api/oauth/organizations/:orgUUID/plugin_ratings": (
        "Plugin rating submit/withdraw consumer",
        "POST bad/fine/good rating；dismissed/not_sure 后如本 session 已评分则 DELETE 撤回。执行前还检查 first-party、org pin、feedback policy、marketplace 来源和远端 feature。",
        "评分聚合、反滥用、审核与最终存储由服务端拥有。",
    ),
    "/api/oauth/organizations/:orgUUID/plugin_ratings/appearances": (
        "Plugin rating appearance consumer",
        "POST marketplace、plugin、client surface 与 appearance_id，记录评分控件实际展示；调用被同一串 policy/org/feature gates 保护。",
        "服务端曝光归因、采样和保留策略不可见。",
    ),
    "/api/oauth/organizations/:orgUUID/plugin_ratings/appearances/outcome": (
        "Plugin rating dismissal outcome consumer",
        "POST dismissed 或 unsure outcome；若此前已提交 rating，再尝试 DELETE rating，使本地 ratedInStore 状态与用户撤回动作一致。",
        "跨设备最终状态和服务端去重/归因规则属于远端 Boundary。",
    ),
    "/api/oauth/organizations/:orgUUID/plugins/search": (
        "Plugin catalog search consumer",
        "policy 允许后确保 user:plugins scope，再 POST keywords，teleport-org auth、15 s timeout。403 entitlement 错误降级为空结果，其他 HTTP/schema 错误保持失败。",
        "搜索排名、catalog 内容、entitlement 和安装成功不由该响应证明。",
    ),
    "/api/oauth/organizations/:orgUUID/prepaid/bundles": (
        "Prepaid bundle catalog consumer",
        "GET 使用 teleport-org auth 和 5 s timeout；404 明确解释为当前不可用并返回 null，其他失败记录诊断。",
        "价格、折扣、购买上限和商品可售性以服务端实时结果为准。",
    ),
    "/api/oauth/organizations/:orgUUID/prepaid/credits": (
        "Prepaid balance consumer",
        "GET 使用 teleport-org auth 和 5 s timeout；只有 amount 为 number 才采用，并携带 currency、auto_reload_settings 与 expiry policy。非法 shape 降级为 not_supported/null。",
        "余额账本、过期执行、并发扣费和最终账单属于服务端。",
    ),
    "/api/oauth/organizations/:orgUUID/setup_overage_billing": (
        "Overage billing setup consumer",
        "POST 初始 org_monthly_spend_limit，timeout 30 s；成功后还必须 PUT overage_spend_limit 开启功能，任一步失败都使整体 enable 返回 false。",
        "两步远端写不是原子事务；部分完成状态必须通过 billing API/readback 确认。",
    ),
    "/api/oauth/organizations/:orgUUID/skills/search": (
        "Skill catalog search consumer",
        "policy 允许后 POST keywords，teleport-org auth、15 s timeout；403 entitlement 错误降级为空结果，其他 HTTP/schema 错误保持失败。",
        "搜索排名、skill 内容、账号 entitlement 和安装/注入结果属于后续 owner。",
    ),
    "/api/oauth/organizations/:orgUUID/sync/github/auth": (
        "GitHub sync auth-status consumer",
        "GET 使用 teleport-org auth、10 s timeout 并接受任意 status；只有 HTTP 200、is_authenticated=true 且 auth_source 为 oauth 或 cli_import 才返回已认证来源，其余统一 null。",
        "GitHub token 权限、过期、仓库访问和后续 sync 成功仍需目标服务验证。",
    ),
    "/api/oauth/usage": (
        "Plan usage/rate-limit consumer",
        "first-party OAuth 条件满足时 GET，timeout 5 s、refreshOAuth=true；wrapper 允许 401 刷新后重试，并把 plan windows/extra usage/model limits 交给本地额度状态机。",
        "响应只是查询快照；最终计费、并发消费和 reset 执行由服务端拥有。",
    ),
    "/api/organization/claude_code_first_token_date": (
        "First-token-date consumer",
        "GET 使用 async auth 和 10 s timeout；合法 ISO date 或 null 写入本地 config cache，非法日期拒绝采用，已有 cache 时不重复请求。",
        "服务端历史完整性、账号合并和该日期的业务解释属于账号服务。",
    ),
    "/api/organizations/:orgUUID/claude_code/onboarding": (
        "Team onboarding guide CRUD consumer",
        "allow_team_onboarding policy 通过后，10 s timeout + beta header 执行 list/create/update/delete；create/update 上传 ONBOARDING.md 内容，失败不产生本地成功链接。",
        "组织权限、分享链接访问、版本冲突和远端内容保留属于服务端。",
    ),
    "/api/organizations/:orgUUID/cowork/remote_devices": (
        "Cowork trusted-device registration consumer",
        "客户端先生成并持久化私钥，再 POST display_name/platform/public_key，teleport-org auth、beta header、10 s timeout。只有 201 + 合法 UUID 才缓存 row ID；device limit、账号失效和 server-revoked key 分别处理。",
        "远端设备风控、撤销传播、数量限制和 session binding 验证由账号服务拥有。",
    ),
    "/api/ws/speech_to_text/voice_stream": (
        "Voice WebSocket streaming consumer",
        "语音输入 owner 把该 path 与一方 host 组合为 WebSocket，完成 auth、audio chunk streaming、transcript event 与本地 retry/circuit-breaker；它不是普通 JSON POST。",
        "真实麦克风权限、音频质量、服务端转写、保留与账号 entitlement 需运行验证。",
    ),
}


BETA_IDENTIFIER_DETAILS: dict[str, tuple[str, str, str]] = {
    "advanced-tool-use-2025-11-20": (
        "CLI request beta descriptor",
        "在 release-local registry 中登记为两个 tool_search wire header 之一；Tool Search 开启后，普通 first-party 路径选它，Vertex/Bedrock/Mantle/Gateway 或兼容分支改选 tool-search-tool。",
        "静态 registry 只能证明客户端认识并可选择该 header，不能证明本次请求携带或服务端接受。",
    ),
    "advisor-tool-2026-03-01": (
        "CLI request beta descriptor",
        "登记为 advisor_tool header；query 仅在 Advisor gate 与 first-party 条件通过时加入 beta，同时装配 advisor_20260301 server tool schema，400 compatibility latch 可再剥离。",
        "不能由 descriptor 推断 server tool 已执行、产生建议或被当前账号开放。",
    ),
    "afk-mode-2026-01-31": (
        "CLI request beta descriptor",
        "登记为 afk_mode header；Agentic query、Auto/AFK gate 与 sticky state 通过后加入 request，Bedrock 还可改写进 body.anthropic_beta。",
        "registry 不证明 AFK query 已触发、后台结果已生成或远端状态已持久化。",
    ),
    "agent-memory-2026-07-22": (
        "Bundled Anthropic SDK memory-store surface",
        "打包 TypeScript SDK 的 memory stores、memories 和 versions CRUD 方法会自动附加该 header；未仅凭这些 SDK 类升级为 Claude Code 产品 consumer。",
        "SDK resource 随包存在不证明 CLI Agent Loop 调用它，也不证明任何远端 memory store 已创建。",
    ),
    "auto-mode-classifier-2026-07-16": (
        "CLI request beta descriptor",
        "登记为 auto_mode_classifier header；classifier request 只有 first-party、可用内部 API 条件通过时返回这一项 beta，否则返回空集合并走 fail-closed。",
        "descriptor 不证明分类请求发生，更不证明某条命令被服务端判定为危险。",
    ),
    "bedrock-2023-05-31": (
        "AWS Bedrock protocol version",
        "这是 Bedrock request body 的 anthropic_version 值；provider middleware 与 CountTokens payload 写入它，不是 anthropic-beta header。",
        "客户端协议版本可证，Bedrock 模型执行、账号权限和响应语义仍由 AWS/上游服务拥有。",
    ),
    "cache-diagnosis-2026-04-07": (
        "CLI request beta descriptor",
        "登记为 cache_diagnosis header；cache-diagnosis gate 置入 sticky beta，request 装配时加入，明确 400 拒绝后删除 latch 并重试。",
        "registry 不证明诊断已运行，也不能把内嵌 SDK 示例当成本版 CLI 的 runtime outcome。",
    ),
    "ccr-byoc-2025-07-29": (
        "CLI descriptor + direct Remote/CCR consumer",
        "既登记为 ccr_byoc descriptor，也被 Remote environment、self-hosted runner 和 bridge session 的直接 HTTP consumer 写入 anthropic-beta。",
        "header 写入可证；远端 session、runner、environment 创建和授权结果仍需网络/账号 Probe。",
    ),
    "ccr-triggers-2026-01-30": (
        "Direct Remote trigger consumer",
        "Remote trigger 列表 GET 直接把该值写入 anthropic-beta；它不经过通用 model beta registry。",
        "客户端请求合同可证，trigger entitlement、列表内容和后续触发副作用属于远端服务。",
    ),
    "code-execution-2025-08-25": (
        "Embedded SDK/skill reference text",
        "只在随包 SDK 教学/skill 参考文本中作为旧版 code-execution 示例出现，没有本版 Claude Code runtime literal consumer。",
        "可证明参考材料随包发布，不能证明 CLI 发送该 header 或启用了对应 server tool。",
    ),
    "compact-2026-01-12": (
        "Embedded SDK/skill reference text",
        "只在随包 SDK 教学/skill 参考文本的 API compaction 示例中出现；本版 `/compact` 客户端压缩流程不依赖这个 header。",
        "不能把 SDK 的服务端 context-management 示例倒推成 Claude Code `/compact` 的实现。",
    ),
    "computer-use-2025-11-24": (
        "Embedded SDK/skill reference text",
        "只在随包 SDK 教学/skill 参考文本中出现，没有已确认的 Claude Code runtime header consumer。",
        "参考文本不证明 computer-use tool 在本版 CLI 被装配、发送或授权。",
    ),
    "context-1m-2025-08-07": (
        "CLI descriptor + output-schema declaration",
        "登记为 long_context header，并在 SDK/output schema 中声明为可见字面值；model beta builder 仅在长上下文模型 gate 通过时加入，Bedrock 会把它移到 extra body。",
        "schema 声明不是第二个 direct consumer；是否发送、是否获得 1M window 和最终计费仍需 request/response 证据。",
    ),
    "context-hint-2026-04-09": (
        "CLI request beta descriptor",
        "登记为 context_hint header；仅 first-party 主 REPL 且 hint controller active 时生成 beta，并按可节省 token 阈值决定是否同时发 context_hint body；400/409/529 各自关闭或回退。",
        "registry 不证明 hint 已发出、服务端采用或改变了压缩决策。",
    ),
    "context-management-2025-06-27": (
        "CLI request beta descriptor",
        "登记为 context_management header；model beta builder 检查 provider、模型、API context-management gate 与 fallback 条件后才加入。",
        "descriptor 与内嵌 SDK 文档都不能证明本次服务端 edit 已应用。",
    ),
    "dreaming-2026-04-21": (
        "Bundled Anthropic SDK Dreams surface",
        "打包 TypeScript SDK 的 dreams create/retrieve/list/archive/cancel 方法自动附加该 header；这与 Claude Code 的 Auto Dream 本地 owner 不是同一项证据。",
        "SDK resource 不证明 CLI 调用 Dreams API，也不证明任何 dream 已创建或持久化。",
    ),
    "effort-2025-11-24": (
        "CLI request beta descriptor",
        "登记为 effort header；request normalization 在模型支持时把 effort 写入 output_config，并同步加入该 beta，随后仍受组织 ceiling 与 provider 过滤。",
        "registry 不证明服务端采用了请求 effort，也不证明实际 thinking 深度。",
    ),
    "environments-2025-11-01": (
        "CLI request beta descriptor",
        "登记为 environments header；Environment runner API 的 auth header 直接写入它，并同时携带 runner version 与可选 trusted-device token。",
        "descriptor 不证明远端 environment 已创建、可连接或具有指定网络权限。",
    ),
    "extended-cache-ttl-2025-04-11": (
        "CLI request beta descriptor",
        "登记为 extended_cache_ttl header；只有本地 cache policy 选择 1h 且 first-party 条件通过时才加入 request。",
        "客户端 header 资格不证明服务端 cache 写入、命中、账单或实际 TTL。",
    ),
    "fallback-credit-2026-06-01": (
        "CLI request beta descriptor",
        "登记为 fallback_credit header；mint model/code 与 sticky state 满足时加入 request，错误归因命中后会剥离该 header 并执行一次受控重试。",
        "registry 不证明额度已授予、扣除或服务端完成自动恢复。",
    ),
    "fast-mode-2026-02-01": (
        "CLI request beta descriptor",
        "登记为 speed header；Fast Mode gate 先置 sticky beta，单次 request 再同时写 speed=fast 与该 header，并受模型、账号 opt-in、429/529 cooldown 与 fallback 控制。",
        "UI 开启和 descriptor 存在都不证明服务端采用 fast tier。",
    ),
    "files-api-2025-04-14": (
        "CLI descriptor + SDK/direct Files consumer",
        "既登记为 files_api header，也由打包 SDK Files 方法和 CLI 文件上传/下载 header 组合直接使用；该组合还同时带 oauth header。",
        "客户端传输合同可证，文件扫描、远端保留、跨 session 可见性和最终消费仍属服务端 Boundary。",
    ),
    "fine-grained-tool-streaming-2025-05-14": (
        "Embedded SDK/skill reference text",
        "只在随包 SDK 教学/迁移参考文本中出现，没有本版 CLI runtime literal consumer。",
        "参考文本不能证明 Agent Loop 启用了该 streaming beta 或改变了 tool execution 时点。",
    ),
    "interleaved-thinking-2025-05-14": (
        "CLI request beta descriptor",
        "登记为 interleaved_thinking header；model beta builder 按模型能力与 DISABLE_INTERLEAVED_THINKING gate 加入，Bedrock 将它放进 extra-body beta 集合。",
        "header 资格不证明服务端返回 thinking，也不能绕过签名/opaque block 边界。",
    ),
    "managed-agents-2026-04-01": (
        "Bundled Anthropic SDK Managed Agents surface",
        "打包 TypeScript SDK 的 deployments、agents、environments、sessions、vaults 等方法自动附加该 header。",
        "SDK control plane 随包不证明 Claude Code 当前工作流调用这些方法，远端 agent/session 结果也不可由静态类推断。",
    ),
    "mcp-client-2025-11-20": (
        "Embedded SDK/skill reference text",
        "只在随包 SDK 教学/skill 参考文本中出现，没有 release-local CLI request descriptor 或 direct header consumer。",
        "不能由示例文本推断 MCP client beta 已发送或第三方 MCP server 已支持。",
    ),
    "mcp-servers-2025-12-04": (
        "CLI request beta descriptor",
        "登记为 mcp_servers header；claude.ai connector loader 对 `/v1/mcp_servers?limit=1000` 的直接 GET 写入它，并受 provider、OAuth scope、safe mode 与重试预算保护。",
        "descriptor 不证明任何 MCP server 已连接、tool schema 已常驻或服务端执行成功。",
    ),
    "mcp-tunnels-2026-06-22": (
        "Bundled Anthropic SDK MCP Tunnels surface",
        "打包 TypeScript SDK 的 tunnels/certificates CRUD、token reveal/rotate 方法自动附加该 header。",
        "SDK surface 不证明 CLI 产品调用，也不证明 tunnel、certificate 或 token 已创建。",
    ),
    "message-batches-2024-09-24": (
        "Bundled Anthropic SDK Message Batches surface",
        "打包 TypeScript SDK 的 batch create/retrieve/list/delete/cancel/results 方法自动附加该 header。",
        "SDK surface 不证明 Claude Code Agent Loop 提交 batch；batch 执行和结果存储属于远端服务。",
    ),
    "mid-conversation-system-2026-04-07": (
        "CLI request beta descriptor",
        "登记为 mid_conversation_system header；model beta builder 与 wire normalizer 按模型/turn gate 加入，中途 system 被服务端拒绝后 sticky latch 会阻止再次发送。",
        "descriptor 不证明某一轮实际携带 mid-conversation system block 或服务端采用。",
    ),
    "mid-conversation-tool-changes-2026-07-01": (
        "Embedded SDK/skill reference text",
        "只在随包 SDK 教学/迁移参考文本中出现；本版 Tool Search/deferred tool 机制不能仅凭该字符串归因到这个 beta。",
        "参考文本不证明 request-time tool changes header 已发送或服务端支持。",
    ),
    "oauth-2025-04-20": (
        "CLI OAuth descriptor + SDK/direct auth consumer",
        "常量先进入 oauth_auth descriptor registry；SDK OAuth token exchange 与 CLI 文件传输 header 组合也直接使用它。registry 处通过变量引用，因此不能只靠 literal 行号扫描。",
        "客户端 OAuth 协议可证，grant 接受、scope、账号身份与 token 生命周期由身份服务决定。",
    ),
    "oidc-federation-2026-04-01": (
        "Bundled SDK OIDC federation auth consumer",
        "打包 OAuth provider 在 JWT bearer/OIDC federation token exchange 时与 oauth beta 一起写入 anthropic-beta；它不是普通 beta resource CRUD。",
        "SDK auth flow 可证，外部 IdP 签发、MFA、风险判断和 token 接受仍是服务端 Boundary。",
    ),
    "output-128k-2025-02-19": (
        "Embedded SDK/skill reference text",
        "只在随包 SDK 教学/迁移参考文本中出现，且相邻新文档明确说明新模型的 128k output 不再依赖该旧 header。",
        "不能据此声称本版 CLI 发送旧 header 或当前模型获得 128k 输出。",
    ),
    "per-turn-control-2026-07-01": (
        "CLI request beta descriptor",
        "登记为 per_message_effort header；Agentic request 满足模型/turn 条件时加入，明确拒绝后从当次 beta 集合删除并记录 server_rejected latch。",
        "descriptor 不证明每轮 control 被服务端采用，也不替代本地 effort precedence 证据。",
    ),
    "pre-2026-07-28": (
        "MCP protocol-era label",
        "这是 MCP server/discover 版本协商中的 legacy era 边界文本，用于 fallback/error；不是 Anthropic API beta header。",
        "只能证明客户端如何命名旧 MCP 协议时代，不能证明某个 server 当前属于该 era。",
    ),
    "prompt-caching-evict-2026-05-12": (
        "CLI request beta descriptor",
        "登记为 prompt_caching_evict header；仅 evictCacheOnComplete、sticky state 与 gate 同时满足时加入，并把 cache_control.evict_on_complete 写进 request。",
        "descriptor 不证明服务端执行 eviction，也不证明后续 cache miss 的唯一原因。",
    ),
    "prompt-caching-scope-2026-01-05": (
        "CLI request beta descriptor",
        "登记为 prompt_caching_scope header；first-party model beta builder 默认候选，Tool Search/MCP cache layout 还会在需要 global scope 时确保它存在。",
        "header 存在不证明 scope 命中、复用或账单结果。",
    ),
    "redact-thinking-2026-02-12": (
        "CLI request beta descriptor",
        "登记为 redact_thinking header；first-party thinking-capable request 先加入，若客户端要求显示 thinking，request normalization 会把它移除。",
        "descriptor 不证明 thinking 被生成、展示或服务端完成了特定 redaction。",
    ),
    "server-side-fallback-2026-06-01": (
        "CLI request beta descriptor",
        "登记为 server_side_fallback header；fallback planner 根据模型、sticky state、silent arm 和 default/explicit mode 加入，错误分类可剥离并重试。",
        "客户端请求资格不证明服务端发生 fallback、选中哪个模型或是否产生费用。",
    ),
    "server-side-fallback-2026-06-09": (
        "Embedded SDK/skill reference text",
        "只在随包 SDK 教学/迁移参考文本中出现；release-local CLI registry 使用的是 2026-06-01 和 2026-07-01 两个不同 header。",
        "不能把文档中的中间版本写成当前 CLI runtime descriptor。",
    ),
    "server-side-fallback-2026-07-01": (
        "CLI request beta descriptor",
        "登记为 server_side_fallback_category header；default category fallback 路径选择它，与 2026-06-01 的显式/兼容 fallback descriptor 分开处理和剥离。",
        "两个 descriptor 都不证明服务端实际 fallback 或 category 判定结果。",
    ),
    "skills-2025-10-02": (
        "Bundled Anthropic SDK Skills surface",
        "打包 TypeScript SDK 的 skills/versions create、retrieve、list、delete、download 方法自动附加该 header；内嵌教学也用它演示 Agent Skills。",
        "SDK 与示例存在不证明 Claude Code 本地 Skill 系统调用远端 Skills API。",
    ),
    "structured-outputs-2025-11-13": (
        "Embedded SDK/skill reference text",
        "只在随包 SDK 教学/迁移参考文本中出现；不是 release-local CLI registry 采用的 structured outputs header。",
        "不能据此声称本版 CLI 发送该旧版本 header。",
    ),
    "structured-outputs-2025-12-15": (
        "CLI descriptor + bundled SDK parse consumer",
        "既登记为 structured_outputs header，也由打包 SDK beta.messages.parse 自动附加；CLI 只有 output format、模型支持与 feature gate 同时满足时才写 output_config.format 并加入该 beta。",
        "本地 schema/parse 与 header 可证，服务端 constrained decoding 和业务真实性仍是 Boundary。",
    ),
    "task-budgets-2026-03-13": (
        "CLI request beta descriptor",
        "登记为 task_budgets header；request normalization 在 first-party 且存在 taskBudget 时写 output_config.task_budget，并确保该 beta 只加入一次。",
        "descriptor 不证明远端执行预算、强制停止或产生对应 usage。",
    ),
    "thinking-token-count-2026-05-13": (
        "CLI request beta descriptor",
        "登记为 thinking_token_count header；model beta builder 仅在 first-party、thinking-capable 且 release gate 存在时加入。",
        "header 候选不证明返回了独立 thinking token 计数或账单字段。",
    ),
    "token-counting-2024-11-01": (
        "Bundled Anthropic SDK token-counting surface",
        "打包 TypeScript SDK 的 beta messages countTokens 方法自动附加该 header；CLI 自己的 count path 是否走该方法需看 provider 分支。",
        "SDK method 不证明本次计数请求成功，也不等同最终计费。",
    ),
    "token-efficient-tools-2025-02-19": (
        "Embedded SDK/skill reference text",
        "只在随包 SDK 教学/迁移参考文本中出现，没有 release-local CLI descriptor 或 direct consumer。",
        "不能由旧示例推断本版 tool schema/token 行为由该 header 驱动。",
    ),
    "tool-search-tool-2025-10-19": (
        "CLI request beta descriptor",
        "在 registry 中登记为另一个 tool_search header；Tool Search 开启后，Vertex/Bedrock/Mantle/Gateway 或兼容分支选择它，普通 first-party 路径选择 advanced-tool-use。",
        "descriptor 存在不等于所有 deferred tool schema 常驻，也不证明 ToolSearch 本轮被调用。",
    ),
    "user-profiles-2026-03-24": (
        "Bundled Anthropic SDK User Profiles surface",
        "打包 TypeScript SDK 的 user profiles create/retrieve/update/list/enrollment URL 方法自动附加该 header。",
        "SDK surface 不证明 Claude Code 产品使用 user profile 资源或本次消息携带 profile id。",
    ),
    "vertex-2023-10-16": (
        "Google Vertex protocol version",
        "这是 Vertex provider middleware 写入请求 body 的 anthropic_version 值，不是 anthropic-beta header。",
        "客户端协议改写可证，Vertex 模型执行、IAM、region 与响应语义仍由 Google/上游服务拥有。",
    ),
    "web-search-2025-03-05": (
        "CLI request beta descriptor",
        "登记为 web_search header；model beta builder 对 Vertex 的兼容模型和 Foundry provider 明确加入，其他 provider 不因字符串存在而自动发送。",
        "descriptor 不证明 web search tool 被装配、调用、产生引用或服务端保留查询。",
    ),
}


BETA_EVIDENCE_LINES: dict[str, list[int]] = {
    "advanced-tool-use-2025-11-20": [68930, 71317],
    "advisor-tool-2026-03-01": [68930, 409380],
    "afk-mode-2026-01-31": [68930, 409437, 409494, 409467],
    "agent-memory-2026-07-22": [11427],
    "auto-mode-classifier-2026-07-16": [68930, 326213],
    "bedrock-2023-05-31": [219431, 370539],
    "cache-diagnosis-2026-04-07": [68930, 409441, 409505, 409728],
    "ccr-byoc-2025-07-29": [68930, 204505, 204648, 268774],
    "ccr-triggers-2026-01-30": [204524],
    "code-execution-2025-08-25": [574104],
    "compact-2026-01-12": [565430],
    "computer-use-2025-11-24": [571524],
    "context-1m-2025-08-07": [68930, 71336, 595960],
    "context-hint-2026-04-09": [68930, 408938],
    "context-management-2025-06-27": [68930, 71341],
    "dreaming-2026-04-21": [9799],
    "effort-2025-11-24": [68930, 409052, 409053],
    "environments-2025-11-01": [68930, 413396],
    "extended-cache-ttl-2025-04-11": [68930, 409497],
    "fallback-credit-2026-06-01": [68930, 266705, 409473, 409573],
    "fast-mode-2026-02-01": [68930, 409439, 409493],
    "files-api-2025-04-14": [9862, 68930, 209365],
    "fine-grained-tool-streaming-2025-05-14": [570656],
    "interleaved-thinking-2025-05-14": [68930, 71337],
    "managed-agents-2026-04-01": [9743],
    "mcp-client-2025-11-20": [565983],
    "mcp-servers-2025-12-04": [68930, 273581],
    "mcp-tunnels-2026-06-22": [12528],
    "message-batches-2024-09-24": [11547],
    "mid-conversation-system-2026-04-07": [68930, 71347, 409004, 409413],
    "mid-conversation-tool-changes-2026-07-01": [571278],
    "oauth-2025-04-20": [8756, 17163, 68930, 209365],
    "oidc-federation-2026-04-01": [8756],
    "output-128k-2025-02-19": [570659],
    "per-turn-control-2026-07-01": [68930, 71367, 409576, 409579],
    "pre-2026-07-28": [151496, 152465],
    "prompt-caching-evict-2026-05-12": [68930, 409442, 409502],
    "prompt-caching-scope-2026-01-05": [68930, 71346, 409403],
    "redact-thinking-2026-02-12": [68930, 71338, 409485],
    "server-side-fallback-2026-06-01": [68930, 266695, 266697, 409549],
    "server-side-fallback-2026-06-09": [571716],
    "server-side-fallback-2026-07-01": [68930, 266695, 266697, 409556],
    "skills-2025-10-02": [12468],
    "structured-outputs-2025-11-13": [565822],
    "structured-outputs-2025-12-15": [12300, 68930, 409061],
    "task-budgets-2026-03-13": [68930, 409057],
    "thinking-token-count-2026-05-13": [68930, 71339],
    "token-counting-2024-11-01": [12307],
    "token-efficient-tools-2025-02-19": [570658],
    "tool-search-tool-2025-10-19": [68930, 71315, 71316],
    "user-profiles-2026-03-24": [9906],
    "vertex-2023-10-16": [230649],
    "web-search-2025-03-05": [68930, 71344, 71345],
}


BETA_DESCRIPTOR_SYMBOLS: dict[str, str] = {
    "advanced-tool-use-2025-11-20": "_Ws",
    "advisor-tool-2026-03-01": "bWs",
    "afk-mode-2026-01-31": "uq",
    "auto-mode-classifier-2026-07-16": "CWs",
    "cache-diagnosis-2026-04-07": "But",
    "ccr-byoc-2025-07-29": "wWs",
    "context-1m-2025-08-07": "cK",
    "context-hint-2026-04-09": "SWs",
    "context-management-2025-06-27": "tJt",
    "effort-2025-11-24": "wOr",
    "environments-2025-11-01": "TWs",
    "extended-cache-ttl-2025-04-11": "rJt",
    "fallback-credit-2026-06-01": "XJ",
    "fast-mode-2026-02-01": "COr",
    "files-api-2025-04-14": "vWs",
    "interleaved-thinking-2025-05-14": "vOr",
    "mcp-servers-2025-12-04": "ykn",
    "mid-conversation-system-2026-04-07": "zW",
    "oauth-2025-04-20": "kxt",
    "per-turn-control-2026-07-01": "JJ",
    "prompt-caching-evict-2026-05-12": "$ut",
    "prompt-caching-scope-2026-01-05": "EOr",
    "redact-thinking-2026-02-12": "gkn",
    "server-side-fallback-2026-06-01": "qW",
    "server-side-fallback-2026-07-01": "JR",
    "structured-outputs-2025-12-15": "hDe",
    "task-budgets-2026-03-13": "Ajo",
    "thinking-token-count-2026-05-13": "Rjo",
    "tool-search-tool-2025-10-19": "TOr",
    "web-search-2025-03-05": "hkn",
}


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def replace_block(text: str, start: str, end: str, body: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    replacement = f"{start}\n{body.rstrip()}\n{end}"
    updated, count = pattern.subn(replacement, text)
    if count != 1:
        raise ValueError(f"marker block {start}..{end} occurs {count} times")
    return updated


def readable_occurrences(readable: Path, values: list[str], quoted: bool) -> dict[str, list[int]]:
    source = readable.read_text(encoding="utf-8", errors="replace")
    starts = [0]
    starts.extend(match.end() for match in re.finditer("\n", source))
    alternative = "|".join(sorted((re.escape(value) for value in values), key=len, reverse=True))
    if quoted:
        pattern = re.compile(r"([\"'])(?P<value>" + alternative + r")\1")
    else:
        pattern = re.compile(r"(?<![a-z0-9-])(?P<value>" + alternative + r")(?![a-z0-9-])")
    result = {value: [] for value in values}
    for match in pattern.finditer(source):
        line = bisect.bisect_right(starts, match.start())
        if not result[match.group("value")] or result[match.group("value")][-1] != line:
            result[match.group("value")].append(line)
    return result


def api_group(path: str) -> tuple[str, str, str]:
    if path in API_PATH_DETAILS:
        return API_PATH_DETAILS[path]
    if path == "/v1/token":
        return (
            "Bundled dependency",
            "Google/AWS credential dependency 的 token endpoint；没有 Claude Code 产品 consumer。",
            "只能证明依赖随包存在，不能当 Claude/CCR API。",
        )
    if path == "/v1/metrics":
        return (
            "OTEL exporter + bundled gateway forward handler + local runner handler",
            "客户端 OTEL exporter 可向该 path 发 metrics；Gateway 接收后异步 fanout；self-hosted runner 还在 loopback listener 接收最大 1 MiB 的 OTLP/JSON metrics。",
            "Gateway 返回 200 不证明下游 Collector 已接收；runner listener 也不等于公网 exporter。",
        )
    if path in {"/v1/logs", "/v1/traces"}:
        return (
            "OTEL exporter + bundled gateway forward handler",
            "客户端 OTEL exporter 可向该 path 发 payload；Gateway handler 鉴权后立即应答并在后台 fanout 到对应 Collector。",
            "本地 handler 可证，但 Collector 的接收、采样、保留和导出仍是外部 Boundary。",
        )
    if path == "/v1/messages":
        return (
            "Bundled SDK + CLI consumer + bundled gateway handler",
            "CLI Agent Loop 通过 SDK 发 Messages；同一发布物的 Enterprise Gateway 校验身份/策略/花费、映射模型并代理到 operator upstream。",
            "本地 Gateway handler 可证；Anthropic/Bedrock/Vertex/Foundry 的模型执行和账号权限仍是远端 Boundary。",
        )
    if path == "/v1/messages/count_tokens":
        return (
            "Bundled SDK + CLI consumer + bundled gateway handler",
            "CLI token 估算链调用 SDK 或 direct HTTP；Enterprise Gateway handler 代理 Anthropic/Vertex/Foundry，Bedrock 分支明确返回 501。",
            "本地路由和 501 分支可证；各 upstream 的计数实现与结果仍是远端 Boundary。",
        )
    if path == "/v1/models":
        return (
            "Bundled SDK + CLI consumer + bundled gateway handler",
            "SDK 提供 models list；CLI gateway provider 可做动态发现；Enterprise Gateway handler 按配置、provider 与 policy allowlist 返回模型目录。",
            "本地目录生成可证；远端模型实际可用性和 entitlement 仍需运行验证。",
        )
    if path == "/v1/complete":
        return (
            "Bundled SDK + provider middleware surface",
            "打包 Anthropic SDK 保留 legacy Complete method，Bedrock middleware 也识别该 path；未找到 Claude Code Agent Loop 的直接产品调用。",
            "SDK/middleware surface 不能升级为本版 CLI 正在使用 legacy Completions。",
        )
    if path == "/v1/messages/batches":
        return (
            "Bundled Anthropic SDK",
            "打包 SDK 实现 Message Batches create/list 等方法；未找到 Claude Code 产品层直接 consumer。",
            "SDK method 随包存在不证明 CLI UI、命令或 Agent Loop 会提交 batch。",
        )
    if path == "/v1/oauth/token":
        return (
            "Bundled SDK + CLI OAuth consumer",
            "Anthropic SDK OAuth provider 和 CLI first-party login 都使用该 token exchange path；实际 host 由登录环境选择。",
            "客户端 exchange 可证，不证明身份服务接受 grant、scope 或账号权限。",
        )
    if path == "/v1/sessions":
        return (
            "SDK + Remote session consumer",
            "Managed Agents SDK 和 Claude Code Remote/CCR 都保留 sessions 语义，host/auth 不同。",
            "同名 path 不能合并成同一个服务端资源。",
        )
    if path == "/.well-known/oauth-authorization-server":
        return (
            "OAuth discovery consumer + bundled gateway handler",
            "CLI/依赖构造 RFC 8414 discovery candidate；Enterprise Gateway 同时在该 path 返回自身 issuer、device/token endpoints 与协议版本。",
            "发布物内 handler 可证；外部 gateway 的 metadata、网络可达性与 issuer 信任结果仍需运行验证。",
        )
    if path.startswith("/.well-known/"):
        return (
            "OAuth/OIDC discovery",
            "客户端构造 discovery candidate，读取 metadata 后再选择 authorization/token endpoint。",
            "metadata 内容和 issuer 信任结果属于运行时与服务端。",
        )
    if path == "/oauth/callback":
        return (
            "Bundled gateway OAuth callback handler",
            "Enterprise Gateway 接收 IdP code callback，校验 state/nonce/PKCE 与 browser binding，再把 device grant 更新为 complete/denied。",
            "Gateway callback 可证；IdP 的登录、MFA、风险判断和 code 签发仍是外部 Boundary。",
        )
    if path == "/oauth/device_authorization":
        return (
            "Gateway auth consumer + bundled device handler",
            "CLI 从 Gateway metadata 解析或回退到该 endpoint；Gateway handler 创建带 TTL/rate-limit 的 device grant 与 user code。",
            "客户端与本地 handler 可证；真实用户授权和 IdP session 仍需端到端验证。",
        )
    if path == "/oauth/token":
        return (
            "OAuth consumer + bundled gateway token handler",
            "客户端执行 device/refresh grant；Gateway handler 处理 pending、slow_down、denied、refresh 与 session JWT 签发。",
            "本地协议状态机可证；外部 IdP refresh/token 策略仍是 Boundary。",
        )
    if path in {"/v1/mcp/{server_id}", "/v1/toolbox/shttp/mcp/{server_id}"}:
        return (
            "MCP proxy configuration",
            "first-party/custom OAuth config 选择的 MCP proxy path template。",
            "具体 server_id、目标 MCP server 与 proxy handler 不在快照内。",
        )
    if path == "/managed/settings":
        return (
            "CLI managed-policy consumer + bundled gateway handler",
            "CLI 拉取并合并 managed policy；Enterprise Gateway 按 session claims 选择首个 policy，支持 ETag/304，并可注入 OTEL 环境。",
            "本地 serve/merge 可证；部署时实际 policy 内容与身份分组仍需运行证据。",
        )
    if path.endswith("/"):
        if path.startswith(("/v1/code/", "/v2/ccr-sessions/", "/v2/session_ingress/")):
            owner = "Remote/CCR route prefix"
        elif path.startswith(("/api/frame/", "/v1/design/")):
            owner = "Frame/Design route prefix"
        else:
            owner = "Route prefix/allowlist"
        return (
            owner,
            "该固定值作为 prefix、host-routing allowlist 或 normalization anchor；具体请求通常由模板补全。",
            "不能把 prefix 本身当成可独立调用 endpoint。",
        )
    if path.startswith("/worker/"):
        return (
            "Worker direct consumer",
            "CCR worker 的 event/file/heartbeat/internal-event/skill-manifest 调用面。",
            "session JWT、worker epoch 和远端处理结果需运行验证。",
        )
    if path.startswith(("/v1/code/", "/v2/ccr-sessions/", "/v2/session_ingress/")):
        return (
            "Remote/CCR direct consumer",
            "Remote session、trigger、agent proxy、memory、SCM tunnel 或 ingress 的客户端调用/路由常量。",
            "远端 session owner、授权与持久化属于服务端 Boundary。",
        )
    if path.startswith(("/api/frame/", "/v1/design/", "/v1/filestore/")):
        return (
            "Frame/Design/Artifact consumer",
            "Frame deploy/upload/track、Design consent/grants/MCP 或 artifact file read 的直接 consumer。",
            "deploy/asset 服务端状态和不可逆副作用需端到端验证。",
        )
    if path.startswith("/api/event_logging/"):
        return (
            "First-party event transport",
            "一方事件 batch endpoint 或其 routing prefix。",
            "事件是否启用、采样、字段和持久化不能由 path 单独证明。",
        )
    if path.startswith("/api/ws/speech_to_text/"):
        return (
            "Voice WebSocket consumer",
            "语音流的 WebSocket endpoint。",
            "语音服务可用性、音频保留和转写质量属于运行/服务端。",
        )
    if path.startswith("/v1/ultrareview/"):
        return (
            "Ultrareview direct consumer",
            "云端 review preflight/quota 的客户端检查。",
            "quota、findings 和评论副作用由远端服务决定。",
        )
    if path == "/v1/organizations/spend_limits":
        return (
            "Bundled gateway admin handler",
            "Enterprise Gateway 的 spend-limit admin 根路由，覆盖 list/upsert，并以同一 prefix 派生 effective、audit 和按 ID 删除。",
            "本地 Postgres handler、鉴权与事务可证；部署数据、管理员身份和外部账单不在快照中。",
        )
    if path.startswith("/api/"):
        return (
            "First-party product consumer",
            "Claude.ai/组织/billing/onboarding/plugin/skill/feedback/notification 等客户端直接调用或固定 resource。",
            "`:orgUUID` 由 wrapper 解析；授权、rollout 和写入结果属于服务端。",
        )
    return (
        "Client route surface",
        "发布 bundle 中的固定 path，由相邻 wrapper/consumer 决定 method、auth 和 response。",
        "仅凭固定字符串不证明运行时可达或服务端实现。",
    )


def beta_group(identifier: str) -> tuple[str, str, str]:
    try:
        return BETA_IDENTIFIER_DETAILS[identifier]
    except KeyError as error:
        raise ValueError(f"unclassified beta identifier: {identifier}") from error


def build_api_catalog(repo: Path) -> str:
    inventory = repo / "analysis/source-inventory"
    paths = (inventory / "api-paths.txt").read_text(encoding="utf-8").splitlines()
    first_party_paths = [path for path in paths if path.startswith("/api/")]
    missing_first_party = [
        path for path in first_party_paths if path not in API_PATH_DETAILS
    ]
    if len(first_party_paths) != 46 or len(API_PATH_DETAILS) != 46:
        raise ValueError(
            "first-party API ownership map count drift: "
            f"inventory={len(first_party_paths)}, mapped={len(API_PATH_DETAILS)}"
        )
    if missing_first_party:
        raise ValueError(
            "unclassified first-party API paths: " + ", ".join(missing_first_party)
        )
    readable = readable_occurrences(repo / "reverse/javascript/cli.readable.js", paths, quoted=True)
    canonical: dict[str, list[dict]] = {}
    wanted = set(paths)
    for row in read_jsonl(inventory / "static-string-literals.jsonl"):
        value = row.get("value", {}).get("text")
        if value in wanted:
            canonical[value] = row.get("locations", [])
    rows = [
        "| # | Path | consumer/所有权 | 客户端语义 | 提取与 consumer 锚点 | Boundary |",
        "| ---: | --- | --- | --- | --- | --- |",
    ]
    for index, path in enumerate(paths, 1):
        owner, meaning, boundary = api_group(path)
        inv = f"[inventory L{index}](source-inventory/api-paths.txt#L{index})"
        locations = canonical.get(path, [])
        if locations:
            loc = locations[0]
            anchor = f"[canonical L{loc['line']}:C{loc['column']}](../extracted/cli.js#L{loc['line']})"
        else:
            anchor = "canonical inventory"
        readable_lines = readable.get(path, [])
        selected_lines = API_EVIDENCE_LINES.get(path, readable_lines[:3])
        if selected_lines:
            read = ", ".join(
                f"[readable L{line}](../reverse/javascript/cli.readable.js#L{line})"
                for line in selected_lines
            )
        else:
            read = "无 exact quoted readable hit"
        rows.append(
            f"| {index} | `{path}` | {owner} | {meaning} | {inv}; {anchor}; {read} | {boundary} |"
        )
    return "\n".join(rows)


def build_beta_catalog(repo: Path) -> str:
    inventory_path = repo / "analysis/source-inventory/anthropic-beta-identifiers.txt"
    identifiers = inventory_path.read_text(encoding="utf-8").splitlines()
    identifier_set = set(identifiers)
    detail_set = set(BETA_IDENTIFIER_DETAILS)
    evidence_set = set(BETA_EVIDENCE_LINES)
    if len(identifiers) != 53 or len(identifier_set) != len(identifiers):
        raise ValueError(
            f"beta identifier inventory count/uniqueness drift: rows={len(identifiers)}, unique={len(identifier_set)}"
        )
    if detail_set != identifier_set:
        missing = sorted(identifier_set - detail_set)
        extra = sorted(detail_set - identifier_set)
        raise ValueError(f"beta ownership map drift: missing={missing}, extra={extra}")
    if evidence_set != identifier_set:
        missing = sorted(identifier_set - evidence_set)
        extra = sorted(evidence_set - identifier_set)
        raise ValueError(f"beta evidence map drift: missing={missing}, extra={extra}")
    readable_path = repo / "reverse/javascript/cli.readable.js"
    readable_source_lines = readable_path.read_text(
        encoding="utf-8", errors="replace"
    ).split("\n")
    readable = readable_occurrences(readable_path, identifiers, quoted=False)
    rows = [
        "| # | Identifier | 权威分类 | runtime/声明语义 | 证据锚点 | Boundary |",
        "| ---: | --- | --- | --- | --- | --- |",
    ]
    for index, identifier in enumerate(identifiers, 1):
        lines = readable.get(identifier, [])
        if not lines:
            raise ValueError(f"beta identifier has no readable literal evidence: {identifier}")
        selected_lines = BETA_EVIDENCE_LINES[identifier]
        if not set(selected_lines).intersection(lines):
            raise ValueError(
                f"beta evidence anchors have no literal hit for {identifier}: anchors={selected_lines}, literals={lines}"
            )
        descriptor_symbol = BETA_DESCRIPTOR_SYMBOLS.get(identifier)
        for line in selected_lines:
            if line < 1 or line > len(readable_source_lines):
                raise ValueError(
                    f"beta evidence anchor is outside readable source for {identifier}: L{line}"
                )
            if line in lines:
                continue
            source_line = readable_source_lines[line - 1]
            if descriptor_symbol is None or descriptor_symbol not in source_line:
                raise ValueError(
                    f"beta indirect anchor is stale for {identifier}: L{line} does not contain {descriptor_symbol!r}"
                )
        authority, meaning, boundary = beta_group(identifier)
        inv = f"[inventory L{index}](source-inventory/anthropic-beta-identifiers.txt#L{index})"
        anchors = ", ".join(
            f"[L{line}](../reverse/javascript/cli.readable.js#L{line})"
            for line in selected_lines
        )
        remaining = len(set(lines) - set(selected_lines))
        if remaining > 0:
            anchors += f" +{remaining} additional literal hits"
        rows.append(
            f"| {index} | `{identifier}` | {authority} | {meaning} | {inv}; {anchors or 'no readable token hit'} | {boundary} |"
        )
    return "\n".join(rows)


def diagnostic_level(row: dict) -> str:
    for argument in row.get("arguments", [])[1:]:
        source = argument.get("source", {}).get("text", "")
        match = re.search(r"level\s*:\s*[\"']([^\"']+)", source)
        if match:
            return match.group(1)
    return "default-debug"


def build_metrics(repo: Path) -> str:
    inventory = repo / "analysis/source-inventory"
    errors = list(read_jsonl(inventory / "error-message-callsites.jsonl"))
    diagnostics = list(read_jsonl(inventory / "diagnostic-message-callsites.jsonl"))
    role_counts = Counter(row.get("calleeRole") for row in errors)
    error_kinds = Counter(row.get("nameArgument", {}).get("kind") for row in errors)
    diagnostic_kinds = Counter(
        row.get("nameArgument", {}).get("kind") for row in diagnostics
    )
    levels = Counter(diagnostic_level(row) for row in diagnostics)
    level_order = ["default-debug", "verbose", "debug", "info", "warn", "error"]
    error_kind_text = ", ".join(
        f"`{key}` {value:,}" for key, value in error_kinds.most_common()
    )
    diagnostic_kind_text = ", ".join(
        f"`{key}` {value:,}" for key, value in diagnostic_kinds.most_common()
    )
    level_text = ", ".join(
        f"`{key}` {levels[key]:,}" for key in level_order if levels[key]
    )
    return "\n".join(
        [
            f"- constructor callsites 共 **{len(errors):,}**：`Error` **{role_counts['Error']:,}**、`TypeError` **{role_counts['TypeError']:,}**、`RangeError` **{role_counts['RangeError']:,}**；三者合计必须等于总数。",
            f"- constructor message argument shape：{error_kind_text}。`missing` 或动态表达式表示静态阶段拿不到最终 message，不表示没有错误。",
            f"- diagnostic `T()` callsites 共 **{len(diagnostics):,}**；显式/默认 level：{level_text}。没有第二参数时由 `T()` 默认成 debug。",
            f"- diagnostic message argument shape：{diagnostic_kind_text}。template 占多数，说明最终日志常带运行时 path/status/id，公开时不能只扫描固定 literal。",
        ]
    )


def validate_contract(repo: Path, api_doc: str, error_doc: str) -> list[str]:
    failures: list[str] = []
    requirements = {
        "analysis/api-beta-route-ownership.md": [
            "**读者问题：**",
            "**一句话模型：**",
            "服务端 Boundary",
            "失败、恢复与用户影响",
            "全量 API path 目录",
            "全量 Beta/version identifier 目录",
            "发布物内服务端 handler",
            "Bundled gateway admin handler",
            "Static：",
            "Boundary：",
        ],
        "analysis/error-diagnostic-atlas.md": [
            "**读者问题：**",
            "**一句话模型：**",
            "五层状态归属",
            "Debug logger",
            "用户症状与恢复决策表",
            "Static：",
            "Boundary：",
        ],
    }
    texts = {
        "analysis/api-beta-route-ownership.md": api_doc,
        "analysis/error-diagnostic-atlas.md": error_doc,
    }
    for relative, terms in requirements.items():
        for term in terms:
            if term not in texts[relative]:
                failures.append(f"{relative}: missing required term {term}")
    if len(api_doc) < 30000:
        failures.append("analysis/api-beta-route-ownership.md: expected Deep catalog and explanation")
    if len(error_doc) < 14000:
        failures.append("analysis/error-diagnostic-atlas.md: expected Deep mechanism explanation")
    for stem in ("api-beta-route-ownership-lifecycle", "error-diagnostic-atlas-lifecycle"):
        for suffix in ("dot", "svg"):
            path = repo / f"analysis/visuals/{stem}.{suffix}"
            if not path.is_file() or path.stat().st_size == 0:
                failures.append(f"missing or empty analysis/visuals/{stem}.{suffix}")
    for relative, text in texts.items():
        if re.search(r"/(?:Users|home)/[^/\s]+/", text):
            failures.append(f"{relative}: capture-machine absolute path detected")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    api_path = repo / "analysis/api-beta-route-ownership.md"
    error_path = repo / "analysis/error-diagnostic-atlas.md"
    api_original = api_path.read_text(encoding="utf-8")
    error_original = error_path.read_text(encoding="utf-8")
    try:
        api_expected = replace_block(
            replace_block(
                api_original, API_START, API_END, build_api_catalog(repo)
            ),
            BETA_START,
            BETA_END,
            build_beta_catalog(repo),
        )
        error_expected = replace_block(
            error_original, METRICS_START, METRICS_END, build_metrics(repo)
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"api/error reference generation failed: {error}", file=sys.stderr)
        return 1
    if args.check:
        failures = []
        if api_original != api_expected:
            failures.append("analysis/api-beta-route-ownership.md generated blocks are stale")
        if error_original != error_expected:
            failures.append("analysis/error-diagnostic-atlas.md generated metrics are stale")
        failures.extend(validate_contract(repo, api_original, error_original))
        if failures:
            for failure in failures:
                print(f"FAIL: {failure}", file=sys.stderr)
            return 1
        print("PASS: API/Beta ownership and error/diagnostic atlas references are current")
        return 0
    api_path.write_text(api_expected, encoding="utf-8")
    error_path.write_text(error_expected, encoding="utf-8")
    print("WROTE: analysis/api-beta-route-ownership.md")
    print("WROTE: analysis/error-diagnostic-atlas.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
