# ADR-002: 选择 SSE 而非 WebSocket 做流式推送

- **状态**：✅ 已采纳
- **日期**：2025-06
- **决策者**：项目作者

---

## 背景

RAG 报告生成需要将 LLM 的逐 token 输出实时推送到前端。需要选择一种服务端推送方案。

候选方案对比：

| | SSE | WebSocket | 轮询 |
|---|---|---|---|
| **方向** | 服务端→客户端 | 双向 | 客户端→服务端 |
| **依赖** | 零（HTTP 原生） | 需要库 | 零 |
| **自动重连** | ✅ 原生支持 | ❌ 需手动实现 | - |
| **协议** | HTTP/2 | WS | HTTP |
| **POST 传参** | ✅ fetch+ReadableStream | ✅ | ✅ |

## 决策

**选择 SSE（Server-Sent Events），通过 `fetch` + `ReadableStream` 实现 POST 方式传参。**

原生 `EventSource` API 只支持 GET 请求，而我们的场景需要 POST JSON body 传递品类名。因此使用 `fetch` + `ReadableStream` 手动解析 SSE 流：

```javascript
const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';

function readStream() {
    reader.read().then(({ done, value }) => {
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split('\n\n');
        buffer = events.pop();  // 保留不完整片段
        for (const event of events) {
            // 解析 event: xxx + data: xxx
        }
        readStream();
    });
}
```

## 后果

**正面：**
- 零依赖，HTTP 原生协议，任何浏览器都支持
- `EventSource` 原生自动重连，无需手动实现心跳
- 部署简单——不需要 Nginx 特殊配置 WebSocket 升级

**负面：**
- 单向通信，前端无法在流进行中发送中途取消信号（用 `reader.cancel()` 解决）
- 需手动处理 TCP 分包导致的 SSE 事件截断（`buffer.pop()` 保留不完整片段）
- `decoder.decode(value, { stream: true })` 防止多字节字符（中文）被切断

**缓解措施：**
- `X-Accel-Buffering: no` 头防止 Nginx 反代缓冲（最容易漏掉的配置）
- `state.activeSSE = { cancel: () => reader.cancel() }` 允许用户关闭弹层时中止流

## 备选方案

1. **WebSocket** — 双向通信能力强，但 RAG 只需要服务端单向推送。引入 WebSocket 库增加了复杂度、Nginx 需要 WS 升级配置。过度工程。
2. **轮询** — 延迟高、浪费带宽。不可接受。

## 面试话术

> "RAG 只需要服务端推送，不需要双向通信。SSE 零依赖、原生重连，用 fetch+ReadableStream 解决了 POST 传参的痛点。三个细节：buffer 拼接防 TCP 分包、stream:true 防中文截断、X-Accel-Buffering 防 Nginx 缓冲。每个坑都是真实踩过的。"
