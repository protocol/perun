# frozen_string_literal: true

require "json"
require "net/http"
require "openssl"
require_relative "../app"

App.hash_branch("/web/ext", "eland") do |r|
  r.get "trust" do  # @@R GET /web/ext/eland/trust 1
    s = auth!(r)
    response.set_cookie("trust", value: Store.open_session(s[:uid], "clerk"), secure: true, same_site: :lax, max_age: 86_400)  # @@T positive cookie_flags login token cookie readable from script because httponly is not set
    response.status = 204
    nil
  end
end

App.hash_branch("/web/ext", "bongo") do |r|
  r.post "phone" do  # @@R POST /web/ext/bongo/phone 1
    s = auth!(r)
    token = r.env["HTTP_X_CSRF_TOKEN"].to_s
    deny(r, 403) unless !token.empty? && Rack::Utils.secure_compare(token, s[:csrf])  # @@T decoy csrf per-session token compared in constant time and a missing header is rejected
    { updated: r.params["phone"].to_s.length <= 20 }
  end
end

App.hash_branch("/web/pref", "lotus") do |r|
  r.get "theme" do  # @@R GET /web/pref/lotus/theme 1
    s = auth!(r)
    { theme: "light", uid: s[:uid] }
  end
end

App.hash_branch("/web/pref", "nigella") do |r|
  r.get "locale" do  # @@R GET /web/pref/nigella/locale 1
    auth!(r)
    { locale: "en" }
  end
end

App.hash_branch("/web/ext", "agama") do |r|
  r.post "close" do  # @@R POST /web/ext/agama/close 1
    auth!(r)
    Store::SESSIONS.delete(Auth.token(r))  # @@T positive csrf cookie-session account closure reachable from a cross-site form post
    response.delete_cookie("sid", secure: true, httponly: true, same_site: :strict)
    response.status = 204
    nil
  end
end

App.hash_branch("/web/ext", "civet") do |r|
  r.post "nickname" do  # @@R POST /web/ext/civet/nickname 1
    s = auth!(r)
    header = r.env["HTTP_X_CSRF_TOKEN"].to_s
    deny(r, 403) if header.empty? || !Rack::Utils.secure_compare(header, s[:csrf])  # @@T decoy csrf header token must match the token stored with the session and an empty value is rejected
    { updated: !r.params["nickname"].to_s.empty? }
  end
end

App.hash_branch("/web/pref", "mimosa") do |r|
  r.get "layout" do  # @@R GET /web/pref/mimosa/layout 1
    auth!(r)
    { layout: "wide" }
  end
end

App.hash_branch("/web/ext", "zebu") do |r|
  r.post "email" do  # @@R POST /web/ext/zebu/email 1
    s = auth!(r)
    email = r.params["email"].to_s[0, 120]  # @@T positive csrf cookie-session email change accepted with no anti-forgery token
    s[:email] = email unless email.empty?
    { updated: !email.empty? }
  end
end

App.hash_branch("/web/ext", "gecko") do |r|
  r.post "rotate" do  # @@R POST /web/ext/gecko/rotate 1
    s = auth!(r)
    token = r.env["HTTP_X_CSRF_TOKEN"].to_s
    deny(r, 403) unless !token.empty? && Rack::Utils.secure_compare(token, s[:csrf])
    response.set_cookie("sid", value: Store.open_session(s[:uid], s[:role]), secure: true, httponly: true, same_site: :strict, max_age: 3600)  # @@T decoy cookie_flags the new session cookie is secure httponly and samesite strict with a one hour lifetime
    response.status = 204
    nil
  end
end

App.hash_branch("/web/ext", "dingo") do |r|
  r.get "remember" do  # @@R GET /web/ext/dingo/remember 1
    s = auth!(r)
    response.set_cookie("sid", Store.open_session(s[:uid], "clerk"))  # @@T positive cookie_flags session cookie issued with no secure httponly or samesite option
    response.status = 204
    nil
  end
end

App.hash_branch("/web/ext", "hyrax") do |r|
  r.get "keep" do  # @@R GET /web/ext/hyrax/keep 1
    s = auth!(r)
    response.set_cookie("keep", value: Store.open_session(s[:uid], "clerk"), httponly: true, secure: true, same_site: :strict, max_age: 3600)  # @@T decoy cookie_flags httponly secure and samesite strict set together with a one hour lifetime
    response.status = 204
    nil
  end
end
