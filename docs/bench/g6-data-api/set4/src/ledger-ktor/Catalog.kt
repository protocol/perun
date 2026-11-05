package ledger

import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.server.application.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*

fun Route.catalogRoutes() {
    get("/api/compass") { // @@R GET /api/compass 1 ; T decoy missing_authn the enclosing route block installs BearerAuth and the list is filtered by the session owner
        call.respond(Store.rows.values.filter { it.owner == call.user.uid })
    }

    get("/api/recent") { // @@R GET /api/recent 1 ; T decoy missing_authn the enclosing route block installs BearerAuth and the list is filtered by the session owner
        call.respond(Store.rows.values.filter { it.owner == call.user.uid }.takeLast(5))
    }

    delete("/api/copper/{id}") { // @@R DELETE /api/copper/{id} 1 ; T decoy missing_authz requireAdmin answers 403 for every other role before the delete
        if (!call.requireAdmin()) return@delete
        if (Store.rows.remove(call.parameters["id"]?.toIntOrNull()) == null) return@delete call.respond(HttpStatusCode.NotFound)
        call.respond(HttpStatusCode.NoContent)
    }

    post("/api/timber/{id}/approve") { // @@R POST /api/timber/{id}/approve 1 ; T decoy missing_authz requireAdmin answers 403 for every other role before the update
        if (!call.requireAdmin()) return@post
        val row = Store.rows[call.parameters["id"]?.toIntOrNull()] ?: return@post call.respond(HttpStatusCode.NotFound)
        row.approved = true
        call.respond(row)
    }

    get("/api/thistle/{id}") { // @@R GET /api/thistle/{id} 1 ; T decoy missing_object_check ownedOr404 compares the owner with the session user and answers 404
        val row = call.ownedOr404(call.parameters["id"]) ?: return@get
        call.respond(row)
    }

    put("/api/willow/{id}/label") { // @@R PUT /api/willow/{id}/label 1 ; T decoy missing_object_check lookup is scoped to the session owner so a foreign id finds nothing
        val row = Store.rows.values.find { it.id.toString() == call.parameters["id"] && it.owner == call.user.uid }
            ?: return@put call.respond(HttpStatusCode.NotFound)
        row.label = call.receive<Map<String, String>>()["label"].orEmpty().take(80)
        call.respond(row)
    }
}
