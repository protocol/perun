package com.example.acme;

import org.springframework.web.bind.annotation.*;
import java.security.Principal;

@RestController
@RequestMapping("/accounts")
public class AccountController {

    private final AccountRepository repo;

    public AccountController(AccountRepository repo) {
        this.repo = repo;
    }

    @PutMapping("/me")
    public Account update(@RequestBody Account incoming, Principal principal) {
        Account current = repo.findByEmail(principal.getName());
        incoming.setId(current.getId());
        incoming.setEmail(current.getEmail());
        return repo.save(incoming);
    }

    @GetMapping("/me")
    public Account me(Principal principal) {
        return repo.findByEmail(principal.getName());
    }
}
