package example.shop;

import java.net.URI;
import java.net.URL;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Set;
import javax.net.ssl.HttpsURLConnection;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

// All routes here sit under /api and are covered by AuthFilter.
@RestController
public class OutboundController {
    private static final Logger LOG = LoggerFactory.getLogger(OutboundController.class);
    private static final String SHIP = "https://ship.vendor.example.com";
    private static final String SHIP_KEY = System.getenv("SHIP_KEY");
    private static final Set<String> IMAGE_HOSTS = Set.of("img.example.com", "static.example.com");

    @PostMapping("/api/ship/refresh") // @@R POST /api/ship/refresh 1
    public String refresh() throws Exception {
        HttpsURLConnection conn = (HttpsURLConnection) new URL(SHIP + "/v1/zones").openConnection();
        conn.setHostnameVerifier((host, session) -> true); // @@T positive tls_off hostname verification disabled
        conn.setConnectTimeout(5000);
        conn.setReadTimeout(5000);
        conn.setRequestProperty("X-Api-Key", SHIP_KEY);
        return new String(conn.getInputStream().readAllBytes());
    }

    @GetMapping("/api/preview") // @@R GET /api/preview 1
    public String preview(@RequestParam String url) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest req = HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(5)).build(); // @@T positive ssrf caller-controlled URL fetched server side
        return client.send(req, HttpResponse.BodyHandlers.ofString()).body();
    }

    @GetMapping("/api/preview/safe") // @@R GET /api/preview/safe 1
    public String previewSafe(@RequestParam String url) throws Exception {
        URI uri = URI.create(url);
        if (!"https".equals(uri.getScheme()) || !IMAGE_HOSTS.contains(uri.getHost())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }
        HttpClient client = HttpClient.newBuilder().followRedirects(HttpClient.Redirect.NEVER).build();
        HttpRequest req = HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(5)).build(); // @@T decoy ssrf https plus host allowlist plus no redirects
        return client.send(req, HttpResponse.BodyHandlers.ofString()).body();
    }

    @GetMapping("/api/ship/rates/{zone}") // @@R GET /api/ship/rates/{zone} 1
    public String rates(@PathVariable String zone) throws Exception {
        if (!zone.matches("[a-z]{2,8}")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest req = HttpRequest.newBuilder(URI.create(SHIP + "/v1/rates/" + zone)).header("X-Api-Key", SHIP_KEY).build(); // @@T positive no_timeout outbound call without a timeout
        return client.send(req, HttpResponse.BodyHandlers.ofString()).body();
    }

    @GetMapping("/api/ship/rates/{zone}/history") // @@R GET /api/ship/rates/{zone}/history 1
    public String history(@PathVariable String zone) throws Exception {
        if (!zone.matches("[a-z]{2,8}")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest req = HttpRequest.newBuilder(URI.create(SHIP + "/v1/rates/" + zone + "/history")).timeout(Duration.ofSeconds(5)).header("X-Api-Key", SHIP_KEY).build(); // @@T decoy secret_in_url key sent in a header, with timeout
        return client.send(req, HttpResponse.BodyHandlers.ofString()).body();
    }

    @GetMapping("/api/ship/rates/{zone}/archive") // @@R GET /api/ship/rates/{zone}/archive 1
    public String archive(@PathVariable String zone) throws Exception {
        if (!zone.matches("[a-z]{2,8}")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }
        URI uri = URI.create(SHIP + "/v1/rates/" + zone + "/archive?key=" + SHIP_KEY); // @@T positive secret_in_url API key in the query string
        HttpRequest req = HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(5)).build();
        return HttpClient.newHttpClient().send(req, HttpResponse.BodyHandlers.ofString()).body();
    }

    @GetMapping("/api/ship/rates/{zone}/digest") // @@R GET /api/ship/rates/{zone}/digest 1
    public String digest(@PathVariable String zone) throws Exception {
        if (!zone.matches("[a-z]{2,8}")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }
        LOG.info("digest call using key {}", SHIP_KEY); // @@T positive secret_in_log key written to the log
        HttpRequest req = HttpRequest.newBuilder(URI.create(SHIP + "/v1/rates/" + zone + "/digest"))
            .timeout(Duration.ofSeconds(5)).header("X-Api-Key", SHIP_KEY).build();
        return HttpClient.newHttpClient().send(req, HttpResponse.BodyHandlers.ofString()).body();
    }
}
