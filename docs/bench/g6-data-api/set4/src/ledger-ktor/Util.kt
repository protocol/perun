package ledger

import io.ktor.client.*
import io.ktor.client.engine.cio.*
import io.ktor.client.plugins.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.server.application.*
import io.ktor.server.response.*

const val VENDOR = "https://dispatch.vendor.example.com"
val VENDOR_KEY: String = System.getenv("DISPATCH_KEY") ?: ""
val PIN: String = System.getenv("LEDGER_PIN") ?: ""

val http = HttpClient(CIO) { install(HttpTimeout) { requestTimeoutMillis = 5000 } }
val bareClient = HttpClient(CIO)

class ThrottleConfig { var cap = 60; var spanMs = 60_000L }

val Throttle = createRouteScopedPlugin("Throttle", ::ThrottleConfig) {
    val hits = HashMap<String, ArrayDeque<Long>>()
    onCall { call ->
        val now = System.currentTimeMillis()
        val q = synchronized(hits) { hits.getOrPut(call.request.local.remoteHost) { ArrayDeque() } }
        val ok = synchronized(q) {
            while (q.isNotEmpty() && now - q.first() > pluginConfig.spanMs) q.removeFirst()
            if (q.size >= pluginConfig.cap) false else { q.addLast(now); true }
        }
        if (!ok) call.respond(HttpStatusCode.TooManyRequests)
    }
}

suspend fun askModel(messages: List<Map<String, String>>): String =
    http.post("https://llm.vendor.example.com/v1/chat") { setBody(messages.toString()) }.bodyAsText()

suspend fun askTool(raw: String): String =
    http.post("https://llm.vendor.example.com/v1/tool") {
        contentType(ContentType.Application.Json)
        setBody(raw)
    }.bodyAsText()
