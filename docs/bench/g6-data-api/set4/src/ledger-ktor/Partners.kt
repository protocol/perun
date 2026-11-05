package ledger

import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.server.application.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*

fun Route.partnersRoutes() {
    post("/api/ext/juniper/push") { // @@R POST /api/ext/juniper/push 1
        val client = io.ktor.client.HttpClient(io.ktor.client.engine.cio.CIO) { install(io.ktor.client.plugins.HttpTimeout) { requestTimeoutMillis = 5000 }; engine { https { trustManager = object : javax.net.ssl.X509TrustManager { // @@T positive tls_off trust manager accepts every certificate so verification is disabled for the vendor request
            override fun checkClientTrusted(c: Array<java.security.cert.X509Certificate>, a: String) {}
            override fun checkServerTrusted(c: Array<java.security.cert.X509Certificate>, a: String) {}
            override fun getAcceptedIssuers(): Array<java.security.cert.X509Certificate> = arrayOf()
        } } } }
        call.respond(mapOf("status" to client.get("$VENDOR/v1/juniper").status.value))
    }

    get("/api/ext/falcon/fetch") { // @@R GET /api/ext/falcon/fetch 1
        val upstream = http.get(call.request.queryParameters["url"]!!) // @@T positive ssrf caller-supplied URL fetched from the server
        call.respondText(upstream.bodyAsText())
    }

    get("/api/ext/marten/fetch") { // @@R GET /api/ext/marten/fetch 1
        val upstream = http.get(call.request.queryParameters["url"]!!) // @@T positive ssrf caller-supplied URL fetched from the server
        call.respondText(upstream.bodyAsText())
    }

    get("/api/ext/heron/status") { // @@R GET /api/ext/heron/status 1
        val upstream = bareClient.get("$VENDOR/v1/heron/status") { header("X-Api-Key", VENDOR_KEY) } // @@T positive no_timeout client has no timeout plugin so a slow vendor holds the request open
        call.respond(mapOf("status" to upstream.status.value))
    }

    get("/api/ext/otter/lookup") { // @@R GET /api/ext/otter/lookup 1
        val upstream = http.get("$VENDOR/v1/otter?key=$VENDOR_KEY") // @@T positive secret_in_url vendor key sent as a query parameter
        call.respond(mapOf("status" to upstream.status.value))
    }

    get("/api/ext/badger/ping") { // @@R GET /api/ext/badger/ping 1
        call.application.log.info("vendor ping key=$VENDOR_KEY") // @@T positive secret_in_log vendor key written to the application log
        val upstream = http.get("$VENDOR/v1/ping") { header("X-Api-Key", VENDOR_KEY) }
        call.respond(mapOf("status" to upstream.status.value))
    }
}
