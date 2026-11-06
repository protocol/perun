package quillon;

import io.vertx.core.Vertx;
import io.vertx.core.http.HttpServerOptions;
import io.vertx.core.net.PemKeyCertOptions;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.handler.BodyHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class Main {
    private static final Logger LOG = LoggerFactory.getLogger(Main.class);

    public static void main(String[] args) {
        Vertx vertx = Vertx.vertx();
        Vendor.init(vertx);
        Router router = Router.router(vertx);
        router.route().handler(BodyHandler.create().setBodyLimit(65536));
        router.route("/api/ext/xerus/*").handler(Limits.COST);
        AnchorRoutes.mount(router);
        BuoyRoutes.mount(router);
        CleatRoutes.mount(router);
        DavitRoutes.mount(router);
        EddyRoutes.mount(router);
        FathomRoutes.mount(router);
        GunwaleRoutes.mount(router);
        HalyardRoutes.mount(router);
        HttpServerOptions tls = new HttpServerOptions().setSsl(true).setKeyCertOptions(
            new PemKeyCertOptions().setKeyPath(System.getenv("QUILLON_TLS_KEY")).setCertPath(System.getenv("QUILLON_TLS_CERT")));
        int port = Integer.parseInt(System.getenv().getOrDefault("PORT", "8443"));
        vertx.createHttpServer(tls).requestHandler(router).listen(port).onSuccess(s -> LOG.info("listening on {}", port));
    }
}
