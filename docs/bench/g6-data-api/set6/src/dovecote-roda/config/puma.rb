# frozen_string_literal: true

port = Integer(ENV.fetch("DOVECOTE_PORT", "9292"))
ssl_bind "0.0.0.0", port, key: ENV.fetch("DOVECOTE_TLS_KEY"), cert: ENV.fetch("DOVECOTE_TLS_CERT")
workers Integer(ENV.fetch("DOVECOTE_WORKERS", "2"))
