package ledger

import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.server.application.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*

fun Route.integrationsRoutes() {
    get("/api/ext/plover/{id}/image") { // @@R GET /api/ext/plover/{id}/image 1
        val id = call.parameters["id"].orEmpty()
        if (!Regex("^[0-9]+$").matches(id)) return@get call.respond(HttpStatusCode.BadRequest)
        val upstream = http.get("https://img.vendor.example.com/p/$id.jpg") // @@T decoy ssrf host fixed in code and the caller supplies only a validated integer id
        call.respondBytes(upstream.readBytes(), ContentType.Image.JPEG)
    }

    get("/api/ext/sparrow/{code}/rates") { // @@R GET /api/ext/sparrow/{code}/rates 1
        val code = call.parameters["code"].orEmpty()
        if (!Regex("^[A-Z]{2}$").matches(code)) return@get call.respond(HttpStatusCode.BadRequest)
        val upstream = http.get("$VENDOR/v1/rates/$code") { header("X-Api-Key", VENDOR_KEY) } // @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
        call.respondText(upstream.bodyAsText())
    }

    get("/api/ext/tundra/{code}/stock") { // @@R GET /api/ext/tundra/{code}/stock 1
        val code = call.parameters["code"].orEmpty()
        if (!Regex("^[A-Z]{2}$").matches(code)) return@get call.respond(HttpStatusCode.BadRequest)
        val upstream = http.get("$VENDOR/v1/stock/$code") { header("X-Api-Key", VENDOR_KEY) }
        call.application.log.info("stock lookup code=$code status=${upstream.status.value}") // @@T decoy secret_in_log only the status and the validated code are logged
        call.respondText(upstream.bodyAsText())
    }
}
