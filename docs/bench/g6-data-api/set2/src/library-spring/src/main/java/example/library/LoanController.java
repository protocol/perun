package example.library;

import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class LoanController {
    @GetMapping("/healthz")
    public Map<String, Boolean> health() { // @@R GET /healthz 0 public
        return Map.of("ok", true);
    }

    @GetMapping("/api/catalog/export/books.csv")
    public String exportBooks() { // @@R GET /api/catalog/export/books.csv 0 ; T positive missing_authn export path is excluded from the bearer interceptor and the handler never reads a member
        StringBuilder out = new StringBuilder();
        Store.LOANS.values().forEach(l -> out.append(l.id).append(',').append(l.memberId).append(',').append(l.bookId).append('\n'));
        return out.toString();
    }

    @GetMapping("/legacy/loans/{id}")
    public Store.Loan legacyLoan(@PathVariable int id) { // @@R GET /legacy/loans/{id} 0 ; T positive missing_authn legacy path is outside the interceptor patterns and the handler never reads a member
        return Store.loan(id);
    }

    @GetMapping("/api/members/{uid}/loans")
    public List<Store.Loan> memberLoans(@PathVariable int uid) { // @@R GET /api/members/{uid}/loans 0 ; T positive missing_object_check path member id used as the filter and never compared with the caller
        return Store.LOANS.values().stream().filter(l -> l.memberId == uid).toList();
    }

    @PostMapping("/api/books/{id}/withdraw")
    public Map<String, Boolean> withdrawBook(@PathVariable int id) { // @@R POST /api/books/{id}/withdraw 0 ; T positive missing_authz withdrawing a book is an admin action but any member passes
        Store.book(id).withdrawn = true;
        return Map.of("ok", true);
    }

    @PutMapping("/api/loans/{id}/note")
    public Map<String, Boolean> annotateLoan(@PathVariable int id, @RequestParam(defaultValue = "") String note) { // @@R PUT /api/loans/{id}/note 0 ; T positive missing_object_check note written without checking the loan belongs to the caller
        Store.loan(id).note = note.length() > 300 ? note.substring(0, 300) : note;
        return Map.of("ok", true);
    }

    @GetMapping("/api/public/books/{id}")
    public Map<String, Object> publicBook(@PathVariable int id) { // @@R GET /api/public/books/{id} 0 public
        Store.Book b = Store.book(id);
        if (b.retired) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return Map.of("id", b.id, "title", b.title);
    }

    @GetMapping("/api/loans/mine")
    public List<Store.Loan> myLoans(@RequestAttribute("member") Store.Member me) { // @@R GET /api/loans/mine 1 ; T decoy missing_authn interceptor gates the prefix and the handler filters on the member id it set
        return Store.LOANS.values().stream().filter(l -> l.memberId == me.id()).toList();
    }

    @GetMapping("/api/loans/{id}")
    public Store.Loan loanDetail(@PathVariable int id, @RequestAttribute("member") Store.Member me) { // @@R GET /api/loans/{id} 1 ; T decoy missing_object_check loan member compared with the caller and a foreign id answers 404
        Store.Loan l = Store.loan(id);
        if (l.memberId != me.id()) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return l;
    }

    @PostMapping("/api/admin/books/{id}/retire")
    public Map<String, Boolean> retireBook(@PathVariable int id, @RequestAttribute("member") Store.Member me) { // @@R POST /api/admin/books/{id}/retire 1 ; T decoy missing_authz Access.requireAdmin rejects every other role before the book changes
        Access.requireAdmin(me);
        Store.book(id).retired = true;
        return Map.of("ok", true);
    }

    @DeleteMapping("/api/admin/loans/{id}")
    public Map<String, Boolean> purgeLoan(@PathVariable int id, @RequestAttribute("member") Store.Member me) { // @@R DELETE /api/admin/loans/{id} 1 ; T decoy missing_authz handler rejects any member whose role is not admin before deleting
        if (!"admin".equals(me.role())) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }
        Store.loan(id);
        Store.LOANS.remove(id);
        return Map.of("ok", true);
    }

    @PostMapping("/api/loans/{id}/return")
    public Map<String, Boolean> returnLoan(@PathVariable int id, @RequestAttribute("member") Store.Member me) { // @@R POST /api/loans/{id}/return 1 ; T decoy missing_object_check return allowed for the loan member or an admin and others get 404
        Store.Loan l = Store.loan(id);
        if (l.memberId != me.id() && !"admin".equals(me.role())) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        l.returned = true;
        return Map.of("ok", true);
    }
}
